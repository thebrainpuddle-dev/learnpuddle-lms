"""Views for TASK-060 — AI Course Generator.

Endpoints (all @admin_only + @tenant_required):
  POST   /api/v1/admin/course-generator/              — enqueue job
  GET    /api/v1/admin/course-generator/jobs/         — list jobs
  GET    /api/v1/admin/course-generator/jobs/{id}/    — poll status
  POST   /api/v1/admin/course-generator/jobs/{id}/materialise/ — create draft
  DELETE /api/v1/admin/course-generator/jobs/{id}/    — purge job

Security:
  - Rate limit: 5 POST /hour/tenant — fail-CLOSED on cache outage (503).
  - File upload cap: 20 MB → 413.
  - URL allowlist: only YouTube/Vimeo hostnames → 400.
  - SSRF defence via strict hostname allowlist.
"""

from __future__ import annotations

import base64
import json
import logging
import time
from urllib.parse import urlparse

from django.core.cache import cache
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from utils.audit import log_audit
from utils.decorators import admin_only, tenant_required

from .models import CourseGenerationJob
from .serializers import (
    CourseGenerationJobListSerializer,
    CourseGenerationJobSerializer,
    MaterialiseResponseSerializer,
)

logger = logging.getLogger(__name__)

# ── constants ────────────────────────────────────────────────────────────────

MAX_FILE_BYTES = 20 * 1024 * 1024  # 20 MB
RATE_LIMIT_WINDOW = 3600  # 1 hour in seconds
RATE_LIMIT_MAX = 5  # max submissions per tenant per window

# Allowlisted hostnames for URL-based sources (SSRF defence)
YOUTUBE_HOSTS = frozenset({"youtube.com", "www.youtube.com", "youtu.be"})
VIMEO_HOSTS = frozenset({"vimeo.com"})
ALLOWED_URL_HOSTS = YOUTUBE_HOSTS | VIMEO_HOSTS

# Valid source types
FILE_SOURCE_TYPES = {"pdf", "docx", "text"}
URL_SOURCE_TYPES = {"youtube", "vimeo"}
ALL_SOURCE_TYPES = FILE_SOURCE_TYPES | URL_SOURCE_TYPES


def _request_data(request):
    """Return parsed request data for both DRF Request and raw WSGIRequest tests."""
    data = getattr(request, "data", None)
    if data is not None:
        return data
    if getattr(request, "content_type", "") == "application/json":
        try:
            return json.loads(request.body.decode("utf-8") or "{}")
        except (TypeError, ValueError, UnicodeDecodeError):
            return {}
    return request.POST


def _request_files(request):
    files = getattr(request, "FILES", None)
    return files if files is not None else {}


def _request_query_params(request):
    return getattr(request, "query_params", request.GET)


# ── rate limiter (fail-CLOSED) ────────────────────────────────────────────────

def _rate_limit_key(tenant_id: str) -> str:
    return f"course_gen_rl:{tenant_id}:{int(time.time()) // RATE_LIMIT_WINDOW}"


def _check_and_increment_rate_limit(tenant_id: str) -> Response | None:
    """Check the rate limit for a tenant.

    Returns:
        None if request should proceed.
        Response(503) if cache is unavailable (fail-CLOSED).
        Response(429) if rate limit is exceeded.
    """
    key = _rate_limit_key(tenant_id)

    # Fail-CLOSED on cache.get failure
    try:
        count = cache.get(key)
    except Exception as exc:
        logger.error("Cache unavailable (get) in rate limiter: %s", exc)
        return Response(
            {"error": "SERVICE_UNAVAILABLE", "detail": "Rate limiting service unavailable."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    if count is None:
        count = 0

    if count >= RATE_LIMIT_MAX:
        return Response(
            {
                "error": "RATE_LIMIT_EXCEEDED",
                "detail": f"Maximum {RATE_LIMIT_MAX} course generation requests per hour.",
            },
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    # Increment — fail-CLOSED on cache.set failure
    try:
        if count == 0:
            cache.set(key, 1, RATE_LIMIT_WINDOW)
        else:
            cache.incr(key)
    except Exception as exc:
        logger.error("Cache unavailable (set/incr) in rate limiter: %s", exc)
        return Response(
            {"error": "SERVICE_UNAVAILABLE", "detail": "Rate limiting service unavailable."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return None


# ── URL validation ────────────────────────────────────────────────────────────

def _validate_url_host(url: str, source_type: str) -> str | None:
    """Return error code string if URL is not on the allowlist, else None."""
    try:
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()
    except Exception:
        return "INVALID_URL"

    if source_type == "youtube" and hostname not in YOUTUBE_HOSTS:
        return "INVALID_URL_HOST"
    if source_type == "vimeo" and hostname not in VIMEO_HOSTS:
        return "INVALID_URL_HOST"
    if source_type in URL_SOURCE_TYPES and hostname not in ALLOWED_URL_HOSTS:
        return "INVALID_URL_HOST"
    return None


# ── views ─────────────────────────────────────────────────────────────────────


def create_generation_job(request):
    """POST /api/v1/admin/course-generator/

    Multipart form data:
      - source_type: "pdf"|"docx"|"text"|"youtube"|"vimeo"
      - file: binary file (when source_type is file-based)
      - url: string (when source_type is url-based)
      - title_hint: optional string
      - target_module_count: optional int (default 5, max 12)
    """
    tenant = request.tenant

    # ── rate limit ────────────────────────────────────────────────────────────
    rl_response = _check_and_increment_rate_limit(str(tenant.id))
    if rl_response is not None:
        return rl_response

    data = _request_data(request)

    # ── validate source_type ──────────────────────────────────────────────────
    source_type = (data.get("source_type") or "").strip().lower()
    if source_type not in ALL_SOURCE_TYPES:
        return Response(
            {
                "error": "INVALID_SOURCE_TYPE",
                "detail": f"source_type must be one of: {sorted(ALL_SOURCE_TYPES)}",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ── parse options ─────────────────────────────────────────────────────────
    title_hint = (data.get("title_hint") or "").strip() or None
    try:
        target_module_count = int(data.get("target_module_count") or 5)
        target_module_count = max(3, min(12, target_module_count))
    except (TypeError, ValueError):
        target_module_count = 5

    source_metadata: dict = {
        "title_hint": title_hint,
        "target_module_count": target_module_count,
    }
    file_b64: str | None = None

    if source_type in FILE_SOURCE_TYPES:
        # ── file upload ───────────────────────────────────────────────────────
        uploaded_file = _request_files(request).get("file")
        if not uploaded_file:
            return Response(
                {"error": "FILE_REQUIRED", "detail": "A file must be uploaded for this source_type."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if uploaded_file.size > MAX_FILE_BYTES:
            return Response(
                {
                    "error": "FILE_TOO_LARGE",
                    "detail": f"File exceeds the {MAX_FILE_BYTES // (1024 * 1024)} MB limit.",
                },
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )

        # Encode file content for the Celery task
        raw_bytes = uploaded_file.read()
        file_b64 = base64.b64encode(raw_bytes).decode("ascii")
        source_metadata["filename"] = uploaded_file.name
        source_metadata["file_size"] = uploaded_file.size
        source_metadata["_file_b64"] = file_b64

    else:
        # ── URL source ────────────────────────────────────────────────────────
        url = (data.get("url") or "").strip()
        if not url:
            return Response(
                {"error": "URL_REQUIRED", "detail": "A url must be provided for this source_type."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        url_error = _validate_url_host(url, source_type)
        if url_error:
            return Response(
                {
                    "error": url_error,
                    "detail": (
                        "URL hostname is not on the allowlist. "
                        "Allowed: youtube.com, www.youtube.com, youtu.be, vimeo.com"
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        source_metadata["url"] = url

    # ── create job ────────────────────────────────────────────────────────────
    job = CourseGenerationJob.objects.create(
        tenant=tenant,
        created_by=request.user,
        source_type=source_type,
        source_metadata=source_metadata,
        status=CourseGenerationJob.STATUS_PENDING,
    )

    # ── enqueue Celery task ───────────────────────────────────────────────────
    from .tasks import generate_course_from_source

    generate_course_from_source.delay(str(job.id))

    return Response(
        {
            "job_id": str(job.id),
            "status": job.status,
        },
        status=status.HTTP_202_ACCEPTED,
    )


def list_generation_jobs(request):
    """GET /api/v1/admin/course-generator/jobs/

    Query params:
      - status: filter by job status
      - created_by: filter by user id
    """
    tenant = request.tenant
    qs = CourseGenerationJob.objects.filter(tenant=tenant).order_by("-created_at")

    # Filter by status
    query_params = _request_query_params(request)

    status_filter = query_params.get("status")
    if status_filter:
        qs = qs.filter(status=status_filter)

    # Filter by creator
    created_by_filter = query_params.get("created_by")
    if created_by_filter:
        qs = qs.filter(created_by_id=created_by_filter)

    serializer = CourseGenerationJobListSerializer(qs, many=True)
    return Response(serializer.data)


def get_generation_job(request, job_id: str):
    """GET or DELETE /api/v1/admin/course-generator/jobs/{job_id}/

    GET  — poll job status.
    DELETE — purge the job record; delegates to delete_generation_job logic.
    """
    if request.method == "DELETE":
        # Re-use the delete view's logic by calling it directly as a plain
        # function (bypassing its own @api_view wrapper).
        return _purge_job(request, job_id)
    tenant = request.tenant

    try:
        job = CourseGenerationJob.objects.get(id=job_id, tenant=tenant)
    except CourseGenerationJob.DoesNotExist:
        return Response(
            {"error": "NOT_FOUND", "detail": "Job not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    serializer = CourseGenerationJobSerializer(job)
    return Response(serializer.data)


def materialise_job(request, job_id: str):
    """POST /api/v1/admin/course-generator/jobs/{job_id}/materialise/

    Explicit consent step: admin has reviewed the outline and wants to
    create the draft Course.  Idempotent — second call returns existing
    draft_course_id.

    Optional body:
      - outline_override: JSON object matching CourseBlueprint schema.
        Frontend can send a client-edited outline here.
    """
    tenant = request.tenant

    try:
        job = CourseGenerationJob.objects.get(id=job_id, tenant=tenant)
    except CourseGenerationJob.DoesNotExist:
        return Response(
            {"error": "NOT_FOUND", "detail": "Job not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Idempotency: if already materialised, return existing course
    if job.draft_course_id:
        return Response(
            {"draft_course_id": str(job.draft_course_id), "idempotent": True},
            status=status.HTTP_200_OK,
        )

    if job.status != CourseGenerationJob.STATUS_SUCCEEDED:
        return Response(
            {
                "error": "JOB_NOT_READY",
                "detail": (
                    f"Job is in status '{job.status}'. "
                    "Wait for status='succeeded' before materialising."
                ),
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not job.outline_json:
        return Response(
            {"error": "NO_OUTLINE", "detail": "Job has no outline to materialise."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ── resolve outline (override or stored) ─────────────────────────────────
    outline_override = _request_data(request).get("outline_override")
    outline_data = outline_override if outline_override else job.outline_json

    try:
        blueprint = _outline_dict_to_blueprint(outline_data, job)
    except (ValueError, KeyError, TypeError) as exc:
        return Response(
            {"error": "INVALID_OUTLINE", "detail": str(exc)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ── materialise ───────────────────────────────────────────────────────────
    from .materialiser import materialise_course

    job.set_status(CourseGenerationJob.STATUS_MATERIALISING)
    try:
        course = materialise_course(
            blueprint=blueprint,
            tenant=tenant,
            created_by=request.user,
        )
    except Exception as exc:
        logger.exception("Materialise failed for job %s", job.id)
        job.set_status(CourseGenerationJob.STATUS_FAILED, error=str(exc))
        log_audit(
            action="COURSE_GENERATION_FAILED",
            target_type="CourseGenerationJob",
            target_id=str(job.id),
            target_repr=str(job),
            changes={"error": str(exc), "step": "materialise"},
            request=request,
        )
        return Response(
            {"error": "MATERIALISE_FAILED", "detail": str(exc)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    # ── update job ────────────────────────────────────────────────────────────
    job.draft_course = course
    job.set_status(CourseGenerationJob.STATUS_SUCCEEDED)
    job.save(update_fields=["draft_course", "updated_at"])

    log_audit(
        action="COURSE_MATERIALISED",
        target_type="CourseGenerationJob",
        target_id=str(job.id),
        target_repr=str(job),
        changes={"draft_course_id": str(course.id), "course_title": course.title},
        request=request,
    )

    return Response(
        {"draft_course_id": str(course.id), "idempotent": False},
        status=status.HTTP_201_CREATED,
    )


def _purge_job(request, job_id: str) -> Response:
    """Inner logic for purging a generation job (shared by two URL routes).

    Purges the job record and erases extracted_text_truncated (compliance).
    If the job has a materialised draft course, the Course is NOT deleted —
    admin must soft-delete it separately.
    """
    tenant = request.tenant

    try:
        job = CourseGenerationJob.objects.get(id=job_id, tenant=tenant)
    except CourseGenerationJob.DoesNotExist:
        return Response(
            {"error": "NOT_FOUND", "detail": "Job not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    draft_course_id = str(job.draft_course_id) if job.draft_course_id else None

    log_audit(
        action="COURSE_GENERATION_PURGED",
        target_type="CourseGenerationJob",
        target_id=str(job.id),
        target_repr=str(job),
        changes={
            "draft_course_id": draft_course_id,
            "note": "extracted_text_truncated purged; draft Course NOT deleted",
        },
        request=request,
    )

    # Purge extracted text before deleting the row
    job.extracted_text_truncated = ""
    job.save(update_fields=["extracted_text_truncated", "updated_at"])

    # Hard-delete the job row
    job.delete()

    return Response(status=status.HTTP_204_NO_CONTENT)


def delete_generation_job(request, job_id: str):
    """DELETE /api/v1/admin/course-generator/jobs/{job_id}/delete/  (legacy URL)

    Kept for backward compatibility with the original /delete/ suffix.
    New callers should use DELETE /jobs/{job_id}/ instead.
    """
    return _purge_job(request, job_id)


create_generation_job_api_view = api_view(["POST"])(
    permission_classes([IsAuthenticated])(
        admin_only(tenant_required(create_generation_job))
    )
)
list_generation_jobs_api_view = api_view(["GET"])(
    permission_classes([IsAuthenticated])(
        admin_only(tenant_required(list_generation_jobs))
    )
)
get_generation_job_api_view = api_view(["GET", "DELETE"])(
    permission_classes([IsAuthenticated])(
        admin_only(tenant_required(get_generation_job))
    )
)
materialise_job_api_view = api_view(["POST"])(
    permission_classes([IsAuthenticated])(
        admin_only(tenant_required(materialise_job))
    )
)
delete_generation_job_api_view = api_view(["DELETE"])(
    permission_classes([IsAuthenticated])(
        admin_only(tenant_required(delete_generation_job))
    )
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _outline_dict_to_blueprint(outline_data: dict, job: CourseGenerationJob):
    """Convert a raw outline dict to a CourseBlueprint.

    Re-uses the validation logic from outline_service.
    """
    from .outline_service import _validate_and_parse

    target_module_count = int(
        (job.source_metadata or {}).get("target_module_count", 12)
    )
    return _validate_and_parse(outline_data, target_module_count)
