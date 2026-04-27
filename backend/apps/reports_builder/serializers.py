"""
apps/reports_builder/serializers.py
--------------------------------------
DRF serializers for the Custom Report Builder.

Security:
  * FilterSchema, GroupBySchema, AggregateSchema validate against per-source
    field whitelists — prevents field-enumeration attacks.
  * ReportDefinitionSerializer.validate() does a dry-parse schema check (no
    DB hit) before the definition is persisted.
  * RecipientValidationMixin rejects email addresses not belonging to the
    current tenant.
"""

from __future__ import annotations

import logging

from rest_framework import serializers

from .models import ReportDefinition, ReportRun, ReportSchedule
from .query_engine import (
    SOURCE_FIELD_WHITELISTS,
    SOURCE_QS_MAP,
    SUPPORTED_OPS,
    AGGREGATE_FN_MAP,
    UNKNOWN_FIELD,
    UNSUPPORTED_OPERATOR,
    UNKNOWN_DATA_SOURCE,
    validate_definition_schema,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Sub-schemas
# ---------------------------------------------------------------------------


class FilterSchemaSerializer(serializers.Serializer):
    """Validates a single filter entry in filters_json."""

    field = serializers.CharField(max_length=100)
    op = serializers.CharField(max_length=20)
    value = serializers.JSONField()

    def validate_op(self, value: str) -> str:
        if value not in SUPPORTED_OPS:
            raise serializers.ValidationError(
                f"{UNSUPPORTED_OPERATOR}: {value!r} is not a supported operator. "
                f"Supported: {sorted(SUPPORTED_OPS)}"
            )
        return value


class GroupBySchemaSerializer(serializers.Serializer):
    """Validates a group-by field string."""

    field = serializers.CharField(max_length=100)


class AggregateSchemaSerializer(serializers.Serializer):
    """Validates an aggregate entry."""

    fn = serializers.ChoiceField(choices=list(AGGREGATE_FN_MAP.keys()))
    field = serializers.CharField(max_length=100, default="id")
    alias = serializers.CharField(max_length=100, required=False, allow_blank=True)


# ---------------------------------------------------------------------------
# ReportDefinition serializer
# ---------------------------------------------------------------------------


class ReportDefinitionSerializer(serializers.ModelSerializer):
    """Full serializer for ReportDefinition CRUD."""

    class Meta:
        model = ReportDefinition
        fields = [
            "id",
            "name",
            "description",
            "data_source",
            "filters_json",
            "group_by_json",
            "aggregates_json",
            "created_by",
            "created_at",
            "updated_at",
            "is_soft_deleted",
        ]
        read_only_fields = ["id", "created_by", "created_at", "updated_at", "is_soft_deleted"]

    def validate(self, attrs: dict) -> dict:
        """Dry-parse schema — validate filters, group-by, aggregates before save."""
        data_source = attrs.get("data_source", "")
        filters = attrs.get("filters_json", [])
        group_by_raw = attrs.get("group_by_json", [])
        aggregates = attrs.get("aggregates_json", [])

        # group_by_json may be a list of strings or list of {"field": ...} dicts
        group_by_fields: list[str] = []
        for item in group_by_raw:
            if isinstance(item, str):
                group_by_fields.append(item)
            elif isinstance(item, dict) and "field" in item:
                group_by_fields.append(item["field"])

        errors = validate_definition_schema(
            data_source=data_source,
            filters=filters,
            group_by=group_by_fields,
            aggregates=aggregates,
        )
        if errors:
            raise serializers.ValidationError({"definition_schema": errors})

        return attrs

    def validate_filters_json(self, value):
        """Validate each filter entry against FilterSchemaSerializer."""
        if not isinstance(value, list):
            raise serializers.ValidationError("filters_json must be a list")
        errors = []
        for i, item in enumerate(value):
            s = FilterSchemaSerializer(data=item)
            if not s.is_valid():
                errors.append({f"filter[{i}]": s.errors})
        if errors:
            raise serializers.ValidationError(errors)
        return value

    def validate_group_by_json(self, value):
        """Validate each group-by entry."""
        if not isinstance(value, list):
            raise serializers.ValidationError("group_by_json must be a list")
        return value

    def validate_aggregates_json(self, value):
        """Validate each aggregate entry."""
        if not isinstance(value, list):
            raise serializers.ValidationError("aggregates_json must be a list")
        errors = []
        for i, item in enumerate(value):
            s = AggregateSchemaSerializer(data=item)
            if not s.is_valid():
                errors.append({f"aggregate[{i}]": s.errors})
        if errors:
            raise serializers.ValidationError(errors)
        return value


class ReportDefinitionListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views."""

    class Meta:
        model = ReportDefinition
        fields = [
            "id",
            "name",
            "description",
            "data_source",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# ReportSchedule serializer
# ---------------------------------------------------------------------------


class ReportScheduleSerializer(serializers.ModelSerializer):
    """Serializer for ReportSchedule CRUD."""

    class Meta:
        model = ReportSchedule
        fields = [
            "id",
            "cadence",
            "run_at_hour",
            "run_at_day_of_week",
            "run_at_day_of_month",
            "recipients_json",
            "enabled",
            "last_run_at",
            "last_run_status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "last_run_at", "last_run_status", "created_at", "updated_at"]

    def validate_recipients_json(self, value):
        """Reject email addresses not belonging to the current tenant.

        MVP: tenant-internal only.
        External addresses are rejected with EXTERNAL_RECIPIENT_NOT_ALLOWED.
        """
        if not isinstance(value, list):
            raise serializers.ValidationError("recipients_json must be a list of email strings")

        request = self.context.get("request")
        if request is None or not hasattr(request, "tenant"):
            raise serializers.ValidationError(
                "recipients_json cannot be validated without tenant context"
            )

        tenant = request.tenant
        if tenant is None:
            raise serializers.ValidationError(
                "recipients_json cannot be validated without tenant context"
            )

        from apps.users.models import User

        # Use all_objects (explicit Manager) to avoid relying on thread-local
        # TenantManager state, which may be None in Celery / test contexts.
        tenant_emails = set(
            User.all_objects.filter(tenant=tenant)
            .values_list("email", flat=True)
        )
        tenant_emails_lower = {e.lower() for e in tenant_emails}

        errors = []
        for email in value:
            if not isinstance(email, str):
                errors.append(f"Invalid email: {email!r}")
                continue
            if email.lower() not in tenant_emails_lower:
                errors.append(
                    f"EXTERNAL_RECIPIENT_NOT_ALLOWED: {email!r} is not a user of this tenant"
                )

        if errors:
            raise serializers.ValidationError(errors)

        return value

    def validate_run_at_hour(self, value):
        if not 0 <= value <= 23:
            raise serializers.ValidationError("run_at_hour must be 0–23")
        return value

    def validate_run_at_day_of_week(self, value):
        if value is not None and not 0 <= value <= 6:
            raise serializers.ValidationError("run_at_day_of_week must be 0–6")
        return value

    def validate_run_at_day_of_month(self, value):
        if value is not None and not 1 <= value <= 28:
            raise serializers.ValidationError("run_at_day_of_month must be 1–28")
        return value


# ---------------------------------------------------------------------------
# ReportRun serializer
# ---------------------------------------------------------------------------


class ReportRunSerializer(serializers.ModelSerializer):
    """Read-only serializer for ReportRun history."""

    class Meta:
        model = ReportRun
        fields = [
            "id",
            "definition",
            "run_by",
            "params_snapshot_json",
            "started_at",
            "finished_at",
            "row_count",
            "artifact_path",
            "artifact_sha256",
            "status",
            "error",
        ]
        read_only_fields = fields
