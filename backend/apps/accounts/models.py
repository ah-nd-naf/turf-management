"""
Models for the accounts app.

WHY THESE MODELS EXIST:
1. User:
   Standard Django comes with a built-in User model that requires a 'username' and uses it for login.
   For a Bangladesh-focused turf booking platform, customers and owners identify and log in using
   their Bangladeshi phone number (e.g. 017XXXXXXXX), not a synthetic username.
   We inherit from:
   - AbstractBaseUser: Gives us core authentication machinery (password hashing, session tokens, last_login).
   - PermissionsMixin: Gives us Django's permissions system (groups, user_permissions, is_superuser)
     so Django Admin and permission decorators continue to work seamlessly.

2. OwnerProfile:
   Turf owners have business-specific attributes (business name, national ID, business address, verification)
   that regular customers do not have.
   Keeping OwnerProfile in a separate OneToOne model keeps the User table lean and fast for customer lookups,
   adheres to the Single Responsibility Principle, and cleanly isolates owner-specific verification logic.
"""

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.core.validators import RegexValidator
from django.db import models

from .managers import UserManager

# Validator for Bangladeshi phone numbers:
# Must start with '01' followed by 9 digits (total 11 digits).
# Examples: 01712345678, 01812345678, 01912345678.
bd_phone_validator = RegexValidator(
    regex=r"^01\d{9}$",
    message="Phone number must be an 11-digit Bangladeshi number in the format '01XXXXXXXXX'.",
)


class User(AbstractBaseUser, PermissionsMixin):
    """
    Custom User model where phone_number is the unique identifier for authentication.
    """

    # Role choices using Django's TextChoices.
    # TextChoices provides typed, readable choices with both code-friendly keys and human-friendly labels.
    class Role(models.TextChoices):
        CUSTOMER = "customer", "Customer"
        OWNER = "owner", "Turf Owner"
        ADMIN = "admin", "Super Admin"

    # --- Core Identification Fields ---
    # phone_number replaces username as the primary login credential.
    phone_number = models.CharField(
        max_length=15,
        unique=True,
        validators=[bd_phone_validator],
        db_index=True,
        verbose_name="phone number",
        help_text="11-digit Bangladeshi mobile number starting with 01 (e.g., 017XXXXXXXX).",
    )

    # Email is optional. If provided, it must be unique across all accounts.
    # Note: null=True allows multiple accounts without an email (PostgreSQL treats NULLs as distinct).
    email = models.EmailField(
        blank=True,
        null=True,
        unique=True,
        verbose_name="email address",
        help_text="Optional contact email. Must be unique if provided.",
    )

    full_name = models.CharField(
        max_length=150,
        blank=True,
        verbose_name="full name",
    )

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.CUSTOMER,
        db_index=True,
        verbose_name="role",
        help_text="Designates user role in the system: customer, owner, or admin.",
    )

    # --- Status and Permission Flags ---
    # is_active: Can be set to False to deactivate an account instead of deleting data (soft-ban).
    is_active = models.BooleanField(
        default=True,
        verbose_name="active status",
        help_text="Designates whether this user should be treated as active.",
    )

    # is_staff: Controls whether this user can log into the Django Admin dashboard (/admin/).
    is_staff = models.BooleanField(
        default=False,
        verbose_name="staff status",
        help_text="Designates whether the user can log into the Django admin site.",
    )

    # --- Timestamps ---
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="created at",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="updated at",
    )

    # Attach our custom manager
    objects = UserManager()

    # --- Django Authentication Configuration ---
    # USERNAME_FIELD: The name of the field on the User model that is used as the unique identifier.
    USERNAME_FIELD = "phone_number"

    # REQUIRED_FIELDS: List of field names prompted for when creating a user via createsuperuser command.
    # Note: USERNAME_FIELD and password are automatically prompted for, so do not include them here.
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        verbose_name = "user"
        verbose_name_plural = "users"
        ordering = ["-created_at"]

    def __str__(self):
        # Friendly string representation in admin and logs
        name_display = f" - {self.full_name}" if self.full_name else ""
        return f"{self.phone_number}{name_display} ({self.get_role_display()})"

    def clean(self):
        """
        Ensure empty email strings are converted to None before validation
        to avoid unique constraint violations in SQL databases.
        """
        super().clean()
        if self.email == "":
            self.email = None

    def save(self, *args, **kwargs):
        """
        Defensively convert empty string email to None before saving to DB.
        """
        if self.email == "":
            self.email = None
        super().save(*args, **kwargs)

    # --- Role Helper Properties ---
    # These provide clean, readable boolean checks (e.g., if user.is_owner: ...)
    @property
    def is_customer(self):
        return self.role == self.Role.CUSTOMER

    @property
    def is_owner(self):
        return self.role == self.Role.OWNER

    @property
    def is_admin_role(self):
        return self.role == self.Role.ADMIN


class OwnerProfile(models.Model):
    """
    Profile extension for users who operate turfs (role='owner').
    Keeps owner-specific business data separated from the core User model.
    """

    # OneToOne link ensures exactly one OwnerProfile per owner user.
    # cascade delete removes the profile if the user account is deleted.
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="owner_profile",
        verbose_name="user",
    )

    business_name = models.CharField(
        max_length=200,
        verbose_name="business name",
        help_text="Registered or operating name of the turf business.",
    )

    # National ID or Trade License number for verification
    nid_number = models.CharField(
        max_length=30,
        blank=True,
        null=True,
        verbose_name="NID / Trade License number",
        help_text="National ID card or Trade License number of the owner for verification.",
    )

    address = models.TextField(
        blank=True,
        null=True,
        verbose_name="business address",
        help_text="Physical or postal address of the business office.",
    )

    # New turfs / owners must be verified by platform admins before public listing
    is_verified = models.BooleanField(
        default=False,
        verbose_name="verified status",
        help_text="Designates whether this turf owner has been verified by platform administrators.",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="created at",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="updated at",
    )

    class Meta:
        verbose_name = "owner profile"
        verbose_name_plural = "owner profiles"
        ordering = ["-created_at"]

    def __str__(self):
        status = "Verified" if self.is_verified else "Pending Verification"
        return f"{self.business_name} ({self.user.phone_number}) - {status}"
