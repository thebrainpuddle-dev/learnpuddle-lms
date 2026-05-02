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
global Channels middleware chain via `config/asgi.py`). Anonymous
connections close with code 4001 — exact pattern mirrored from
`apps/notifications/consumers.py:46-50`.

Phase 0: emits a hardcoded StatelessEvent triplet on receipt of
`{"action":"start"}`. Real LangGraph integration arrives in MAIC-005
(replaces the `if action == "start"` body with `async for event in
stream_classroom(initial_state): await self.send_json(event)`).
"""
from __future__ import annotations

import logging
from typing import Any

from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth.models import AnonymousUser

logger = logging.getLogger(__name__)

# Phase-0 hardcoded message id — also used by MAIC-005's StateGraph stub.
# Keeping the value identical so the regression test for this consumer
# survives the MAIC-005 implementation swap unchanged.
_PHASE0_MESSAGE_ID = "phase0-stub"


class ClassroomConsumer(AsyncJsonWebsocketConsumer):
    """WebSocket consumer for an AI Classroom session.

    Lifecycle:
      connect()      — auth check, accept with echoed subprotocol
      receive_json() — dispatch on `action` field; Phase-0 emits stub frames
      disconnect()   — log only (no group cleanup needed in Phase 0)
    """

    async def connect(self) -> None:
        self.user = self.scope.get("user", AnonymousUser())
        if self.user.is_anonymous:
            logger.warning("MAIC v2 WS: rejected anonymous connection")
            await self.close(code=4001)
            return

        self.session_id: str = self.scope["url_route"]["kwargs"]["session_id"]
        self.tenant_id = getattr(self.user, "tenant_id", None)

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
            # Phase-0 stub. MAIC-005 replaces this branch with:
            #   from .orchestration.director_graph import stream_classroom, build_initial_state
            #   async for evt in stream_classroom(build_initial_state(...)):
            #       await self.send_json(evt)
            await self.send_json({
                "type": "agent_start",
                "data": {
                    "messageId": _PHASE0_MESSAGE_ID,
                    "agentId": _PHASE0_MESSAGE_ID,
                    "agentName": "MAIC v2 (Phase 0 stub)",
                    "agentAvatar": None,
                    "agentColor": "#5b9bd5",
                },
            })
            await self.send_json({
                "type": "text_delta",
                "data": {
                    "content": "Phase 0 WS wired. Real graph in MAIC-005.",
                    "messageId": _PHASE0_MESSAGE_ID,
                },
            })
            await self.send_json({
                "type": "agent_end",
                "data": {
                    "messageId": _PHASE0_MESSAGE_ID,
                    "agentId": _PHASE0_MESSAGE_ID,
                },
            })
            return

        # Unknown action — non-fatal; future-compat for client iterations
        logger.warning("MAIC v2 WS: unknown action=%r session=%s", action, getattr(self, "session_id", "?"))
        await self.send_json({
            "type": "error",
            "data": {"message": f"unknown action: {action!r}"},
        })
