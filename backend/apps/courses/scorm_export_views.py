"""
apps/courses/scorm_export_views.py
-----------------------------------
SCORM 1.2 export endpoints.

Endpoints:
  POST /api/v1/admin/courses/{id}/scorm-export/   → whole-course zip
  POST /api/v1/admin/contents/{id}/scorm-export/  → single-content zip

Both endpoints are:
  * Admin-only  (@admin_only + @tenant_required)
  * Rate-limited: 10 exports/hour/tenant (fail-closed on cache outage)
  * Audit-logged on success (action="EXPORT_SCORM")

Error codes returned in response body (HTTP 400):
  * CANNOT_REEXPORT_SCORM — content is an imported SCORM package
  * PACKAGE_TOO_LARGE     — estimated size > 500 MB
  * COURSE_DELETED        — soft-deleted course
  * CONTENT_DELETED       — soft-deleted content

HTTP 503 is returned when the cache is unavailable (rate-limit fail-closed).
"""

from __future__ import annotations

import logging

from django.core.cache import cache
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from utils.audit import log_audit
from utils.decorators import admin_only, tenant_required

from .models import Content, Course
from .scorm_export import (
    CANNOT_REEXPORT_SCORM,
    CONTENT_DELETED,
    COURSE_DELETED,
    PACKAGE_TOO_LARGE,
    ScormExportError,
    build_scorm_package_for_content,
    build_scorm_package_for_course,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

EXPORT_RATE_LIMIT = 10  # exports per hour
EXPORT_RATE_WINDOW = 3600  # 1 hour in seconds


def _rate_limit_key(tenant_id) -> str:
    return f"scorm_export:rate:{tenant_id}"


def _check_and_increment_rate_limit(tenant_id) -> tuple[bool, str]:
    """Check and increment the per-tenant export rate counter.

    Returns:
        (allowed: bool, error_detail: str)
        error_detail is non-empty only when allowed=False.

    Fail-closed: if the cache raises any exception, deny the request (503).
    """
    key = _rate_limit_key(tenant_id)
    try:
        current = cache.get(key)
    except Exception:
        logger.exception(
            "SCORM export rate-limit cache unavailable (get) tenant=%s", tenant_id
        )
        return False, "service_unavailable"

    if current is None:
        current = 0

    if current >= EXPORT_RATE_LIMIT:
        return False, "rate_limit_exceeded"

    try:
        cache.set(key, current + 1, timeout=EXPORT_RATE_WINDOW)
    except Exception:
        logger.exception(
            "SCORM export rate-limit cache unavailable (set) tenant=%s", tenant_id
        )
        return False, "service_unavailable"

    return True, ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _zip_response(zip_bytes: bytes, filename: str) -> HttpResponse:
    """Return an HttpResponse streaming the zip bytes as an attachment."""
    response = HttpResponse(zip_bytes, content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Content-Length"] = str(len(zip_bytes))
    return response


def _handle_export_error(exc: ScormExportError) -> Response:
    """Map a ScormExportError to an appropriate DRF Response."""
    http_status = status.HTTP_400_BAD_REQUEST
    return Response(
        {"error": exc.message, "code": exc.code},
        status=http_status,
    )


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def course_scorm_export(request, course_id):
    """Export a whole course as a SCORM 1.2 zip.

    URL: POST /api/v1/admin/courses/{course_id}/scorm-export/

    Returns a streaming zip download.  The zip contains:
      * imsmanifest.xml  — SCORM 1.2 manifest
      * content/*.html   — per-content launch HTML files

    Rate limit: 10 exports/hour/tenant (fail-closed on cache outage → 503).
    """
    # Rate limit
    allowed, err = _check_and_increment_rate_limit(request.tenant.id)
    if not allowed:
        if err == "service_unavailable":
            return Response(
                {"error": "Service temporarily unavailable. Please try again later."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(
            {"error": "Export rate limit exceeded. Please try again later."},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    # Cross-tenant: get_object_or_404 returns 404 if tenant doesn't match.
    # Course.objects uses TenantSoftDeleteManager which already filters by
    # tenant (via TenantMiddleware context) AND excludes soft-deleted.
    # We use all_objects so we can give a better error for deleted courses.
    course = get_object_or_404(
        Course.all_objects.filter(tenant=request.tenant),
        id=course_id,
    )

    try:
        zip_bytes, filename = build_scorm_package_for_course(
            course=course, user=request.user
        )
    except ScormExportError as exc:
        return _handle_export_error(exc)
    except Exception:
        logger.exception(
            "Unexpected error building SCORM export for course=%s", course_id
        )
        return Response(
            {"error": "An unexpected error occurred during SCORM export."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    log_audit(
        action="EXPORT_SCORM",
        target_type="Course",
        target_id=str(course.id),
        target_repr=str(course),
        request=request,
        changes={
            "filename": filename,
            "size_bytes": len(zip_bytes),
        },
    )

    return _zip_response(zip_bytes, filename)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def content_scorm_export(request, content_id):
    """Export a single content item as a minimal SCORM 1.2 zip.

    URL: POST /api/v1/admin/contents/{content_id}/scorm-export/

    Exportable content types: TEXT, VIDEO, QUIZ, DOCUMENT, LINK.
    SCORM packages cannot be re-exported (returns 400 + CANNOT_REEXPORT_SCORM).

    Rate limit: 10 exports/hour/tenant (fail-closed on cache outage → 503).
    """
    # Rate limit
    allowed, err = _check_and_increment_rate_limit(request.tenant.id)
    if not allowed:
        if err == "service_unavailable":
            return Response(
                {"error": "Service temporarily unavailable. Please try again later."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(
            {"error": "Export rate limit exceeded. Please try again later."},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    # Resolve content — cross-tenant returns 404 automatically because Content
    # doesn't have a direct tenant FK; we traverse course.tenant instead.
    # We use all_objects to fetch deleted items too (so we can give better error
    # messages for deleted content vs non-existent).
    content = get_object_or_404(
        Content.all_objects.select_related("module__course"),
        id=content_id,
    )

    # Cross-tenant check: ensure the content belongs to the requesting tenant.
    if content.module.course.tenant_id != request.tenant.id:
        # Return 404 — never reveal existence of cross-tenant content.
        from django.http import Http404

        raise Http404

    try:
        zip_bytes, filename = build_scorm_package_for_content(
            content=content, user=request.user
        )
    except ScormExportError as exc:
        return _handle_export_error(exc)
    except Exception:
        logger.exception(
            "Unexpected error building SCORM export for content=%s", content_id
        )
        return Response(
            {"error": "An unexpected error occurred during SCORM export."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    log_audit(
        action="EXPORT_SCORM",
        target_type="Content",
        target_id=str(content.id),
        target_repr=str(content),
        request=request,
        changes={
            "filename": filename,
            "size_bytes": len(zip_bytes),
            "content_type": content.content_type,
        },
    )

    return _zip_response(zip_bytes, filename)
