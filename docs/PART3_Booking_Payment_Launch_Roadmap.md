# PART 3 — Booking + Payment + Notifications + Launch

> Prerequisite: **Part 1 and Part 2 are complete** (auth, locations, turfs, schedule, pricing, slot engine, search, admin approval).
> Work on **ONE STEP at a time**. After each step: stop, report, wait for approval.

---

## 0. Project Context (same in all 3 parts)

**Product:** Turf Booking Platform for Bangladesh. A booking is confirmed only after a verified **15% advance** payment.

**Roles:** `customer`, `owner`, `admin`

**Stack:** Python 3.11+, Django 5.x, DRF, PostgreSQL, simplejwt, drf-spectacular. **Added now:** Redis, Celery (+ beat), SSLCommerz, gunicorn, Docker.

**Critical rules (never break)**
1. **No double booking — enforced by a PostgreSQL exclusion constraint.** Redis lock is only a helper, the DB is the source of truth.
2. **Payment is authoritative:** only a server-verified successful payment confirms a booking. Never trust the browser redirect alone.
3. Temporary lock window is configurable (default 10 min).
4. Money: `Decimal`, BDT. Advance = 15% (configurable setting, default 15). Remaining = total − advance.
5. Timezone `Asia/Dhaka`.
6. Backend authorization on every owner/admin endpoint. Audit-log critical actions.

**Agent rules**
- Do only the step requested. Comment code for a DRF beginner.
- Never put real API keys in code. Use `.env` and SSLCommerz **sandbox** only.
- Report files changed + how to verify after each step.

---

## 1. Goal of Part 3

Complete booking flow (guest + registered), temporary slot locking, 15% advance payment with gateway verification, expiry handling, notifications, cancellation/refund, reviews, owner/admin dashboards, security hardening, tests and deployment.

---

## 2. Folder Changes (on top of Part 2)

```
backend/
├── apps/
│   ├── bookings/
│   │   ├── models.py        # Booking, BookingSlot (+ exclusion constraint), Review
│   │   ├── services/
│   │   │   ├── create_booking.py
│   │   │   ├── locking.py       # Redis helper
│   │   │   ├── cancellation.py
│   │   │   └── codes.py         # booking ID generator
│   │   ├── tasks.py             # Celery: expire pending bookings, reminders
│   │   ├── serializers.py, views.py, urls.py, admin.py
│   │   └── tests/ (incl. test_concurrency.py)
│   ├── payments/
│   │   ├── models.py            # Payment, Refund
│   │   ├── gateways/
│   │   │   ├── base.py
│   │   │   └── sslcommerz.py
│   │   ├── services.py, views.py (init, success, fail, cancel, ipn), urls.py
│   │   └── tests/
│   ├── notifications/           # NEW app
│   │   ├── models.py, services.py, tasks.py, backends/(console, sms, email)
│   └── core/
│       ├── models.py            # PlatformSetting, AuditLog
│       └── audit.py
├── config/
│   ├── celery.py
│   └── settings/prod.py         # security settings
├── Dockerfile
docker-compose.yml               # + redis, celery worker, celery beat
docker-compose.prod.yml          # (optional)
nginx/                           # sample config
```

---

## 3. New Dependencies

`requirements/base.txt` (add)
```
redis>=5.0
django-redis>=5.4
celery>=5.3
django-celery-beat>=2.6
requests>=2.31
```
`requirements/prod.txt` (add)
```
gunicorn
whitenoise
sentry-sdk
```
Dev (add): `pytest-mock`, `responses` (mock gateway HTTP calls).
Infra: Redis 7 container (add to `docker-compose.yml`).

---

## 4. Data Model (summary)

**Booking (complete)**
`booking_code` (unique, human-friendly e.g. `TRF-20261020-7K3Q`), `turf`, `customer` (nullable for guests), `guest_name`, `guest_phone`, `emergency_phone`, `date`, `total_amount`, `advance_percent`, `advance_amount`, `remaining_amount`, `status` (`pending_payment | confirmed | completed | cancelled | no_show | refunded`), `cancel_reason`, `expires_at`, `created_at`, `confirmed_at`.

**BookingSlot**
`booking`, `turf`, `start_at`, `end_at`, `price`, `is_active`.
**DB constraint (the anti-double-booking guarantee):**
```python
# migration 1: BtreeGistExtension()  (django.contrib.postgres.operations)
ExclusionConstraint(
    name="no_overlapping_active_slots",
    expressions=[
        ("turf", RangeOperators.EQUAL),
        (TsTzRange("start_at", "end_at", RangeBoundary()), RangeOperators.OVERLAPS),
    ],
    condition=Q(is_active=True),
)
```
`is_active=False` when a booking expires/cancels, so the slot becomes free again.

**Payment:** `booking`, `provider` (`sslcommerz`), `tran_id` (unique), `amount`, `currency`, `status` (`pending | paid | failed | refunded`), `val_id`, `gateway_payload` (JSON), `paid_at`, timestamps.

**Refund:** `payment`, `amount`, `status` (`pending | processed | failed`), `reason`, `processed_by`, timestamps.

**PlatformSetting (key/value, admin-editable):** `advance_percent`, `slot_lock_minutes`, cancellation rules (below).

**CancellationRule:** `hours_before_start` (min), `refund_percent`. Example: ≥24h → 100%, 6–24h → 50%, <6h → 0%. (Configurable, not hard-coded.)

**Notification:** `user` (nullable), `phone/email`, `channel` (`sms|email`), `template`, `payload`, `status`, `sent_at`, `error`.

**Review:** `booking` (OneToOne), `turf`, `customer`, `rating` (1–5), `comment` (optional), `is_hidden` (moderation).

**AuditLog:** `actor`, `action`, `object_type`, `object_id`, `before/after` (JSON), `ip`, `created_at`.

**Dispute:** `booking`, `raised_by`, `description`, `status`, `resolution`.

---

## 5. Steps

### STEP 1 — Infrastructure: Redis + Celery
- Add Redis to `docker-compose.yml`; configure `django-redis` cache.
- `config/celery.py`, load in `config/__init__.py`; `django-celery-beat` installed.
- Sample task + beat schedule works.

**Done when:** a test Celery task runs through the worker.

### STEP 2 — Booking models + exclusion constraint
- Complete `Booking`, `BookingSlot`; add `BtreeGistExtension` migration first, then the constraint migration.
- `PlatformSetting` (+ seed defaults: advance 15, lock 10 min).
- `codes.py` booking code generator (collision-safe).
- Test with **raw DB-level insert** that two overlapping active slots for the same turf raise `IntegrityError`.

### STEP 3 — Create-booking service & API
`POST /api/v1/bookings/` (guest OR authenticated customer)
Request: `turf`, `date`, `slots: [start_at, ...]`, `full_name`, `phone`, `emergency_phone`.
Service logic inside `transaction.atomic()`:
1. Validate turf is `approved`, date not past.
2. **Re-generate slots server-side** using the Part 2 engine; every requested slot must be currently `available`. **Never trust price/amount from the client.**
3. Compute `total`, `advance` (15%, rounded to 2 dp), `remaining`.
4. Create `Booking(status=pending_payment, expires_at=now+lock_minutes)` + `BookingSlot` rows.
5. Catch `IntegrityError` from the exclusion constraint → return **HTTP 409** ("slot just taken").
6. (Optional fast path) Redis `SET NX EX` lock per slot to reject obvious races early; never rely on it alone.
Validate BD phone numbers; max slots per booking (setting).

### STEP 4 — Payment initiation (SSLCommerz sandbox)
- `gateways/base.py` interface (`initiate`, `verify`, `refund`) so bKash/Nagad can be added later.
- `gateways/sslcommerz.py`: init session call with `tran_id`, amount = **advance_amount**, success/fail/cancel/ipn URLs, customer info.
- `POST /api/v1/payments/initiate/` → body: `booking_code` → returns `payment_url` (GatewayPageURL).
- Only for `pending_payment` and non-expired bookings. Creates `Payment(status=pending)`.
- Env: `SSLCOMMERZ_STORE_ID`, `SSLCOMMERZ_STORE_PASSWORD`, `SSLCOMMERZ_SANDBOX=True`.

### STEP 5 — Payment verification (the critical step)
- Endpoints: success/fail/cancel (browser redirects) and **IPN** (server-to-server POST).
- On success or IPN: **call SSLCommerz Validation API with `val_id`**; confirm `status` VALID/VALIDATED, `tran_id` matches, `amount` equals expected advance, `currency` BDT.
- Then, in `transaction.atomic()` + `select_for_update()`: set `Payment=paid`, `Booking=confirmed`, `confirmed_at`. **Idempotent** (IPN may arrive multiple times).
- Late payment after expiry: if slots are still free → confirm; otherwise mark payment for refund + flag for admin.
- Fail/cancel → `Payment=failed`; booking stays pending until expiry (or release immediately on cancel).
- Save raw gateway payload; log to AuditLog.

### STEP 6 — Expiry & slot release (Celery beat)
- Task every minute: bookings `pending_payment` with `expires_at < now` → `status=cancelled` (reason `expired`), `BookingSlot.is_active=False`.
- Reminder task: bookings starting in ~2h (confirmed) → queue notification.

### STEP 7 — Customer booking APIs
- `GET /api/v1/bookings/my/?tab=upcoming|past|cancelled` (auth)
- `GET /api/v1/bookings/{booking_code}/` (owner of booking; admin)
- **Guest lookup:** `POST /api/v1/bookings/lookup/` with `booking_code` + `phone` → returns booking (rate-limited).
- Fields shown: booking ID, slots, total, advance paid, remaining, status.
- `GET /api/v1/payments/my/` payment history.
- Link guest bookings to an account when a user registers with the same phone (optional, MVP-safe version).

### STEP 8 — Notifications
- `notifications` app with backend abstraction: `console` (dev), `email` (Django email / Resend SMTP), `sms` (adapter for a BD SMS gateway, keep provider swappable).
- Celery tasks send: booking confirmation, payment confirmation, reminder, cancellation/refund, **new booking to owner**, booking change.
- Store every attempt in `Notification` with status/error. Never block the request thread.

### STEP 9 — Cancellation & refund
- `CancellationRule` + admin-editable settings (no hard-coded rules).
- `POST /bookings/{code}/cancel/` → compute refund % from rules and time-to-start; create `Refund(pending)`; booking `cancelled`; slots released.
- Owner-initiated cancellation → 100% refund path.
- Admin refund management: list refunds, mark processed (and gateway refund call if supported), booking → `refunded`.
- Notification on each state change.

### STEP 10 — Owner dashboard APIs
- `/owner/bookings/` (filter by turf/date/status), booking detail with customer contact.
- `/owner/dashboard/` revenue overview (today/week/month, per turf), upcoming bookings, history.
- Owner can mark `completed` / `no_show` after the slot time.
- Strictly scoped to the owner's own turfs.

### STEP 11 — Reviews
- `POST /api/v1/reviews/` only if booking is `completed` and belongs to the customer; one review per booking; rating 1–5.
- Public: list reviews per turf + average rating on turf detail/search.
- Admin: hide/remove review.

### STEP 12 — Admin dashboard & management
- `GET /api/v1/admin/stats/` (users, turfs by status, bookings, revenue, pending approvals).
- Django Admin: Bookings, Payments, Refunds, Reviews, Disputes, PlatformSettings, CancellationRules, AuditLogs (read-only).
- Customer/owner management (activate/deactivate), basic reports (date range).
- `AuditLog` written for: turf approval/suspension, refunds, payment status changes, cancellations, setting changes.

### STEP 13 — Security hardening
- DRF throttling (anon/user + stricter on login, booking lookup, payment init).
- Prod settings: `SECURE_SSL_REDIRECT`, secure cookies, HSTS, `X-Frame-Options`, strict `ALLOWED_HOSTS`, strict CORS/CSRF origins.
- Password hashing (Django default Argon2/PBKDF2), password validators.
- Check: input validation on all serializers; no raw SQL with user input; every owner/admin view has permission + queryset scoping; no sensitive data in logs.
- `python manage.py check --deploy` clean.

### STEP 14 — Testing
Must include:
- **Concurrency test** (`TransactionTestCase` + threads): N parallel create-booking requests for the same slot → exactly one succeeds, others 409.
- Expiry releases slots; late/duplicate IPN is idempotent; amount mismatch rejected; fake `val_id` rejected (mock gateway with `responses`).
- Advance calculation: 2h × ৳1,500 = ৳3,000 → advance ৳450, remaining ৳2,550.
- Guest vs registered booking; permission tests per role; cancellation refund tiers.

### STEP 15 — Deployment
- `Dockerfile` (gunicorn), `docker-compose.prod.yml` (web, db, redis, celery worker, celery beat, nginx).
- Env-based config, `collectstatic`, WhiteNoise or nginx static, media on Cloudinary/S3.
- Sentry, DB backups, HTTPS (Let's Encrypt), health check endpoint `/health/`.
- Deployment guide in README (VPS or Railway/Render).
- Production SSLCommerz credentials only after sandbox end-to-end test passes.

### STEP 16 — Beta launch checklist
- Onboard 3–5 real turfs, test real small-amount payments, monitor errors, collect feedback.
- Then start the **Frontend phase (Next.js + Tailwind)** against the Swagger API.

---

## 6. Definition of Done (Part 3)
- [ ] Overlapping bookings rejected by the DB constraint (concurrency test passes)
- [ ] Guest + registered booking works; booking ID generated
- [ ] 15% advance computed server-side; payment verified via gateway validation API
- [ ] Booking confirms only after verified payment; IPN idempotent
- [ ] Unpaid bookings auto-expire and release slots
- [ ] Notifications sent via Celery (console/email/SMS adapter)
- [ ] Configurable cancellation/refund with tracking
- [ ] Owner dashboard + admin management + audit logs
- [ ] Reviews only after completed bookings
- [ ] `check --deploy` clean; deployed with HTTPS

## 7. Agent Prompt Template
```
Read docs/PART3_Booking_Payment_Launch_Roadmap.md fully. Parts 1 and 2 are complete.
Execute ONLY "STEP <N>". Follow the data model, folder structure and critical rules.
Use SSLCommerz sandbox only; no real credentials in code. When done, list files
changed, commands to run, and how I can verify. Then wait.
```
