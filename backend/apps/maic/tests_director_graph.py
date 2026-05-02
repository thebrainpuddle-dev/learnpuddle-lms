"""Tests for apps.maic.orchestration.director_graph (Phase-0 stub).

Coverage targets:
  - apps/maic/orchestration/director_graph.py  ≥ 90% lines
  - apps/maic/exceptions.py  100% (just class declarations)
"""
from __future__ import annotations

import pytest

from apps.maic.exceptions import (
    MaicError,
    MaicGraphError,
    MaicProtocolError,
)
from apps.maic.orchestration.director_graph import (
    _PHASE0_MESSAGE_ID,
    _make_safe_writer,
    _validate_event,
    build_initial_state,
    create_orchestration_graph,
    stream_classroom,
)


# ── _validate_event ────────────────────────────────────────────────────


@pytest.mark.parametrize("type_tag", [
    "agent_start", "text_delta", "action", "agent_end",
    "thinking", "cue_user", "speech_audio", "error",
])
def test_validate_event_accepts_all_eight_valid_types(type_tag):
    _validate_event({"type": type_tag, "data": {}})  # no raise


@pytest.mark.parametrize("bad_event", [
    {"type": "definitely_not_a_real_type", "data": {}},   # unknown type
    {"type": "agent_start"},                               # missing data
    "not a dict",                                          # not a dict
    {"data": {}},                                          # missing type
    None,                                                  # not a dict
    42,                                                    # not a dict
])
def test_validate_event_rejects_invalid_shapes(bad_event):
    with pytest.raises(MaicProtocolError):
        _validate_event(bad_event)  # type: ignore[arg-type]


# ── _make_safe_writer ──────────────────────────────────────────────────


def test_safe_writer_drops_invalid_event_without_calling_raw():
    """Invalid events are logged + dropped. Raw writer must NOT be invoked
    (a bad frame should not pollute the wire)."""
    raw_calls: list[dict] = []
    safe = _make_safe_writer(lambda e: raw_calls.append(e))
    safe({"type": "DEFINITELY_INVALID", "data": {}})
    assert raw_calls == []


def test_safe_writer_passes_valid_event_through():
    raw_calls: list[dict] = []
    safe = _make_safe_writer(lambda e: raw_calls.append(e))
    valid = {"type": "agent_start", "data": {"messageId": "m"}}
    safe(valid)
    assert raw_calls == [valid]


def test_safe_writer_swallows_raw_writer_exception():
    """controller-closed-after-abort path: raw raises, safe writer must NOT.
    This mirrors upstream director-graph.ts:104-111."""
    def boom(_event):
        raise RuntimeError("controller closed after abort")

    safe = _make_safe_writer(boom)
    safe({"type": "agent_start", "data": {"messageId": "m"}})  # no raise


def test_safe_writer_handles_none_writer():
    """Unit-test convenience path: invoking a node directly outside of
    `astream(stream_mode='custom')` may pass None for the writer.  The
    safe wrapper logs + drops; production never hits this path because
    LangGraph always injects a real StreamWriter."""
    safe = _make_safe_writer(None)
    safe({"type": "agent_start", "data": {"messageId": "m"}})  # no raise


# ── build_initial_state ────────────────────────────────────────────────


def test_initial_state_has_all_16_fields():
    """Mirror of OrchestratorState 16-field set; if these drift, MAIC-004
    regression test catches it first, but this is the runtime confirm."""
    state = build_initial_state()
    expected = {
        "messages", "storeState", "availableAgentIds", "maxTurns",
        "languageModelId", "thinkingConfig", "discussionContext",
        "triggerAgentId", "userProfile", "agentConfigOverrides",
        "currentAgentId", "turnCount", "shouldEnd", "totalActions",
        "agentResponses", "whiteboardLedger",
    }
    assert set(state.keys()) == expected


def test_initial_state_defaults():
    state = build_initial_state()
    assert state["turnCount"] == 0
    assert state["shouldEnd"] is False
    assert state["agentResponses"] == []
    assert state["whiteboardLedger"] == []
    assert state["maxTurns"] == 1
    assert state["availableAgentIds"] == [_PHASE0_MESSAGE_ID]


def test_initial_state_propagates_inputs():
    state = build_initial_state(
        messages=[{"id": "m1", "role": "user", "content": "hi"}],
        available_agent_ids=["a1", "a2"],
        max_turns=5,
    )
    assert state["messages"][0]["content"] == "hi"
    assert state["availableAgentIds"] == ["a1", "a2"]
    assert state["maxTurns"] == 5


# ── stream_classroom (the real public API) ─────────────────────────────


@pytest.mark.asyncio
async def test_stream_phase1_default_maxturns1_emits_4_events():
    """Phase-1 single-agent with the typical maxTurns=1 contract (one
    director→agent cycle per request, mirroring upstream
    `buildInitialState` line 533: `maxTurns: turnCount + 1`):

        thinking{stage:agent_loading,agentId}   (director dispatch)
      → agent_start
      → text_delta
      → agent_end
        (director runs again, turnCount(1) ≥ maxTurns(1) → end without
         emitting cue_user)

    cue_user fires only when maxTurns ≥ 2 (a multi-turn session) — see
    test_cue_user_fires_when_maxturns_allows_followup below.
    """
    events = []
    async for event in stream_classroom(build_initial_state()):
        events.append(event)
    types = [e["type"] for e in events]
    assert types == [
        "thinking", "agent_start", "text_delta", "agent_end",
    ], events
    assert events[0]["data"]["stage"] == "agent_loading"
    assert events[0]["data"]["agentId"] == _PHASE0_MESSAGE_ID


@pytest.mark.asyncio
async def test_cue_user_fires_when_maxturns_allows_followup():
    """maxTurns=2 → director gets a second pass after the agent
    responds, emits cue_user, then ends."""
    state = build_initial_state(max_turns=2)
    events = [e async for e in stream_classroom(state)]
    types = [e["type"] for e in events]
    assert types == [
        "thinking", "agent_start", "text_delta", "agent_end", "cue_user",
    ], events
    cue = events[-1]
    assert cue["data"]["fromAgentId"] == _PHASE0_MESSAGE_ID


@pytest.mark.asyncio
async def test_stream_dispatches_first_available_agent_id():
    """Director uses availableAgentIds[0] for single-agent dispatch
    (matches upstream director-graph.ts:121)."""
    state = build_initial_state(
        available_agent_ids=["my-custom-agent"],
        max_turns=2,
    )
    events = [e async for e in stream_classroom(state)]
    thinking = next(e for e in events if e["type"] == "thinking")
    assert thinking["data"]["agentId"] == "my-custom-agent"
    cue = next(e for e in events if e["type"] == "cue_user")
    assert cue["data"]["fromAgentId"] == "my-custom-agent"


@pytest.mark.asyncio
async def test_stream_falls_back_to_default_1_when_no_agent_ids():
    """Empty availableAgentIds → fallback to 'default-1' (matches upstream
    `state.availableAgentIds[0] || 'default-1'` at director-graph.ts:122)."""
    state = build_initial_state(available_agent_ids=[])
    events = [e async for e in stream_classroom(state)]
    thinking = next(e for e in events if e["type"] == "thinking")
    assert thinking["data"]["agentId"] == "default-1"


@pytest.mark.asyncio
async def test_stream_text_delta_carries_phase0_marker():
    events = [e async for e in stream_classroom(build_initial_state())]
    delta = next(e for e in events if e["type"] == "text_delta")
    assert "Phase 0" in delta["data"]["content"]
    assert delta["data"]["messageId"] == _PHASE0_MESSAGE_ID


@pytest.mark.asyncio
async def test_stream_terminates_after_one_turn():
    """maxTurns=1 → director ends after a single agent_generate cycle."""
    events = [e async for e in stream_classroom(build_initial_state(max_turns=1))]
    end_frames = [e for e in events if e["type"] == "agent_end"]
    assert len(end_frames) == 1, f"expected exactly one agent_end, got {events}"


# ── create_orchestration_graph (constructor smoke) ─────────────────────


def test_graph_compiles_without_error():
    g = create_orchestration_graph()
    assert g is not None
    # Confirm both nodes exist by name
    nodes = set(g.get_graph().nodes.keys()) - {"__start__", "__end__"}
    assert {"director", "agent_generate"} <= nodes, f"unexpected node set: {nodes}"


# ── MaicGraphError surface ─────────────────────────────────────────────


def test_exception_hierarchy():
    """MaicProtocolError ⊂ MaicGraphError ⊂ MaicError. Catching MaicError
    catches all internal failures — a single broad-net for the consumer."""
    assert issubclass(MaicProtocolError, MaicGraphError)
    assert issubclass(MaicGraphError, MaicError)
