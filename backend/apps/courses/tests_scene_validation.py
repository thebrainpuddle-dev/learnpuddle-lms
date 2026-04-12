# apps/courses/tests_scene_validation.py
"""
Comprehensive tests for the scene normalization and validation pipeline.

Covers every public function in ``apps.courses.scene_validation`` including
edge cases around LLM output variability, XSS prevention, and the full
normalize_scenes pipeline.
"""

from __future__ import annotations

import uuid

import pytest

from apps.courses.scene_validation import (
    FIELD_MAX_LENGTHS,
    LIST_FIELD_LIMITS,
    MAX_SCENES,
    SLIDE_TYPE_ALIASES,
    VALID_SLIDE_TYPES,
    coerce_field_types,
    normalize_quiz_options,
    normalize_scenes,
    normalize_slide_type,
    sanitize_scene_fields,
    validate_required_fields,
)


# ============================================================================
# normalize_slide_type
# ============================================================================


class TestNormalizeSlideType:
    """Tests for ``normalize_slide_type``."""

    # --- Direct canonical types ---

    @pytest.mark.parametrize("raw", list(VALID_SLIDE_TYPES))
    def test_canonical_types_pass_through(self, raw: str):
        assert normalize_slide_type(raw) == raw

    # --- Case insensitivity ---

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("Content", "content"),
            ("QUIZ", "quiz"),
            ("Reflection", "reflection"),
            ("ACTIVITY", "activity"),
            ("Definition", "definition"),
            ("SUMMARY", "summary"),
            ("Case_Study", "case_study"),
        ],
    )
    def test_case_insensitive(self, raw: str, expected: str):
        assert normalize_slide_type(raw) == expected

    # --- Whitespace stripping ---

    def test_strips_leading_trailing_whitespace(self):
        assert normalize_slide_type("  content  ") == "content"
        assert normalize_slide_type("\tquiz\n") == "quiz"

    # --- Aliases ---

    @pytest.mark.parametrize(
        "alias, expected",
        [
            ("info", "content"),
            ("information", "content"),
            ("text", "content"),
            ("narrative", "content"),
            ("lecture", "content"),
            ("slide", "content"),
            ("intro", "title"),
            ("introduction", "title"),
            ("question", "quiz"),
            ("mcq", "quiz"),
            ("multiple_choice", "quiz"),
            ("multiple choice", "quiz"),
            ("multiplechoice", "quiz"),
            ("true_false", "quiz"),
            ("true/false", "quiz"),
            ("reflect", "reflection"),
            ("think", "reflection"),
            ("prompt", "reflection"),
            ("exercise", "activity"),
            ("task", "activity"),
            ("practice", "activity"),
            ("hands_on", "activity"),
            ("hands-on", "activity"),
            ("define", "definition"),
            ("term", "definition"),
            ("vocabulary", "definition"),
            ("vocab", "definition"),
            ("glossary", "definition"),
            ("recap", "summary"),
            ("review", "summary"),
            ("wrap_up", "summary"),
            ("wrap-up", "summary"),
            ("wrapup", "summary"),
            ("conclusion", "summary"),
            ("case", "case_study"),
            ("casestudy", "case_study"),
            ("case-study", "case_study"),
            ("scenario", "case_study"),
        ],
    )
    def test_all_aliases_resolve(self, alias: str, expected: str):
        assert normalize_slide_type(alias) == expected

    # --- Aliases are case-insensitive too ---

    def test_alias_case_insensitive(self):
        assert normalize_slide_type("MCQ") == "quiz"
        assert normalize_slide_type("Narrative") == "content"
        assert normalize_slide_type("RECAP") == "summary"

    # --- Unknown types ---

    @pytest.mark.parametrize("raw", ["unknown", "video", "animation", "123", ""])
    def test_unknown_returns_none(self, raw: str):
        assert normalize_slide_type(raw) is None

    # --- Non-string input ---

    def test_non_string_returns_none(self):
        assert normalize_slide_type(123) is None
        assert normalize_slide_type(None) is None
        assert normalize_slide_type([]) is None


# ============================================================================
# coerce_field_types
# ============================================================================


class TestCoerceFieldTypes:
    """Tests for ``coerce_field_types``."""

    def test_string_to_list_for_key_points(self):
        scene = {"key_points": "point one, point two, point three"}
        result = coerce_field_types(scene)
        assert result["key_points"] == ["point one", "point two", "point three"]

    def test_string_to_list_for_bullets(self):
        scene = {"bullets": "first,second,third"}
        result = coerce_field_types(scene)
        assert result["bullets"] == ["first", "second", "third"]

    def test_string_to_list_for_options(self):
        scene = {"options": "A, B, C"}
        result = coerce_field_types(scene)
        assert result["options"] == ["A", "B", "C"]

    def test_string_to_list_for_steps(self):
        scene = {"steps": "step1, step2"}
        result = coerce_field_types(scene)
        assert result["steps"] == ["step1", "step2"]

    def test_string_to_list_strips_whitespace(self):
        scene = {"key_points": "  a ,  b , c  "}
        result = coerce_field_types(scene)
        assert result["key_points"] == ["a", "b", "c"]

    def test_string_to_list_drops_empty_parts(self):
        scene = {"key_points": "a,,b, ,c"}
        result = coerce_field_types(scene)
        assert result["key_points"] == ["a", "b", "c"]

    def test_already_list_left_unchanged(self):
        scene = {"key_points": ["a", "b"]}
        result = coerce_field_types(scene)
        assert result["key_points"] == ["a", "b"]

    def test_reflection_min_length_string_to_int(self):
        scene = {"reflection_min_length": "50"}
        result = coerce_field_types(scene)
        assert result["reflection_min_length"] == 50

    def test_reflection_min_length_invalid_string_removed(self):
        scene = {"reflection_min_length": "not_a_number"}
        result = coerce_field_types(scene)
        assert "reflection_min_length" not in result

    def test_reflection_min_length_already_int(self):
        scene = {"reflection_min_length": 100}
        result = coerce_field_types(scene)
        assert result["reflection_min_length"] == 100

    def test_does_not_mutate_original(self):
        original = {"key_points": "a, b"}
        coerce_field_types(original)
        assert original["key_points"] == "a, b"

    def test_non_list_fields_unchanged(self):
        scene = {"title": "Hello", "body": "Some text"}
        result = coerce_field_types(scene)
        assert result["title"] == "Hello"
        assert result["body"] == "Some text"


# ============================================================================
# sanitize_scene_fields
# ============================================================================


class TestSanitizeSceneFields:
    """Tests for ``sanitize_scene_fields``."""

    def test_xss_script_tag_stripped(self):
        scene = {"title": '<script>alert("XSS")</script>Hello'}
        result = sanitize_scene_fields(scene)
        assert "<script>" not in result["title"]
        assert "</script>" not in result["title"]
        assert "Hello" in result["title"]

    def test_xss_onerror_stripped(self):
        scene = {"body": '<img src=x onerror="alert(1)">'}
        result = sanitize_scene_fields(scene)
        assert "onerror" not in result["body"]

    def test_xss_iframe_stripped(self):
        scene = {"narrative": '<iframe src="evil.com"></iframe>Safe text'}
        result = sanitize_scene_fields(scene)
        assert "<iframe" not in result["narrative"]
        assert "Safe text" in result["narrative"]

    def test_title_truncated(self):
        long_title = "A" * 500
        scene = {"title": long_title}
        result = sanitize_scene_fields(scene)
        assert len(result["title"]) == FIELD_MAX_LENGTHS["title"]

    def test_body_truncated(self):
        long_body = "B" * 10000
        scene = {"body": long_body}
        result = sanitize_scene_fields(scene)
        assert len(result["body"]) == FIELD_MAX_LENGTHS["body"]

    def test_question_truncated(self):
        long_q = "Q" * 2000
        scene = {"question": long_q}
        result = sanitize_scene_fields(scene)
        assert len(result["question"]) == FIELD_MAX_LENGTHS["question"]

    def test_field_not_in_max_lengths_not_truncated(self):
        scene = {"custom_field": "X" * 10000}
        result = sanitize_scene_fields(scene)
        assert len(result["custom_field"]) == 10000

    def test_list_field_capped(self):
        scene = {"key_points": [f"point_{i}" for i in range(20)]}
        result = sanitize_scene_fields(scene)
        assert len(result["key_points"]) == LIST_FIELD_LIMITS["key_points"]

    def test_list_items_sanitized(self):
        scene = {"bullets": ['<script>evil</script>Good point', "Normal text"]}
        result = sanitize_scene_fields(scene)
        assert "<script>" not in result["bullets"][0]
        assert "Good point" in result["bullets"][0]
        assert result["bullets"][1] == "Normal text"

    def test_list_with_non_string_items_preserved(self):
        scene = {"options": [{"id": "1", "text": "A"}]}
        result = sanitize_scene_fields(scene)
        assert result["options"][0] == {"id": "1", "text": "A"}

    def test_does_not_mutate_original(self):
        original = {"title": '<script>x</script>Hello'}
        sanitize_scene_fields(original)
        assert "<script>" in original["title"]


# ============================================================================
# normalize_quiz_options
# ============================================================================


class TestNormalizeQuizOptions:
    """Tests for ``normalize_quiz_options``."""

    def test_basic_string_options_converted(self):
        scene = {
            "type": "quiz",
            "options": ["Alpha", "Beta", "Gamma"],
            "correct_answer": "Beta",
        }
        result = normalize_quiz_options(scene)
        assert len(result["options"]) == 3
        for opt in result["options"]:
            assert "id" in opt
            assert "text" in opt
            assert "is_correct" in opt
        texts = {o["text"]: o["is_correct"] for o in result["options"]}
        assert texts["Beta"] is True
        assert texts["Alpha"] is False
        assert texts["Gamma"] is False

    def test_correct_answer_removed(self):
        scene = {
            "type": "quiz",
            "options": ["A", "B"],
            "correct_answer": "A",
        }
        result = normalize_quiz_options(scene)
        assert "correct_answer" not in result

    def test_case_insensitive_match(self):
        scene = {
            "type": "quiz",
            "options": ["alpha", "BETA", "Gamma"],
            "correct_answer": "beta",
        }
        result = normalize_quiz_options(scene)
        correct = [o for o in result["options"] if o["is_correct"]]
        assert len(correct) == 1
        assert correct[0]["text"] == "BETA"

    def test_whitespace_trimmed_match(self):
        scene = {
            "type": "quiz",
            "options": ["  Alpha  ", "Beta"],
            "correct_answer": "Alpha",
        }
        result = normalize_quiz_options(scene)
        correct = [o for o in result["options"] if o["is_correct"]]
        assert len(correct) == 1
        assert correct[0]["text"] == "  Alpha  "

    def test_no_match_marks_first_correct(self):
        scene = {
            "type": "quiz",
            "options": ["A", "B", "C"],
            "correct_answer": "Z",
        }
        result = normalize_quiz_options(scene)
        assert result["options"][0]["is_correct"] is True
        assert result["options"][1]["is_correct"] is False
        assert result["options"][2]["is_correct"] is False

    def test_no_correct_answer_field_marks_first(self):
        scene = {
            "type": "quiz",
            "options": ["A", "B"],
        }
        result = normalize_quiz_options(scene)
        assert result["options"][0]["is_correct"] is True
        assert result["options"][1]["is_correct"] is False

    def test_already_normalized_passthrough(self):
        scene = {
            "type": "quiz",
            "options": [
                {"id": "existing-1", "text": "A", "is_correct": True},
                {"id": "existing-2", "text": "B", "is_correct": False},
            ],
        }
        result = normalize_quiz_options(scene)
        assert result["options"][0]["id"] == "existing-1"
        assert result["options"][0]["is_correct"] is True
        assert result["options"][1]["id"] == "existing-2"

    def test_already_normalized_missing_id_gets_uuid(self):
        scene = {
            "type": "quiz",
            "options": [
                {"text": "A", "is_correct": True},
                {"text": "B", "is_correct": False},
            ],
        }
        result = normalize_quiz_options(scene)
        for opt in result["options"]:
            assert "id" in opt
            # Verify it's a valid UUID
            uuid.UUID(opt["id"])

    def test_non_quiz_scene_unchanged(self):
        scene = {
            "type": "content",
            "options": ["should", "not", "change"],
        }
        result = normalize_quiz_options(scene)
        assert result["options"] == ["should", "not", "change"]

    def test_empty_options_unchanged(self):
        scene = {"type": "quiz", "options": []}
        result = normalize_quiz_options(scene)
        assert result["options"] == []

    def test_unique_ids_generated(self):
        scene = {
            "type": "quiz",
            "options": ["A", "B", "C", "D"],
            "correct_answer": "A",
        }
        result = normalize_quiz_options(scene)
        ids = [o["id"] for o in result["options"]]
        assert len(set(ids)) == 4  # All unique

    def test_non_string_option_coerced(self):
        scene = {
            "type": "quiz",
            "options": [1, 2, 3],
            "correct_answer": "2",
        }
        result = normalize_quiz_options(scene)
        correct = [o for o in result["options"] if o["is_correct"]]
        assert len(correct) == 1
        assert correct[0]["text"] == "2"


# ============================================================================
# validate_required_fields
# ============================================================================


class TestValidateRequiredFields:
    """Tests for ``validate_required_fields``."""

    def test_valid_content_with_body(self):
        scene = {"type": "content", "title": "Intro", "body": "Some text"}
        assert validate_required_fields(scene) == []

    def test_valid_content_with_bullets(self):
        scene = {"type": "content", "title": "Intro", "bullets": ["a", "b"]}
        assert validate_required_fields(scene) == []

    def test_content_missing_body_and_bullets(self):
        scene = {"type": "content", "title": "Intro"}
        missing = validate_required_fields(scene)
        assert "body" in missing

    def test_content_missing_title(self):
        scene = {"type": "content", "body": "text"}
        missing = validate_required_fields(scene)
        assert "title" in missing

    def test_content_empty_title(self):
        scene = {"type": "content", "title": "", "body": "text"}
        missing = validate_required_fields(scene)
        assert "title" in missing

    def test_content_whitespace_only_title(self):
        scene = {"type": "content", "title": "   ", "body": "text"}
        missing = validate_required_fields(scene)
        assert "title" in missing

    def test_valid_quiz(self):
        scene = {
            "type": "quiz",
            "title": "Q1",
            "question": "What?",
            "options": ["A", "B"],
        }
        assert validate_required_fields(scene) == []

    def test_quiz_missing_question(self):
        scene = {"type": "quiz", "title": "Q1", "options": ["A"]}
        missing = validate_required_fields(scene)
        assert "question" in missing

    def test_quiz_empty_options(self):
        scene = {"type": "quiz", "title": "Q1", "question": "What?", "options": []}
        missing = validate_required_fields(scene)
        assert "options" in missing

    def test_valid_reflection(self):
        scene = {"type": "reflection", "title": "Reflect", "prompt": "Think about..."}
        assert validate_required_fields(scene) == []

    def test_reflection_missing_prompt(self):
        scene = {"type": "reflection", "title": "Reflect"}
        missing = validate_required_fields(scene)
        assert "prompt" in missing

    def test_valid_activity(self):
        scene = {"type": "activity", "title": "Do it", "instructions": "Step 1"}
        assert validate_required_fields(scene) == []

    def test_activity_missing_instructions(self):
        scene = {"type": "activity", "title": "Do it"}
        missing = validate_required_fields(scene)
        assert "instructions" in missing

    def test_valid_definition(self):
        scene = {"type": "definition", "term": "LMS", "definition": "A system..."}
        assert validate_required_fields(scene) == []

    def test_definition_missing_term(self):
        scene = {"type": "definition", "definition": "A system..."}
        missing = validate_required_fields(scene)
        assert "term" in missing

    def test_valid_summary(self):
        scene = {"type": "summary", "title": "Wrap up"}
        assert validate_required_fields(scene) == []

    def test_valid_case_study(self):
        scene = {"type": "case_study", "title": "Case", "scenario": "A student..."}
        assert validate_required_fields(scene) == []

    def test_unknown_type_returns_type_error(self):
        scene = {"type": "unknown_thing", "title": "X"}
        missing = validate_required_fields(scene)
        assert "type" in missing

    def test_missing_type_field(self):
        scene = {"title": "No type"}
        missing = validate_required_fields(scene)
        assert "type" in missing

    def test_content_with_empty_body_and_no_bullets(self):
        scene = {"type": "content", "title": "Intro", "body": ""}
        missing = validate_required_fields(scene)
        assert "body" in missing

    def test_content_with_empty_bullets_and_no_body(self):
        scene = {"type": "content", "title": "Intro", "bullets": []}
        missing = validate_required_fields(scene)
        assert "body" in missing


# ============================================================================
# normalize_scenes (full pipeline)
# ============================================================================


class TestNormalizeScenes:
    """Integration tests for ``normalize_scenes``."""

    # --- UUID assignment ---

    def test_uuid_assigned_to_each_scene(self):
        raw = [
            {"type": "content", "title": "S1", "body": "Text"},
            {"type": "content", "title": "S2", "body": "Text"},
        ]
        result = normalize_scenes(raw)
        assert len(result) == 2
        for scene in result:
            uid = scene["id"]
            uuid.UUID(uid)  # Raises if invalid

    def test_uuids_are_unique(self):
        raw = [{"type": "content", "title": f"S{i}", "body": "T"} for i in range(5)]
        result = normalize_scenes(raw)
        ids = [s["id"] for s in result]
        assert len(set(ids)) == 5

    # --- Order from index ---

    def test_order_derived_from_index(self):
        raw = [
            {"type": "content", "title": "First", "body": "A"},
            {"type": "content", "title": "Second", "body": "B"},
            {"type": "content", "title": "Third", "body": "C"},
        ]
        result = normalize_scenes(raw)
        assert [s["order"] for s in result] == [0, 1, 2]

    def test_order_skips_dropped_scenes(self):
        """Order should reflect position in the *output* list, re-indexed from 0."""
        raw = [
            {"type": "content", "title": "Valid", "body": "A"},
            {"type": "unknown_type", "title": "Invalid"},  # dropped
            {"type": "content", "title": "Also valid", "body": "B"},
        ]
        result = normalize_scenes(raw)
        assert len(result) == 2
        # Order comes from the original index passed to _apply_backend_defaults
        assert result[0]["order"] == 0
        assert result[1]["order"] == 2

    # --- Image status logic ---

    def test_image_status_pending_with_keyword(self):
        raw = [{"type": "content", "title": "S", "body": "T", "image_keyword": "classroom"}]
        result = normalize_scenes(raw)
        assert result[0]["image_status"] == "pending"

    def test_image_status_none_without_keyword(self):
        raw = [{"type": "content", "title": "S", "body": "T"}]
        result = normalize_scenes(raw)
        assert result[0]["image_status"] == "none"

    def test_image_status_none_with_empty_keyword(self):
        raw = [{"type": "content", "title": "S", "body": "T", "image_keyword": ""}]
        result = normalize_scenes(raw)
        assert result[0]["image_status"] == "none"

    def test_image_status_none_with_whitespace_keyword(self):
        raw = [{"type": "content", "title": "S", "body": "T", "image_keyword": "   "}]
        result = normalize_scenes(raw)
        assert result[0]["image_status"] == "none"

    # --- image_url, audio_url, duration_seconds always None ---

    def test_media_fields_always_none(self):
        raw = [
            {
                "type": "content",
                "title": "S",
                "body": "T",
                "image_url": "http://evil.com/img.jpg",
                "audio_url": "http://evil.com/audio.mp3",
                "duration_seconds": 9999,
            }
        ]
        result = normalize_scenes(raw)
        assert result[0]["image_url"] is None
        assert result[0]["audio_url"] is None
        assert result[0]["duration_seconds"] is None

    # --- auto alt_text ---

    def test_alt_text_auto_generated(self):
        raw = [{"type": "content", "title": "S", "body": "T", "image_keyword": "bloom taxonomy"}]
        result = normalize_scenes(raw)
        assert result[0]["alt_text"] == "Illustration for: bloom taxonomy"

    def test_alt_text_not_overwritten_if_provided(self):
        raw = [
            {
                "type": "content",
                "title": "S",
                "body": "T",
                "image_keyword": "bloom",
                "alt_text": "Custom alt",
            }
        ]
        result = normalize_scenes(raw)
        assert result[0]["alt_text"] == "Custom alt"

    # --- Definition title auto-generation ---

    def test_definition_auto_title(self):
        raw = [{"type": "definition", "term": "LMS", "definition": "A system for managing learning"}]
        result = normalize_scenes(raw)
        assert result[0]["title"] == "Definition: LMS"

    def test_definition_existing_title_not_overwritten(self):
        raw = [
            {
                "type": "definition",
                "term": "LMS",
                "definition": "A system",
                "title": "Existing Title",
            }
        ]
        result = normalize_scenes(raw)
        assert result[0]["title"] == "Existing Title"

    # --- Activity defaults ---

    def test_activity_defaults_injected(self):
        raw = [{"type": "activity", "title": "Do it", "instructions": "Step 1"}]
        result = normalize_scenes(raw)
        assert result[0]["activity_type"] == "individual"
        assert result[0]["estimated_minutes"] == 5

    def test_activity_custom_values_preserved(self):
        raw = [
            {
                "type": "activity",
                "title": "Group work",
                "instructions": "Step 1",
                "activity_type": "group",
                "estimated_minutes": 15,
            }
        ]
        result = normalize_scenes(raw)
        assert result[0]["activity_type"] == "group"
        assert result[0]["estimated_minutes"] == 15

    # --- Invalid scenes dropped ---

    def test_invalid_scene_dropped_missing_required(self):
        raw = [
            {"type": "content", "title": "Valid", "body": "OK"},
            {"type": "quiz"},  # missing title, question, options
            {"type": "content", "title": "Also Valid", "body": "OK"},
        ]
        result = normalize_scenes(raw)
        assert len(result) == 2
        assert result[0]["title"] == "Valid"
        assert result[1]["title"] == "Also Valid"

    def test_unknown_type_dropped(self):
        raw = [
            {"type": "content", "title": "Good", "body": "OK"},
            {"type": "fancy_animation", "title": "Bad"},
        ]
        result = normalize_scenes(raw)
        assert len(result) == 1

    def test_non_dict_scenes_dropped(self):
        raw = [
            {"type": "content", "title": "Good", "body": "OK"},
            "not a dict",
            42,
            None,
            ["list"],
        ]
        result = normalize_scenes(raw)
        assert len(result) == 1

    # --- Max 20 cap ---

    def test_max_scenes_cap(self):
        raw = [{"type": "content", "title": f"S{i}", "body": "T"} for i in range(30)]
        result = normalize_scenes(raw)
        assert len(result) == MAX_SCENES

    # --- Empty / None input ---

    def test_none_input_returns_empty_list(self):
        assert normalize_scenes(None) == []

    def test_empty_list_returns_empty_list(self):
        assert normalize_scenes([]) == []

    def test_non_list_input_returns_empty_list(self):
        assert normalize_scenes("not a list") == []
        assert normalize_scenes(42) == []
        assert normalize_scenes({}) == []

    # --- Slide-type alias in pipeline ---

    def test_alias_resolved_in_pipeline(self):
        raw = [{"type": "MCQ", "title": "Q1", "question": "What?", "options": ["A", "B"]}]
        result = normalize_scenes(raw)
        assert len(result) == 1
        assert result[0]["type"] == "quiz"

    def test_slide_type_key_supported(self):
        """LLMs sometimes use ``slide_type`` instead of ``type``."""
        raw = [{"slide_type": "info", "title": "Hello", "body": "World"}]
        result = normalize_scenes(raw)
        assert len(result) == 1
        assert result[0]["type"] == "content"
        assert "slide_type" not in result[0]

    # --- Coercion in pipeline ---

    def test_string_list_coerced_in_pipeline(self):
        raw = [
            {
                "type": "content",
                "title": "S1",
                "body": "text",
                "key_points": "point one, point two",
            }
        ]
        result = normalize_scenes(raw)
        assert result[0]["key_points"] == ["point one", "point two"]

    # --- Sanitisation in pipeline ---

    def test_xss_sanitized_in_pipeline(self):
        raw = [
            {
                "type": "content",
                "title": '<script>alert("XSS")</script>Safe Title',
                "body": "Clean body",
            }
        ]
        result = normalize_scenes(raw)
        assert "<script>" not in result[0]["title"]
        assert "Safe Title" in result[0]["title"]

    # --- Quiz normalization in pipeline ---

    def test_quiz_options_normalized_in_pipeline(self):
        raw = [
            {
                "type": "quiz",
                "title": "Q1",
                "question": "Pick one?",
                "options": ["Red", "Blue", "Green"],
                "correct_answer": "Blue",
            }
        ]
        result = normalize_scenes(raw)
        assert len(result) == 1
        opts = result[0]["options"]
        assert all(isinstance(o, dict) for o in opts)
        correct = [o for o in opts if o["is_correct"]]
        assert len(correct) == 1
        assert correct[0]["text"] == "Blue"
        assert "correct_answer" not in result[0]

    # --- Full realistic scene set ---

    def test_realistic_mixed_scene_set(self):
        raw = [
            {
                "type": "intro",
                "title": "Welcome",
                "body": "Welcome to the lesson on Bloom's Taxonomy.",
                "image_keyword": "classroom learning",
            },
            {
                "type": "content",
                "title": "Key Concepts",
                "bullets": ["Remember", "Understand", "Apply"],
                "key_points": "knowledge, comprehension",
            },
            {
                "type": "MCQ",
                "title": "Quick Check",
                "question": "Which is the highest level?",
                "options": ["Remember", "Create", "Analyze"],
                "correct_answer": "Create",
            },
            {
                "type": "reflect",
                "title": "Your Experience",
                "prompt": "How do you use higher-order thinking in your classroom?",
            },
            {
                "type": "define",
                "term": "Bloom's Taxonomy",
                "definition": "A hierarchical classification of learning objectives.",
            },
            {
                "type": "exercise",
                "title": "Practice Activity",
                "instructions": "Design a lesson plan using all 6 levels.",
            },
            {
                "type": "conclusion",
                "title": "Summary",
                "body": "Today we covered all six levels of Bloom's Taxonomy.",
            },
        ]
        result = normalize_scenes(raw)
        assert len(result) == 7

        types = [s["type"] for s in result]
        assert types == [
            "title",
            "content",
            "quiz",
            "reflection",
            "definition",
            "activity",
            "summary",
        ]

        # Check intro became title with image_status pending
        assert result[0]["image_status"] == "pending"
        assert result[0]["alt_text"] == "Illustration for: classroom learning"

        # Check string key_points were coerced
        assert result[1]["key_points"] == ["knowledge", "comprehension"]

        # Check quiz normalized
        quiz = result[2]
        assert all(isinstance(o, dict) for o in quiz["options"])
        correct = [o for o in quiz["options"] if o["is_correct"]]
        assert correct[0]["text"] == "Create"

        # Check definition got auto title
        assert result[4]["title"] == "Definition: Bloom's Taxonomy"

        # Check activity got defaults
        assert result[5]["activity_type"] == "individual"
        assert result[5]["estimated_minutes"] == 5

        # Check all have id and order
        for i, scene in enumerate(result):
            uuid.UUID(scene["id"])  # Valid UUID
            assert scene["image_url"] is None
            assert scene["audio_url"] is None
            assert scene["duration_seconds"] is None


