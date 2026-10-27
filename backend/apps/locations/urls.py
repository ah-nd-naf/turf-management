"""
URL routing configuration for the locations app.

HOW URL ROUTING WORKS IN DJANGO & DRF:
1. `config/urls.py` acts as the master telephone switchboard. It intercepts requests
   starting with `api/v1/locations/` and forwards them to this file (`apps/locations/urls.py`)
   using `include('apps.locations.urls')`.
2. This file matches the remainder of the path:
   - `divisions/` -> routes to `DivisionListView`
   - `districts/` -> routes to `DistrictListView`
3. Calling `.as_view()` transforms the DRF class-based view into a callable HTTP request handler.
4. Setting `app_name = "locations"` namespaces these routes so they can be uniquely reversed
   as `locations:division-list` and `locations:district-list`.
"""

from django.urls import path
from .views import DistrictListView, DivisionListView

app_name = "locations"

urlpatterns = [
    path("divisions/", DivisionListView.as_view(), name="division-list"),
    path("districts/", DistrictListView.as_view(), name="district-list"),
]
