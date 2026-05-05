"""LangGraph orchestrator state — direct port of upstream OpenMAIC.

Source:
    https://github.com/THU-MAIC/OpenMAIC/blob/main/lib/orchestration/director-graph.ts#L47-L74
    /Volumes/CrucialX9/OpenMAIC/lib/orchestration/director-graph.ts:47-74

The state object passed between LangGraph nodes (director ⇄ agent_generate).
Three field categories:

  1. Inputs (set once at graph entry, never mutated): messages, storeState,
     availableAgentIds, maxTurns, languageModelId, thinkingConfig,
     discussionContext, triggerAgentId, userProfile, agentConfigOverrides.

  2. Mutable scalars (overwritten by node return): currentAgentId,
     turnCount, shouldEnd, totalActions.

  3. Reducer-accumulated lists: agentResponses, whiteboardLedger.
     Reducer is `operator.add` (Python equivalent of upstream's
     `(prev, update) => [...prev, ...update]`). Empirically validated
     under langgraph 1.1.10 in MAIC-001 self-cert; see
     obsidian-vault/.../maic-rebuild/phase-0-foundation/MAIC-001-CERTIFICATION.md.

Deviation from upstream: `languageModelId: str` rather than upstream's
`languageModel: LanguageModel` instance.  Reason: state must stay
JSON-serializable for snapshot/restore (frontend playback engine
re-issues state on reconnect via [[../phase-3-multi-agent/index]]).  The
actual langchain chat model is constructed inside nodes from this ID
via `apps.maic.orchestration.ai_adapter.resolve_model(id)` (lands in
MAIC-005).
"""
from __future__ import annotations

from operator import add
from typing import Annotated, Any, TypedDict


# ── Supporting TypedDicts (subsets of upstream types) ──────────────────


class Message(TypedDict, total=False):
    """Mirror of upstream chat Message — id, role, content, agentId.

    Source: lib/types/chat.ts.  Phase 0 ships the minimal subset used
    by the director and agent_generate nodes; richer fields (timestamps,
    tool_calls) are added when their callers exist (Phase 1+).
    """
    id: str
    role: str          # 'user' | 'assistant' | 'system'
    content: str
    agentId: str | None


class StoreState(TypedDict, total=False):
    """Mirror of upstream storeState — current scene, slides list,
    whiteboard-open flag.

    Source: lib/types/store.ts.  Subset used by the director's prompt
    and the action-protocol filter (slide-only actions are stripped
    when scene type ≠ slide — see upstream director-graph.ts:275-279).
    """
    currentSceneId: str | None
    scenes: list[dict[str, Any]]
    whiteboardOpen: bool


class AgentTurnSummary(TypedDict):
    """Reducer-accumulated record of one agent's turn.

    Upstream type: lib/orchestration/types.ts AgentTurnSummary.
    Used by the director prompt (Phase 3, MAIC-104) to summarize the
    conversation so far without resending the full message history.
    """
    agentId: str
    agentName: str
    contentPreview: str
    actionCount: int
    whiteboardActions: list[dict[str, Any]]


class WhiteboardActionRecord(TypedDict):
    """Reducer-accumulated record of one whiteboard action taken.

    Upstream type: lib/orchestration/types.ts WhiteboardActionRecord.
    Drives the director's "what's already on the board" awareness in
    Phase 3 (MAIC-415 — whiteboard ledger included in director prompt).
    """
    actionName: str        # one of wb_open | wb_draw_text | wb_draw_shape | …
    agentId: str
    agentName: str
    params: dict[str, Any]


class WidgetEvent(TypedDict, total=False):
    """One event emitted by an interactive widget iframe and forwarded
    to the backend over the WS as `{action: 'widget_event', data: {...}}`.

    Phase 6 (MAIC-603): the consumer buffers these into
    `OrchestratorState.pendingWidgetEvents`. Phase 7's PBL agentic
    loop reads the buffer at each director-turn entry to surface
    student widget interactions to the next agent's prompt context
    (e.g. "the student set numerator to 3 and clicked apply").

    Shape:
      - sceneId : the active scene's id (correlates to the iframe
        registered via widget-iframe-store.ts on the frontend).
      - widgetId: optional intra-scene widget identifier (when one
        scene hosts multiple widgets — rare in Phase 6, reserved).
      - event   : a short verb describing what happened
        (e.g. 'click', 'change', 'submit', 'complete').
      - payload : free-form JSON dict with event details. Whatever
        the widget HTML chose to postMessage; the backend doesn't
        prescribe a schema since each widget type emits different
        signal shapes.
      - receivedAt: ISO-8601 server timestamp of when the consumer
        accepted the frame. Useful for ordering and stale-event
        filtering on the director side.
    """
    sceneId: str
    widgetId: str | None
    event: str
    payload: dict[str, Any]
    receivedAt: str


# ── OrchestratorState — the LangGraph state ────────────────────────────


class OrchestratorState(TypedDict, total=False):
    """LangGraph state for the AI Classroom orchestrator.

    Field-for-field port of upstream director-graph.ts:47-74. Adding a
    field here without a corresponding node read/write is a code smell;
    every field is consumed by either the director or agent_generate
    node (or both).
    """

    # ── Inputs (set once at graph entry) ──
    messages: list[Message]
    storeState: StoreState
    availableAgentIds: list[str]
    maxTurns: int
    languageModelId: str                              # see module docstring deviation
    directorModelId: str | None                       # MAIC-104.2: optional separate
                                                      # model for the director's
                                                      # multi-agent decisions; falls
                                                      # back to languageModelId when
                                                      # unset. Useful for picking a
                                                      # faster/cheaper router model
                                                      # vs the agent generation model.
    thinkingConfig: dict[str, Any] | None
    discussionContext: dict[str, Any] | None          # shape: {topic, prompt?}
    triggerAgentId: str | None
    userProfile: dict[str, Any] | None                # shape: {nickname?, bio?}
    agentConfigOverrides: dict[str, dict[str, Any]]   # request-scoped agent configs
    ttsConfig: dict[str, Any] | None                  # MAIC-502: pre-resolved per-tenant
                                                      # TTS bundle (provider, api_key,
                                                      # base_url, voice). Resolved once
                                                      # at WS handshake to avoid sync DB
                                                      # calls inside the async stream.
                                                      # Shape: dict from
                                                      # TenantAIConfig.resolve_tts_config().

    # ── Mutable scalars (overwritten by nodes) ──
    currentAgentId: str | None
    turnCount: int
    shouldEnd: bool
    totalActions: int

    # ── Reducer-accumulated lists ──
    # Annotated[list, add] tells LangGraph to merge the previous and incoming
    # values via operator.add (list concatenation).  Empirically verified to
    # work under langgraph 1.1.10 in MAIC-001 cert.
    agentResponses: Annotated[list[AgentTurnSummary], add]
    whiteboardLedger: Annotated[list[WhiteboardActionRecord], add]
    pendingWidgetEvents: Annotated[list[WidgetEvent], add]    # MAIC-603: widget
                                                              # iframe events forwarded
                                                              # by the WS consumer; the
                                                              # director reads + drains
                                                              # these at next turn entry
                                                              # (Phase 7 PBL will use).
