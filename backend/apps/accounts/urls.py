"""
URL routing configuration for accounts authentication endpoints.

WHY THIS FILE EXISTS:
Each Django application maintains its own urls.py to keep routes modular and decoupled.
These routes are mounted under '/api/v1/auth/' in config/urls.py.

AVAILABLE ROUTES:
- POST /api/v1/auth/register/       -> Register a new customer or owner account
- POST /api/v1/auth/login/          -> Obtain JWT access and refresh tokens via phone_number + password
- POST /api/v1/auth/token/refresh/  -> Refresh an access token using a valid refresh token
"""

from django.urls import path

from .views import CustomTokenRefreshView, LoginView, RegisterView

app_name = "accounts"

urlpatterns = [
    # Customer and Owner Registration
    path("register/", RegisterView.as_view(), name="register"),
    # JWT Phone + Password Login
    path("login/", LoginView.as_view(), name="login"),
    # JWT Access Token Refresh
    path("token/refresh/", CustomTokenRefreshView.as_view(), name="token_refresh"),
]
