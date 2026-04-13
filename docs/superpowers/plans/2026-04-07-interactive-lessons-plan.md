# S1: Enhanced Interactive Lessons — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade interactive lessons from flat text scenes to 7 visually-typed slide layouts with curated icons, embedded quizzes, activity prompts, and parallel audio generation.

**Architecture:** Backend-first approach. Add model fields + scene validation module, update AI service prompt for v2 schema, modify API endpoints, then build frontend components (SceneRenderer with layout registry, split AIGenerationPanel, upgrade InteractiveLessonPlayer). No new tables — scenes stay in JSONField.

**Tech Stack:** Django 4.2 + DRF, PostgreSQL 15, Celery 5.3, Redis, React 18 + TypeScript + Vite, Zod 3.23, React Query 5, Heroicons 2

**Spec:** `docs/superpowers/specs/2026-04-07-interactive-lessons-design.md`

**No git operations in this session.**

---

## Chunk 1: Backend Data Layer

### Task 1: Add model fields via Django migration

**Files:**
- Modify: `backend/apps/courses/ai_studio_models.py`
- Create: `backend/apps/courses/migrations/0016_interactive_lesson_v2_fields.py`

- [ ] **Step 1: Add 5 new fields to InteractiveLesson model**

Open `backend/apps/courses/ai_studio_models.py`. After the existing `generation_model` field (around line 80), add:

```python
    scene_schema_version = models.PositiveSmallIntegerField(default=2)
    image_generation_status = models.CharField(
        max_length=20,
        choices=[
            ("none", "None"),
            ("pending", "Pending"),
            ("in_progress", "In Progress"),
            ("completed", "Completed"),
            ("partial_failure", "Partial Failure"),
        ],
        default="none",
    )
    lesson_format = models.CharField(
        max_length=10,
        choices=[("text", "Text"), ("visual", "Visual")],
        default="visual",
    )
    has_audio = models.BooleanField(default=False)
    generation_error = models.TextField(blank=True, default="")
```

- [ ] **Step 2: Add scene_id field to LessonReflectionResponse**

In the same file, find `LessonReflectionResponse` (around line 262). After `scene_index`, add:

```python
    scene_id = models.CharField(max_length=36, blank=True, null=True, db_index=True)
```

- [ ] **Step 3: Generate and review migration**

Run: `cd /Users/rakeshreddy/LMS/backend && python manage.py makemigrations courses --name interactive_lesson_v2_fields`

Expected: Creates `0016_interactive_lesson_v2_fields.py`

- [ ] **Step 4: Dry-run migration to verify**

Run: `python manage.py migrate courses --plan`

Expected: Shows `0016_interactive_lesson_v2_fields` as planned migration.

---

### Task 2: Create scene_validation.py — Constants and normalization primitives

**Files:**
- Create: `backend/apps/courses/scene_validation.py`
- Create: `backend/apps/courses/tests_scene_validation.py`

- [ ] **Step 1: Write tests for slide_type normalization**

Create `backend/apps/courses/tests_scene_validation.py`:

```python
import pytest
from apps.courses.scene_validation import normalize_slide_type, VALID_SLIDE_TYPES


class TestNormalizeSlideType:
    def test_valid_types_pass_through(self):
        for t in VALID_SLIDE_TYPES:
            assert normalize_slide_type(t) == t

    def test_case_insensitive(self):
        assert normalize_slide_type("Title") == "title"
        assert normalize_slide_type("QUIZ") == "quiz"

    def test_aliases(self):
        assert normalize_slide_type("intro") == "title"
        assert normalize_slide_type("introduction") == "title"
        assert normalize_slide_type("mcq") == "quiz"
        assert normalize_slide_type("multiple_choice") == "quiz"
        assert normalize_slide_type("recap") == "summary"
        assert normalize_slide_type("conclusion") == "summary"
        assert normalize_slide_type("define") == "definition"
        assert normalize_slide_type("compare") == "comparison"
        assert normalize_slide_type("exercise") == "activity"

    def test_unknown_returns_none(self):
        assert normalize_slide_type("unknown_xyz") is None
        assert normalize_slide_type("") is None

    def test_whitespace_stripped(self):
        assert normalize_slide_type("  title  ") == "title"
```

- [ ] **Step 2: Run test to verify failure**

Run: `cd /Users/rakeshreddy/LMS/backend && python -m pytest apps/courses/tests_scene_validation.py::TestNormalizeSlideType -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'apps.courses.scene_validation'`

- [ ] **Step 3: Implement normalize_slide_type**

Create `backend/apps/courses/scene_validation.py`:

```python
"""
Scene validation and normalization for Interactive Lesson v2 schema.

Normalizes raw LLM output into canonical scene format:
- Resolves slide_type aliases
- Adds UUIDs, order, backend-only fields
- Sanitizes text fields
- Validates required fields per type
- Converts quiz options from string[] to [{id, text, is_correct}]
"""

import uuid
import re
from typing import Any

import bleach

VALID_SLIDE_TYPES = frozenset(
    ["title", "content", "definition", "comparison", "quiz", "activity", "summary"]
)

SLIDE_TYPE_ALIASES: dict[str, str] = {
    "intro": "title",
    "introduction": "title",
    "multiple_choice": "quiz",
    "mcq": "quiz",
    "question": "quiz",
    "recap": "summary",
    "conclusion": "summary",
    "review": "summary",
    "define": "definition",
    "vocab": "definition",
    "vocabulary": "definition",
    "compare": "comparison",
    "versus": "comparison",
    "vs": "comparison",
    "exercise": "activity",
    "task": "activity",
    "practice": "activity",
}

REQUIRED_FIELDS: dict[str, list[str]] = {
    "title": ["title"],
    "content": ["title"],
    "definition": ["term", "definition"],
    "comparison": ["title", "left_label", "left_points", "right_label", "right_points"],
    "quiz": ["title", "question", "options", "correct_answer"],
    "activity": ["title", "instructions", "activity_type"],
    "summary": ["title", "recap_points"],
}

# Max lengths for truncation (not rejection)
FIELD_MAX_LENGTHS: dict[str, int] = {
    "title": 200,
    "subtitle": 300,
    "body": 3000,
    "term": 200,
    "definition": 1000,
    "example": 500,
    "question": 500,
    "explanation": 1000,
    "instructions": 1000,
    "reflection_prompt": 500,
    "speaker_notes": 2000,
    "alt_text": 300,
    "left_label": 100,
    "right_label": 100,
    "next_steps": 500,
    "image_keyword": 50,
}

LIST_FIELD_LIMITS: dict[str, tuple[int, int]] = {
    # field_name: (max_items, max_chars_per_item)
    "bullets": (20, 300),
    "key_points": (20, 300),
    "left_points": (10, 300),
    "right_points": (10, 300),
    "recap_points": (10, 300),
    "options": (6, 200),
}

_SANITIZE_TAGS: list[str] = []  # Strip all HTML from scene text fields


def normalize_slide_type(raw: str) -> str | None:
    """Resolve a raw slide_type string to a canonical type, or None if unknown."""
    cleaned = raw.strip().lower() if isinstance(raw, str) else ""
    if not cleaned:
        return None
    if cleaned in VALID_SLIDE_TYPES:
        return cleaned
    return SLIDE_TYPE_ALIASES.get(cleaned)
```

- [ ] **Step 4: Run test to verify pass**

Run: `cd /Users/rakeshreddy/LMS/backend && python -m pytest apps/courses/tests_scene_validation.py::TestNormalizeSlideType -v`

Expected: All 5 tests PASS.

---

### Task 3: scene_validation.py — Field coercion and sanitization

**Files:**
- Modify: `backend/apps/courses/scene_validation.py`
- Modify: `backend/apps/courses/tests_scene_validation.py`

- [ ] **Step 1: Write tests for coerce_field_types and sanitize_scene_fields**

Append to `tests_scene_validation.py`:

```python
from apps.courses.scene_validation import coerce_field_types, sanitize_scene_fields


class TestCoerceFieldTypes:
    def test_string_to_array_for_key_points(self):
        scene = {"key_points": "single point"}
        result = coerce_field_types(scene)
        assert result["key_points"] == ["single point"]

    def test_array_stays_array(self):
        scene = {"key_points": ["a", "b"]}
        result = coerce_field_types(scene)
        assert result["key_points"] == ["a", "b"]

    def test_string_to_array_for_bullets(self):
        scene = {"bullets": "one bullet"}
        result = coerce_field_types(scene)
        assert result["bullets"] == ["one bullet"]

    def test_none_becomes_empty_list(self):
        scene = {"key_points": None}
        result = coerce_field_types(scene)
        assert result["key_points"] == []

    def test_reflection_min_length_coerced_to_int(self):
        scene = {"reflection_min_length": "50"}
        result = coerce_field_types(scene)
        assert result["reflection_min_length"] == 50

    def test_non_numeric_reflection_min_length_defaults(self):
        scene = {"reflection_min_length": "abc"}
        result = coerce_field_types(scene)
        assert result["reflection_min_length"] == 50


class TestSanitizeSceneFields:
    def test_strips_script_tags(self):
        scene = {"title": "Hello <script>alert(1)</script>World"}
        result = sanitize_scene_fields(scene)
        assert "<script>" not in result["title"]
        assert "Hello" in result["title"]

    def test_strips_html_from_speaker_notes(self):
        scene = {"speaker_notes": "<p>Notes <b>here</b></p>"}
        result = sanitize_scene_fields(scene)
        assert "<p>" not in result["speaker_notes"]
        assert "Notes here" in result["speaker_notes"]

    def test_truncates_long_title(self):
        scene = {"title": "A" * 500}
        result = sanitize_scene_fields(scene)
        assert len(result["title"]) <= 200

    def test_truncates_list_items(self):
        scene = {"key_points": ["A" * 500, "B"]}
        result = sanitize_scene_fields(scene)
        assert len(result["key_points"][0]) <= 300
        assert result["key_points"][1] == "B"

    def test_limits_list_length(self):
        scene = {"bullets": [f"item{i}" for i in range(30)]}
        result = sanitize_scene_fields(scene)
        assert len(result["bullets"]) <= 20

    def test_non_text_fields_untouched(self):
        scene = {"order": 3, "image_status": "pending"}
        result = sanitize_scene_fields(scene)
        assert result["order"] == 3
        assert result["image_status"] == "pending"
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest apps/courses/tests_scene_validation.py::TestCoerceFieldTypes -v`

Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement coerce_field_types and sanitize_scene_fields**

Append to `backend/apps/courses/scene_validation.py`:

```python
_LIST_FIELDS = frozenset(
    ["bullets", "key_points", "left_points", "right_points", "recap_points", "options"]
)


def coerce_field_types(scene: dict[str, Any]) -> dict[str, Any]:
    """Coerce field types to expected shapes. Mutates and returns scene."""
    for field in _LIST_FIELDS:
        val = scene.get(field)
        if val is None:
            scene[field] = []
        elif isinstance(val, str):
            scene[field] = [val] if val.strip() else []

    # reflection_min_length → int
    rml = scene.get("reflection_min_length")
    if rml is not None:
        try:
            scene["reflection_min_length"] = int(rml)
        except (ValueError, TypeError):
            scene["reflection_min_length"] = 50

    return scene


def sanitize_scene_fields(scene: dict[str, Any]) -> dict[str, Any]:
    """Sanitize and truncate text fields. Mutates and returns scene."""
    # Sanitize + truncate string fields
    for field, max_len in FIELD_MAX_LENGTHS.items():
        val = scene.get(field)
        if isinstance(val, str):
            cleaned = bleach.clean(val, tags=_SANITIZE_TAGS, strip=True).strip()
            scene[field] = cleaned[:max_len]

    # Sanitize + truncate list fields
    for field, (max_items, max_chars) in LIST_FIELD_LIMITS.items():
        val = scene.get(field)
        if isinstance(val, list):
            sanitized = []
            for item in val[:max_items]:
                if isinstance(item, str):
                    cleaned = bleach.clean(item, tags=_SANITIZE_TAGS, strip=True).strip()
                    sanitized.append(cleaned[:max_chars])
                else:
                    sanitized.append(item)
            scene[field] = sanitized

    return scene
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest apps/courses/tests_scene_validation.py -v`

Expected: All tests PASS.

---

### Task 4: scene_validation.py — Quiz normalization

**Files:**
- Modify: `backend/apps/courses/scene_validation.py`
- Modify: `backend/apps/courses/tests_scene_validation.py`

- [ ] **Step 1: Write tests for normalize_quiz_options**

Append to `tests_scene_validation.py`:

```python
from apps.courses.scene_validation import normalize_quiz_options


class TestNormalizeQuizOptions:
    def test_converts_string_array_to_objects(self):
        scene = {
            "slide_type": "quiz",
            "options": ["Alpha", "Beta", "Gamma"],
            "correct_answer": "Beta",
        }
        result = normalize_quiz_options(scene)
        opts = result["options"]
        assert len(opts) == 3
        assert all(isinstance(o, dict) for o in opts)
        assert all("id" in o and "text" in o and "is_correct" in o for o in opts)

    def test_correct_answer_matched_case_insensitive(self):
        scene = {
            "slide_type": "quiz",
            "options": ["Yes", "No"],
            "correct_answer": "yes",
        }
        result = normalize_quiz_options(scene)
        correct = [o for o in result["options"] if o["is_correct"]]
        assert len(correct) == 1
        assert correct[0]["text"] == "Yes"

    def test_correct_answer_matched_whitespace_trimmed(self):
        scene = {
            "slide_type": "quiz",
            "options": ["Apple", "Banana"],
            "correct_answer": "  Banana  ",
        }
        result = normalize_quiz_options(scene)
        correct = [o for o in result["options"] if o["is_correct"]]
        assert correct[0]["text"] == "Banana"

    def test_correct_answer_removed_from_output(self):
        scene = {
            "slide_type": "quiz",
            "options": ["A", "B"],
            "correct_answer": "A",
        }
        result = normalize_quiz_options(scene)
        assert "correct_answer" not in result

    def test_no_match_marks_first_option_correct(self):
        scene = {
            "slide_type": "quiz",
            "options": ["A", "B"],
            "correct_answer": "Z",
        }
        result = normalize_quiz_options(scene)
        correct = [o for o in result["options"] if o["is_correct"]]
        assert len(correct) == 1
        assert correct[0]["text"] == "A"

    def test_already_normalized_options_left_alone(self):
        scene = {
            "slide_type": "quiz",
            "options": [
                {"id": "x1", "text": "A", "is_correct": False},
                {"id": "x2", "text": "B", "is_correct": True},
            ],
        }
        result = normalize_quiz_options(scene)
        assert result["options"] == scene["options"]

    def test_non_quiz_scene_untouched(self):
        scene = {"slide_type": "content", "title": "Hello"}
        result = normalize_quiz_options(scene)
        assert result == scene

    def test_options_get_unique_ids(self):
        scene = {
            "slide_type": "quiz",
            "options": ["A", "B", "C"],
            "correct_answer": "B",
        }
        result = normalize_quiz_options(scene)
        ids = [o["id"] for o in result["options"]]
        assert len(set(ids)) == 3  # all unique
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest apps/courses/tests_scene_validation.py::TestNormalizeQuizOptions -v`

Expected: FAIL

- [ ] **Step 3: Implement normalize_quiz_options**

Append to `scene_validation.py`:

```python
def normalize_quiz_options(scene: dict[str, Any]) -> dict[str, Any]:
    """Convert quiz options from LLM format to canonical format. Mutates and returns scene."""
    if scene.get("slide_type") != "quiz":
        return scene

    options = scene.get("options", [])
    if not options:
        return scene

    # Already normalized (list of dicts with 'id', 'text', 'is_correct')
    if options and isinstance(options[0], dict) and "is_correct" in options[0]:
        scene.pop("correct_answer", None)
        return scene

    # LLM format: options is string[], correct_answer is string
    correct_answer = str(scene.pop("correct_answer", "")).strip().lower()

    normalized = []
    matched = False
    for text in options:
        text_str = str(text).strip()
        is_correct = not matched and text_str.lower().strip() == correct_answer
        if is_correct:
            matched = True
        normalized.append({
            "id": f"opt-{uuid.uuid4().hex[:12]}",
            "text": text_str,
            "is_correct": is_correct,
        })

    # Fallback: if no match, mark first option correct
    if not matched and normalized:
        normalized[0]["is_correct"] = True

    scene["options"] = normalized
    return scene
```

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest apps/courses/tests_scene_validation.py::TestNormalizeQuizOptions -v`

Expected: All 8 tests PASS.

---

### Task 5: scene_validation.py — Full normalize_scenes pipeline

**Files:**
- Modify: `backend/apps/courses/scene_validation.py`
- Modify: `backend/apps/courses/tests_scene_validation.py`

- [ ] **Step 1: Write tests for validate_required_fields and normalize_scenes**

Append to `tests_scene_validation.py`:

```python
from apps.courses.scene_validation import validate_required_fields, normalize_scenes


class TestValidateRequiredFields:
    def test_valid_title_scene(self):
        scene = {"slide_type": "title", "title": "Hello"}
        assert validate_required_fields(scene) == []

    def test_missing_title_on_content(self):
        scene = {"slide_type": "content", "body": "text"}
        errors = validate_required_fields(scene)
        assert "title" in errors

    def test_content_needs_body_or_bullets(self):
        scene = {"slide_type": "content", "title": "T"}
        errors = validate_required_fields(scene)
        assert any("body" in e or "bullets" in e for e in errors)

    def test_content_with_bullets_only_valid(self):
        scene = {"slide_type": "content", "title": "T", "bullets": ["a"]}
        assert validate_required_fields(scene) == []

    def test_quiz_missing_question(self):
        scene = {"slide_type": "quiz", "title": "T", "options": ["a"], "correct_answer": "a"}
        errors = validate_required_fields(scene)
        assert "question" in errors

    def test_definition_valid(self):
        scene = {"slide_type": "definition", "term": "X", "definition": "Y"}
        assert validate_required_fields(scene) == []


class TestNormalizeScenes:
    def test_adds_uuid_ids(self):
        raw = [{"slide_type": "title", "title": "Hello"}]
        result = normalize_scenes(raw)
        assert len(result) == 1
        assert "id" in result[0]
        # UUID format check
        assert len(result[0]["id"]) == 36

    def test_assigns_order_from_index(self):
        raw = [
            {"slide_type": "title", "title": "A", "order": 99},
            {"slide_type": "content", "title": "B", "body": "text"},
        ]
        result = normalize_scenes(raw)
        assert result[0]["order"] == 0
        assert result[1]["order"] == 1

    def test_resolves_slide_type_alias(self):
        raw = [{"slide_type": "intro", "title": "Hello"}]
        result = normalize_scenes(raw)
        assert result[0]["slide_type"] == "title"

    def test_drops_invalid_slide_type(self):
        raw = [
            {"slide_type": "title", "title": "Good"},
            {"slide_type": "unknown_garbage", "title": "Bad"},
        ]
        result = normalize_scenes(raw)
        assert len(result) == 1
        assert result[0]["title"] == "Good"

    def test_sets_image_status_skipped_when_no_keyword(self):
        raw = [{"slide_type": "title", "title": "Hi"}]
        result = normalize_scenes(raw)
        assert result[0]["image_status"] == "skipped"

    def test_sets_image_status_pending_when_keyword_present(self):
        raw = [{"slide_type": "title", "title": "Hi", "image_keyword": "classroom"}]
        result = normalize_scenes(raw)
        assert result[0]["image_status"] == "pending"

    def test_backend_fields_added(self):
        raw = [{"slide_type": "title", "title": "Hi"}]
        result = normalize_scenes(raw)
        scene = result[0]
        assert scene["image_url"] is None
        assert scene["audio_url"] is None
        assert scene["duration_seconds"] is None
        assert isinstance(scene["key_points"], list)

    def test_sanitizes_xss(self):
        raw = [{"slide_type": "title", "title": "<script>xss</script>Hello"}]
        result = normalize_scenes(raw)
        assert "<script>" not in result[0]["title"]

    def test_normalizes_quiz_options(self):
        raw = [{
            "slide_type": "quiz",
            "title": "Q",
            "question": "What?",
            "options": ["A", "B"],
            "correct_answer": "B",
        }]
        result = normalize_scenes(raw)
        opts = result[0]["options"]
        assert isinstance(opts[0], dict)
        assert "correct_answer" not in result[0]

    def test_definition_auto_generates_title(self):
        raw = [{"slide_type": "definition", "term": "Pedagogy", "definition": "The art of teaching"}]
        result = normalize_scenes(raw)
        assert "Pedagogy" in result[0]["title"]

    def test_empty_input_returns_empty(self):
        assert normalize_scenes([]) == []
        assert normalize_scenes(None) == []

    def test_max_20_scenes(self):
        raw = [{"slide_type": "title", "title": f"S{i}"} for i in range(25)]
        result = normalize_scenes(raw)
        assert len(result) == 20
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest apps/courses/tests_scene_validation.py::TestNormalizeScenes -v`

Expected: FAIL

- [ ] **Step 3: Implement validate_required_fields and normalize_scenes**

Append to `scene_validation.py`:

```python
_MAX_SCENES = 20


def validate_required_fields(scene: dict[str, Any]) -> list[str]:
    """Return list of missing required field names for the given slide_type."""
    slide_type = scene.get("slide_type", "")
    required = REQUIRED_FIELDS.get(slide_type, [])
    missing = []
    for field in required:
        val = scene.get(field)
        if val is None or (isinstance(val, (str, list)) and not val):
            missing.append(field)

    # Content: at least one of body or bullets
    if slide_type == "content" and not scene.get("body") and not scene.get("bullets"):
        missing.append("body or bullets")

    return missing


def _add_backend_defaults(scene: dict[str, Any], index: int) -> dict[str, Any]:
    """Add backend-managed fields with defaults."""
    scene["id"] = str(uuid.uuid4())
    scene["order"] = index
    scene.setdefault("image_url", None)
    scene.setdefault("audio_url", None)
    scene.setdefault("duration_seconds", None)
    scene.setdefault("key_points", [])
    scene.setdefault("speaker_notes", "")
    scene.setdefault("alt_text", "")

    # Image status invariant
    keyword = (scene.get("image_keyword") or "").strip()
    if not keyword:
        scene["image_keyword"] = ""
        scene["image_status"] = "skipped"
    else:
        scene["image_keyword"] = keyword
        scene.setdefault("image_status", "pending")

    # Auto-generate alt_text if missing
    if not scene["alt_text"] and keyword:
        scene["alt_text"] = f"Illustration for {scene.get('title', keyword)}"

    # Definition: auto-generate title from term
    if scene.get("slide_type") == "definition" and not scene.get("title"):
        term = scene.get("term", "")
        scene["title"] = f"What is '{term}'?" if term else "Definition"

    # Activity: ensure flat fields
    if scene.get("slide_type") == "activity":
        scene.setdefault("activity_type", "reflection")
        scene.setdefault("reflection_prompt", scene.get("instructions", ""))
        scene.setdefault("reflection_min_length", 50)

    return scene


def normalize_scenes(raw_scenes: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Full normalization pipeline: validate, coerce, sanitize, enrich.

    Drops invalid scenes rather than failing the whole generation.
    """
    if not raw_scenes:
        return []

    normalized = []
    for i, raw in enumerate(raw_scenes[:_MAX_SCENES]):
        if not isinstance(raw, dict):
            continue

        # 1. Resolve slide_type
        raw_type = raw.get("slide_type", "")
        slide_type = normalize_slide_type(str(raw_type))
        if slide_type is None:
            continue  # Drop scenes with unknown type
        raw["slide_type"] = slide_type

        # 2. Coerce field types (string→array, etc.)
        coerce_field_types(raw)

        # 3. Validate required fields — skip invalid scenes
        missing = validate_required_fields(raw)
        if missing:
            continue

        # 4. Normalize quiz options
        normalize_quiz_options(raw)

        # 5. Sanitize text + enforce lengths
        sanitize_scene_fields(raw)

        # 6. Add backend defaults (id, order, image_status, etc.)
        _add_backend_defaults(raw, len(normalized))

        normalized.append(raw)

    return normalized
```

- [ ] **Step 4: Run full test suite**

Run: `python -m pytest apps/courses/tests_scene_validation.py -v`

Expected: All tests PASS.

---

## Chunk 2: Backend API Layer

### Task 6: Update AI service prompt for v2 schema

**Files:**
- Modify: `backend/apps/courses/ai_service.py` (lines ~750-850)

- [ ] **Step 1: Replace the generate_interactive_lesson prompt**

In `ai_service.py`, find `generate_interactive_lesson` (around line 740). Replace the user prompt section (the f-string that builds the JSON template) with the v2 flat schema prompt. Key changes:

1. Change temperature from `0.7` to `0.4`
2. Wrap user inputs in `<user_input>` tags for prompt injection defense
3. Replace the scene JSON template with flat slide_type format
4. Add explicit instructions: "Do NOT include order or id fields"
5. Quiz: "Set correct_answer to the exact text of the correct option"
6. Activity: "Use flat fields reflection_prompt and reflection_min_length"
7. Clamp num_scenes: `num_scenes = max(3, min(12, num_scenes))`

Replace the prompt from approximately line 769 to line 797:

```python
        num_scenes = max(3, min(12, num_scenes))

        source_section = ""
        if source_content:
            source_section = f"""
## Source Material
<user_input>
{source_content[:8000]}
</user_input>
"""

        prompt = f"""Design an interactive lesson with exactly {num_scenes} scenes (slides).

## Lesson Parameters
- Topic: <user_input>{topic[:500]}</user_input>
- Description: <user_input>{description[:2000]}</user_input>
- Target Audience: <user_input>{target_audience[:200]}</user_input>
{source_section}

## Output Format
Return ONLY valid JSON. Do NOT include ```json markers, order, or id fields.

Each scene MUST have a "slide_type" field set to one of: title, content, definition, comparison, quiz, activity, summary.

### Scene structures by slide_type:

**title**: {{"slide_type": "title", "title": "...", "subtitle": "...", "image_keyword": "...", "speaker_notes": "...", "key_points": []}}

**content**: {{"slide_type": "content", "title": "...", "body": "paragraph text", "bullets": ["point 1", "point 2"], "image_keyword": "...", "speaker_notes": "...", "key_points": ["..."]}}

**definition**: {{"slide_type": "definition", "term": "...", "definition": "...", "example": "...", "image_keyword": "...", "speaker_notes": "...", "key_points": []}}

**comparison**: {{"slide_type": "comparison", "title": "...", "left_label": "...", "left_points": ["..."], "right_label": "...", "right_points": ["..."], "image_keyword": "...", "speaker_notes": "...", "key_points": []}}

**quiz**: {{"slide_type": "quiz", "title": "Check Your Understanding", "question": "...", "options": ["A", "B", "C", "D"], "correct_answer": "exact text of correct option", "explanation": "...", "image_keyword": "quiz", "speaker_notes": "", "key_points": []}}

**activity**: {{"slide_type": "activity", "title": "...", "instructions": "...", "activity_type": "reflection", "reflection_prompt": "...", "reflection_min_length": 50, "image_keyword": "...", "speaker_notes": "...", "key_points": []}}

**summary**: {{"slide_type": "summary", "title": "Key Takeaways", "recap_points": ["..."], "next_steps": "...", "image_keyword": "summary", "speaker_notes": "...", "key_points": []}}

## Structure Requirements
- First scene MUST be slide_type "title"
- Last scene MUST be slide_type "summary"
- Include at least 1 "quiz" scene
- Include at least 1 "activity" scene with activity_type "reflection"
- Use varied slide types for the middle scenes
- image_keyword: single word describing a visual for the slide
- speaker_notes: what a presenter would say (used for audio narration)
- For quiz: set correct_answer to the EXACT text of one option
"""
```

- [ ] **Step 2: Update the response parsing to use normalize_scenes**

After the JSON extraction (around line 811), replace the manual normalization with:

```python
        from apps.courses.scene_validation import normalize_scenes

        raw_scenes = lesson_data.get("scenes", [])
        normalized = normalize_scenes(raw_scenes)
        if not normalized:
            logger.warning("No valid scenes after normalization for topic: %s", topic[:100])
            return None

        lesson_data["scenes"] = normalized
```

Remove the old manual normalization loop (lines ~825-841).

- [ ] **Step 3: Change temperature to 0.4**

Find the `llm_generate` call (around line 799) and change `temperature=0.7` to `temperature=0.4`.

- [ ] **Step 4: Verify existing tests still pass**

Run: `python -m pytest apps/courses/ -v -k "test" --timeout=30`

Expected: Existing tests should pass (AI service tests likely use mocks).

---

### Task 7: Fix rate limit + add idempotency guard

**Files:**
- Modify: `backend/apps/courses/ai_studio_views.py`

- [ ] **Step 1: Fix _check_studio_rate_limit (lines 49-54)**

Replace:
```python
def _check_studio_rate_limit(tenant_id: str) -> bool:
    """Check AI Studio rate limit for tenant."""
    cache_key = f"ai_studio_rate:{tenant_id}"
    cache.add(cache_key, 0, timeout=AI_STUDIO_RATE_WINDOW)
    current_count = cache.incr(cache_key)
    return current_count <= AI_STUDIO_RATE_LIMIT
```

With:
```python
def _check_studio_rate_limit(tenant_id: str) -> bool:
    """Check AI Studio rate limit for tenant (atomic increment)."""
    cache_key = f"ai_studio_rate:{tenant_id}"
    try:
        current_count = cache.incr(cache_key)
    except ValueError:
        cache.set(cache_key, 1, timeout=AI_STUDIO_RATE_WINDOW)
        current_count = 1
    return current_count <= AI_STUDIO_RATE_LIMIT
```

- [ ] **Step 2: Add idempotency guard to async generate view**

In `ai_studio_generate_lesson_async` (around line 750), after the rate limit check and before dispatching the Celery task, add:

```python
        # Idempotency guard: prevent duplicate generations
        content_id = request.data.get("content_id")
        if content_id:
            from apps.courses.ai_studio_models import InteractiveLesson
            existing = InteractiveLesson.objects.filter(
                content_id=content_id,
                status__in=["GENERATING", "DRAFT"],
            ).first()
            if existing:
                return Response(
                    {"error": {"code": "GENERATION_IN_PROGRESS", "message": "A lesson is already being generated for this content."}},
                    status=409,
                )
```

- [ ] **Step 3: Add num_scenes clamping at view layer**

In both `ai_studio_generate_lesson` and `ai_studio_generate_lesson_async`, after parsing `num_scenes`, add:

```python
        num_scenes = max(3, min(12, num_scenes))
```

---

### Task 8: Enhanced status endpoint + new scene edit endpoints

**Files:**
- Modify: `backend/apps/courses/ai_studio_views.py`
- Modify: `backend/apps/courses/urls.py`

- [ ] **Step 1: Enhance the status endpoint response**

In `ai_studio_generation_status` (around line 932), update the lesson response block to include new fields:

```python
            # Inside the lesson branch of the status view
            scenes = lesson.scenes or []
            response_data = {
                "type": "lesson",
                "id": str(lesson.id),
                "title": lesson.title,
                "status": lesson.status,
                "phase": _get_generation_phase(lesson),
                "progress": _get_generation_progress(lesson),
                "phases_completed": _get_completed_phases(lesson),
                "phases_remaining": _get_remaining_phases(lesson),
                "scene_count": len(scenes),
                "has_audio": lesson.has_audio,
                "error": lesson.generation_error or None,
                "created_at": lesson.created_at.isoformat() if lesson.created_at else None,
                "updated_at": lesson.updated_at.isoformat() if lesson.updated_at else None,
            }
```

Add helper functions before the view:

```python
def _get_generation_phase(lesson) -> str | None:
    status_phase_map = {
        "GENERATING": "content_generation",
        "IMAGES": "image_generation",
        "NARRATING": "audio_generation",
    }
    return status_phase_map.get(lesson.status)


def _get_generation_progress(lesson) -> dict | None:
    if lesson.status not in ("GENERATING", "IMAGES", "NARRATING"):
        return None
    scenes = lesson.scenes or []
    total = len(scenes) or 1
    if lesson.status == "IMAGES":
        done = sum(1 for s in scenes if s.get("image_status") in ("ready", "failed", "skipped"))
    elif lesson.status == "NARRATING":
        done = sum(1 for s in scenes if s.get("audio_url"))
    else:
        done = total if scenes else 0
    return {"current_scene": done, "total_scenes": total, "percentage": int(done / total * 100)}


def _get_completed_phases(lesson) -> list[str]:
    phases = []
    if lesson.status in ("IMAGES", "NARRATING", "READY", "FAILED", "PARTIAL_FAILURE"):
        phases.append("content_generation")
    if lesson.status in ("NARRATING", "READY", "PARTIAL_FAILURE"):
        phases.append("image_generation")
    if lesson.status in ("READY", "PARTIAL_FAILURE"):
        phases.append("audio_generation")
    return phases


def _get_remaining_phases(lesson) -> list[str]:
    phases = []
    if lesson.status == "GENERATING":
        phases.extend(["image_generation", "audio_generation"])
    elif lesson.status == "IMAGES":
        phases.append("audio_generation")
    return phases
```

- [ ] **Step 2: Add scene edit endpoint**

Add a new view function:

```python
@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
@admin_only
@tenant_required
def ai_studio_edit_scene(request, lesson_id, scene_id):
    """Edit a single scene within an interactive lesson."""
    from apps.courses.ai_studio_models import InteractiveLesson
    from apps.courses.scene_validation import sanitize_scene_fields

    try:
        lesson = InteractiveLesson.objects.get(id=lesson_id, tenant=request.tenant)
    except InteractiveLesson.DoesNotExist:
        return Response({"detail": "Lesson not found."}, status=404)

    scenes = lesson.scenes or []
    scene_idx = None
    for i, s in enumerate(scenes):
        if s.get("id") == str(scene_id):
            scene_idx = i
            break

    if scene_idx is None:
        return Response({"detail": "Scene not found."}, status=404)

    # Only allow editing safe fields
    editable_fields = {"title", "subtitle", "body", "bullets", "key_points",
                       "speaker_notes", "term", "definition", "example",
                       "question", "explanation", "instructions",
                       "reflection_prompt", "left_label", "left_points",
                       "right_label", "right_points", "recap_points", "next_steps",
                       "image_keyword"}
    updates = {k: v for k, v in request.data.items() if k in editable_fields}

    if not updates:
        return Response({"detail": "No editable fields provided."}, status=400)

    scenes[scene_idx].update(updates)
    sanitize_scene_fields(scenes[scene_idx])

    lesson.scenes = scenes
    lesson.save(update_fields=["scenes", "updated_at"])

    log_audit(
        request=request,
        action="UPDATE",
        model_name="InteractiveLesson",
        object_id=str(lesson.id),
        changes={"scene_id": str(scene_id), "fields": list(updates.keys())},
    )

    return Response(scenes[scene_idx], status=200)
```

- [ ] **Step 3: Add URL patterns**

In `backend/apps/courses/urls.py`, add after the existing ai-studio paths:

```python
    path('ai-studio/lessons/<uuid:lesson_id>/scenes/<str:scene_id>/',
         ai_studio_views.ai_studio_edit_scene, name='ai-studio-edit-scene'),
```

- [ ] **Step 4: Add tenant isolation to audio task**

In `backend/apps/courses/ai_studio_tasks.py`, in `generate_lesson_audio` (around line 354), add tenant context setting after getting the lesson:

```python
        lesson = InteractiveLesson.objects.select_related("tenant").get(id=lesson_id)
        set_current_tenant(lesson.tenant)
        try:
            # ... existing audio generation logic ...
        finally:
            clear_current_tenant()
```

---

## Chunk 3: Frontend Foundation

### Task 9: Zod schemas and TypeScript types

**Files:**
- Create: `frontend/src/components/lessons/schemas.ts`
- Create: `frontend/src/components/lessons/types.ts`

- [ ] **Step 1: Create the lessons directory**

Run: `mkdir -p /Users/rakeshreddy/LMS/frontend/src/components/lessons/layouts`

- [ ] **Step 2: Create schemas.ts with Zod validation**

Create `frontend/src/components/lessons/schemas.ts`:

```typescript
import { z } from 'zod';

const ImageStatus = z.enum(['pending', 'generating', 'ready', 'failed', 'skipped']);

const BaseSceneSchema = z.object({
  id: z.string(),
  slide_type: z.string(),
  order: z.number(),
  title: z.string().default(''),
  image_keyword: z.string().default(''),
  image_url: z.string().nullable().default(null),
  image_status: ImageStatus.default('skipped'),
  alt_text: z.string().default(''),
  speaker_notes: z.string().default(''),
  key_points: z.array(z.string()).default([]),
  audio_url: z.string().nullable().default(null),
  duration_seconds: z.number().nullable().default(null),
});

export const TitleSceneSchema = BaseSceneSchema.extend({
  slide_type: z.literal('title'),
  subtitle: z.string().default(''),
});

export const ContentSceneSchema = BaseSceneSchema.extend({
  slide_type: z.literal('content'),
  body: z.string().default(''),
  bullets: z.array(z.string()).default([]),
});

export const DefinitionSceneSchema = BaseSceneSchema.extend({
  slide_type: z.literal('definition'),
  term: z.string(),
  definition: z.string(),
  example: z.string().default(''),
});

export const ComparisonSceneSchema = BaseSceneSchema.extend({
  slide_type: z.literal('comparison'),
  left_label: z.string(),
  left_points: z.array(z.string()),
  right_label: z.string(),
  right_points: z.array(z.string()),
});

const QuizOptionSchema = z.object({
  id: z.string(),
  text: z.string(),
  is_correct: z.boolean(),
});

export const QuizSceneSchema = BaseSceneSchema.extend({
  slide_type: z.literal('quiz'),
  question: z.string(),
  options: z.array(QuizOptionSchema),
  explanation: z.string().default(''),
});

export const ActivitySceneSchema = BaseSceneSchema.extend({
  slide_type: z.literal('activity'),
  instructions: z.string(),
  activity_type: z.string().default('reflection'),
  reflection_prompt: z.string().default(''),
  reflection_min_length: z.number().default(50),
});

export const SummarySceneSchema = BaseSceneSchema.extend({
  slide_type: z.literal('summary'),
  recap_points: z.array(z.string()),
  next_steps: z.string().default(''),
});

export const SceneSchema = z.discriminatedUnion('slide_type', [
  TitleSceneSchema,
  ContentSceneSchema,
  DefinitionSceneSchema,
  ComparisonSceneSchema,
  QuizSceneSchema,
  ActivitySceneSchema,
  SummarySceneSchema,
]);

export const LessonDocumentSchema = z.object({
  schema_version: z.number().default(1),
  scenes: z.array(SceneSchema),
});

export type TitleScene = z.infer<typeof TitleSceneSchema>;
export type ContentScene = z.infer<typeof ContentSceneSchema>;
export type DefinitionScene = z.infer<typeof DefinitionSceneSchema>;
export type ComparisonScene = z.infer<typeof ComparisonSceneSchema>;
export type QuizScene = z.infer<typeof QuizSceneSchema>;
export type ActivityScene = z.infer<typeof ActivitySceneSchema>;
export type SummaryScene = z.infer<typeof SummarySceneSchema>;
export type Scene = z.infer<typeof SceneSchema>;
export type QuizOption = z.infer<typeof QuizOptionSchema>;
export type ImageStatus = z.infer<typeof ImageStatus>;

/**
 * Parse scenes with graceful degradation: invalid scenes are filtered out.
 */
export function parseScenes(raw: unknown[]): Scene[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((s) => {
      const result = SceneSchema.safeParse(s);
      return result.success ? result.data : null;
    })
    .filter((s): s is Scene => s !== null);
}
```

- [ ] **Step 3: Create types.ts with additional types**

Create `frontend/src/components/lessons/types.ts`:

```typescript
import type { Scene, QuizOption } from './schemas';

export type SlideType = Scene['slide_type'];

export interface LayoutProps {
  scene: Scene;
  onAction?: (action: SceneAction) => void;
  isAdmin?: boolean;
}

export type SceneAction =
  | { type: 'SUBMIT_QUIZ'; sceneId: string; answerId: string }
  | { type: 'SUBMIT_REFLECTION'; sceneId: string; text: string }
  | { type: 'REGENERATE_SCENE'; sceneId: string }
  | { type: 'EDIT_SCENE'; sceneId: string; updates: Partial<Scene> };

export interface LessonConfig {
  num_scenes: number;
  include_quiz: boolean;
  include_activity: boolean;
  generate_narration: boolean;
}

export interface GenerationStatus {
  type: string;
  id: string;
  title: string;
  status: 'PENDING' | 'GENERATING' | 'IMAGES' | 'NARRATING' | 'READY' | 'FAILED' | 'PARTIAL_FAILURE';
  phase: string | null;
  progress: { current_scene: number; total_scenes: number; percentage: number } | null;
  phases_completed: string[];
  phases_remaining: string[];
  scene_count: number;
  has_audio: boolean;
  error: string | null;
  created_at: string;
  updated_at: string;
}
```

---

### Task 10: Icon map and useGenerationStatus hook

**Files:**
- Create: `frontend/src/components/lessons/iconMap.ts`
- Create: `frontend/src/components/lessons/useGenerationStatus.ts`

- [ ] **Step 1: Create iconMap.ts**

Create `frontend/src/components/lessons/iconMap.ts`:

```typescript
import {
  AcademicCapIcon,
  BeakerIcon,
  BookOpenIcon,
  BriefcaseIcon,
  CalculatorIcon,
  ChatBubbleLeftRightIcon,
  CheckCircleIcon,
  ClipboardDocumentCheckIcon,
  ClockIcon,
  CloudIcon,
  CodeBracketIcon,
  CogIcon,
  ComputerDesktopIcon,
  DocumentTextIcon,
  GlobeAltIcon,
  HandRaisedIcon,
  LightBulbIcon,
  PencilSquareIcon,
  PresentationChartBarIcon,
  PuzzlePieceIcon,
  ScaleIcon,
  SparklesIcon,
  StarIcon,
  TrophyIcon,
  UserGroupIcon,
} from '@heroicons/react/24/outline';

type HeroIcon = React.ForwardRefExoticComponent<React.SVGProps<SVGSVGElement>>;

const ICON_MAP: Record<string, HeroIcon> = {
  classroom: AcademicCapIcon,
  education: AcademicCapIcon,
  teaching: AcademicCapIcon,
  pedagogy: AcademicCapIcon,
  science: BeakerIcon,
  experiment: BeakerIcon,
  research: BeakerIcon,
  book: BookOpenIcon,
  reading: BookOpenIcon,
  literacy: BookOpenIcon,
  library: BookOpenIcon,
  leadership: BriefcaseIcon,
  management: BriefcaseIcon,
  strategy: BriefcaseIcon,
  math: CalculatorIcon,
  calculation: CalculatorIcon,
  statistics: CalculatorIcon,
  discussion: ChatBubbleLeftRightIcon,
  communication: ChatBubbleLeftRightIcon,
  debate: ChatBubbleLeftRightIcon,
  quiz: ClipboardDocumentCheckIcon,
  assessment: ClipboardDocumentCheckIcon,
  checklist: CheckCircleIcon,
  goal: CheckCircleIcon,
  time: ClockIcon,
  schedule: ClockIcon,
  technology: ComputerDesktopIcon,
  computer: ComputerDesktopIcon,
  digital: ComputerDesktopIcon,
  coding: CodeBracketIcon,
  programming: CodeBracketIcon,
  cloud: CloudIcon,
  settings: CogIcon,
  document: DocumentTextIcon,
  writing: DocumentTextIcon,
  summary: DocumentTextIcon,
  global: GlobeAltIcon,
  world: GlobeAltIcon,
  activity: HandRaisedIcon,
  practice: HandRaisedIcon,
  idea: LightBulbIcon,
  creativity: LightBulbIcon,
  innovation: LightBulbIcon,
  edit: PencilSquareIcon,
  note: PencilSquareIcon,
  journal: PencilSquareIcon,
  presentation: PresentationChartBarIcon,
  data: PresentationChartBarIcon,
  analytics: PresentationChartBarIcon,
  puzzle: PuzzlePieceIcon,
  problem: PuzzlePieceIcon,
  comparison: ScaleIcon,
  balance: ScaleIcon,
  ai: SparklesIcon,
  highlight: StarIcon,
  achievement: TrophyIcon,
  trophy: TrophyIcon,
  teamwork: UserGroupIcon,
  collaboration: UserGroupIcon,
  group: UserGroupIcon,
};

export function getSceneIcon(keyword: string): HeroIcon {
  if (!keyword) return LightBulbIcon;
  return ICON_MAP[keyword.toLowerCase().trim()] || LightBulbIcon;
}

export { LightBulbIcon as DefaultIcon };
```

- [ ] **Step 2: Create useGenerationStatus hook**

Create `frontend/src/components/lessons/useGenerationStatus.ts`:

```typescript
import { useQuery } from '@tanstack/react-query';
import { aiService } from '@/services/aiService';
import type { GenerationStatus } from './types';

export function useGenerationStatus(lessonId: string | null) {
  return useQuery<GenerationStatus>({
    queryKey: ['generationStatus', lessonId],
    queryFn: async () => {
      const response = await aiService.studio.getStatus(lessonId!);
      return response.data;
    },
    enabled: Boolean(lessonId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (!status) return 3000;
      if (status === 'READY' || status === 'FAILED' || status === 'PARTIAL_FAILURE') return false;
      return 3000;
    },
    refetchIntervalInBackground: false,
  });
}
```

---

### Task 11: SceneRenderer + FallbackLayout

**Files:**
- Create: `frontend/src/components/lessons/SceneRenderer.tsx`
- Create: `frontend/src/components/lessons/layouts/FallbackLayout.tsx`

- [ ] **Step 1: Create FallbackLayout**

Create `frontend/src/components/lessons/layouts/FallbackLayout.tsx`:

```tsx
import React from 'react';
import type { LayoutProps } from '../types';

export const FallbackLayout: React.FC<LayoutProps> = ({ scene }) => (
  <div className="p-6 text-center">
    <h2 className="text-xl font-semibold mb-2">{scene.title || 'Untitled Scene'}</h2>
    <p className="text-sm text-gray-500">
      Unknown slide type: <code className="bg-gray-100 px-1 rounded">{scene.slide_type}</code>
    </p>
    {scene.key_points.length > 0 && (
      <ul className="mt-4 text-left list-disc list-inside text-gray-600">
        {scene.key_points.map((point, i) => (
          <li key={i}>{point}</li>
        ))}
      </ul>
    )}
  </div>
);
```

- [ ] **Step 2: Create SceneRenderer**

Create `frontend/src/components/lessons/SceneRenderer.tsx`:

```tsx
import React from 'react';
import type { Scene } from './schemas';
import type { LayoutProps, SceneAction } from './types';
import { FallbackLayout } from './layouts/FallbackLayout';

// Lazy-registered layouts — populated by Task 12
const LAYOUT_REGISTRY: Record<string, React.FC<LayoutProps>> = {};

export function registerLayout(slideType: string, component: React.FC<LayoutProps>) {
  LAYOUT_REGISTRY[slideType] = component;
}

interface SceneRendererProps {
  scene: Scene;
  onAction?: (action: SceneAction) => void;
  isAdmin?: boolean;
}

class SceneErrorBoundary extends React.Component<
  { fallback: React.ReactNode; children: React.ReactNode },
  { hasError: boolean }
> {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  render() {
    if (this.state.hasError) return this.fallback;
    return this.props.children;
  }

  get fallback() {
    return this.props.fallback;
  }
}

export const SceneRenderer: React.FC<SceneRendererProps> = ({ scene, onAction, isAdmin }) => {
  const Layout = LAYOUT_REGISTRY[scene.slide_type] || FallbackLayout;

  return (
    <SceneErrorBoundary
      fallback={<FallbackLayout scene={scene} onAction={onAction} isAdmin={isAdmin} />}
    >
      <Layout scene={scene} onAction={onAction} isAdmin={isAdmin} />
    </SceneErrorBoundary>
  );
};
```

---

### Task 12: Layout components (7 types)

**Files:**
- Create: `frontend/src/components/lessons/layouts/TitleLayout.tsx`
- Create: `frontend/src/components/lessons/layouts/ContentLayout.tsx`
- Create: `frontend/src/components/lessons/layouts/DefinitionLayout.tsx`
- Create: `frontend/src/components/lessons/layouts/ComparisonLayout.tsx`
- Create: `frontend/src/components/lessons/layouts/QuizLayout.tsx`
- Create: `frontend/src/components/lessons/layouts/ActivityLayout.tsx`
- Create: `frontend/src/components/lessons/layouts/SummaryLayout.tsx`
- Create: `frontend/src/components/lessons/layouts/index.ts`

- [ ] **Step 1: Create TitleLayout**

```tsx
// frontend/src/components/lessons/layouts/TitleLayout.tsx
import React from 'react';
import type { LayoutProps } from '../types';
import type { TitleScene } from '../schemas';
import { getSceneIcon } from '../iconMap';

export const TitleLayout: React.FC<LayoutProps> = ({ scene }) => {
  const s = scene as TitleScene;
  const Icon = getSceneIcon(s.image_keyword);

  return (
    <div className="flex flex-col items-center justify-center text-center p-8 min-h-[300px]">
      {s.image_url ? (
        <img src={s.image_url} alt={s.alt_text} className="w-24 h-24 mb-6 rounded-lg object-cover" />
      ) : (
        <Icon className="w-16 h-16 text-indigo-500 mb-6" />
      )}
      <h1 className="text-3xl sm:text-4xl font-bold text-gray-900 mb-3">{s.title}</h1>
      {s.subtitle && <p className="text-lg text-gray-500 max-w-xl">{s.subtitle}</p>}
    </div>
  );
};
```

- [ ] **Step 2: Create ContentLayout**

```tsx
// frontend/src/components/lessons/layouts/ContentLayout.tsx
import React from 'react';
import type { LayoutProps } from '../types';
import type { ContentScene } from '../schemas';
import { getSceneIcon } from '../iconMap';

export const ContentLayout: React.FC<LayoutProps> = ({ scene }) => {
  const s = scene as ContentScene;
  const Icon = getSceneIcon(s.image_keyword);

  return (
    <div className="p-6 sm:p-8">
      <h2 className="text-2xl font-bold text-gray-900 mb-4">{s.title}</h2>
      <div className="flex flex-col sm:flex-row gap-6">
        <div className="flex-1">
          {s.body && <p className="text-gray-700 leading-relaxed mb-4">{s.body}</p>}
          {s.bullets.length > 0 && (
            <ul className="space-y-2">
              {s.bullets.map((item, i) => (
                <li key={i} className="flex items-start gap-2">
                  <span className="mt-1.5 w-1.5 h-1.5 bg-indigo-500 rounded-full shrink-0" />
                  <span className="text-gray-700">{item}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="sm:w-1/3 flex items-start justify-center">
          {s.image_url ? (
            <img src={s.image_url} alt={s.alt_text} className="rounded-lg max-w-full" />
          ) : (
            <Icon className="w-20 h-20 text-indigo-300" />
          )}
        </div>
      </div>
    </div>
  );
};
```

- [ ] **Step 3: Create DefinitionLayout**

```tsx
// frontend/src/components/lessons/layouts/DefinitionLayout.tsx
import React from 'react';
import type { LayoutProps } from '../types';
import type { DefinitionScene } from '../schemas';
import { BookOpenIcon } from '@heroicons/react/24/outline';

export const DefinitionLayout: React.FC<LayoutProps> = ({ scene }) => {
  const s = scene as DefinitionScene;

  return (
    <div className="p-6 sm:p-8">
      <h2 className="text-2xl font-bold text-gray-900 mb-4">{s.title}</h2>
      <div className="bg-indigo-50 border-l-4 border-indigo-500 rounded-r-lg p-6">
        <div className="flex items-start gap-3">
          <BookOpenIcon className="w-6 h-6 text-indigo-600 mt-0.5 shrink-0" />
          <div>
            <p className="font-semibold text-indigo-900 text-lg">{s.term}</p>
            <p className="text-gray-700 mt-2">{s.definition}</p>
          </div>
        </div>
      </div>
      {s.example && (
        <div className="mt-4 bg-gray-50 rounded-lg p-4">
          <p className="text-sm font-medium text-gray-500 mb-1">Example</p>
          <p className="text-gray-700 italic">{s.example}</p>
        </div>
      )}
    </div>
  );
};
```

- [ ] **Step 4: Create ComparisonLayout**

```tsx
// frontend/src/components/lessons/layouts/ComparisonLayout.tsx
import React from 'react';
import type { LayoutProps } from '../types';
import type { ComparisonScene } from '../schemas';

export const ComparisonLayout: React.FC<LayoutProps> = ({ scene }) => {
  const s = scene as ComparisonScene;

  return (
    <div className="p-6 sm:p-8">
      <h2 className="text-2xl font-bold text-gray-900 mb-6">{s.title}</h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="bg-blue-50 rounded-lg p-5">
          <h3 className="font-semibold text-blue-900 mb-3 text-center">{s.left_label}</h3>
          <ul className="space-y-2">
            {s.left_points.map((p, i) => (
              <li key={i} className="flex items-start gap-2 text-blue-800">
                <span className="mt-1.5 w-1.5 h-1.5 bg-blue-500 rounded-full shrink-0" />
                {p}
              </li>
            ))}
          </ul>
        </div>
        <div className="bg-emerald-50 rounded-lg p-5">
          <h3 className="font-semibold text-emerald-900 mb-3 text-center">{s.right_label}</h3>
          <ul className="space-y-2">
            {s.right_points.map((p, i) => (
              <li key={i} className="flex items-start gap-2 text-emerald-800">
                <span className="mt-1.5 w-1.5 h-1.5 bg-emerald-500 rounded-full shrink-0" />
                {p}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
};
```

- [ ] **Step 5: Create QuizLayout**

```tsx
// frontend/src/components/lessons/layouts/QuizLayout.tsx
import React, { useState } from 'react';
import type { LayoutProps } from '../types';
import type { QuizScene, QuizOption } from '../schemas';
import { CheckCircleIcon, XCircleIcon } from '@heroicons/react/24/solid';

export const QuizLayout: React.FC<LayoutProps> = ({ scene, onAction }) => {
  const s = scene as QuizScene;
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);

  const handleSubmit = () => {
    if (!selectedId) return;
    setSubmitted(true);
    onAction?.({ type: 'SUBMIT_QUIZ', sceneId: s.id, answerId: selectedId });
  };

  const getOptionStyle = (opt: QuizOption) => {
    if (!submitted) {
      return selectedId === opt.id
        ? 'border-indigo-500 bg-indigo-50 ring-2 ring-indigo-500'
        : 'border-gray-200 hover:border-gray-300';
    }
    if (opt.is_correct) return 'border-green-500 bg-green-50';
    if (selectedId === opt.id && !opt.is_correct) return 'border-red-500 bg-red-50';
    return 'border-gray-200 opacity-50';
  };

  return (
    <div className="p-6 sm:p-8">
      <h2 className="text-2xl font-bold text-gray-900 mb-2">{s.title}</h2>
      <p className="text-gray-700 text-lg mb-6">{s.question}</p>

      <div className="space-y-3" role="radiogroup" aria-label="Quiz options">
        {s.options.map((opt) => (
          <button
            key={opt.id}
            onClick={() => !submitted && setSelectedId(opt.id)}
            disabled={submitted}
            className={`w-full text-left p-4 rounded-lg border-2 transition-colors flex items-center gap-3 ${getOptionStyle(opt)}`}
            role="radio"
            aria-checked={selectedId === opt.id}
          >
            <span className="flex-1">{opt.text}</span>
            {submitted && opt.is_correct && <CheckCircleIcon className="w-5 h-5 text-green-600" />}
            {submitted && selectedId === opt.id && !opt.is_correct && <XCircleIcon className="w-5 h-5 text-red-600" />}
          </button>
        ))}
      </div>

      {!submitted && (
        <button
          onClick={handleSubmit}
          disabled={!selectedId}
          className="mt-4 px-6 py-2 bg-indigo-600 text-white rounded-lg disabled:opacity-50 hover:bg-indigo-700 transition-colors"
        >
          Submit Answer
        </button>
      )}

      {submitted && s.explanation && (
        <div className="mt-4 bg-blue-50 border-l-4 border-blue-500 p-4 rounded-r-lg">
          <p className="text-blue-800">{s.explanation}</p>
        </div>
      )}
    </div>
  );
};
```

- [ ] **Step 6: Create ActivityLayout**

```tsx
// frontend/src/components/lessons/layouts/ActivityLayout.tsx
import React, { useState } from 'react';
import type { LayoutProps } from '../types';
import type { ActivityScene } from '../schemas';
import { PencilSquareIcon } from '@heroicons/react/24/outline';

export const ActivityLayout: React.FC<LayoutProps> = ({ scene, onAction }) => {
  const s = scene as ActivityScene;
  const [text, setText] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const minLen = s.reflection_min_length || 50;

  const handleSubmit = () => {
    if (text.length < minLen) return;
    setSubmitted(true);
    onAction?.({ type: 'SUBMIT_REFLECTION', sceneId: s.id, text });
  };

  return (
    <div className="p-6 sm:p-8">
      <h2 className="text-2xl font-bold text-gray-900 mb-2">{s.title}</h2>
      <p className="text-gray-700 mb-4">{s.instructions}</p>

      <div className="bg-amber-50 border-l-4 border-amber-500 rounded-r-lg p-5 mb-4">
        <div className="flex items-start gap-3">
          <PencilSquareIcon className="w-5 h-5 text-amber-600 mt-0.5 shrink-0" />
          <p className="text-amber-900 font-medium">{s.reflection_prompt}</p>
        </div>
      </div>

      {!submitted ? (
        <>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Type your reflection here..."
            className="w-full h-32 p-3 border border-gray-300 rounded-lg resize-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
            aria-label="Reflection response"
          />
          <div className="flex items-center justify-between mt-2">
            <span className={`text-sm ${text.length >= minLen ? 'text-green-600' : 'text-gray-400'}`}>
              {text.length}/{minLen} characters minimum
            </span>
            <button
              onClick={handleSubmit}
              disabled={text.length < minLen}
              className="px-6 py-2 bg-indigo-600 text-white rounded-lg disabled:opacity-50 hover:bg-indigo-700 transition-colors"
            >
              Submit Reflection
            </button>
          </div>
        </>
      ) : (
        <div className="bg-green-50 border border-green-200 rounded-lg p-4">
          <p className="text-green-800 font-medium mb-1">Reflection submitted</p>
          <p className="text-gray-700">{text}</p>
        </div>
      )}
    </div>
  );
};
```

- [ ] **Step 7: Create SummaryLayout**

```tsx
// frontend/src/components/lessons/layouts/SummaryLayout.tsx
import React from 'react';
import type { LayoutProps } from '../types';
import type { SummaryScene } from '../schemas';
import { CheckCircleIcon } from '@heroicons/react/24/outline';

export const SummaryLayout: React.FC<LayoutProps> = ({ scene }) => {
  const s = scene as SummaryScene;

  return (
    <div className="p-6 sm:p-8">
      <h2 className="text-2xl font-bold text-gray-900 mb-6">{s.title}</h2>
      <div className="space-y-3 mb-6">
        {s.recap_points.map((point, i) => (
          <div key={i} className="flex items-start gap-3">
            <CheckCircleIcon className="w-5 h-5 text-green-500 mt-0.5 shrink-0" />
            <span className="text-gray-700">{point}</span>
          </div>
        ))}
      </div>
      {s.next_steps && (
        <div className="bg-gray-50 rounded-lg p-4">
          <p className="text-sm font-medium text-gray-500 mb-1">Next Steps</p>
          <p className="text-gray-700">{s.next_steps}</p>
        </div>
      )}
    </div>
  );
};
```

- [ ] **Step 8: Create index.ts to register all layouts**

Create `frontend/src/components/lessons/layouts/index.ts`:

```typescript
import { registerLayout } from '../SceneRenderer';
import { TitleLayout } from './TitleLayout';
import { ContentLayout } from './ContentLayout';
import { DefinitionLayout } from './DefinitionLayout';
import { ComparisonLayout } from './ComparisonLayout';
import { QuizLayout } from './QuizLayout';
import { ActivityLayout } from './ActivityLayout';
import { SummaryLayout } from './SummaryLayout';

registerLayout('title', TitleLayout);
registerLayout('content', ContentLayout);
registerLayout('definition', DefinitionLayout);
registerLayout('comparison', ComparisonLayout);
registerLayout('quiz', QuizLayout);
registerLayout('activity', ActivityLayout);
registerLayout('summary', SummaryLayout);
```

---

## Chunk 4: Frontend Admin Flow

### Task 13: Extract helpers and types from AIGenerationPanel

**Files:**
- Create: `frontend/src/components/courses/ai-generation/types.ts`
- Create: `frontend/src/components/courses/ai-generation/helpers.ts`

- [ ] **Step 1: Create the directory**

Run: `mkdir -p /Users/rakeshreddy/LMS/frontend/src/components/courses/ai-generation`

- [ ] **Step 2: Extract types.ts**

Move types from `AIGenerationPanel.tsx` lines 28-77 into `ai-generation/types.ts`:

```typescript
export type GeneratorState =
  | 'idle'
  | 'parsing'
  | 'generating-outline'
  | 'outline-ready'
  | 'generating-content'
  | 'content-ready'
  | 'lesson-config'
  | 'lesson-generating'
  | 'lesson-preview';

export type ContentType = 'lesson' | 'quiz' | 'assignment' | 'summary';

export interface AIGenerationPanelProps {
  courseId: string;
  modules: Array<{ id: string; title: string; order: number }>;
  onContentAdded?: () => void;
}

export interface OutlineSection {
  id: string;
  title: string;
  keyPoints: string[];
  selectedTypes: Set<ContentType>;
  expanded: boolean;
}

export interface GeneratedItem {
  sectionIndex: number;
  sectionTitle: string;
  type: ContentType;
  content: string;
  status: 'pending' | 'generating' | 'done' | 'error';
  error?: string;
}

export interface GeneratedQuestion {
  question: string;
  options: string[];
  correct_index: number;
  explanation: string;
}

export interface SectionProgress {
  sectionIndex: number;
  sectionTitle: string;
  types: Map<ContentType, 'pending' | 'generating' | 'done' | 'error'>;
}

export const ALL_CONTENT_TYPES: ContentType[] = ['lesson', 'quiz', 'assignment', 'summary'];
```

- [ ] **Step 3: Extract helpers.ts**

Move helpers from `AIGenerationPanel.tsx` lines 79-118 into `ai-generation/helpers.ts`:

```typescript
export function genId(): string {
  return `gen-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
}

export function extractErrorMessage(err: unknown, fallback = 'An unexpected error occurred'): string {
  if (err && typeof err === 'object' && 'response' in err) {
    const resp = (err as any).response;
    if (resp?.data) {
      const d = resp.data;
      if (typeof d === 'string') return d;
      if (d.detail) return String(d.detail);
      if (d.error) return typeof d.error === 'string' ? d.error : d.error.message || fallback;
      const firstKey = Object.keys(d)[0];
      if (firstKey && Array.isArray(d[firstKey])) return `${firstKey}: ${d[firstKey][0]}`;
    }
  }
  if (err instanceof Error) return err.message;
  return fallback;
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
```

- [ ] **Step 4: Update AIGenerationPanel imports**

At the top of `AIGenerationPanel.tsx`, replace the inline type definitions and helpers with:

```typescript
import type {
  GeneratorState, ContentType, AIGenerationPanelProps,
  OutlineSection, GeneratedItem, SectionProgress, ALL_CONTENT_TYPES
} from './ai-generation/types';
import { genId, extractErrorMessage, formatFileSize } from './ai-generation/helpers';
```

Remove the original inline definitions (lines ~28-118).

---

### Task 14: LessonConfigStep component

**Files:**
- Create: `frontend/src/components/courses/ai-generation/LessonConfigStep.tsx`

- [ ] **Step 1: Create LessonConfigStep**

```tsx
import React, { useState } from 'react';
import type { LessonConfig } from '../../lessons/types';
import { SparklesIcon } from '@heroicons/react/24/outline';

interface LessonConfigStepProps {
  onGenerate: (config: LessonConfig) => void;
  isGenerating: boolean;
}

export const LessonConfigStep: React.FC<LessonConfigStepProps> = ({ onGenerate, isGenerating }) => {
  const [config, setConfig] = useState<LessonConfig>({
    num_scenes: 10,
    include_quiz: true,
    include_activity: true,
    generate_narration: false,
  });

  return (
    <div className="space-y-6">
      <h3 className="text-lg font-semibold text-gray-900">Interactive Lesson Settings</h3>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">
          Number of Slides ({config.num_scenes})
        </label>
        <input
          type="range"
          min={3}
          max={12}
          value={config.num_scenes}
          onChange={(e) => setConfig((c) => ({ ...c, num_scenes: Number(e.target.value) }))}
          className="w-full"
        />
        <div className="flex justify-between text-xs text-gray-400">
          <span>3</span><span>12</span>
        </div>
      </div>

      <div className="space-y-3">
        <label className="flex items-center gap-3 cursor-pointer">
          <input
            type="checkbox"
            checked={config.include_quiz}
            onChange={(e) => setConfig((c) => ({ ...c, include_quiz: e.target.checked }))}
            className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
          />
          <span className="text-sm text-gray-700">Include quiz slides</span>
        </label>

        <label className="flex items-center gap-3 cursor-pointer">
          <input
            type="checkbox"
            checked={config.include_activity}
            onChange={(e) => setConfig((c) => ({ ...c, include_activity: e.target.checked }))}
            className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
          />
          <span className="text-sm text-gray-700">Include reflection activities</span>
        </label>

        <label className="flex items-center gap-3 cursor-pointer">
          <input
            type="checkbox"
            checked={config.generate_narration}
            onChange={(e) => setConfig((c) => ({ ...c, generate_narration: e.target.checked }))}
            className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
          />
          <span className="text-sm text-gray-700">Generate audio narration</span>
        </label>
      </div>

      <button
        onClick={() => onGenerate(config)}
        disabled={isGenerating}
        className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors"
      >
        <SparklesIcon className="w-5 h-5" />
        {isGenerating ? 'Generating...' : 'Generate Interactive Lesson'}
      </button>
    </div>
  );
};
```

---

### Task 15: LessonGenerationStep (progress) and GenerationProgress

**Files:**
- Create: `frontend/src/components/lessons/GenerationProgress.tsx`
- Create: `frontend/src/components/courses/ai-generation/LessonGenerationStep.tsx`

- [ ] **Step 1: Create GenerationProgress**

```tsx
// frontend/src/components/lessons/GenerationProgress.tsx
import React from 'react';
import type { GenerationStatus } from './types';

interface GenerationProgressProps {
  status: GenerationStatus | undefined;
  isLoading: boolean;
}

const PHASE_LABELS: Record<string, string> = {
  content_generation: 'Generating slides',
  image_generation: 'Generating images',
  audio_generation: 'Adding narration',
};

export const GenerationProgress: React.FC<GenerationProgressProps> = ({ status, isLoading }) => {
  if (isLoading || !status) {
    return (
      <div className="text-center py-12">
        <div className="animate-spin w-8 h-8 border-2 border-indigo-600 border-t-transparent rounded-full mx-auto mb-3" />
        <p className="text-gray-500">Starting generation...</p>
      </div>
    );
  }

  const percentage = status.progress?.percentage ?? 0;
  const phaseLabel = status.phase ? (PHASE_LABELS[status.phase] || status.phase) : 'Processing';

  return (
    <div className="py-8 px-4">
      <div className="max-w-md mx-auto">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-medium text-gray-700">{phaseLabel}...</span>
          <span className="text-sm text-gray-500">{percentage}%</span>
        </div>
        <div className="w-full bg-gray-200 rounded-full h-2.5">
          <div
            className="bg-indigo-600 h-2.5 rounded-full transition-all duration-500"
            style={{ width: `${percentage}%` }}
          />
        </div>
        {status.progress && (
          <p className="text-xs text-gray-400 mt-2 text-center">
            Scene {status.progress.current_scene} of {status.progress.total_scenes}
          </p>
        )}
        {status.error && (
          <div className="mt-4 bg-red-50 border border-red-200 rounded-lg p-3">
            <p className="text-sm text-red-700">{status.error}</p>
          </div>
        )}
      </div>
    </div>
  );
};
```

- [ ] **Step 2: Create LessonGenerationStep**

```tsx
// frontend/src/components/courses/ai-generation/LessonGenerationStep.tsx
import React from 'react';
import { GenerationProgress } from '../../lessons/GenerationProgress';
import { useGenerationStatus } from '../../lessons/useGenerationStatus';

interface LessonGenerationStepProps {
  lessonId: string;
  onComplete: (lessonId: string) => void;
  onError: (error: string) => void;
}

export const LessonGenerationStep: React.FC<LessonGenerationStepProps> = ({
  lessonId,
  onComplete,
  onError,
}) => {
  const { data: status, isLoading } = useGenerationStatus(lessonId);

  React.useEffect(() => {
    if (!status) return;
    if (status.status === 'READY' || status.status === 'PARTIAL_FAILURE') {
      onComplete(lessonId);
    } else if (status.status === 'FAILED') {
      onError(status.error || 'Generation failed');
    }
  }, [status?.status, lessonId, onComplete, onError]);

  return <GenerationProgress status={status} isLoading={isLoading} />;
};
```

---

### Task 16: LessonPreviewStep (scene preview with navigation)

**Files:**
- Create: `frontend/src/components/courses/ai-generation/LessonPreviewStep.tsx`

- [ ] **Step 1: Create LessonPreviewStep**

```tsx
import React, { useState, useCallback, useEffect } from 'react';
import { SceneRenderer } from '../../lessons/SceneRenderer';
import '../../lessons/layouts'; // registers all layouts
import { parseScenes } from '../../lessons/schemas';
import type { Scene } from '../../lessons/schemas';
import type { SceneAction } from '../../lessons/types';
import {
  ChevronLeftIcon,
  ChevronRightIcon,
  ArrowPathIcon,
  PlusCircleIcon,
  SpeakerWaveIcon,
} from '@heroicons/react/24/outline';

interface LessonPreviewStepProps {
  lessonId: string;
  rawScenes: unknown[];
  lessonTitle: string;
  onAddToModule: (lessonId: string) => void;
  onRegenerate: (lessonId: string, sceneId: string) => void;
  onBack: () => void;
}

export const LessonPreviewStep: React.FC<LessonPreviewStepProps> = ({
  lessonId,
  rawScenes,
  lessonTitle,
  onAddToModule,
  onRegenerate,
  onBack,
}) => {
  const scenes = parseScenes(rawScenes);
  const [currentIndex, setCurrentIndex] = useState(0);
  const scene = scenes[currentIndex];

  const goNext = useCallback(() => setCurrentIndex((i) => Math.min(i + 1, scenes.length - 1)), [scenes.length]);
  const goPrev = useCallback(() => setCurrentIndex((i) => Math.max(i - 1, 0)), []);

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'ArrowRight') goNext();
      if (e.key === 'ArrowLeft') goPrev();
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [goNext, goPrev]);

  const handleAction = (action: SceneAction) => {
    if (action.type === 'REGENERATE_SCENE') {
      onRegenerate(lessonId, action.sceneId);
    }
  };

  if (!scene) {
    return <p className="text-center text-gray-500 py-8">No valid scenes found.</p>;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-gray-900">{lessonTitle}</h3>
        <button onClick={onBack} className="text-sm text-gray-500 hover:text-gray-700">
          Back to input
        </button>
      </div>

      {/* Scene viewer */}
      <div className="border border-gray-200 rounded-xl bg-white overflow-hidden shadow-sm">
        <SceneRenderer scene={scene} onAction={handleAction} isAdmin />
      </div>

      {/* Navigation */}
      <div className="flex items-center justify-between">
        <button
          onClick={goPrev}
          disabled={currentIndex === 0}
          className="p-2 rounded-lg hover:bg-gray-100 disabled:opacity-30"
          aria-label="Previous scene"
        >
          <ChevronLeftIcon className="w-5 h-5" />
        </button>

        <div className="flex items-center gap-1.5">
          {scenes.map((_, i) => (
            <button
              key={i}
              onClick={() => setCurrentIndex(i)}
              className={`w-2 h-2 rounded-full transition-colors ${
                i === currentIndex ? 'bg-indigo-600' : 'bg-gray-300 hover:bg-gray-400'
              }`}
              aria-label={`Go to scene ${i + 1}`}
            />
          ))}
        </div>

        <button
          onClick={goNext}
          disabled={currentIndex === scenes.length - 1}
          className="p-2 rounded-lg hover:bg-gray-100 disabled:opacity-30"
          aria-label="Next scene"
        >
          <ChevronRightIcon className="w-5 h-5" />
        </button>
      </div>

      {/* Scene info + speaker notes */}
      <div className="text-sm text-gray-500 text-center">
        Scene {currentIndex + 1} of {scenes.length} — {scene.slide_type}
      </div>

      {scene.speaker_notes && (
        <div className="bg-gray-50 rounded-lg p-3 text-sm text-gray-600">
          <p className="font-medium text-gray-500 mb-1 flex items-center gap-1">
            <SpeakerWaveIcon className="w-4 h-4" /> Speaker Notes
          </p>
          {scene.speaker_notes}
        </div>
      )}

      {/* Actions */}
      <div className="flex gap-3">
        <button
          onClick={() => onRegenerate(lessonId, scene.id)}
          className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 transition-colors"
        >
          <ArrowPathIcon className="w-4 h-4" /> Regenerate Scene
        </button>
        <button
          onClick={() => onAddToModule(lessonId)}
          className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors"
        >
          <PlusCircleIcon className="w-4 h-4" /> Add to Module
        </button>
      </div>
    </div>
  );
};
```

---

## Chunk 5: Integration

### Task 17: Add aiService methods for new endpoints

**Files:**
- Modify: `frontend/src/services/aiService.ts`

- [ ] **Step 1: Add new studio methods**

In `aiService.ts`, inside the `studio` object (around line 296), add:

```typescript
    editScene: (lessonId: string, sceneId: string, updates: Record<string, unknown>) =>
      api.patch(`/v1/courses/ai-studio/lessons/${lessonId}/scenes/${sceneId}/`, updates),

    regenerateScene: (lessonId: string, sceneId: string) =>
      api.post(`/v1/courses/ai-studio/lessons/${lessonId}/scenes/${sceneId}/regenerate/`),

    generateImages: (lessonId: string) =>
      api.post(`/v1/courses/ai-studio/lessons/${lessonId}/generate-images/`),
```

- [ ] **Step 2: Update GenerateLessonRequest type**

Find the `GenerateLessonRequest` type (around line 143) and add:

```typescript
export interface GenerateLessonRequest {
  topic: string;
  description?: string;
  target_audience?: string;
  num_scenes?: number;
  include_quiz?: boolean;
  include_activity?: boolean;
  content_id?: string;
  module_id?: string;
  course_id?: string;
  generate_audio?: boolean;
}
```

---

### Task 18: Wire lesson flow into AIGenerationPanel

**Files:**
- Modify: `frontend/src/components/courses/AIGenerationPanel.tsx`

- [ ] **Step 1: Add lesson flow states**

After the existing state declarations (~line 553-565), add:

```typescript
const [lessonId, setLessonId] = useState<string | null>(null);
const [lessonScenes, setLessonScenes] = useState<unknown[]>([]);
const [lessonTitle, setLessonTitle] = useState('');
```

- [ ] **Step 2: Add content type toggle**

In the input phase UI, add a toggle between "Text Article" and "Interactive Lesson" before the generate button. When "Interactive Lesson" is selected, set `generatorState` to `'lesson-config'`.

- [ ] **Step 3: Add lesson config/generation/preview rendering**

In the main render, add cases for the new states:

```typescript
{generatorState === 'lesson-config' && (
  <LessonConfigStep
    onGenerate={async (config) => {
      setGeneratorState('lesson-generating');
      try {
        const res = await aiService.studio.generateLessonAsync({
          topic: inputText,
          num_scenes: config.num_scenes,
          include_quiz: config.include_quiz,
          include_activity: config.include_activity,
          generate_audio: config.generate_narration,
          module_id: selectedModuleId || undefined,
        });
        setLessonId(res.data.id || res.data.task_id);
      } catch (err) {
        setError(extractErrorMessage(err));
        setGeneratorState('lesson-config');
      }
    }}
    isGenerating={false}
  />
)}

{generatorState === 'lesson-generating' && lessonId && (
  <LessonGenerationStep
    lessonId={lessonId}
    onComplete={async (id) => {
      const res = await aiService.studio.getStatus(id);
      setLessonScenes(res.data.scenes || []);
      setLessonTitle(res.data.title || inputText);
      setGeneratorState('lesson-preview');
    }}
    onError={(err) => {
      setError(err);
      setGeneratorState('lesson-config');
    }}
  />
)}

{generatorState === 'lesson-preview' && (
  <LessonPreviewStep
    lessonId={lessonId!}
    rawScenes={lessonScenes}
    lessonTitle={lessonTitle}
    onAddToModule={async (id) => {
      await aiService.studio.createLesson(
        { id, title: lessonTitle },
        selectedModuleId || undefined,
      );
      onContentAdded?.();
      setGeneratorState('idle');
    }}
    onRegenerate={async (lid, sid) => {
      await aiService.studio.regenerateScene(lid, sid);
      const res = await aiService.studio.getStatus(lid);
      setLessonScenes(res.data.scenes || []);
    }}
    onBack={() => setGeneratorState('idle')}
  />
)}
```

- [ ] **Step 4: Add imports at top of file**

```typescript
import { LessonConfigStep } from './ai-generation/LessonConfigStep';
import { LessonGenerationStep } from './ai-generation/LessonGenerationStep';
import { LessonPreviewStep } from './ai-generation/LessonPreviewStep';
```

---

### Task 19: Update InteractiveLessonPlayer for v2 scenes

**Files:**
- Modify: `frontend/src/components/teacher/InteractiveLessonPlayer.tsx`

- [ ] **Step 1: Add v2 scene detection and SceneRenderer import**

At the top of the file:

```typescript
import { SceneRenderer } from '../lessons/SceneRenderer';
import '../lessons/layouts'; // register layout components
import { SceneSchema } from '../lessons/schemas';
```

- [ ] **Step 2: Add version-aware rendering**

In the scene rendering section (where `scene.narrative` is rendered, around line 273), wrap in a version check:

```typescript
{/* Scene content — v2 uses SceneRenderer, v1 uses legacy rendering */}
{scene.slide_type ? (
  <SceneRenderer
    scene={SceneSchema.parse(scene)}
    onAction={(action) => {
      if (action.type === 'SUBMIT_REFLECTION') {
        reflectionMutation.mutate({
          lessonId: lesson.id,
          sceneIndex: currentScene,
          responseText: action.text,
        });
      }
    }}
  />
) : (
  /* Existing v1 rendering code stays here unchanged */
  <>
    <div className="prose prose-sm" dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(scene.narrative || '') }} />
    {/* ... existing key_points, reflection rendering ... */}
  </>
)}
```

This preserves backward compatibility: v1 scenes (no `slide_type`) render with the existing code, v2 scenes delegate to `SceneRenderer`.

---

### Task 20: Install json-repair backend dependency

**Files:**
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Add json-repair**

Add to `requirements.txt`:

```
json-repair==0.30.0
```

- [ ] **Step 2: Update ai_service.py to use json-repair**

In `ai_service.py`, in the JSON extraction section of `generate_interactive_lesson`, add fallback:

```python
        try:
            lesson_data = json.loads(raw_json)
        except json.JSONDecodeError:
            try:
                from json_repair import repair_json
                repaired = repair_json(raw_json)
                lesson_data = json.loads(repaired)
            except Exception:
                logger.warning("Failed to parse or repair LLM JSON output")
                return None
```

---

## File Map Summary

| Action | Path | Task |
|--------|------|------|
| Modify | `backend/apps/courses/ai_studio_models.py` | 1 |
| Create | `backend/apps/courses/migrations/0016_*.py` | 1 |
| Create | `backend/apps/courses/scene_validation.py` | 2-5 |
| Create | `backend/apps/courses/tests_scene_validation.py` | 2-5 |
| Modify | `backend/apps/courses/ai_service.py` | 6 |
| Modify | `backend/apps/courses/ai_studio_views.py` | 7-8 |
| Modify | `backend/apps/courses/ai_studio_tasks.py` | 8 |
| Modify | `backend/apps/courses/urls.py` | 8 |
| Modify | `backend/requirements.txt` | 20 |
| Create | `frontend/src/components/lessons/schemas.ts` | 9 |
| Create | `frontend/src/components/lessons/types.ts` | 9 |
| Create | `frontend/src/components/lessons/iconMap.ts` | 10 |
| Create | `frontend/src/components/lessons/useGenerationStatus.ts` | 10 |
| Create | `frontend/src/components/lessons/SceneRenderer.tsx` | 11 |
| Create | `frontend/src/components/lessons/GenerationProgress.tsx` | 15 |
| Create | `frontend/src/components/lessons/layouts/*.tsx` (8 files) | 12 |
| Create | `frontend/src/components/courses/ai-generation/types.ts` | 13 |
| Create | `frontend/src/components/courses/ai-generation/helpers.ts` | 13 |
| Create | `frontend/src/components/courses/ai-generation/LessonConfigStep.tsx` | 14 |
| Create | `frontend/src/components/courses/ai-generation/LessonGenerationStep.tsx` | 15 |
| Create | `frontend/src/components/courses/ai-generation/LessonPreviewStep.tsx` | 16 |
| Modify | `frontend/src/services/aiService.ts` | 17 |
| Modify | `frontend/src/components/courses/AIGenerationPanel.tsx` | 13, 18 |
| Modify | `frontend/src/components/teacher/InteractiveLessonPlayer.tsx` | 19 |

**Total: 20 tasks, ~28 files (15 new, 13 modified)**
