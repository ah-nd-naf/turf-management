# Step 5 Explained: Custom User Model & Architecture

This guide explains all foundational concepts implemented in **Step 5** of the Turf Management platform. It is written specifically for Django and Django REST Framework (DRF) beginners.

---

## Table of Contents
1. [Why a Custom User Model Must Be Created Before the First Migrate](#1-why-a-custom-user-model-must-be-created-before-the-first-migrate)
2. [AbstractUser vs. AbstractBaseUser (And Why AbstractBaseUser Was Chosen)](#2-abstractuser-vs-abstractbaseuser-and-why-abstractbaseuser-was-chosen)
3. [What USERNAME_FIELD, REQUIRED_FIELDS, and PermissionsMixin Do](#3-what-username_field-required_fields-and-permissionsmixin-do)
4. [What the UserManager Does (create_user vs. create_superuser)](#4-what-the-usermanager-does-create_user-vs-create_superuser)
5. [How TextChoices Works for the Role Field](#5-how-textchoices-works-for-the-role-field)
6. [Why OwnerProfile Is a Separate Model (OneToOne)](#6-why-ownerprofile-is-a-separate-model-onetoone)
7. [Line-by-Line Walkthrough of models.py and managers.py](#7-line-by-line-walkthrough-of-models-py-and-managers-py)
8. [What the Migration Created in PostgreSQL](#8-what-the-migration-created-in-postgresql)

---

## 1. Why a Custom User Model Must Be Created Before the First Migrate

When you start a fresh Django project, Django provides a default user model (`django.contrib.auth.models.User`) that uses a `username` field for authentication.

Other installed applications in Django—such as `django.contrib.admin` (`LogEntry`), `django.contrib.auth` (`Permission`, `Group`), and third-party packages like `rest_framework_simplejwt.token_blacklist` (`OutstandingToken`)—contain foreign keys pointing directly to the User model configured in your settings.

### What happens if you run `migrate` before creating a custom User model?
1. Django runs the initial migrations for `auth`, `admin`, `contenttypes`, and `sessions`.
2. Those migrations create tables in PostgreSQL where foreign key constraints point directly to the default `auth_user` table.
3. If you decide *afterwards* to switch to a custom `accounts.User` model by setting `AUTH_USER_MODEL = 'accounts.User'`, Django will fail. The database already has foreign key constraints locked onto `auth_user`, resulting in circular migration dependencies and database schema conflicts.
4. Fixing this post-migration usually requires completely wiping the database, deleting migration histories, and starting over.

### The Official Django Rule:
> *"If you intend to use a custom user model for your project, you should set `AUTH_USER_MODEL` before running your first `migrate` command."*

By configuring `AUTH_USER_MODEL = 'accounts.User'` in `config/settings/base.py` **before** running `migrate`, Django builds all initial tables (`accounts_user`, `admin_logentry`, `token_blacklist_outstandingtoken`, etc.) with correct foreign keys pointing to `accounts_user` from day one.

---

## 2. AbstractUser vs. AbstractBaseUser (And Why AbstractBaseUser Was Chosen)

Django offers two classes you can inherit from when customizing the User model:

| Feature | `AbstractUser` | `AbstractBaseUser` |
|---|---|---|
| **What it contains** | Full user model with `username`, `first_name`, `last_name`, `email`, `is_staff`, `is_active`, `date_joined`, plus permissions. | Only password hashing, last login, and core auth hooks. No pre-set fields. |
| **Default identifier** | `username` | None (you define `USERNAME_FIELD`) |
| **Best used when** | You are satisfied with Django's default fields and usernames, but just want to add extra fields (like `birth_date` or `bio`). | You want complete control over fields and want to change how users identify themselves (e.g., phone number or email instead of username). |

### Why `AbstractBaseUser` was chosen for this project:
1. **Bangladeshi Context**: In Bangladesh, customers and turf owners log in using their **11-digit mobile phone number** (`01XXXXXXXXX`), not a synthetic username.
2. **No Dead Weight**: If we used `AbstractUser`, the database table would still have a `username` column that we would have to artificially populate or leave unused.
3. **Clean Architecture**: `AbstractBaseUser` gives us a blank slate. We keep only what we need: `phone_number`, `email`, `full_name`, `role`, timestamps, and active flags.

---

## 3. What USERNAME_FIELD, REQUIRED_FIELDS, and PermissionsMixin Do

### `USERNAME_FIELD = "phone_number"`
- Tells Django's authentication system which field on our model is the **unique identifier** for logging in.
- Django will use this field when checking passwords, generating auth tokens, and running `createsuperuser`.
- This field **must** be set to `unique=True` in the model.

### `REQUIRED_FIELDS = ["full_name"]`
- This is a list of field names that the CLI command `python manage.py createsuperuser` will prompt for in the terminal.
- **Rule**: Never put `USERNAME_FIELD` or `password` in `REQUIRED_FIELDS` because Django already prompts for them automatically.
- Here, when creating a superuser, Django prompts for:
  1. Phone number (`USERNAME_FIELD`)
  2. Full name (`REQUIRED_FIELDS`)
  3. Password

### `PermissionsMixin`
- `AbstractBaseUser` only handles authentication (passwords and login tokens). It does **not** know about permissions or groups.
- `PermissionsMixin` adds:
  - `is_superuser` (boolean flag granting all permissions).
  - `groups` (Many-to-Many relationship with `auth.Group`).
  - `user_permissions` (Many-to-Many relationship with `auth.Permission`).
  - Helper methods like `has_perm()`, `has_perms()`, and `has_module_perms()`.
- Without `PermissionsMixin`, our custom User cannot log into or use the Django Admin interface (`/admin/`).

---

## 4. What the UserManager Does (create_user vs. create_superuser)

When you build a custom user model using `AbstractBaseUser`, Django no longer knows how to create user records because it cannot assume a `username` field exists.

We provide a custom manager subclassing `BaseUserManager` with two core methods:

### 1. `create_user(self, phone_number, password=None, **extra_fields)`
- **Validates Input**: Checks that a phone number is provided; raises a `ValueError` if missing.
- **Normalizes Email**: Uses `self.normalize_email(email)` to lower-case the domain part (e.g. `ALICE@GMAIL.COM` becomes `ALICE@gmail.com`). Converts empty strings `""` to `None` so database unique constraints are not violated.
- **Sets Default Role**: Ensures regular users default to the `'customer'` role.
- **Instantiates Model**: Uses `self.model(phone_number=phone_number, **extra_fields)`. Using `self.model` prevents hardcoding the `User` class name and avoids circular imports.
- **Hashes the Password**: Calls `user.set_password(password)`. This uses one-way cryptographic hashing (PBKDF2 with SHA-256 by default). **Passwords are never stored in plain text.**
- **Saves to DB**: Calls `user.save(using=self._db)` and returns the user object.

### 2. `create_superuser(self, phone_number, password=None, **extra_fields)`
- Automatically sets administrative flags:
  - `is_staff = True` (allows logging into `/admin/`).
  - `is_superuser = True` (grants all permissions without explicit assignments).
  - `is_active = True`.
  - `role = "admin"` (matches platform business logic).
- Validates that `is_staff` and `is_superuser` are strictly `True`.
- Delegates the actual creation and hashing to `self.create_user(phone_number, password, **extra_fields)`.

---

## 5. How TextChoices Works for the Role Field

Django 3.0 introduced `models.TextChoices`, which creates a strongly-typed enum for choices fields:

```python
class Role(models.TextChoices):
    CUSTOMER = "customer", "Customer"
    OWNER = "owner", "Turf Owner"
    ADMIN = "admin", "Super Admin"
```

Each choice consists of a tuple:
1. **Database Value (`"customer"`)**: The raw string stored in the PostgreSQL `varchar(20)` column.
2. **Human-Readable Label (`"Customer"`)**: The label displayed in Django Admin dropdowns and forms.

### Why this is better than raw strings or old-style tuples:
1. **No Magic Strings**: In your application logic, you write `User.Role.CUSTOMER` instead of typing the string `"customer"`. If you make a typo like `User.Role.CUSTMR`, Python raises an `AttributeError` immediately, preventing silent bugs.
2. **Accessing Labels**: Django automatically generates a helper method `user.get_role_display()` which returns `"Customer"` or `"Turf Owner"`.
3. **Serializer & Form Validation**: Passing `choices=Role.choices` to `models.CharField` tells Django and DRF to reject any value other than `'customer'`, `'owner'`, or `'admin'`.

---

## 6. Why OwnerProfile Is a Separate Model (OneToOne)

Instead of dumping owner-specific fields into the `User` model, we created a separate `OwnerProfile` linked via `models.OneToOneField`:

```python
class OwnerProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="owner_profile")
    business_name = models.CharField(max_length=200)
    nid_number = models.CharField(max_length=30, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    is_verified = models.BooleanField(default=False)
    ...
```

### Key Reasons for this Separation:
1. **Single Responsibility Principle (SRP)**:
   - Over 90% of accounts will be regular customers booking turfs. Customers do not have business names, trade licenses, or owner verification statuses.
   - Putting owner fields in `User` would mean most rows in the database would have empty/null columns.
2. **Database Performance & Clean Indexes**:
   - The `accounts_user` table remains lean, compact, and fast to query on every authentication check.
3. **Clear Business Security Boundaries**:
   - Only users with `role='owner'` get an associated `OwnerProfile`.
   - Admin verification logic (`is_verified`) applies strictly to the turf owner's business entity, not customer logins.
4. **Future Extensibility**:
   - When turf payout information, bank accounts, or tax certificates are added in later phases, they belong on `OwnerProfile` without bloating the core authentication table.

---

## 7. Line-by-Line Walkthrough of models.py and managers.py

### A. Walkthrough of `apps/accounts/managers.py`

```python
from django.contrib.auth.base_user import BaseUserManager
```
- Imports Django's base manager class designed for user models.

```python
class UserManager(BaseUserManager):
```
- Declares our custom manager inheriting from `BaseUserManager`.

```python
    def create_user(self, phone_number, password=None, **extra_fields):
```
- Defines the creation helper for regular users. `extra_fields` captures any optional kwargs like `full_name` or `email`.

```python
        if not phone_number:
            raise ValueError("The phone number must be provided.")
```
- Enforces our primary business constraint: every user must have a valid phone number.

```python
        email = extra_fields.get("email")
        if email:
            extra_fields["email"] = self.normalize_email(email)
        elif email == "":
            extra_fields["email"] = None
```
- Normalizes email domain to lowercase. If an empty string was passed, converts it to `None` so PostgreSQL unique constraints don't clash on empty strings.

```python
        extra_fields.setdefault("role", "customer")
```
- Ensures default role is `'customer'` if not explicitly passed.

```python
        user = self.model(phone_number=phone_number, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user
```
- `self.model`: Resolves to the model class this manager is attached to (`User`).
- `user.set_password(password)`: Hashes the password securely.
- `user.save(using=self._db)`: Persists the record to the configured database.

```python
    def create_superuser(self, phone_number, password=None, **extra_fields):
```
- Method invoked by `python manage.py createsuperuser`.

```python
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("role", "admin")
```
- Sets the necessary privileges for administrative access.

```python
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self.create_user(phone_number, password, **extra_fields)
```
- Guard checks ensuring superuser permissions cannot be disabled accidentally, then delegates to `create_user`.

---

### B. Walkthrough of `apps/accounts/models.py`

```python
from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.core.validators import RegexValidator
from django.db import models
from .managers import UserManager
```
- Imports necessary Django core modules, the settings object (for referencing the user model safely), and our custom manager.

```python
bd_phone_validator = RegexValidator(
    regex=r"^01\d{9}$",
    message="Phone number must be an 11-digit Bangladeshi number in the format '01XXXXXXXXX'.",
)
```
- A reusable validator enforcing the Bangladesh standard format: starts with `01`, followed by 9 digits (`\d{9}`), totaling exactly 11 digits.

```python
class User(AbstractBaseUser, PermissionsMixin):
```
- Defines the `User` class combining `AbstractBaseUser` (password/login) and `PermissionsMixin` (groups/permissions/admin).

```python
    class Role(models.TextChoices):
        CUSTOMER = "customer", "Customer"
        OWNER = "owner", "Turf Owner"
        ADMIN = "admin", "Super Admin"
```
- The enum defining system roles.

```python
    phone_number = models.CharField(
        max_length=15,
        unique=True,
        validators=[bd_phone_validator],
        db_index=True,
        verbose_name="phone number",
        help_text="11-digit Bangladeshi mobile number starting with 01 (e.g., 017XXXXXXXX).",
    )
```
- Unique login identifier with regex validation and an index for fast lookups.

```python
    email = models.EmailField(
        blank=True,
        null=True,
        unique=True,
        verbose_name="email address",
        help_text="Optional contact email. Must be unique if provided.",
    )
```
- Optional email address. `null=True` allows multiple users without an email, but `unique=True` ensures no two users can share the same email.

```python
    full_name = models.CharField(max_length=150, blank=True, verbose_name="full name")
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.CUSTOMER,
        db_index=True,
        verbose_name="role",
    )
```
- Full name and role fields. `role` is indexed for filtering users by role in admin queries.

```python
    is_active = models.BooleanField(default=True, verbose_name="active status")
    is_staff = models.BooleanField(default=False, verbose_name="staff status")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="created at")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="updated at")
```
- Status flags and automated audit timestamps.

```python
    objects = UserManager()
    USERNAME_FIELD = "phone_number"
    REQUIRED_FIELDS = ["full_name"]
```
- Configures our custom manager and authentication fields.

```python
    @property
    def is_customer(self):
        return self.role == self.Role.CUSTOMER

    @property
    def is_owner(self):
        return self.role == self.Role.OWNER

    @property
    def is_admin_role(self):
        return self.role == self.Role.ADMIN
```
- Convenience properties for readable role checking (e.g. `if request.user.is_owner:`).

```python
class OwnerProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="owner_profile",
        verbose_name="user",
    )
```
- Creates a 1:1 relationship between a `User` and their `OwnerProfile`. Deleting the user automatically deletes their profile (`CASCADE`).

```python
    business_name = models.CharField(max_length=200, verbose_name="business name")
    nid_number = models.CharField(max_length=30, blank=True, null=True, verbose_name="NID / Trade License number")
    address = models.TextField(blank=True, null=True, verbose_name="business address")
    is_verified = models.BooleanField(default=False, verbose_name="verified status")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="created at")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="updated at")
```
- Business attributes for turf operators with admin verification tracking.

---

## 8. What the Migration Created in PostgreSQL

When we ran `python manage.py makemigrations` followed by `python manage.py migrate`, Django translated our Python definitions into standard PostgreSQL SQL DDL.

Here are the exact database objects created in PostgreSQL:

### 1. `accounts_user` Table
```sql
CREATE TABLE "accounts_user" (
    "id" bigint NOT NULL PRIMARY KEY GENERATED BY DEFAULT AS IDENTITY,
    "password" varchar(128) NOT NULL,
    "last_login" timestamp with time zone NULL,
    "is_superuser" boolean NOT NULL,
    "phone_number" varchar(15) NOT NULL UNIQUE,
    "email" varchar(254) NULL UNIQUE,
    "full_name" varchar(150) NOT NULL,
    "role" varchar(20) NOT NULL,
    "is_active" boolean NOT NULL,
    "is_staff" boolean NOT NULL,
    "created_at" timestamp with time zone NOT NULL,
    "updated_at" timestamp with time zone NOT NULL
);
```
- **Indexes Created**:
  - Primary key index on `id`.
  - Unique index on `phone_number`.
  - Unique index on `email`.
  - B-tree index on `role`.
  - Pattern matching indexes (`varchar_pattern_ops`) for `phone_number`, `email`, and `role` to accelerate search queries like `phone_number LIKE '017%'`.

### 2. `accounts_ownerprofile` Table
```sql
CREATE TABLE "accounts_ownerprofile" (
    "id" bigint NOT NULL PRIMARY KEY GENERATED BY DEFAULT AS IDENTITY,
    "business_name" varchar(200) NOT NULL,
    "nid_number" varchar(30) NULL,
    "address" text NULL,
    "is_verified" boolean NOT NULL,
    "created_at" timestamp with time zone NOT NULL,
    "updated_at" timestamp with time zone NOT NULL,
    "user_id" bigint NOT NULL UNIQUE
);
```
- **Constraints**:
  - `user_id` has a `UNIQUE` constraint, enforcing that one user can only have one profile.
  - Foreign key constraint `FOREIGN KEY ("user_id") REFERENCES "accounts_user" ("id")` with `DEFERRABLE INITIALLY DEFERRED`.

### 3. Join Tables for Permissions (from `PermissionsMixin`)
- `accounts_user_groups`: Junction table between `accounts_user` and `auth_group` with columns `(id, user_id, group_id)`.
- `accounts_user_user_permissions`: Junction table between `accounts_user` and `auth_permission` with columns `(id, user_id, permission_id)`.

### 4. Integration with Django Internal Apps
Because `AUTH_USER_MODEL = "accounts.User"` was registered before the first migration:
- `django_admin_log` (`admin.LogEntry`) points its `user_id` foreign key directly to `accounts_user.id`.
- `token_blacklist_outstandingtoken` points its `user_id` foreign key directly to `accounts_user.id`.
No dangling references or invalid foreign keys exist anywhere in the database.
