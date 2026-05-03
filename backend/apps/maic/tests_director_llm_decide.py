"""Tests for _director_llm_decide (MAIC-104.1).

Real stream_text — no mocks per CLAUDE.md hard rule. We use two
production providers:

  - "stub-director" — the new dev/test provider that returns
    deterministic JSON decisions. Same pattern as the existing "stub"
    provider; both are real production code.

  - "stub" — agent-generate's stub. When the director uses this, it
    parses the JSON-array stub output as a director decision (which
    will fail the regex extract) → fallback to round-robin.

Round-robin fallback testing exercises the real production fallback
path that fires when an LLM returns garbage.
"""
from __future__ import annotations

import pytest

from apps.maic.orchestration.ai_adapter import (
    reset_director_stub_counter,
)
from apps.maic.orchestration.director_graph import (
    _director_llm_decide,
    _looks_like_explicit_end,
    _round_robin_fallback,
    _build_conversation_summary,
)
from apps.maic.orchestration.director_prompt import DirectorDecision


@pytest.fixture(autouse=True)
def reset_stub():
    """Reset the director-stub counter so tests are deterministic."""
    reset_director_stub_counter()
    yield
    reset_director_stub_counter()


# ── _round_robin_fallback ──────────────────────────────────────────


class TestRoundRobinFallback:
    def test_no_agents_returns_end(self):
        result = _round_robin_fallback({"availableAgentIds": []})
        assert result == DirectorDecision(next_agent_id=None, should_end=True)

    def test_no_agents_field_returns_end(self):
        result = _round_robin_fallback({})
        assert result == DirectorDecision(next_agent_id=None, should_end=True)

    def test_no_responses_picks_first(self):
        result = _round_robin_fallback(
            {"availableAgentIds": ["default-1", "default-3", "default-4"]}
        )
        assert result == DirectorDecision(next_agent_id="default-1", should_end=False)

    def test_picks_next_after_last_responder(self):
        result = _round_robin_fallback(
            {
                "availableAgentIds": ["default-1", "default-3", "default-4"],
                "agentResponses": [
                    {"agentId": "default-1", "agentName": "T", "contentPreview": "x", "actionCount": 0, "whiteboardActions": []},
                ],
            }
        )
        assert result == DirectorDecision(next_agent_id="default-3", should_end=False)

    def test_wraps_at_end_of_list(self):
        result = _round_robin_fallback(
            {
                "availableAgentIds": ["default-1", "default-3", "default-4"],
                "agentResponses": [
                    {"agentId": "default-4", "agentName": "T", "contentPreview": "x", "actionCount": 0, "whiteboardActions": []},
                ],
            }
        )
        assert result == DirectorDecision(next_agent_id="default-1", should_end=False)

    def test_unknown_last_responder_picks_first(self):
        # Defensive: if the last responder somehow isn't in the
        # available list, pick the first available rather than crashing.
        result = _round_robin_fallback(
            {
                "availableAgentIds": ["default-1", "default-3"],
                "agentResponses": [
                    {"agentId": "default-99", "agentName": "X", "contentPreview": "x", "actionCount": 0, "whiteboardActions": []},
                ],
            }
        )
        assert result == DirectorDecision(next_agent_id="default-1", should_end=False)


# ── _looks_like_explicit_end ───────────────────────────────────────


class TestLooksLikeExplicitEnd:
    def test_explicit_next_agent_end(self):
        assert _looks_like_explicit_end('{"next_agent": "END"}') is True

    def test_lowercase_end_still_matches(self):
        assert _looks_like_explicit_end('{"next_agent": "end"}') is True

    def test_should_end_true_marker(self):
        assert _looks_like_explicit_end('{"shouldEnd": true}') is True

    def test_no_marker_returns_false(self):
        assert _looks_like_explicit_end("I cannot decide.") is False

    def test_empty_string_returns_false(self):
        assert _looks_like_explicit_end("") is False


# ── _build_conversation_summary ───────────────────────────────────


class TestBuildConversationSummary:
    def test_empty_messages(self):
        assert _build_conversation_summary({"messages": []}) == ""

    def test_renders_recent_messages(self):
        messages = [
            {"role": "user", "content": "What are fractions?"},
            {"role": "assistant", "content": "A fraction is..."},
        ]
        summary = _build_conversation_summary({"messages": messages})
        assert "What are fractions?" in summary
        assert "A fraction is..." in summary

    def test_truncates_long_content(self):
        long_text = "x" * 500
        summary = _build_conversation_summary(
            {"messages": [{"role": "user", "content": long_text}]}
        )
        # 200-char cap + role prefix
        assert len(summary) < 300

    def test_keeps_only_last_4(self):
        messages = [
            {"role": "user", "content": f"msg-{i}"} for i in range(10)
        ]
        summary = _build_conversation_summary({"messages": messages})
        assert "msg-9" in summary
        assert "msg-0" not in summary


# ── _director_llm_decide — real stub-director path ────────────────


@pytest.mark.asyncio
async def test_decide_with_stub_director_returns_first_agent():
    """First call to stub-director returns 'default-1' per
    DIRECTOR_STUB_OUTPUTS."""
    state = {
        "availableAgentIds": ["default-1", "default-3", "default-4"],
        "languageModelId": "stub-director",
        "turnCount": 1,
    }
    decision = await _director_llm_decide(state)
    assert decision == DirectorDecision(next_agent_id="default-1", should_end=False)


@pytest.mark.asyncio
async def test_decide_with_stub_director_cycles():
    """Successive calls cycle through DIRECTOR_STUB_OUTPUTS."""
    state = {
        "availableAgentIds": ["default-1", "default-3", "default-4"],
        "languageModelId": "stub-director",
        "turnCount": 1,
    }
    d1 = await _director_llm_decide(state)
    d2 = await _director_llm_decide(state)
    d3 = await _director_llm_decide(state)
    d4 = await _director_llm_decide(state)
    assert d1.next_agent_id == "default-1"
    assert d2.next_agent_id == "default-3"
    assert d3.next_agent_id == "default-4"
    assert d4 == DirectorDecision(next_agent_id=None, should_end=True)  # END


@pytest.mark.asyncio
async def test_decide_falls_back_when_stub_returns_garbage():
    """Using the agent-generate "stub" provider returns a JSON array
    that doesn't match the director's `next_agent` regex → parse fails
    → round-robin fallback fires (not should_end=True)."""
    state = {
        "availableAgentIds": ["default-1", "default-3", "default-4"],
        "languageModelId": "stub",  # NOT stub-director
        "turnCount": 1,
        "agentResponses": [],
    }
    decision = await _director_llm_decide(state)
    # Round-robin: no responders yet → first agent
    assert decision == DirectorDecision(next_agent_id="default-1", should_end=False)


@pytest.mark.asyncio
async def test_decide_falls_back_uses_last_responder_for_round_robin():
    """When the parser fails, fallback should pick next-after-last-
    responder, not always the first agent."""
    state = {
        "availableAgentIds": ["default-1", "default-3", "default-4"],
        "languageModelId": "stub",  # garbage output → parse failure
        "turnCount": 2,
        "agentResponses": [
            {"agentId": "default-1", "agentName": "T", "contentPreview": "intro", "actionCount": 0, "whiteboardActions": []},
        ],
    }
    decision = await _director_llm_decide(state)
    assert decision == DirectorDecision(next_agent_id="default-3", should_end=False)


@pytest.mark.asyncio
async def test_decide_with_no_resolvable_agents_returns_end():
    state = {
        "availableAgentIds": ["unknown-agent-xyz"],
        "languageModelId": "stub-director",
        "turnCount": 1,
    }
    decision = await _director_llm_decide(state)
    assert decision == DirectorDecision(next_agent_id=None, should_end=True)


@pytest.mark.asyncio
async def test_decide_rejects_llm_choice_outside_available_pool():
    """If the LLM picks an agent that isn't in availableAgentIds,
    fallback to round-robin instead of trusting the bad pick.

    We can't easily force the stub-director to pick a non-available
    agent, but we can rotate the stub past 'default-1' and then offer
    only ['default-3'] — the stub will return 'default-1' (round 0)
    which is NOT in available → fallback fires.
    """
    state = {
        "availableAgentIds": ["default-3"],
        "languageModelId": "stub-director",
        "turnCount": 1,
    }
    # First call returns 'default-1', not in available → fallback
    decision = await _director_llm_decide(state)
    # Round-robin fallback with no prior responders + single available
    # agent → pick that agent.
    assert decision == DirectorDecision(next_agent_id="default-3", should_end=False)


@pytest.mark.asyncio
async def test_decide_honors_explicit_end_from_llm():
    """Skip past the first 3 stub outputs to reach the END one (4th)."""
    state = {
        "availableAgentIds": ["default-1", "default-3", "default-4"],
        "languageModelId": "stub-director",
        "turnCount": 1,
    }
    # Burn 3 calls to advance the counter
    await _director_llm_decide(state)
    await _director_llm_decide(state)
    await _director_llm_decide(state)
    # 4th call should return END
    decision = await _director_llm_decide(state)
    assert decision == DirectorDecision(next_agent_id=None, should_end=True)
