"""Tests for `apps.maic.generation.action_parser` (MAIC-424)."""
from __future__ import annotations

import json

from apps.maic.generation.action_parser import (
    parse_actions_from_structured_output,
)
from apps.maic.protocol import validate_action


# ── Happy path ────────────────────────────────────────────────────


def test_parses_text_and_action_items_in_order():
    """Text → speech, action → typed action; original order preserved."""
    response = json.dumps([
        {"type": "action", "name": "spotlight", "params": {"elementId": "img_1"}},
        {"type": "text", "content": "First"},
        {"type": "action", "name": "wb_open", "params": {}},
        {"type": "text", "content": "Second"},
    ])
    out = parse_actions_from_structured_output(response, scene_type="slide")
    assert [a["type"] for a in out] == ["spotlight", "speech", "wb_open", "speech"]
    assert out[1]["text"] == "First"
    assert out[3]["text"] == "Second"
    assert out[0]["elementId"] == "img_1"


def test_text_items_become_speech_actions():
    response = json.dumps([{"type": "text", "content": "hello"}])
    out = parse_actions_from_structured_output(response)
    assert len(out) == 1
    assert out[0]["type"] == "speech"
    assert out[0]["text"] == "hello"
    assert out[0]["id"].startswith("action_")


def test_supports_legacy_tool_name_format():
    """Some upstream LLM outputs use tool_name/parameters/tool_id
    instead of the new name/params/action_id."""
    response = json.dumps([
        {
            "type": "action",
            "tool_name": "spotlight",
            "parameters": {"elementId": "img_2"},
            "tool_id": "legacy_xyz",
        }
    ])
    out = parse_actions_from_structured_output(response, scene_type="slide")
    assert len(out) == 1
    assert out[0]["type"] == "spotlight"
    assert out[0]["id"] == "legacy_xyz"
    assert out[0]["elementId"] == "img_2"


def test_normalizes_slide_element_target_aliases():
    response = json.dumps([
        {
            "type": "action",
            "name": "spotlight",
            "params": {"target": "img_1", "dimness": "35%"},
        },
        {
            "type": "action",
            "name": "laser",
            "params": {"element_id": "label_2", "colour": "#00ff00"},
        },
        {
            "type": "action",
            "name": "playVideo",
            "params": {"targetId": "video_3"},
        },
    ])
    out = parse_actions_from_structured_output(response, scene_type="slide")

    assert [a["type"] for a in out] == ["spotlight", "laser", "play_video"]
    assert out[0]["elementId"] == "img_1"
    assert out[0]["dimOpacity"] == 0.35
    assert "target" not in out[0]
    assert "dimness" not in out[0]
    assert out[1]["elementId"] == "label_2"
    assert out[1]["color"] == "#00ff00"
    assert "element_id" not in out[1]
    assert out[2]["elementId"] == "video_3"
    for action in out:
        validate_action(action)


def test_normalizes_highlight_action_name_to_spotlight():
    response = json.dumps([
        {"type": "action", "name": "highlight", "params": {"element_id": "text_1"}},
    ])
    out = parse_actions_from_structured_output(response, scene_type="slide")
    assert [a["type"] for a in out] == ["spotlight"]
    assert out[0]["elementId"] == "text_1"
    validate_action(out[0])


def test_preserves_widget_target_params():
    response = json.dumps([
        {"type": "action", "name": "widget_highlight", "params": {"target": "#answer"}},
    ])
    out = parse_actions_from_structured_output(response, scene_type="interactive")
    assert [a["type"] for a in out] == ["widget_highlight"]
    assert out[0]["target"] == "#answer"
    assert "elementId" not in out[0]


def test_supports_json_encoded_arguments_params():
    response = json.dumps([
        {
            "type": "action",
            "actionName": "laser_pointer",
            "arguments": "{\"element_id\":\"chart_1\"}",
        },
    ])
    out = parse_actions_from_structured_output(response, scene_type="slide")
    assert [a["type"] for a in out] == ["laser"]
    assert out[0]["elementId"] == "chart_1"


def test_action_id_generated_when_missing():
    response = json.dumps([
        {"type": "action", "name": "wb_open", "params": {}}
    ])
    out = parse_actions_from_structured_output(response)
    assert out[0]["id"].startswith("action_")
    assert len(out[0]["id"]) > len("action_")


def test_action_id_preserved_when_provided():
    response = json.dumps([
        {"type": "action", "name": "wb_open", "params": {}, "action_id": "custom-id"}
    ])
    out = parse_actions_from_structured_output(response)
    assert out[0]["id"] == "custom-id"


# ── Code fence stripping ──────────────────────────────────────────


def test_strips_markdown_code_fences():
    inner = json.dumps([{"type": "text", "content": "wrapped"}])
    response = f"```json\n{inner}\n```"
    out = parse_actions_from_structured_output(response)
    assert len(out) == 1
    assert out[0]["text"] == "wrapped"


def test_strips_unlabeled_code_fences():
    inner = json.dumps([{"type": "text", "content": "no lang tag"}])
    response = f"```\n{inner}\n```"
    out = parse_actions_from_structured_output(response)
    assert out[0]["text"] == "no lang tag"


# ── Robust parsing ────────────────────────────────────────────────


def test_unclosed_array_recoverable_via_json_repair():
    """Truncated mid-stream output: closing ] missing. json_repair
    should still extract complete entries."""
    response = '[{"type":"text","content":"complete"},{"type":"text","content":"truncat'
    out = parse_actions_from_structured_output(response)
    # At least the first complete entry should survive
    assert len(out) >= 1
    assert any(a.get("text") == "complete" for a in out)


def test_no_json_array_returns_empty():
    out = parse_actions_from_structured_output("just prose, no JSON")
    assert out == []


def test_invalid_action_without_name_dropped():
    response = json.dumps([
        {"type": "action", "params": {}},  # missing name
        {"type": "action", "name": "wb_open", "params": {}},
    ])
    out = parse_actions_from_structured_output(response)
    assert len(out) == 1
    assert out[0]["type"] == "wb_open"


def test_non_dict_items_skipped():
    response = json.dumps([
        "stray string",
        42,
        {"type": "text", "content": "valid"},
        None,
    ])
    out = parse_actions_from_structured_output(response)
    assert len(out) == 1
    assert out[0]["text"] == "valid"


# ── Discussion last-only invariant ────────────────────────────────


def test_discussion_must_be_last_truncates_after():
    """Mirrors upstream Step 5: if discussion appears mid-list, drop
    everything after it."""
    response = json.dumps([
        {"type": "text", "content": "intro"},
        {"type": "action", "name": "discussion", "params": {"topic": "T"}},
        {"type": "text", "content": "this should be dropped"},
        {"type": "action", "name": "wb_open", "params": {}},
    ])
    out = parse_actions_from_structured_output(response)
    assert [a["type"] for a in out] == ["speech", "discussion"]


def test_discussion_at_end_kept():
    response = json.dumps([
        {"type": "text", "content": "intro"},
        {"type": "action", "name": "discussion", "params": {"topic": "T"}},
    ])
    out = parse_actions_from_structured_output(response)
    assert [a["type"] for a in out] == ["speech", "discussion"]


# ── Scene-type filter (defense in depth) ──────────────────────────


def test_slide_only_actions_stripped_on_non_slide_scene():
    response = json.dumps([
        {"type": "action", "name": "spotlight", "params": {"elementId": "x"}},
        {"type": "action", "name": "laser", "params": {"elementId": "y"}},
        {"type": "action", "name": "wb_open", "params": {}},
    ])
    out = parse_actions_from_structured_output(response, scene_type="quiz")
    types = [a["type"] for a in out]
    assert "spotlight" not in types
    assert "laser" not in types
    assert "wb_open" in types


def test_slide_only_actions_kept_on_slide_scene():
    response = json.dumps([
        {"type": "action", "name": "spotlight", "params": {"elementId": "x"}},
    ])
    out = parse_actions_from_structured_output(response, scene_type="slide")
    assert [a["type"] for a in out] == ["spotlight"]


# ── allowed_actions whitelist ────────────────────────────────────


def test_allowed_actions_whitelist_filters_disallowed():
    """Even if the LLM hallucinates an action a student-role agent
    shouldn't emit (e.g. spotlight after seeing teacher chat history),
    the whitelist filter strips it."""
    response = json.dumps([
        {"type": "text", "content": "I'll spotlight this"},
        {"type": "action", "name": "spotlight", "params": {"elementId": "x"}},
        {"type": "action", "name": "wb_open", "params": {}},
    ])
    out = parse_actions_from_structured_output(
        response,
        scene_type="slide",  # allows spotlight
        allowed_actions=["wb_open"],  # but agent role permits only wb_open
    )
    types = [a["type"] for a in out]
    # speech is always allowed; wb_open is whitelisted; spotlight stripped.
    assert "spotlight" not in types
    assert "speech" in types
    assert "wb_open" in types


def test_speech_always_permitted_regardless_of_whitelist():
    """`speech` (the agent's voice) is always permitted, even when
    not in allowed_actions."""
    response = json.dumps([
        {"type": "text", "content": "hi"},
    ])
    out = parse_actions_from_structured_output(
        response, allowed_actions=["wb_open"]
    )
    assert len(out) == 1
    assert out[0]["type"] == "speech"


# ── Determinism ────────────────────────────────────────────────────


def test_action_ids_are_unique_within_one_call():
    """Generated IDs (when not provided) must not collide within a
    single call. Trivial property — but guards against a future
    refactor that uses a deterministic counter."""
    response = json.dumps([
        {"type": "action", "name": "wb_open", "params": {}},
        {"type": "action", "name": "wb_close", "params": {}},
        {"type": "action", "name": "wb_open", "params": {}},
    ])
    out = parse_actions_from_structured_output(response)
    ids = [a["id"] for a in out]
    assert len(set(ids)) == len(ids), f"IDs collided: {ids}"
