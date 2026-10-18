# Turf Management — Backend

A modern turf booking and scheduling platform for Bangladesh.
Customers can search turfs across 8 Divisions and 64 Districts, choose time slots, and book with an advance payment. Turf owners manage facilities, hourly pricing, and booking schedules, while administrators oversee verification and platform governance.

---

## 🛠 Tech Stack

- **Language & Runtime:** Python 3.12+
- **Web Framework:** Django 5.x + Django REST Framework (DRF)
- **Database:** PostgreSQL 18 (Local installation)
- **Authentication:** JWT via `djangorestframework-simplejwt`
- **API Documentation:** `drf-spectacular` (OpenAPI / Swagger)
- **Timezone:** `Asia/Dhaka`
- **Currency:** BDT (`DecimalField`)

---

## 📁 Repository Structure

```text
turf-management/
├── backend/
│   ├── config/            # Django project settings and URLs
│   ├── apps/              # Django modular apps (core, accounts, locations, turfs, bookings, payments)
│   ├── requirements/      # Dependency specifications (base, dev, prod)
│   │   ├── base.txt
│   │   ├── dev.txt
│   │   └── prod.txt
│   ├── pytest.ini         # Pytest configuration
│   └── .env.example       # Sample environment configuration
├── docs/                  # Architecture & roadmap documentation
├── .gitignore             # Git ignore patterns
└── README.md              # Setup & development instructions
```

---

## 🚀 Getting Started (Windows / PowerShell)

### 1. Prerequisites
- **Python 3.12** installed (`py -3.12 --version`)
- **Git**
- **PostgreSQL 18** installed locally and running on port 5432

### 2. Environment Setup
Clone or open the repository root:
```powershell
cd "f:\Trial Projects\turf-management"
```

Create a Python 3.12 virtual environment:
```powershell
py -3.12 -m venv venv
```

Activate the virtual environment:
```powershell
.\venv\Scripts\Activate.ps1
```
*(If execution policy blocks activation, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned` in PowerShell)*

### 3. Install Dependencies
Install development dependencies:
```powershell
pip install -r backend/requirements/dev.txt
```

Verify the core libraries are installed:
```powershell
pip list
```
*(Should include `Django`, `djangorestframework`, `djangorestframework-simplejwt`, and `psycopg`)*

---

## 📖 Roadmap Progress
- [x] **Step 1:** Repository structure, Git initialization, environment setup, dependencies
- [ ] **Step 2:** Django project configuration, split settings (`base.py`, `dev.py`, `prod.py`), environment variables
- [ ] **Step 3:** PostgreSQL 18 local connection verification
- [ ] **Step 4:** Django apps creation (`core`, `accounts`, `locations`, `turfs`, `bookings`, `payments`)
- [ ] **Step 5:** Custom User model (`accounts.User`) with phone-number authentication & role-based access
- [ ] **Step 6:** Divisions (8) and Districts (64) seed data and management commands
- [ ] **Step 7:** Authentication APIs (`register`, `login`, `refresh`, `logout`, `me`)
- [ ] **Step 8:** Role-based permissions (`IsCustomer`, `IsOwner`, `IsAdminRole`)
- [ ] **Step 9:** Django Admin customization
- [ ] **Step 10:** Swagger documentation, pytest suite, and wrap-up
