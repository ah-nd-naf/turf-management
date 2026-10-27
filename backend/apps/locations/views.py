"""
Views for the locations app.

WHY DRF GENERICS (ListAPIView)?
In Django REST Framework:
1. `APIView`: The foundational class-based view. You have to manually write the `get()`
   method, call `.all()`, pass data to the serializer, and return a `Response()`.
2. `generics.ListAPIView`: A pre-built view specifically tailored for read-only listing.
   It encapsulates standard patterns (querying data, applying filters, serializing,
   paginating, and returning HTTP 200 responses) into a clean, declarative interface.
   Using `ListAPIView` reduces boilerplate and enforces consistent DRF architectural patterns.

WHY EXPLICIT `permission_classes = [AllowAny]`?
In `config/settings/base.py`, we set:
    `REST_FRAMEWORK['DEFAULT_PERMISSION_CLASSES'] = ('rest_framework.permissions.IsAuthenticated',)`
This means by default, ANY endpoint in the entire project requires a valid JWT Bearer token!
Because Division and District lists are public reference data needed by unauthenticated
guests (e.g. browsing turfs or registering an account), we must EXPLICITLY override the
default permission with `[AllowAny]`.

WHY `pagination_class = None`?
Our project setting sets a global page size of 20 (`PageNumberPagination`).
However, Bangladesh has exactly 8 divisions and 64 districts.
When a frontend application renders a `<select>` or autocomplete dropdown, it needs the
ENTIRE list of options at once. Paginated responses (with `next`, `previous`, `results`)
would require frontend code to make multiple round-trips to populate a single dropdown.
Setting `pagination_class = None` disables pagination for these specific endpoints,
returning a clean JSON array `[...]`.

WHY `select_related("division")`?
When a district is serialized, accessing its parent division (or validating relationships)
could trigger an additional database query for every single row (the infamous "N+1 query" problem).
`select_related("division")` performs an SQL `INNER JOIN` right in the initial `SELECT` query,
fetching all district and parent division columns in a single, lightning-fast database round-trip.
"""

from rest_framework import generics
from rest_framework.permissions import AllowAny

from .filters import DistrictFilter
from .models import District, Division
from .serializers import DistrictSerializer, DivisionSerializer


class DivisionListView(generics.ListAPIView):
    """
    Public read-only list of all 8 administrative divisions of Bangladesh.

    Endpoint:
        GET /api/v1/locations/divisions/

    Permissions:
        Public (AllowAny) - No authentication required.

    Response format:
        [
            {
                "id": 1,
                "name": "Barishal",
                "name_bn": "বরিশাল",
                "slug": "barishal"
            },
            ...
        ]
    """

    queryset = Division.objects.all()
    serializer_class = DivisionSerializer
    permission_classes = [AllowAny]
    pagination_class = None


class DistrictListView(generics.ListAPIView):
    """
    Public read-only list of administrative districts of Bangladesh.

    Endpoint:
        GET /api/v1/locations/districts/
        GET /api/v1/locations/districts/?division=<id>

    Permissions:
        Public (AllowAny) - No authentication required.

    Filtering:
        Filter districts by parent Division ID using `?division=<id>` query parameter.

    Performance:
        Uses `select_related("division")` to join the Division table in a single SQL query,
        preventing N+1 queries.

    Response format:
        [
            {
                "id": 1,
                "name": "Barguna",
                "name_bn": "বরগুনা",
                "slug": "barguna",
                "division": 1
            },
            ...
        ]
    """

    queryset = District.objects.select_related("division").all()
    serializer_class = DistrictSerializer
    permission_classes = [AllowAny]
    pagination_class = None
    filterset_class = DistrictFilter
