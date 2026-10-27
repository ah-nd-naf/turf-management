"""
Serializers for the locations app.

WHAT IS A SERIALIZER IN DRF?
A serializer is a two-way translator between Python/Django objects and external data formats (like JSON).
1. Serialization (Output): Converts complex Django Model instances (or QuerySets) into Python
   primitive data types (dicts, lists, strings, ints), which can easily be rendered into JSON.
2. Deserialization (Input): Converts incoming JSON request data into validated Python types
   or Django model instances.

WHY MODELSERIALIZER INSTEAD OF SERIALIZER?
- A standard `rest_framework.serializers.Serializer` requires manually declaring every single
  field, type, and validation logic.
- A `rest_framework.serializers.ModelSerializer` is an abstraction shortcut. It inspects the
  underlying Django Model and automatically generates the fields, types, and validators.
  Because Division and District models already define field types, maximum lengths, and
  constraints, ModelSerializer eliminates boilerplate code while keeping everything in sync.
"""

from rest_framework import serializers
from .models import District, Division


class DivisionSerializer(serializers.ModelSerializer):
    """
    Serializer for the Division model.

    Serializes administrative divisions of Bangladesh into JSON:
    - id: Unique primary key integer
    - name: English division name (e.g., 'Dhaka')
    - name_bn: Bengali division name (e.g., 'ঢাকা')
    - slug: URL-friendly identifier (e.g., 'dhaka')
    """

    class Meta:
        model = Division
        fields = ("id", "name", "name_bn", "slug")
        # Since this is a read-only endpoint, all fields are read-only
        read_only_fields = ("id", "name", "name_bn", "slug")


class DistrictSerializer(serializers.ModelSerializer):
    """
    Serializer for the District model.

    Serializes administrative districts of Bangladesh into JSON:
    - id: Unique primary key integer
    - name: English district name (e.g., 'Gazipur')
    - name_bn: Bengali district name (e.g., 'গাজীপুর')
    - slug: URL-friendly identifier (e.g., 'gazipur')
    - division: Primary key (ID) of the parent Division

    WHY `division` RETURNS AN INTEGER ID:
    By default, ModelSerializer represents a ForeignKey as a PrimaryKeyRelatedField.
    This outputs the parent division's ID (e.g. `"division": 3`), which is exactly
    what frontend applications need when linking a selected district back to its division.
    """

    class Meta:
        model = District
        fields = ("id", "name", "name_bn", "slug", "division")
        # Read-only public reference data
        read_only_fields = ("id", "name", "name_bn", "slug", "division")
