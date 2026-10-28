"""
Views for the accounts app.

WHY THESE VIEWS EXIST:
1. RegisterView:
   - Provides public self-registration for new 'customer' and 'owner' accounts.
   - Explicitly marked AllowAny because users who are not yet registered cannot be authenticated.
   - Handled via DRF's CreateAPIView, which handles validation, calls serializer.save(),
     and returns HTTP 201 Created on success or HTTP 400 with validation errors on failure.

2. LoginView:
   - Provides public login via phone_number and password.
   - Subclasses SimpleJWT's TokenObtainPairView to use our CustomTokenObtainPairSerializer.
   - Explicitly marked AllowAny because unauthenticated visitors must be able to log in.
   - Returns HTTP 200 with access/refresh tokens and basic user profile information.

3. CustomTokenRefreshView:
   - Provides an endpoint to exchange an unexpired refresh token for a fresh access token.
   - Subclasses SimpleJWT's TokenRefreshView.
   - Explicitly marked AllowAny because when a user's access token expires, their request
     to refresh the token is unauthenticated by definition.
"""

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics, permissions, status
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
)
from rest_framework_simplejwt.views import (
    TokenRefreshView as SimpleJWTTokenRefreshView,
)

from .serializers import (
    CustomTokenObtainPairSerializer,
    LoginResponseSerializer,
    UserRegisterSerializer,
)


@extend_schema(
    tags=["Auth"],
    summary="Register a new customer or turf owner account",
    description=(
        "Public self-registration endpoint for customers and turf owners.\n\n"
        "**Rules & Constraints:**\n"
        "- `phone_number`: Bangladeshi format (e.g. `017XXXXXXXX`), unique.\n"
        "- `role`: Must be either `'customer'` or `'owner'`.\n"
        "- `role='admin'` is strictly rejected to prevent privilege escalation.\n"
        "- If `role='owner'`, `business_name` is mandatory and creates an OwnerProfile.\n"
        "- Password and confirmation must match and satisfy standard security checks.\n"
        "- Passwords are never returned in the API response."
    ),
    responses={
        status.HTTP_201_CREATED: UserRegisterSerializer,
        status.HTTP_400_BAD_REQUEST: OpenApiResponse(
            description="Validation failure (e.g., duplicate phone/email, password mismatch, admin role attempted, missing business name)."
        ),
    },
)
class RegisterView(generics.CreateAPIView):
    """
    User registration endpoint.
    AllowAny is set explicitly to override the global IsAuthenticated default in settings.
    """

    permission_classes = (permissions.AllowAny,)
    serializer_class = UserRegisterSerializer


@extend_schema(
    tags=["Auth"],
    summary="Log in with phone number and password",
    description=(
        "Authenticates a user using their 11-digit Bangladeshi mobile number and password.\n\n"
        "**Returns:**\n"
        "- `access`: JWT access token (valid for 60 minutes, contains custom claims 'role', 'full_name', 'phone_number').\n"
        "- `refresh`: JWT refresh token (valid for 7 days).\n"
        "- Basic user details: `id`, `phone_number`, `full_name`, `role`, and `user` object."
    ),
    responses={
        status.HTTP_200_OK: LoginResponseSerializer,
        status.HTTP_401_UNAUTHORIZED: OpenApiResponse(
            description="No active account found with the given credentials."
        ),
    },
)
class LoginView(TokenObtainPairView):
    """
    User authentication endpoint.
    Issues JWT access & refresh tokens on successful credentials verification.
    AllowAny is set explicitly to allow unauthenticated clients to log in.
    """

    permission_classes = (permissions.AllowAny,)
    serializer_class = CustomTokenObtainPairSerializer


@extend_schema(
    tags=["Auth"],
    summary="Refresh an expired JWT access token",
    description=(
        "Takes a valid JWT refresh token and returns a new access token.\n"
        "With token rotation enabled, a new refresh token is also issued."
    ),
    responses={
        status.HTTP_200_OK: OpenApiResponse(description="Token refreshed successfully."),
        status.HTTP_401_UNAUTHORIZED: OpenApiResponse(description="Token is invalid or expired."),
    },
)
class CustomTokenRefreshView(SimpleJWTTokenRefreshView):
    """
    Token refresh endpoint.
    AllowAny is set explicitly so clients whose access tokens have expired can obtain a fresh one.
    """

    permission_classes = (permissions.AllowAny,)

