"""
Chatbot views for TASK-059 — AI Chatbot Tutor (RAG backend).

Endpoints:
  POST   /api/v1/chatbot/ask/             — submit a question
  GET    /api/v1/chatbot/history/         — list caller's chat history
  DELETE /api/v1/chatbot/history/{id}/    — purge a query row

Security:
  - Rate limit: 30 questions/hour/user — fail-CLOSED on cache outage (503).
  - Question length cap: 2000 chars → 400 QUESTION_TOO_LONG.
  - Course scope guard: caller must be enrolled or admin.
  - Tenant isolation: every query scoped to request.tenant.
  - PII: question text is NEVER logged; only structured metadata.
"""

from __future__ import annotations

import logging
import time

from django.core.cache import cache
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from utils.audit import log_audit
from utils.decorators import tenant_required

from .models import ChatQuery
from .rag_service import RAGAnswer, answer_question
from .serializers import AskRequestSerializer, AskResponseSerializer, ChatQueryHistorySerializer

logger = logging.getLogger(__name__)

# ── Rate limiting constants ───────────────────────────────────────────────────
RATE_LIMIT_WINDOW = 3600  # 1 hour in seconds
RATE_LIMIT_MAX = 30       # max questions per user per window


# ── Rate limiter (fail-CLOSED) ────────────────────────────────────────────────

def _rate_limit_key(user_id: str) -> str:
    return f"chatbot_rl:{user_id}:{int(time.time()) // RATE_LIMIT_WINDOW}"


def _check_and_increment_rate_limit(user_id: str) -> Response | None:
    """
    Check and increment the per-user rate limit.

    Returns:
        None if request should proceed.
        Response(503) on cache.get failure (fail-CLOSED).
        Response(503) on cache.set failure (fail-CLOSED).
        Response(429) if limit is exceeded.
    """
    key = _rate_limit_key(user_id)

    # Fail-CLOSED on cache.get failure
    try:
        count = cache.get(key)
    except Exception as exc:
        logger.error("chatbot: cache.get failed in rate limiter: %s", exc)
        return Response(
            {
                "error": "SERVICE_UNAVAILABLE",
                "detail": "Rate limiting service unavailable.",
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    if count is None:
        count = 0

    if count >= RATE_LIMIT_MAX:
        return Response(
            {
                "error": "RATE_LIMIT_EXCEEDED",
                "detail": f"Maximum {RATE_LIMIT_MAX} questions per hour.",
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
        logger.error("chatbot: cache.set/incr failed in rate limiter: %s", exc)
        return Response(
            {
                "error": "SERVICE_UNAVAILABLE",
                "detail": "Rate limiting service unavailable.",
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return None


# ── Course scope guard ────────────────────────────────────────────────────────

def _check_course_scope(request, course_id) -> Response | None:
    """
    Verify the caller is enrolled in the course or is an admin.

    Returns None if allowed, Response(403) if denied, Response(404) if course
    not found in tenant.
    """
    from apps.courses.models import Course

    tenant = request.tenant
    user = request.user

    # Admin (SCHOOL_ADMIN / SUPER_ADMIN) always allowed
    if user.role in ("SCHOOL_ADMIN", "SUPER_ADMIN"):
        return None

    try:
        course = Course.all_objects.get(id=course_id, tenant=tenant)
    except Course.DoesNotExist:
        return Response(
            {"error": "NOT_FOUND", "detail": "Course not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Check teacher is assigned
    is_assigned = (
        course.assigned_to_all
        or course.assigned_teachers.filter(id=user.id).exists()
        or course.assigned_groups.filter(members=user).exists()
    )
    if not is_assigned:
        return Response(
            {
                "error": "FORBIDDEN",
                "detail": "You are not enrolled in this course.",
            },
            status=status.HTTP_403_FORBIDDEN,
        )
    return None


# ── Views ─────────────────────────────────────────────────────────────────────


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@tenant_required
def ask_view(request):
    """POST /api/v1/chatbot/ask/

    Body: { question: str, course_id?: UUID, top_k?: int }
    Returns: { query_id, answer, citations, grounded }
    """
    tenant = request.tenant
    user = request.user

    # ── Rate limit ────────────────────────────────────────────────────────────
    rl_response = _check_and_increment_rate_limit(str(user.id))
    if rl_response is not None:
        return rl_response

    # ── Deserialise + validate input ──────────────────────────────────────────
    serializer = AskRequestSerializer(data=request.data)
    if not serializer.is_valid():
        # Surface QUESTION_TOO_LONG specifically for the length cap
        errors = serializer.errors
        if "question" in errors:
            for err in errors["question"]:
                if "2000" in str(err) or "max_length" in str(err).lower():
                    return Response(
                        {
                            "error": "QUESTION_TOO_LONG",
                            "detail": "Question must be 2000 characters or fewer.",
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )
        return Response(errors, status=status.HTTP_400_BAD_REQUEST)

    question: str = serializer.validated_data["question"]
    course_id = serializer.validated_data.get("course_id")
    top_k: int = serializer.validated_data.get("top_k", 5)

    # Manual length guard (belt-and-suspenders after serializer)
    if len(question) > 2000:
        return Response(
            {
                "error": "QUESTION_TOO_LONG",
                "detail": "Question must be 2000 characters or fewer.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ── Course scope guard ────────────────────────────────────────────────────
    if course_id is not None:
        scope_response = _check_course_scope(request, course_id)
        if scope_response is not None:
            return scope_response

    # ── RAG pipeline ──────────────────────────────────────────────────────────
    try:
        rag_answer: RAGAnswer = answer_question(
            question=question,
            tenant=tenant,
            user=user,
            course_id=str(course_id) if course_id else None,
            top_k=top_k,
        )
    except Exception as exc:
        # Persist an error row for the audit trail before surfacing the 500.
        # The question text is stored in the DB row (compliance); it is NEVER
        # logged to stdout.
        error_msg = str(exc)[:500]
        try:
            ChatQuery.objects.create(
                tenant=tenant,
                user=user,
                course_id=course_id,
                question=question,
                answer="",
                error=error_msg,
                grounded=False,
            )
        except Exception:
            logger.exception("chatbot: failed to persist error ChatQuery row")
        logger.error(
            "chatbot.ask: RAG pipeline failed query_id=None tenant=%s user=%s",
            str(tenant.id),
            str(user.id),
        )
        return Response(
            {"error": "SERVICE_ERROR", "detail": "An internal error occurred."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    # ── Persist query row ─────────────────────────────────────────────────────
    citations_data = [
        {
            "block": c.block,
            "source_type": c.source_type,
            "source_id": c.source_id,
            "title": c.title,
            "score": c.score,
        }
        for c in rag_answer.citations
    ]

    query = ChatQuery.objects.create(
        tenant=tenant,
        user=user,
        course_id=course_id,
        question=question,
        retrieved_chunk_ids=rag_answer.retrieved_chunk_ids,
        answer=rag_answer.answer,
        citations=citations_data,
        grounded=rag_answer.grounded,
        provider=rag_answer.provider,
        model=rag_answer.model,
        tokens_prompt=rag_answer.tokens_prompt,
        tokens_completion=rag_answer.tokens_completion,
        latency_ms=rag_answer.latency_ms,
        # Persist retrieval errors (e.g. "search_failed") for ops observability.
        # None → empty string (ChatQuery.error is a CharField with default="").
        error=rag_answer.error or "",
    )

    # ── Audit log (no question text) ──────────────────────────────────────────
    log_audit(
        action="CHAT_QUERY_ASKED",
        target_type="ChatQuery",
        target_id=str(query.id),
        target_repr=f"ChatQuery({query.id})",
        changes={
            "tenant_id": str(tenant.id),
            "user_id": str(user.id),
            "course_id": str(course_id) if course_id else None,
            "grounded": rag_answer.grounded,
            "latency_ms": rag_answer.latency_ms,
            "provider": rag_answer.provider,
        },
        request=request,
    )

    # Structured metadata log — PII-free.
    logger.info(
        "chatbot.ask: query_id=%s tenant=%s user=%s latency_ms=%s grounded=%s",
        str(query.id),
        str(tenant.id),
        str(user.id),
        rag_answer.latency_ms,
        rag_answer.grounded,
    )

    response_data = {
        "query_id": str(query.id),
        "answer": rag_answer.answer,
        "citations": citations_data,
        "grounded": rag_answer.grounded,
    }
    return Response(response_data, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@tenant_required
def history_list_view(request):
    """GET /api/v1/chatbot/history/

    Returns the caller's query history (30-day window, paginated).
    Admin can filter to another user in the same tenant via ?user_id=.
    """
    import datetime

    from django.utils import timezone

    tenant = request.tenant
    user = request.user

    # Build base queryset — scoped to tenant
    qs = ChatQuery.all_objects.filter(
        tenant=tenant,
        created_at__gte=timezone.now() - datetime.timedelta(days=30),
    ).order_by("-created_at")

    # Admin: can filter by ?user_id=
    user_id_filter = request.query_params.get("user_id")
    if user_id_filter and user.role in ("SCHOOL_ADMIN", "SUPER_ADMIN"):
        qs = qs.filter(user_id=user_id_filter)
    else:
        # Regular teachers can only see their own history
        qs = qs.filter(user=user)

    # Simple pagination
    try:
        page_size = max(1, min(100, int(request.query_params.get("page_size", 20))))
    except (ValueError, TypeError):
        page_size = 20
    try:
        page = max(1, int(request.query_params.get("page", 1)))
    except (ValueError, TypeError):
        page = 1

    offset = (page - 1) * page_size
    items = qs[offset: offset + page_size]
    total = qs.count()

    serializer = ChatQueryHistorySerializer(items, many=True)
    return Response(
        {
            "results": serializer.data,
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
@tenant_required
def history_delete_view(request, query_id: str):
    """DELETE /api/v1/chatbot/history/{query_id}/

    Teacher can delete their own row.
    Admin can delete any row within the tenant.
    Cross-tenant → 404.
    """
    tenant = request.tenant
    user = request.user

    try:
        query = ChatQuery.all_objects.get(id=query_id, tenant=tenant)
    except ChatQuery.DoesNotExist:
        return Response(
            {"error": "NOT_FOUND", "detail": "Query not found."},
            status=status.HTTP_404_NOT_FOUND,
        )

    # Permission check
    is_admin = user.role in ("SCHOOL_ADMIN", "SUPER_ADMIN")
    is_owner = str(query.user_id) == str(user.id)
    if not is_admin and not is_owner:
        return Response(
            {
                "error": "FORBIDDEN",
                "detail": "You can only delete your own query history.",
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    audit_changes = {
        "tenant_id": str(tenant.id),
        "deleted_by_user_id": str(user.id),
        "owner_user_id": str(query.user_id),
        "grounded": query.grounded,
    }

    # Purge row
    query.delete()

    log_audit(
        action="CHAT_QUERY_PURGED",
        target_type="ChatQuery",
        target_id=str(query_id),
        target_repr=f"ChatQuery({query_id})",
        changes=audit_changes,
        request=request,
    )

    return Response(status=status.HTTP_204_NO_CONTENT)
