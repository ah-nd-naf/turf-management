"""
Filter classes for the locations app.

HOW DJANGO-FILTER POWERS QUERY PARAMETERS:
django-filter bridges URL query parameters (like `?division=1`) with Django ORM lookups.
Instead of manually writing `request.query_params.get('division')` and parsing integers
inside the view, django-filter provides a declarative `FilterSet`.

It automatically:
1. Extracts the parameter from the request URL.
2. Validates that the input data type matches (e.g., verifying `1` is a valid integer).
3. Applies the `.filter()` query directly to the Django QuerySet.
"""

import django_filters
from .models import District


class DistrictFilter(django_filters.FilterSet):
    """
    FilterSet for filtering Districts by query parameters.

    Supported query parameters:
        GET /api/v1/locations/districts/?division=<id>

    Example:
        GET /api/v1/locations/districts/?division=3
        Returns only districts belonging to Division with ID 3 (e.g., Dhaka).

    WHY `field_name="division_id"`:
    The `District` model has a ForeignKey called `division`.
    In PostgreSQL, Django creates an underlying integer column named `division_id`.
    By filtering directly on `division_id`, we match the foreign key column directly
    without performing an unnecessary SQL table join for the WHERE clause.
    """

    division = django_filters.NumberFilter(
        field_name="division_id",
        help_text="Filter districts by parent Division ID (e.g. ?division=3)",
    )

    class Meta:
        model = District
        fields = ["division"]
