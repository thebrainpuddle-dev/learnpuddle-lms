"""Serializers for TASK-058 — Auto-Translation Service.

TASK-064b additions
-------------------
``ContentTranslationReviewSerializer``  — read-only serializer returned by all
    approve / reject / edit / publish endpoints; includes review state fields.
``FieldEditSerializer``                 — validates the ``edited_text`` body
    sent to the PUT .../edit/ endpoint.
"""

from __future__ import annotations

from rest_framework import serializers

from .models import ContentTranslation, TranslationJobRun


class ContentTranslationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentTranslation
        fields = [
            "id",
            "source_type",
            "source_id",
            "field",
            "target_language",
            "translated_text",
            "provider",
            "model",
            "source_hash",
            "translated_at",
            "updated_at",
        ]
        read_only_fields = fields


class ContentTranslationReviewSerializer(serializers.ModelSerializer):
    """Serializer for TASK-064b review endpoints and the admin GET endpoint.

    Returns the full translation row including review state fields so the
    frontend can update its local store without a follow-up GET.

    This is a strict superset of ``ContentTranslationSerializer`` — all fields
    from the base serializer are present plus the TASK-064b review fields
    (``edited_text``, ``review_status``, ``reviewed_by``, ``reviewed_by_email``,
    ``reviewed_at``, ``published_at``).
    """

    reviewed_by_email = serializers.SerializerMethodField()

    class Meta:
        model = ContentTranslation
        fields = [
            # ---- base fields (ContentTranslationSerializer parity) ----
            "id",
            "source_type",
            "source_id",
            "field",
            "target_language",
            "translated_text",
            "provider",
            "model",
            "source_hash",
            "translated_at",
            "updated_at",
            # ---- TASK-064b review fields ----
            "edited_text",
            "review_status",
            "reviewed_by",
            "reviewed_by_email",
            "reviewed_at",
            "published_at",
        ]
        read_only_fields = fields

    def get_reviewed_by_email(self, obj) -> str | None:
        if obj.reviewed_by_id:
            return getattr(obj.reviewed_by, "email", None)
        return None


class FieldEditSerializer(serializers.Serializer):
    """Validates the body of PUT .../fields/{field}/edit/?lang=xx."""

    # TASK-064b M1: cap at 50 KB (50 000 chars) to mirror TASK-058's FIELD_TOO_LARGE guard.
    edited_text = serializers.CharField(
        allow_blank=False,
        max_length=50_000,
        help_text="Admin's manual correction for this translation field (max 50 000 chars).",
        error_messages={
            "max_length": "FIELD_TOO_LARGE",
        },
    )


class TranslationJobRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = TranslationJobRun
        fields = [
            "id",
            "kind",
            "target_id",
            "target_languages",
            "status",
            "started_at",
            "finished_at",
            "fields_translated",
            "error",
            "created_at",
        ]
        read_only_fields = fields
