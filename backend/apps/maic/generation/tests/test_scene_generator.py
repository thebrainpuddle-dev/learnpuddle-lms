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
async def test_dispatcher_routes_interactive_to_widget_content():
    """Interactive outlines hit the widget umbrella (MAIC-422.5)."""
    outline = {
        "type": "interactive",
        "title": "Wave Mechanics",
        "description": "interactive wave demo",
        "widgetType": "simulation",
        "widgetOutline": {"concept": "Wave Mechanics", "keyVariables": ["amplitude"]},
    }

    async def _fake(*args, **kwargs):
        return "<!DOCTYPE html><html><body>simulation</body></html>"

    with patch(
        "apps.maic.generation.scene_generator.generate_text", new=_fake
    ):
        content = await generate_scene_content(
            outline, language_model_id="stub"
        )
    assert content is not None
    assert content["widgetType"] == "simulation"
    assert "<html>" in content["html"]
    assert content["teacherActions"] is None  # MAIC-422.7 lands later


@pytest.mark.asyncio
async def test_dispatcher_routes_pbl_to_stub():
    """PBL outlines hit the programmatic STUB (MAIC-422.4) — no LLM."""
    outline = {
        "type": "pbl",
        "title": "Build a Mini-LMS",
        "description": "Project description",
    }
    content = await generate_scene_content(outline)
    assert content is not None
    assert "projectConfig" in content
    pc = content["projectConfig"]
    assert pc["projectInfo"]["title"] == "Build a Mini-LMS"
    assert pc["projectInfo"]["description"] == "Project description"
    assert pc["agents"] == []
    assert pc["issueboard"] == {
        "agent_ids": [],
        "issues": [],
        "current_issue_id": None,
    }
    assert pc["chat"] == {"messages": []}


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


# ── Scene actions dispatcher (MAIC-422.1) ─────────────────────────


from apps.maic.generation.scene_generator import generate_scene_actions


@pytest.mark.asyncio
async def test_actions_dispatcher_routes_slide():
    outline = {"type": "slide", "title": "T", "keyPoints": ["a"]}
    content = {
        "elements": [
            {"id": "el-1", "type": "text", "content": "hello"},
        ],
    }

    async def _fake(*args, **kwargs):
        return json.dumps([
            {"type": "action", "name": "spotlight", "params": {"elementId": "el-1"}},
            {"type": "text", "content": "describing the slide"},
        ])

    with patch(
        "apps.maic.generation.scene_generator.generate_text", new=_fake
    ):
        actions = await generate_scene_actions(
            outline, content, language_model_id="stub"
        )
    assert len(actions) == 2
    assert actions[0]["type"] == "spotlight"
    assert actions[0]["elementId"] == "el-1"
    assert actions[1]["type"] == "speech"
    assert actions[1]["text"] == "describing the slide"


@pytest.mark.asyncio
async def test_actions_dispatcher_routes_quiz():
    """Quiz outlines now hit the quiz-actions branch (MAIC-422.3)."""
    outline = {"type": "quiz", "title": "Q", "keyPoints": ["a"]}
    content = {
        "questions": [
            {"id": "q_1", "type": "single", "question": "What?", "options": []},
        ],
    }

    async def _fake(*args, **kwargs):
        return json.dumps([
            {"type": "text", "content": "Let's test what we learned."},
            {
                "type": "action",
                "name": "discussion",
                "params": {"topic": "What did this quiz reveal?"},
            },
        ])

    with patch(
        "apps.maic.generation.scene_generator.generate_text", new=_fake
    ):
        actions = await generate_scene_actions(
            outline, content, language_model_id="stub"
        )
    assert len(actions) == 2
    assert actions[0]["type"] == "speech"
    assert actions[0]["text"] == "Let's test what we learned."
    assert actions[1]["type"] == "discussion"


@pytest.mark.asyncio
async def test_actions_dispatcher_routes_interactive():
    """Interactive outlines now hit the interactive-actions branch
    (MAIC-422.6)."""
    outline = {
        "type": "interactive",
        "title": "Wave Mechanics",
        "keyPoints": ["amplitude", "frequency"],
        "widgetType": "simulation",
        "widgetOutline": {"concept": "Wave Mechanics"},
    }
    content = {
        "html": "<html><body>widget</body></html>",
        "widgetType": "simulation",
        "widgetConfig": None,
        "teacherActions": None,
    }

    async def _fake(*args, **kwargs):
        return json.dumps([
            {"type": "text", "content": "Try adjusting the amplitude slider."},
        ])

    with patch(
        "apps.maic.generation.scene_generator.generate_text", new=_fake
    ):
        actions = await generate_scene_actions(
            outline, content, language_model_id="stub"
        )
    assert len(actions) == 1
    assert actions[0]["type"] == "speech"
    assert "amplitude" in actions[0]["text"]


@pytest.mark.asyncio
async def test_actions_dispatcher_routes_pbl():
    """PBL outlines now hit the pbl-actions branch (MAIC-422.4)."""
    outline = {"type": "pbl", "title": "P", "keyPoints": []}
    content = {"projectConfig": {"projectInfo": {"title": "P"}}}

    async def _fake(*args, **kwargs):
        return json.dumps([
            {"type": "text", "content": "Welcome to the project."},
        ])

    with patch(
        "apps.maic.generation.scene_generator.generate_text", new=_fake
    ):
        actions = await generate_scene_actions(
            outline, content, language_model_id="stub"
        )
    assert len(actions) == 1
    assert actions[0]["type"] == "speech"
    assert actions[0]["text"] == "Welcome to the project."


# ── Slide actions branch ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_slide_actions_falls_back_to_default_when_llm_returns_empty():
    """LLM returns nothing parseable → default actions."""
    outline = {
        "type": "slide",
        "title": "Photosynthesis",
        "description": "intro",
        "keyPoints": ["chlorophyll", "light"],
    }
    content = {
        "elements": [
            {"id": "el-1", "type": "text", "content": "hello"},
        ],
    }

    async def _fake(*args, **kwargs):
        return "garbage no JSON"

    with patch(
        "apps.maic.generation.scene_generator.generate_text", new=_fake
    ):
        actions = await generate_scene_actions(
            outline, content, language_model_id="stub"
        )
    # Default fallback: spotlight on first text element + speech with
    # joined keyPoints.
    types = [a["type"] for a in actions]
    assert "spotlight" in types
    assert "speech" in types
    speech = next(a for a in actions if a["type"] == "speech")
    assert "chlorophyll" in speech["text"]
    assert "light" in speech["text"]


@pytest.mark.asyncio
async def test_slide_actions_default_uses_description_when_no_keypoints():
    """No keyPoints → speech.text falls back to description."""
    outline = {
        "type": "slide",
        "title": "T",
        "description": "fallback desc",
        "keyPoints": [],
    }
    content = {"elements": []}

    async def _fake(*args, **kwargs):
        return "no actions here"

    with patch(
        "apps.maic.generation.scene_generator.generate_text", new=_fake
    ):
        actions = await generate_scene_actions(
            outline, content, language_model_id="stub"
        )
    speech = next(a for a in actions if a["type"] == "speech")
    assert speech["text"] == "fallback desc"


@pytest.mark.asyncio
async def test_slide_actions_default_uses_title_when_no_keypoints_or_description():
    outline = {"type": "slide", "title": "Just a title"}
    content = {"elements": []}

    async def _fake(*args, **kwargs):
        return "no actions"

    with patch(
        "apps.maic.generation.scene_generator.generate_text", new=_fake
    ):
        actions = await generate_scene_actions(
            outline, content, language_model_id="stub"
        )
    speech = next(a for a in actions if a["type"] == "speech")
    assert speech["text"] == "Just a title"


@pytest.mark.asyncio
async def test_slide_actions_processes_invalid_element_id():
    """spotlight.elementId pointing at non-existent element gets
    rewritten to the first element's id (defense in depth)."""
    outline = {"type": "slide", "title": "T"}
    content = {
        "elements": [
            {"id": "real-el", "type": "text", "content": "x"},
        ],
    }

    async def _fake(*args, **kwargs):
        return json.dumps([
            {"type": "action", "name": "spotlight", "params": {"elementId": "ghost"}},
        ])

    with patch(
        "apps.maic.generation.scene_generator.generate_text", new=_fake
    ):
        actions = await generate_scene_actions(
            outline, content, language_model_id="stub"
        )
    assert actions[0]["elementId"] == "real-el"


@pytest.mark.asyncio
async def test_slide_actions_processes_discussion_invalid_agent():
    """discussion.agentId pointing at unknown agent gets reassigned
    to a random student (or non-teacher)."""
    outline = {"type": "slide", "title": "T"}
    content = {"elements": [{"id": "e1", "type": "text"}]}
    agents = [
        {"id": "default-1", "name": "Teacher", "role": "teacher"},
        {"id": "default-3", "name": "Student", "role": "student"},
    ]

    async def _fake(*args, **kwargs):
        return json.dumps([
            {
                "type": "action",
                "name": "discussion",
                "params": {"agentId": "ghost", "topic": "test"},
            },
        ])

    with patch(
        "apps.maic.generation.scene_generator.generate_text", new=_fake
    ):
        actions = await generate_scene_actions(
            outline,
            content,
            language_model_id="stub",
            options={"agents": agents},
        )
    # discussion got reassigned to a student
    assert actions[0]["agentId"] == "default-3"


@pytest.mark.asyncio
async def test_slide_actions_action_ids_filled():
    """Actions arriving without an id get a generated `action_<8chars>` id."""
    outline = {"type": "slide", "title": "T"}
    content = {"elements": []}

    async def _fake(*args, **kwargs):
        # action without explicit id
        return json.dumps([
            {"type": "action", "name": "wb_open", "params": {}},
        ])

    with patch(
        "apps.maic.generation.scene_generator.generate_text", new=_fake
    ):
        actions = await generate_scene_actions(
            outline, content, language_model_id="stub"
        )
    assert actions[0]["id"].startswith("action_")
    assert len(actions[0]["id"]) > len("action_")


@pytest.mark.asyncio
async def test_slide_actions_passes_course_context_into_prompt():
    """Course context (page index + previous speeches) flows into
    the slide-actions prompt via build_course_context."""
    captured_vars = {}

    def _capture(template_id, vars):
        captured_vars.update(vars)
        from apps.maic.prompts.loader import BuiltPrompt
        return BuiltPrompt(system="sys", user="user")

    async def _fake(*args, **kwargs):
        return json.dumps([])

    outline = {"type": "slide", "title": "T", "keyPoints": []}
    content = {"elements": []}
    ctx = {
        "pageIndex": 2,
        "totalPages": 5,
        "allTitles": ["A", "B", "C", "D", "E"],
        "previousSpeeches": ["earlier speech text"],
    }

    with patch(
        "apps.maic.generation.scene_generator.load_generation_prompt",
        side_effect=_capture,
    ):
        with patch(
            "apps.maic.generation.scene_generator.generate_text", new=_fake
        ):
            await generate_scene_actions(
                outline,
                content,
                language_model_id="stub",
                options={"ctx": ctx},
            )
    assert "Page 2 of 5" in captured_vars["courseContext"]
    assert "earlier speech text" in captured_vars["courseContext"]


# ── Quiz-content branch (MAIC-422.2) ──────────────────────────────


@pytest.mark.asyncio
async def test_dispatcher_routes_quiz_to_quiz_content():
    """Quiz outlines now hit the quiz-content branch (MAIC-422.2)."""
    outline = {
        "type": "quiz",
        "title": "Photosynthesis Quiz",
        "description": "test understanding",
        "keyPoints": ["chlorophyll", "ATP"],
    }

    async def _fake(*args, **kwargs):
        return json.dumps([
            {
                "type": "single",
                "question": "What pigment captures light?",
                "options": ["chlorophyll", "hemoglobin", "melanin"],
                "correctAnswer": "A",
            },
        ])

    with patch(
        "apps.maic.generation.scene_generator.generate_text", new=_fake
    ):
        content = await generate_scene_content(outline, language_model_id="stub")
    assert content is not None
    assert "questions" in content
    assert len(content["questions"]) == 1


@pytest.mark.asyncio
async def test_quiz_questions_get_unique_ids():
    """Generated question IDs must be unique within one call."""
    outline = {"type": "quiz", "title": "Q"}

    async def _fake(*args, **kwargs):
        return json.dumps([
            {"type": "single", "question": "Q1?", "options": ["a", "b"]},
            {"type": "single", "question": "Q2?", "options": ["a", "b"]},
            {"type": "single", "question": "Q3?", "options": ["a", "b"]},
        ])

    with patch(
        "apps.maic.generation.scene_generator.generate_text", new=_fake
    ):
        content = await generate_scene_content(outline, language_model_id="stub")
    ids = [q["id"] for q in content["questions"]]
    assert len(set(ids)) == 3  # all unique
    for q_id in ids:
        assert q_id.startswith("q_")


@pytest.mark.asyncio
async def test_quiz_options_normalized_from_string_array():
    """Plain string options get coerced to {value: letter, label: str}."""
    outline = {"type": "quiz", "title": "T"}

    async def _fake(*args, **kwargs):
        return json.dumps([
            {
                "type": "single",
                "question": "?",
                "options": ["First", "Second", "Third"],
            },
        ])

    with patch(
        "apps.maic.generation.scene_generator.generate_text", new=_fake
    ):
        content = await generate_scene_content(outline, language_model_id="stub")
    options = content["questions"][0]["options"]
    assert options == [
        {"value": "A", "label": "First"},
        {"value": "B", "label": "Second"},
        {"value": "C", "label": "Third"},
    ]


@pytest.mark.asyncio
async def test_quiz_options_normalized_from_dict_array():
    """Dict options pass through with letter fallback when missing."""
    outline = {"type": "quiz", "title": "T"}

    async def _fake(*args, **kwargs):
        return json.dumps([
            {
                "type": "single",
                "question": "?",
                "options": [
                    {"value": "X", "label": "First"},  # explicit value
                    {"label": "Second"},  # missing value → fallback letter
                    {"value": "C"},  # missing label → use value as label
                ],
            },
        ])

    with patch(
        "apps.maic.generation.scene_generator.generate_text", new=_fake
    ):
        content = await generate_scene_content(outline, language_model_id="stub")
    options = content["questions"][0]["options"]
    assert options[0] == {"value": "X", "label": "First"}
    assert options[1] == {"value": "B", "label": "Second"}  # B from index
    assert options[2]["value"] == "C"


@pytest.mark.asyncio
async def test_quiz_answer_normalized_from_various_field_names():
    """The AI may use answer / correctAnswer / correct_answer; all
    three resolve to a string[] under `answer`."""
    outline = {"type": "quiz", "title": "T"}

    async def _fake(*args, **kwargs):
        return json.dumps([
            {"type": "single", "question": "Q1", "answer": "A"},
            {"type": "single", "question": "Q2", "correctAnswer": "B"},
            {"type": "single", "question": "Q3", "correct_answer": ["C", "D"]},
        ])

    with patch(
        "apps.maic.generation.scene_generator.generate_text", new=_fake
    ):
        content = await generate_scene_content(outline, language_model_id="stub")
    assert content["questions"][0]["answer"] == ["A"]
    assert content["questions"][1]["answer"] == ["B"]
    assert content["questions"][2]["answer"] == ["C", "D"]


@pytest.mark.asyncio
async def test_short_answer_questions_have_no_options_or_answer():
    """short_answer questions are free-form — options + answer get
    nulled, hasAnswer=False."""
    outline = {"type": "quiz", "title": "T"}

    async def _fake(*args, **kwargs):
        return json.dumps([
            {
                "type": "short_answer",
                "question": "Explain photosynthesis.",
                "options": ["should", "be", "stripped"],
                "correctAnswer": "free response",
            },
        ])

    with patch(
        "apps.maic.generation.scene_generator.generate_text", new=_fake
    ):
        content = await generate_scene_content(outline, language_model_id="stub")
    q = content["questions"][0]
    assert q["options"] is None
    assert q["answer"] is None
    assert q["hasAnswer"] is False


@pytest.mark.asyncio
async def test_other_question_types_have_hasAnswer_true():
    outline = {"type": "quiz", "title": "T"}

    async def _fake(*args, **kwargs):
        return json.dumps([
            {"type": "single", "question": "?", "options": ["a"], "answer": "A"},
        ])

    with patch(
        "apps.maic.generation.scene_generator.generate_text", new=_fake
    ):
        content = await generate_scene_content(outline, language_model_id="stub")
    assert content["questions"][0]["hasAnswer"] is True


@pytest.mark.asyncio
async def test_quiz_content_returns_none_on_parse_failure():
    outline = {"type": "quiz", "title": "T"}

    async def _fake(*args, **kwargs):
        return "not json at all"

    with patch(
        "apps.maic.generation.scene_generator.generate_text", new=_fake
    ):
        content = await generate_scene_content(outline, language_model_id="stub")
    assert content is None


@pytest.mark.asyncio
async def test_quiz_uses_default_config_when_outline_has_none():
    """No quizConfig → defaults: 3 questions, medium, ['single']."""
    captured_vars = {}

    def _capture(template_id, vars):
        captured_vars.update(vars)
        from apps.maic.prompts.loader import BuiltPrompt
        return BuiltPrompt(system="sys", user="user")

    async def _fake(*args, **kwargs):
        return json.dumps([])

    outline = {"type": "quiz", "title": "T"}

    with patch(
        "apps.maic.generation.scene_generator.load_generation_prompt",
        side_effect=_capture,
    ):
        with patch(
            "apps.maic.generation.scene_generator.generate_text", new=_fake
        ):
            await generate_scene_content(outline, language_model_id="stub")
    assert captured_vars["questionCount"] == 3
    assert captured_vars["difficulty"] == "medium"
    assert captured_vars["questionTypes"] == "single"


@pytest.mark.asyncio
async def test_quiz_uses_explicit_quizConfig_when_provided():
    """When the outline carries quizConfig, those values flow into
    the prompt instead of the defaults."""
    captured_vars = {}

    def _capture(template_id, vars):
        captured_vars.update(vars)
        from apps.maic.prompts.loader import BuiltPrompt
        return BuiltPrompt(system="sys", user="user")

    async def _fake(*args, **kwargs):
        return json.dumps([])

    outline = {
        "type": "quiz",
        "title": "T",
        "quizConfig": {
            "questionCount": 7,
            "difficulty": "hard",
            "questionTypes": ["single", "multiple", "short_answer"],
        },
    }

    with patch(
        "apps.maic.generation.scene_generator.load_generation_prompt",
        side_effect=_capture,
    ):
        with patch(
            "apps.maic.generation.scene_generator.generate_text", new=_fake
        ):
            await generate_scene_content(outline, language_model_id="stub")
    assert captured_vars["questionCount"] == 7
    assert captured_vars["difficulty"] == "hard"
    assert captured_vars["questionTypes"] == "single, multiple, short_answer"


# ── Quiz-actions branch (MAIC-422.3) ──────────────────────────────


@pytest.mark.asyncio
async def test_quiz_actions_falls_back_to_default_when_llm_returns_empty():
    """LLM returns nothing parseable → default quiz actions."""
    outline = {
        "type": "quiz",
        "title": "Photosynthesis Quiz",
        "description": "intro",
        "keyPoints": ["chlorophyll"],
    }
    content = {
        "questions": [
            {"id": "q1", "type": "single", "question": "?", "options": []},
        ],
    }

    async def _fake(*args, **kwargs):
        return "no JSON here"

    with patch(
        "apps.maic.generation.scene_generator.generate_text", new=_fake
    ):
        actions = await generate_scene_actions(
            outline, content, language_model_id="stub"
        )
    # Default quiz fallback: a single intro speech.
    assert len(actions) == 1
    assert actions[0]["type"] == "speech"
    assert actions[0]["title"] == "测验引导"
    assert actions[0]["id"].startswith("action_")


@pytest.mark.asyncio
async def test_quiz_actions_default_on_missing_template():
    """Prompt template missing → default fallback (no LLM call)."""
    outline = {"type": "quiz", "title": "T", "keyPoints": []}
    content = {"questions": []}

    from apps.maic.exceptions import MaicConfigError

    def _raise(*args, **kwargs):
        raise MaicConfigError("template not found: quiz-actions")

    async def _fake_text(*args, **kwargs):  # should NOT be called
        raise AssertionError("LLM must not be called when template missing")

    with patch(
        "apps.maic.generation.scene_generator.load_generation_prompt",
        side_effect=_raise,
    ):
        with patch(
            "apps.maic.generation.scene_generator.generate_text",
            new=_fake_text,
        ):
            actions = await generate_scene_actions(
                outline, content, language_model_id="stub"
            )
    assert len(actions) == 1
    assert actions[0]["type"] == "speech"


@pytest.mark.asyncio
async def test_quiz_actions_passes_questions_summary_into_prompt():
    """Per-question summary lines flow into the quiz-actions prompt
    so the LLM can write narration that references specific items."""
    captured_vars = {}

    def _capture(template_id, vars):
        captured_vars.update(vars)
        from apps.maic.prompts.loader import BuiltPrompt
        return BuiltPrompt(system="sys", user="user")

    async def _fake(*args, **kwargs):
        return json.dumps([])

    outline = {"type": "quiz", "title": "T", "keyPoints": []}
    content = {
        "questions": [
            {
                "id": "q1",
                "type": "single",
                "question": "What pigment captures light?",
                "options": [
                    {"value": "A", "label": "chlorophyll"},
                    {"value": "B", "label": "hemoglobin"},
                ],
            },
            {
                "id": "q2",
                "type": "short_answer",
                "question": "Explain ATP.",
            },
        ],
    }

    with patch(
        "apps.maic.generation.scene_generator.load_generation_prompt",
        side_effect=_capture,
    ):
        with patch(
            "apps.maic.generation.scene_generator.generate_text", new=_fake
        ):
            await generate_scene_actions(
                outline, content, language_model_id="stub"
            )
    questions_text = captured_vars["questions"]
    assert "Q1 (single)" in questions_text
    assert "What pigment captures light?" in questions_text
    assert "A. chlorophyll" in questions_text
    assert "Q2 (short_answer)" in questions_text


@pytest.mark.asyncio
async def test_quiz_actions_processes_discussion_invalid_agent():
    """Discussion in quiz actions: invalid agentId reassigned to a
    student (mirrors upstream's processActions on quiz scenes)."""
    outline = {"type": "quiz", "title": "T", "keyPoints": []}
    content = {"questions": [{"id": "q1", "type": "single", "question": "?"}]}
    agents = [
        {"id": "default-1", "name": "Teacher", "role": "teacher"},
        {"id": "default-3", "name": "Student", "role": "student"},
    ]

    async def _fake(*args, **kwargs):
        return json.dumps([
            {
                "type": "action",
                "name": "discussion",
                "params": {"agentId": "ghost", "topic": "T"},
            },
        ])

    with patch(
        "apps.maic.generation.scene_generator.generate_text", new=_fake
    ):
        actions = await generate_scene_actions(
            outline,
            content,
            language_model_id="stub",
            options={"agents": agents},
        )
    assert actions[0]["agentId"] == "default-3"


@pytest.mark.asyncio
async def test_quiz_actions_passes_course_context():
    """Course context (page index + previous speeches) flows into
    the quiz-actions prompt via build_course_context."""
    captured_vars = {}

    def _capture(template_id, vars):
        captured_vars.update(vars)
        from apps.maic.prompts.loader import BuiltPrompt
        return BuiltPrompt(system="sys", user="user")

    async def _fake(*args, **kwargs):
        return json.dumps([])

    outline = {"type": "quiz", "title": "T", "keyPoints": []}
    content = {"questions": []}
    ctx = {
        "pageIndex": 4,
        "totalPages": 6,
        "allTitles": ["A", "B", "C", "D", "E", "F"],
        "previousSpeeches": ["intro speech"],
    }

    with patch(
        "apps.maic.generation.scene_generator.load_generation_prompt",
        side_effect=_capture,
    ):
        with patch(
            "apps.maic.generation.scene_generator.generate_text", new=_fake
        ):
            await generate_scene_actions(
                outline,
                content,
                language_model_id="stub",
                options={"ctx": ctx},
            )
    assert "Page 4 of 6" in captured_vars["courseContext"]
    assert "intro speech" in captured_vars["courseContext"]


@pytest.mark.asyncio
async def test_quiz_actions_default_when_llm_call_fails():
    """LLM error → default fallback (don't propagate)."""
    outline = {"type": "quiz", "title": "T", "keyPoints": []}
    content = {"questions": []}

    async def _fake(*args, **kwargs):
        raise RuntimeError("provider down")

    with patch(
        "apps.maic.generation.scene_generator.generate_text", new=_fake
    ):
        actions = await generate_scene_actions(
            outline, content, language_model_id="stub"
        )
    assert len(actions) == 1
    assert actions[0]["type"] == "speech"


def test_format_questions_for_prompt_handles_string_options():
    """Defense in depth: if normalize wasn't applied, string options
    still render gracefully (don't crash)."""
    from apps.maic.generation.scene_generator import _format_questions_for_prompt
    out = _format_questions_for_prompt([
        {"type": "single", "question": "?", "options": ["a", "b"]},
    ])
    assert "Q1 (single)" in out
    # raw strings render as themselves
    assert "a" in out and "b" in out


def test_format_questions_for_prompt_omits_options_when_absent():
    from apps.maic.generation.scene_generator import _format_questions_for_prompt
    out = _format_questions_for_prompt([
        {"type": "short_answer", "question": "Explain X."},
    ])
    assert "Q1 (short_answer): Explain X." in out
    assert "Options:" not in out


# ── PBL content STUB (MAIC-422.4) ─────────────────────────────────


@pytest.mark.asyncio
async def test_pbl_content_stub_uses_pblConfig_when_provided():
    """When outline.pblConfig has projectTopic + projectDescription,
    those win over outline.title / outline.description."""
    outline = {
        "type": "pbl",
        "title": "outer-title",
        "description": "outer-desc",
        "pblConfig": {
            "projectTopic": "explicit-topic",
            "projectDescription": "explicit-desc",
        },
    }
    content = await generate_scene_content(outline)
    assert content["projectConfig"]["projectInfo"] == {
        "title": "explicit-topic",
        "description": "explicit-desc",
    }


@pytest.mark.asyncio
async def test_pbl_content_stub_does_not_call_llm():
    """The STUB is purely programmatic — no `generate_text` call."""
    outline = {"type": "pbl", "title": "T"}

    async def _fake(*args, **kwargs):
        raise AssertionError("STUB must not call generate_text")

    with patch(
        "apps.maic.generation.scene_generator.generate_text", new=_fake
    ):
        content = await generate_scene_content(outline, language_model_id="stub")
    assert content is not None
    assert "projectConfig" in content


# ── PBL actions branch (MAIC-422.4) ───────────────────────────────


@pytest.mark.asyncio
async def test_pbl_actions_falls_back_to_default_when_llm_returns_empty():
    """LLM returns nothing parseable → default PBL kickoff speech."""
    outline = {
        "type": "pbl",
        "title": "Mini Project",
        "description": "intro",
        "keyPoints": ["a"],
    }
    content = {"projectConfig": {"projectInfo": {"title": "Mini Project"}}}

    async def _fake(*args, **kwargs):
        return "no JSON here"

    with patch(
        "apps.maic.generation.scene_generator.generate_text", new=_fake
    ):
        actions = await generate_scene_actions(
            outline, content, language_model_id="stub"
        )
    assert len(actions) == 1
    assert actions[0]["type"] == "speech"
    assert actions[0]["title"] == "PBL 项目介绍"


@pytest.mark.asyncio
async def test_pbl_actions_default_on_missing_template():
    outline = {"type": "pbl", "title": "T", "keyPoints": []}
    content = {"projectConfig": {}}

    from apps.maic.exceptions import MaicConfigError

    def _raise(*args, **kwargs):
        raise MaicConfigError("template not found: pbl-actions")

    async def _fake_text(*args, **kwargs):
        raise AssertionError("LLM must not be called when template missing")

    with patch(
        "apps.maic.generation.scene_generator.load_generation_prompt",
        side_effect=_raise,
    ):
        with patch(
            "apps.maic.generation.scene_generator.generate_text",
            new=_fake_text,
        ):
            actions = await generate_scene_actions(
                outline, content, language_model_id="stub"
            )
    assert len(actions) == 1
    assert actions[0]["type"] == "speech"


@pytest.mark.asyncio
async def test_pbl_actions_default_when_llm_call_fails():
    outline = {"type": "pbl", "title": "T", "keyPoints": []}
    content = {"projectConfig": {}}

    async def _fake(*args, **kwargs):
        raise RuntimeError("provider down")

    with patch(
        "apps.maic.generation.scene_generator.generate_text", new=_fake
    ):
        actions = await generate_scene_actions(
            outline, content, language_model_id="stub"
        )
    assert len(actions) == 1
    assert actions[0]["type"] == "speech"


@pytest.mark.asyncio
async def test_pbl_actions_passes_pblConfig_into_prompt():
    """projectTopic / projectDescription from outline.pblConfig flow
    into the pbl-actions prompt (mirrors upstream lines 1269-1270)."""
    captured_vars = {}

    def _capture(template_id, vars):
        captured_vars.update(vars)
        from apps.maic.prompts.loader import BuiltPrompt
        return BuiltPrompt(system="sys", user="user")

    async def _fake(*args, **kwargs):
        return json.dumps([])

    outline = {
        "type": "pbl",
        "title": "fallback-title",
        "description": "fallback-desc",
        "pblConfig": {
            "projectTopic": "explicit-topic",
            "projectDescription": "explicit-desc",
        },
    }
    content = {"projectConfig": {}}

    with patch(
        "apps.maic.generation.scene_generator.load_generation_prompt",
        side_effect=_capture,
    ):
        with patch(
            "apps.maic.generation.scene_generator.generate_text", new=_fake
        ):
            await generate_scene_actions(
                outline, content, language_model_id="stub"
            )
    assert captured_vars["projectTopic"] == "explicit-topic"
    assert captured_vars["projectDescription"] == "explicit-desc"


@pytest.mark.asyncio
async def test_pbl_actions_falls_back_to_outline_when_no_pblConfig():
    """No pblConfig → projectTopic/Description fall back to title/desc."""
    captured_vars = {}

    def _capture(template_id, vars):
        captured_vars.update(vars)
        from apps.maic.prompts.loader import BuiltPrompt
        return BuiltPrompt(system="sys", user="user")

    async def _fake(*args, **kwargs):
        return json.dumps([])

    outline = {
        "type": "pbl",
        "title": "Outline Title",
        "description": "Outline Desc",
    }
    content = {"projectConfig": {}}

    with patch(
        "apps.maic.generation.scene_generator.load_generation_prompt",
        side_effect=_capture,
    ):
        with patch(
            "apps.maic.generation.scene_generator.generate_text", new=_fake
        ):
            await generate_scene_actions(
                outline, content, language_model_id="stub"
            )
    assert captured_vars["projectTopic"] == "Outline Title"
    assert captured_vars["projectDescription"] == "Outline Desc"


# ── Interactive / widget content (MAIC-422.5) ─────────────────────


@pytest.mark.asyncio
async def test_interactive_simulation_routes_to_simulation_template():
    """The widget-content branch loads the simulation-content template
    first; MAIC-422.7's widget-teacher-actions call lands second."""
    template_ids: list[str] = []

    def _capture(template_id, vars):
        template_ids.append(template_id)
        from apps.maic.prompts.loader import BuiltPrompt
        return BuiltPrompt(system="sys", user="user")

    async def _fake(*args, **kwargs):
        return "<!DOCTYPE html><html><body>x</body></html>"

    outline = {
        "type": "interactive",
        "title": "T",
        "widgetType": "simulation",
        "widgetOutline": {"concept": "C"},
    }

    with patch(
        "apps.maic.generation.scene_generator.load_generation_prompt",
        side_effect=_capture,
    ):
        with patch(
            "apps.maic.generation.scene_generator.generate_text", new=_fake
        ):
            await generate_scene_content(outline, language_model_id="stub")
    assert template_ids[0] == "simulation-content"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "widget_type, expected_template, extra_outline",
    [
        ("simulation", "simulation-content", {"concept": "C"}),
        ("diagram", "diagram-content", {"diagramType": "flowchart"}),
        ("code", "code-content", {"language": "python"}),
        ("game", "game-content", {"gameType": "quiz"}),
        (
            "visualization3d",
            "visualization3d-content",
            {"visualizationType": "custom"},
        ),
    ],
)
async def test_each_widget_type_routes_to_its_template(
    widget_type, expected_template, extra_outline
):
    """Per-widget content template is loaded FIRST; widget-teacher-
    actions lands second (MAIC-422.7)."""
    template_ids: list[str] = []

    def _capture(template_id, vars):
        template_ids.append(template_id)
        from apps.maic.prompts.loader import BuiltPrompt
        return BuiltPrompt(system="sys", user="user")

    async def _fake(*args, **kwargs):
        return "<!DOCTYPE html><html><body>x</body></html>"

    outline = {
        "type": "interactive",
        "title": "T",
        "description": "d",
        "widgetType": widget_type,
        "widgetOutline": extra_outline,
    }

    with patch(
        "apps.maic.generation.scene_generator.load_generation_prompt",
        side_effect=_capture,
    ):
        with patch(
            "apps.maic.generation.scene_generator.generate_text", new=_fake
        ):
            content = await generate_scene_content(
                outline, language_model_id="stub"
            )
    assert template_ids[0] == expected_template
    assert content is not None
    assert content["widgetType"] == widget_type


@pytest.mark.asyncio
async def test_interactive_returns_none_on_html_extraction_failure():
    outline = {
        "type": "interactive",
        "title": "T",
        "widgetType": "simulation",
        "widgetOutline": {"concept": "C"},
    }

    async def _fake(*args, **kwargs):
        return "no html anywhere — just prose"

    with patch(
        "apps.maic.generation.scene_generator.generate_text", new=_fake
    ):
        content = await generate_scene_content(outline, language_model_id="stub")
    assert content is None


@pytest.mark.asyncio
async def test_interactive_returns_none_on_unknown_widget_type():
    outline = {
        "type": "interactive",
        "title": "T",
        "widgetType": "totally-fake-widget",
        "widgetOutline": {"concept": "C"},
    }
    content = await generate_scene_content(outline, language_model_id="stub")
    assert content is None


@pytest.mark.asyncio
async def test_interactive_defaults_to_simulation_when_no_widget_config():
    """Defensive: outline_generator already handles this case but if
    an interactive arrives sans widget config, default to a simulation
    keyed on title (mirrors upstream lines 307-316)."""
    captures: list[tuple[str, dict]] = []

    def _capture(template_id, vars):
        captures.append((template_id, dict(vars)))
        from apps.maic.prompts.loader import BuiltPrompt
        return BuiltPrompt(system="sys", user="user")

    async def _fake(*args, **kwargs):
        return "<!DOCTYPE html><html><body>x</body></html>"

    outline = {
        "type": "interactive",
        "title": "Bare Interactive",
        "description": "no widget config at all",
    }

    with patch(
        "apps.maic.generation.scene_generator.load_generation_prompt",
        side_effect=_capture,
    ):
        with patch(
            "apps.maic.generation.scene_generator.generate_text", new=_fake
        ):
            content = await generate_scene_content(
                outline, language_model_id="stub"
            )
    # First capture is the widget content (simulation-content); the
    # second is widget-teacher-actions (MAIC-422.7).
    assert captures[0][0] == "simulation-content"
    assert captures[0][1]["conceptName"] == "Bare Interactive"
    assert content is not None
    assert content["widgetType"] == "simulation"


@pytest.mark.asyncio
async def test_interactive_html_runs_through_post_processor():
    """LaTeX delimiters in the LLM output get converted by
    post_process_interactive_html (mirrors upstream line 1090)."""
    outline = {
        "type": "interactive",
        "title": "T",
        "widgetType": "simulation",
        "widgetOutline": {"concept": "C"},
    }

    # \\( ... \\) is upstream LaTeX; post-processor converts to $ ... $
    raw_html = (
        '<!DOCTYPE html><html><body>'
        r'<p>The formula is \(E = mc^2\).</p>'
        '</body></html>'
    )

    async def _fake(*args, **kwargs):
        return raw_html

    with patch(
        "apps.maic.generation.scene_generator.generate_text", new=_fake
    ):
        content = await generate_scene_content(outline, language_model_id="stub")
    # Post-processor injects KaTeX script; original LaTeX should
    # remain in the body in some form (either converted or preserved).
    assert content is not None
    assert "html" in content
    # KaTeX CDN injection lands somewhere in the document.
    assert "katex" in content["html"].lower()


@pytest.mark.asyncio
async def test_interactive_extracts_widget_config_when_present():
    """If the LLM-generated HTML embeds a `<script id="widget-config">`,
    the JSON inside is parsed and surfaced under widgetConfig."""
    outline = {
        "type": "interactive",
        "title": "T",
        "widgetType": "simulation",
        "widgetOutline": {"concept": "C"},
    }
    config_payload = '{"engine": "p5", "params": {"speed": 1.5}}'
    html = (
        '<!DOCTYPE html><html><head>'
        f'<script type="application/json" id="widget-config">{config_payload}</script>'
        '</head><body>x</body></html>'
    )

    async def _fake(*args, **kwargs):
        return html

    with patch(
        "apps.maic.generation.scene_generator.generate_text", new=_fake
    ):
        content = await generate_scene_content(outline, language_model_id="stub")
    assert content["widgetConfig"] == {
        "engine": "p5",
        "params": {"speed": 1.5},
    }


@pytest.mark.asyncio
async def test_interactive_widget_config_is_none_when_absent():
    outline = {
        "type": "interactive",
        "title": "T",
        "widgetType": "simulation",
        "widgetOutline": {"concept": "C"},
    }

    async def _fake(*args, **kwargs):
        return "<!DOCTYPE html><html><body>no config</body></html>"

    with patch(
        "apps.maic.generation.scene_generator.generate_text", new=_fake
    ):
        content = await generate_scene_content(outline, language_model_id="stub")
    assert content["widgetConfig"] is None


# ── extract_html / extract_widget_config helpers ──────────────────


def test_extract_html_finds_doctype_document():
    from apps.maic.generation.scene_generator import _extract_html
    out = _extract_html("preamble<!DOCTYPE html><html>x</html>trailing")
    assert out == "<!DOCTYPE html><html>x</html>"


def test_extract_html_finds_html_tag_when_no_doctype():
    from apps.maic.generation.scene_generator import _extract_html
    out = _extract_html("<html>x</html>")
    assert out == "<html>x</html>"


def test_extract_html_pulls_from_code_block():
    from apps.maic.generation.scene_generator import _extract_html
    response = "Here you go:\n```html\n<html>x</html>\n```\nhope it helps"
    out = _extract_html(response)
    assert out is not None
    assert "<html>x</html>" in out


def test_extract_html_returns_none_when_no_html_anywhere():
    from apps.maic.generation.scene_generator import _extract_html
    assert _extract_html("just prose, no markup") is None


def test_extract_widget_config_parses_embedded_json():
    from apps.maic.generation.scene_generator import _extract_widget_config
    html = (
        '<script type="application/json" id="widget-config">'
        '{"engine":"p5","speed":1}</script>'
    )
    cfg = _extract_widget_config(html)
    assert cfg == {"engine": "p5", "speed": 1}


def test_extract_widget_config_returns_none_when_no_script_tag():
    from apps.maic.generation.scene_generator import _extract_widget_config
    assert _extract_widget_config("<html>no config</html>") is None


def test_extract_widget_config_returns_none_on_invalid_json():
    from apps.maic.generation.scene_generator import _extract_widget_config
    html = (
        '<script type="application/json" id="widget-config">'
        'not json{{{</script>'
    )
    assert _extract_widget_config(html) is None


# ── Interactive-actions branch (MAIC-422.6) ───────────────────────


@pytest.mark.asyncio
async def test_interactive_actions_falls_back_to_default_when_llm_returns_empty():
    outline = {
        "type": "interactive",
        "title": "T",
        "widgetType": "simulation",
        "widgetOutline": {"concept": "C"},
    }
    content = {
        "html": "<html>x</html>",
        "widgetType": "simulation",
        "widgetConfig": None,
        "teacherActions": None,
    }

    async def _fake(*args, **kwargs):
        return "no JSON here"

    with patch(
        "apps.maic.generation.scene_generator.generate_text", new=_fake
    ):
        actions = await generate_scene_actions(
            outline, content, language_model_id="stub"
        )
    assert len(actions) == 1
    assert actions[0]["type"] == "speech"
    assert actions[0]["title"] == "交互引导"


@pytest.mark.asyncio
async def test_interactive_actions_default_on_missing_template():
    outline = {
        "type": "interactive",
        "title": "T",
        "widgetType": "simulation",
        "widgetOutline": {"concept": "C"},
    }
    content = {
        "html": "<html>x</html>",
        "widgetType": "simulation",
        "widgetConfig": None,
        "teacherActions": None,
    }

    from apps.maic.exceptions import MaicConfigError

    def _raise(*args, **kwargs):
        raise MaicConfigError("template not found: interactive-actions")

    async def _fake_text(*args, **kwargs):
        raise AssertionError("LLM must not be called when template missing")

    with patch(
        "apps.maic.generation.scene_generator.load_generation_prompt",
        side_effect=_raise,
    ):
        with patch(
            "apps.maic.generation.scene_generator.generate_text",
            new=_fake_text,
        ):
            actions = await generate_scene_actions(
                outline, content, language_model_id="stub"
            )
    assert len(actions) == 1
    assert actions[0]["type"] == "speech"


@pytest.mark.asyncio
async def test_interactive_actions_default_when_llm_call_fails():
    outline = {
        "type": "interactive",
        "title": "T",
        "widgetType": "simulation",
        "widgetOutline": {"concept": "C"},
    }
    content = {
        "html": "<html>x</html>",
        "widgetType": "simulation",
        "widgetConfig": None,
        "teacherActions": None,
    }

    async def _fake(*args, **kwargs):
        raise RuntimeError("provider down")

    with patch(
        "apps.maic.generation.scene_generator.generate_text", new=_fake
    ):
        actions = await generate_scene_actions(
            outline, content, language_model_id="stub"
        )
    assert len(actions) == 1
    assert actions[0]["type"] == "speech"


@pytest.mark.asyncio
async def test_interactive_actions_pulls_concept_from_widget_outline():
    """Ultra Mode: conceptName comes from outline.widgetOutline.concept,
    not legacy outline.interactiveConfig."""
    captured_vars = {}

    def _capture(template_id, vars):
        captured_vars.update(vars)
        from apps.maic.prompts.loader import BuiltPrompt
        return BuiltPrompt(system="sys", user="user")

    async def _fake(*args, **kwargs):
        return json.dumps([])

    outline = {
        "type": "interactive",
        "title": "outline-title",
        "widgetType": "simulation",
        "widgetOutline": {
            "concept": "Wave Mechanics",
            "designIdea": "interactive sliders",
        },
    }
    content = {
        "html": "<html>x</html>",
        "widgetType": "simulation",
        "widgetConfig": None,
        "teacherActions": None,
    }

    with patch(
        "apps.maic.generation.scene_generator.load_generation_prompt",
        side_effect=_capture,
    ):
        with patch(
            "apps.maic.generation.scene_generator.generate_text", new=_fake
        ):
            await generate_scene_actions(
                outline, content, language_model_id="stub"
            )
    assert captured_vars["conceptName"] == "Wave Mechanics"
    assert captured_vars["designIdea"] == "interactive sliders"


@pytest.mark.asyncio
async def test_interactive_actions_falls_back_to_legacy_interactive_config():
    """Legacy: when widgetOutline lacks concept/designIdea, pull from
    interactiveConfig (back-compat)."""
    captured_vars = {}

    def _capture(template_id, vars):
        captured_vars.update(vars)
        from apps.maic.prompts.loader import BuiltPrompt
        return BuiltPrompt(system="sys", user="user")

    async def _fake(*args, **kwargs):
        return json.dumps([])

    outline = {
        "type": "interactive",
        "title": "outline-title",
        "interactiveConfig": {
            "conceptName": "Legacy Concept",
            "designIdea": "Legacy Idea",
        },
    }
    content = {
        "html": "<html>x</html>",
        "widgetType": "simulation",
        "widgetConfig": None,
        "teacherActions": None,
    }

    with patch(
        "apps.maic.generation.scene_generator.load_generation_prompt",
        side_effect=_capture,
    ):
        with patch(
            "apps.maic.generation.scene_generator.generate_text", new=_fake
        ):
            await generate_scene_actions(
                outline, content, language_model_id="stub"
            )
    assert captured_vars["conceptName"] == "Legacy Concept"
    assert captured_vars["designIdea"] == "Legacy Idea"


@pytest.mark.asyncio
async def test_interactive_actions_concept_falls_back_to_title_when_missing():
    """No widgetOutline + no interactiveConfig → conceptName = title."""
    captured_vars = {}

    def _capture(template_id, vars):
        captured_vars.update(vars)
        from apps.maic.prompts.loader import BuiltPrompt
        return BuiltPrompt(system="sys", user="user")

    async def _fake(*args, **kwargs):
        return json.dumps([])

    outline = {"type": "interactive", "title": "T-fallback"}
    content = {
        "html": "<html>x</html>",
        "widgetType": "simulation",
        "widgetConfig": None,
        "teacherActions": None,
    }

    with patch(
        "apps.maic.generation.scene_generator.load_generation_prompt",
        side_effect=_capture,
    ):
        with patch(
            "apps.maic.generation.scene_generator.generate_text", new=_fake
        ):
            await generate_scene_actions(
                outline, content, language_model_id="stub"
            )
    assert captured_vars["conceptName"] == "T-fallback"
    assert captured_vars["designIdea"] == ""


@pytest.mark.asyncio
async def test_interactive_actions_processes_discussion_invalid_agent():
    outline = {
        "type": "interactive",
        "title": "T",
        "widgetType": "simulation",
        "widgetOutline": {"concept": "C"},
    }
    content = {
        "html": "<html>x</html>",
        "widgetType": "simulation",
        "widgetConfig": None,
        "teacherActions": None,
    }
    agents = [
        {"id": "default-1", "name": "Teacher", "role": "teacher"},
        {"id": "default-3", "name": "Student", "role": "student"},
    ]

    async def _fake(*args, **kwargs):
        return json.dumps([
            {
                "type": "action",
                "name": "discussion",
                "params": {"agentId": "ghost", "topic": "T"},
            },
        ])

    with patch(
        "apps.maic.generation.scene_generator.generate_text", new=_fake
    ):
        actions = await generate_scene_actions(
            outline,
            content,
            language_model_id="stub",
            options={"agents": agents},
        )
    assert actions[0]["agentId"] == "default-3"


# ── Widget teacher actions / Ultra Mode (MAIC-422.7) ──────────────


@pytest.mark.asyncio
async def test_widget_content_attaches_teacher_actions_when_returned():
    """The widget content branch makes a 2nd LLM call to widget-
    teacher-actions; when the LLM returns `{"actions": [...]}` those
    flow through to content["teacherActions"]."""
    call_count = {"n": 0}

    async def _fake(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return "<!DOCTYPE html><html><body>x</body></html>"
        return json.dumps({
            "actions": [
                {"type": "speech", "label": "Intro", "content": "Welcome."},
                {
                    "type": "highlight",
                    "label": "Spot",
                    "target": "#amplitude-slider",
                    "content": "Watch this.",
                },
            ]
        })

    outline = {
        "type": "interactive",
        "title": "T",
        "widgetType": "simulation",
        "widgetOutline": {"concept": "C"},
    }

    with patch(
        "apps.maic.generation.scene_generator.generate_text", new=_fake
    ):
        content = await generate_scene_content(outline, language_model_id="stub")
    assert content is not None
    assert content["teacherActions"] is not None
    assert len(content["teacherActions"]) == 2
    assert content["teacherActions"][0]["type"] == "speech"
    assert content["teacherActions"][1]["type"] == "highlight"


@pytest.mark.asyncio
async def test_widget_content_teacher_actions_none_on_unparseable_response():
    """If the 2nd LLM call returns garbage, teacherActions defaults
    to None (caller falls through to standard interactive-actions
    LLM call)."""
    call_count = {"n": 0}

    async def _fake(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return "<!DOCTYPE html><html>x</html>"
        return "no JSON anywhere"

    outline = {
        "type": "interactive",
        "title": "T",
        "widgetType": "simulation",
        "widgetOutline": {"concept": "C"},
    }

    with patch(
        "apps.maic.generation.scene_generator.generate_text", new=_fake
    ):
        content = await generate_scene_content(outline, language_model_id="stub")
    assert content is not None
    assert content["teacherActions"] is None


@pytest.mark.asyncio
async def test_widget_content_teacher_actions_none_when_template_missing():
    """If the widget-teacher-actions template is absent, the function
    returns None and the widget content still ships."""
    captures: list[str] = []

    def _capture(template_id, vars):
        captures.append(template_id)
        if template_id == "widget-teacher-actions":
            from apps.maic.exceptions import MaicConfigError
            raise MaicConfigError("template not found")
        from apps.maic.prompts.loader import BuiltPrompt
        return BuiltPrompt(system="sys", user="user")

    async def _fake(*args, **kwargs):
        return "<!DOCTYPE html><html>x</html>"

    outline = {
        "type": "interactive",
        "title": "T",
        "widgetType": "simulation",
        "widgetOutline": {"concept": "C"},
    }

    with patch(
        "apps.maic.generation.scene_generator.load_generation_prompt",
        side_effect=_capture,
    ):
        with patch(
            "apps.maic.generation.scene_generator.generate_text", new=_fake
        ):
            content = await generate_scene_content(outline, language_model_id="stub")
    assert content is not None
    assert content["teacherActions"] is None
    assert "simulation-content" in captures
    assert "widget-teacher-actions" in captures


@pytest.mark.asyncio
async def test_actions_dispatcher_ultra_mode_early_exit():
    """When content carries teacherActions, the actions dispatcher
    converts directly without an LLM call (skips the standard
    interactive-actions branch)."""
    outline = {
        "type": "interactive",
        "title": "T",
        "widgetType": "simulation",
        "widgetOutline": {"concept": "C"},
    }
    content = {
        "html": "<html>x</html>",
        "widgetType": "simulation",
        "widgetConfig": None,
        "teacherActions": [
            {"type": "speech", "label": "Intro", "content": "Welcome."},
        ],
    }

    async def _fake(*args, **kwargs):
        raise AssertionError(
            "LLM must not be called when Ultra Mode actions present"
        )

    with patch(
        "apps.maic.generation.scene_generator.generate_text", new=_fake
    ):
        actions = await generate_scene_actions(
            outline, content, language_model_id="stub"
        )
    assert len(actions) == 1
    assert actions[0]["type"] == "speech"
    assert actions[0]["text"] == "Welcome."


# ── _convert_teacher_actions_to_actions ───────────────────────────


def test_convert_speech_teacher_action_to_speech_action():
    from apps.maic.generation.scene_generator import (
        _convert_teacher_actions_to_actions,
    )
    out = _convert_teacher_actions_to_actions([
        {"type": "speech", "label": "Hello", "content": "Hi there."},
    ])
    assert len(out) == 1
    assert out[0]["type"] == "speech"
    assert out[0]["text"] == "Hi there."
    assert out[0]["title"] == "Hello"
    assert out[0]["id"].startswith("action_")


def test_convert_highlight_teacher_action_emits_widget_and_speech():
    from apps.maic.generation.scene_generator import (
        _convert_teacher_actions_to_actions,
    )
    out = _convert_teacher_actions_to_actions([
        {
            "type": "highlight",
            "label": "Spot",
            "target": "#x",
            "content": "Notice this.",
        },
    ])
    assert len(out) == 2
    assert out[0]["type"] == "widget_highlight"
    assert out[0]["target"] == "#x"
    assert out[1]["type"] == "speech"
    assert out[1]["text"] == "Notice this."
    assert out[1]["id"] == f"{out[0]['id']}_speech"


def test_convert_highlight_without_content_emits_only_widget_action():
    from apps.maic.generation.scene_generator import (
        _convert_teacher_actions_to_actions,
    )
    out = _convert_teacher_actions_to_actions([
        {"type": "highlight", "label": "Spot", "target": "#x"},
    ])
    assert len(out) == 1
    assert out[0]["type"] == "widget_highlight"


def test_convert_setState_teacher_action():
    from apps.maic.generation.scene_generator import (
        _convert_teacher_actions_to_actions,
    )
    out = _convert_teacher_actions_to_actions([
        {
            "type": "setState",
            "label": "Set",
            "state": {"speed": 2},
            "content": "Speed up.",
        },
    ])
    assert len(out) == 2
    assert out[0]["type"] == "widget_setState"
    assert out[0]["state"] == {"speed": 2}
    assert out[1]["type"] == "speech"


def test_convert_annotation_and_reveal_teacher_actions():
    from apps.maic.generation.scene_generator import (
        _convert_teacher_actions_to_actions,
    )
    out = _convert_teacher_actions_to_actions([
        {"type": "annotation", "label": "A", "target": "#a"},
        {"type": "reveal", "label": "R", "target": "#b"},
    ])
    types = [a["type"] for a in out]
    assert "widget_annotation" in types
    assert "widget_reveal" in types


def test_convert_unknown_teacher_action_falls_back_to_speech():
    from apps.maic.generation.scene_generator import (
        _convert_teacher_actions_to_actions,
    )
    out = _convert_teacher_actions_to_actions([
        {"type": "future-mystery-type", "label": "?", "content": "hi"},
    ])
    assert len(out) == 1
    assert out[0]["type"] == "speech"
    assert out[0]["text"] == "hi"


def test_convert_teacher_action_ids_are_unique():
    from apps.maic.generation.scene_generator import (
        _convert_teacher_actions_to_actions,
    )
    out = _convert_teacher_actions_to_actions([
        {"type": "speech", "content": "A"},
        {"type": "speech", "content": "B"},
        {"type": "speech", "content": "C"},
    ])
    ids = [a["id"] for a in out]
    assert len(set(ids)) == 3


# ── generate_full_scenes orchestrator (MAIC-422.8) ────────────────


from apps.maic.generation.scene_generator import generate_full_scenes


@pytest.mark.asyncio
async def test_full_scenes_runs_all_outlines_in_parallel():
    """All outlines flow through generate_scene_content → actions →
    build_complete_scene; output preserves outline order."""
    outlines = [
        {"type": "slide", "title": "S1", "description": "d1", "keyPoints": []},
        {"type": "slide", "title": "S2", "description": "d2", "keyPoints": []},
        {"type": "slide", "title": "S3", "description": "d3", "keyPoints": []},
    ]

    async def _fake(*args, **kwargs):
        # Distinguish content vs actions calls: only the actions
        # prompts ask for "JSON array directly" with N segments.
        msgs = (
            kwargs.get("messages")
            or (args[0] if args else None)
        ) or []
        prompt_text = " ".join(getattr(m, "content", "") for m in msgs)
        if "JSON array directly" in prompt_text:
            return json.dumps([
                {"type": "text", "content": "narration"},
            ])
        return json.dumps({
            "elements": [{"type": "text", "id": "el1", "content": "x"}],
        })

    with patch(
        "apps.maic.generation.scene_generator.generate_text", new=_fake
    ):
        scenes = await generate_full_scenes(outlines, language_model_id="stub")
    assert len(scenes) == 3
    titles = [s.get("title") for s in scenes]
    assert titles == ["S1", "S2", "S3"]


@pytest.mark.asyncio
async def test_full_scenes_drops_failed_scene_content():
    """A scene whose content generation returns None is dropped (not
    a hard failure for the whole pipeline)."""
    outlines = [
        {"type": "slide", "title": "OK", "description": "d", "keyPoints": []},
        {"type": "slide", "title": "BAD", "description": "d", "keyPoints": []},
    ]

    async def _fake(*args, **kwargs):
        msgs = (
            kwargs.get("messages")
            or (args[0] if args else None)
        ) or []
        prompt_text = " ".join(getattr(m, "content", "") for m in msgs)
        if "BAD" in prompt_text:
            return "no JSON anywhere"
        if "JSON array directly" in prompt_text:
            return json.dumps([
                {"type": "text", "content": "narration"},
            ])
        return json.dumps({
            "elements": [{"type": "text", "id": "el1", "content": "x"}],
        })

    with patch(
        "apps.maic.generation.scene_generator.generate_text", new=_fake
    ):
        scenes = await generate_full_scenes(outlines, language_model_id="stub")
    assert len(scenes) == 1
    assert scenes[0]["title"] == "OK"


@pytest.mark.asyncio
async def test_full_scenes_emits_progress_callbacks():
    """onProgress fires before generation starts and after each
    completion (best-effort under parallel execution)."""
    outlines = [
        {"type": "slide", "title": "S1", "description": "d", "keyPoints": []},
        {"type": "slide", "title": "S2", "description": "d", "keyPoints": []},
    ]
    progress_events: list[dict] = []

    def _on_progress(p):
        progress_events.append(dict(p))

    async def _fake(*args, **kwargs):
        return json.dumps({
            "elements": [{"type": "text", "id": "el1", "content": "x"}],
        })

    with patch(
        "apps.maic.generation.scene_generator.generate_text", new=_fake
    ):
        scenes = await generate_full_scenes(
            outlines,
            language_model_id="stub",
            callbacks={"onProgress": _on_progress},
        )
    assert len(scenes) == 2
    # First event = "starting" (completed=0), final event = full
    # completion (completed=2).
    assert progress_events[0]["completed"] == 0
    assert progress_events[-1]["completed"] == 2
    assert progress_events[-1]["total"] == 2


@pytest.mark.asyncio
async def test_full_scenes_emits_onerror_for_failed_scene():
    """Failed scenes go through callbacks.onError."""
    outlines = [
        {"type": "slide", "title": "OK", "description": "d", "keyPoints": []},
        {"type": "slide", "title": "FAIL", "description": "d", "keyPoints": []},
    ]
    errors: list[str] = []

    def _on_error(msg):
        errors.append(msg)

    async def _fake(*args, **kwargs):
        msgs = (
            kwargs.get("messages")
            or (args[0] if args else None)
        ) or []
        prompt_text = " ".join(getattr(m, "content", "") for m in msgs)
        if "FAIL" in prompt_text:
            return "garbage"
        if "JSON array directly" in prompt_text:
            return json.dumps([{"type": "text", "content": "n"}])
        return json.dumps({
            "elements": [{"type": "text", "id": "el1", "content": "x"}],
        })

    with patch(
        "apps.maic.generation.scene_generator.generate_text", new=_fake
    ):
        await generate_full_scenes(
            outlines,
            language_model_id="stub",
            callbacks={"onError": _on_error},
        )
    # _generate_single_scene returns None on content failure, but
    # that's a soft drop (not an exception). onError fires only on
    # exceptions in this orchestrator. So errors stays empty here —
    # the FAIL scene is silently dropped, content failure is logged.
    # (This locks the contract: content-None != exception.)
    assert errors == []


@pytest.mark.asyncio
async def test_full_scenes_empty_outlines_returns_empty_list():
    scenes = await generate_full_scenes([], language_model_id="stub")
    assert scenes == []


@pytest.mark.asyncio
async def test_full_scenes_passes_ctx_with_correct_pageIndex():
    """Each scene's actions get a `ctx` reflecting its position in
    the outline list (1-based pageIndex, total = len(outlines)).
    The course context renderer emits "FIRST page" for index 1,
    "LAST page" for index N, and "Page X of N" for middle pages."""
    captured_courseContexts: list[str] = []

    outlines = [
        {"type": "slide", "title": f"S{i}", "description": "d", "keyPoints": []}
        for i in range(3)
    ]

    async def _fake(*args, **kwargs):
        return json.dumps({
            "elements": [{"type": "text", "id": "el1", "content": "x"}],
        })

    def _capture(template_id, vars):
        if template_id == "slide-actions":
            captured_courseContexts.append(vars.get("courseContext", ""))
        from apps.maic.prompts.loader import BuiltPrompt
        return BuiltPrompt(system="sys", user="user")

    with patch(
        "apps.maic.generation.scene_generator.load_generation_prompt",
        side_effect=_capture,
    ):
        with patch(
            "apps.maic.generation.scene_generator.generate_text", new=_fake
        ):
            await generate_full_scenes(outlines, language_model_id="stub")
    # Three distinct courseContext strings (one per scene), each
    # tagged with its position in the outline.
    assert len(captured_courseContexts) == 3
    contexts_text = " ".join(captured_courseContexts)
    assert "FIRST page" in contexts_text
    assert "LAST page" in contexts_text
    assert "Page 2 of 3" in contexts_text
