"""
Serializers for the accounts app.

WHY THESE SERIALIZERS EXIST:
1. UserRegisterSerializer:
   - Validates user input when creating a new account (phone format, password rules, role restrictions).
   - Prevents privilege escalation: rejects any attempt to self-register as 'admin'.
   - Ensures transactional integrity: creates OwnerProfile atomically if role is 'owner'.
   - Security guarantee: password fields are write-only and never included in API responses.

2. CustomTokenObtainPairSerializer:
   - Subclasses SimpleJWT's TokenObtainPairSerializer to authenticate via phone_number + password.
   - Embeds custom claims ('role', 'full_name', 'phone_number') directly into the access token payload.
   - Augments the login response body with user profile data (id, phone_number, full_name, role)
     alongside the access and refresh tokens.

3. LoginResponseSerializer & UserSummarySerializer:
   - Provide OpenAPI / Swagger schema definitions for drf-spectacular documentation.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import OwnerProfile, bd_phone_validator

User = get_user_model()


class UserRegisterSerializer(serializers.ModelSerializer):
    """
    Serializer for public user registration.

    Supported roles:
    - 'customer': Standard user for finding and booking turfs.
    - 'owner': Turf operator. Requires 'business_name' to create an OwnerProfile.

    Security rules:
    - 'admin' role cannot self-register; requests are rejected with a 400 error.
    - Password must be confirmed with 'password_confirm'.
    - Password must satisfy Django's configured password validators (length, complexity, etc.).
    - Passwords are write-only and NEVER returned in API responses.
    """

    # Explicit phone_number field with Bangladeshi phone validator
    phone_number = serializers.CharField(
        max_length=15,
        validators=[bd_phone_validator],
        help_text="11-digit Bangladeshi mobile number starting with 01 (e.g., 017XXXXXXXX).",
    )

    full_name = serializers.CharField(
        max_length=150,
        required=True,
        allow_blank=False,
        help_text="User's full name.",
    )

    email = serializers.EmailField(
        required=False,
        allow_null=True,
        default=None,
        help_text="Optional contact email. Must be unique if provided.",
    )

    # Password inputs: write_only=True ensures they are never read or returned in serialized output
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

    # Business name: required when role == 'owner', ignored/not required for customers
    business_name = serializers.CharField(
        required=False,
        allow_blank=True,
        write_only=True,
        max_length=200,
        help_text="Required when role is 'owner'. Operating name of the turf business.",
    )

    class Meta:
        model = User
        fields = (
            "id",
            "phone_number",
            "full_name",
            "email",
            "role",
            "business_name",
            "password",
            "password_confirm",
            "created_at",
        )
        read_only_fields = ("id", "created_at")

    def validate_phone_number(self, value):
        """
        Validate phone number uniqueness before database hit.
        """
        cleaned_phone = value.strip()
        if User.objects.filter(phone_number=cleaned_phone).exists():
            raise serializers.ValidationError("A user with this phone number already exists.")
        return cleaned_phone

    def validate_role(self, value):
        """
        Validate user role.
        Strictly rejects 'admin' to prevent privilege escalation attacks.
        Only 'customer' and 'owner' are allowed.
        """
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

    def validate_email(self, value):
        """
        Ensure email is lowercase and unique if provided.
        """
        if value:
            cleaned_email = value.lower().strip()
            if User.objects.filter(email__iexact=cleaned_email).exists():
                raise serializers.ValidationError("A user with this email address already exists.")
            return cleaned_email
        return None

    def validate(self, attrs):
        """
        Cross-field validations:
        1. Check that password == password_confirm.
        2. Run Django's validate_password on the raw password.
        3. If role is 'owner', verify that business_name is provided.
        """
        password = attrs.get("password")
        password_confirm = attrs.get("password_confirm")

        # 1. Password confirmation check
        if password != password_confirm:
            raise serializers.ValidationError({
                "password_confirm": "Password confirmation does not match the password."
            })

        # 2. Run Django's built-in password validators (length, common passwords, similarity, numeric)
        try:
            validate_password(password)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({
                "password": list(exc.messages)
            })

        # 3. Require business_name if registering as an owner
        role = attrs.get("role", User.Role.CUSTOMER)
        if role == User.Role.OWNER:
            business_name = attrs.get("business_name")
            if not business_name or not str(business_name).strip():
                raise serializers.ValidationError({
                    "business_name": "Business name is required when registering as a turf owner."
                })

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        """
        Create the User using UserManager.create_user (which properly hashes the password).
        If the role is 'owner', create the associated OwnerProfile in the same atomic transaction.
        """
        # Remove non-model write-only fields
        validated_data.pop("password_confirm", None)
        password = validated_data.pop("password")
        business_name = validated_data.pop("business_name", None)

        # Normalize empty email to None for PostgreSQL unique constraint
        if validated_data.get("email") == "":
            validated_data["email"] = None

        # create_user hashes the password using PBKDF2 with SHA-256
        user = User.objects.create_user(password=password, **validated_data)

        # If role is owner, create associated OwnerProfile within the atomic block
        if user.role == User.Role.OWNER:
            OwnerProfile.objects.create(
                user=user,
                business_name=business_name.strip(),
            )

        return user

    def to_representation(self, instance):
        """
        Guarantee password fields are never leaked, and attach business_name
        if the user is an owner with an existing profile.
        """
        data = super().to_representation(instance)

        # Defense-in-depth: ensure passwords are never in serialized response
        data.pop("password", None)
        data.pop("password_confirm", None)

        # Include business_name in response if owner profile exists
        if instance.role == User.Role.OWNER and hasattr(instance, "owner_profile"):
            data["business_name"] = instance.owner_profile.business_name
        else:
            data["business_name"] = None

        return data


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Custom SimpleJWT serializer authenticating users via phone_number and password.

    Enhancements over default TokenObtainPairSerializer:
    1. Authenticates against User.phone_number (our custom USERNAME_FIELD).
    2. Adds custom claims ('role', 'full_name', 'phone_number') into the JWT payload.
    3. Adds basic user details (id, phone_number, full_name, role) directly into
       the HTTP response body alongside 'access' and 'refresh'.
    """

    # Declare explicit fields so drf-spectacular documents them correctly
    phone_number = serializers.CharField(
        write_only=True,
        required=True,
        help_text="11-digit Bangladeshi mobile number (e.g. 017XXXXXXXX).",
    )
    password = serializers.CharField(
        write_only=True,
        required=True,
        style={"input_type": "password"},
        help_text="Account password.",
    )

    @classmethod
    def get_token(cls, user):
        """
        Embed custom claims into the JWT token payload.
        These claims can be decoded client-side without making an additional API call.
        """
        token = super().get_token(user)

        # Add custom claims
        token["role"] = user.role
        token["full_name"] = user.full_name
        token["phone_number"] = user.phone_number

        return token

    def validate(self, attrs):
        """
        Validate credentials, generate tokens, and augment the response payload.
        """
        # Superclass handles authenticate(phone_number=..., password=...) and issues tokens
        data = super().validate(attrs)

        # Include basic user info directly alongside access and refresh
        data["id"] = self.user.id
        data["phone_number"] = self.user.phone_number
        data["full_name"] = self.user.full_name
        data["role"] = self.user.role

        # Also provide nested user object for client convenience
        data["user"] = {
            "id": self.user.id,
            "phone_number": self.user.phone_number,
            "full_name": self.user.full_name,
            "role": self.user.role,
        }

        # If owner, include business_name
        if self.user.role == User.Role.OWNER and hasattr(self.user, "owner_profile"):
            data["business_name"] = self.user.owner_profile.business_name
            data["user"]["business_name"] = self.user.owner_profile.business_name
        else:
            data["business_name"] = None
            data["user"]["business_name"] = None

        return data


class UserSummarySerializer(serializers.Serializer):
    """
    Basic user summary schema for OpenAPI documentation.
    """

    id = serializers.IntegerField(read_only=True)
    phone_number = serializers.CharField(read_only=True)
    full_name = serializers.CharField(read_only=True)
    role = serializers.CharField(read_only=True)
    business_name = serializers.CharField(read_only=True, required=False, allow_null=True)


class LoginResponseSerializer(serializers.Serializer):
    """
    Schema definition for the login response body in Swagger / OpenAPI documentation.
    """

    access = serializers.CharField(read_only=True, help_text="JWT Access token (valid for 60 minutes).")
    refresh = serializers.CharField(read_only=True, help_text="JWT Refresh token (valid for 7 days).")
    id = serializers.IntegerField(read_only=True)
    phone_number = serializers.CharField(read_only=True)
    full_name = serializers.CharField(read_only=True)
    role = serializers.CharField(read_only=True)
    business_name = serializers.CharField(read_only=True, required=False, allow_null=True)
    user = UserSummarySerializer(read_only=True)
