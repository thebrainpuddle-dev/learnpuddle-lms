"""Tests for apps.maic.orchestration.registry — agent configuration."""
from __future__ import annotations

import pytest

from apps.maic.orchestration.registry import (
    AgentConfig,
    DEFAULT_AGENTS,
    ROLE_ACTIONS,
    SLIDE_ACTIONS,
    WHITEBOARD_ACTIONS,
    get_actions_for_role,
    get_default_agent,
    list_default_agents,
    resolve_agent,
)


# ── Default-agent lock-set (mirror upstream store.ts:46-191) ──────────


def test_six_default_agents_present():
    assert set(DEFAULT_AGENTS) == {
        "default-1", "default-2", "default-3",
        "default-4", "default-5", "default-6",
    }


def test_default_agents_have_distinct_avatars():
    avatars = [a.avatar for a in DEFAULT_AGENTS.values()]
    assert len(avatars) == len(set(avatars)), f"avatar collision: {avatars}"


def test_default_agents_have_distinct_colors():
    colors = [a.color for a in DEFAULT_AGENTS.values()]
    assert len(colors) == len(set(colors)), f"color collision: {colors}"


def test_default_teacher_has_slide_actions():
    teacher = DEFAULT_AGENTS["default-1"]
    assert teacher.role == "teacher"
    assert "spotlight" in teacher.allowedActions
    assert "laser" in teacher.allowedActions
    assert "play_video" in teacher.allowedActions
    # And whiteboard
    assert "wb_draw_text" in teacher.allowedActions


def test_default_assistant_has_whiteboard_only():
    assistant = DEFAULT_AGENTS["default-2"]
    assert assistant.role == "assistant"
    assert "spotlight" not in assistant.allowedActions
    assert "laser" not in assistant.allowedActions
    # But whiteboard yes
    assert all(a.startswith("wb_") for a in assistant.allowedActions)


def test_default_students_have_whiteboard_only():
    for sid in ("default-3", "default-4", "default-5", "default-6"):
        agent = DEFAULT_AGENTS[sid]
        assert agent.role == "student"
        assert "spotlight" not in agent.allowedActions
        assert all(a.startswith("wb_") for a in agent.allowedActions)


@pytest.mark.parametrize("agent_id", sorted(DEFAULT_AGENTS))
def test_each_default_persona_is_substantive(agent_id):
    """Personas are the agent's voice; an empty/short one indicates a
    port mistake."""
    agent = DEFAULT_AGENTS[agent_id]
    assert len(agent.persona) > 300, (
        f"{agent_id} persona too short ({len(agent.persona)} chars) — "
        "likely a botched verbatim port"
    )


def test_priority_ordering_lists_teacher_first():
    ranked = list_default_agents()
    assert ranked[0].id == "default-1"  # teacher, priority=10
    # non-increasing priority
    priorities = [a.priority for a in ranked]
    assert priorities == sorted(priorities, reverse=True)


# ── Role action mapping ────────────────────────────────────────────────


def test_role_actions_teacher_includes_slide_and_whiteboard():
    actions = ROLE_ACTIONS["teacher"]
    assert set(SLIDE_ACTIONS) <= set(actions)
    assert set(WHITEBOARD_ACTIONS) <= set(actions)


def test_role_actions_assistant_no_slide():
    actions = ROLE_ACTIONS["assistant"]
    assert set(WHITEBOARD_ACTIONS) <= set(actions)
    assert not (set(SLIDE_ACTIONS) & set(actions))


def test_get_actions_for_unknown_role_falls_back_to_whiteboard():
    """Unknown role = least-privilege default. Generated agents with
    weird role labels never escalate to slide control."""
    result = get_actions_for_role("totally-made-up-role")
    assert result == [*WHITEBOARD_ACTIONS]
    assert not (set(SLIDE_ACTIONS) & set(result))


# ── resolve_agent ─────────────────────────────────────────────────────


def test_resolve_default_agent():
    agent = resolve_agent("default-1")
    assert agent is not None
    assert agent.id == "default-1"


def test_resolve_unknown_returns_none():
    assert resolve_agent("nonexistent-id") is None


def test_resolve_request_override_wins_over_default():
    """When a request-scoped override exists for default-1, it takes
    precedence (matches upstream director-graph.ts:82-84)."""
    override_payload = {
        "default-1": {
            "id": "default-1",
            "name": "Custom Teacher",
            "role": "teacher",
            "persona": "x" * 100,
            "avatar": "/x.png",
            "color": "#000000",
            "allowedActions": ["speech"],
            "priority": 5,
            "isDefault": False,
        },
    }
    agent = resolve_agent("default-1", override_payload)
    assert agent is not None
    assert agent.name == "Custom Teacher"
    assert agent.allowedActions == ["speech"]


def test_resolve_falls_back_to_default_when_override_lookup_misses():
    overrides = {
        "different-id": {
            "id": "different-id", "name": "X", "role": "teacher",
            "persona": "y" * 100, "avatar": "/x.png", "color": "#000",
            "allowedActions": [], "priority": 1, "isDefault": False,
        },
    }
    agent = resolve_agent("default-1", overrides)
    # The override map is non-empty but doesn't contain default-1, so
    # we fall through to the built-in default.
    assert agent is not None
    assert agent.id == "default-1"
    assert agent.name == "AI teacher"


def test_resolve_drops_invalid_override_silently():
    """A malformed override payload (missing required field) makes
    resolve_agent return None — better to drop the agent than dispatch
    a half-configured one."""
    bad = {"default-1": {"id": "default-1", "name": "X"}}  # missing many fields
    assert resolve_agent("default-1", bad) is None


def test_resolve_with_no_overrides_arg():
    """The overrides parameter is optional — production WS path passes
    None when state.agentConfigOverrides is empty."""
    agent = resolve_agent("default-2", None)
    assert agent is not None
    assert agent.id == "default-2"
