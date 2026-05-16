"""Tests for apps.maic.protocol.actions — the 21-type action vocabulary.

Coverage targets:
  - actions.py ≥ 90% (constraint paths exercised below)
  - validate_action() raises MaicProtocolError on every malformed shape
  - filter_for_scene() strips slide-only actions for non-slide scenes
"""
from __future__ import annotations

import pytest

from apps.maic.exceptions import MaicProtocolError
from apps.maic.protocol import (
    ALL_ACTION_TYPES,
    DiscussionAction,
    FIRE_AND_FORGET_ACTIONS,
    SLIDE_ONLY_ACTIONS,
    SYNC_ACTIONS,
    SpeechAction,
    SpotlightAction,
    WbDrawLineAction,
    WbDrawShapeAction,
    WbEditCodeAction,
    export_json_schema,
    filter_for_scene,
    validate_action,
    validate_actions,
)


# ── Category constants — match upstream lib/types/action.ts:245-271 ───


def test_total_action_count_is_21():
    assert len(ALL_ACTION_TYPES) == 21


def test_fire_and_forget_set():
    assert FIRE_AND_FORGET_ACTIONS == {"spotlight", "laser"}


def test_slide_only_set():
    assert SLIDE_ONLY_ACTIONS == {"spotlight", "laser"}


def test_sync_actions_partition():
    """SYNC ∪ FIRE_AND_FORGET must equal ALL — no orphan types."""
    assert SYNC_ACTIONS | FIRE_AND_FORGET_ACTIONS == ALL_ACTION_TYPES
    assert SYNC_ACTIONS & FIRE_AND_FORGET_ACTIONS == set()


@pytest.mark.parametrize("expected_type", sorted(ALL_ACTION_TYPES))
def test_every_action_type_has_a_pydantic_model(expected_type):
    """Round-trip a minimum-valid payload for each of the 21 types."""
    minimal = _minimal_payload(expected_type)
    parsed = validate_action(minimal)
    assert parsed.type == expected_type


# ── validate_action — happy paths ──────────────────────────────────────


def test_validate_speech_minimal():
    s = validate_action({"id": "a1", "type": "speech", "text": "hello"})
    assert isinstance(s, SpeechAction)
    assert s.text == "hello"
    assert s.audioId is None
    assert s.audioUrl is None


def test_validate_spotlight_with_dim():
    s = validate_action({
        "id": "a2", "type": "spotlight", "elementId": "el-7", "dimOpacity": 0.3,
    })
    assert isinstance(s, SpotlightAction)
    assert s.dimOpacity == 0.3


def test_validate_wb_draw_line_full():
    line = validate_action({
        "id": "a3", "type": "wb_draw_line",
        "startX": 0, "startY": 0, "endX": 1000, "endY": 562,
        "style": "dashed", "points": ["", "arrow"], "width": 3,
    })
    assert isinstance(line, WbDrawLineAction)
    assert line.points == ("", "arrow")


def test_validate_wb_edit_code_replace():
    edit = validate_action({
        "id": "a4", "type": "wb_edit_code", "elementId": "code-1",
        "operation": "replace_lines", "lineIds": ["l1", "l2"],
        "content": "print('hi')",
    })
    assert isinstance(edit, WbEditCodeAction)
    assert edit.operation == "replace_lines"


def test_validate_actions_list_preserves_order():
    payload = [
        {"id": "a", "type": "speech", "text": "one"},
        {"id": "b", "type": "wb_open"},
    ]
    out = validate_actions(payload)
    assert [a.type for a in out] == ["speech", "wb_open"]


# ── validate_action — failure modes ────────────────────────────────────


@pytest.mark.parametrize("bad", [
    pytest.param({"id": "a", "type": "speech"}, id="speech-missing-text"),
    pytest.param({"id": "a", "type": "speech", "text": ""}, id="speech-empty-text"),
    pytest.param({"id": "a", "type": "spotlight"}, id="spotlight-missing-elementId"),
    pytest.param(
        {"id": "a", "type": "spotlight", "elementId": "x", "dimOpacity": 1.5},
        id="spotlight-dim-out-of-range",
    ),
    pytest.param({"id": "a", "type": "totally_unknown_action"}, id="unknown-type"),
    pytest.param(
        {"id": "a", "type": "wb_draw_line",
         "startX": 0, "startY": 0, "endX": 1500, "endY": 0},
        id="wb_draw_line-x-out-of-frame",
    ),
    pytest.param(
        {"id": "a", "type": "wb_draw_shape", "shape": "hexagon",
         "x": 0, "y": 0, "width": 10, "height": 10},
        id="wb_draw_shape-bad-shape",
    ),
    pytest.param(
        {"id": "a", "type": "wb_draw_shape", "shape": "rectangle",
         "x": 0, "y": 0, "width": 0, "height": 10},
        id="wb_draw_shape-zero-width",
    ),
    pytest.param(
        {"id": "a", "type": "wb_edit_code", "elementId": "c",
         "operation": "rebuild_from_scratch"},
        id="wb_edit_code-bad-operation",
    ),
    pytest.param("not a dict", id="non-dict"),
    pytest.param(None, id="None"),
])
def test_validate_action_raises_on_bad_input(bad):
    with pytest.raises(MaicProtocolError):
        validate_action(bad)


def test_validate_action_extra_fields_rejected():
    """`extra='forbid'` on _ActionBase blocks unknown keys.  This catches
    typos in agent output before they propagate to the playback engine."""
    with pytest.raises(MaicProtocolError):
        validate_action({"id": "a", "type": "speech", "text": "x", "speeed": 1.5})


@pytest.mark.parametrize("widget_payload", [
    pytest.param(
        {"id": "w1", "type": "widget_highlight", "target": "#x",
         "selectorr": "typo"},
        id="widget_highlight-extra-field",
    ),
    pytest.param(
        {"id": "w2", "type": "widget_setState", "state": {"k": 1},
         "extraState": "should-go-inside-state"},
        id="widget_setState-extra-field",
    ),
    pytest.param(
        {"id": "w3", "type": "widget_annotation", "target": "#x",
         "annotation": "no-such-key"},
        id="widget_annotation-extra-field",
    ),
    pytest.param(
        {"id": "w4", "type": "widget_reveal", "target": "#x",
         "revealMode": "no-such-key"},
        id="widget_reveal-extra-field",
    ),
])
def test_widget_actions_reject_extra_fields(widget_payload):
    """Audit Section B.1: a hallucinated key on widget_* must be caught
    at parse time, not at the playback engine. Each of the four widget
    actions inherits `extra='forbid'` from _ActionBase; this test pins
    that contract so a future refactor cannot accidentally loosen it.
    """
    with pytest.raises(MaicProtocolError):
        validate_action(widget_payload)


def test_widget_setState_inner_dict_is_permissive_by_design():
    """`state` is `dict[str, Any]` so widgets can carry arbitrary
    simulation variables. This is intentional and matches upstream —
    extras BELONG inside `state`, not as siblings of `state`. Asserted
    so the reader does not confuse this with the extra-fields rejection
    above.
    """
    a = validate_action({
        "id": "w", "type": "widget_setState",
        "state": {"temperature": 280, "pressure": 1.2, "running": True},
    })
    assert a.state["temperature"] == 280
    assert a.state["running"] is True


def test_validate_actions_failing_index_in_message():
    with pytest.raises(MaicProtocolError, match=r"actions\[1\]"):
        validate_actions([
            {"id": "a", "type": "speech", "text": "ok"},
            {"id": "b", "type": "speech"},  # missing text → bad index 1
        ])


# ── filter_for_scene ───────────────────────────────────────────────────


def test_filter_for_scene_keeps_all_for_slide():
    allowed = ["speech", "spotlight", "laser", "wb_draw_text"]
    assert filter_for_scene(allowed, "slide") == allowed


def test_filter_for_scene_strips_slide_only_for_non_slide():
    allowed = ["speech", "spotlight", "laser", "wb_draw_text"]
    assert filter_for_scene(allowed, "quiz") == ["speech", "wb_draw_text"]


def test_filter_for_scene_strips_unknown_action_types():
    """Defense-in-depth: an LLM that outputs `allowed_actions: ['foo']`
    must not slip past the filter even if it matched a sceneType clause."""
    assert filter_for_scene(["speech", "foo", "wb_open"], "slide") == ["speech", "wb_open"]


def test_filter_for_scene_handles_none_scene_type():
    """No scene means restrictive — strip slide-only just like non-slide."""
    assert filter_for_scene(["speech", "spotlight"], None) == ["speech"]


# ── JSON Schema export ─────────────────────────────────────────────────


def test_export_json_schema_lists_all_action_types():
    schema = export_json_schema()
    # Pydantic v2 emits a `oneOf` at the top of a discriminated union.
    one_of = schema.get("oneOf", [])
    discriminator_types = {
        ref_name(item).removesuffix("Action").lower()
        for item in one_of
        if "$ref" in item
    }
    # Some are easier to verify via the `discriminator` mapping
    discriminator = schema.get("discriminator", {})
    mapping = discriminator.get("mapping", {})
    assert set(mapping.keys()) == ALL_ACTION_TYPES, (
        f"json schema missing types: {ALL_ACTION_TYPES - set(mapping.keys())}"
    )


def ref_name(item: dict) -> str:
    """Extract the trailing $defs name from `{'$ref': '#/$defs/Foo'}`."""
    return item["$ref"].rsplit("/", 1)[-1]


# ── helpers ────────────────────────────────────────────────────────────


def _minimal_payload(action_type: str) -> dict:
    """Return the minimum-valid Action payload for each type — used by the
    parametrized round-trip test above."""
    base = {"id": f"x-{action_type}", "type": action_type}
    extras: dict[str, dict] = {
        "spotlight": {"elementId": "el"},
        "laser": {"elementId": "el"},
        "speech": {"text": "hi"},
        "wb_open": {},
        "wb_close": {},
        "wb_clear": {},
        "wb_delete": {"elementId": "el"},
        "wb_draw_text": {"content": "x", "x": 0, "y": 0},
        "wb_draw_shape": {"shape": "rectangle", "x": 0, "y": 0, "width": 1, "height": 1},
        "wb_draw_chart": {
            "chartType": "bar", "x": 0, "y": 0, "width": 1, "height": 1,
            "data": {"labels": [], "legends": [], "series": []},
        },
        "wb_draw_latex": {"latex": "x", "x": 0, "y": 0},
        "wb_draw_table": {"x": 0, "y": 0, "width": 1, "height": 1, "data": [[]]},
        "wb_draw_line": {"startX": 0, "startY": 0, "endX": 0, "endY": 0},
        "wb_draw_code": {"language": "python", "code": "x", "x": 0, "y": 0},
        "wb_edit_code": {"elementId": "c", "operation": "delete_lines"},
        "play_video": {"elementId": "v"},
        "discussion": {"topic": "x"},
        "widget_highlight": {"target": "x"},
        "widget_setState": {"state": {}},
        "widget_annotation": {"target": "x"},
        "widget_reveal": {"target": "x"},
    }
    return {**base, **extras[action_type]}
