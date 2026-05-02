"""Phase-0 stub of the LangGraph director graph.

Source: https://github.com/THU-MAIC/OpenMAIC/blob/main/lib/orchestration/director-graph.ts
        /Volumes/CrucialX9/OpenMAIC/lib/orchestration/director-graph.ts (547 lines)

Topology (frozen — changes require an ADR):

    START ──→ director ──end──→ END
                  │
                  └──next──→ agent_generate ──→ director  (loop)

Phase-0 node bodies are STUBS. They emit a hardcoded StatelessEvent
triplet so the WS pipe can be exercised end-to-end before the real
multi-agent logic lands. Real bodies in:
  - directorNode body  → MAIC-103 (single-agent), MAIC-104 (multi-agent)
  - agentGenerate body → MAIC-105

Streaming contract: nodes accept `writer: StreamWriter` (auto-injected
by LangGraph 1.1.10 via signature inspection). Calling `writer(event)`
delivers the event to the caller through `astream(stream_mode="custom")`.

CRITICAL — do NOT switch to `config.get("writer")`. That pattern returns
None in langgraph 1.1.10 and silently drops events; verified empirically
in MAIC-001 self-cert (READINESS-AUDIT §Issue-6).
"""
from __future__ import annotations

import logging
from typing import Any, AsyncIterator, Final

from langgraph.graph import StateGraph, START, END
from langgraph.pregel import Pregel
from langgraph.types import StreamWriter

from apps.maic.exceptions import MaicGraphError, MaicProtocolError
from .state import OrchestratorState

logger = logging.getLogger(__name__)

# ── Wire-format constants — keep in sync with upstream lib/types/chat.ts ──
_VALID_EVENT_TYPES: Final[frozenset[str]] = frozenset({
    "agent_start", "text_delta", "action", "agent_end",
    "thinking", "cue_user", "speech_audio", "error",
})

# Phase-0 hardcoded message ID — used by both the consumer's start branch
# (apps/maic/consumers.py uses the same value when not yet wired to the
# graph) and the agent_generate stub here. Keeping a single value makes
# the regression tests survive the consumer→graph swap unchanged.
_PHASE0_MESSAGE_ID: Final[str] = "phase0-stub"


# ── Helpers ────────────────────────────────────────────────────────────


def _validate_event(event: dict[str, Any]) -> None:
    """Cheap structural check. Raises MaicProtocolError on violation.

    Mirrors upstream's TypeScript discriminated-union enforcement at the
    runtime boundary. We can't get TS-level safety in Python, so we get
    the next best thing: explicit type-tag validation at emission time.
    """
    if not isinstance(event, dict):
        raise MaicProtocolError(f"event must be dict, got {type(event).__name__}")
    t = event.get("type")
    if t not in _VALID_EVENT_TYPES:
        raise MaicProtocolError(
            f"unknown event type {t!r}; valid: {sorted(_VALID_EVENT_TYPES)}"
        )
    if "data" not in event:
        raise MaicProtocolError(f"event {t!r} missing required 'data' key")


def _make_safe_writer(raw_writer: StreamWriter | None) -> StreamWriter:
    """Wrap StreamWriter with try/except + protocol validation.

    Port of upstream lib/orchestration/director-graph.ts:104-111:

        const write = (chunk) => {
          try { rawWrite(chunk); }
          catch { /* controller closed after abort */ }
        };

    We additionally validate the event shape; production drops invalid
    frames with logger.error rather than crashing the node, because a
    single bad frame should not abort an in-flight classroom session.

    `raw_writer is None` only happens in unit-test contexts where the
    node is invoked directly outside `astream(stream_mode='custom')`.
    Production LangGraph always injects a non-None StreamWriter.
    """
    def write(event: dict[str, Any]) -> None:
        try:
            _validate_event(event)
        except MaicProtocolError:
            logger.error("dropping invalid event", extra={"event": event}, exc_info=True)
            return
        if raw_writer is None:
            logger.warning(
                "no writer injected — event dropped",
                extra={"event_type": event.get("type")},
            )
            return
        try:
            raw_writer(event)
        except Exception:  # noqa: BLE001 — mirrors upstream's swallow-on-controller-closed
            logger.debug(
                "writer raised; controller likely closed after abort",
                exc_info=True,
            )
    return write


# ── Nodes ─────────────────────────────────────────────────────────────


async def _director_node(
    state: OrchestratorState,
    writer: StreamWriter,
) -> dict[str, Any]:
    """Director — chooses which agent speaks next.

    Phase-1 single-agent path (this ticket, MAIC-103). Mirrors upstream
    director-graph.ts:120-135:

      - turn 0: dispatch the single available agent (or 'default-1' if
        none provided). Emit `thinking{stage:"agent_loading", agentId}`
        so the client can show a loading state for the right avatar.
      - turn 1+: that agent has now responded. Emit a `cue_user` event
        so the frontend playback engine knows to enter live mode for
        a follow-up question, then end the graph.
      - turnCount >= maxTurns at any time: ends without emitting (the
        loop is exhausted; no UX signal needed). Mirrors
        director-graph.ts:114-118.

    Multi-agent (LLM-based decision) lands in Phase 3, MAIC-104.
    """
    write = _make_safe_writer(writer)
    turn = state.get("turnCount", 0)
    max_turns = state.get("maxTurns", 1)

    # Turn-limit check (applies to single + multi)
    if turn >= max_turns:
        logger.info(
            "director: turn limit reached (%d/%d), ending",
            turn, max_turns,
        )
        return {"shouldEnd": True}

    # Single-agent dispatch
    available = state.get("availableAgentIds") or []
    agent_id = available[0] if available else "default-1"

    if turn == 0:
        logger.info("director: dispatching single agent %r", agent_id)
        write({"type": "thinking", "data": {
            "stage": "agent_loading",
            "agentId": agent_id,
        }})
        return {"currentAgentId": agent_id, "shouldEnd": False}

    # Agent already responded — cue user for follow-up, then end
    logger.info("director: cueing user after %r", agent_id)
    write({"type": "cue_user", "data": {"fromAgentId": agent_id}})
    return {"shouldEnd": True}


def _director_condition(state: OrchestratorState) -> str:
    """LangGraph conditional-edge router. Returns a string key matched
    in add_conditional_edges. The string MUST be one of the keys in the
    routing map; LangGraph raises if not.
    """
    return END if state.get("shouldEnd") else "agent_generate"


async def _agent_generate_node(
    state: OrchestratorState,
    writer: StreamWriter,
) -> dict[str, Any]:
    """Phase-0 stub. Real body in MAIC-105.

    Emits a StatelessEvent triplet (agent_start → text_delta → agent_end)
    through the injected writer. Increments turnCount so the next director
    call ends the loop.
    """
    write = _make_safe_writer(writer)

    write({
        "type": "agent_start",
        "data": {
            "messageId": _PHASE0_MESSAGE_ID,
            "agentId": _PHASE0_MESSAGE_ID,
            "agentName": "MAIC v2 (Phase 0 stub)",
            "agentAvatar": None,
            "agentColor": "#5b9bd5",
        },
    })
    write({
        "type": "text_delta",
        "data": {
            "content": "Phase 0 graph wired. Real agents in Phase 1.",
            "messageId": _PHASE0_MESSAGE_ID,
        },
    })
    write({
        "type": "agent_end",
        "data": {"messageId": _PHASE0_MESSAGE_ID, "agentId": _PHASE0_MESSAGE_ID},
    })

    return {
        "turnCount": state.get("turnCount", 0) + 1,
        "currentAgentId": None,
    }


# ── Public API ─────────────────────────────────────────────────────────


def create_orchestration_graph() -> Pregel:
    """Mirror of upstream createOrchestrationGraph at director-graph.ts:482-494.

    No checkpointer in Phase 0; Phase 7 (PBL) may add a Postgres saver
    for session resumption.
    """
    graph = StateGraph(OrchestratorState)
    graph.add_node("director", _director_node)
    graph.add_node("agent_generate", _agent_generate_node)
    graph.add_edge(START, "director")
    graph.add_conditional_edges(
        "director",
        _director_condition,
        {"agent_generate": "agent_generate", END: END},
    )
    graph.add_edge("agent_generate", "director")
    return graph.compile()


def build_initial_state(
    *,
    messages: list[dict[str, Any]] | None = None,
    available_agent_ids: list[str] | None = None,
    max_turns: int = 1,
) -> OrchestratorState:
    """Mirror of upstream buildInitialState at director-graph.ts:500-547.

    Distinction in `available_agent_ids` semantics:
      - `None`  → caller didn't specify; we fill in [_PHASE0_MESSAGE_ID]
        as a development convenience (zero-config probe page works).
      - `[]`    → caller explicitly specified no agents; preserve the
        empty list. The director then applies its `'default-1'` fallback
        rule from upstream director-graph.ts:122 — never overwrite
        caller intent here.
    """
    if available_agent_ids is None:
        available_agent_ids = [_PHASE0_MESSAGE_ID]

    return {
        "messages": messages or [],
        "storeState": {"currentSceneId": None, "scenes": [], "whiteboardOpen": False},
        "availableAgentIds": available_agent_ids,
        "maxTurns": max_turns,
        "languageModelId": "stub",
        "thinkingConfig": None,
        "discussionContext": None,
        "triggerAgentId": None,
        "userProfile": None,
        "agentConfigOverrides": {},
        "currentAgentId": None,
        "turnCount": 0,
        "shouldEnd": False,
        "totalActions": 0,
        "agentResponses": [],
        "whiteboardLedger": [],
    }


async def stream_classroom(
    initial_state: OrchestratorState,
) -> AsyncIterator[dict[str, Any]]:
    """Run the graph and yield StatelessEvent dicts.

    The WS consumer (apps/maic/consumers.py) is the only intended
    caller. Hides stream_mode and writer plumbing.

    Raises:
        MaicGraphError — wraps any exception raised by LangGraph itself.
    """
    graph = create_orchestration_graph()
    try:
        async for chunk in graph.astream(initial_state, stream_mode="custom"):
            yield chunk
    except Exception as exc:  # noqa: BLE001 — re-raised wrapped
        logger.exception("classroom stream errored")
        raise MaicGraphError(str(exc)) from exc
