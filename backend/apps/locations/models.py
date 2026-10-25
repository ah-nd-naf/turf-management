"""
Models for the locations app.

WHY THESE MODELS EXIST:
1. Division:
   Represents the top-level administrative division of Bangladesh (e.g., Dhaka, Chattogram, Sylhet).
   There are exactly 8 official divisions in Bangladesh.
   It acts as the parent category in geographical filtering.

2. District:
   Represents an administrative district (Zila) within a division (e.g., Gazipur, Narayanganj inside Dhaka).
   There are exactly 64 official districts in Bangladesh.
   Every district belongs to exactly one division via a ForeignKey.

HOW THEY FIT INTO THE TURF PLATFORM:
- Turf Registration (Part 2):
  When a turf owner registers a new sports arena, they select the Division and District
  where the turf is physically located.
- Customer Search (Part 3):
  Customers filter available turfs by Division -> District -> Date.
  Using standardized, pre-seeded Division and District tables ensures data consistency:
  customers and owners use the exact same spelling, IDs, and location hierarchy, preventing
  typos, duplicates, and misaligned search results.
"""

from django.db import models


class Division(models.Model):
    """
    Represents one of the 8 administrative divisions of Bangladesh.
    """

    name = models.CharField(
        max_length=50,
        unique=True,
        help_text="English name of division, e.g. Dhaka",
    )
    name_bn = models.CharField(
        max_length=50,
        blank=True,
        help_text="Bengali name of division, e.g. ঢাকা",
    )
    slug = models.SlugField(
        max_length=50,
        unique=True,
        help_text="URL-friendly identifier, e.g. dhaka",
    )

    class Meta:
        ordering = ("name",)
        verbose_name = "Division"
        verbose_name_plural = "Divisions"

    def __str__(self) -> str:
        return self.name


class District(models.Model):
    """
    Represents one of the 64 administrative districts of Bangladesh,
    belonging to a specific Division.
    """

    division = models.ForeignKey(
        Division,
        on_delete=models.CASCADE,
        related_name="districts",
        help_text="Division to which this district belongs",
    )
    name = models.CharField(
        max_length=50,
        help_text="English name of district, e.g. Gazipur",
    )
    name_bn = models.CharField(
        max_length=50,
        blank=True,
        help_text="Bengali name of district, e.g. গাজীপুর",
    )
    slug = models.SlugField(
        max_length=50,
        help_text="URL-friendly identifier, e.g. gazipur",
    )

    class Meta:
        ordering = ("name",)
        verbose_name = "District"
        verbose_name_plural = "Districts"
        unique_together = ("division", "name")

    def __str__(self) -> str:
        return f"{self.name} ({self.division.name})"
