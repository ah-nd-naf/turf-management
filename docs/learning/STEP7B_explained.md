# Step 7B Explained: Authentication API (Register, Login, & Token Refresh)

This guide provides an in-depth, beginner-friendly explanation of everything built in **Step 7B** of the Turf Management platform. Whether you are new to Django REST Framework (DRF), JSON Web Tokens (JWT), or relational database transactions, this document will help you understand **how** each piece works and **why** it was designed that way.

---

## Table of Contents
1. [How Serializer Validation Works: The 3-Tier Pipeline](#1-how-serializer-validation-works-the-3-tier-pipeline)
2. [Why `password` is `write_only` and Why `password_confirm` Exists](#2-why-password-is-write_only-and-why-password_confirm-exists)
3. [Why `role` Cannot Be "admin" in Registration (Security: Privilege Escalation)](#3-why-role-cannot-be-admin-in-registration-security-privilege-escalation)
4. [Why `create_user()` is Used Instead of `User.objects.create()` (Password Hashing)](#4-why-create_user-is-used-instead-of-userobjectscreate-password-hashing)
5. [Why `transaction.atomic()` is Used for User + OwnerProfile](#5-why-transactionatomic-is-used-for-user--ownerprofile)
6. [How JWT Works: Access vs Refresh Tokens, Claims, and Roles](#6-how-jwt-works-access-vs-refresh-tokens-claims-and-roles)
7. [How Custom `TokenObtainPairSerializer` Works with `phone_number`](#7-how-custom-tokenobtainpairserializer-works-with-phone_number)
8. [What `AllowAny` Is and Why Register/Login Must Declare It Explicitly](#8-what-allowany-is-and-why-registerlogin-must-declare-it-explicitly)
9. [Step-by-Step Request/Response Walkthrough of `POST /api/v1/auth/register/`](#9-step-by-step-requestresponse-walkthrough-of-post-apiv1authregister)
10. [Line-by-Line Walkthrough of `serializers.py` and `views.py`](#10-line-by-line-walkthrough-of-serializerspy-and-viewspy)
11. [How to Verify & Test via Swagger UI](#11-how-to-verify--test-via-swagger-ui)

---

## 1. How Serializer Validation Works: The 3-Tier Pipeline

When an incoming HTTP request brings JSON data to your server, you can never blindly trust it. Clients can send malformed strings, missing fields, malicious values, or conflicting passwords.

DRF serializers process data through a rigorous **3-tier validation pipeline** that runs automatically when you call `serializer.is_valid()`:

```
Incoming JSON Payload
        │
        ▼
[ Tier 1: Field-Level Type Checks & Validators ]
  - Checks types (is it a string, email, integer?)
  - Checks constraints (required, max_length, unique)
  - Runs validators=[...] (e.g. bd_phone_validator regex)
        │
        ▼ (If passed)
[ Tier 2: Individual Field Methods: validate_<field_name>() ]
  - validate_phone_number(value)
  - validate_role(value)
  - validate_email(value)
        │
        ▼ (If passed)
[ Tier 3: Cross-Field Object Method: validate(attrs) ]
  - Compares multiple fields together: password == password_confirm
  - Conditional checks: if role == 'owner', is business_name provided?
  - External validators: validate_password(password)
        │
        ▼
Success: serializer.validated_data is ready!
(Or raises serializers.ValidationError with error dict)
```

### Tier 1: Field Definitions and Built-in Validators
When you declare fields on a serializer:
```python
phone_number = serializers.CharField(
    max_length=15,
    validators=[bd_phone_validator],
)
```
DRF checks:
- Is the input present? (If `required=True`).
- Is it within `max_length`?
- Does it pass every callable inside `validators=[...]`? Here, `bd_phone_validator` ensures it matches `^01\d{9}$`. If not, DRF immediately flags an error on `phone_number`.

### Tier 2: `validate_<field_name>(self, value)`
If a field passes Tier 1, DRF searches the serializer class for a method named exactly `validate_<field_name>`.
- The method receives the clean `value` of that single field.
- You can perform custom checks, normalization, or queries.
- **Rule:** You **MUST return the value** (or a transformed version of it). If invalid, you raise `serializers.ValidationError("reason")`.

Example from our `validate_role`:
```python
def validate_role(self, value):
    role_str = str(value).lower().strip()
    if role_str == User.Role.ADMIN:
        raise serializers.ValidationError(
            "Registration with role 'admin' is not permitted. Only 'customer' and 'owner' accounts can be registered."
        )
    if role_str not in [User.Role.CUSTOMER, User.Role.OWNER]:
        raise serializers.ValidationError(f"Invalid role '{value}'.")
    return role_str  # Cleaned, lowercase value returned
```

### Tier 3: `validate(self, attrs)` (Cross-Field Validation)
Tier 2 methods only see **one field at a time**. But what if the validity of field A depends on field B?
- Does `password` match `password_confirm`?
- If `role` is `'owner'`, is `business_name` provided?

Tier 3 solves this. DRF passes `attrs`, a Python dictionary containing all validated fields from Tiers 1 and 2:
```python
def validate(self, attrs):
    # Cross-field check 1: passwords must match
    if attrs.get("password") != attrs.get("password_confirm"):
        raise serializers.ValidationError({
            "password_confirm": "Password confirmation does not match the password."
        })

    # Cross-field check 2: owners must provide business_name
    if attrs.get("role") == User.Role.OWNER:
        if not attrs.get("business_name"):
            raise serializers.ValidationError({
                "business_name": "Business name is required when registering as a turf owner."
            })

    return attrs  # Always return attrs dictionary
```

---

## 2. Why `password` is `write_only` and Why `password_confirm` Exists

### Why `password` is `write_only=True`
In REST APIs, data flows in two directions:
1. **Deserialization (Writing):** Client sends JSON → Server saves to database.
2. **Serialization (Reading):** Server queries database → Serializes object into JSON → Sends to client.

By default, fields declared on a serializer appear in **both** directions. If `password` were not marked `write_only=True`:
1. A customer registers by sending their raw password `"MySecret123!"`.
2. The server creates the user in the database.
3. The server serializes the newly created user to return the response.
4. **Catastrophe:** The raw or hashed password would be included in the JSON response body across the public network!

Setting `write_only=True` tells DRF:
> *"Accept this field in incoming POST/PUT/PATCH requests, but **never** include this field when generating outbound JSON responses."*

### Why `password_confirm` Exists
When users sign up on web and mobile forms, password input fields mask characters with dots (`••••••••`). Because characters are hidden, typing errors (typos) are extremely common.

If a user accidentally types `P@sswrod123` instead of `P@ssword123` and submits without confirmation:
1. The typo is hashed and saved.
2. The user is logged out later.
3. The user tries to log in with `P@ssword123` and is locked out because their stored password has a typo they are unaware of.

`password_confirm` acts as a confirmation safety net. Both fields must match identically in Tier 3 validation before any database write occurs. Furthermore, `password_confirm` is not a column on the `User` table; it exists purely in the serializer for verification and is discarded (`validated_data.pop('password_confirm')`) before saving.

---

## 3. Why `role` Cannot Be "admin" in Registration (Security: Privilege Escalation)

In the database, the `User` model supports three roles:
1. `customer`: Regular turf searcher and slot booker.
2. `owner`: Turf arena manager with turf listing and scheduling access.
3. `admin`: Platform superuser with access to all private records, finances, and system settings.

### What is Privilege Escalation?
Privilege escalation is a critical security vulnerability where an unprivileged attacker elevates their access rights to administrative level.

Imagine if our `/api/v1/auth/register/` endpoint accepted any role sent in JSON:
```json
// Malicious payload sent by an attacker
{
  "phone_number": "01799999999",
  "full_name": "Attacker",
  "role": "admin",
  "password": "Password123!",
  "password_confirm": "Password123!"
}
```
If our serializer did not restrict this, any random person on the internet could make themselves a super administrator and gain control over the entire platform, access customers' private phone numbers, cancel bookings, and divert payments.

### The Defensive Architecture
- **Self-registration is strictly restricted to `customer` and `owner`.**
- If an incoming payload contains `"role": "admin"`, `validate_role` immediately halts execution and returns HTTP 400 Bad Request:
  ```json
  {
    "role": [
      "Registration with role 'admin' is not permitted. Only 'customer' and 'owner' accounts can be registered."
    ]
  }
  ```
- **How are administrators created?** Platform administrators are created exclusively via the secure CLI command `python manage.py createsuperuser` or granted directly by an existing administrator through the Django Admin console.

---

## 4. Why `create_user()` is Used Instead of `User.objects.create()` (Password Hashing)

In standard Django models, creating a row is normally done via `Model.objects.create(**kwargs)`:
```python
# ❌ DANGEROUS: DO NOT DO THIS FOR USERS
user = User.objects.create(
    phone_number="01711111111",
    password="MyRawPassword123!"
)
```

### The Plaintext Catastrophe
If you call `User.objects.create(password="MyRawPassword123!")`, Django writes `"MyRawPassword123!"` directly into the PostgreSQL database as **plain, readable text**.
If a database backup leaks, or a developer views the database, or an SQL injection occurs, every user's password is completely exposed.

### How `create_user()` Solves This
Our custom `UserManager` defines a specialized `create_user()` method:
```python
# In apps/accounts/managers.py
def create_user(self, phone_number, password=None, **extra_fields):
    ...
    user = self.model(phone_number=phone_number, **extra_fields)
    user.set_password(password)  # <--- SECURE ONE-WAY HASHING
    user.save(using=self._db)
    return user
```
`user.set_password(password)` uses **PBKDF2 with SHA-256** encryption with a unique random cryptographic salt and tens of thousands of hashing rounds:
```
Raw Password: "MyRawPassword123!"
       ↓ (PBKDF2 + SHA-256 + Salt)
Stored in DB: "pbkdf2_sha256$720000$s1a2b3...$x9y8z7..."
```
This hash is **one-way**: it is mathematically impossible to reverse the hash back into the plain text password. When logging in later, Django hashes the provided password with the stored salt and compares hashes (`check_password()`).

In `UserRegisterSerializer.create()`, we always call:
```python
user = User.objects.create_user(password=password, **validated_data)
```

---

## 5. Why `transaction.atomic()` is Used for User + OwnerProfile

When a turf owner registers, the system must create **two separate database records**:
1. A row in `accounts_user` table (the login account).
2. A row in `accounts_ownerprofile` table (the business info linked via `user_id`).

### The Disaster Without a Transaction (Orphaned Records)
Consider what happens without atomic transactions if the server crashes or an unexpected database error occurs right after step 1:
```
Step 1: User.objects.create_user(...)  --> SUCCESS! (User #42 written to PostgreSQL)
Step 2: Server crashes or DB constraint fails on OwnerProfile
Result: User #42 exists with role='owner', but has NO OwnerProfile!
```
Now:
- User #42 tries to log in. The application looks for `user.owner_profile` and crashes with `DoesNotExist`.
- User #42 cannot re-register because their phone number is already taken.
- Your database is corrupted with incomplete, orphaned state.

### The Solution: `transaction.atomic()`
`transaction.atomic()` wraps the operations in a SQL transaction block:
```sql
BEGIN; -- Start transaction
INSERT INTO accounts_user ...;
INSERT INTO accounts_ownerprofile ...;
COMMIT; -- All succeeded! Save permanently.
```
If **anything** fails or raises an exception before the end of the block, PostgreSQL immediately executes:
```sql
ROLLBACK; -- Undo everything!
```
The user table remains untouched as if the request never happened. Atomicity ensures **"All or Nothing"** execution.

```python
@transaction.atomic
def create(self, validated_data):
    ...
    user = User.objects.create_user(password=password, **validated_data)
    if user.role == User.Role.OWNER:
        OwnerProfile.objects.create(user=user, business_name=business_name)
    return user
```

---

## 6. How JWT Works: Access vs Refresh Tokens, Claims, and Roles

Traditional web applications use **session cookies**: the server stores session IDs in RAM or a Redis/database table, and the browser sends a cookie with every request.
For modern mobile apps, microservices, and Single Page Applications (Next.js/React), **JSON Web Tokens (JWT)** are the industry standard.

### What is a JWT?
A JWT is a cryptographically signed, URL-safe base64 string divided into three parts separated by dots:
```
header.payload.signature
```
1. **Header:** Algorithm used (e.g. `{"alg": "HS256", "typ": "JWT"}`).
2. **Payload:** Data dictionary (claims) containing user identity and metadata.
3. **Signature:** Cryptographic signature calculated using `HMACSHA256(header + "." + payload, SECRET_KEY)`.

Because only the Django backend knows `SECRET_KEY`, no attacker can alter the payload (e.g. changing `"role": "customer"` to `"role": "admin"`) without invalidating the signature.

---

### Access Token vs Refresh Token

| Property | Access Token | Refresh Token |
|---|---|---|
| **Purpose** | Sent in `Authorization: Bearer <token>` to authenticate API requests | Sent to `/api/v1/auth/token/refresh/` to obtain a fresh access token |
| **Lifetime** | Short (60 minutes in our config) | Long (7 days in our config) |
| **Storage** | Client memory / App state | Secure HTTP-only storage / Secure device keychain |
| **Risk if Stolen** | Low impact: expires in less than an hour | High impact: can be revoked or rotated in DB (`token_blacklist`) |

### Why Two Tokens?
If you only had a single token valid for 30 days and an attacker intercepted it, they would have 30 days of uninterrupted access. With short-lived access tokens (60 minutes), the attack window is minimized. If an account is suspended or a token compromised, platform admins can blacklist the refresh token.

### What is a Claim?
Any key-value pair stored inside the JWT payload is called a **claim**.
Standard claims include:
- `user_id`: ID of the authenticated user.
- `exp`: Expiration timestamp (Unix epoch).
- `iat`: Issued-at timestamp.

### Why Add Custom Claims (`role`, `full_name`, `phone_number`)?
In `CustomTokenObtainPairSerializer.get_token()`:
```python
@classmethod
def get_token(cls, user):
    token = super().get_token(user)
    # Custom claims:
    token["role"] = user.role
    token["full_name"] = user.full_name
    token["phone_number"] = user.phone_number
    return token
```
**Why this is powerful:**
When the frontend Next.js app receives the access token, it can decode the base64 payload instantly without calling the backend!
- It can read `role == 'owner'` and immediately render the Turf Owner Dashboard.
- It can display "Welcome back, Rahim!" using `full_name`.
- It eliminates the need for an extra HTTP roundtrip to `/api/v1/auth/me/` on every single page refresh.

---

## 7. How Custom `TokenObtainPairSerializer` Works with `phone_number`

By default, SimpleJWT's `TokenObtainPairSerializer` expects a JSON body with:
```json
{
  "username": "...",
  "password": "..."
}
```
However, in our system, customers and turf owners log in using their **Bangladeshi phone number**.

### How It Automatically Adapts
SimpleJWT checks the `User` model's `USERNAME_FIELD` attribute:
```python
# In apps/accounts/models.py
class User(AbstractBaseUser, PermissionsMixin):
    USERNAME_FIELD = "phone_number"
```
In SimpleJWT's base `TokenObtainSerializer`:
```python
class TokenObtainSerializer(serializers.Serializer):
    username_field = get_user_model().USERNAME_FIELD  # Evaluates to "phone_number"
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields[self.username_field] = serializers.CharField(write_only=True)
        self.fields["password"] = PasswordField(write_only=True)
```
When `serializer.validate(attrs)` runs:
```python
authenticate_kwargs = {
    self.username_field: attrs[self.username_field], # 'phone_number': '017XXXXXXXX'
    'password': attrs['password'],
}
self.user = authenticate(**authenticate_kwargs)
```
Django's `ModelBackend.authenticate()` takes `phone_number` and queries `User.objects.get_by_natural_key(phone_number)`. It verifies the password with `user.check_password(password)`.

### Adding Basic User Info to the Login Response
Standard SimpleJWT returns only:
```json
{
  "refresh": "eyJhbGciOi...",
  "access": "eyJhbGciOi..."
}
```
Our `CustomTokenObtainPairSerializer` overrides `validate(attrs)`:
```python
def validate(self, attrs):
    data = super().validate(attrs)

    # Attach user details directly alongside tokens
    data["id"] = self.user.id
    data["phone_number"] = self.user.phone_number
    data["full_name"] = self.user.full_name
    data["role"] = self.user.role
    data["user"] = {
        "id": self.user.id,
        "phone_number": self.user.phone_number,
        "full_name": self.user.full_name,
        "role": self.user.role,
    }
    return data
```
This gives mobile apps and frontend clients instant access to user metadata right upon login.

---

## 8. What `AllowAny` Is and Why Register/Login Must Declare It Explicitly

In `backend/config/settings/base.py`, we configured the global DRF permission:
```python
REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
    ),
    ...
}
```
This is a secure **"closed by default"** security posture: every API endpoint in the platform requires a valid JWT token unless explicitly permitted otherwise.

### The Catch-22 (Why Auth Endpoints Need `AllowAny`)
If the global setting is `IsAuthenticated`:
- A new visitor wanting to register has **no account yet**, so they have no JWT token.
- A registered user wanting to log in has **no token yet**; that's why they are logging in!
- If an access token expires after 60 minutes, the client's request to `/auth/token/refresh/` is unauthenticated.

If we did not override permissions on these views, DRF would block them with:
`HTTP 401 Unauthorized: Authentication credentials were not provided.`

### The Explicit Override
In `apps/accounts/views.py`, every auth view explicitly sets:
```python
class RegisterView(generics.CreateAPIView):
    permission_classes = [permissions.AllowAny]

class LoginView(TokenObtainPairView):
    permission_classes = [permissions.AllowAny]

class CustomTokenRefreshView(SimpleJWTTokenRefreshView):
    permission_classes = [permissions.AllowAny]
```
`AllowAny` tells DRF:
> *"Permit any incoming HTTP request to reach this view regardless of whether an Authorization header is present."*

---

## 9. Step-by-Step Request/Response Walkthrough of `POST /api/v1/auth/register/`

Here is the exact lifecycle of a registration request from the moment the client hits the network to the database commit:

```
[ Client (Browser / Swagger / Postman) ]
   │
   │ 1. POST /api/v1/auth/register/
   │    Payload: {"phone_number": "01744444444", "role": "owner", "business_name": "Arena", ...}
   ▼
[ Django config/urls.py & apps/accounts/urls.py ]
   │ Matches 'api/v1/auth/register/' -> calls RegisterView.as_view()
   ▼
[ RegisterView (generics.CreateAPIView) ]
   │ 2. Checks permission_classes = [AllowAny] -> ALLOWED
   │ 3. Instantiates UserRegisterSerializer(data=request.data)
   │ 4. Calls serializer.is_valid(raise_exception=True)
   ▼
[ UserRegisterSerializer Validation ]
   │ Tier 1: phone_number matches bd_phone_validator regex? -> YES
   │ Tier 2: validate_phone_number() -> phone not in DB? -> YES
   │ Tier 2: validate_role() -> role is 'owner' (not 'admin')? -> YES
   │ Tier 3: validate() -> password == password_confirm? -> YES
   │ Tier 3: validate() -> validate_password(password)? -> PASSES DJANGO SECURITY
   │ Tier 3: validate() -> role == 'owner', is business_name present? -> YES
   ▼
[ RegisterView calls serializer.save() -> Serializer.create() ]
   │ 5. Enters @transaction.atomic block
   │ 6. Pops 'password' and 'business_name'
   │ 7. Calls User.objects.create_user(phone_number, password=password, ...)
   │      └─ User.set_password() hashes password via PBKDF2/SHA-256
   │      └─ Saves User instance to PostgreSQL
   │ 8. Creates OwnerProfile(user=user, business_name='Arena')
   │ 9. Transaction COMMITS to PostgreSQL!
   ▼
[ RegisterView Returns HTTP Response ]
   │ 10. Serializer runs to_representation(user)
   │     └─ Defensively removes 'password' & 'password_confirm'
   │     └─ Attaches 'business_name'
   │ 11. Returns HTTP 201 Created with JSON body
   ▼
[ Client Receives Response ]
{
  "id": 4,
  "phone_number": "01744444444",
  "full_name": "Valid Owner",
  "email": null,
  "role": "owner",
  "business_name": "Arena",
  "created_at": "2026-10-28T22:04:53Z"
}
```

---

## 10. Line-by-Line Walkthrough of `serializers.py` and `views.py`

### `apps/accounts/serializers.py`

```python
User = get_user_model()
```
> References the active user model specified by `AUTH_USER_MODEL = 'accounts.User'` in settings. Avoids hardcoding `from .models import User` for standard Django best practices.

```python
phone_number = serializers.CharField(
    max_length=15,
    validators=[bd_phone_validator],
    help_text="11-digit Bangladeshi mobile number starting with 01 (e.g., 017XXXXXXXX).",
)
```
> Exposes `phone_number` and validates the string format against `bd_phone_validator` (`^01\d{9}$`).

```python
password = serializers.CharField(
    write_only=True,
    required=True,
    style={"input_type": "password"},
    help_text="Account password. Must be at least 8 characters and pass Django security checks.",
)
password_confirm = serializers.CharField(
    write_only=True,
    required=True,
    style={"input_type": "password"},
    help_text="Password confirmation. Must match password exactly.",
)
```
> Both passwords are `write_only=True` so they never serialize into responses. `style={"input_type": "password"}` tells Swagger UI and DRF Browsable API to render HTML masked input boxes.

```python
business_name = serializers.CharField(
    required=False,
    allow_blank=True,
    write_only=True,
    max_length=200,
    help_text="Required when role is 'owner'. Operating name of the turf business.",
)
```
> Receives the owner's company or arena name during registration. It is marked `required=False` at the field level because customers do not have a business name; cross-field validation enforces it conditionally.

```python
def validate_role(self, value):
    if not value:
        return User.Role.CUSTOMER
    role_str = str(value).lower().strip()
    if role_str == User.Role.ADMIN:
        raise serializers.ValidationError(
            "Registration with role 'admin' is not permitted. Only 'customer' and 'owner' accounts can be registered."
        )
    if role_str not in [User.Role.CUSTOMER, User.Role.OWNER]:
        raise serializers.ValidationError(
            f"Invalid role '{value}'. Allowed roles are 'customer' and 'owner'."
        )
    return role_str
```
> Tier 2 field validator. Normalizes the string to lowercase. Rejects `"admin"` with an informative security message, rejects unknown roles, and permits `'customer'` or `'owner'`.

```python
def validate(self, attrs):
    password = attrs.get("password")
    password_confirm = attrs.get("password_confirm")

    if password != password_confirm:
        raise serializers.ValidationError({
            "password_confirm": "Password confirmation does not match the password."
        })

    try:
        validate_password(password)
    except DjangoValidationError as exc:
        raise serializers.ValidationError({
            "password": list(exc.messages)
        })

    role = attrs.get("role", User.Role.CUSTOMER)
    if role == User.Role.OWNER:
        business_name = attrs.get("business_name")
        if not business_name or not str(business_name).strip():
            raise serializers.ValidationError({
                "business_name": "Business name is required when registering as a turf owner."
            })
    return attrs
```
> Tier 3 cross-field validator. Tests password matching, executes Django's built-in password security checks (from `AUTH_PASSWORD_VALIDATORS` in `base.py`), and ensures owners provide a non-empty `business_name`.

```python
@transaction.atomic
def create(self, validated_data):
    validated_data.pop("password_confirm", None)
    password = validated_data.pop("password")
    business_name = validated_data.pop("business_name", None)

    if validated_data.get("email") == "":
        validated_data["email"] = None

    user = User.objects.create_user(password=password, **validated_data)

    if user.role == User.Role.OWNER:
        OwnerProfile.objects.create(
            user=user,
            business_name=business_name.strip(),
        )

    return user
```
> Pops non-model fields (`password_confirm`, raw `password`, and `business_name`). Calls `User.objects.create_user()` to hash the password and save the user. If the role is owner, creates the `OwnerProfile`. The entire method runs under `@transaction.atomic`.

```python
def to_representation(self, instance):
    data = super().to_representation(instance)
    data.pop("password", None)
    data.pop("password_confirm", None)

    if instance.role == User.Role.OWNER and hasattr(instance, "owner_profile"):
        data["business_name"] = instance.owner_profile.business_name
    else:
        data["business_name"] = None

    return data
```
> Serializes the saved `user` object into JSON for the HTTP 201 response. Ensures password keys are purged and attaches `business_name` for owners.

---

### `apps/accounts/views.py`

```python
class RegisterView(generics.CreateAPIView):
    permission_classes = [permissions.AllowAny]
    serializer_class = UserRegisterSerializer
```
> Inherits from DRF's built-in `CreateAPIView`. Provides a `POST` handler that parses incoming JSON into `UserRegisterSerializer`, validates it, saves the new user, and returns HTTP 201 Created. `permission_classes = [permissions.AllowAny]` opens it to unauthenticated visitors.

```python
class LoginView(TokenObtainPairView):
    permission_classes = [permissions.AllowAny]
    serializer_class = CustomTokenObtainPairSerializer
```
> Inherits from SimpleJWT's `TokenObtainPairView`. Points to our `CustomTokenObtainPairSerializer`, which authenticates via `phone_number` and returns JWT access + refresh tokens and user profile information.

```python
class CustomTokenRefreshView(SimpleJWTTokenRefreshView):
    permission_classes = [permissions.AllowAny]
```
> Inherits from SimpleJWT's `TokenRefreshView`. Accepts `{"refresh": "..."}` and issues a new access token.

---

## 11. How to Verify & Test via Swagger UI

Start the local Django development server:
```powershell
cd backend
..\venv\Scripts\python.exe manage.py runserver
```

Open your browser and navigate to:
**`http://127.0.0.1:8000/api/docs/`**

You will see the new **Auth** section containing three endpoints:

```
[Auth]
  POST /api/v1/auth/register/       Register a new customer or turf owner account
  POST /api/v1/auth/login/          Log in with phone number and password
  POST /api/v1/auth/token/refresh/  Refresh an expired JWT access token
```

### Verification Flow

#### Test 1: Register a Customer
1. Click `POST /api/v1/auth/register/` → **Try it out**.
2. Paste into the request body:
   ```json
   {
     "phone_number": "01710000001",
     "full_name": "Karim Benzema",
     "email": "karim@example.com",
     "role": "customer",
     "password": "CustomerSecurePass123!",
     "password_confirm": "CustomerSecurePass123!"
   }
   ```
3. Click **Execute**.
4. **Expected Result:** `HTTP 201 Created`. Response body contains user data with `id`, `phone_number`, `role: "customer"`, `business_name: null`, and **no password**.

#### Test 2: Try Registering as "admin" (Security Check)
1. In `POST /api/v1/auth/register/`, change `"role": "admin"`.
2. Click **Execute**.
3. **Expected Result:** `HTTP 400 Bad Request`.
   ```json
   {
     "role": [
       "Registration with role 'admin' is not permitted. Only 'customer' and 'owner' accounts can be registered."
     ]
   }
   ```

#### Test 3: Register an Owner Missing `business_name`
1. Set `"role": "owner"` and `"phone_number": "01720000002"`, leaving `"business_name"` empty or omitted.
2. Click **Execute**.
3. **Expected Result:** `HTTP 400 Bad Request`.
   ```json
   {
     "business_name": [
       "Business name is required when registering as a turf owner."
     ]
   }
   ```

#### Test 4: Register a Valid Owner
1. Add `"business_name": "Banani Sports Arena"`.
2. Click **Execute**.
3. **Expected Result:** `HTTP 201 Created`.
   ```json
   {
     "id": 5,
     "phone_number": "01720000002",
     "full_name": "Karim Benzema",
     "email": null,
     "role": "owner",
     "business_name": "Banani Sports Arena",
     "created_at": "..."
   }
   ```

#### Test 5: Login with Phone and Password
1. Click `POST /api/v1/auth/login/` → **Try it out**.
2. Enter:
   ```json
   {
     "phone_number": "01720000002",
     "password": "CustomerSecurePass123!"
   }
   ```
3. Click **Execute**.
4. **Expected Result:** `HTTP 200 OK`.
   Response includes `access`, `refresh`, user ID, name, role, and the nested `user` dictionary.
5. Copy the returned `access` token and paste it into [jwt.io](https://jwt.io). Notice the claims inside the decoded payload:
   ```json
   {
     "token_type": "access",
     "role": "owner",
     "full_name": "Karim Benzema",
     "phone_number": "01720000002"
   }
   ```

#### Test 6: Refresh Access Token
1. Click `POST /api/v1/auth/token/refresh/` → **Try it out**.
2. Paste the `refresh` token copied from Test 5 into:
   ```json
   {
     "refresh": "<YOUR_REFRESH_TOKEN>"
   }
   ```
3. Click **Execute**.
4. **Expected Result:** `HTTP 200 OK`. Returns a brand new `access` token (and new `refresh` token with rotation).
