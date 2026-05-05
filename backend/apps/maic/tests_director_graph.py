"""Tests for apps.maic.orchestration.director_graph.

Coverage targets:
  - apps/maic/orchestration/director_graph.py  ≥ 90% lines
  - apps/maic/exceptions.py  100% (just class declarations)
"""
from __future__ import annotations

import sys
import types
from typing import Any

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


# ── Autouse fixture: stub edge_tts so director_graph tests don't hit
#    the real Microsoft TTS endpoint (was making the suite take ~9s).
#    Dedicated TTS tests live in tests_tts_service.py +
#    tests_director_graph_tts.py and provide their own fixtures.


class _AutostubCommunicate:
    def __init__(self, *_a, **_kw):
        pass

    async def stream(self):
        yield {"type": "audio", "data": b"\xff\xfb\x90autostub-audio"}


@pytest.fixture(autouse=True)
def _stub_edge_tts(monkeypatch):
    fake = types.ModuleType("edge_tts")
    fake.Communicate = _AutostubCommunicate  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "edge_tts", fake)


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


def test_initial_state_has_all_18_fields():
    """Runtime state from build_initial_state() — 16 fields at Phase 1,
    +ttsConfig in Phase 5 MAIC-502 = 17, +pendingWidgetEvents in Phase 6
    MAIC-603 = 18. The TypedDict declares `directorModelId` but
    build_initial_state doesn't populate it (TypedDict total=False), so
    the runtime keyset stays one less than the annotation count. The
    annotation-count lock lives in
    tests_orchestration.test_total_field_count_is_nineteen."""
    state = build_initial_state()
    expected = {
        "messages", "storeState", "availableAgentIds", "maxTurns",
        "languageModelId", "thinkingConfig", "discussionContext",
        "triggerAgentId", "userProfile", "agentConfigOverrides",
        "ttsConfig",
        "currentAgentId", "turnCount", "shouldEnd", "totalActions",
        "agentResponses", "whiteboardLedger", "pendingWidgetEvents",
    }
    assert set(state.keys()) == expected


def test_initial_state_defaults():
    state = build_initial_state()
    assert state["turnCount"] == 0
    assert state["shouldEnd"] is False
    assert state["agentResponses"] == []
    assert state["whiteboardLedger"] == []
    assert state["maxTurns"] == 1
    # MAIC-105.3: default availableAgentIds points at the registry's
    # built-in teacher agent so agent_generate resolves a real config.
    assert state["availableAgentIds"] == ["default-1"]


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
async def test_stream_phase1_default_maxturns1_full_pipeline():
    """Phase-1 single-agent with default-1 (built-in teacher) under
    maxTurns=1 + stub LLM. The stub emits one text item + one speech
    action, so the full event sequence is:

        thinking{stage:agent_loading, agentId="default-1"}
      → agent_start{agentName="AI teacher", agentColor="#3b82f6", ...}
      → text_delta(s)         (≥1 — parser may chunk)
      → action{actionName="speech"}
      → agent_end
        (director runs again, turnCount(1) ≥ maxTurns(1) → end without
         emitting cue_user)

    Validates: real registry resolution, stub LLM streaming, parser
    integration, action validation against teacher's allowed_actions.
    """
    events = []
    async for event in stream_classroom(build_initial_state()):
        events.append(event)
    types = [e["type"] for e in events]
    assert types[0] == "thinking"
    assert types[1] == "agent_start"
    assert "text_delta" in types
    assert "action" in types
    assert types[-1] == "agent_end"

    assert events[0]["data"]["stage"] == "agent_loading"
    assert events[0]["data"]["agentId"] == "default-1"

    start = events[1]
    assert start["data"]["agentId"] == "default-1"
    assert start["data"]["agentName"] == "AI teacher"
    assert start["data"]["agentColor"] == "#3b82f6"

    # Stub emits a wb_open action which is in teacher's allowedActions
    wb_action = next(e for e in events if e["type"] == "action")
    assert wb_action["data"]["actionName"] == "wb_open"
    assert wb_action["data"]["agentId"] == "default-1"


@pytest.mark.asyncio
async def test_cue_user_fires_when_maxturns_allows_followup():
    """maxTurns=2 → director gets a second pass after the agent
    responds, emits cue_user, then ends."""
    state = build_initial_state(max_turns=2)
    events = [e async for e in stream_classroom(state)]
    types = [e["type"] for e in events]
    assert types[-1] == "cue_user", events
    assert events[-1]["data"]["fromAgentId"] == "default-1"


@pytest.mark.asyncio
async def test_stream_dispatches_first_available_agent_id():
    """Director uses availableAgentIds[0] for single-agent dispatch
    (matches upstream director-graph.ts:121). Uses default-2 (assistant)
    so we test override of the default-1 default."""
    state = build_initial_state(
        available_agent_ids=["default-2"],
        max_turns=2,
    )
    events = [e async for e in stream_classroom(state)]
    thinking = next(e for e in events if e["type"] == "thinking")
    assert thinking["data"]["agentId"] == "default-2"
    start = next(e for e in events if e["type"] == "agent_start")
    assert start["data"]["agentName"] == "AI助教"
    cue = next(e for e in events if e["type"] == "cue_user")
    assert cue["data"]["fromAgentId"] == "default-2"


@pytest.mark.asyncio
async def test_unknown_agent_id_emits_error_and_ends():
    """When agent_id resolves to neither a default nor an override, the
    agent_generate node emits an error frame and ends without crashing."""
    state = build_initial_state(available_agent_ids=["nonexistent-agent"])
    events = [e async for e in stream_classroom(state)]
    types = [e["type"] for e in events]
    assert "error" in types
    err = next(e for e in events if e["type"] == "error")
    assert "nonexistent-agent" in err["data"]["message"]


@pytest.mark.asyncio
async def test_stream_falls_back_to_default_1_when_no_agent_ids():
    """Empty availableAgentIds → fallback to 'default-1' (matches upstream
    `state.availableAgentIds[0] || 'default-1'` at director-graph.ts:122)."""
    state = build_initial_state(available_agent_ids=[])
    events = [e async for e in stream_classroom(state)]
    thinking = next(e for e in events if e["type"] == "thinking")
    assert thinking["data"]["agentId"] == "default-1"


@pytest.mark.asyncio
async def test_stream_text_delta_concatenates_to_stub_content():
    """The stub LLM emits 'Hello students. …' inside a {type:text} JSON
    item. Concatenating all text_deltas must yield that string exactly
    (no duplication, no loss across streaming chunks). Single messageId
    across deltas."""
    events = [e async for e in stream_classroom(build_initial_state())]
    deltas = [e for e in events if e["type"] == "text_delta"]
    assert deltas
    full = "".join(d["data"]["content"] for d in deltas)
    assert full == "Hello students. Today we will learn about the topic at hand."
    msg_ids = {d["data"]["messageId"] for d in deltas}
    assert len(msg_ids) == 1


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
