"""Tests for `apps.maic.generation.scene_generator` (MAIC-422.x).

MAIC-422.0 (this chunk) ships:
    - module skeleton + scene-type dispatcher
    - slide-content branch end-to-end

Tests for quiz / pbl / interactive content branches arrive in
MAIC-422.2 / 422.4 / 422.5 (Sessions 3-4).
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from apps.maic.generation.scene_generator import generate_scene_content


# ── Dispatcher ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dispatcher_routes_slide_to_slide_content():
    """Slide outlines hit the slide-content branch."""
    outline = {
        "type": "slide",
        "title": "Intro",
        "description": "Welcome",
        "keyPoints": ["A", "B"],
    }

    async def _fake_generate(*args, **kwargs):
        return json.dumps({
            "elements": [
                {"type": "text", "left": 0, "top": 0, "width": 100, "height": 50}
            ],
            "background": {"type": "solid", "color": "#fff"},
        })

    with patch(
        "apps.maic.generation.scene_generator.generate_text", new=_fake_generate
    ):
        content = await generate_scene_content(
            outline, language_model_id="stub"
        )
    assert content is not None
    assert "elements" in content


@pytest.mark.asyncio
async def test_dispatcher_returns_none_for_quiz_until_maic_422_2():
    """Quiz branch lands in MAIC-422.2. Until then, dispatcher
    returns None — defended by an explicit branch (not a default
    fall-through) so a misrouted outline doesn't silently break."""
    outline = {"type": "quiz", "title": "Q"}
    content = await generate_scene_content(outline)
    assert content is None


@pytest.mark.asyncio
async def test_dispatcher_returns_none_for_interactive_until_maic_422_5():
    outline = {"type": "interactive", "title": "I"}
    content = await generate_scene_content(outline)
    assert content is None


@pytest.mark.asyncio
async def test_dispatcher_returns_none_for_pbl_until_maic_422_4():
    outline = {"type": "pbl", "title": "P"}
    content = await generate_scene_content(outline)
    assert content is None


@pytest.mark.asyncio
async def test_dispatcher_returns_none_for_unknown_type():
    outline = {"type": "totally-unknown", "title": "X"}
    content = await generate_scene_content(outline)
    assert content is None


# ── Slide-content branch ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_slide_content_returns_generated_slide_dict():
    """Happy path: LLM returns valid JSON; the function returns a
    GeneratedSlideContent-shaped dict."""
    outline = {
        "type": "slide",
        "title": "Photosynthesis",
        "description": "Intro to photosynthesis",
        "keyPoints": ["chlorophyll", "light energy", "glucose"],
    }

    async def _fake(*args, **kwargs):
        return json.dumps({
            "elements": [
                {"type": "text", "left": 50, "top": 50, "width": 200, "height": 30, "content": "Hi"}
            ],
            "background": {"type": "solid", "color": "#ffffff"},
            "remark": "Speaker notes here",
        })

    with patch(
        "apps.maic.generation.scene_generator.generate_text", new=_fake
    ):
        content = await generate_scene_content(
            outline, language_model_id="stub"
        )
    assert content is not None
    assert content["elements"][0]["content"] == "Hi"
    assert content["background"] == {"type": "solid", "color": "#ffffff"}
    assert content["remark"] == "Speaker notes here"


@pytest.mark.asyncio
async def test_slide_content_falls_back_to_outline_description_when_no_remark():
    """When the LLM omits `remark`, fall back to outline.description
    (mirrors upstream line 772)."""
    outline = {
        "type": "slide",
        "title": "T",
        "description": "fallback description",
        "keyPoints": [],
    }

    async def _fake(*args, **kwargs):
        return json.dumps({
            "elements": [{"type": "text"}],
            # No `remark` key
        })

    with patch(
        "apps.maic.generation.scene_generator.generate_text", new=_fake
    ):
        content = await generate_scene_content(outline, language_model_id="stub")
    assert content["remark"] == "fallback description"


@pytest.mark.asyncio
async def test_slide_content_returns_none_on_parse_failure():
    """Garbage from the LLM → parse fails → return None (caller
    treats as scene-content-failed, builds a placeholder elsewhere)."""
    outline = {"type": "slide", "title": "T", "description": "d"}

    async def _fake(*args, **kwargs):
        return "this is not JSON anywhere"

    with patch(
        "apps.maic.generation.scene_generator.generate_text", new=_fake
    ):
        content = await generate_scene_content(outline, language_model_id="stub")
    assert content is None


@pytest.mark.asyncio
async def test_slide_content_returns_none_when_elements_is_not_a_list():
    """Schema regression: LLM returns `elements: "not a list"`."""
    outline = {"type": "slide", "title": "T"}

    async def _fake(*args, **kwargs):
        return json.dumps({"elements": "not a list"})

    with patch(
        "apps.maic.generation.scene_generator.generate_text", new=_fake
    ):
        content = await generate_scene_content(outline, language_model_id="stub")
    assert content is None


@pytest.mark.asyncio
async def test_slide_content_handles_gradient_background():
    """Background can be solid OR gradient (mirrors upstream lines
    761-766)."""
    outline = {"type": "slide", "title": "T"}
    gradient = {
        "type": "linear",
        "colors": [{"pos": 0, "color": "#ff0000"}, {"pos": 1, "color": "#0000ff"}],
        "rotate": 90,
    }

    async def _fake(*args, **kwargs):
        return json.dumps({
            "elements": [],
            "background": {"type": "gradient", "gradient": gradient},
        })

    with patch(
        "apps.maic.generation.scene_generator.generate_text", new=_fake
    ):
        content = await generate_scene_content(outline, language_model_id="stub")
    assert content["background"]["type"] == "gradient"
    assert content["background"]["gradient"] == gradient


@pytest.mark.asyncio
async def test_slide_content_invalid_background_type_silently_skipped():
    """Defensive: if LLM returns bg.type='neither-solid-nor-gradient',
    background is None (don't ship a malformed shape)."""
    outline = {"type": "slide", "title": "T"}

    async def _fake(*args, **kwargs):
        return json.dumps({
            "elements": [{"type": "text"}],
            "background": {"type": "weird-future-type", "data": {}},
        })

    with patch(
        "apps.maic.generation.scene_generator.generate_text", new=_fake
    ):
        content = await generate_scene_content(outline, language_model_id="stub")
    assert content is not None
    assert content["background"] is None


@pytest.mark.asyncio
async def test_slide_content_passes_teacher_persona_into_prompt():
    """Verify the teacher persona is forwarded into the prompt
    template variables — this is how slide content adapts tone to
    the configured teacher."""
    captured_vars = {}

    def _capture(template_id, vars):
        captured_vars.update(vars)
        from apps.maic.prompts.loader import BuiltPrompt
        return BuiltPrompt(system="sys", user="user")

    async def _fake_text(*args, **kwargs):
        return json.dumps({"elements": [{"type": "text"}]})

    outline = {"type": "slide", "title": "T", "description": "d"}
    agents = [
        {
            "id": "default-1",
            "name": "Alice",
            "role": "teacher",
            "persona": "patient and warm",
        }
    ]

    with patch(
        "apps.maic.generation.scene_generator.load_generation_prompt",
        side_effect=_capture,
    ):
        with patch(
            "apps.maic.generation.scene_generator.generate_text", new=_fake_text
        ):
            await generate_scene_content(
                outline,
                language_model_id="stub",
                options={"agents": agents},
            )

    teacher_ctx = captured_vars.get("teacherContext", "")
    assert "Alice" in teacher_ctx
    assert "patient and warm" in teacher_ctx


@pytest.mark.asyncio
async def test_slide_content_passes_canvas_dimensions():
    """Lock the canvas dims into the prompt — they MUST match the
    Slide.viewportSize / viewportRatio in scene_builder's
    DEFAULT_SLIDE_THEME, otherwise generated elements get
    placed in coordinates the playback engine can't render."""
    captured_vars = {}

    def _capture(template_id, vars):
        captured_vars.update(vars)
        from apps.maic.prompts.loader import BuiltPrompt
        return BuiltPrompt(system="sys", user="user")

    async def _fake(*args, **kwargs):
        return json.dumps({"elements": []})

    with patch(
        "apps.maic.generation.scene_generator.load_generation_prompt",
        side_effect=_capture,
    ):
        with patch(
            "apps.maic.generation.scene_generator.generate_text", new=_fake
        ):
            await generate_scene_content(
                {"type": "slide", "title": "T"},
                language_model_id="stub",
            )
    assert captured_vars["canvas_width"] == 1000
    assert captured_vars["canvas_height"] == 562.5


@pytest.mark.asyncio
async def test_slide_content_keypoints_are_numbered():
    """LLM prompts expect keyPoints rendered as `1. foo\\n2. bar`
    (mirrors upstream line 683)."""
    captured_vars = {}

    def _capture(template_id, vars):
        captured_vars.update(vars)
        from apps.maic.prompts.loader import BuiltPrompt
        return BuiltPrompt(system="sys", user="user")

    async def _fake(*args, **kwargs):
        return json.dumps({"elements": []})

    with patch(
        "apps.maic.generation.scene_generator.load_generation_prompt",
        side_effect=_capture,
    ):
        with patch(
            "apps.maic.generation.scene_generator.generate_text", new=_fake
        ):
            await generate_scene_content(
                {
                    "type": "slide",
                    "title": "T",
                    "keyPoints": ["one", "two", "three"],
                },
                language_model_id="stub",
            )
    rendered = captured_vars["keyPoints"]
    assert "1. one" in rendered
    assert "2. two" in rendered
    assert "3. three" in rendered


@pytest.mark.asyncio
async def test_slide_content_image_flags_all_false_in_phase_4():
    """Phase 4 has no PDF / generated images → all 4 flags False.
    Lock the contract so a future Phase-5 retrofit doesn't silently
    flip these without notice."""
    captured_vars = {}

    def _capture(template_id, vars):
        captured_vars.update(vars)
        from apps.maic.prompts.loader import BuiltPrompt
        return BuiltPrompt(system="sys", user="user")

    async def _fake(*args, **kwargs):
        return json.dumps({"elements": []})

    with patch(
        "apps.maic.generation.scene_generator.load_generation_prompt",
        side_effect=_capture,
    ):
        with patch(
            "apps.maic.generation.scene_generator.generate_text", new=_fake
        ):
            await generate_scene_content(
                {"type": "slide", "title": "T"},
                language_model_id="stub",
            )
    assert captured_vars["imageElementEnabled"] is False
    assert captured_vars["generatedImageEnabled"] is False
    assert captured_vars["generatedVideoEnabled"] is False
    assert captured_vars["mediaElementEnabled"] is False
