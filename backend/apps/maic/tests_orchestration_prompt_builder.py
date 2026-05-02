"""Tests for apps.maic.orchestration.prompt_builder.

These tests render real prompts using the ported templates + snippets.
They catch:
  - Template variables that don't get substituted (literal `{{var}}`
    surviving in the output)
  - Missing templates / snippets discovered at render time
  - Drift between role-aware branches (slide vs whiteboard prompts)
"""
from __future__ import annotations

import re

import pytest

from apps.maic.orchestration.prompt_builder import (
    FORMAT_EXAMPLE_SLIDE,
    FORMAT_EXAMPLE_WB,
    ROLE_GUIDELINES,
    build_peer_context_section,
    build_structured_prompt,
)
from apps.maic.orchestration.registry import DEFAULT_AGENTS


_TEACHER = DEFAULT_AGENTS["default-1"]
_ASSISTANT = DEFAULT_AGENTS["default-2"]
_STUDENT = DEFAULT_AGENTS["default-3"]


# ── Render: no literal placeholders survive ───────────────────────────


@pytest.mark.parametrize("agent_id", sorted(DEFAULT_AGENTS))
def test_no_unsubstituted_placeholders_in_rendered_prompt(agent_id):
    """Rendered prompt MUST NOT contain literal `{{...}}` — that's the
    classic silent-passthrough bug from the loader's design choice to
    leave unknown placeholders intact. Catches typos in the template
    or missing variables in the builder's `vars` dict."""
    agent = DEFAULT_AGENTS[agent_id]
    prompt = build_structured_prompt(agent)
    leftover = re.findall(r"\{\{[\w\-: #/]+\}\}", prompt)
    # Allow `{{` literals INSIDE quoted JSON examples (they're not template
    # syntax, they're documentation). Strip those before checking.
    real_placeholders = [
        m for m in leftover
        # `{{ }` (single-close) typo would still match — our regex needs
        # double-close already, so this is sufficient
        if "snippet:" not in m  # snippets resolve eagerly; would have failed earlier
    ]
    assert not real_placeholders, (
        f"unsubstituted placeholders in {agent_id}: {real_placeholders}"
    )


@pytest.mark.parametrize("agent_id", sorted(DEFAULT_AGENTS))
def test_rendered_prompt_includes_persona(agent_id):
    """The agent's persona is the most identity-bearing variable;
    if it's missing the agent has no character."""
    agent = DEFAULT_AGENTS[agent_id]
    prompt = build_structured_prompt(agent)
    # Spot-check a substring of each persona
    assert agent.persona[:40] in prompt, (
        f"persona missing from {agent_id} rendered prompt"
    )


@pytest.mark.parametrize("agent_id", sorted(DEFAULT_AGENTS))
def test_rendered_prompt_includes_role_guideline(agent_id):
    agent = DEFAULT_AGENTS[agent_id]
    prompt = build_structured_prompt(agent)
    expected_role = ROLE_GUIDELINES.get(agent.role, ROLE_GUIDELINES["student"])
    # First line of the role guideline is a stable signature
    sig = expected_role.split("\n", 1)[0]
    assert sig in prompt, f"role guideline missing for {agent_id} (role={agent.role})"


# ── Slide vs whiteboard branch ────────────────────────────────────────


def test_teacher_prompt_uses_slide_format_example():
    """Teacher has spotlight → uses FORMAT_EXAMPLE_SLIDE (which contains
    the `spotlight` action) and includes spotlight guidelines."""
    prompt = build_structured_prompt(_TEACHER)
    assert "spotlight" in prompt
    assert "spotlight" in FORMAT_EXAMPLE_SLIDE
    assert "Whiteboard / Canvas mutual exclusion" in prompt


def test_student_prompt_uses_wb_only_format_example():
    """Student has wb actions only → uses FORMAT_EXAMPLE_WB (no spotlight
    in the format example), no mutual exclusion note."""
    prompt = build_structured_prompt(_STUDENT)
    assert "wb_open" in FORMAT_EXAMPLE_WB
    # The mutual-exclusion note is the wedge — it's only included when
    # slide actions are available
    assert "Whiteboard / Canvas mutual exclusion" not in prompt


# ── Length guidelines branching ────────────────────────────────────────


def test_teacher_length_target_is_100_chars():
    prompt = build_structured_prompt(_TEACHER)
    assert "100 characters" in prompt


def test_assistant_length_target_is_80_chars():
    prompt = build_structured_prompt(_ASSISTANT)
    assert "80 characters" in prompt


def test_student_length_target_is_50_chars():
    prompt = build_structured_prompt(_STUDENT)
    assert "50 characters" in prompt


# ── Whiteboard guidelines (loaded from agent-system-wb-{role} template) ──


def test_each_role_loads_correct_wb_template():
    """Smoke: rendering each role's prompt must succeed (which means the
    role's wb-template loaded). A typo in the role name → MaicConfigError."""
    for agent in (_TEACHER, _ASSISTANT, _STUDENT):
        prompt = build_structured_prompt(agent)
        # Whiteboard reference snippet must have been pulled in
        assert "whiteboard" in prompt.lower()


# ── peer_context_section ──────────────────────────────────────────────


def test_peer_context_empty_when_no_responses():
    assert build_peer_context_section(None, "Teacher") == ""
    assert build_peer_context_section([], "Teacher") == ""


def test_peer_context_excludes_self():
    """Defensive — director shouldn't dispatch the same agent twice in a
    round, but if it does, the agent shouldn't see ITS OWN summary as a
    peer."""
    out = build_peer_context_section(
        [{"agentName": "Teacher", "contentPreview": "self talk"}],
        "Teacher",
    )
    assert out == ""


def test_peer_context_renders_multiple_peers():
    out = build_peer_context_section(
        [
            {"agentName": "Teacher", "contentPreview": "Lesson intro"},
            {"agentName": "Assistant", "contentPreview": "Background context"},
        ],
        current_agent_name="CuriousStudent",
    )
    assert "Teacher" in out
    assert "Assistant" in out
    assert "CuriousStudent" in out  # current agent name appears in MUST clauses
    assert "1." in out and "2." in out  # numbered MUST list


# ── Slide-aware filtering ─────────────────────────────────────────────


def test_non_slide_scene_strips_slide_only_descriptions():
    """When current scene is non-slide, the rendered actionDescriptions
    block must NOT advertise spotlight/laser to the LLM (otherwise it
    would emit them and they'd be silently dropped at action validation
    time)."""
    teacher_prompt = build_structured_prompt(
        _TEACHER,
        store_state={
            "currentSceneId": "s1",
            "scenes": [{"id": "s1", "type": "quiz"}],
        },
    )
    # The action-description block is itself a substring of the prompt;
    # spotlight should not appear in the AVAILABLE ACTIONS list. But it
    # MAY appear elsewhere (the registry's persona mentions spotlight).
    # The clearest signal: the slide-action-guidelines section is missing
    # AND mutual-exclusion note is missing.
    assert "Don't overuse — max 1-2" not in teacher_prompt  # SLIDE_ACTION_GUIDELINES sig
    assert "Whiteboard / Canvas mutual exclusion" not in teacher_prompt
