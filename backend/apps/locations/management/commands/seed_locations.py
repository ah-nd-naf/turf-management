"""
Management command to seed Bangladesh locations (8 divisions and 64 districts).

WHY THIS COMMAND EXISTS:
1. Standardized Geographical Data:
   Both turf registration (owner side) and turf search (customer side) rely on a fixed,
   hierarchical list of Bangladesh's 8 administrative divisions and 64 districts.
2. Automation & Consistency:
   Instead of manually adding 72 records through Django Admin or running raw SQL inserts,
   this command reads a structured JSON file and seeds the database automatically in seconds.
3. Idempotency (Safe to run multiple times):
   Using `update_or_create` ensures that running this command multiple times (e.g. on every deploy,
   in CI/CD pipelines, or after adding Bengali translations) will NEVER create duplicate rows
   or throw UniqueConstraint integrity errors.
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.locations.models import District, Division


class Command(BaseCommand):
    help = "Seed database with all 8 Divisions and 64 Districts of Bangladesh from bd_locations.json (Idempotent)."

    def handle(self, *args, **options):
        # Locate the JSON file relative to this command file:
        # File hierarchy:
        # backend/apps/locations/management/commands/seed_locations.py
        # -> parent (commands)
        # -> parent.parent (management)
        # -> parent.parent.parent (locations)
        # -> / data / bd_locations.json
        json_path = (
            Path(__file__).resolve().parent.parent.parent
            / "data"
            / "bd_locations.json"
        )

        if not json_path.exists():
            raise CommandError(f"Locations data file not found at: {json_path}")

        self.stdout.write(
            self.style.NOTICE(f"Reading locations data from: {json_path}")
        )

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                divisions_data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            raise CommandError(f"Failed to read or parse JSON file: {e}") from e

        # Counters to track operation results
        divisions_created = 0
        divisions_updated = 0
        districts_created = 0
        districts_updated = 0

        # Wrap everything in a database transaction so that if anything fails,
        # the entire operation rolls back, keeping the database in a clean state.
        with transaction.atomic():
            for div_item in divisions_data:
                # 1. Seed or update Division
                # slug is unique for divisions, so we look up by slug.
                division, div_created = Division.objects.update_or_create(
                    slug=div_item["slug"],
                    defaults={
                        "name": div_item["name"],
                        "name_bn": div_item.get("name_bn", ""),
                    },
                )

                if div_created:
                    divisions_created += 1
                else:
                    divisions_updated += 1

                # 2. Seed or update Districts under this division
                for dist_item in div_item.get("districts", []):
                    # District has a unique constraint on (division, name).
                    # We look up by division + name to ensure idempotency.
                    _district, dist_created = District.objects.update_or_create(
                        division=division,
                        name=dist_item["name"],
                        defaults={
                            "name_bn": dist_item.get("name_bn", ""),
                            "slug": dist_item["slug"],
                        },
                    )

                    if dist_created:
                        districts_created += 1
                    else:
                        districts_updated += 1

        # Summary reports
        total_divisions = Division.objects.count()
        total_districts = District.objects.count()

        self.stdout.write(
            self.style.SUCCESS(
                f"Locations seed complete:\n"
                f"  - Divisions: {divisions_created} created, {divisions_updated} updated (Total in DB: {total_divisions})\n"
                f"  - Districts: {districts_created} created, {districts_updated} updated (Total in DB: {total_districts})"
            )
        )
