"""Tests for `apps.maic.generation.prompt_formatters` (MAIC-427)."""
from __future__ import annotations

from apps.maic.generation.prompt_formatters import (
    build_course_context,
    build_language_text,
    build_vision_user_content,
    format_agents_for_prompt,
    format_image_description,
    format_image_placeholder,
    format_teacher_persona_for_prompt,
)


# ── build_course_context ─────────────────────────────────────────


class TestBuildCourseContext:
    def test_returns_empty_string_when_ctx_is_none(self):
        assert build_course_context(None) == ""

    def test_marks_current_page_with_arrow(self):
        ctx = {
            "pageIndex": 2,
            "totalPages": 3,
            "allTitles": ["Intro", "Body", "Outro"],
            "previousSpeeches": [],
        }
        out = build_course_context(ctx)
        # Current page = 2 → "Body" gets the marker
        assert "  2. Body ← current" in out
        assert "  1. Intro" in out
        assert "  3. Outro" in out
        assert "← current" not in out.split("Body")[0]  # not on Intro

    def test_first_page_says_first_page_open_with_greeting(self):
        ctx = {
            "pageIndex": 1,
            "totalPages": 3,
            "allTitles": ["A", "B", "C"],
            "previousSpeeches": [],
        }
        out = build_course_context(ctx)
        assert "FIRST page" in out
        assert "course introduction" in out

    def test_last_page_says_last_page_conclude(self):
        ctx = {
            "pageIndex": 3,
            "totalPages": 3,
            "allTitles": ["A", "B", "C"],
            "previousSpeeches": [],
        }
        out = build_course_context(ctx)
        assert "LAST page" in out
        assert "summary and closing" in out

    def test_middle_page_says_middle(self):
        ctx = {
            "pageIndex": 2,
            "totalPages": 5,
            "allTitles": ["A", "B", "C", "D", "E"],
            "previousSpeeches": [],
        }
        out = build_course_context(ctx)
        assert "Page 2 of 5" in out
        assert "middle of the course" in out

    def test_includes_no_previous_session_reminder(self):
        """Critical anti-hallucination: prevent the LLM from saying
        'last class' or 'previous session' when all pages are in the
        same session."""
        ctx = {
            "pageIndex": 2,
            "totalPages": 3,
            "allTitles": ["A", "B", "C"],
            "previousSpeeches": [],
        }
        out = build_course_context(ctx)
        assert "SAME class session" in out
        assert "Do NOT greet again" in out

    def test_previous_speech_truncated_to_last_150_chars(self):
        long_speech = "x" * 500
        ctx = {
            "pageIndex": 2,
            "totalPages": 3,
            "allTitles": ["A", "B", "C"],
            "previousSpeeches": [long_speech],
        }
        out = build_course_context(ctx)
        assert "Previous page speech" in out
        # Includes ellipsis + last 150 chars (full match impossible w/o
        # exact regex; check for the count instead)
        assert "...xxxxx" in out

    def test_no_previous_speech_block_when_empty(self):
        ctx = {
            "pageIndex": 2,
            "totalPages": 3,
            "allTitles": ["A", "B", "C"],
            "previousSpeeches": [],
        }
        out = build_course_context(ctx)
        assert "Previous page speech" not in out


# ── format_agents_for_prompt ─────────────────────────────────────


class TestFormatAgentsForPrompt:
    def test_empty_agents_returns_empty(self):
        assert format_agents_for_prompt(None) == ""
        assert format_agents_for_prompt([]) == ""

    def test_renders_each_agent_with_role(self):
        agents = [
            {"id": "default-1", "name": "Teacher", "role": "teacher"},
            {"id": "default-3", "name": "Student", "role": "student"},
        ]
        out = format_agents_for_prompt(agents)
        assert "Classroom Agents:" in out
        assert 'id: "default-1"' in out
        assert 'name: "Teacher"' in out
        assert "role: teacher" in out
        assert 'id: "default-3"' in out

    def test_persona_appended_with_em_dash(self):
        agents = [
            {
                "id": "x",
                "name": "X",
                "role": "teacher",
                "persona": "patient and warm",
            }
        ]
        out = format_agents_for_prompt(agents)
        assert "— patient and warm" in out

    def test_no_persona_means_no_dash(self):
        agents = [{"id": "x", "name": "X", "role": "teacher"}]
        out = format_agents_for_prompt(agents)
        # Each agent line ends right after the role with no trailing dash
        assert "—" not in out


# ── format_teacher_persona_for_prompt ────────────────────────────


class TestFormatTeacherPersonaForPrompt:
    def test_no_agents_returns_empty(self):
        assert format_teacher_persona_for_prompt(None) == ""
        assert format_teacher_persona_for_prompt([]) == ""

    def test_no_teacher_role_returns_empty(self):
        agents = [{"id": "s", "name": "Student", "role": "student"}]
        assert format_teacher_persona_for_prompt(agents) == ""

    def test_teacher_without_persona_returns_empty(self):
        agents = [{"id": "t", "name": "T", "role": "teacher"}]
        assert format_teacher_persona_for_prompt(agents) == ""

    def test_teacher_persona_includes_no_name_on_slides_guard(self):
        """The "no teacher name on slides" rule is critical — slides
        should read as neutral aids. Lock the guard text."""
        agents = [
            {
                "id": "t",
                "name": "Alice",
                "role": "teacher",
                "persona": "patient and warm",
            }
        ]
        out = format_teacher_persona_for_prompt(agents)
        assert "Name: Alice" in out
        assert "patient and warm" in out
        assert "name and identity must NOT appear on the slides" in out
        assert '"Teacher Alice\'s tips"' in out


# ── format_image_description / placeholder ───────────────────────


class TestFormatImageHelpers:
    def test_description_with_dimensions(self):
        img = {
            "id": "img_1",
            "pageNumber": 3,
            "width": 800,
            "height": 600,
            "description": "a cat",
        }
        out = format_image_description(img)
        assert "img_1" in out
        assert "page 3" in out
        assert "800×600" in out
        assert "1.33" in out  # aspect ratio
        assert "a cat" in out

    def test_description_without_dimensions(self):
        img = {"id": "img_1", "pageNumber": 1, "description": "test"}
        out = format_image_description(img)
        assert "img_1" in out
        assert "page 1" in out
        assert "test" in out
        assert "size:" not in out

    def test_placeholder_omits_description(self):
        """In vision mode the model sees the image directly; the
        placeholder skips the description."""
        img = {
            "id": "img_1",
            "pageNumber": 1,
            "description": "should be excluded",
            "width": 100,
            "height": 100,
        }
        out = format_image_placeholder(img)
        assert "img_1" in out
        assert "page 1" in out
        assert "[see attached]" in out
        assert "should be excluded" not in out


# ── build_vision_user_content (DEFERRED helpers) ─────────────────


class TestBuildVisionUserContent:
    def test_no_images_returns_just_text(self):
        out = build_vision_user_content("hello prompt")
        assert out == [{"type": "text", "text": "hello prompt"}]

    def test_single_image_via_data_uri_strips_prefix(self):
        out = build_vision_user_content(
            "prompt",
            [
                {
                    "id": "img_1",
                    "src": "data:image/png;base64,iVBORw0KGg",
                    "width": 100,
                    "height": 50,
                }
            ],
        )
        # parts: prompt, separator, label, image
        assert out[0]["text"] == "prompt"
        assert "Attached Images" in out[1]["text"]
        assert "img_1" in out[2]["text"]
        assert "100×50" in out[2]["text"]
        assert out[3] == {
            "type": "image",
            "image": "iVBORw0KGg",
            "mimeType": "image/png",
        }

    def test_https_url_passed_through(self):
        out = build_vision_user_content(
            "x", [{"id": "img_1", "src": "https://example.com/img.png"}]
        )
        # Last part is the image dict with the URL
        last = out[-1]
        assert last == {"type": "image", "image": "https://example.com/img.png"}


# ── build_language_text ──────────────────────────────────────────


class TestBuildLanguageText:
    def test_both_empty_returns_empty(self):
        assert build_language_text() == ""
        assert build_language_text(None, None) == ""
        assert build_language_text("", "") == ""

    def test_directive_only(self):
        out = build_language_text("Speak in English.")
        assert out == "Speak in English."

    def test_scene_note_only(self):
        out = build_language_text(scene_note="use casual tone")
        assert "Additional language note for this scene: use casual tone" in out

    def test_both_combined_with_double_newline(self):
        out = build_language_text("Speak in English.", "use casual tone")
        assert "Speak in English." in out
        assert "Additional language note for this scene: use casual tone" in out
        assert "\n\n" in out
