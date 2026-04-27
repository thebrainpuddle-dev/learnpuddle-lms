"""
apps/reports_builder/views.py
-------------------------------
Custom Report Builder API endpoints (TASK-053).

All views are @admin_only + @tenant_required.

Endpoints:
  GET/POST    /api/v1/admin/reports/definitions/
  GET/PATCH/DELETE /api/v1/admin/reports/definitions/{id}/
  POST        /api/v1/admin/reports/definitions/{id}/run/
  POST        /api/v1/admin/reports/definitions/{id}/export/
  GET         /api/v1/admin/reports/runs/
  GET         /api/v1/admin/reports/runs/{id}/download/
  GET/POST    /api/v1/admin/reports/definitions/{id}/schedules/
  GET/PATCH/DELETE /api/v1/admin/reports/definitions/{id}/schedules/{sid}/

Security:
  * Cross-tenant read/run/export returns 404 (never 403 — do not leak).
  * Rate limit: 20 runs/hr/tenant; fail-closed on cache outage → 503.
  * Every run is audit-logged (action="RUN_REPORT" or "EXPORT_REPORT").
  * Signed-URL download reuses apps/courses/helpers/signed_urls.py.
"""

from __future__ import annotations

import logging
import traceback

from django.core.cache import cache
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from utils.audit import log_audit
from utils.decorators import admin_only, tenant_required

from .models import ReportDefinition, ReportRun, ReportSchedule
from .query_engine import (
    AGGREGATE_FN_MAP,
    ROW_CAP_EXCEEDED,
    SOURCE_FIELD_WHITELISTS,
    SUPPORTED_OPS,
    run_report,
)
from .serializers import (
    ReportDefinitionListSerializer,
    ReportDefinitionSerializer,
    ReportRunSerializer,
    ReportScheduleSerializer,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rate limiting (20 runs/hr/tenant — fail-closed on cache outage)
# Mirror of TASK-047 / TASK-052 pattern.
# ---------------------------------------------------------------------------

RUN_RATE_LIMIT = 20
RUN_RATE_WINDOW = 3600  # 1 hour


def _run_rate_limit_key(tenant_id) -> str:
    return f"report_builder:run_rate:{tenant_id}"


def _check_and_increment_run_rate_limit(tenant_id) -> tuple[bool, str]:
    """Fail-closed rate check.

    Returns:
        (allowed: bool, error_detail: str)
    """
    key = _run_rate_limit_key(tenant_id)
    try:
        current = cache.get(key)
    except Exception:
        logger.exception(
            "Report builder rate-limit cache unavailable (get) tenant=%s", tenant_id
        )
        return False, "service_unavailable"

    if current is None:
        current = 0

    if current >= RUN_RATE_LIMIT:
        return False, "rate_limit_exceeded"

    try:
        cache.set(key, current + 1, timeout=RUN_RATE_WINDOW)
    except Exception:
        logger.exception(
            "Report builder rate-limit cache unavailable (set) tenant=%s", tenant_id
        )
        return False, "service_unavailable"

    return True, ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_definition_or_404(definition_id, tenant):
    """Return ReportDefinition for tenant or 404 (never 403)."""
    try:
        return ReportDefinition.all_objects.get(
            id=definition_id,
            tenant=tenant,
            is_soft_deleted=False,
        )
    except (ReportDefinition.DoesNotExist, ValueError):
        return None


def _get_run_or_404(run_id, tenant):
    """Return ReportRun for tenant or 404 (never 403)."""
    try:
        return ReportRun.all_objects.get(id=run_id, tenant=tenant)
    except (ReportRun.DoesNotExist, ValueError):
        return None


# ---------------------------------------------------------------------------
# Data-source schema (field / operator / aggregate whitelists)
# ---------------------------------------------------------------------------

DATA_SOURCE_LABELS = {
    "courses": "Courses",
    "teacher_progress": "Teacher Progress",
    "assignments": "Assignments",
    "quiz_attempts": "Quiz Attempts",
    "gamification": "XP / Gamification",
    "certifications": "Certifications",
}


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def data_source_schema(request):
    """GET — return the whitelists used by the report builder UI.

    Shape:
        {
          "data_sources": [
            {
              "name": "teacher_progress",
              "label": "Teacher Progress",
              "fields": ["id", "status", ...],
              "operators": ["eq", "ne", ...],
              "aggregates": ["count", "distinct_count", "sum", "avg"]
            },
            ...
          ]
        }
    """
    data_sources = []
    for name, fields in SOURCE_FIELD_WHITELISTS.items():
        data_sources.append(
            {
                "name": name,
                "label": DATA_SOURCE_LABELS.get(name, name),
                "fields": sorted(fields),
                "operators": sorted(SUPPORTED_OPS),
                "aggregates": sorted(AGGREGATE_FN_MAP.keys()),
            }
        )
    data_sources.sort(key=lambda d: d["label"])
    return Response({"data_sources": data_sources})


# ---------------------------------------------------------------------------
# ReportDefinition CRUD
# ---------------------------------------------------------------------------


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def definition_list_create(request):
    """
    GET  — list non-deleted definitions for this tenant.
    POST — create a new definition.
    """
    if request.method == "GET":
        qs = ReportDefinition.all_objects.filter(
            tenant=request.tenant, is_soft_deleted=False
        ).order_by("-created_at")
        serializer = ReportDefinitionListSerializer(qs, many=True)
        return Response(serializer.data)

    # POST
    serializer = ReportDefinitionSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    definition = serializer.save(
        tenant=request.tenant,
        created_by=request.user,
    )
    log_audit(
        action="CREATE",
        target_type="ReportDefinition",
        target_id=str(definition.id),
        target_repr=definition.name,
        request=request,
    )
    return Response(
        ReportDefinitionSerializer(definition).data,
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def definition_detail(request, definition_id):
    """
    GET    — retrieve definition.
    PATCH  — partial update.
    DELETE — soft delete.
    """
    definition = _get_definition_or_404(definition_id, request.tenant)
    if definition is None:
        return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "GET":
        return Response(ReportDefinitionSerializer(definition).data)

    if request.method == "PATCH":
        serializer = ReportDefinitionSerializer(
            definition, data=request.data, partial=True
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        definition = serializer.save()
        log_audit(
            action="UPDATE",
            target_type="ReportDefinition",
            target_id=str(definition.id),
            target_repr=definition.name,
            request=request,
        )
        return Response(ReportDefinitionSerializer(definition).data)

    # DELETE (soft)
    definition.soft_delete()
    log_audit(
        action="DELETE",
        target_type="ReportDefinition",
        target_id=str(definition.id),
        target_repr=definition.name,
        request=request,
    )
    return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Run (synchronous JSON result)
# ---------------------------------------------------------------------------


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def definition_run(request, definition_id):
    """POST — execute definition synchronously; return JSON rows.

    Rate-limited: 20/hr/tenant. Fail-closed on cache outage → 503.
    Audit-logged on success with action="RUN_REPORT".
    """
    definition = _get_definition_or_404(definition_id, request.tenant)
    if definition is None:
        return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    # Rate limit check (fail-closed)
    allowed, reason = _check_and_increment_run_rate_limit(str(request.tenant.id))
    if not allowed:
        if reason == "service_unavailable":
            return Response(
                {"error": "Service temporarily unavailable. Please try again later."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(
            {"error": "Rate limit exceeded. Max 20 report runs per hour per tenant."},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    # Build group_by as list of strings
    group_by_raw = definition.group_by_json or []
    group_by_fields: list[str] = []
    for item in group_by_raw:
        if isinstance(item, str):
            group_by_fields.append(item)
        elif isinstance(item, dict) and "field" in item:
            group_by_fields.append(item["field"])

    # Create run record
    run = ReportRun.all_objects.create(
        tenant=request.tenant,
        definition=definition,
        run_by=request.user,
        params_snapshot_json={
            "data_source": definition.data_source,
            "filters": definition.filters_json,
            "group_by": group_by_fields,
            "aggregates": definition.aggregates_json,
        },
        status="running",
        started_at=timezone.now(),
    )

    try:
        rows, row_count = run_report(
            tenant=request.tenant,
            data_source=definition.data_source,
            filters=definition.filters_json or [],
            group_by=group_by_fields,
            aggregates=definition.aggregates_json or [],
        )
    except ValueError as exc:
        error_code = str(exc)
        run.status = "error"
        run.error = error_code
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "error", "finished_at"])

        if error_code == ROW_CAP_EXCEEDED:
            return Response(
                {"error": ROW_CAP_EXCEEDED, "detail": "Result exceeds 50,000 row cap."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {"error": error_code},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except Exception:
        tb = traceback.format_exc()
        run.status = "error"
        run.error = tb
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "error", "finished_at"])
        logger.exception("Unexpected error executing report run=%s", run.id)
        return Response(
            {"error": "Internal server error during report execution."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    run.status = "success"
    run.row_count = row_count
    run.finished_at = timezone.now()
    run.save(update_fields=["status", "row_count", "finished_at"])

    # Audit log
    log_audit(
        action="RUN_REPORT",
        target_type="ReportRun",
        target_id=str(run.id),
        target_repr=definition.name,
        changes={"row_count": row_count},
        request=request,
    )

    return Response(
        {
            "run_id": str(run.id),
            "row_count": row_count,
            "rows": rows,
        }
    )


# ---------------------------------------------------------------------------
# Export (async CSV build → signed-URL download)
# ---------------------------------------------------------------------------


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def definition_export(request, definition_id):
    """POST — enqueue CSV build task; return {run_id}.

    Rate-limited (shared with run). Audit-logged as "EXPORT_REPORT".
    """
    definition = _get_definition_or_404(definition_id, request.tenant)
    if definition is None:
        return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    # Rate limit check (fail-closed)
    allowed, reason = _check_and_increment_run_rate_limit(str(request.tenant.id))
    if not allowed:
        if reason == "service_unavailable":
            return Response(
                {"error": "Service temporarily unavailable. Please try again later."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(
            {"error": "Rate limit exceeded. Max 20 report runs per hour per tenant."},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    run = ReportRun.all_objects.create(
        tenant=request.tenant,
        definition=definition,
        run_by=request.user,
        params_snapshot_json={
            "data_source": definition.data_source,
            "filters": definition.filters_json,
            "group_by": definition.group_by_json,
            "aggregates": definition.aggregates_json,
            "export": True,
        },
        status="pending",
        started_at=timezone.now(),
    )

    # Enqueue CSV build task
    from .tasks import build_csv_export

    build_csv_export.delay(str(run.id))

    log_audit(
        action="EXPORT_REPORT",
        target_type="ReportRun",
        target_id=str(run.id),
        target_repr=definition.name,
        request=request,
    )

    return Response({"run_id": str(run.id)}, status=status.HTTP_202_ACCEPTED)


# ---------------------------------------------------------------------------
# Run history + signed-URL download
# ---------------------------------------------------------------------------


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def run_list(request):
    """GET — list run history for tenant (optionally filter by definition_id)."""
    qs = ReportRun.all_objects.filter(tenant=request.tenant).order_by("-started_at")
    definition_id = request.query_params.get("definition_id")
    if definition_id:
        qs = qs.filter(definition_id=definition_id)
    serializer = ReportRunSerializer(qs[:200], many=True)
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def run_download(request, run_id):
    """GET — return a signed URL to download the CSV artifact.

    Reuses apps/courses/helpers/signed_urls.py (TASK-052 helper).
    Token is user-bound. TTL max 24h.
    """
    run = _get_run_or_404(run_id, request.tenant)
    if run is None:
        return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    if run.status != "success" or not run.artifact_path:
        return Response(
            {"error": "Export artifact not ready yet."},
            status=status.HTTP_404_NOT_FOUND,
        )

    from apps.courses.helpers.signed_urls import make_signed_url

    # Build the base download URL — the download_redirect view validates the token.
    base_url = request.build_absolute_uri(
        f"/api/v1/admin/reports/runs/{run_id}/artifact/"
    )
    signed = make_signed_url(
        base_url=base_url,
        user_id=str(request.user.id),
        ttl_seconds=3600,  # 1 hour; max allowed is 86400
        extra_params={"run": str(run_id)},
    )

    return Response({"download_url": signed, "expires_in": 3600})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def run_artifact(request, run_id):
    """GET — serve the CSV artifact after verifying the signed URL.

    Called by the frontend after obtaining the signed URL from run_download.
    """
    from apps.courses.helpers.signed_urls import verify_signed_url
    from django.http import HttpResponse

    run = _get_run_or_404(run_id, request.tenant)
    if run is None:
        return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    # Verify signed URL params
    token = request.query_params.get("lp_token", "")
    expires_str = request.query_params.get("lp_expires", "0")
    try:
        expires_ts = int(expires_str)
    except ValueError:
        return Response({"error": "Invalid signed URL."}, status=status.HTTP_403_FORBIDDEN)

    base_url = request.build_absolute_uri(
        f"/api/v1/admin/reports/runs/{run_id}/artifact/"
    )
    valid = verify_signed_url(
        base_url=base_url,
        user_id=str(request.user.id),
        token=token,
        expires_ts=expires_ts,
        extra_params={"run": str(run_id)},
    )
    if not valid:
        return Response(
            {"error": "Invalid or expired signed URL."},
            status=status.HTTP_403_FORBIDDEN,
        )

    # Serve the CSV
    if not run.artifact_path:
        return Response(
            {"error": "Artifact not available."}, status=status.HTTP_404_NOT_FOUND
        )

    try:
        with open(run.artifact_path, "rb") as f:
            csv_bytes = f.read()
    except OSError:
        return Response(
            {"error": "Artifact file missing."},
            status=status.HTTP_404_NOT_FOUND,
        )

    response = HttpResponse(csv_bytes, content_type="text/csv")
    response["Content-Disposition"] = (
        f'attachment; filename="report_{run_id}.csv"'
    )
    return response


# ---------------------------------------------------------------------------
# Schedule CRUD
# ---------------------------------------------------------------------------


@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def schedule_list_create(request, definition_id):
    """
    GET  — list schedules for a definition.
    POST — create a new schedule.
    """
    definition = _get_definition_or_404(definition_id, request.tenant)
    if definition is None:
        return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "GET":
        qs = ReportSchedule.all_objects.filter(
            definition=definition, tenant=request.tenant
        ).order_by("-created_at")
        serializer = ReportScheduleSerializer(qs, many=True)
        return Response(serializer.data)

    # POST
    serializer = ReportScheduleSerializer(
        data=request.data, context={"request": request}
    )
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    schedule = serializer.save(
        definition=definition,
        tenant=request.tenant,
    )
    log_audit(
        action="CREATE",
        target_type="ReportSchedule",
        target_id=str(schedule.id),
        target_repr=str(schedule),
        request=request,
    )
    return Response(
        ReportScheduleSerializer(schedule).data, status=status.HTTP_201_CREATED
    )


@api_view(["GET", "PATCH", "DELETE"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def schedule_detail(request, definition_id, schedule_id):
    """GET / PATCH / DELETE a single schedule."""
    definition = _get_definition_or_404(definition_id, request.tenant)
    if definition is None:
        return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    try:
        schedule = ReportSchedule.all_objects.get(
            id=schedule_id,
            definition=definition,
            tenant=request.tenant,
        )
    except (ReportSchedule.DoesNotExist, ValueError):
        return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "GET":
        return Response(ReportScheduleSerializer(schedule).data)

    if request.method == "PATCH":
        serializer = ReportScheduleSerializer(
            schedule, data=request.data, partial=True, context={"request": request}
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        schedule = serializer.save()
        log_audit(
            action="UPDATE",
            target_type="ReportSchedule",
            target_id=str(schedule.id),
            target_repr=str(schedule),
            request=request,
        )
        return Response(ReportScheduleSerializer(schedule).data)

    # DELETE
    schedule.delete()
    log_audit(
        action="DELETE",
        target_type="ReportSchedule",
        target_id=str(schedule_id),
        request=request,
    )
    return Response(status=status.HTTP_204_NO_CONTENT)
