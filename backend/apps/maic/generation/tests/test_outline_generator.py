"""Tests for `apps.maic.generation.outline_generator` (MAIC-421).

Coverage:
  - Stage 1 happy path against `stub` provider (deterministic; no LLM
    network calls in the default test run).
  - Both response shapes: legacy flat-array AND object with
    languageDirective + outlines.
  - Outline enrichment: missing id gets generated, order index added.
  - Schema-fail responses → GenerationResult{success: False}.
  - User profile injection (nickname / bio).
  - apply_outline_fallbacks for interactive + pbl edge cases.

Real-LLM tests (against OpenRouter) are gated by `OPENROUTER_API_KEY`.
"""
from __future__ import annotations

import json
import os
from unittest.mock import patch

import pytest

from apps.maic.generation.outline_generator import (
    DEFAULT_LANGUAGE_DIRECTIVE,
    apply_outline_fallbacks,
    generate_scene_outlines_from_requirements,
)


# ── apply_outline_fallbacks ───────────────────────────────────────


class TestApplyOutlineFallbacks:
    def test_slide_outline_passes_through(self):
        outline = {"type": "slide", "title": "intro"}
        result = apply_outline_fallbacks(outline, has_language_model=True)
        assert result["type"] == "slide"

    def test_interactive_without_config_falls_back_to_slide(self):
        outline = {"type": "interactive", "title": "x"}
        result = apply_outline_fallbacks(outline, has_language_model=True)
        assert result["type"] == "slide"

    def test_interactive_with_widget_config_kept(self):
        """Ultra mode: interactive scenes with widgetType +
        widgetOutline are valid even without interactiveConfig."""
        outline = {
            "type": "interactive",
            "title": "x",
            "widgetType": "code",
            "widgetOutline": {"language": "python"},
        }
        result = apply_outline_fallbacks(outline, has_language_model=True)
        assert result["type"] == "interactive"

    def test_interactive_with_interactive_config_kept(self):
        outline = {
            "type": "interactive",
            "title": "x",
            "interactiveConfig": {"foo": "bar"},
        }
        result = apply_outline_fallbacks(outline, has_language_model=True)
        assert result["type"] == "interactive"

    def test_pbl_without_config_falls_back(self):
        outline = {"type": "pbl", "title": "x"}
        result = apply_outline_fallbacks(outline, has_language_model=True)
        assert result["type"] == "slide"

    def test_pbl_without_language_model_falls_back(self):
        outline = {
            "type": "pbl",
            "title": "x",
            "pblConfig": {"foo": "bar"},
        }
        result = apply_outline_fallbacks(outline, has_language_model=False)
        assert result["type"] == "slide"

    def test_pbl_with_config_and_lm_kept(self):
        outline = {
            "type": "pbl",
            "title": "x",
            "pblConfig": {"foo": "bar"},
        }
        result = apply_outline_fallbacks(outline, has_language_model=True)
        assert result["type"] == "pbl"

    def test_returns_new_dict_when_falling_back(self):
        """Defensive: caller's input shouldn't mutate."""
        outline = {"type": "interactive", "title": "x"}
        result = apply_outline_fallbacks(outline, has_language_model=True)
        assert outline["type"] == "interactive"  # input unchanged
        assert result["type"] == "slide"  # output flipped


# ── generate_scene_outlines_from_requirements ─────────────────────


@pytest.mark.asyncio
async def test_stage_1_with_stub_provider_returns_success_envelope():
    """The stub provider yields STUB_OUTPUT (a JSON array) which the
    parser sees as the legacy flat-array format. Verify the call
    shape works end-to-end."""
    result = await generate_scene_outlines_from_requirements(
        requirements={"requirement": "teach fractions", "language": "English"},
        language_model_id="stub",
    )
    # The stub provider returns a JSON array of {type:'text'/'action'}
    # items (not outlines) — the parser successfully parses it as a
    # list, treats it as outlines, and the enrichment loop coerces
    # them into outline-shaped dicts (with id + order).
    assert result["success"] is True
    assert "data" in result
    assert "languageDirective" in result["data"]
    assert "outlines" in result["data"]


@pytest.mark.asyncio
async def test_object_response_with_language_directive_extracted():
    """When the LLM returns the object shape, languageDirective is
    extracted (not the default)."""
    response = json.dumps({
        "languageDirective": "Teach in Mandarin Chinese.",
        "outlines": [
            {"type": "slide", "title": "Intro", "id": "outline-1"},
            {"type": "quiz", "title": "Check"},
        ],
    })

    async def _fake_generate_text(*args, **kwargs):
        return response

    with patch(
        "apps.maic.generation.outline_generator.generate_text",
        new=_fake_generate_text,
    ):
        result = await generate_scene_outlines_from_requirements(
            requirements={"requirement": "x", "language": "Mandarin"},
            language_model_id="stub",  # bypassed by the patch
        )
    assert result["success"]
    assert result["data"]["languageDirective"] == "Teach in Mandarin Chinese."
    assert len(result["data"]["outlines"]) == 2


@pytest.mark.asyncio
async def test_image_enabled_repairs_missing_slide_media_generations():
    response = json.dumps({
        "languageDirective": "Teach in English.",
        "outlines": [
            {
                "type": "slide",
                "title": "Chloroplasts",
                "description": "Explain how leaves capture light.",
                "keyPoints": ["Chlorophyll absorbs light", "Leaves exchange gases"],
            },
            {"type": "quiz", "title": "Check", "quizConfig": {"questionCount": 2}},
        ],
    })

    async def _fake_generate_text(*args, **kwargs):
        return response

    with patch(
        "apps.maic.generation.outline_generator.generate_text",
        new=_fake_generate_text,
    ):
        result = await generate_scene_outlines_from_requirements(
            requirements={"requirement": "Teach photosynthesis"},
            language_model_id="stub",
            options={"image_generation_enabled": True},
        )

    outlines = result["data"]["outlines"]
    slide = outlines[0]
    assert slide["mediaGenerations"][0]["type"] == "image"
    assert slide["mediaGenerations"][0]["elementId"].startswith("gen_img_")
    assert "Chloroplasts" in slide["mediaGenerations"][0]["prompt"]
    assert "Chlorophyll absorbs light" in slide["mediaGenerations"][0]["prompt"]
    assert "mediaGenerations" not in outlines[1]


@pytest.mark.asyncio
async def test_legacy_flat_array_response_uses_default_directive():
    """When LLM returns just an array (legacy / fallback), the
    default directive applies."""
    response = json.dumps([
        {"type": "slide", "title": "A"},
        {"type": "slide", "title": "B"},
    ])

    async def _fake(*args, **kwargs):
        return response

    with patch(
        "apps.maic.generation.outline_generator.generate_text", new=_fake
    ):
        result = await generate_scene_outlines_from_requirements(
            requirements={"requirement": "x"}, language_model_id="stub",
        )
    assert result["success"]
    assert result["data"]["languageDirective"] == DEFAULT_LANGUAGE_DIRECTIVE


@pytest.mark.asyncio
async def test_outlines_get_ids_and_order():
    """Each outline gets a generated id (if missing) + 1-based order."""
    response = json.dumps({
        "outlines": [
            {"type": "slide", "title": "A"},  # no id
            {"type": "quiz", "title": "B", "id": "b-explicit"},  # has id
            {"type": "slide", "title": "C"},  # no id
        ],
    })

    async def _fake(*args, **kwargs):
        return response

    with patch(
        "apps.maic.generation.outline_generator.generate_text", new=_fake
    ):
        result = await generate_scene_outlines_from_requirements(
            requirements={"requirement": "x"}, language_model_id="stub",
        )
    outlines = result["data"]["outlines"]
    assert len(outlines) == 3
    assert outlines[0]["order"] == 1
    assert outlines[1]["order"] == 2
    assert outlines[2]["order"] == 3
    assert outlines[1]["id"] == "b-explicit"
    # Generated ids non-empty
    assert outlines[0]["id"] and outlines[0]["id"] != ""
    assert outlines[2]["id"] and outlines[2]["id"] != ""
    # Generated ids unique
    assert outlines[0]["id"] != outlines[2]["id"]


@pytest.mark.asyncio
async def test_exact_scene_count_trims_extra_outlines_and_caps_tokens():
    response = json.dumps({
        "outlines": [
            {"type": "slide", "title": f"Scene {i}"}
            for i in range(1, 9)
        ],
    })
    captured = {}

    async def _fake(*args, **kwargs):
        captured.update(kwargs)
        return response

    with patch(
        "apps.maic.generation.outline_generator.generate_text", new=_fake
    ):
        result = await generate_scene_outlines_from_requirements(
            requirements={"requirement": "Create exactly 6 scenes."},
            language_model_id="stub",
            options={"scene_count": 6},
        )

    assert result["success"]
    outlines = result["data"]["outlines"]
    assert len(outlines) == 6
    assert outlines[-1]["title"] == "Scene 6"
    assert captured["max_tokens"] == 3900


@pytest.mark.asyncio
async def test_exact_scene_count_shortfall_fails():
    response = json.dumps({
        "outlines": [
            {"type": "slide", "title": "Only one"},
        ],
    })

    async def _fake(*args, **kwargs):
        return response

    with patch(
        "apps.maic.generation.outline_generator.generate_text", new=_fake
    ):
        result = await generate_scene_outlines_from_requirements(
            requirements={"requirement": "Create exactly 3 scenes."},
            language_model_id="stub",
            options={"scene_count": 3},
        )

    assert not result["success"]
    assert "Expected exactly 3 scene outlines" in result["error"]


@pytest.mark.asyncio
async def test_unparseable_response_returns_failure():
    """LLM returns garbage → result.success=False with helpful error."""
    async def _fake(*args, **kwargs):
        return "this is not JSON anywhere"

    with patch(
        "apps.maic.generation.outline_generator.generate_text", new=_fake
    ):
        result = await generate_scene_outlines_from_requirements(
            requirements={"requirement": "x"}, language_model_id="stub",
        )
    assert result["success"] is False
    assert "Failed to parse" in result.get("error", "")


@pytest.mark.asyncio
async def test_object_response_missing_outlines_key_returns_failure():
    """An object without `outlines` is a schema regression."""
    response = json.dumps({
        "languageDirective": "test",
        "wrong_key": [{"type": "slide"}],
    })

    async def _fake(*args, **kwargs):
        return response

    with patch(
        "apps.maic.generation.outline_generator.generate_text", new=_fake
    ):
        result = await generate_scene_outlines_from_requirements(
            requirements={"requirement": "x"}, language_model_id="stub",
        )
    assert result["success"] is False


@pytest.mark.asyncio
async def test_user_profile_injected_when_present():
    """Verify the loader receives the user profile string (which the
    template uses for student-context injection)."""
    captured_vars = {}

    def _capture_load(template_id, vars):
        captured_vars.update(vars)
        from apps.maic.prompts.loader import BuiltPrompt
        return BuiltPrompt(system="sys", user="user")

    async def _fake_generate(*args, **kwargs):
        return json.dumps({"outlines": []})

    with patch(
        "apps.maic.generation.outline_generator.load_generation_prompt",
        side_effect=_capture_load,
    ):
        with patch(
            "apps.maic.generation.outline_generator.generate_text",
            new=_fake_generate,
        ):
            await generate_scene_outlines_from_requirements(
                requirements={
                    "requirement": "x",
                    "userNickname": "Alice",
                    "userBio": "10th grade math student",
                },
                language_model_id="stub",
            )
    assert "Alice" in captured_vars.get("userProfile", "")
    assert "10th grade" in captured_vars.get("userProfile", "")


@pytest.mark.asyncio
async def test_no_user_profile_when_neither_provided():
    """Empty profile string when no nickname/bio."""
    captured_vars = {}

    def _capture_load(template_id, vars):
        captured_vars.update(vars)
        from apps.maic.prompts.loader import BuiltPrompt
        return BuiltPrompt(system="sys", user="user")

    async def _fake_generate(*args, **kwargs):
        return json.dumps({"outlines": []})

    with patch(
        "apps.maic.generation.outline_generator.load_generation_prompt",
        side_effect=_capture_load,
    ):
        with patch(
            "apps.maic.generation.outline_generator.generate_text",
            new=_fake_generate,
        ):
            await generate_scene_outlines_from_requirements(
                requirements={"requirement": "x"},
                language_model_id="stub",
            )
    assert captured_vars["userProfile"] == ""


@pytest.mark.asyncio
async def test_progress_callback_fires_at_start_and_end():
    """Stage 1 fires onProgress twice — once before the LLM call,
    once after success."""
    progress_events = []

    async def _fake(*args, **kwargs):
        return json.dumps({"outlines": [{"type": "slide", "title": "T"}]})

    with patch(
        "apps.maic.generation.outline_generator.generate_text", new=_fake
    ):
        await generate_scene_outlines_from_requirements(
            requirements={"requirement": "x"},
            language_model_id="stub",
            callbacks={"onProgress": lambda p: progress_events.append(p)},
        )
    assert len(progress_events) == 2
    assert progress_events[0]["stage"] == 1
    assert progress_events[0]["total"] == 0
    assert progress_events[1]["total"] == 1


# ── Real-LLM smoke (gated) ────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="OPENROUTER_API_KEY not set; skipping real-LLM smoke",
)
async def test_real_openrouter_smoke():
    """Optional real-LLM smoke. Runs only when OPENROUTER_API_KEY is
    set in the environment. Verifies the full Stage 1 flow against a
    real cheap model."""
    result = await generate_scene_outlines_from_requirements(
        requirements={
            "requirement": "Teach the difference between numerator and denominator.",
            "language": "English",
        },
        language_model_id="openrouter/anthropic/claude-3.5-haiku",
    )
    assert result["success"], f"real-LLM stage 1 failed: {result.get('error')}"
    assert isinstance(result["data"]["outlines"], list)
    assert len(result["data"]["outlines"]) > 0
