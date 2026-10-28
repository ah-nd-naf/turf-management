"""
URL configuration for Turf Management project.

API URL STRUCTURE:
- /admin/                   Django Admin portal
- /api/schema/              OpenAPI 3.0 schema generation endpoint (drf-spectacular)
- /api/docs/                Interactive Swagger UI documentation
- /api/v1/auth/             Authentication endpoints (apps.accounts)
- /api/v1/locations/        Division & District location endpoints (apps.locations)
"""

from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    # Django Admin Site
    path('admin/', admin.site.urls),

    # OpenAPI 3 Schema & Swagger UI Documentation
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),

    # API v1 App Endpoints
    path('api/v1/auth/', include('apps.accounts.urls')),
    path('api/v1/locations/', include('apps.locations.urls')),
]

