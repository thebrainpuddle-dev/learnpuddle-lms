"""Tests for `apps.maic.generation.scene_builder` (MAIC-423)."""
from __future__ import annotations

import pytest

from apps.maic.generation.scene_builder import (
    DEFAULT_SLIDE_THEME,
    build_complete_scene,
    uniquify_media_element_ids,
)


# ── uniquify_media_element_ids ────────────────────────────────────


class TestUniquifyMediaElementIds:
    def test_outlines_without_media_pass_through_unchanged(self):
        """Phase 4 default — no image generation → passthrough."""
        outlines = [
            {"id": "o1", "type": "slide", "title": "A"},
            {"id": "o2", "type": "quiz", "title": "B"},
        ]
        result = uniquify_media_element_ids(outlines)
        # Same list reference returned (no copy on the no-op path).
        assert result is outlines

    def test_replaces_sequential_image_id(self):
        outlines = [
            {
                "id": "o1",
                "type": "slide",
                "title": "A",
                "mediaGenerations": [
                    {"elementId": "gen_img_1", "type": "image"},
                ],
            }
        ]
        result = uniquify_media_element_ids(outlines)
        new_id = result[0]["mediaGenerations"][0]["elementId"]
        assert new_id != "gen_img_1"
        assert new_id.startswith("gen_img_")
        assert len(new_id) > len("gen_img_")  # has nanoid suffix

    def test_replaces_sequential_video_id(self):
        outlines = [
            {
                "id": "o1",
                "type": "slide",
                "title": "A",
                "mediaGenerations": [
                    {"elementId": "gen_vid_2", "type": "video"},
                ],
            }
        ]
        result = uniquify_media_element_ids(outlines)
        new_id = result[0]["mediaGenerations"][0]["elementId"]
        assert new_id.startswith("gen_vid_")
        assert new_id != "gen_vid_2"

    def test_duplicate_id_references_resolve_to_same_replacement(self):
        """If two mediaGenerations entries (in same OR different
        outlines) point at the same sequential ID, both get the SAME
        replacement. Otherwise a single image ends up with two
        different unique IDs and the rendering breaks."""
        outlines = [
            {
                "id": "o1", "type": "slide", "title": "A",
                "mediaGenerations": [
                    {"elementId": "gen_img_1", "type": "image"},
                ],
            },
            {
                "id": "o2", "type": "slide", "title": "B",
                "mediaGenerations": [
                    {"elementId": "gen_img_1", "type": "image"},
                    {"elementId": "gen_img_2", "type": "image"},
                ],
            },
        ]
        result = uniquify_media_element_ids(outlines)
        id_a = result[0]["mediaGenerations"][0]["elementId"]
        id_b_first = result[1]["mediaGenerations"][0]["elementId"]
        id_b_second = result[1]["mediaGenerations"][1]["elementId"]
        # Same source ID → same replacement
        assert id_a == id_b_first
        # Different source ID → different replacement
        assert id_b_first != id_b_second

    def test_input_not_mutated(self):
        """Defensive: caller's outlines stay intact when the function
        returns a copy."""
        outlines = [
            {
                "id": "o1", "type": "slide", "title": "A",
                "mediaGenerations": [
                    {"elementId": "gen_img_1", "type": "image"},
                ],
            }
        ]
        original_id = outlines[0]["mediaGenerations"][0]["elementId"]
        result = uniquify_media_element_ids(outlines)
        assert outlines[0]["mediaGenerations"][0]["elementId"] == original_id
        assert result[0]["mediaGenerations"][0]["elementId"] != original_id


# ── build_complete_scene ──────────────────────────────────────────


class TestBuildCompleteScene:
    def _make_outline(self, scene_type: str, **extras) -> dict:
        return {
            "id": "outline-1",
            "type": scene_type,
            "title": "Test Scene",
            "order": 5,
            **extras,
        }

    def test_slide_scene_assembles_correctly(self):
        outline = self._make_outline("slide")
        content = {
            "elements": [{"type": "text", "left": 0, "top": 0, "width": 100, "height": 50}],
            "background": {"type": "solid", "color": "#fff"},
        }
        actions = [{"id": "a1", "type": "speech", "text": "hello"}]
        scene = build_complete_scene(outline, content, actions, "stage-1")
        assert scene is not None
        assert scene["type"] == "slide"
        assert scene["title"] == "Test Scene"
        assert scene["order"] == 5
        assert scene["stageId"] == "stage-1"
        assert scene["actions"] == actions
        # Slide content wrapping
        assert scene["content"]["type"] == "slide"
        assert "canvas" in scene["content"]
        canvas = scene["content"]["canvas"]
        assert canvas["viewportSize"] == 1000
        assert canvas["viewportRatio"] == 0.5625
        assert canvas["theme"] == DEFAULT_SLIDE_THEME
        assert canvas["elements"] == content["elements"]
        assert canvas["background"] == content["background"]

    def test_quiz_scene_assembles_correctly(self):
        outline = self._make_outline("quiz")
        content = {
            "questions": [{"q": "What is 2+2?", "options": ["3", "4"], "correct": 1}],
        }
        actions = [{"id": "a1", "type": "speech"}]
        scene = build_complete_scene(outline, content, actions, "stage-1")
        assert scene is not None
        assert scene["type"] == "quiz"
        assert scene["content"]["type"] == "quiz"
        assert scene["content"]["questions"] == content["questions"]

    def test_interactive_scene_assembles_with_widget_fields(self):
        outline = self._make_outline("interactive")
        content = {
            "html": "<div>interactive</div>",
            "widgetType": "code",
            "widgetConfig": {"language": "python"},
            "teacherActions": [{"id": "ta1"}],
        }
        scene = build_complete_scene(outline, content, [], "stage-1")
        assert scene is not None
        assert scene["type"] == "interactive"
        assert scene["content"]["html"] == "<div>interactive</div>"
        assert scene["content"]["widgetType"] == "code"
        assert scene["content"]["widgetConfig"] == {"language": "python"}
        assert scene["content"]["teacherActions"] == [{"id": "ta1"}]
        assert scene["content"]["url"] == ""  # always empty per upstream

    def test_interactive_scene_widget_fields_optional(self):
        """Non-Ultra-Mode interactive scenes have no widgetType/Config/
        teacherActions — they should be present as None."""
        outline = self._make_outline("interactive")
        content = {"html": "<div>x</div>"}
        scene = build_complete_scene(outline, content, [], "stage-1")
        assert scene is not None
        assert scene["content"]["widgetType"] is None
        assert scene["content"]["widgetConfig"] is None
        assert scene["content"]["teacherActions"] is None

    def test_pbl_scene_assembles_with_project_config(self):
        outline = self._make_outline("pbl")
        content = {
            "projectConfig": {"phases": [], "agents": []},
        }
        scene = build_complete_scene(outline, content, [], "stage-1")
        assert scene is not None
        assert scene["type"] == "pbl"
        assert scene["content"]["type"] == "pbl"
        assert scene["content"]["projectConfig"] == content["projectConfig"]

    def test_returns_none_when_type_doesnt_match_content(self):
        """Defensive: outline.type=slide but content has no 'elements'
        — returns None rather than building a malformed Scene."""
        outline = self._make_outline("slide")
        content = {"questions": []}  # quiz-shaped, not slide-shaped
        scene = build_complete_scene(outline, content, [], "stage-1")
        assert scene is None

    def test_returns_none_for_unknown_scene_type(self):
        outline = self._make_outline("unknown-type")
        scene = build_complete_scene(outline, {}, [], "stage-1")
        assert scene is None

    def test_each_scene_gets_unique_ids(self):
        """Two consecutive build_complete_scene calls must produce
        scenes with different ids — collisions break the playback
        engine's scene-cursor logic."""
        outline = self._make_outline("slide")
        content = {"elements": [], "background": None}
        a = build_complete_scene(outline, content, [], "stage-1")
        b = build_complete_scene(outline, content, [], "stage-1")
        assert a["id"] != b["id"]

    def test_created_at_and_updated_at_are_milliseconds(self):
        """Upstream uses Date.now() which is integer ms since epoch."""
        outline = self._make_outline("slide")
        content = {"elements": [], "background": None}
        scene = build_complete_scene(outline, content, [], "stage-1")
        # 2026 = ~1.78e12 ms; sanity-check the magnitude
        assert scene["createdAt"] > 1_000_000_000_000
        assert scene["updatedAt"] == scene["createdAt"]


# ── outline_generator integration (regression net) ─────────────────


def test_outline_generator_now_uses_real_uniquify():
    """MAIC-423 replaced the outline_generator's no-op stub with a
    real call to scene_builder.uniquify_media_element_ids. Verify
    the wiring works for an outline with media IDs."""
    from apps.maic.generation.outline_generator import (
        _uniquify_media_element_ids,
    )

    outlines = [
        {
            "id": "o1",
            "type": "slide",
            "title": "A",
            "mediaGenerations": [
                {"elementId": "gen_img_1", "type": "image"},
            ],
        }
    ]
    result = _uniquify_media_element_ids(outlines)
    new_id = result[0]["mediaGenerations"][0]["elementId"]
    assert new_id != "gen_img_1"
    assert new_id.startswith("gen_img_")
