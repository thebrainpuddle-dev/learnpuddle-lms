"""WebSocket consumers for MAIC v2 — see docs/AI_CLASSROOM_BLUEPRINT.md §3.2.

Wire format (matches OpenMAIC StatelessEvent — `lib/types/chat.ts`):

  ← from server: {"type": "agent_start" | "text_delta" | "action" |
                          "agent_end" | "thinking" | "cue_user" |
                          "speech_audio" | "error",
                  "data": {...}}
  → to server:   {"action": "start" | "interrupt" | "resume" | "stop"
                          | "user_message",
                  "data": {...}}

Auth: JWT in `Sec-WebSocket-Protocol: Bearer.<jwt>` subprotocol, parsed
by `apps/notifications/middleware.py::JWTAuthMiddleware` (already in the
global Channels middleware chain via `config/asgi.py`).

Close codes:
  4001 — anonymous (no JWT or invalid JWT)
  4003 — authenticated but session_id belongs to a different tenant
         (cross-tenant access attempt)
  4004 — authenticated user has no tenant_id (system error / corrupt user)
  4403 — MAIC v2 disabled globally or for this tenant

Tenant binding (MAIC-101):
  On connect we look up MaicSessionV2 by session_id. If the row exists
  and tenant_id matches the user's tenant, accept. If the row exists
  with a DIFFERENT tenant, close 4003. If the row does NOT exist, we
  create it on the fly bound to the user's tenant — Phase 1 lets the
  WS open ad-hoc so the dev probe and future "join this classroom by
  link" flows work without an explicit HTTP-create step. MAIC-301 will
  add the explicit POST /api/maic/v2/sessions/ route for the regular
  flow; both write the same `maic_session_v2` row.

Session-state container (MAIC-110.3):
  Each connection holds two pieces of mutable state:
    * `_classroom_task` — the in-flight asyncio.Task running the
      LangGraph stream, or None when no stream is active.
    * `_state` — the OrchestratorState the stream was started with.
      Phase 3's interrupt/resume/user_message handlers reuse this
      state on resume so the conversation context survives an
      interrupt without round-tripping through the client.

  A `_writer_alive` flag is set to False when the connection closes
  or a stream is cancelled mid-frame; the streaming helper checks it
  before every send_json so an interrupt landing between two frames
  doesn't blow up on a dead transport. (MAIC-110.4 is the first
  consumer of the writer-guard pattern — 110.3 just establishes it.)
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth.models import AnonymousUser

logger = logging.getLogger(__name__)

_DEFAULT_MAX_TURNS = 1
_MAX_MAX_TURNS = 12


def _coerce_max_turns(raw: Any) -> int:
    """Parse client maxTurns with a hard cost-control ceiling."""
    if raw is None:
        return _DEFAULT_MAX_TURNS
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("maxTurns must be an integer") from exc
    if value < 1:
        raise ValueError("maxTurns must be at least 1")
    return min(value, _MAX_MAX_TURNS)


@database_sync_to_async
def _user_has_maic_v2_access(user) -> bool:
    """Run the shared MAIC v2 gate in a DB-safe sync context."""
    from apps.maic.permissions import user_has_maic_v2_access

    return user_has_maic_v2_access(user)


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


@database_sync_to_async
def _resolve_tts_config_for_tenant(tenant_id) -> dict | None:
    """Load and decrypt TenantAIConfig.resolve_tts_config() for one tenant.

    MAIC-502: called once at WS `start` action so the orchestration loop
    runs without sync DB hits.

    Returns None when:
      - `tenant_id` is None (probe / unauthenticated path)
      - no `TenantAIConfig` row exists for the tenant
      - the DB itself is unreachable (`OperationalError` / `InterfaceError`)

    Other exceptions — Fernet decrypt failures from a rotated
    SECRET_KEY, schema drift, code bugs — propagate. Production
    deployments should see real config errors loudly so an admin can
    fix them, not silently fall back to edge_tts and ship the wrong
    voice to every classroom.

    Tests that exercise the WS consumer without a Django test DB should
    monkeypatch this helper directly (see tests_consumers.py
    `mock_tts_resolver` fixture) rather than rely on broad swallowing.
    """
    if tenant_id is None:
        return None
    from django.db.utils import DatabaseError, InterfaceError, OperationalError

    try:
        from apps.courses.maic_models import TenantAIConfig

        manager = TenantAIConfig.objects
        qs = (
            manager.all_tenants() if hasattr(manager, "all_tenants") else manager
        ).filter(tenant_id=tenant_id)
        cfg = qs.first()
        if cfg is None:
            return None
        return cfg.resolve_tts_config()
    except (OperationalError, InterfaceError, DatabaseError) as exc:
        # DB outage / connection refused / network blip — degrade to
        # edge_tts so audio still plays. Real config bugs (Fernet,
        # schema, code) are NOT swallowed; they propagate.
        logger.warning(
            "MAIC v2 WS: DB error resolving TTS config for tenant=%s: %s; "
            "falling back to edge",
            tenant_id, exc,
        )
        return None


@database_sync_to_async
def _resolve_llm_config_for_tenant(tenant_id) -> dict:
    from apps.maic.llm_config import resolve_tenant_llm_runtime_config

    return resolve_tenant_llm_runtime_config(tenant_id=tenant_id)


class ClassroomConsumer(AsyncJsonWebsocketConsumer):
    """WebSocket consumer for an AI Classroom session.

    Lifecycle:
      connect()      — auth check, tenant gate, session resolve/create
      receive_json() — dispatch on `action` field:
                         start      → spawn classroom stream (MAIC-005, 110.3)
                         interrupt  → cancel in-flight stream, keep
                                      connection alive (110.4)
                         stop       → cancel + emit cue_user ack (110.4)
                         resume     → restart from saved state (110.5)
                         user_message → append + resume (110.5)
      disconnect()   — cancel any in-flight task, mark writer dead.
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

        if not await _user_has_maic_v2_access(self.user):
            logger.warning(
                "MAIC v2 WS: user %s tenant=%s failed v2 access gate",
                self.user.id,
                self.tenant_id,
            )
            await self.close(code=4403)
            return

        # MAIC-101: resolve / create the MaicSessionV2 row + cross-tenant gate
        session, cross_tenant = await _resolve_or_create_session(
            self.session_id, self.user,
        )
        if cross_tenant:
            await self.close(code=4003)
            return
        self.session = session

        # MAIC-110.3: per-connection session-state container.
        self._classroom_task: asyncio.Task[None] | None = None
        self._state: dict[str, Any] | None = None
        self._writer_alive: bool = True

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
        # Mark the writer dead BEFORE cancelling — the streaming helper
        # checks this flag between frames so a cancel landing mid-frame
        # doesn't try to send on a dead transport.
        self._writer_alive = False

        task = getattr(self, "_classroom_task", None)
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                # Best-effort cleanup — the connection is already closing.
                pass

        logger.info(
            "MAIC v2 WS disconnect session=%s code=%d",
            getattr(self, "session_id", "<pre-accept>"),
            close_code,
        )

    # ── Internal helpers ───────────────────────────────────────────────

    async def _safe_send_json(self, payload: dict[str, Any]) -> bool:
        """Send a frame iff the writer is still alive.

        Returns True on success, False if the writer was already marked
        dead or if the underlying send raised. Callers that need to
        bail out of a streaming loop check the return value.
        """
        if not self._writer_alive:
            return False
        try:
            await self.send_json(payload)
            return True
        except Exception:  # noqa: BLE001 — transport gone, mark dead
            self._writer_alive = False
            return False

    async def _run_classroom_stream(self, initial_state: dict[str, Any]) -> None:
        """Drain the LangGraph stream into the WS, frame-by-frame.

        Cancellation safety: every frame send is gated by
        `_writer_alive`, so a `task.cancel()` between two frames simply
        returns `False` from the next `_safe_send_json` and the loop
        unwinds via `CancelledError` on the next `await`.
        """
        from apps.maic.exceptions import MaicGraphError
        from .orchestration.director_graph import stream_classroom

        try:
            async for event in stream_classroom(initial_state):
                if not self._writer_alive:
                    return
                await self._safe_send_json(event)
        except asyncio.CancelledError:
            # Caller (interrupt/disconnect) explicitly cancelled — just
            # propagate. The director graph's own task cleanup is
            # handled by langgraph internally.
            raise
        except MaicGraphError as exc:
            logger.exception(
                "MAIC v2 graph error session=%s",
                getattr(self, "session_id", "?"),
            )
            await self._safe_send_json({
                "type": "error",
                "data": {"message": str(exc)},
            })
        except Exception as exc:  # noqa: BLE001 — surface as wire-error frame
            logger.exception(
                "MAIC v2 stream errored session=%s",
                getattr(self, "session_id", "?"),
            )
            await self._safe_send_json({
                "type": "error",
                "data": {"message": str(exc)},
            })

    async def _cancel_in_flight(self) -> None:
        """Cancel any running classroom task and await its teardown.

        Idempotent: safe to call when no task is running. Used by both
        `disconnect()` and (in MAIC-110.4) the `interrupt`/`stop`
        handlers — both need the same race-safe shutdown sequence.
        """
        task = getattr(self, "_classroom_task", None)
        if task is None or task.done():
            return
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass

    # ── Inbound dispatch ───────────────────────────────────────────────

    async def receive_json(self, content: dict[str, Any], **kwargs) -> None:
        action = content.get("action")

        if action == "start":
            # MAIC-005: streams events from the LangGraph director.
            # MAIC-110.3: the stream now runs as a tracked asyncio.Task
            # so future handlers (interrupt/stop/user_message —
            # MAIC-110.4/.5) can cancel and resume it.
            from .orchestration.director_graph import build_initial_state

            # Defensive: a fresh `start` with a stream still running is
            # a client bug, but we'd rather cancel cleanly than spawn
            # parallel streams on the same connection.
            await self._cancel_in_flight()

            data = content.get("data") or {}
            # Pre-resolve per-tenant model + TTS config once per session
            # start so the async orchestration loop doesn't do sync DB
            # calls. Missing/disabled LLM config is a hard product error:
            # a production classroom must not silently fall back to stub.
            try:
                llm_config = await _resolve_llm_config_for_tenant(
                    self.tenant_id
                )
                language_model_id = str(llm_config["language_model_id"])
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "MAIC v2 WS: failed resolving LLM config for tenant=%s: %s",
                    self.tenant_id,
                    exc,
                )
                await self._safe_send_json({
                    "type": "error",
                    "data": {"message": str(exc)},
                })
                return

            # MAIC-502: TTS remains soft-fallback so audio still plays
            # when only voice config is missing.
            tts_config = await _resolve_tts_config_for_tenant(self.tenant_id)
            try:
                max_turns = _coerce_max_turns(data.get("maxTurns"))
            except ValueError as exc:
                await self._safe_send_json({
                    "type": "error",
                    "data": {"message": str(exc)},
                })
                return
            initial_state = build_initial_state(
                messages=data.get("messages"),
                available_agent_ids=data.get("agentIds"),
                max_turns=max_turns,
                language_model_id=language_model_id,
                llm_config=llm_config,
                tts_config=tts_config,
            )
            self._state = initial_state
            self._classroom_task = asyncio.create_task(
                self._run_classroom_stream(initial_state)
            )
            return

        if action == "interrupt":
            # MAIC-110.4: cancel the in-flight stream but keep the
            # connection open. The client follows up with
            # `user_message` (110.5) or `resume` (110.5) to continue.
            # We deliberately do NOT send a terminal frame — the next
            # action's first frame is the right "I heard you" signal.
            await self._cancel_in_flight()
            return

        if action == "stop":
            # MAIC-110.4: terminal — cancel the stream and emit a
            # `cue_user` ack so the client knows control has been
            # returned to the user. The connection stays open; it's
            # the client's choice whether to disconnect or start a
            # fresh classroom.
            await self._cancel_in_flight()
            await self._safe_send_json({
                "type": "cue_user",
                "data": {"reason": "stopped_by_user"},
            })
            return

        if action == "user_message":
            # MAIC-110.5: append the user's reply to state.messages and
            # restart the LangGraph stream with a small live-mode
            # budget. Used after `interrupt` to enter the live-mode
            # discussion loop. Client flow:
            #   start → ... → interrupt → user_message → ... → resume
            data = content.get("data") or {}
            text = (data.get("text") or "").strip()
            if not text:
                await self._safe_send_json({
                    "type": "error",
                    "data": {"message": "user_message requires non-empty data.text"},
                })
                return
            if self._state is None:
                await self._safe_send_json({
                    "type": "error",
                    "data": {"message": "user_message requires a prior start"},
                })
                return

            # Defensive: cancel any stream still running (e.g. client
            # forgot to interrupt first). Cleanly tears down before we
            # mutate the shared state.
            await self._cancel_in_flight()

            self._state.setdefault("messages", []).append({
                "role": "user",
                "content": text,
            })
            # Reset director scaffolding so the next graph run treats
            # this as a fresh routing decision, but preserve all the
            # accumulated history (agentResponses + whiteboardLedger
            # are reducer-merged lists — never blow them away).
            self._state["currentAgentId"] = None
            self._state["turnCount"] = 0
            self._state["shouldEnd"] = False
            # Live-mode budget: small by default (2 turns ≈ one
            # round-trip), overridable per request.
            self._state["maxTurns"] = int(data.get("maxTurns", 2))

            self._classroom_task = asyncio.create_task(
                self._run_classroom_stream(self._state)
            )
            return

        if action == "widget_event":
            # MAIC-603: an interactive widget iframe emitted an event
            # (student dragged a slider, clicked an answer, completed
            # a step). Buffer it onto state.pendingWidgetEvents so the
            # next director-turn entry can read + drain. Phase 7's PBL
            # agentic loop is the primary consumer.
            #
            # Defensive: drop silently if no `start` has run yet — a
            # widget can't have been mounted without an active stream.
            if self._state is None:
                logger.warning(
                    "MAIC v2 WS: widget_event before start session=%s",
                    self.session_id,
                )
                return

            data = content.get("data") or {}
            scene_id = (data.get("sceneId") or "").strip()
            event_name = (data.get("event") or "").strip()
            if not scene_id or not event_name:
                await self._safe_send_json({
                    "type": "error",
                    "data": {"message": "widget_event requires data.sceneId and data.event"},
                })
                return

            from datetime import datetime, timezone
            buffered = {
                "sceneId": scene_id,
                "widgetId": data.get("widgetId"),
                "event": event_name,
                "payload": data.get("payload") or {},
                "receivedAt": datetime.now(timezone.utc).isoformat(),
            }
            # Append, not extend — pendingWidgetEvents is a reducer
            # field on the state TypedDict but inside the consumer we
            # mutate it directly because we're outside the LangGraph
            # node boundary. The next director-turn entry will pick
            # this up when the graph resumes.
            self._state.setdefault("pendingWidgetEvents", []).append(buffered)
            logger.info(
                "MAIC v2 WS widget_event session=%s scene=%s event=%s",
                self.session_id, scene_id, event_name,
            )
            return

        if action == "resume":
            # MAIC-110.5: restart the stream from the saved state
            # without appending a user message. Useful for "continue
            # the lecture from where you stopped" UX.
            if self._state is None:
                await self._safe_send_json({
                    "type": "error",
                    "data": {"message": "resume requires a prior start"},
                })
                return

            await self._cancel_in_flight()

            data = content.get("data") or {}
            self._state["currentAgentId"] = None
            self._state["turnCount"] = 0
            self._state["shouldEnd"] = False
            # Caller can override maxTurns; otherwise reuse the
            # last-known budget so a long lecture can keep going.
            if "maxTurns" in data:
                self._state["maxTurns"] = int(data["maxTurns"])

            self._classroom_task = asyncio.create_task(
                self._run_classroom_stream(self._state)
            )
            return

        # Unknown action — non-fatal; future-compat for client iterations.
        logger.warning(
            "MAIC v2 WS: unknown action=%r session=%s",
            action,
            getattr(self, "session_id", "?"),
        )
        await self._safe_send_json({
            "type": "error",
            "data": {"message": f"unknown action: {action!r}"},
        })
