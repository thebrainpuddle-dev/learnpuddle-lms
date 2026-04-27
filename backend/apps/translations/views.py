"""Admin + teacher HTTP views for TASK-058 — Auto-Translation Service.

Admin endpoints (``@admin_only + @tenant_required``)
----------------------------------------------------
  POST   /api/v1/admin/translations/courses/{course_id}/
  POST   /api/v1/admin/translations/content/{content_id}/
  GET    /api/v1/admin/translations/jobs/{job_id}/
  GET    /api/v1/admin/translations/content/{content_id}/?lang=xx
  DELETE /api/v1/admin/translations/content/{content_id}/?lang=xx

  -- TASK-064b per-field review endpoints --
  PUT    /api/v1/admin/translations/content/{content_id}/fields/{field}/approve/?lang=xx
  PUT    /api/v1/admin/translations/content/{content_id}/fields/{field}/reject/?lang=xx
  PUT    /api/v1/admin/translations/content/{content_id}/fields/{field}/edit/?lang=xx
  POST   /api/v1/admin/translations/content/{content_id}/publish/?lang=xx

Teacher endpoint (``@tenant_required`` + enrollment check)
----------------------------------------------------------
  GET    /api/teacher/content/{content_id}/translation/?lang=xx

  NOTE (TASK-064b): teacher reads are now filtered to ``published_at IS NOT
  NULL``.  Prior to this change teachers saw all translated rows including
  pending and rejected translations — a latent product concern fixed here.
"""

from __future__ import annotations

import logging
import uuid

from django.core.cache import cache
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from apps.courses.models import Content, Course
from apps.progress.models import TeacherProgress
from utils.audit import log_audit
from utils.decorators import admin_only, tenant_required

from .models import (
    ContentTranslation,
    FIELD_TITLE,
    FIELD_DESCRIPTION,
    FIELD_BODY,
    FIELD_TRANSCRIPT,
    REVIEW_STATUS_APPROVED,
    REVIEW_STATUS_REJECTED,
    SOURCE_TYPE_CONTENT,
    TranslationJobRun,
)
from .serializers import (
    ContentTranslationReviewSerializer,
    FieldEditSerializer,
    TranslationJobRunSerializer,
)
from .services import (
    COURSE_TOKEN_ESTIMATE_CAP,
    estimate_course_token_count,
    extract_content_fields,
    oversize_fields,
    validate_target_languages,
)
from .tasks import translate_content as translate_content_task
from .tasks import translate_course as translate_course_task

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Rate-limit helpers (fail-closed on cache outage → 503)
# ---------------------------------------------------------------------------


COURSE_RATE_LIMIT = 10
CONTENT_RATE_LIMIT = 60
# TASK-064b: review actions are cheap writes but still rate-limited.
REVIEW_RATE_LIMIT = 300   # approve / reject / edit per tenant per hour
PUBLISH_RATE_LIMIT = 20   # publish runs per tenant per hour
RATE_WINDOW = 3600

# Valid translatable field names — used to validate URL path param.
_VALID_FIELDS = {
    FIELD_TITLE,
    FIELD_DESCRIPTION,
    FIELD_BODY,
    FIELD_TRANSCRIPT,
}


def _rate_key(scope: str, tenant_id) -> str:
    return f"translations:{scope}:{tenant_id}"


def _check_rate_limit(scope: str, tenant_id, limit: int):
    """Return ``(allowed: bool, reason: str)``.

    Wraps BOTH ``cache.get`` AND ``cache.set`` in try/except — on any
    Redis / cache-backend failure we fail closed and return 503.
    """
    key = _rate_key(scope, tenant_id)
    try:
        current = cache.get(key)
    except Exception:
        logger.exception(
            "translation rate-limit cache.get failed scope=%s tenant=%s", scope, tenant_id
        )
        return False, "service_unavailable"

    if current is None:
        current = 0
    if current >= limit:
        return False, "rate_limit_exceeded"

    try:
        cache.set(key, current + 1, timeout=RATE_WINDOW)
    except Exception:
        logger.exception(
            "translation rate-limit cache.set failed scope=%s tenant=%s", scope, tenant_id
        )
        return False, "service_unavailable"

    return True, ""


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _coerce_languages(raw):
    """Normalise target_languages payload into a list of strings."""
    if isinstance(raw, str):
        return [part.strip() for part in raw.split(",") if part.strip()]
    if isinstance(raw, (list, tuple)):
        return [str(x).strip() for x in raw if str(x).strip()]
    return []


def _content_for_tenant(content_id, tenant) -> Content | None:
    """Return a Content belonging to ``tenant`` or ``None``."""
    try:
        content = Content.all_objects.select_related("module__course").get(
            id=content_id
        )
    except (Content.DoesNotExist, ValueError):
        return None
    if content.module.course.tenant_id != tenant.id:
        return None
    return content


def _course_for_tenant(course_id, tenant) -> Course | None:
    try:
        course = Course.all_objects.get(id=course_id)
    except (Course.DoesNotExist, ValueError):
        return None
    if course.tenant_id != tenant.id:
        return None
    return course


# ---------------------------------------------------------------------------
# Admin: POST /admin/translations/courses/{id}/
# ---------------------------------------------------------------------------


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def translate_course_view(request, course_id):
    tenant = request.tenant

    # --- Rate limit (fail-closed) ---
    allowed, reason = _check_rate_limit("course", str(tenant.id), COURSE_RATE_LIMIT)
    if not allowed:
        if reason == "service_unavailable":
            return Response(
                {"error": "service_unavailable", "detail": "Translation rate-limit service is unavailable."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(
            {"error": "rate_limit_exceeded", "detail": "Too many translation runs; try again later."},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    course = _course_for_tenant(course_id, tenant)
    if course is None:
        return Response({"error": "not_found"}, status=status.HTTP_404_NOT_FOUND)

    langs_raw = _coerce_languages(request.data.get("target_languages"))
    if not langs_raw:
        return Response(
            {"error": "target_languages_required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    valid, rejected = validate_target_languages(langs_raw)
    if rejected or not valid:
        return Response(
            {
                "error": "UNSUPPORTED_LANGUAGE",
                "rejected": rejected,
                "valid": valid,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Cost guard
    token_estimate = estimate_course_token_count(course)
    if token_estimate > COURSE_TOKEN_ESTIMATE_CAP:
        return Response(
            {
                "error": "COST_LIMIT_EXCEEDED",
                "detail": "Course is too large; split into smaller translation runs.",
                "token_estimate": token_estimate,
                "cap": COURSE_TOKEN_ESTIMATE_CAP,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    job = TranslationJobRun.objects.all_tenants().create(
        tenant=tenant,
        kind=TranslationJobRun.KIND_COURSE,
        target_id=course.id,
        target_languages=valid,
        created_by=request.user if request.user.is_authenticated else None,
        status=TranslationJobRun.STATUS_PENDING,
    )

    translate_course_task.delay(str(course.id), valid, str(job.id))

    return Response(
        {
            "job_id": str(job.id),
            "status": job.status,
            "target_languages": valid,
        },
        status=status.HTTP_202_ACCEPTED,
    )


# ---------------------------------------------------------------------------
# Admin: POST /admin/translations/content/{id}/
# ---------------------------------------------------------------------------


@api_view(["POST", "GET", "DELETE"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def translations_content_view(request, content_id):
    tenant = request.tenant

    # For POST — rate limit fail-closed BEFORE lookup to avoid leaking existence.
    if request.method == "POST":
        allowed, reason = _check_rate_limit(
            "content", str(tenant.id), CONTENT_RATE_LIMIT
        )
        if not allowed:
            if reason == "service_unavailable":
                return Response(
                    {"error": "service_unavailable"},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            return Response(
                {"error": "rate_limit_exceeded"},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

    content = _content_for_tenant(content_id, tenant)
    if content is None:
        return Response({"error": "not_found"}, status=status.HTTP_404_NOT_FOUND)

    if request.method == "POST":
        return _admin_enqueue_content_translation(request, tenant, content)

    if request.method == "GET":
        return _admin_get_content_translation(request, tenant, content)

    # DELETE
    return _admin_delete_content_translation(request, tenant, content)


def _admin_enqueue_content_translation(request, tenant, content):
    langs_raw = _coerce_languages(request.data.get("target_languages"))
    if not langs_raw:
        return Response(
            {"error": "target_languages_required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    valid, rejected = validate_target_languages(langs_raw)
    if rejected or not valid:
        return Response(
            {"error": "UNSUPPORTED_LANGUAGE", "rejected": rejected, "valid": valid},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Size cap — per translatable field <= 50 KB
    pairs = extract_content_fields(content)
    over = oversize_fields(pairs)
    if over:
        return Response(
            {
                "error": "FIELD_TOO_LARGE",
                "detail": "One or more translatable fields exceed the 50 KB cap.",
                "fields": over,
            },
            status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )

    job = TranslationJobRun.objects.all_tenants().create(
        tenant=tenant,
        kind=TranslationJobRun.KIND_CONTENT,
        target_id=content.id,
        target_languages=valid,
        created_by=request.user if request.user.is_authenticated else None,
        status=TranslationJobRun.STATUS_PENDING,
    )

    translate_content_task.delay(str(content.id), valid, str(job.id))

    return Response(
        {
            "job_id": str(job.id),
            "status": job.status,
            "target_languages": valid,
        },
        status=status.HTTP_202_ACCEPTED,
    )


def _admin_get_content_translation(request, tenant, content):
    lang = (request.GET.get("lang") or "").strip()
    if not lang:
        return Response(
            {"error": "lang_required"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    valid, rejected = validate_target_languages([lang])
    if rejected or not valid:
        return Response(
            {"error": "UNSUPPORTED_LANGUAGE", "rejected": rejected},
            status=status.HTTP_400_BAD_REQUEST,
        )

    qs = ContentTranslation.objects.all_tenants().filter(
        tenant=tenant,
        source_type=SOURCE_TYPE_CONTENT,
        source_id=content.id,
        target_language=lang,
    )
    if not qs.exists():
        return Response(
            {"error": "TRANSLATION_NOT_AVAILABLE"},
            status=status.HTTP_404_NOT_FOUND,
        )

    return Response(
        {
            "content_id": str(content.id),
            "lang": lang,
            "rows": ContentTranslationReviewSerializer(qs, many=True).data,
        }
    )


def _admin_delete_content_translation(request, tenant, content):
    lang = (request.GET.get("lang") or "").strip()
    if not lang:
        return Response(
            {"error": "lang_required"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    valid, rejected = validate_target_languages([lang])
    if rejected or not valid:
        return Response(
            {"error": "UNSUPPORTED_LANGUAGE", "rejected": rejected},
            status=status.HTTP_400_BAD_REQUEST,
        )

    qs = ContentTranslation.objects.all_tenants().filter(
        tenant=tenant,
        source_type=SOURCE_TYPE_CONTENT,
        source_id=content.id,
        target_language=lang,
    )
    removed = qs.count()
    qs.delete()

    log_audit(
        request=request,
        action="TRANSLATION_PURGED",
        target_type="Content",
        target_id=str(content.id),
        target_repr=str(content),
        changes={"lang": lang, "rows_removed": removed},
    )

    return Response(
        {"lang": lang, "rows_removed": removed},
        status=status.HTTP_200_OK,
    )


# ---------------------------------------------------------------------------
# Admin: GET /admin/translations/jobs/{job_id}/
# ---------------------------------------------------------------------------


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def translation_job_detail(request, job_id):
    tenant = request.tenant
    try:
        job = TranslationJobRun.objects.all_tenants().get(id=job_id, tenant=tenant)
    except (TranslationJobRun.DoesNotExist, ValueError):
        return Response({"error": "not_found"}, status=status.HTTP_404_NOT_FOUND)
    return Response(TranslationJobRunSerializer(job).data)


# ---------------------------------------------------------------------------
# TASK-064b helpers
# ---------------------------------------------------------------------------


def _get_review_row(content, tenant, field, lang):
    """Return (row | None, error_response | None).

    Returns 404 if the (content, field, lang) translation does not exist or
    belongs to a different tenant.  Cross-tenant is automatically prevented
    because ``content`` is already validated against ``tenant`` by
    ``_content_for_tenant`` before callers reach here.
    """
    try:
        row = ContentTranslation.objects.all_tenants().get(
            tenant=tenant,
            source_type=SOURCE_TYPE_CONTENT,
            source_id=content.id,
            field=field,
            target_language=lang,
        )
        return row, None
    except ContentTranslation.DoesNotExist:
        return None, Response(
            {"error": "TRANSLATION_NOT_AVAILABLE"},
            status=status.HTTP_404_NOT_FOUND,
        )


def _parse_review_params(request, field: str):
    """Return (field, lang, error_response | None).

    Validates the ``field`` URL path parameter against ``_VALID_FIELDS`` and
    the ``lang`` query-string parameter against the language allowlist.

    ``field`` is already extracted from the URL route and passed directly.
    ``lang``  is expected in ``request.GET["lang"]``.
    """
    field = (field or "").strip()
    if field not in _VALID_FIELDS:
        return None, None, Response(
            {
                "error": "invalid_field",
                "detail": f"field must be one of: {', '.join(sorted(_VALID_FIELDS))}",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    lang = (request.GET.get("lang") or "").strip()
    if not lang:
        return None, None, Response(
            {"error": "lang_required"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    valid, rejected = validate_target_languages([lang])
    if rejected or not valid:
        return None, None, Response(
            {"error": "UNSUPPORTED_LANGUAGE", "rejected": rejected},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return field, lang, None


# ---------------------------------------------------------------------------
# Admin: PUT /admin/translations/content/{content_id}/fields/{field}/approve/
# ---------------------------------------------------------------------------


@api_view(["PUT"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def approve_translation_field(request, content_id, field):
    """Approve a single translated field for the given content and language.

    Returns the updated row's review state on success (200).
    Non-admin → 403 (via @admin_only).
    Cross-tenant or missing row → 404.
    """
    tenant = request.tenant

    allowed, reason = _check_rate_limit("review", str(tenant.id), REVIEW_RATE_LIMIT)
    if not allowed:
        _code = status.HTTP_503_SERVICE_UNAVAILABLE if reason == "service_unavailable" else status.HTTP_429_TOO_MANY_REQUESTS
        return Response({"error": reason}, status=_code)

    content = _content_for_tenant(content_id, tenant)
    if content is None:
        return Response({"error": "not_found"}, status=status.HTTP_404_NOT_FOUND)

    field_clean, lang, err = _parse_review_params(request, field)
    if err is not None:
        return err

    row, err = _get_review_row(content, tenant, field_clean, lang)
    if err is not None:
        return err

    now = timezone.now()
    row.review_status = REVIEW_STATUS_APPROVED
    row.reviewed_by = request.user
    row.reviewed_at = now
    row.save(update_fields=["review_status", "reviewed_by", "reviewed_at", "updated_at"])

    log_audit(
        request=request,
        action="TRANSLATION_FIELD_APPROVED",
        target_type="ContentTranslation",
        target_id=str(row.id),
        target_repr=str(row),
        changes={"field": field_clean, "lang": lang, "content_id": str(content.id)},
    )

    return Response(ContentTranslationReviewSerializer(row).data, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Admin: PUT /admin/translations/content/{content_id}/fields/{field}/reject/
# ---------------------------------------------------------------------------


@api_view(["PUT"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def reject_translation_field(request, content_id, field):
    """Reject a single translated field for the given content and language.

    Returns the updated row's review state on success (200).
    Non-admin → 403 (via @admin_only).
    Cross-tenant or missing row → 404.
    """
    tenant = request.tenant

    allowed, reason = _check_rate_limit("review", str(tenant.id), REVIEW_RATE_LIMIT)
    if not allowed:
        _code = status.HTTP_503_SERVICE_UNAVAILABLE if reason == "service_unavailable" else status.HTTP_429_TOO_MANY_REQUESTS
        return Response({"error": reason}, status=_code)

    content = _content_for_tenant(content_id, tenant)
    if content is None:
        return Response({"error": "not_found"}, status=status.HTTP_404_NOT_FOUND)

    field_clean, lang, err = _parse_review_params(request, field)
    if err is not None:
        return err

    row, err = _get_review_row(content, tenant, field_clean, lang)
    if err is not None:
        return err

    now = timezone.now()
    row.review_status = REVIEW_STATUS_REJECTED
    row.reviewed_by = request.user
    row.reviewed_at = now
    row.save(update_fields=["review_status", "reviewed_by", "reviewed_at", "updated_at"])

    log_audit(
        request=request,
        action="TRANSLATION_FIELD_REJECTED",
        target_type="ContentTranslation",
        target_id=str(row.id),
        target_repr=str(row),
        changes={"field": field_clean, "lang": lang, "content_id": str(content.id)},
    )

    return Response(ContentTranslationReviewSerializer(row).data, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Admin: PUT /admin/translations/content/{content_id}/fields/{field}/edit/
# ---------------------------------------------------------------------------


@api_view(["PUT"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def edit_translation_field(request, content_id, field):
    """Edit a translated field (admin manual correction) and auto-approve it.

    Body: ``{"edited_text": "<corrected text>"}``
    Returns the updated row on success (200) with review_status='approved'.
    Non-admin → 403 (via @admin_only).
    Cross-tenant or missing row → 404.
    """
    tenant = request.tenant

    allowed, reason = _check_rate_limit("review", str(tenant.id), REVIEW_RATE_LIMIT)
    if not allowed:
        _code = status.HTTP_503_SERVICE_UNAVAILABLE if reason == "service_unavailable" else status.HTTP_429_TOO_MANY_REQUESTS
        return Response({"error": reason}, status=_code)

    content = _content_for_tenant(content_id, tenant)
    if content is None:
        return Response({"error": "not_found"}, status=status.HTTP_404_NOT_FOUND)

    field_clean, lang, err = _parse_review_params(request, field)
    if err is not None:
        return err

    serializer = FieldEditSerializer(data=request.data)
    if not serializer.is_valid():
        # TASK-064b M1: if edited_text failed its max_length constraint, surface
        # the same FIELD_TOO_LARGE 413 that TASK-058 raises for source fields.
        edited_text_errors = serializer.errors.get("edited_text", [])
        # Primary check: DRF ValidationError detail items carry a .code attribute.
        # Fallback: string-match for defensive compat with non-standard error objects.
        is_too_large = any(
            getattr(e, "code", None) == "max_length"
            or "FIELD_TOO_LARGE" in str(e)
            for e in edited_text_errors
        )
        if is_too_large:
            return Response(
                {
                    "error": "FIELD_TOO_LARGE",
                    "detail": "edited_text exceeds the 50 000-character cap.",
                },
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    row, err = _get_review_row(content, tenant, field_clean, lang)
    if err is not None:
        return err

    now = timezone.now()
    row.edited_text = serializer.validated_data["edited_text"]
    row.review_status = REVIEW_STATUS_APPROVED
    row.reviewed_by = request.user
    row.reviewed_at = now
    row.save(
        update_fields=[
            "edited_text",
            "review_status",
            "reviewed_by",
            "reviewed_at",
            "updated_at",
        ]
    )

    log_audit(
        request=request,
        action="TRANSLATION_FIELD_EDITED",
        target_type="ContentTranslation",
        target_id=str(row.id),
        target_repr=str(row),
        changes={
            "field": field_clean,
            "lang": lang,
            "content_id": str(content.id),
            "edited_text_length": len(row.edited_text),
        },
    )

    return Response(ContentTranslationReviewSerializer(row).data, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Admin: POST /admin/translations/content/{content_id}/publish/
# ---------------------------------------------------------------------------


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def publish_content_translation(request, content_id):
    """Publish all approved translations for the given content and language.

    Only rows where ``review_status='approved'`` are promoted (published_at
    is set to now).  Rows with ``review_status='pending'`` or ``'rejected'``
    are skipped.

    Returns:
        {
          "published_at": "<iso8601>",
          "rows_published": <int>,
          "skipped": {
              "title":       "pending|rejected|not_translated",
              "description": ...,
              ...
          }
        }

    Non-admin → 403 (via @admin_only).
    Cross-tenant or missing content → 404.
    lang query-param required; UNSUPPORTED_LANGUAGE → 400.
    """
    tenant = request.tenant

    allowed, reason = _check_rate_limit("publish", str(tenant.id), PUBLISH_RATE_LIMIT)
    if not allowed:
        _code = status.HTTP_503_SERVICE_UNAVAILABLE if reason == "service_unavailable" else status.HTTP_429_TOO_MANY_REQUESTS
        return Response({"error": reason}, status=_code)

    content = _content_for_tenant(content_id, tenant)
    if content is None:
        return Response({"error": "not_found"}, status=status.HTTP_404_NOT_FOUND)

    lang = (request.GET.get("lang") or "").strip()
    if not lang:
        return Response({"error": "lang_required"}, status=status.HTTP_400_BAD_REQUEST)
    valid, rejected = validate_target_languages([lang])
    if rejected or not valid:
        return Response(
            {"error": "UNSUPPORTED_LANGUAGE", "rejected": rejected},
            status=status.HTTP_400_BAD_REQUEST,
        )

    now = timezone.now()
    all_rows = {
        r.field: r
        for r in ContentTranslation.objects.all_tenants().filter(
            tenant=tenant,
            source_type=SOURCE_TYPE_CONTENT,
            source_id=content.id,
            target_language=lang,
        )
    }

    rows_published = 0
    skipped: dict[str, str] = {}
    published_ids: list[str] = []

    for field_name in (FIELD_TITLE, FIELD_DESCRIPTION, FIELD_BODY, FIELD_TRANSCRIPT):
        row = all_rows.get(field_name)
        if row is None:
            skipped[field_name] = "not_translated"
            continue
        if row.review_status != REVIEW_STATUS_APPROVED:
            skipped[field_name] = row.review_status  # "pending" or "rejected"
            continue
        row.published_at = now
        row.save(update_fields=["published_at", "updated_at"])
        rows_published += 1
        published_ids.append(str(row.id))

    log_audit(
        request=request,
        action="TRANSLATION_PUBLISHED",
        target_type="Content",
        target_id=str(content.id),
        target_repr=str(content),
        changes={
            "lang": lang,
            "rows_published": rows_published,
            "skipped": skipped,
            "published_row_ids": published_ids,
        },
    )

    return Response(
        {
            "published_at": now.isoformat(),
            "rows_published": rows_published,
            "skipped": skipped,
        },
        status=status.HTTP_200_OK,
    )


# ---------------------------------------------------------------------------
# Teacher: GET /teacher/content/{id}/translation/?lang=xx
# ---------------------------------------------------------------------------


class _TeacherTranslationThrottle(ScopedRateThrottle):
    """Dedicated ScopedRateThrottle subclass for the teacher read path.

    DRF's ScopedRateThrottle needs a fixed ``scope`` attribute when used
    via ``@throttle_classes`` on a function-based view — it cannot read
    ``throttle_scope`` off the view callable.
    """

    scope = "teacher_translation_read"


def _is_teacher_enrolled_or_admin(user, tenant, course_id) -> bool:
    """Return True if user may view translations for the given course.

    Rules:
      * SCHOOL_ADMIN / SUPER_ADMIN of this tenant — allowed.
      * TEACHER (and similar authoring roles) — must have a
        ``TeacherProgress`` row for this course.
    """
    role = getattr(user, "role", "")
    if role in ("SCHOOL_ADMIN", "SUPER_ADMIN", "HOD", "IB_COORDINATOR"):
        return True
    # Non-admin — must have an existing progress row in this course.
    return TeacherProgress.all_objects.filter(
        tenant=tenant, teacher=user, course_id=course_id
    ).exists()


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@throttle_classes([_TeacherTranslationThrottle])
@tenant_required
def teacher_content_translation(request, content_id):
    tenant = request.tenant

    # Shape + allowlist validation BEFORE DB lookup to avoid leaking existence.
    lang = (request.GET.get("lang") or "").strip()
    if not lang:
        return Response(
            {"error": "lang_required"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    valid, rejected = validate_target_languages([lang])
    if rejected or not valid:
        return Response(
            {"error": "UNSUPPORTED_LANGUAGE", "rejected": rejected},
            status=status.HTTP_400_BAD_REQUEST,
        )

    content = _content_for_tenant(content_id, tenant)
    if content is None:
        # Cross-tenant or missing — 404 to avoid leaking existence.
        return Response(
            {"error": "not_found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    if not _is_teacher_enrolled_or_admin(
        request.user, tenant, content.module.course_id
    ):
        # Not enrolled → 404 (not 403, per spec).
        return Response(
            {"error": "not_found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    # TASK-064b: only return rows that an admin has published.
    # Prior to this change teachers saw ALL translated rows including pending
    # and rejected ones — a latent product concern.  Admins must approve and
    # then POST .../publish/ before a translation is visible here.
    rows = ContentTranslation.objects.all_tenants().filter(
        tenant=tenant,
        source_type=SOURCE_TYPE_CONTENT,
        source_id=content.id,
        target_language=lang,
        published_at__isnull=False,
    )
    if not rows.exists():
        return Response(
            {"error": "TRANSLATION_NOT_AVAILABLE"},
            status=status.HTTP_404_NOT_FOUND,
        )

    by_field = {r.field: r for r in rows}

    # Defense-in-depth: if source hash doesn't match current source, flag stale.
    stale = False
    try:
        from .services import compute_source_hash
        current_pairs = {f: t for f, t in extract_content_fields(content)}
        # Use any existing row's (provider, model) as the hash key.
        any_row = next(iter(by_field.values()))
        src_lang = getattr(tenant, "default_language", None) or "en"
        for field, row in by_field.items():
            expected = compute_source_hash(
                current_pairs.get(field, ""),
                src_lang,
                lang,
                any_row.model,
            )
            if row.source_hash != expected:
                stale = True
                break
    except (AttributeError, KeyError, TypeError):  # pragma: no cover - defensive
        pass

    def _effective_text(row) -> str:
        """Return edited_text if the admin provided a correction, else translated_text."""
        if row.edited_text is not None:
            return row.edited_text
        return row.translated_text

    return Response(
        {
            "content_id": str(content.id),
            "lang": lang,
            "title": _effective_text(by_field[FIELD_TITLE]) if FIELD_TITLE in by_field else None,
            "description": _effective_text(by_field[FIELD_DESCRIPTION]) if FIELD_DESCRIPTION in by_field else None,
            "body": _effective_text(by_field[FIELD_BODY]) if FIELD_BODY in by_field else None,
            "transcript": _effective_text(by_field[FIELD_TRANSCRIPT]) if FIELD_TRANSCRIPT in by_field else None,
            "stale": stale,
        }
    )
