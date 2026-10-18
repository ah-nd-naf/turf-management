# PART 2 — Core Business (Turf + Schedule + Pricing + Slot Engine + Search + Approval)

> Prerequisite: **Part 1 is complete** (custom User, OwnerProfile, Division/District seeded, JWT auth, role permissions).
> Work on **ONE STEP at a time**. After each step: stop, report, wait for approval.

---

## 0. Project Context (same in all 3 parts)

**Product:** Turf Booking Platform for Bangladesh. Customers search turfs by Division → District → Date → optional preferred time, pick slots, and confirm a booking by paying a **15% advance**. Turf Owners manage turfs/schedule/pricing/bookings. Super Admin manages the platform.

**Roles:** `customer`, `owner`, `admin`

**Stack:** Python 3.11+, Django 5.x, DRF, PostgreSQL, simplejwt, drf-spectacular. (Redis/Celery/SSLCommerz come in Part 3.)

**Critical rules (never break)**
1. No double booking — enforced at DB level (Part 3).
2. Owner controls schedule; customer never defines operating hours.
3. Same Division → District data for turf registration AND customer search.
4. Availability is dynamic: schedule + slot duration + bookings + blocked periods. **Slots are NOT stored in DB; they are generated on demand.**
5. Only verified payment confirms a booking.
6. New turfs are `pending_approval` until an admin approves; only `approved` turfs are public.
7. Timezone `Asia/Dhaka`; money in `DecimalField` (BDT).

**Agent rules**
- Do only the step requested. No features from Part 3 (payments, Redis, Celery, notifications).
- Comment code for a DRF beginner. Report files changed + how to verify after each step.

---

## 1. Goal of Part 2

Owners can create turfs, configure operating hours, slot duration, pricing, exceptions and blocks, and submit for approval. Admin can approve/reject/suspend. Customers can search turfs by Division/District/date/preferred time/name and see slot-level availability. Available turfs are listed above unavailable ones.

---

## 2. Folder Changes (on top of Part 1)

```
backend/apps/
├── turfs/
│   ├── models.py          # Turf, TurfImage, TurfSchedule, ScheduleException, PricingRule, BlockedPeriod
│   ├── serializers/       # owner.py, admin.py, public.py
│   ├── views/             # owner.py, admin.py, public.py
│   ├── services/
│   │   ├── slots.py       # ★ slot generation engine
│   │   ├── pricing.py     # price resolution
│   │   └── search.py      # search + sorting logic
│   ├── filters.py
│   ├── permissions.py
│   ├── urls.py
│   ├── admin.py
│   └── tests/
│       ├── test_slots.py
│       ├── test_pricing.py
│       ├── test_search.py
│       └── test_owner_api.py
└── bookings/
    └── models.py          # MINIMAL Booking + BookingSlot only (needed to compute availability)
```

---

## 3. New Dependencies

```
django-storages>=1.14        # image storage abstraction
cloudinary>=1.40             # or boto3 for S3 — choose ONE
django-cloudinary-storage    # only if Cloudinary chosen
```
(`Pillow`, `django-filter` already installed in Part 1.)
Dev/local: start with local `MEDIA_ROOT`; switch to Cloudinary/S3 via env flag.

---

## 4. Data Model (summary)

**Turf**
`owner` (FK User, role=owner), `name`, `slug`, `address`, `division` (FK), `district` (FK), `latitude`, `longitude`, `google_maps_url` (auto-built from lat/lng if empty), `turf_type` (5v5, 6v6, 7v7, 8v8, 9v9, 11v11, other), `contact_person_name`, `contact_number`, `description`, `sports_supported`, `is_indoor`, `surface`, amenities (`has_parking`, `has_changing_room`, `has_washroom`, `has_floodlights`, `has_seating`, `has_drinking_water`), `slot_duration_minutes` (30/60/90/120/custom int), `status` (`draft | pending_approval | approved | rejected | suspended`), `rejection_reason`, `created_at`, `updated_at`.
Validate: district must belong to selected division; lat/lng in Bangladesh range.

**TurfImage:** `turf`, `image`, `is_cover`, `order`.

**TurfSchedule (weekly):** `turf`, `weekday` (0–6; use Saturday-first display in UI), `open_time`, `close_time`, `is_closed`. Unique (`turf`, `weekday`).
⚠️ **Midnight rule:** `close_time = 00:00` means *midnight at end of that day* (i.e. 24:00). Handle explicitly in the slot engine.

**ScheduleException:** `turf`, `date`, `exception_type` (`closed | special_hours | maintenance`), `open_time`, `close_time` (nullable), `reason`.

**PricingRule:** `turf`, `price` (Decimal), `weekday` (nullable), `start_time` (nullable), `end_time` (nullable), `priority` (int), `rule_type` (`default | time_based | special` — "special" reserved for future event pricing), `valid_from/valid_to` (nullable).
One `default` rule per turf is required before submission.

**BlockedPeriod:** `turf`, `start_at`, `end_at` (aware datetimes), `block_type` (`blocked | maintenance`), `reason`, `created_by`.

**Booking (MINIMAL — completed in Part 3):**
`booking_code`, `turf`, `customer` (nullable), `guest_name`, `guest_phone`, `emergency_phone`, `date`, `total_amount`, `status`.
**BookingSlot:** `booking` (FK), `turf` (FK), `start_at`, `end_at`, `price`, `is_active`.
> Only create what is needed so availability can read existing bookings. DB exclusion constraint, payment, locking → Part 3.

---

## 5. Steps

### STEP 1 — Turf model + owner CRUD
- Models: `Turf`, `TurfImage` (+ migrations).
- Owner API: `/api/v1/owner/turfs/` (list/create/retrieve/update/partial_update). **Queryset filtered to `request.user` only.** One owner can have many turfs.
- Slug auto-generated; `google_maps_url` auto-generated from lat/lng.
- New turf starts as `draft`.
- Image upload endpoint `/owner/turfs/{id}/images/` (max file size + type validation).

**Done when:** owner A cannot see/edit owner B's turf (tested).

### STEP 2 — Operating schedule + exceptions
- `TurfSchedule`, `ScheduleException` models.
- Endpoints: `/owner/turfs/{id}/schedule/` (GET + PUT for all 7 days in one request), `/owner/turfs/{id}/exceptions/` (CRUD).
- Validation: `open < close` (except close = 00:00), no duplicate weekday, exception date not in the past.

**Done when:** owner can save the weekly schedule from the PDF example (Sat 8AM–12AM … Mon 10AM–11PM).

### STEP 3 — Slot duration + pricing
- `slot_duration_minutes` set via turf update (allowed: 30, 60, 90, 120, custom ≥ 15).
- `PricingRule` model + `/owner/turfs/{id}/pricing-rules/` CRUD.
- `services/pricing.py`: `get_price(turf, slot_start)` → picks the best rule: matching special > time_based (highest priority, matching weekday/time) > default.
- Validation: no overlapping time-based rules with equal priority on same weekday.

**Done when:** 6–7 PM = ৳1,500 and 8–9 PM = ৳1,800 with default ৳1,200 resolves correctly (unit tests).

### STEP 4 — Blocked/maintenance periods
- `BlockedPeriod` model + `/owner/turfs/{id}/blocked-periods/` CRUD.
- Overlap with an existing confirmed booking should be rejected (or warn) — implement a check using minimal Booking model.

### STEP 5 — ★ Slot generation engine (most important step)
`services/slots.py`

```python
@dataclass
class Slot:
    start_at: datetime   # aware, Asia/Dhaka
    end_at: datetime
    price: Decimal
    status: str          # available | booked | payment_pending | closed | maintenance | past

def get_slots_for_date(turf, date) -> list[Slot]: ...
def get_slots_bulk(turfs, date) -> dict[turf_id, list[Slot]]: ...   # for search, avoids N+1
```
Algorithm:
1. Find operating window: `ScheduleException` for that date overrides weekly `TurfSchedule`. Closed day → no slots (status `closed`).
2. Generate slots from `open_time` using `slot_duration_minutes`; a slot is valid only if its end ≤ close (treat 00:00 close as next-day midnight).
3. Attach price via `pricing.get_price`.
4. Mark status: `booked` (active BookingSlot, confirmed), `payment_pending` (BookingSlot in pending_payment & not expired — placeholder until Part 3), `maintenance` (BlockedPeriod overlap), `past` (today and start ≤ now).
5. `get_slots_bulk` must fetch bookings/blocks/schedules for all turfs with **a constant number of queries**.

Unit tests (`test_slots.py`) must cover: normal day, midnight close, 1.5h duration with leftover time, exception closure, special hours, blocked slot, booked slot, past slot today, price per slot.

**Done when:** all tests pass; engine has no DB writes.

### STEP 6 — Public turf detail + slots API
- `GET /api/v1/turfs/{slug}/` — only `approved` turfs (others 404). Includes address, map link, lat/lng, amenities, images, contact (decide: show contact number publicly — yes per spec).
- `GET /api/v1/turfs/{slug}/slots/?date=YYYY-MM-DD` — returns slot list with status + price.

### STEP 7 — Search API
`GET /api/v1/turfs/search/`
| Param | Required | Notes |
|---|---|---|
| `division` | yes | id or slug |
| `district` | yes | must belong to the division |
| `date` | yes | not in the past |
| `from_time` | no | e.g. `18:00` — only slots starting at/after it count |
| `q` | no | turf name (icontains); works alone or with others |

Response: `{ "available": [...], "unavailable": [...] }`, each turf with `availability` = `available | partially_available | unavailable`, matching slots, `min_price`, cover image.
- `available` = at least one bookable slot matching criteria; **partially_available** = some booked, some free (show both).
- Unavailable turfs must still be returned (fully booked / closed / no slot after from_time).
- Only `approved` turfs. Paginate sensibly. Use `get_slots_bulk`.

**Done when:** the PDF example (Dhaka/Dhaka, 20 Oct, from 6 PM) returns correct grouping in tests.

### STEP 7.5 — Submit for approval (owner side)
- `POST /owner/turfs/{id}/submit/` → only from `draft` or `rejected`. Requires: basic info, location, schedule for ≥1 day, slot duration, default price. Sets `pending_approval`.
- Editing critical fields of an approved turf: decide policy (simple MVP: allowed, logged).

### STEP 8 — Admin approval APIs
- `GET /api/v1/admin/turfs/?status=pending_approval`
- `POST /admin/turfs/{id}/approve/`, `/reject/` (reason required), `/suspend/` (reason), `/unsuspend/`
- Admin only (`IsAdminRole`). Record who/when (simple `reviewed_by`, `reviewed_at` fields; full audit log in Part 3).

### STEP 9 — Django Admin for Turf module
- Register Turf (list: name, owner, district, status; filters; actions: approve/reject/suspend), schedules/pricing/blocked as inlines, images inline.

### STEP 10 — Tests, docs, wrap-up
- Owner isolation tests, status-flow tests, search tests, slot tests.
- Swagger tags: Owner / Public / Admin.
- Seed command `seed_demo_turfs` (optional): 3–5 demo turfs in Dhaka for manual testing.
- Commit: `part-2-core-business`.

---

## 6. Definition of Done (Part 2)
- [ ] Owner can create/manage multiple turfs, only their own
- [ ] Weekly schedule + exceptions + slot duration + pricing rules work
- [ ] Slot engine generates correct slots (midnight, 1.5h, exceptions covered by tests)
- [ ] Blocked/maintenance periods affect availability
- [ ] Search returns Available above Unavailable, partial availability shown
- [ ] Only approved turfs are public
- [ ] Admin approve/reject/suspend works via API and Django Admin
- [ ] Constant-query bulk availability for search
- [ ] All tests pass

## 7. Agent Prompt Template
```
Read docs/PART2_Core_Business_Roadmap.md fully. Part 1 is already complete.
Execute ONLY "STEP <N>". Follow the data model, folder structure and critical rules.
Do not implement payments, Redis, Celery or notifications. When done, list files
changed, commands to run, and how I can verify. Then wait.
```
