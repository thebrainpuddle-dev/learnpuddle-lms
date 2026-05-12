"""HTTP views for MAIC v2.

Phase 1 ships a single endpoint:

  POST /api/maic/v2/sessions/
    Creates a new MaicSessionV2 row bound to the authenticated user's
    tenant.  Returns the session_id + WebSocket URL the frontend should
    open next.  Idempotent for `(tenant, opened_by)` when the caller
    passes a known session_id (frontend can persist + reconnect to it
    across reloads).

The WS consumer (apps/maic/consumers.py, MAIC-101) ALSO creates
sessions ad-hoc on first connect — both paths write to the same row.
This HTTP route is the canonical "I want to start a classroom" entry
point so frontend code doesn't need a "create-on-connect race"
defensive pattern.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.courses.models import Course
from apps.maic.models import MaicSessionV2
from apps.maic.permissions import MaicV2TenantPermission
from apps.maic.runtime_gap_quiz import (
    grade_quiz_payload,
    normalize_quiz_grade_payload,
)
from apps.tenants.models import Tenant

logger = logging.getLogger(__name__)


def _ws_url_for(request: Request, session_id: str) -> str:
    """Build the absolute WS URL for the freshly-created session.

    Returns ws[s]://<host>/ws/maic/v2/classroom/<session_id>/
    matching the route mounted by apps/maic/routing.py.
    """
    is_secure = request.is_secure()
    proto = "wss" if is_secure else "ws"
    host = request.get_host()
    return f"{proto}://{host}/ws/maic/v2/classroom/{session_id}/"


class MaicSessionCreateView(APIView):
    """POST /api/maic/v2/sessions/ — create a MAIC v2 classroom session.

    Request body (all optional):
      session_id: caller-chosen id (must match `[\\w-]{1,64}`); if
                  omitted we mint a `s-<uuid4>` form.
      course_id:  optional Course FK to bind the session to (must be in
                  the same tenant; otherwise 404'd).

    Response 201:
      { sessionId: str, wsUrl: str, tenantId: str|int }

    Response 400:
      { error: "<reason>" }

    Response 404:
      Course not found in the user's tenant.
    """

    permission_classes = [IsAuthenticated, MaicV2TenantPermission]

    def post(self, request: Request) -> Response:
        user = request.user
        tenant_id = getattr(user, "tenant_id", None)
        if tenant_id is None:
            logger.warning(
                "MAIC v2 sessions.create: user=%s has no tenant_id",
                getattr(user, "id", None),
            )
            return Response(
                {"error": "user has no tenant"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        body: dict[str, Any] = request.data if isinstance(request.data, dict) else {}

        # session_id — caller-supplied or minted; validate the route regex
        session_id = body.get("session_id") or f"s-{uuid.uuid4().hex[:24]}"
        if not isinstance(session_id, str) or not _is_valid_session_id(session_id):
            return Response(
                {"error": "session_id must match [\\w-]{1,64}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Optional course binding — must be in the user's tenant
        course = None
        course_id = body.get("course_id")
        if course_id is not None:
            # Course.objects auto-filters to current tenant via TenantManager
            # IF a tenant is set on the thread-local. The DRF view runs after
            # TenantMiddleware, so this is safe.
            course = Course.objects.filter(id=course_id).first()
            if course is None:
                return Response(
                    {"error": "course not found in your tenant"},
                    status=status.HTTP_404_NOT_FOUND,
                )

        # Resolve the Tenant explicitly (we don't use TenantManager here
        # because we want to write the FK id directly without a query).
        tenant = Tenant.objects.filter(id=tenant_id).first()
        if tenant is None:
            return Response(
                {"error": "user's tenant has been deleted"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Get-or-create — caller-supplied session_id can already exist.
        # We treat that as idempotent within the user's tenant; cross-tenant
        # collisions raise 409.
        existing = (
            MaicSessionV2.objects.all_tenants()
            .filter(id=session_id)
            .first()
        )
        if existing is not None:
            if existing.tenant_id != tenant_id:
                logger.warning(
                    "MAIC v2 sessions.create: session_id=%s collides across tenants "
                    "(existing tenant=%s, request tenant=%s, user=%s)",
                    session_id, existing.tenant_id, tenant_id, user.id,
                )
                return Response(
                    {"error": "session_id already exists for a different tenant"},
                    status=status.HTTP_409_CONFLICT,
                )
            session = existing
            created = False
        else:
            session = MaicSessionV2.objects.create(
                id=session_id,
                tenant=tenant,
                course=course,
                opened_by=user,
            )
            created = True

        logger.info(
            "MAIC v2 sessions.create: %s session_id=%s tenant=%s user=%s",
            "created" if created else "reused",
            session_id, tenant_id, user.id,
        )

        return Response(
            {
                "sessionId": session.id,
                "wsUrl": _ws_url_for(request, session.id),
                "tenantId": str(session.tenant_id),
                "courseId": str(session.course_id) if session.course_id else None,
                "created": created,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


def _is_valid_session_id(s: str) -> bool:
    """Mirror the route regex `[\\w-]{1,64}` from apps/maic/routing.py."""
    if not s or len(s) > 64:
        return False
    import re
    return bool(re.fullmatch(r"[\w-]+", s))


class MaicQuizGradeView(APIView):
    """POST /api/maic/v2/quiz-grade/ — grade a MAIC v2 quiz answer."""

    permission_classes = [IsAuthenticated, MaicV2TenantPermission]

    def post(self, request: Request) -> Response:
        tenant = getattr(request.user, "tenant", None)
        payload, error = normalize_quiz_grade_payload(request.data)
        if error:
            return error

        assert payload is not None
        result, error = grade_quiz_payload(payload, tenant)
        if error:
            return error

        return Response(result)
