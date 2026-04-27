"""DRF serializers for TASK-060 — AI Course Generator."""

from __future__ import annotations

from rest_framework import serializers

from .models import CourseGenerationJob


class CourseGenerationJobSerializer(serializers.ModelSerializer):
    """Read-serializer for CourseGenerationJob (list + detail)."""

    created_by_email = serializers.SerializerMethodField()
    draft_course_id = serializers.SerializerMethodField()

    class Meta:
        model = CourseGenerationJob
        fields = [
            "id",
            "source_type",
            "source_metadata",
            "extracted_char_count",
            "status",
            "error",
            "outline_json",
            "provider",
            "model",
            "tokens_prompt",
            "tokens_completion",
            "draft_course_id",
            "created_by_email",
            "started_at",
            "finished_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_created_by_email(self, obj: CourseGenerationJob) -> str | None:
        if obj.created_by:
            return obj.created_by.email
        return None

    def get_draft_course_id(self, obj: CourseGenerationJob) -> str | None:
        if obj.draft_course_id:
            return str(obj.draft_course_id)
        return None


class CourseGenerationJobListSerializer(serializers.ModelSerializer):
    """Lightweight list serializer (omits outline_json for performance)."""

    created_by_email = serializers.SerializerMethodField()
    draft_course_id = serializers.SerializerMethodField()

    class Meta:
        model = CourseGenerationJob
        fields = [
            "id",
            "source_type",
            "status",
            "error",
            "provider",
            "model",
            "draft_course_id",
            "created_by_email",
            "created_at",
            "finished_at",
        ]
        read_only_fields = fields

    def get_created_by_email(self, obj: CourseGenerationJob) -> str | None:
        if obj.created_by:
            return obj.created_by.email
        return None

    def get_draft_course_id(self, obj: CourseGenerationJob) -> str | None:
        if obj.draft_course_id:
            return str(obj.draft_course_id)
        return None


class MaterialiseResponseSerializer(serializers.Serializer):
    """Response body for POST .../materialise/"""

    draft_course_id = serializers.UUIDField()
    idempotent = serializers.BooleanField()
