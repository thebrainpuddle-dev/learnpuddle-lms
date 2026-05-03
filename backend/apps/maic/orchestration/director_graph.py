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

# Director LLM decision (MAIC-104.1). Imported at module top so tests
# can patch the symbol cleanly; the build_director_prompt + stream_text
# are real, no fakes per CLAUDE.md "Hard rule".
from apps.maic.orchestration.director_prompt import (
    DirectorDecision,
    build_director_prompt,
    parse_director_decision,
)

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


# ── LLM-based director decision (MAIC-104.1) ──────────────────────────


async def _director_llm_decide(state: OrchestratorState) -> DirectorDecision:
    """Ask the LLM which agent should speak next.

    Mirrors upstream lib/orchestration/director-graph.ts:153-225 — the
    "director chooses next agent" path. Builds a director prompt from
    state, streams the LLM response, parses the JSON decision.

    On any provider failure or parse failure we return a deterministic
    round-robin fallback (next in `availableAgentIds` after the most
    recent agent in `agentResponses`). This keeps the loop alive even
    when the LLM is misbehaving — the director_node caller can always
    rely on getting a valid decision back.
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    from apps.maic.orchestration.ai_adapter import stream_text
    from apps.maic.orchestration.registry import resolve_agent

    overrides = state.get("agentConfigOverrides") or {}
    available_ids = state.get("availableAgentIds") or []
    agents = []
    for agent_id in available_ids:
        agent = resolve_agent(agent_id, overrides)
        if agent is not None:
            agents.append(agent)

    if not agents:
        # No agents to pick from — end the round
        logger.warning("director_llm_decide: no resolvable agents in availableAgentIds")
        return DirectorDecision(next_agent_id=None, should_end=True)

    store_state = state.get("storeState") or {}
    whiteboard_open = bool(store_state.get("whiteboardOpen", False))

    try:
        system_prompt = build_director_prompt(
            agents=agents,
            conversation_summary=_build_conversation_summary(state),
            agent_responses=state.get("agentResponses") or [],
            turn_count=state.get("turnCount", 0),
            discussion_context=state.get("discussionContext"),
            trigger_agent_id=state.get("triggerAgentId"),
            whiteboard_ledger=state.get("whiteboardLedger"),
            user_profile=state.get("userProfile"),
            whiteboard_open=whiteboard_open,
        )
    except Exception:  # noqa: BLE001 — re-raised as fallback below
        logger.exception("director_llm_decide: prompt build failed; falling back")
        return _round_robin_fallback(state)

    # Build LLM messages: system prompt + a tight user message asking
    # for the JSON decision. Upstream uses a single HumanMessage prompt
    # ("Choose the next agent.") at lib/orchestration/director-graph.ts:188.
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=(
            "Based on the rules above, decide who should speak next.\n"
            'Reply with ONLY a JSON object: {"next_agent": "<agent_id>"} '
            'or {"next_agent": "END"} when the round should end.'
        )),
    ]

    # Director gets its own model id (MAIC-104.2) so a 3-agent run
    # can use stub-director for routing while agents use stub for
    # generation. Falls back to languageModelId when unset (Phase-1
    # backward compat for single-agent runs that don't set both).
    director_model_id = (
        state.get("directorModelId")
        or state.get("languageModelId")
        or "stub"
    )

    try:
        chunks: list[str] = []
        async for chunk in stream_text(messages, director_model_id):
            chunks.append(chunk)
        full_text = "".join(chunks)
    except Exception:  # noqa: BLE001 — provider failure → safe fallback
        logger.exception("director_llm_decide: stream_text failed; falling back")
        return _round_robin_fallback(state)

    decision = parse_director_decision(full_text)

    # If the LLM parser failed but we have agents available, fall back
    # to round-robin instead of ending the round prematurely. parse_
    # director_decision returns should_end=True on failure; we
    # distinguish "parse failed" from "LLM said END" by checking whether
    # the raw text contained the word END.
    if decision.should_end and not _looks_like_explicit_end(full_text):
        logger.warning(
            "director_llm_decide: parse failed (text=%r); using round-robin",
            full_text[:200],
        )
        return _round_robin_fallback(state)

    # Sanity-check the chosen agent is actually in the available pool
    if decision.next_agent_id is not None:
        if decision.next_agent_id not in available_ids:
            logger.warning(
                "director_llm_decide: LLM picked %r but it's not in "
                "availableAgentIds=%s; using round-robin",
                decision.next_agent_id, available_ids,
            )
            return _round_robin_fallback(state)

    return decision


def _looks_like_explicit_end(text: str) -> bool:
    """Heuristic: did the LLM explicitly say to end the round?

    Used to distinguish "LLM said END" (decision is right; honor it)
    from "JSON parse failed" (decision is bogus; round-robin instead).
    """
    if not text:
        return False
    lowered = text.lower()
    # An explicit `"next_agent": "END"` string OR `"shouldEnd"` style
    # keyword in the raw output. Conservative: if neither marker is
    # present, treat the should_end=True as a parse failure.
    return ('"next_agent": "end"' in lowered) or ('"shouldend": true' in lowered)


def _round_robin_fallback(state: OrchestratorState) -> DirectorDecision:
    """Pick the next-after-last-responder from availableAgentIds.

    Deterministic, never crashes. If no agent has spoken yet, picks
    `availableAgentIds[0]`. If the most-recent responder is the last
    in the list, wraps to `[0]`.

    On exhaustion (every agent has spoken `maxTurns / N` times — not
    tracked precisely; fallback is a degenerate path) the caller's
    turn-limit check in `_director_node` will end the loop.
    """
    available = state.get("availableAgentIds") or []
    if not available:
        return DirectorDecision(next_agent_id=None, should_end=True)

    responses = state.get("agentResponses") or []
    if not responses:
        return DirectorDecision(next_agent_id=available[0], should_end=False)

    last_responder = responses[-1].get("agentId")
    if last_responder not in available:
        return DirectorDecision(next_agent_id=available[0], should_end=False)

    next_idx = (available.index(last_responder) + 1) % len(available)
    return DirectorDecision(next_agent_id=available[next_idx], should_end=False)


def _build_conversation_summary(state: OrchestratorState) -> str:
    """Build a compact conversation summary for the director prompt.

    Phase-3 placeholder until MAIC-109 (LLM-backed summarizer) lands —
    for now we render the last 4 messages verbatim with role/content
    truncation. Good enough for short sessions; long-session
    truncation is the summarizer's job.
    """
    messages = state.get("messages") or []
    if not messages:
        return ""
    recent = messages[-4:]
    lines = []
    for m in recent:
        role = m.get("role", "?")
        content = (m.get("content") or "")[:200]
        if content:
            lines.append(f"- {role}: {content}")
    return "\n".join(lines) if lines else ""


# ── Nodes ─────────────────────────────────────────────────────────────


async def _director_node(
    state: OrchestratorState,
    writer: StreamWriter,
) -> dict[str, Any]:
    """Director — chooses which agent speaks next.

    Three branches:

      1. **Turn-limit exit** (turn >= maxTurns): end without emitting.
         The loop is exhausted; no UX signal needed. Mirrors upstream
         director-graph.ts:114-118.

      2. **Turn-0 fast-path** (no LLM call):
         - If `triggerAgentId` is set in state AND in availableAgentIds
           → that agent speaks first
         - Else → `availableAgentIds[0]` (or 'default-1' if empty)
         Emit `thinking{stage:"agent_loading", agentId}` and dispatch.
         Mirrors upstream director-graph.ts:120-135.

      3. **Turn-≥1 dispatch:**
         - **Single-agent** (len(available) <= 1): preserve Phase-1
           cue-user-then-end. Keeps the single-agent acceptance criteria
           working without LLM cost.
         - **Multi-agent** (len(available) > 1, MAIC-104.2): LLM
           decides via `_director_llm_decide`. should_end → cue_user
           and end. Else emit `thinking` for chosen agent + dispatch.

    Logging is verbose at every turn boundary by design (Phase-3 plan
    §"Highest risk: log every turn boundary so debugging is grep-able").
    """
    write = _make_safe_writer(writer)
    turn = state.get("turnCount", 0)
    max_turns = state.get("maxTurns", 1)
    available = state.get("availableAgentIds") or []

    # Branch 1: turn-limit exit
    if turn >= max_turns:
        logger.info(
            "director[turn=%d/%d]: turn limit reached, ending",
            turn, max_turns,
        )
        return {"shouldEnd": True}

    # Branch 2: turn-0 fast-path
    if turn == 0:
        trigger_id = state.get("triggerAgentId")
        if trigger_id and trigger_id in available:
            agent_id = trigger_id
            logger.info(
                "director[turn=0]: fast-path → trigger agent %r",
                agent_id,
            )
        else:
            agent_id = available[0] if available else "default-1"
            logger.info(
                "director[turn=0]: fast-path → first agent %r (no trigger)",
                agent_id,
            )
        write({"type": "thinking", "data": {
            "stage": "agent_loading",
            "agentId": agent_id,
        }})
        return {"currentAgentId": agent_id, "shouldEnd": False}

    # Branch 3a: single-agent — preserve Phase-1 cue-user-then-end
    if len(available) <= 1:
        last_agent_id = available[0] if available else "default-1"
        logger.info(
            "director[turn=%d]: single-agent — cueing user after %r",
            turn, last_agent_id,
        )
        write({"type": "cue_user", "data": {"fromAgentId": last_agent_id}})
        return {"shouldEnd": True}

    # Branch 3b: multi-agent — LLM decides (MAIC-104.2)
    logger.info(
        "director[turn=%d/%d]: multi-agent decide (available=%s)",
        turn, max_turns, available,
    )
    decision = await _director_llm_decide(state)

    if decision.should_end or decision.next_agent_id is None:
        responses = state.get("agentResponses") or []
        last_agent_id = (
            responses[-1].get("agentId") if responses else (available[0] if available else None)
        )
        logger.info(
            "director[turn=%d]: LLM said END after %r — emitting cue_user",
            turn, last_agent_id,
        )
        write({"type": "cue_user", "data": {"fromAgentId": last_agent_id}})
        return {"shouldEnd": True}

    chosen_id = decision.next_agent_id
    logger.info(
        "director[turn=%d]: LLM chose %r — dispatching",
        turn, chosen_id,
    )
    write({"type": "thinking", "data": {
        "stage": "agent_loading",
        "agentId": chosen_id,
    }})
    return {"currentAgentId": chosen_id, "shouldEnd": False}


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
    """Run one agent's generation turn.

    Direct port of upstream director-graph.ts:238-432. Streams the LLM's
    structured-JSON output through parse_structured_chunk to extract
    text deltas + actions in original interleaved order, validates each
    action against the agent's allowed_actions (scene-filtered), and
    emits StatelessEvent frames (`agent_start`, `text_delta`, `action`,
    `agent_end`) through the injected StreamWriter.

    Action validation:
      - Filter by scene type (slide-only actions stripped on non-slide).
      - Drop disallowed actions (logged at warn).
      - Pydantic validate via apps.maic.protocol.validate_action;
        invalid payloads dropped with logger.warning.

    Whiteboard ledger accumulation:
      - All wb_* actions are appended to whiteboardLedger via the
        OrchestratorState reducer.
      - Used by the director's prompt (Phase 3 MAIC-415) to summarize
        what's been drawn so far.

    Returns partial state update:
      turnCount += 1
      agentResponses += [AgentTurnSummary(...)]   (reducer)
      whiteboardLedger += [...]                   (reducer)
      totalActions += action_count
      currentAgentId = None                        (clear for next director call)
    """
    import time
    import uuid

    from apps.maic.exceptions import MaicConfigError, MaicGraphError, MaicProviderError
    from apps.maic.orchestration.ai_adapter import stream_text
    from apps.maic.orchestration.prompt_builder import build_structured_prompt
    from apps.maic.orchestration.registry import resolve_agent
    from apps.maic.orchestration.stateless_parser import (
        create_parser_state,
        finalize_parser,
        parse_structured_chunk,
    )
    from apps.maic.orchestration.tool_schemas import get_effective_actions
    from apps.maic.protocol import validate_action
    from apps.maic.exceptions import MaicProtocolError
    from langchain_core.messages import HumanMessage, SystemMessage

    write = _make_safe_writer(writer)

    agent_id = state.get("currentAgentId")
    if not agent_id:
        logger.warning("agent_generate called without currentAgentId; ending")
        return {"shouldEnd": True}

    overrides = state.get("agentConfigOverrides") or {}
    agent = resolve_agent(agent_id, overrides)
    if agent is None:
        logger.error("agent_generate: agent_id=%r not in registry or overrides", agent_id)
        write({"type": "error", "data": {"message": f"unknown agent_id: {agent_id}"}})
        # Increment turnCount so the director's turn-limit branch fires
        # next pass and ends the loop. Without this the director would
        # re-dispatch the unknown agent forever (a node's `shouldEnd`
        # is overwritten when director runs and ignores incoming flags).
        return {
            "shouldEnd": True,
            "currentAgentId": None,
            "turnCount": state.get("turnCount", 0) + 1,
        }

    message_id = f"assistant-{agent_id}-{int(time.time() * 1000)}-{uuid.uuid4().hex[:6]}"

    # Determine effective allowed actions for this scene
    store_state = state.get("storeState") or {}
    scene_type: str | None = None
    current_id = store_state.get("currentSceneId")
    if current_id:
        scenes = store_state.get("scenes") or []
        scene = next((s for s in scenes if s.get("id") == current_id), None)
        if scene:
            scene_type = scene.get("type")
    effective_actions = get_effective_actions(agent.allowedActions, scene_type)

    # Emit agent_start so the frontend can show this agent's avatar/colour
    write({
        "type": "agent_start",
        "data": {
            "messageId": message_id,
            "agentId": agent_id,
            "agentName": agent.name,
            "agentAvatar": agent.avatar,
            "agentColor": agent.color,
        },
    })

    # Build the prompt + LLM message list
    try:
        system_prompt = build_structured_prompt(
            agent,
            store_state=store_state,
            discussion_context=state.get("discussionContext"),
            whiteboard_ledger=state.get("whiteboardLedger"),
            user_profile=state.get("userProfile"),
            agent_responses=state.get("agentResponses"),
        )
    except MaicConfigError as exc:
        logger.exception("agent_generate: prompt build failed")
        write({"type": "error", "data": {"message": str(exc)}})
        write({"type": "agent_end", "data": {"messageId": message_id, "agentId": agent_id}})
        return {"shouldEnd": True, "currentAgentId": None}

    # Convert state.messages (subset of OpenAI shape) to LangChain BaseMessages.
    # Phase 1 single-agent: append a "Please begin." trigger if no human turn
    # is present yet (mirrors upstream director-graph.ts:304-309).
    lc_messages = [SystemMessage(content=system_prompt)]
    history = state.get("messages") or []
    has_human = any(m.get("role") == "user" for m in history)
    if not has_human:
        lc_messages.append(HumanMessage(content="Please begin."))
    else:
        from langchain_core.messages import AIMessage
        for m in history:
            content = str(m.get("content", ""))
            role = m.get("role")
            if role == "user":
                lc_messages.append(HumanMessage(content=content))
            elif role == "assistant":
                lc_messages.append(AIMessage(content=content))
            elif role == "system":
                lc_messages.append(SystemMessage(content=content))
        # Ensure the trailing message is a HumanMessage (LLMs require it
        # for completion). If it isn't, append the upstream cue.
        if not isinstance(lc_messages[-1], HumanMessage):
            lc_messages.append(
                HumanMessage(content="It's your turn to speak. Respond from your perspective.")
            )

    # Stream the LLM response, parse structured chunks, emit events
    parser_state = create_parser_state()
    full_text = ""
    action_count = 0
    whiteboard_actions: list[dict[str, Any]] = []
    language_model_id = state.get("languageModelId") or "stub"

    try:
        async for chunk in stream_text(lc_messages, language_model_id):
            result = parse_structured_chunk(chunk, parser_state)
            for entry in result.ordered:
                if entry["type"] == "text":
                    text = result.textChunks[entry["index"]]
                    full_text += text
                    write({
                        "type": "text_delta",
                        "data": {"content": text, "messageId": message_id},
                    })
                elif entry["type"] == "action":
                    parsed = result.actions[entry["index"]]
                    if parsed["actionName"] not in effective_actions:
                        logger.warning(
                            "agent %s emitted disallowed action %r; skipping",
                            agent.name, parsed["actionName"],
                        )
                        continue
                    payload = {
                        "id": parsed["actionId"],
                        "type": parsed["actionName"],
                        **parsed["params"],
                    }
                    try:
                        validated = validate_action(payload)
                    except MaicProtocolError as exc:
                        logger.warning(
                            "agent %s emitted invalid action: %s",
                            agent.name, exc,
                        )
                        continue
                    action_count += 1
                    if parsed["actionName"].startswith("wb_"):
                        whiteboard_actions.append({
                            "actionName": parsed["actionName"],
                            "agentId": agent_id,
                            "agentName": agent.name,
                            "params": parsed["params"],
                        })
                    write({
                        "type": "action",
                        "data": {
                            "actionId": parsed["actionId"],
                            "actionName": parsed["actionName"],
                            "params": parsed["params"],
                            "agentId": agent_id,
                            "messageId": message_id,
                        },
                    })

        # Drain any trailing partial text the model didn't close cleanly
        final = finalize_parser(parser_state)
        for entry in final.ordered:
            if entry["type"] == "text":
                text = final.textChunks[entry["index"]]
                full_text += text
                write({
                    "type": "text_delta",
                    "data": {"content": text, "messageId": message_id},
                })
            elif entry["type"] == "action":
                # finalize emits actions only when partial parse completed late;
                # validation path identical to streaming branch
                parsed = final.actions[entry["index"]]
                if parsed["actionName"] not in effective_actions:
                    continue
                payload = {
                    "id": parsed["actionId"],
                    "type": parsed["actionName"],
                    **parsed["params"],
                }
                try:
                    validate_action(payload)
                except MaicProtocolError:
                    continue
                action_count += 1
                if parsed["actionName"].startswith("wb_"):
                    whiteboard_actions.append({
                        "actionName": parsed["actionName"],
                        "agentId": agent_id,
                        "agentName": agent.name,
                        "params": parsed["params"],
                    })
                write({
                    "type": "action",
                    "data": {
                        "actionId": parsed["actionId"],
                        "actionName": parsed["actionName"],
                        "params": parsed["params"],
                        "agentId": agent_id,
                        "messageId": message_id,
                    },
                })

    except MaicProviderError as exc:
        logger.exception("agent_generate: provider error")
        write({"type": "error", "data": {"message": str(exc)}})

    # ── TTS: synthesize the agent's spoken text into a speech_audio frame ──
    # Phase 1 contract: one audio per agent turn (concatenated text).
    # MAIC-501.2. Phase 5 (VoxCPM2) may split per text-item for better
    # interleaving with actions in long turns.
    if full_text.strip():
        try:
            from apps.maic.tts import SpeechSynthesisError, synthesize_speech

            voice_id = (
                agent.voiceConfig.voiceId
                if agent.voiceConfig is not None
                else None
            )
            audio_id = f"speech-{uuid.uuid4().hex[:12]}"
            speech = await synthesize_speech(
                full_text,
                audio_id=audio_id,
                voice=voice_id,
            )
            write({
                "type": "speech_audio",
                "data": {
                    "audioId": speech.audio_id,
                    "audioB64": speech.audio_b64,
                    "format": speech.format,
                    "messageId": message_id,
                    "agentId": agent_id,
                },
            })
        except SpeechSynthesisError as exc:
            # TTS failure should NOT abort the agent's turn — the
            # frontend can still render text, just without audio.
            logger.warning(
                "agent_generate: TTS failed for agent %s: %s",
                agent.name, exc,
            )

    write({
        "type": "agent_end",
        "data": {"messageId": message_id, "agentId": agent_id},
    })

    if not full_text and action_count == 0:
        logger.warning(
            "agent %s produced empty response (no text, no actions)", agent.name,
        )

    return {
        "turnCount": state.get("turnCount", 0) + 1,
        "currentAgentId": None,
        "totalActions": state.get("totalActions", 0) + action_count,
        "agentResponses": [{
            "agentId": agent_id,
            "agentName": agent.name,
            "contentPreview": full_text[:300],
            "actionCount": action_count,
            "whiteboardActions": whiteboard_actions,
        }],
        "whiteboardLedger": whiteboard_actions,
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
      - `None`  → caller didn't specify; default to ["default-1"] (the
        built-in teacher agent). agent_generate resolves this through
        the registry to a real, well-personaed AgentConfig.
      - `[]`    → caller explicitly specified no agents; preserve the
        empty list. The director then applies its `'default-1'` fallback
        rule from upstream director-graph.ts:122 — never overwrite
        caller intent here.
    """
    if available_agent_ids is None:
        available_agent_ids = ["default-1"]

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
