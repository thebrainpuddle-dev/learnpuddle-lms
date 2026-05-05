"""Tests for apps.maic.orchestration.state.

Guard against accidental field renames or removals — the OrchestratorState
shape is a load-bearing contract: the WS consumer (MAIC-003 → MAIC-005),
the director graph, and the future HTTP session route (MAIC-301) all
depend on it. Drift here breaks the wire format silently.
"""
from __future__ import annotations

from operator import add
from typing import Annotated, get_type_hints

import pytest

from apps.maic.orchestration.state import (
    AgentTurnSummary,
    Message,
    OrchestratorState,
    StoreState,
    WhiteboardActionRecord,
)


# ── Field-set lock (regression net) ────────────────────────────────────


def test_orchestrator_state_field_set_locked():
    """The 17 fields must all be present.

    Phase 1 had 16 fields. Phase 3 (MAIC-104.2) added `directorModelId`.
    Phase 5 (MAIC-502) added `ttsConfig` so per-tenant TTS provider/key
    pre-resolved at WS handshake flows through the orchestration loop
    without sync-DB calls inside the async stream.

    If this fails because the spec genuinely changed, sync the upstream
    counterpart first, then update this list (and OrchestratorState)
    in lockstep. Do NOT relax the assertion to make a stray field pass.
    """
    expected = {
        # 12 inputs (was 11 at Phase 3; +ttsConfig in MAIC-502)
        "messages",
        "storeState",
        "availableAgentIds",
        "maxTurns",
        "languageModelId",
        "directorModelId",
        "thinkingConfig",
        "discussionContext",
        "triggerAgentId",
        "userProfile",
        "agentConfigOverrides",
        "ttsConfig",
        # 4 mutable scalars
        "currentAgentId",
        "turnCount",
        "shouldEnd",
        "totalActions",
        # 2 reducer-accumulated lists
        "agentResponses",
        "whiteboardLedger",
    }
    actual = set(OrchestratorState.__annotations__.keys())
    assert actual == expected, (
        f"OrchestratorState field-set drift: "
        f"missing={expected - actual}, extra={actual - expected}"
    )


def test_total_field_count_is_eighteen():
    """Sanity check: 12 inputs + 4 scalars + 2 reducer-lists = 18.

    Phase 3 (MAIC-104.2) bumped the count from 16 → 17 with `directorModelId`.
    Phase 5 (MAIC-502) bumped the count from 17 → 18 with `ttsConfig`.
    """
    assert len(OrchestratorState.__annotations__) == 18


# ── Reducer-merge fields use Annotated[..., add] ───────────────────────


@pytest.mark.parametrize("field_name,inner_type", [
    ("agentResponses", "AgentTurnSummary"),
    ("whiteboardLedger", "WhiteboardActionRecord"),
])
def test_reducer_fields_use_operator_add(field_name, inner_type):
    """The two list-accumulating fields must be Annotated[list[...], operator.add].

    LangGraph reads the second arg of Annotated as the reducer; getting
    this wrong silently overwrites instead of accumulating, which is
    exactly the kind of bug that's invisible in unit tests but breaks
    multi-turn conversation context.
    """
    hints = get_type_hints(OrchestratorState, include_extras=True)
    annotated = hints[field_name]
    # Annotated[list[X], operator.add] → __metadata__ = (operator.add,)
    assert hasattr(annotated, "__metadata__"), (
        f"{field_name} must be typing.Annotated, not raw list"
    )
    metadata = annotated.__metadata__
    assert add in metadata, (
        f"{field_name} reducer must include operator.add; got {metadata}"
    )


# ── total=False ⇒ partial state updates allowed (LangGraph node returns) ──


def test_orchestrator_state_is_partial():
    """LangGraph nodes return partial state dicts (only the fields they
    modify). TypedDict's `total=False` makes that legal at the type
    level."""
    # The cleanest check is __total__ = False on the class.
    assert OrchestratorState.__total__ is False


# ── Supporting TypedDicts: smoke ───────────────────────────────────────


def test_supporting_types_importable_and_have_expected_fields():
    assert "id" in Message.__annotations__
    assert "role" in Message.__annotations__
    assert "content" in Message.__annotations__

    assert "currentSceneId" in StoreState.__annotations__
    assert "scenes" in StoreState.__annotations__
    assert "whiteboardOpen" in StoreState.__annotations__

    # AgentTurnSummary is total=True (no missing fields allowed when used
    # in agentResponses reducer).
    assert {"agentId", "agentName", "contentPreview", "actionCount", "whiteboardActions"} <= set(
        AgentTurnSummary.__annotations__.keys()
    )

    assert {"actionName", "agentId", "agentName", "params"} <= set(
        WhiteboardActionRecord.__annotations__.keys()
    )


# ── Functional integration with langgraph (smoke) ──────────────────────


def test_state_compatible_with_state_graph():
    """Build an empty StateGraph(OrchestratorState) — proves the type is
    accepted by langgraph as a state schema. If langgraph's API for
    schema acceptance changes (e.g. requires a Pydantic class), this
    test catches it before MAIC-005 lands."""
    from langgraph.graph import StateGraph
    g = StateGraph(OrchestratorState)
    # We don't compile (no nodes) — just ensure the constructor accepts it.
    assert g is not None


def test_reducer_actually_merges_when_graph_runs():
    """Hard integration: run a 2-step graph that adds to agentResponses
    in each step, confirm both entries appear in the final state.

    This is the test that would have caught 'reducer silently
    overwrites' if we had used the wrong typing pattern.
    """
    import asyncio
    from langgraph.graph import StateGraph, START, END

    async def step_one(state: OrchestratorState) -> dict:
        return {"agentResponses": [{
            "agentId": "a1", "agentName": "A1",
            "contentPreview": "first", "actionCount": 0,
            "whiteboardActions": [],
        }]}

    async def step_two(state: OrchestratorState) -> dict:
        return {"agentResponses": [{
            "agentId": "a2", "agentName": "A2",
            "contentPreview": "second", "actionCount": 1,
            "whiteboardActions": [],
        }]}

    g = (StateGraph(OrchestratorState)
         .add_node("one", step_one)
         .add_node("two", step_two)
         .add_edge(START, "one")
         .add_edge("one", "two")
         .add_edge("two", END)
         .compile())

    initial: OrchestratorState = {"agentResponses": [], "whiteboardLedger": []}
    final = asyncio.run(g.ainvoke(initial))
    assert len(final["agentResponses"]) == 2, f"reducer didn't merge: {final}"
    assert [r["agentId"] for r in final["agentResponses"]] == ["a1", "a2"]
