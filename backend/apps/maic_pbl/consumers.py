"""WS chat consumer for the PBL subsystem (Phase 7, MAIC-704).

Wire format (mirrors apps.maic.consumers — same posture):

  client → {action: "chat", message: "@question what should I build first?"}
         → {action: "interrupt"}            (cancel an in-flight stream)

  server ← {type: "agent_start", data: {agentName, agentType}}
         ← {type: "text_delta",  data: {content}}        (streams)
         ← {type: "agent_end",   data: {agentName, complete: bool}}
         ← {type: "error",       data: {message}}

@mention routing:
  - "@question ..."  → Question agent for the active issue
  - "@judge ..."     → Judge agent for the active issue
  - bare text        → Question agent (default helper)

Issue-completion lifecycle:
  When a Judge reply contains the literal string "COMPLETE" (verdict
  protocol from agent_templates.py:get_judge_agent_prompt), the
  consumer marks the active issue done + auto-activates the next
  one. Frontend gets a fresh `agent_end{complete:true}` event so the
  workspace UI can advance.

Auth: same JWT-in-subprotocol pattern as ClassroomConsumer. Cross-
tenant access closes 4003.

Close codes:
  4001 — anonymous (no JWT)
  4003 — cross-tenant (session belongs to another tenant)
  4004 — session not found
  4040 — user has no tenant_id
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from typing import Any

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.contrib.auth.models import AnonymousUser
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)


_MENTION_RE = re.compile(r"@(question|judge)\b", re.IGNORECASE)


@database_sync_to_async
def _load_session(session_id: str, user) -> tuple[Any, int]:
    """Load + tenant-scope a MaicPBLSession.

    Returns (session, code) where code is:
      0    — OK
      4003 — cross-tenant (session exists for a different tenant)
      4004 — session not found
    """
    from apps.maic_pbl.models import MaicPBLSession

    user_tenant_id = getattr(user, "tenant_id", None)
    sess = (
        MaicPBLSession.objects
        .all_tenants()
        .filter(id=session_id)
        .first()
    )
    if sess is None:
        return None, 4004
    if sess.tenant_id != user_tenant_id:
        logger.warning(
            "PBL WS: cross-tenant access attempt session=%s session_tenant=%s user_tenant=%s user=%s",
            session_id, sess.tenant_id, user_tenant_id, getattr(user, "id", None),
        )
        return sess, 4003
    return sess, 0


@database_sync_to_async
def _persist_chat_turn(session_id: str, message: dict[str, Any]) -> None:
    """Append one chat message to MaicPBLSession.chat_messages.

    Re-reads the row to avoid clobbering concurrent writers (rare —
    PBL is single-owner per upstream model — but the read-modify-
    write is still cheap insurance)."""
    from apps.maic_pbl.models import MaicPBLSession

    sess = MaicPBLSession.objects.all_tenants().filter(id=session_id).first()
    if sess is None:
        return
    sess.chat_messages.append(message)
    sess.save(update_fields=["chat_messages", "updated_at"])


@database_sync_to_async
def _mark_issue_complete_and_advance(session_id: str) -> tuple[bool, str | None]:
    """Mark the current issue is_done + activate next; return
    (advanced, next_title) so the consumer can include the info in
    the agent_end frame."""
    from apps.maic_pbl.mcp import AgentMCP, IssueboardMCP
    from apps.maic_pbl.models import MaicPBLSession

    sess = MaicPBLSession.objects.all_tenants().filter(id=session_id).first()
    if sess is None:
        return False, None
    config = sess.project_config or {}
    if "issueboard" not in config:
        return False, None

    agent_mcp = AgentMCP(config)
    board = IssueboardMCP(config, agent_mcp)
    board.complete_current_issue()
    advance = board.activate_next_issue()

    next_title: str | None = None
    if advance.success:
        next_title = (advance.model_dump().get("message") or "").removeprefix(
            "Activated issue: "
        )

    sess.project_config = config
    if not advance.success:
        sess.status = MaicPBLSession.STATUS_COMPLETED
        sess.save(
            update_fields=["project_config", "status", "updated_at"],
        )
    else:
        sess.save(update_fields=["project_config", "updated_at"])
    return advance.success, next_title


def _resolve_target_agent(
    project_config: dict[str, Any], message: str,
) -> tuple[dict[str, Any] | None, str]:
    """Pick which agent should answer this user message.

    Returns (agent_dict, agent_type) where agent_type is "question"
    or "judge". Falls back to Question if no @mention is present.
    Returns (None, "") when the active issue has no resolved Q/J
    agent — caller emits an error frame.
    """
    issueboard = project_config.get("issueboard") or {}
    issues = issueboard.get("issues") or []
    active = next((i for i in issues if i.get("is_active")), None)
    if active is None:
        return None, ""

    match = _MENTION_RE.search(message or "")
    agent_type = (match.group(1).lower() if match else "question")
    name_field = (
        "judge_agent_name" if agent_type == "judge"
        else "question_agent_name"
    )
    target_name = active.get(name_field)
    if not target_name:
        return None, agent_type

    agent = next(
        (a for a in (project_config.get("agents") or []) if a["name"] == target_name),
        None,
    )
    return agent, agent_type


def _build_chat_system_prompt(
    agent: dict[str, Any],
    project_config: dict[str, Any],
    user_role: str,
    agent_type: str,
) -> str:
    """Assemble the per-message system prompt — agent's prompt +
    active-issue context + recent-message context. Mirrors upstream
    /api/pbl/chat/route.ts:42-62 byte-for-byte."""
    issueboard = project_config.get("issueboard") or {}
    active = next(
        (i for i in (issueboard.get("issues") or []) if i.get("is_active")),
        None,
    )
    recent_messages = (project_config.get("chat") or {}).get("messages") or []

    issue_context = ""
    if active is not None:
        issue_context = (
            f"\n\n## Current Issue"
            f"\nTitle: {active['title']}"
            f"\nDescription: {active['description']}"
            f"\nPerson in Charge: {active['person_in_charge']}"
        )
        gq = active.get("generated_questions") or ""
        if gq:
            label = (
                "Questions to Evaluate Against"
                if agent_type == "judge"
                else "Generated Questions"
            )
            issue_context += f"\n\n{label}:\n{gq}"

    recent_context = ""
    if recent_messages:
        formatted = "\n".join(
            f"{m['agent_name']}: {m['message']}"
            for m in recent_messages[-5:]
        )
        recent_context = f"\n\n## Recent Conversation\n{formatted}"

    role_section = f"\n\nThe student's role is: {user_role}" if user_role else ""

    return (
        agent["system_prompt"] + issue_context + recent_context + role_section
    )


class PBLChatConsumer(AsyncJsonWebsocketConsumer):
    """WS consumer for `/ws/maic/pbl/<session_id>/`.

    Lifecycle:
      connect     — auth, tenant gate, session resolve
      chat        — one student turn → one agent reply (streamed)
      interrupt   — cancel the in-flight LLM call
      disconnect  — cancel any in-flight task
    """

    async def connect(self) -> None:
        self.user = self.scope.get("user", AnonymousUser())
        if self.user.is_anonymous:
            logger.warning("PBL WS: rejected anonymous connection")
            await self.close(code=4001)
            return

        self.session_id: str = self.scope["url_route"]["kwargs"]["session_id"]
        self.tenant_id = getattr(self.user, "tenant_id", None)
        if self.tenant_id is None:
            logger.warning("PBL WS: user %s has no tenant_id", self.user.id)
            await self.close(code=4040)
            return

        sess, code = await _load_session(self.session_id, self.user)
        if code != 0:
            await self.close(code=code)
            return
        self.session = sess

        self._chat_task: asyncio.Task[None] | None = None
        self._writer_alive = True

        accepted_subprotocol = self.scope.get("accepted_subprotocol")
        await self.accept(subprotocol=accepted_subprotocol)

        logger.info(
            "PBL WS connect session=%s user=%s tenant=%s",
            self.session_id, self.user.id, self.tenant_id,
        )

    async def disconnect(self, close_code: int) -> None:
        self._writer_alive = False
        await self._cancel_in_flight()

    async def _safe_send_json(self, payload: dict[str, Any]) -> None:
        if not self._writer_alive:
            return
        try:
            await self.send_json(payload)
        except Exception:  # noqa: BLE001
            self._writer_alive = False

    async def _cancel_in_flight(self) -> None:
        task = getattr(self, "_chat_task", None)
        if task is None or task.done():
            return
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass

    async def receive_json(self, content: dict[str, Any], **kwargs) -> None:
        action = content.get("action")
        if action == "chat":
            data = content.get("data") or {}
            message = (data.get("message") or "").strip()
            if not message:
                await self._safe_send_json({
                    "type": "error",
                    "data": {"message": "chat requires non-empty data.message"},
                })
                return
            user_role = data.get("userRole") or ""
            language_model_id = data.get("languageModelId", "stub")
            await self._cancel_in_flight()
            self._chat_task = asyncio.create_task(
                self._run_chat_turn(message, user_role, language_model_id),
            )
            return

        if action == "interrupt":
            await self._cancel_in_flight()
            return

        logger.warning("PBL WS: unknown action=%r session=%s", action, self.session_id)
        await self._safe_send_json({
            "type": "error",
            "data": {"message": f"unknown action: {action!r}"},
        })

    async def _run_chat_turn(
        self, message: str, user_role: str, language_model_id: str,
    ) -> None:
        """Run one chat turn: pick agent, stream LLM, persist."""
        # Re-load the session so any persisted issueboard mutations
        # from prior turns (issue completed, next activated) are
        # visible. Cheap and avoids stale-state bugs.
        sess, code = await _load_session(self.session_id, self.user)
        if code != 0 or sess is None:
            await self._safe_send_json({
                "type": "error",
                "data": {"message": "session unavailable"},
            })
            return
        config = sess.project_config or {}

        agent, agent_type = _resolve_target_agent(config, message)
        if agent is None:
            await self._safe_send_json({
                "type": "error",
                "data": {"message": "no active issue or target agent"},
            })
            return

        if language_model_id == "stub":
            await self._safe_send_json({
                "type": "error",
                "data": {"message": "languageModelId 'stub' is for tests; pick a real provider"},
            })
            return

        try:
            from apps.maic.exceptions import MaicConfigError
            from apps.maic.orchestration.ai_adapter import resolve_chat_model
            try:
                model = resolve_chat_model(language_model_id)
            except MaicConfigError as exc:
                await self._safe_send_json({
                    "type": "error",
                    "data": {"message": f"model resolve failed: {exc}"},
                })
                return

            system_prompt = _build_chat_system_prompt(
                agent, config, user_role, agent_type,
            )

            # Persist the user's message immediately so a refresh during
            # streaming doesn't lose the turn.
            user_msg = {
                "id": f"msg_{uuid.uuid4().hex[:8]}",
                "agent_name": "user",
                "message": message,
                "timestamp": time.time(),
                "read_by": [],
            }
            await _persist_chat_turn(self.session_id, user_msg)

            await self._safe_send_json({
                "type": "agent_start",
                "data": {
                    "agentName": agent["name"],
                    "agentType": agent_type,
                },
            })

            collected: list[str] = []
            try:
                async for chunk in model.astream([
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=message),
                ]):
                    text = chunk.content if isinstance(chunk.content, str) else str(chunk.content)
                    if text:
                        collected.append(text)
                        await self._safe_send_json({
                            "type": "text_delta",
                            "data": {"content": text},
                        })
            except Exception as exc:  # noqa: BLE001 — model is IO boundary
                logger.warning("PBL WS chat: model.astream failed: %s", exc)
                await self._safe_send_json({
                    "type": "error",
                    "data": {"message": f"model error: {exc}"},
                })
                return

            full_text = "".join(collected)
            agent_msg = {
                "id": f"msg_{uuid.uuid4().hex[:8]}",
                "agent_name": agent["name"],
                "message": full_text,
                "timestamp": time.time(),
                "read_by": [],
            }
            await _persist_chat_turn(self.session_id, agent_msg)

            complete = False
            advanced_to: str | None = None
            if agent_type == "judge" and "COMPLETE" in full_text.upper():
                complete = True
                _advanced, advanced_to = await _mark_issue_complete_and_advance(
                    self.session_id,
                )

            await self._safe_send_json({
                "type": "agent_end",
                "data": {
                    "agentName": agent["name"],
                    "complete": complete,
                    "advancedTo": advanced_to,
                },
            })
        except asyncio.CancelledError:
            # Interrupt is a normal flow; don't surface as error.
            raise
        except Exception as exc:  # noqa: BLE001 — final safety net
            logger.exception("PBL WS chat: unexpected error session=%s", self.session_id)
            await self._safe_send_json({
                "type": "error",
                "data": {"message": f"chat failed: {exc}"},
            })
