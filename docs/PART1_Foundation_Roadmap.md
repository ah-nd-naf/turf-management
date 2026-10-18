# PART 1 — Foundation (Setup + Data + Auth)

> Upload this file to your Gemini project / give it to the Antigravity agent.
> Work on **ONE STEP at a time**. After each step: stop, report what was done, wait for approval.

---

## 0. Project Context (same in all 3 parts)

**Product:** Turf Booking Platform for Bangladesh. Customers search turfs by Division → District → Date → optional preferred time, pick slots, and confirm a booking by paying a **15% advance**. Turf Owners manage turfs/schedule/pricing/bookings. Super Admin manages the whole platform.

**Roles:** `customer`, `owner`, `admin`

**Stack**
| Layer | Choice |
|---|---|
| Backend | Python 3.11+, Django 5.x, Django REST Framework |
| DB | PostgreSQL 15+ |
| Auth | JWT (`djangorestframework-simplejwt`) |
| API docs | `drf-spectacular` (Swagger) |
| Later (Part 3) | Redis, Celery, SSLCommerz |
| Frontend | Next.js + Tailwind (separate phase, NOT now) |

**Critical rules (never break)**
1. No double booking — enforced at DB level (Part 3).
2. Owner controls schedule; customer never defines operating hours.
3. Same Division → District data is used for turf registration AND customer search.
4. Availability is calculated dynamically (schedule + slot config + bookings + blocks).
5. Only verified payment confirms a booking.
6. New turfs need admin approval before public listing.
7. Timezone: `Asia/Dhaka`, `USE_TZ = True`. Currency: BDT, use `DecimalField` (never float).

**Agent rules**
- Do only the step requested. Do not build features from later parts.
- Add short comments/docstrings so a DRF beginner can follow the code.
- After each step, list: files created/changed, commands run, how to verify.
- Never commit secrets. Use `.env`.

---

## 1. Goal of Part 1

A running Django + DRF backend connected to PostgreSQL with:
custom User model, role-based JWT auth, Division/District data (8 + 64) seeded, shared permissions, Django Admin working, Swagger docs, and a few tests.

**Prerequisites on the machine:** Python 3.11+, Git, PostgreSQL (or Docker), VS Code.

---

## 2. Target Folder Structure (end of Part 1)

```
turf-booking/
├── backend/
│   ├── manage.py
│   ├── config/
│   │   ├── __init__.py
│   │   ├── settings/
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   ├── dev.py
│   │   │   └── prod.py
│   │   ├── urls.py
│   │   ├── asgi.py
│   │   └── wsgi.py
│   ├── apps/
│   │   ├── __init__.py
│   │   ├── core/          # shared permissions, base models, utils
│   │   ├── accounts/      # User, OwnerProfile, auth APIs
│   │   ├── locations/     # Division, District, seed data
│   │   ├── turfs/         # (empty stub — Part 2)
│   │   ├── bookings/      # (empty stub — Part 3)
│   │   └── payments/      # (empty stub — Part 3)
│   ├── requirements/
│   │   ├── base.txt
│   │   ├── dev.txt
│   │   └── prod.txt
│   ├── pytest.ini
│   └── .env.example
├── docs/
│   └── (put these 3 roadmap files here)
├── docker-compose.yml     # postgres (redis added in Part 3)
├── .gitignore
└── README.md
```

---

## 3. Dependencies

`requirements/base.txt`
```
Django>=5.0,<5.2
djangorestframework>=3.15
djangorestframework-simplejwt>=5.3
psycopg[binary]>=3.1
django-environ>=0.11
drf-spectacular>=0.27
django-cors-headers>=4.3
django-filter>=24.1
Pillow>=10.0
```
`requirements/dev.txt`
```
-r base.txt
pytest
pytest-django
factory-boy
ruff
black
```
`requirements/prod.txt`
```
-r base.txt
gunicorn
```

---

## 4. Steps

### STEP 1 — Repo & environment
- Create root `turf-booking/`, `git init`, `.gitignore` (Python, venv, `.env`, `__pycache__`, media).
- Create `backend/`, virtualenv (`python -m venv venv`), install `requirements/dev.txt`.
- Create `README.md` with setup instructions.

**Done when:** `pip list` shows Django, DRF, simplejwt, psycopg.

### STEP 2 — Django project & settings
- `django-admin startproject config .` inside `backend/`.
- Split settings into `base.py / dev.py / prod.py`; `manage.py` defaults to `config.settings.dev`.
- Load env vars with `django-environ` (`SECRET_KEY`, `DEBUG`, `DATABASE_URL`, `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`).
- Set `TIME_ZONE = "Asia/Dhaka"`, `USE_TZ = True`.
- Configure `REST_FRAMEWORK`: JWT auth default, `IsAuthenticated` default? (use `AllowAny` default + explicit per view), pagination (PageNumber, size 20), `DEFAULT_SCHEMA_CLASS = drf_spectacular...`, filter backends.
- Add `.env.example`.

**Done when:** `python manage.py check` passes.

### STEP 3 — PostgreSQL connection
- `docker-compose.yml` with `postgres:15` (db `turf_db`, volume) OR guide for local Postgres.
- Set `DATABASE_URL` in `.env`.
- ⚠️ **Do NOT run `migrate` yet** (custom User model must exist first).

**Done when:** Django can connect (`python manage.py dbshell` works).

### STEP 4 — Create apps
- Create apps inside `backend/apps/`: `core, accounts, locations, turfs, bookings, payments`.
- Set each `AppConfig.name = "apps.<name>"`; register in `INSTALLED_APPS`.
- `turfs`, `bookings`, `payments` stay empty stubs for now.

**Done when:** `manage.py check` passes with all apps registered.

### STEP 5 — Custom User model (BEFORE first migrate)
In `accounts`:
- `User` (extends `AbstractBaseUser` + `PermissionsMixin`):
  `phone_number` (unique, USERNAME_FIELD, BD format `01XXXXXXXXX`), `email` (optional, unique if set), `full_name`, `role` (`customer|owner|admin`, default `customer`), `is_active`, `is_staff`, `created_at`, `updated_at`.
- Custom `UserManager` with `create_user` and `create_superuser` (superuser gets role `admin`).
- `OwnerProfile` (OneToOne to User): `business_name`, `nid_number` (optional), `address` (optional), `is_verified` (default False).
- `AUTH_USER_MODEL = "accounts.User"` in settings.
- Run `makemigrations` then `migrate`. Create superuser.

**Done when:** `migrate` succeeds and superuser can be created.

### STEP 6 — Locations (Division/District) + seed
In `locations`:
- `Division`: `name`, `name_bn` (optional), `slug` (unique).
- `District`: `division` (FK, related_name `districts`), `name`, `name_bn` (optional), `slug`; unique together (`division`, `name`).
- Seed via **data migration or management command `seed_locations`** (idempotent — safe to run twice). Use a JSON file `locations/data/bd_locations.json`.

Official data to seed (8 divisions, 64 districts):
- **Barishal (6):** Barguna, Barishal, Bhola, Jhalokati, Patuakhali, Pirojpur
- **Chattogram (11):** Bandarban, Brahmanbaria, Chandpur, Chattogram, Cumilla, Cox's Bazar, Feni, Khagrachhari, Lakshmipur, Noakhali, Rangamati
- **Dhaka (13):** Dhaka, Faridpur, Gazipur, Gopalganj, Kishoreganj, Madaripur, Manikganj, Munshiganj, Narayanganj, Narsingdi, Rajbari, Shariatpur, Tangail
- **Khulna (10):** Bagerhat, Chuadanga, Jashore, Jhenaidah, Khulna, Kushtia, Magura, Meherpur, Narail, Satkhira
- **Mymensingh (4):** Jamalpur, Mymensingh, Netrokona, Sherpur
- **Rajshahi (8):** Bogura, Chapainawabganj, Joypurhat, Naogaon, Natore, Pabna, Rajshahi, Sirajganj
- **Rangpur (8):** Dinajpur, Gaibandha, Kurigram, Lalmonirhat, Nilphamari, Panchagarh, Rangpur, Thakurgaon
- **Sylhet (4):** Habiganj, Moulvibazar, Sunamganj, Sylhet

**Done when:** `Division.objects.count() == 8` and `District.objects.count() == 64`.

### STEP 7 — Auth API
Base path `/api/v1/`:
| Method | Endpoint | Purpose |
|---|---|---|
| POST | `auth/register/` | Register. Allowed roles: `customer`, `owner` only. **Never allow `admin` self-registration.** Owner registration also creates `OwnerProfile`. |
| POST | `auth/login/` | phone + password → access + refresh |
| POST | `auth/token/refresh/` | refresh token |
| POST | `auth/logout/` | blacklist refresh token (enable `rest_framework_simplejwt.token_blacklist`) |
| GET/PATCH | `auth/me/` | own profile (cannot change role) |
| GET | `locations/divisions/` | list divisions |
| GET | `locations/districts/?division=<id>` | districts filtered by division |

Use serializers with validation (phone format, password rules). Include `role` in the JWT claims.

**Done when:** register → login → `/me/` flow works in Swagger/Postman.

### STEP 8 — Role-based permissions
In `core/permissions.py`:
- `IsCustomer`, `IsOwner`, `IsAdminRole`, `IsOwnerOrAdmin`, `IsOwnerOfObject` (object-level template for Part 2).
- Add a temporary test endpoint per role (e.g. `/api/v1/debug/owner-only/`) to verify, then remove or guard with `DEBUG`.

**Done when:** each role gets 200 on its endpoint and 403 on others.

### STEP 9 — Django Admin
- Register `User` (custom `UserAdmin`: list phone/name/role/active; filter by role; search by phone/name), `OwnerProfile`, `Division`, `District` (inline districts under division).

**Done when:** you can log in to `/admin/` and manage users/locations.

### STEP 10 — Docs, tests, wrap-up
- Swagger at `/api/docs/`, schema at `/api/schema/`.
- Tests (pytest): register customer/owner, block admin registration, login success/fail, `/me/`, divisions count, districts filter, role permissions.
- Update README with run instructions.
- `ruff`/`black` clean. Git commit: `part-1-foundation`.

---

## 5. Definition of Done (Part 1)
- [ ] `python manage.py runserver` works, connected to PostgreSQL
- [ ] Custom User + OwnerProfile migrated
- [ ] 8 divisions + 64 districts seeded (idempotent)
- [ ] Register/login/refresh/logout/me working
- [ ] Role permissions tested
- [ ] Django Admin usable
- [ ] Swagger docs reachable
- [ ] Tests pass

## 6. Agent Prompt Template
```
Read docs/PART1_Foundation_Roadmap.md fully.
Execute ONLY "STEP <N>". Follow the folder structure and rules in the file.
Do not start any other step. When done, list files changed, commands to run,
and how I can verify it. Then wait.
```
