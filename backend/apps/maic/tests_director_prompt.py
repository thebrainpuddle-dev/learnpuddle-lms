"""Tests for apps/maic/orchestration/director_prompt.py (MAIC-104a).

Real prompt loader, real template, real string interpolation — no
mocks per the no-fakes rule. The director template at
apps/maic/prompts/templates/director/system.md is byte-identical to
upstream's; this test exercises the real loader against it.
"""
from __future__ import annotations

import pytest

from apps.maic.orchestration.director_prompt import (
    DirectorDecision,
    build_director_prompt,
    build_whiteboard_state_for_director,
    parse_director_decision,
    summarize_whiteboard_for_director,
)
from apps.maic.orchestration.registry import DEFAULT_AGENTS


# ── parse_director_decision ────────────────────────────────────────


class TestParseDirectorDecision:
    def test_parses_clean_json_with_agent_id(self):
        result = parse_director_decision('{"next_agent": "default-3"}')
        assert result == DirectorDecision(next_agent_id="default-3", should_end=False)

    def test_extracts_json_from_prose_wrapper(self):
        # LLMs love to add explanations
        content = (
            "Based on the conversation flow and the teacher having "
            'already spoken, my decision is: {"next_agent": "default-4", '
            '"reasoning": "curious student should ask the follow-up"}'
        )
        result = parse_director_decision(content)
        assert result.next_agent_id == "default-4"
        assert result.should_end is False

    def test_end_string_returns_should_end_true(self):
        result = parse_director_decision('{"next_agent": "END"}')
        assert result == DirectorDecision(next_agent_id=None, should_end=True)

    def test_null_next_agent_returns_should_end_true(self):
        result = parse_director_decision('{"next_agent": null}')
        assert result == DirectorDecision(next_agent_id=None, should_end=True)

    def test_missing_next_agent_key(self):
        # No key matching the regex → no JSON match → end
        result = parse_director_decision('{"foo": "bar"}')
        assert result.should_end is True
        assert result.next_agent_id is None

    def test_malformed_json_falls_back_to_end(self):
        # Regex matches the leading brace but JSON is broken
        result = parse_director_decision(
            '{"next_agent": "default-1", broken[]}'
        )
        assert result == DirectorDecision(next_agent_id=None, should_end=True)

    def test_empty_content_returns_end(self):
        result = parse_director_decision("")
        assert result == DirectorDecision(next_agent_id=None, should_end=True)

    def test_non_string_next_agent_returns_end(self):
        # Defensive against the LLM emitting a number or array
        result = parse_director_decision('{"next_agent": 42}')
        assert result == DirectorDecision(next_agent_id=None, should_end=True)

    def test_no_json_at_all_returns_end(self):
        result = parse_director_decision("I cannot make a decision.")
        assert result == DirectorDecision(next_agent_id=None, should_end=True)


# ── summarize_whiteboard_for_director ──────────────────────────────


class TestSummarizeWhiteboard:
    def test_empty_ledger(self):
        result = summarize_whiteboard_for_director([])
        assert result == {"element_count": 0, "contributors": []}

    def test_counts_draw_actions(self):
        ledger = [
            {"actionName": "wb_open", "agentName": "AI teacher", "params": {}},
            {"actionName": "wb_draw_text", "agentName": "AI teacher", "params": {"content": "hi"}},
            {"actionName": "wb_draw_shape", "agentName": "AI teacher", "params": {"shape": "circle"}},
            {"actionName": "wb_draw_text", "agentName": "AI助教", "params": {"content": "yo"}},
        ]
        result = summarize_whiteboard_for_director(ledger)
        assert result["element_count"] == 3  # 2 text + 1 shape; open doesn't count
        assert set(result["contributors"]) == {"AI teacher", "AI助教"}

    def test_wb_clear_resets_count_but_keeps_contributors(self):
        ledger = [
            {"actionName": "wb_draw_text", "agentName": "alice", "params": {"content": "x"}},
            {"actionName": "wb_draw_text", "agentName": "bob", "params": {"content": "y"}},
            {"actionName": "wb_clear", "agentName": "alice", "params": {}},
            {"actionName": "wb_draw_text", "agentName": "alice", "params": {"content": "z"}},
        ]
        result = summarize_whiteboard_for_director(ledger)
        assert result["element_count"] == 1  # clear reset, then 1 added
        # alice + bob still listed (mirrors upstream's "they still participated")
        assert set(result["contributors"]) == {"alice", "bob"}

    def test_wb_delete_decrements_count(self):
        ledger = [
            {"actionName": "wb_draw_text", "agentName": "a", "params": {}},
            {"actionName": "wb_draw_text", "agentName": "a", "params": {}},
            {"actionName": "wb_delete", "agentName": "a", "params": {"elementId": "t1"}},
        ]
        result = summarize_whiteboard_for_director(ledger)
        assert result["element_count"] == 1

    def test_wb_delete_clamps_at_zero(self):
        ledger = [
            {"actionName": "wb_delete", "agentName": "a", "params": {"elementId": "t1"}},
        ]
        result = summarize_whiteboard_for_director(ledger)
        assert result["element_count"] == 0


# ── build_whiteboard_state_for_director ────────────────────────────


class TestBuildWhiteboardState:
    def test_empty_ledger_returns_empty_string(self):
        assert build_whiteboard_state_for_director(None) == ""
        assert build_whiteboard_state_for_director([]) == ""

    def test_renders_count_and_contributors(self):
        ledger = [
            {"actionName": "wb_draw_text", "agentName": "AI teacher", "params": {}},
            {"actionName": "wb_draw_shape", "agentName": "AI助教", "params": {}},
        ]
        rendered = build_whiteboard_state_for_director(ledger)
        assert "# Whiteboard State" in rendered
        assert "Elements on whiteboard: 2" in rendered
        assert "AI teacher" in rendered
        assert "AI助教" in rendered

    def test_emits_crowded_warning_above_5(self):
        ledger = [
            {"actionName": "wb_draw_text", "agentName": "a", "params": {}}
            for _ in range(6)
        ]
        rendered = build_whiteboard_state_for_director(ledger)
        assert "crowded" in rendered.lower() or "⚠" in rendered

    def test_no_warning_at_or_below_5(self):
        ledger = [
            {"actionName": "wb_draw_text", "agentName": "a", "params": {}}
            for _ in range(5)
        ]
        rendered = build_whiteboard_state_for_director(ledger)
        assert "crowded" not in rendered.lower()


# ── build_director_prompt ──────────────────────────────────────────


class TestBuildDirectorPrompt:
    def test_renders_with_three_default_agents(self):
        agents = [DEFAULT_AGENTS[k] for k in ("default-1", "default-3", "default-4")]
        prompt = build_director_prompt(
            agents=agents,
            conversation_summary="The student asked about derivatives.",
            agent_responses=[],
            turn_count=0,
        )
        assert isinstance(prompt, str)
        assert len(prompt) > 100  # not the empty / unrendered template
        # Each agent appears in the rendered prompt
        for a in agents:
            assert a.id in prompt
            assert a.name in prompt

    def test_responded_list_renders_when_agents_have_spoken(self):
        agents = [DEFAULT_AGENTS["default-1"], DEFAULT_AGENTS["default-3"]]
        prompt = build_director_prompt(
            agents=agents,
            conversation_summary="",
            agent_responses=[
                {
                    "agentId": "default-1",
                    "agentName": "AI teacher",
                    "contentPreview": "Today we discuss fractions.",
                    "actionCount": 1,
                    "whiteboardActions": [],
                },
            ],
            turn_count=1,
        )
        assert "AI teacher" in prompt
        assert "Today we discuss fractions" in prompt

    def test_no_responses_yields_none_yet_marker(self):
        agents = [DEFAULT_AGENTS["default-1"]]
        prompt = build_director_prompt(
            agents=agents,
            conversation_summary="",
            agent_responses=[],
            turn_count=0,
        )
        assert "None yet" in prompt

    def test_discussion_mode_block(self):
        agents = [DEFAULT_AGENTS["default-1"], DEFAULT_AGENTS["default-3"]]
        prompt = build_director_prompt(
            agents=agents,
            conversation_summary="",
            agent_responses=[],
            turn_count=2,
            discussion_context={"topic": "edge cases", "prompt": "what about NaN?"},
            trigger_agent_id="default-3",
        )
        assert "Discussion Mode" in prompt
        assert "edge cases" in prompt
        assert "what about NaN?" in prompt
        # rule1 in discussion mode mentions the initiator
        assert "default-3" in prompt

    def test_user_profile_section(self):
        agents = [DEFAULT_AGENTS["default-1"]]
        prompt = build_director_prompt(
            agents=agents,
            conversation_summary="",
            agent_responses=[],
            turn_count=0,
            user_profile={"nickname": "Aanya", "bio": "Class 8 student in Pune"},
        )
        assert "Aanya" in prompt
        assert "Pune" in prompt

    def test_whiteboard_section_included_when_ledger_nonempty(self):
        agents = [DEFAULT_AGENTS["default-1"]]
        prompt = build_director_prompt(
            agents=agents,
            conversation_summary="",
            agent_responses=[],
            turn_count=0,
            whiteboard_ledger=[
                {"actionName": "wb_draw_text", "agentName": "AI teacher", "params": {}},
            ],
        )
        assert "Elements on whiteboard: 1" in prompt
        assert "AI teacher" in prompt

    def test_whiteboard_open_text_branches(self):
        agents = [DEFAULT_AGENTS["default-1"]]
        open_prompt = build_director_prompt(
            agents=agents,
            conversation_summary="",
            agent_responses=[],
            turn_count=0,
            whiteboard_open=True,
        )
        assert "OPEN" in open_prompt
        closed_prompt = build_director_prompt(
            agents=agents,
            conversation_summary="",
            agent_responses=[],
            turn_count=0,
            whiteboard_open=False,
        )
        assert "CLOSED" in closed_prompt

    def test_turn_count_renders_one_indexed(self):
        agents = [DEFAULT_AGENTS["default-1"]]
        prompt = build_director_prompt(
            agents=agents,
            conversation_summary="",
            agent_responses=[],
            turn_count=0,
        )
        # turnCountPlusOne = 1
        assert "1" in prompt  # weak; stronger check below
        prompt2 = build_director_prompt(
            agents=agents,
            conversation_summary="",
            agent_responses=[],
            turn_count=4,
        )
        # turnCountPlusOne = 5
        assert "5" in prompt2

    def test_conversation_summary_appears_verbatim(self):
        agents = [DEFAULT_AGENTS["default-1"]]
        summary = "The student is curious about edge cases in floating-point arithmetic."
        prompt = build_director_prompt(
            agents=agents,
            conversation_summary=summary,
            agent_responses=[],
            turn_count=0,
        )
        assert summary in prompt


# ── Whiteboard summary in agent_responses ──────────────────────────


class TestAgentResponseWhiteboardSummary:
    def test_text_action_summary(self):
        agents = [DEFAULT_AGENTS["default-1"]]
        prompt = build_director_prompt(
            agents=agents,
            conversation_summary="",
            agent_responses=[
                {
                    "agentId": "default-1",
                    "agentName": "AI teacher",
                    "contentPreview": "Hello",
                    "actionCount": 1,
                    "whiteboardActions": [
                        {
                            "actionName": "wb_draw_text",
                            "agentId": "default-1",
                            "agentName": "AI teacher",
                            "params": {"content": "Welcome to fractions!"},
                        },
                    ],
                },
            ],
            turn_count=1,
        )
        assert 'drew text "Welcome to fractions!"' in prompt

    def test_table_action_summary_includes_dimensions(self):
        agents = [DEFAULT_AGENTS["default-1"]]
        prompt = build_director_prompt(
            agents=agents,
            conversation_summary="",
            agent_responses=[
                {
                    "agentId": "default-1",
                    "agentName": "AI teacher",
                    "contentPreview": "x",
                    "actionCount": 1,
                    "whiteboardActions": [
                        {
                            "actionName": "wb_draw_table",
                            "agentId": "default-1",
                            "agentName": "AI teacher",
                            "params": {"data": [["a", "b"], ["1", "2"], ["3", "4"]]},
                        },
                    ],
                },
            ],
            turn_count=1,
        )
        assert "drew table(3×2)" in prompt

    def test_chart_action_summary_includes_type_and_labels(self):
        agents = [DEFAULT_AGENTS["default-1"]]
        prompt = build_director_prompt(
            agents=agents,
            conversation_summary="",
            agent_responses=[
                {
                    "agentId": "default-1",
                    "agentName": "AI teacher",
                    "contentPreview": "x",
                    "actionCount": 1,
                    "whiteboardActions": [
                        {
                            "actionName": "wb_draw_chart",
                            "agentId": "default-1",
                            "agentName": "AI teacher",
                            "params": {
                                "chartType": "pie",
                                "data": {"labels": ["Q1", "Q2", "Q3", "Q4"]},
                            },
                        },
                    ],
                },
            ],
            turn_count=1,
        )
        assert "drew chart(pie" in prompt
        assert "Q1,Q2,Q3,Q4" in prompt
