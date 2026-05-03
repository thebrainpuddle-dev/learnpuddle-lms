"""Tests for apps.maic.orchestration.tool_schemas."""
from __future__ import annotations

import pytest

from apps.maic.orchestration.tool_schemas import (
    _ACTION_DESCRIPTIONS,
    get_action_descriptions,
    get_effective_actions,
)


# ── get_effective_actions ─────────────────────────────────────────────


def test_no_scene_type_returns_full_list():
    actions = ["spotlight", "laser", "speech", "wb_draw_text"]
    assert get_effective_actions(actions) == actions


def test_slide_scene_returns_full_list():
    actions = ["spotlight", "laser", "speech", "wb_draw_text"]
    assert get_effective_actions(actions, "slide") == actions


def test_non_slide_scene_strips_slide_only():
    actions = ["spotlight", "laser", "speech", "wb_draw_text"]
    out = get_effective_actions(actions, "quiz")
    assert "spotlight" not in out
    assert "laser" not in out
    assert "speech" in out
    assert "wb_draw_text" in out


def test_filter_does_not_mutate_input():
    """The slide-only filter must return a NEW list — caller's list is
    typically `agent.allowedActions` and we don't want to corrupt the
    registry's stored values."""
    actions = ["spotlight", "wb_draw_text"]
    result = get_effective_actions(actions, "interactive")
    assert actions == ["spotlight", "wb_draw_text"]  # input unchanged
    assert result == ["wb_draw_text"]


@pytest.mark.parametrize("scene_type", ["interactive", "quiz", "code", "diagram", "game"])
def test_non_slide_scenes_all_strip_slide_only(scene_type):
    actions = ["spotlight", "laser", "speech"]
    assert "spotlight" not in get_effective_actions(actions, scene_type)
    assert "laser" not in get_effective_actions(actions, scene_type)


# ── discussion survives the scene filter (MAIC-110.2) ────────────────


@pytest.mark.parametrize(
    "scene_type",
    [None, "slide", "whiteboard", "interactive", "quiz", "code", "diagram", "game"],
)
def test_discussion_survives_every_scene_type(scene_type):
    """`discussion` is teacher/assistant-spawnable on every scene type.
    Phase 1 introduced the slide filter (spotlight/laser only on
    slide-typed scenes); Phase 3 (MAIC-110.2) confirms the same filter
    does NOT mistakenly strip `discussion`. Mirrors upstream's
    SLIDE_ONLY_ACTIONS = {'spotlight', 'laser'} — `discussion` is
    not slide-only."""
    actions = ["spotlight", "laser", "discussion", "wb_draw_text", "speech"]
    out = get_effective_actions(actions, scene_type)
    assert "discussion" in out, f"discussion stripped on scene_type={scene_type!r}"


def test_discussion_in_default_teacher_survives_non_slide_scene():
    """Real-world wiring: a default-1 (teacher) on a whiteboard scene
    should still see `discussion` in their effective action list."""
    from apps.maic.orchestration.registry import DEFAULT_AGENTS

    teacher = DEFAULT_AGENTS["default-1"]
    out = get_effective_actions(teacher.allowedActions, "whiteboard")
    assert "discussion" in out
    assert "spotlight" not in out  # slide-only, correctly stripped
    assert "laser" not in out


# ── get_action_descriptions ───────────────────────────────────────────


def test_empty_allowed_returns_no_actions_message():
    out = get_action_descriptions([])
    assert "no actions" in out.lower()
    assert "speak to students" in out.lower()


def test_descriptions_render_known_actions_with_dash_prefix():
    out = get_action_descriptions(["spotlight", "wb_draw_text"])
    assert out.startswith("- spotlight:")
    assert "\n- wb_draw_text:" in out


def test_descriptions_skip_unknown_actions():
    """A typo in allowed_actions (or a future-action not yet described
    here) is silently skipped — the system prompt is best-effort, not
    a security gate."""
    out = get_action_descriptions(["spotlight", "totally-unknown"])
    assert "- spotlight:" in out
    assert "totally-unknown" not in out


def test_descriptions_preserve_caller_order():
    """Order of action descriptions follows the order of allowed_actions
    (so the prompt builder can put high-priority actions first)."""
    out = get_action_descriptions(["wb_draw_text", "spotlight"])
    text_idx = out.index("- wb_draw_text:")
    spot_idx = out.index("- spotlight:")
    assert text_idx < spot_idx


def test_all_documented_actions_match_protocol_or_speech():
    """Every key in _ACTION_DESCRIPTIONS must be a known action type
    from the protocol. (`speech` and `widget_*` are described by
    separate prompt sections upstream and are not in this map; from
    MAIC-110.2 onward `discussion` IS described here so the agent
    prompt knows the schema for the discussion action.)

    Concretely: every description key must be in ALL_ACTION_TYPES."""
    from apps.maic.protocol import ALL_ACTION_TYPES
    described = set(_ACTION_DESCRIPTIONS)
    unknown = described - ALL_ACTION_TYPES
    assert not unknown, f"_ACTION_DESCRIPTIONS contains non-action types: {unknown}"


def test_discussion_description_is_present_and_substantive():
    """MAIC-110.2: `discussion` must have a description so the prompt
    builder includes it in the agent's tool list. Without this, even
    if `discussion` is in allowedActions, get_action_descriptions
    silently drops it (it filters by description presence)."""
    out = get_action_descriptions(["discussion"])
    assert out.startswith("- discussion:")
    # Must mention both required parameters and the user-facing UX hook
    lower = out.lower()
    assert "topic" in lower
    assert "prompt" in lower
    assert "live" in lower or "user" in lower


def test_includes_descriptions_for_all_slide_and_whiteboard_actions():
    """Spot-check: every WHITEBOARD_ACTION + every SLIDE_ACTION from
    the registry should have a description (so a teacher agent never
    sees an undocumented action in their prompt)."""
    from apps.maic.orchestration.registry import SLIDE_ACTIONS, WHITEBOARD_ACTIONS
    described = set(_ACTION_DESCRIPTIONS)
    missing = (set(WHITEBOARD_ACTIONS) | set(SLIDE_ACTIONS)) - described
    assert not missing, f"actions in registry without prompt descriptions: {missing}"
