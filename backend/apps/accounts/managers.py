"""
Custom Manager for User Model.

WHY THIS EXISTS:
Django's default UserManager expects a 'username' field to create users.
Because our platform uses 'phone_number' as the unique identifier (USERNAME_FIELD)
and removes the username field entirely, we must provide a custom manager
subclassing BaseUserManager to tell Django how to:
1. create_user: Create regular users (customers or turf owners).
2. create_superuser: Create platform administrators with full privileges.
"""

from django.contrib.auth.base_user import BaseUserManager


class UserManager(BaseUserManager):
    """
    Manager for custom User model where phone_number is the unique login identifier.
    """

    def create_user(self, phone_number, password=None, **extra_fields):
        """
        Create and save a regular User with the given phone number and password.
        """
        # Phone number is mandatory for all accounts in our system
        if not phone_number:
            raise ValueError("The phone number must be provided.")

        # Clean email if provided: normalize converts domain part to lowercase (e.g. USER@GMAIL.COM -> USER@gmail.com).
        # If an empty string is passed, store as None so PostgreSQL unique constraint allows it.
        email = extra_fields.get("email")
        if email:
            extra_fields["email"] = self.normalize_email(email)
        elif email == "":
            extra_fields["email"] = None

        # Default role for a standard registration is customer
        extra_fields.setdefault("role", "customer")

        # self.model references the User model this manager is attached to.
        # This prevents circular imports between models.py and managers.py.
        user = self.model(phone_number=phone_number, **extra_fields)

        # set_password hashes the raw password using PBKDF2 with SHA-256 (never store plain text passwords!)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, phone_number, password=None, **extra_fields):
        """
        Create and save a SuperUser with phone number, password, and admin role.
        """
        # Superusers need staff and superuser permissions to access Django Admin
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        # In our business logic, superusers belong to the 'admin' role
        extra_fields.setdefault("role", "admin")

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(phone_number, password, **extra_fields)
