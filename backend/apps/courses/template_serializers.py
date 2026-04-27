"""Serializers for the Course Templates library (TASK-049)."""

import json

from rest_framework import serializers

from .template_models import CourseTemplate

# Maximum serialized size of blueprint_json accepted over the wire (256 KB).
# Prevents runaway payloads from blowing up DB row size or JSON parsing time.
BLUEPRINT_JSON_MAX_BYTES = 256_000


class CourseTemplateListSerializer(serializers.ModelSerializer):
    """Lightweight listing — omits the heavy ``blueprint_json`` payload."""

    class Meta:
        model = CourseTemplate
        fields = [
            "id",
            "slug",
            "title",
            "description",
            "category",
            "language",
            "estimated_hours",
            "level",
            "thumbnail_url",
            "is_published",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class CourseTemplateDetailSerializer(serializers.ModelSerializer):
    """Full detail serializer, used for CRUD and tenant-side preview."""

    class Meta:
        model = CourseTemplate
        fields = [
            "id",
            "slug",
            "title",
            "description",
            "category",
            "language",
            "estimated_hours",
            "level",
            "thumbnail_url",
            "blueprint_json",
            "is_published",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_by", "created_at", "updated_at"]

    def validate_blueprint_json(self, value):
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError(
                "blueprint_json must be a JSON object."
            )
        if len(json.dumps(value)) > BLUEPRINT_JSON_MAX_BYTES:
            raise serializers.ValidationError("BLUEPRINT_TOO_LARGE")
        modules = value.get("modules")
        if modules is not None and not isinstance(modules, list):
            raise serializers.ValidationError(
                "blueprint_json.modules must be a list."
            )
        return value


class CloneTemplateSerializer(serializers.Serializer):
    """Body shape for ``POST /admin/course-templates/{id}/clone/``."""

    title_override = serializers.CharField(
        required=False, allow_blank=True, max_length=300
    )
    module_prefix = serializers.CharField(
        required=False, allow_blank=True, max_length=64
    )
