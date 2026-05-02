"""WebSocket consumers for MAIC v2 — see docs/AI_CLASSROOM_BLUEPRINT.md §3.2.

Wire format (matches OpenMAIC StatelessEvent — `lib/types/chat.ts`):

  ← from server: {"type": "agent_start" | "text_delta" | "action" |
                          "agent_end" | "thinking" | "cue_user" |
                          "speech_audio" | "error",
                  "data": {...}}
  → to server:   {"action": "start" | "interrupt" | "resume" | "stop",
                  "data": {...}}

Auth: JWT in `Sec-WebSocket-Protocol: Bearer.<jwt>` subprotocol, parsed
by `apps/notifications/middleware.py::JWTAuthMiddleware` (already in the
global Channels middleware chain via `config/asgi.py`).

Close codes:
  4001 — anonymous (no JWT or invalid JWT)
  4003 — authenticated but session_id belongs to a different tenant
         (cross-tenant access attempt)
  4004 — authenticated user has no tenant_id (system error / corrupt user)

Tenant binding (MAIC-101):
  On connect we look up MaicSessionV2 by session_id. If the row exists
  and tenant_id matches the user's tenant, accept. If the row exists
  with a DIFFERENT tenant, close 4003. If the row does NOT exist, we
  create it on the fly bound to the user's tenant — Phase 1 lets the
  WS open ad-hoc so the dev probe and future "join this classroom by
  link" flows work without an explicit HTTP-create step. MAIC-301 will
  add the explicit POST /api/maic/v2/sessions/ route for the regular
  flow; both write the same `maic_session_v2` row.
"""
from __future__ import annotations

import logging
from typing import Any

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth.models import AnonymousUser

logger = logging.getLogger(__name__)


@database_sync_to_async
def _resolve_or_create_session(session_id: str, user) -> tuple[Any, bool]:
    """Look up `MaicSessionV2` for this session_id; create on miss.

    Returns (session, cross_tenant) where cross_tenant is True when the
    session exists for a DIFFERENT tenant than the user's. The caller
    closes 4003 in that case and does NOT create.
    """
    from .models import MaicSessionV2

    user_tenant_id = getattr(user, "tenant_id", None)

    # Explicit query bypasses TenantManager so we can detect cross-tenant
    # mismatches by comparing tenant_ids ourselves (TenantManager would
    # silently filter out the foreign-tenant row).
    existing = (
        MaicSessionV2.objects
        .all_tenants()
        .filter(id=session_id)
        .select_related("tenant")
        .first()
    )

    if existing is not None:
        if existing.tenant_id != user_tenant_id:
            logger.warning(
                "MAIC v2 WS: cross-tenant session access attempt "
                "(session=%s session_tenant=%s user_tenant=%s user=%s)",
                session_id, existing.tenant_id, user_tenant_id, user.id,
            )
            return existing, True
        return existing, False

    # No row → create one bound to the user's tenant.
    from apps.tenants.models import Tenant
    tenant = Tenant.objects.filter(id=user_tenant_id).first()
    if tenant is None:
        # User has tenant_id pointing at a deleted/missing tenant — this is
        # a corrupt-state scenario, not a normal cross-tenant attempt.
        return None, True

    session = MaicSessionV2.objects.create(
        id=session_id,
        tenant=tenant,
        opened_by=user,
    )
    logger.info(
        "MAIC v2 WS: created ad-hoc session_id=%s tenant=%s user=%s",
        session_id, tenant.id, user.id,
    )
    return session, False


class ClassroomConsumer(AsyncJsonWebsocketConsumer):
    """WebSocket consumer for an AI Classroom session.

    Lifecycle:
      connect()      — auth check, tenant gate, session resolve/create
      receive_json() — dispatch on `action` field; streams from the
                       LangGraph director (MAIC-005)
      disconnect()   — log only (no group cleanup in Phase 1)
    """

    async def connect(self) -> None:
        self.user = self.scope.get("user", AnonymousUser())
        if self.user.is_anonymous:
            logger.warning("MAIC v2 WS: rejected anonymous connection")
            await self.close(code=4001)
            return

        self.session_id: str = self.scope["url_route"]["kwargs"]["session_id"]
        self.tenant_id = getattr(self.user, "tenant_id", None)

        if self.tenant_id is None:
            logger.warning(
                "MAIC v2 WS: user %s has no tenant_id; rejecting", self.user.id,
            )
            await self.close(code=4004)
            return

        # MAIC-101: resolve / create the MaicSessionV2 row + cross-tenant gate
        session, cross_tenant = await _resolve_or_create_session(
            self.session_id, self.user,
        )
        if cross_tenant:
            await self.close(code=4003)
            return
        self.session = session

        # Echo the JWT-bearing subprotocol — the WebSocket spec requires the
        # server to choose one of the client's offered subprotocols for the
        # handshake to succeed (same pattern as apps/notifications consumer).
        accepted_subprotocol = self.scope.get("accepted_subprotocol")
        await self.accept(subprotocol=accepted_subprotocol)

        logger.info(
            "MAIC v2 WS connect session=%s user=%s tenant=%s",
            self.session_id,
            self.user.id,
            self.tenant_id,
        )

    async def disconnect(self, close_code: int) -> None:
        logger.info(
            "MAIC v2 WS disconnect session=%s code=%d",
            getattr(self, "session_id", "<pre-accept>"),
            close_code,
        )

    async def receive_json(self, content: dict[str, Any], **kwargs) -> None:
        action = content.get("action")

        if action == "start":
            # MAIC-005: streams events from the LangGraph director.  The
            # graph's Phase-0 stub emits the same agent_start → text_delta
            # → agent_end triplet the placeholder did, so this swap is
            # invisible to clients.
            from .orchestration.director_graph import (
                build_initial_state,
                stream_classroom,
            )
            from apps.maic.exceptions import MaicGraphError

            data = content.get("data") or {}
            initial_state = build_initial_state(
                messages=data.get("messages"),
                available_agent_ids=data.get("agentIds"),
                max_turns=int(data.get("maxTurns", 1)),
            )
            try:
                async for event in stream_classroom(initial_state):
                    await self.send_json(event)
            except MaicGraphError as exc:
                logger.exception(
                    "MAIC v2 graph error session=%s",
                    getattr(self, "session_id", "?"),
                )
                await self.send_json({
                    "type": "error",
                    "data": {"message": str(exc)},
                })
            return

        # Unknown action — non-fatal; future-compat for client iterations
        logger.warning("MAIC v2 WS: unknown action=%r session=%s", action, getattr(self, "session_id", "?"))
        await self.send_json({
            "type": "error",
            "data": {"message": f"unknown action: {action!r}"},
        })
