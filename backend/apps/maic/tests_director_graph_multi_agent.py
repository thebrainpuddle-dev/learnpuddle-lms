"""Tests for the multi-agent director path (MAIC-104.2).

Drives the real `stream_classroom` over multi-agent state with
`languageModelId="stub-director"` so the director's LLM call is
deterministic + production-grade (no mocks per CLAUDE.md hard rule).

The stub-director cycles through DIRECTOR_STUB_OUTPUTS:
  ['default-1', 'default-3', 'default-4', 'END']
"""
from __future__ import annotations

import sys
import types

import pytest

from apps.maic.orchestration.ai_adapter import reset_director_stub_counter
from apps.maic.orchestration.director_graph import (
    build_initial_state,
    stream_classroom,
)


# Reuse the autostub edge_tts pattern from tests_director_graph.py.
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


@pytest.fixture(autouse=True)
def _reset_director_stub():
    reset_director_stub_counter()
    yield
    reset_director_stub_counter()


# ── Helpers ────────────────────────────────────────────────────────


async def _drain(state):
    """Run stream_classroom to completion, return all events as list."""
    events = []
    async for ev in stream_classroom(state):
        events.append(ev)
    return events


def _types(events):
    return [e["type"] for e in events]


def _agent_starts(events):
    return [e["data"]["agentId"] for e in events if e["type"] == "agent_start"]


def _thinking_agents(events):
    return [
        e["data"].get("agentId")
        for e in events
        if e["type"] == "thinking" and e["data"].get("stage") == "agent_loading"
    ]


# ── Tests ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_three_agent_chain_dispatches_in_decider_order():
    """3 agents + maxTurns=4 + stub-director → director picks
    default-1 (turn-0 fast-path), default-1 (LLM #1), default-3
    (LLM #2), default-4 (LLM #3), then turn-limit ends.
    """
    state = build_initial_state(
        messages=[{"id": "u1", "role": "user", "content": "Teach me fractions."}],
        available_agent_ids=["default-1", "default-3", "default-4"],
        max_turns=4,
    )
    state["languageModelId"] = "stub"
    state["directorModelId"] = "stub-director"

    events = await _drain(state)

    # 4 agent turns total: turn-0 fast-path + 3 LLM-decided turns
    starts = _agent_starts(events)
    assert starts == ["default-1", "default-1", "default-3", "default-4"], (
        f"unexpected agent_start sequence: {starts}"
    )

    # Each turn must emit a `thinking` for the right agent BEFORE
    # the agent_start.
    thinkings = _thinking_agents(events)
    assert thinkings == ["default-1", "default-1", "default-3", "default-4"], (
        f"unexpected thinking sequence: {thinkings}"
    )

    # Turn-limit ends → no cue_user (turn-limit branch ends silently)
    assert "cue_user" not in _types(events)


@pytest.mark.asyncio
async def test_three_agent_chain_emits_cue_user_when_llm_says_end():
    """maxTurns=5 lets the director run 4 LLM decisions; the 4th
    stub-director output is END → cue_user fires.
    """
    state = build_initial_state(
        messages=[{"id": "u1", "role": "user", "content": "Teach me."}],
        available_agent_ids=["default-1", "default-3", "default-4"],
        max_turns=5,
    )
    state["languageModelId"] = "stub"
    state["directorModelId"] = "stub-director"

    events = await _drain(state)

    starts = _agent_starts(events)
    assert starts == ["default-1", "default-1", "default-3", "default-4"], starts

    # Last director call (turn=4) → LLM #4 → END → cue_user emitted
    cue_events = [e for e in events if e["type"] == "cue_user"]
    assert len(cue_events) == 1
    assert cue_events[0]["data"]["fromAgentId"] == "default-4"


@pytest.mark.asyncio
async def test_single_agent_preserves_phase1_behavior():
    """When only one agent is available, the Phase-1 cue-user-then-end
    path runs (no LLM call). Backward-compatibility check."""
    state = build_initial_state(
        messages=[],
        available_agent_ids=["default-1"],
        max_turns=2,
    )
    state["languageModelId"] = "stub"
    state["directorModelId"] = "stub-director"  # Should NOT be called

    events = await _drain(state)

    # 1 turn: fast-path → default-1 → cue_user (Phase-1 single-agent)
    starts = _agent_starts(events)
    assert starts == ["default-1"]

    cue_events = [e for e in events if e["type"] == "cue_user"]
    assert len(cue_events) == 1
    assert cue_events[0]["data"]["fromAgentId"] == "default-1"


@pytest.mark.asyncio
async def test_trigger_agent_id_takes_turn_zero():
    """When triggerAgentId is set, that agent speaks first regardless
    of position in availableAgentIds."""
    state = build_initial_state(
        messages=[],
        available_agent_ids=["default-1", "default-3", "default-4"],
        max_turns=2,
    )
    state["languageModelId"] = "stub"
    state["directorModelId"] = "stub-director"
    state["triggerAgentId"] = "default-3"

    events = await _drain(state)

    # First thinking + agent_start should be default-3
    thinkings = _thinking_agents(events)
    assert thinkings[0] == "default-3"
    starts = _agent_starts(events)
    assert starts[0] == "default-3"


@pytest.mark.asyncio
async def test_trigger_agent_outside_available_falls_back_to_first():
    """If triggerAgentId is set but isn't in availableAgentIds,
    fast-path falls back to availableAgentIds[0]."""
    state = build_initial_state(
        messages=[],
        available_agent_ids=["default-1", "default-3"],
        max_turns=1,
    )
    state["languageModelId"] = "stub"
    state["directorModelId"] = "stub-director"
    state["triggerAgentId"] = "default-99"  # not in available

    events = await _drain(state)
    starts = _agent_starts(events)
    assert starts[0] == "default-1"


@pytest.mark.asyncio
async def test_multi_agent_state_accumulates_agent_responses_correctly():
    """After a 3-agent chain, agentResponses should hold one entry per
    turn, in dispatch order. This is the reducer-merge contract that
    the director's LLM prompt depends on."""
    state = build_initial_state(
        messages=[],
        available_agent_ids=["default-1", "default-3", "default-4"],
        max_turns=4,
    )
    state["languageModelId"] = "stub"
    state["directorModelId"] = "stub-director"

    # Use astream directly so we can inspect the final state, not
    # just the events.
    from apps.maic.orchestration.director_graph import create_orchestration_graph

    graph = create_orchestration_graph()
    final_state = await graph.ainvoke(state)
    responses = final_state.get("agentResponses") or []

    # 4 turns happened (default-1 fast-path, default-1 LLM, default-3 LLM,
    # default-4 LLM)
    assert len(responses) == 4
    assert [r["agentId"] for r in responses] == [
        "default-1", "default-1", "default-3", "default-4",
    ]


@pytest.mark.asyncio
async def test_multi_agent_with_stub_provider_falls_back_to_round_robin():
    """When languageModelId is the agent-generate "stub" (not stub-
    director), the JSON-array stub output doesn't match next_agent
    → parse fails → round-robin fallback fires.

    Round-robin from default-1 → default-3 → default-4 → default-1.
    """
    state = build_initial_state(
        messages=[],
        available_agent_ids=["default-1", "default-3", "default-4"],
        max_turns=4,
    )
    state["languageModelId"] = "stub"  # NOT stub-director — agent stub

    events = await _drain(state)
    starts = _agent_starts(events)
    # turn-0 fast-path: default-1
    # turn-1 LLM (stub returns garbage → round-robin from last responder
    #   default-1 → next = default-3)
    # turn-2 LLM (last = default-3 → next = default-4)
    # turn-3 LLM (last = default-4 → wraps to default-1)
    assert starts == ["default-1", "default-3", "default-4", "default-1"]
