"""
Views for semantic_search (TASK-057).

Three endpoints:

  POST /api/v1/search/semantic/                 — query (teacher+admin)
  POST /api/v1/admin/search/reindex-tenant/     — admin-only enqueue
  GET  /api/v1/admin/search/status/             — admin-only status

Cross-tenant policy: every view runs under ``@tenant_required`` so
SCHOOL_ADMINs from tenant A cannot target tenant B. We additionally
reject mismatched ``tenant_id`` in the reindex payload with 404.
"""

from __future__ import annotations

import logging
import uuid

from django.core.cache import cache
from django.db import connection
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from utils.audit import log_audit
from utils.decorators import admin_only, tenant_required

from .embeddings import EmbeddingError, embedder_info
from .models import EmbeddingChunk, EmbeddingJobRun
from .retrieval import (
    MAX_QUERY_CHARS,
    MAX_TOP_K,
    SearchValidationError,
    search,
)
from .serializers import SemanticSearchRequestSerializer


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DRF throttle (60/min/user)
# ---------------------------------------------------------------------------


class _SemanticSearchThrottle(ScopedRateThrottle):
    """Concrete ScopedRateThrottle subclass for function-based views.

    DRF's ScopedRateThrottle reads ``throttle_scope`` from the *view*
    object; FBV's @api_view wrapper exposes no class-level attribute.
    A dedicated subclass with a fixed ``scope`` is the idiomatic
    workaround (see apps/integrations_chat/views.py).
    """
    scope = "search_semantic"


# ---------------------------------------------------------------------------
# Rate-limit helper for reindex-tenant (1/hr/tenant, fail-CLOSED)
# ---------------------------------------------------------------------------

REINDEX_RATE_LIMIT = 1
REINDEX_RATE_WINDOW = 3600  # 1 hour


def _reindex_rate_key(tenant_id) -> str:
    return f"semantic_search:reindex_tenant:{tenant_id}"


def _check_and_increment_reindex_rate(tenant_id) -> tuple[bool, str]:
    """
    Fail-CLOSED rate-limit check.

    Returns ``(allowed, error_code)``. When the cache backend raises
    on either ``get`` or ``set``, we treat it as a hard failure and
    return ``(False, "service_unavailable")`` so the view can respond
    503. This is a hard requirement (TASK-053 / TASK-047 reviewers
    verify both branches).
    """
    key = _reindex_rate_key(tenant_id)
    try:
        current = cache.get(key)
    except Exception:
        logger.exception("semantic_search: rate-limit cache.get failed (tenant=%s)", tenant_id)
        return False, "service_unavailable"

    if current is None:
        current = 0

    if current >= REINDEX_RATE_LIMIT:
        return False, "rate_limit_exceeded"

    try:
        cache.set(key, current + 1, timeout=REINDEX_RATE_WINDOW)
    except Exception:
        logger.exception("semantic_search: rate-limit cache.set failed (tenant=%s)", tenant_id)
        return False, "service_unavailable"

    return True, ""


# ---------------------------------------------------------------------------
# POST /search/semantic/
# ---------------------------------------------------------------------------


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@tenant_required
@throttle_classes([_SemanticSearchThrottle])
def semantic_search_view(request):
    """
    Semantic similarity search over the current tenant's course content.

    Body:
        { query: str, top_k?: int<=50, kinds?: [..], course_id?: uuid }

    Errors:
        400 TOP_K_TOO_LARGE            — top_k > 50
        400 QUERY_TOO_LONG             — query > 2000 chars
        400 VALIDATION_ERROR           — other input problems
        503 EMBEDDINGS_UNAVAILABLE     — upstream provider chain failed
    """
    tenant = request.tenant

    # Fast-path caps BEFORE the serializer — lets us return the exact
    # error codes the spec mandates (TOP_K_TOO_LARGE / QUERY_TOO_LONG).
    body = request.data or {}

    top_k_raw = body.get("top_k", 10)
    try:
        if int(top_k_raw) > MAX_TOP_K:
            return Response(
                {"error": "TOP_K_TOO_LARGE", "max": MAX_TOP_K},
                status=status.HTTP_400_BAD_REQUEST,
            )
    except (TypeError, ValueError):
        pass  # serializer will reject below

    q_raw = body.get("query", "") or ""
    if isinstance(q_raw, str) and len(q_raw) > MAX_QUERY_CHARS:
        return Response(
            {"error": "QUERY_TOO_LONG", "max": MAX_QUERY_CHARS},
            status=status.HTTP_400_BAD_REQUEST,
        )

    ser = SemanticSearchRequestSerializer(data=body)
    if not ser.is_valid():
        errs = ser.errors
        # Translate inner codes back up.
        flat = [str(e) for v in errs.values() for e in v] if isinstance(errs, dict) else []
        if any("TOP_K_TOO_LARGE" in s for s in flat):
            return Response({"error": "TOP_K_TOO_LARGE"}, status=status.HTTP_400_BAD_REQUEST)
        if any("QUERY_TOO_LONG" in s for s in flat):
            return Response({"error": "QUERY_TOO_LONG"}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {"error": "VALIDATION_ERROR", "details": errs},
            status=status.HTTP_400_BAD_REQUEST,
        )

    v = ser.validated_data
    try:
        hits = search(
            tenant,
            v["query"],
            top_k=v.get("top_k") or 10,
            kinds=v.get("kinds") or None,
            course_id=str(v["course_id"]) if v.get("course_id") else None,
        )
    except SearchValidationError as exc:
        msg = str(exc)
        if msg in ("TOP_K_TOO_LARGE", "QUERY_TOO_LONG"):
            return Response({"error": msg}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {"error": "VALIDATION_ERROR", "detail": msg},
            status=status.HTTP_400_BAD_REQUEST,
        )
    except EmbeddingError as exc:
        logger.warning("semantic_search: embedding provider unavailable: %s", exc)
        return Response(
            {"error": "EMBEDDINGS_UNAVAILABLE", "detail": str(exc)},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    except Exception:
        logger.exception("semantic_search: unexpected failure")
        return Response(
            {"error": "INTERNAL_ERROR"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return Response(
        {
            "results": hits,
            "count": len(hits),
            "top_k": v.get("top_k") or 10,
            "query": v["query"],
        }
    )


# ---------------------------------------------------------------------------
# POST /admin/search/reindex-tenant/
# ---------------------------------------------------------------------------


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def reindex_tenant_view(request):
    """
    Enqueue a full-tenant reindex.

    - Admin-only; cross-tenant attempts (non-matching ``tenant_id`` in
      body) return 404 to avoid leaking tenant existence.
    - Rate-limited 1/hour/tenant; cache outage fails CLOSED → 503.
    """
    tenant = request.tenant

    # Cross-tenant guard: if a tenant_id is supplied, it MUST match.
    target_id = (request.data or {}).get("tenant_id")
    if target_id:
        try:
            uuid.UUID(str(target_id))
        except (ValueError, TypeError):
            return Response({"error": "NOT_FOUND"}, status=status.HTTP_404_NOT_FOUND)
        if str(target_id) != str(tenant.id):
            return Response({"error": "NOT_FOUND"}, status=status.HTTP_404_NOT_FOUND)

    allowed, error_code = _check_and_increment_reindex_rate(tenant.id)
    if not allowed:
        if error_code == "service_unavailable":
            return Response(
                {"error": "SERVICE_UNAVAILABLE"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(
            {"error": "RATE_LIMIT_EXCEEDED", "detail": "1 reindex / hour / tenant"},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    # Audit: STARTED (synchronous; task emits FINISHED/FAILED later).
    log_audit(
        action="SEMANTIC_REINDEX_STARTED",
        target_type="Tenant",
        target_id=str(tenant.id),
        target_repr=tenant.name,
        request=request,
        tenant=tenant,
    )

    try:
        from .tasks import reindex_tenant as reindex_tenant_task

        async_result = reindex_tenant_task.apply_async(args=[str(tenant.id)])
        task_id = getattr(async_result, "id", None)
    except Exception as exc:
        logger.exception("semantic_search: reindex enqueue failed tenant=%s", tenant.id)
        log_audit(
            action="SEMANTIC_REINDEX_FAILED",
            target_type="Tenant",
            target_id=str(tenant.id),
            target_repr=tenant.name,
            changes={"error": str(exc)[:500]},
            request=request,
            tenant=tenant,
        )
        return Response(
            {"error": "ENQUEUE_FAILED"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return Response(
        {"status": "queued", "task_id": task_id, "tenant_id": str(tenant.id)},
        status=status.HTTP_202_ACCEPTED,
    )


# ---------------------------------------------------------------------------
# GET /admin/search/status/
# ---------------------------------------------------------------------------


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def search_status_view(request):
    """Return a lightweight status payload for the admin UI."""
    tenant = request.tenant

    total = EmbeddingChunk.all_objects.filter(tenant=tenant).count()
    by_kind_qs = (
        EmbeddingChunk.all_objects
        .filter(tenant=tenant)
        .values_list("source_type")
    )
    per_kind: dict = {}
    for (st,) in by_kind_qs:
        per_kind[st] = per_kind.get(st, 0) + 1

    last_succeeded = (
        EmbeddingJobRun.objects
        .filter(tenant=tenant, status=EmbeddingJobRun.STATUS_SUCCEEDED)
        .order_by("-finished_at")
        .first()
    )
    pending = EmbeddingJobRun.objects.filter(
        tenant=tenant, status=EmbeddingJobRun.STATUS_RUNNING,
    ).count()

    # Has the vector column been installed?
    has_vector = False
    try:
        with connection.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name=%s AND column_name=%s",
                ["semantic_search_embeddingchunk", "embedding"],
            )
            has_vector = cur.fetchone() is not None
    except Exception:
        has_vector = False

    return Response(
        {
            "tenant_id": str(tenant.id),
            "total_chunks": total,
            "by_kind": per_kind,
            "last_successful_reindex": (
                last_succeeded.finished_at.isoformat() if last_succeeded and last_succeeded.finished_at else None
            ),
            "pending_jobs": pending,
            "pgvector_installed": has_vector,
            "embedder": embedder_info(),
        }
    )
