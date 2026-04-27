"""
apps/reports_builder/query_engine.py
--------------------------------------
Safe query engine for the Custom Report Builder.

Design principles:
  * No dynamic eval, no .extra(), no raw SQL, no RawSQL() injection surface.
  * Data sources are a strict whitelist mapping to Django QuerySet factories.
  * Filter DSL is JSON-only; operator and field names are validated against
    per-source whitelists before any ORM call.
  * Results are capped at ROW_CAP rows per run (returns ROW_CAP_EXCEEDED error
    before returning partial data — fail-closed).
  * Every query is further filtered by tenant (belt-and-braces on top of
    TenantManager auto-filtering).
"""

from __future__ import annotations

import csv
import hashlib
import io
import logging
from typing import Any

from django.db.models import (
    Avg,
    Count,
    QuerySet,
    Sum,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ROW_CAP = 50_000

# Error code strings
ROW_CAP_EXCEEDED = "ROW_CAP_EXCEEDED"
UNSUPPORTED_OPERATOR = "UNSUPPORTED_OPERATOR"
UNKNOWN_FIELD = "UNKNOWN_FIELD"
UNKNOWN_DATA_SOURCE = "UNKNOWN_DATA_SOURCE"
UNKNOWN_AGGREGATE = "UNKNOWN_AGGREGATE"

# Supported filter operators
SUPPORTED_OPS = frozenset(
    ["eq", "ne", "gt", "gte", "lt", "lte", "in", "contains", "between"]
)

# ---------------------------------------------------------------------------
# Per-source field whitelists
# These control which model fields can be referenced in filters / group-by.
# Do NOT add any field that would expose cross-tenant data.
# ---------------------------------------------------------------------------

SOURCE_FIELD_WHITELISTS: dict[str, set[str]] = {
    "courses": {
        "id",
        "title",
        "is_mandatory",
        "deadline",
        "estimated_hours",
        "created_at",
        "is_deleted",
    },
    "teacher_progress": {
        "id",
        "status",
        "progress_percentage",
        "started_at",
        "completed_at",
        "last_accessed",
        "created_at",
        "course__title",
        "teacher__email",
        "teacher__department",
        "teacher__first_name",
        "teacher__last_name",
    },
    "assignments": {
        "id",
        "title",
        "due_date",
        "created_at",
        "course__title",
        "is_deleted",
    },
    "quiz_attempts": {
        "id",
        "score",
        "started_at",
        "submitted_at",
        "teacher__email",
        "teacher__department",
        "quiz__assignment__title",
    },
    "gamification": {
        "id",
        "total_xp",
        "level",
        "level_name",
        "xp_this_month",
        "xp_this_week",
        "last_xp_at",
        "created_at",
        "teacher__email",
        "teacher__department",
    },
    "certifications": {
        "id",
        "issued_at",
        "expires_at",
        "status",
        "renewal_count",
        "teacher__email",
        "teacher__department",
        "certification_type__name",
        "created_at",
    },
}

# Supported aggregate functions
AGGREGATE_FN_MAP = {
    "count": Count,
    "distinct_count": lambda field: Count(field, distinct=True),
    "sum": Sum,
    "avg": Avg,
}

# ---------------------------------------------------------------------------
# QuerySet factories (one per data source)
# ---------------------------------------------------------------------------


def _qs_courses(tenant):
    from apps.courses.models import Course

    return Course.all_objects.filter(tenant=tenant, is_deleted=False)


def _qs_teacher_progress(tenant):
    from apps.progress.models import TeacherProgress

    return (
        TeacherProgress.all_objects.filter(tenant=tenant)
        .select_related("teacher", "course")
    )


def _qs_assignments(tenant):
    from apps.progress.models import Assignment

    return Assignment.all_objects.filter(tenant=tenant, is_deleted=False)


def _qs_quiz_attempts(tenant):
    from apps.progress.models import QuizSubmission

    return (
        QuizSubmission.all_objects.filter(tenant=tenant)
        .select_related("teacher", "quiz__assignment")
    )


def _qs_gamification(tenant):
    """XP / gamification — uses TeacherXPSummary."""
    try:
        from apps.progress.gamification_models import TeacherXPSummary

        return TeacherXPSummary.all_objects.filter(
            tenant=tenant
        ).select_related("teacher")
    except ImportError:
        # Fallback: return empty queryset-like iterable to avoid crashing
        from apps.progress.models import TeacherProgress

        return TeacherProgress.all_objects.none()


def _qs_certifications(tenant):
    try:
        from apps.progress.certification_models import TeacherCertification

        return (
            TeacherCertification.all_objects.filter(tenant=tenant)
            .select_related("teacher", "certification_type")
        )
    except ImportError:
        from apps.progress.models import TeacherProgress

        return TeacherProgress.all_objects.none()


SOURCE_QS_MAP = {
    "courses": _qs_courses,
    "teacher_progress": _qs_teacher_progress,
    "assignments": _qs_assignments,
    "quiz_attempts": _qs_quiz_attempts,
    "gamification": _qs_gamification,
    "certifications": _qs_certifications,
}

# ---------------------------------------------------------------------------
# Filter application
# ---------------------------------------------------------------------------


def _apply_filter(qs: QuerySet, filt: dict) -> QuerySet:
    """Apply a single validated filter dict to *qs*.

    *filt* must already be validated by the serializer layer — this function
    assumes field and op are whitelisted.

    No string concatenation into SQL; all values are passed as ORM parameters.
    """
    field: str = filt["field"]
    op: str = filt["op"]
    value: Any = filt["value"]

    # Map DSL op → Django ORM lookup
    if op == "eq":
        return qs.filter(**{field: value})
    if op == "ne":
        return qs.exclude(**{field: value})
    if op == "gt":
        return qs.filter(**{f"{field}__gt": value})
    if op == "gte":
        return qs.filter(**{f"{field}__gte": value})
    if op == "lt":
        return qs.filter(**{f"{field}__lt": value})
    if op == "lte":
        return qs.filter(**{f"{field}__lte": value})
    if op == "in":
        if not isinstance(value, (list, tuple)):
            value = [value]
        return qs.filter(**{f"{field}__in": value})
    if op == "contains":
        return qs.filter(**{f"{field}__icontains": value})
    if op == "between":
        # value must be [lower, upper]
        if isinstance(value, (list, tuple)) and len(value) == 2:
            return qs.filter(**{f"{field}__gte": value[0], f"{field}__lte": value[1]})
        return qs
    # Defense-in-depth: if an unrecognized op somehow passes the serializer,
    # raise rather than silently returning an unfiltered queryset.
    raise ValueError(f"{UNSUPPORTED_OPERATOR}: {op!r}")


# ---------------------------------------------------------------------------
# Aggregate application
# ---------------------------------------------------------------------------


def _apply_aggregates(qs: QuerySet, group_by: list[str], aggregates: list[dict]):
    """Apply group-by + aggregates via annotate/values.

    Returns a ValuesQuerySet if group_by is non-empty, else an annotated qs.
    """
    if not group_by and not aggregates:
        return qs

    annotations: dict[str, Any] = {}
    for agg in aggregates:
        fn_name = agg.get("fn", "count").lower()
        agg_field = agg.get("field", "id")
        alias = agg.get("alias", f"{fn_name}_{agg_field}".replace("__", "_"))
        fn = AGGREGATE_FN_MAP.get(fn_name)
        if fn is None:
            continue
        annotations[alias] = fn(agg_field)

    if group_by:
        qs = qs.values(*group_by).annotate(**annotations)
    else:
        qs = qs.annotate(**annotations)

    return qs


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_definition_schema(
    data_source: str,
    filters: list[dict],
    group_by: list[str],
    aggregates: list[dict],
) -> list[str]:
    """Validate a report definition schema without hitting the DB.

    Returns a list of error strings (empty = valid).
    """
    errors: list[str] = []

    if data_source not in SOURCE_QS_MAP:
        errors.append(f"{UNKNOWN_DATA_SOURCE}: {data_source!r}")
        return errors  # Cannot validate fields without knowing source

    whitelist = SOURCE_FIELD_WHITELISTS.get(data_source, set())

    for filt in filters:
        op = filt.get("op", "")
        field = filt.get("field", "")
        if op not in SUPPORTED_OPS:
            errors.append(f"{UNSUPPORTED_OPERATOR}: {op!r}")
        if field not in whitelist:
            errors.append(f"{UNKNOWN_FIELD}: {field!r} not allowed for source {data_source!r}")

    for gb in group_by:
        if gb not in whitelist:
            errors.append(f"{UNKNOWN_FIELD}: group_by field {gb!r} not allowed for source {data_source!r}")

    for agg in aggregates:
        fn_name = agg.get("fn", "")
        agg_field = agg.get("field", "id")
        if fn_name not in AGGREGATE_FN_MAP:
            errors.append(f"{UNKNOWN_AGGREGATE}: {fn_name!r}")
        if agg_field != "id" and agg_field not in whitelist:
            errors.append(f"{UNKNOWN_FIELD}: aggregate field {agg_field!r} not allowed for source {data_source!r}")

    return errors


def run_report(
    tenant,
    data_source: str,
    filters: list[dict],
    group_by: list[str],
    aggregates: list[dict],
) -> tuple[list[dict], int]:
    """Execute a report definition against the DB.

    Returns:
        (rows: list[dict], row_count: int)

    Raises:
        ValueError with error code string as message on constraint violations.
    """
    qs_factory = SOURCE_QS_MAP.get(data_source)
    if qs_factory is None:
        raise ValueError(UNKNOWN_DATA_SOURCE)

    qs: QuerySet = qs_factory(tenant)

    # Apply filters (field + op already validated upstream)
    for filt in filters:
        qs = _apply_filter(qs, filt)

    # Apply group-by + aggregates
    qs = _apply_aggregates(qs, group_by, aggregates)

    # Materialise at most ROW_CAP + 1 rows in one DB round-trip.
    # If we get ROW_CAP + 1 rows the cap is exceeded — fail-closed before
    # returning partial data.  This avoids the double-query cost of an
    # explicit .count() followed by .values().
    if not hasattr(qs, "_fields"):
        raw_rows = list(qs.values()[: ROW_CAP + 1])
    else:
        raw_rows = list(qs[: ROW_CAP + 1])
    if len(raw_rows) > ROW_CAP:
        raise ValueError(ROW_CAP_EXCEEDED)
    rows = raw_rows
    # Normalise UUIDs and datetimes to strings for JSON serialisation
    serialisable_rows = []
    for row in rows:
        if isinstance(row, dict):
            serialisable_rows.append({k: _coerce(v) for k, v in row.items()})
        else:
            # Model instance (no group-by case)
            serialisable_rows.append(_model_to_dict(row))

    return serialisable_rows, len(serialisable_rows)


def _coerce(v: Any) -> Any:
    """Convert non-JSON-serialisable types to strings."""
    import datetime
    import uuid

    if isinstance(v, (uuid.UUID,)):
        return str(v)
    if isinstance(v, (datetime.datetime, datetime.date)):
        return v.isoformat()
    return v


def _model_to_dict(obj: Any) -> dict:
    """Shallow dict of a model instance's concrete fields."""
    from django.db import models as dj_models

    result = {}
    for f in obj._meta.concrete_fields:
        result[f.name] = _coerce(getattr(obj, f.attname, None))
    return result


# ---------------------------------------------------------------------------
# CSV writer
# ---------------------------------------------------------------------------


def rows_to_csv(rows: list[dict]) -> tuple[bytes, str]:
    """Serialise *rows* to UTF-8 CSV bytes.

    Returns:
        (csv_bytes, sha256_hex)
    """
    if not rows:
        return b"", hashlib.sha256(b"").hexdigest()

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    csv_bytes = buf.getvalue().encode("utf-8")
    sha256 = hashlib.sha256(csv_bytes).hexdigest()
    return csv_bytes, sha256
