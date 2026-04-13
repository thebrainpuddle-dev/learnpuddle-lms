# apps/courses/scene_validation.py
"""
Scene normalization and validation pipeline for LLM-generated interactive content.

This module converts raw scene data from language models into a canonical,
safe format suitable for storage and rendering.  The pipeline handles:

1. Slide-type normalization (aliases, case folding)
2. Field-type coercion (string -> list, string -> int)
3. HTML sanitization (XSS prevention via ``bleach``)
4. Field truncation and list-length capping
5. Quiz-option normalization (string[] + correct_answer -> structured objects)
6. Required-field validation per slide type
7. Backend-default injection (UUIDs, ordering, image status, etc.)

Public entry point
------------------
``normalize_scenes(raw_scenes)`` -- runs the full pipeline and returns a clean
list of scene dicts.
"""

from __future__ import annotations

import uuid
from typing import Any

import bleach

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_SLIDE_TYPES: set[str] = frozenset(
    {
        "title",
        "content",
        "quiz",
        "reflection",
        "activity",
        "definition",
        "comparison",
        "summary",
        "case_study",
    }
)

SLIDE_TYPE_ALIASES: dict[str, str] = {
    # Common LLM variations -> canonical type
    "info": "content",
    "information": "content",
    "text": "content",
    "narrative": "content",
    "lecture": "content",
    "slide": "content",
    "intro": "title",
    "introduction": "title",
    "opening": "title",
    "hero": "title",
    "question": "quiz",
    "mcq": "quiz",
    "multiple_choice": "quiz",
    "multiple choice": "quiz",
    "multiplechoice": "quiz",
    "true_false": "quiz",
    "true/false": "quiz",
    "reflect": "reflection",
    "think": "reflection",
    "prompt": "reflection",
    "exercise": "activity",
    "task": "activity",
    "practice": "activity",
    "hands_on": "activity",
    "hands-on": "activity",
    "define": "definition",
    "term": "definition",
    "vocabulary": "definition",
    "vocab": "definition",
    "glossary": "definition",
    "recap": "summary",
    "review": "summary",
    "wrap_up": "summary",
    "wrap-up": "summary",
    "wrapup": "summary",
    "conclusion": "summary",
    "compare": "comparison",
    "versus": "comparison",
    "vs": "comparison",
    "side_by_side": "comparison",
    "side-by-side": "comparison",
    "case": "case_study",
    "casestudy": "case_study",
    "case-study": "case_study",
    "scenario": "case_study",
}

#: Fields that must be present for each slide type (at least one of each set).
REQUIRED_FIELDS: dict[str, list[str]] = {
    "title": ["title"],
    "content": ["title"],       # also needs body OR bullets (handled specially)
    "quiz": ["title", "question", "options"],
    "reflection": ["title", "prompt"],
    "activity": ["title", "instructions"],
    "definition": ["term", "definition"],
    "comparison": ["title"],    # needs left_label + right_label (handled specially)
    "summary": ["title"],
    "case_study": ["title", "scenario"],
}

FIELD_MAX_LENGTHS: dict[str, int] = {
    "title": 300,
    "subtitle": 500,
    "body": 5000,
    "narrative": 5000,
    "question": 1000,
    "prompt": 1000,
    "reflection_prompt": 1000,
    "instructions": 3000,
    "term": 200,
    "definition": 3000,
    "example": 3000,
    "scenario": 5000,
    "image_keyword": 100,
    "alt_text": 300,
    "explanation": 3000,
    "speaker_notes": 3000,
    "left_label": 200,
    "right_label": 200,
}

LIST_FIELD_LIMITS: dict[str, int] = {
    "key_points": 10,
    "bullets": 10,
    "options": 8,
    "steps": 15,
    "examples": 10,
    "learning_objectives": 10,
    "tags": 10,
    "left_points": 10,
    "right_points": 10,
    "recap_points": 10,
    "next_steps": 10,
}

#: List-typed fields that LLMs sometimes emit as comma-separated strings.
_LIST_FIELDS: set[str] = frozenset(LIST_FIELD_LIMITS.keys())

#: Fields that contain intentional HTML (body, narrative, etc.)
_HTML_FIELDS: set[str] = frozenset({"body", "narrative", "definition", "example", "instructions", "scenario"})

#: Allowed HTML tags for rich-text fields
_ALLOWED_HTML_TAGS: list[str] = [
    "p", "br", "strong", "b", "em", "i", "u",
    "ul", "ol", "li",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "span", "div", "blockquote", "code", "pre",
    "a", "sup", "sub",
    "table", "thead", "tbody", "tr", "th", "td",
]

#: Allowed HTML attributes
_ALLOWED_HTML_ATTRS: dict[str, list[str]] = {
    "a": ["href", "title", "target"],
    "span": ["class"],
}

#: Maximum number of scenes in a single lesson.
MAX_SCENES = 20


# ---------------------------------------------------------------------------
# 1. Slide-type normalization
# ---------------------------------------------------------------------------

def normalize_slide_type(raw: str) -> str | None:
    """Return the canonical slide type or ``None`` if unrecognised.

    * Case-insensitive
    * Leading/trailing whitespace stripped
    * Checks aliases before giving up
    """
    if not isinstance(raw, str):
        return None
    cleaned = raw.strip().lower()
    if not cleaned:
        return None
    if cleaned in VALID_SLIDE_TYPES:
        return cleaned
    return SLIDE_TYPE_ALIASES.get(cleaned)


# ---------------------------------------------------------------------------
# 2. Field-type coercion
# ---------------------------------------------------------------------------

def coerce_field_types(scene: dict) -> dict:
    """Coerce mis-typed fields emitted by LLMs into expected Python types.

    * String values for known list fields are split on ``", "`` / ``","``
      into a real list.
    * ``reflection_min_length`` is cast to ``int`` if it arrives as a string.

    Returns a *new* dict (shallow copy).
    """
    result = dict(scene)

    for field in _LIST_FIELDS:
        value = result.get(field)
        if isinstance(value, str):
            # Split on comma (with optional surrounding whitespace)
            parts = [p.strip() for p in value.split(",") if p.strip()]
            result[field] = parts

    # reflection_min_length -> int
    rml = result.get("reflection_min_length")
    if isinstance(rml, str):
        try:
            result["reflection_min_length"] = int(rml)
        except (ValueError, TypeError):
            result.pop("reflection_min_length", None)

    return result


# ---------------------------------------------------------------------------
# 3. Sanitization
# ---------------------------------------------------------------------------

def sanitize_scene_fields(scene: dict) -> dict:
    """Sanitise all text fields and enforce length/count limits.

    * Runs ``bleach.clean()`` on every string value (strips dangerous HTML).
    * Truncates text fields per ``FIELD_MAX_LENGTHS``.
    * Caps list lengths per ``LIST_FIELD_LIMITS``.
    * Sanitises individual list-item strings as well.

    Returns a *new* dict (shallow copy of top level).
    """
    result = dict(scene)

    # Sanitise and truncate string fields
    for key, value in result.items():
        if isinstance(value, str):
            if key in _HTML_FIELDS:
                # Allow safe HTML tags in rich-text fields
                cleaned = bleach.clean(
                    value,
                    tags=_ALLOWED_HTML_TAGS,
                    attributes=_ALLOWED_HTML_ATTRS,
                    strip=True,
                )
            else:
                cleaned = bleach.clean(value, tags=[], strip=True)
            max_len = FIELD_MAX_LENGTHS.get(key)
            if max_len is not None:
                cleaned = cleaned[:max_len]
            result[key] = cleaned

    # Sanitise and cap list fields
    for field, limit in LIST_FIELD_LIMITS.items():
        items = result.get(field)
        if isinstance(items, list):
            sanitised: list[Any] = []
            for item in items[:limit]:
                if isinstance(item, str):
                    sanitised.append(bleach.clean(item, tags=[], strip=True))
                else:
                    # Sanitize string values inside nested dicts (e.g., quiz option text)
                    if isinstance(item, dict):
                        item = {
                            k: bleach.clean(str(v), tags=[], strip=True) if isinstance(v, str) else v
                            for k, v in item.items()
                        }
                    sanitised.append(item)
            result[field] = sanitised

    return result


# ---------------------------------------------------------------------------
# 4. Quiz-option normalization
# ---------------------------------------------------------------------------

def normalize_quiz_options(scene: dict) -> dict:
    """Convert flat quiz options into structured ``[{id, text, is_correct}]``.

    Expected *input* format from LLMs::

        {
            "type": "quiz",
            "options": ["Alpha", "Beta", "Gamma"],
            "correct_answer": "Beta"
        }

    Output::

        {
            "type": "quiz",
            "options": [
                {"id": "<uuid>", "text": "Alpha", "is_correct": false},
                {"id": "<uuid>", "text": "Beta",  "is_correct": true},
                {"id": "<uuid>", "text": "Gamma", "is_correct": false},
            ]
        }

    Rules:
    * Matching is case-insensitive and whitespace-trimmed.
    * ``correct_answer`` is removed after processing.
    * If no option matches, the first option is marked correct.
    * If options are already normalised (list of dicts with ``is_correct``),
      they are left unchanged.
    * Non-quiz scenes are returned unchanged.
    """
    result = dict(scene)
    slide_type = result.get("type", "")
    if slide_type != "quiz":
        return result

    options = result.get("options")
    if not isinstance(options, list) or len(options) == 0:
        return result

    # Already normalised? (list of dicts with ``is_correct`` key)
    if isinstance(options[0], dict) and "is_correct" in options[0]:
        # Ensure each option has a unique id
        for opt in options:
            if "id" not in opt:
                opt["id"] = str(uuid.uuid4())
        return result

    # Flat list of strings -- normalise
    correct_raw = result.pop("correct_answer", None)
    correct_normalised = (
        correct_raw.strip().lower() if isinstance(correct_raw, str) else None
    )

    normalised: list[dict[str, Any]] = []
    matched = False
    for text in options:
        if not isinstance(text, str):
            text = str(text)
        is_correct = False
        if correct_normalised is not None and text.strip().lower() == correct_normalised:
            is_correct = True
            matched = True
        normalised.append(
            {
                "id": str(uuid.uuid4()),
                "text": text,
                "is_correct": is_correct,
            }
        )

    # Fallback: if no match found, mark the first option as correct
    if not matched and normalised:
        normalised[0]["is_correct"] = True

    result["options"] = normalised
    return result


# ---------------------------------------------------------------------------
# 5. Required-field validation
# ---------------------------------------------------------------------------

def validate_required_fields(scene: dict) -> list[str]:
    """Return a list of missing required field names for the given scene.

    The ``content`` type is handled specially: it requires ``title`` **and**
    at least one of ``body`` or ``bullets``.

    An empty list means the scene is valid.
    """
    slide_type = scene.get("type", "")
    required = REQUIRED_FIELDS.get(slide_type)
    if required is None:
        # Unknown type -- cannot validate, treat as invalid
        return ["type"]

    missing: list[str] = []
    for field in required:
        value = scene.get(field)
        if value is None:
            missing.append(field)
        elif isinstance(value, str) and not value.strip():
            missing.append(field)
        elif isinstance(value, list) and len(value) == 0:
            missing.append(field)

    # Special rule for content: needs at least body OR bullets
    if slide_type == "content":
        body = scene.get("body")
        bullets = scene.get("bullets")
        has_body = isinstance(body, str) and bool(body.strip())
        has_bullets = isinstance(bullets, list) and len(bullets) > 0
        if not has_body and not has_bullets:
            if "body" not in missing:
                missing.append("body")

    # Special rule for comparison: needs left_label AND right_label
    if slide_type == "comparison":
        left_label = scene.get("left_label")
        right_label = scene.get("right_label")
        if not (isinstance(left_label, str) and left_label.strip()):
            if "left_label" not in missing:
                missing.append("left_label")
        if not (isinstance(right_label, str) and right_label.strip()):
            if "right_label" not in missing:
                missing.append("right_label")

    return missing


# ---------------------------------------------------------------------------
# 6. Full pipeline
# ---------------------------------------------------------------------------

def normalize_scenes(raw_scenes: list | None) -> list[dict[str, Any]]:
    """Run the complete normalisation pipeline on raw LLM-generated scenes.

    Steps per scene:
    1. Normalise slide type (drop scene if unrecognised).
    2. Coerce mis-typed fields.
    3. Validate required fields (drop scene if any missing).
    4. Normalise quiz options.
    5. Sanitise text and enforce limits.
    6. Inject backend defaults (id, order, image metadata, etc.).

    Returns at most ``MAX_SCENES`` (20) scenes.
    """
    if not isinstance(raw_scenes, list):
        return []

    output: list[dict[str, Any]] = []

    for idx, raw in enumerate(raw_scenes):
        if not isinstance(raw, dict):
            continue

        scene = dict(raw)

        # --- Step 1: slide type ---
        raw_type = scene.get("type", scene.get("slide_type", ""))
        canonical = normalize_slide_type(str(raw_type))
        if canonical is None:
            continue  # drop unrecognised types
        scene["type"] = canonical
        scene.pop("slide_type", None)

        # --- Step 2: coerce ---
        scene = coerce_field_types(scene)

        # --- Step 3: validate ---
        missing = validate_required_fields(scene)
        if missing:
            continue  # drop invalid scenes

        # --- Step 4: quiz options ---
        scene = normalize_quiz_options(scene)

        # --- Step 5: sanitise ---
        scene = sanitize_scene_fields(scene)

        # --- Step 6: backend defaults ---
        scene = _apply_backend_defaults(scene, idx)

        output.append(scene)

        if len(output) >= MAX_SCENES:
            break

    return output


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _apply_backend_defaults(scene: dict, index: int) -> dict:
    """Inject server-side defaults that the LLM should not control.

    * ``id`` -- UUID v4 (never trust client-supplied IDs)
    * ``order`` -- 0-based, derived from list index
    * ``image_url`` -- always starts as ``None``
    * ``audio_url`` -- always starts as ``None``
    * ``duration_seconds`` -- always starts as ``None``
    * ``image_status`` -- ``"pending"`` if scene has ``image_keyword``,
      otherwise ``"none"``
    * ``alt_text`` -- auto-generated from ``image_keyword`` if not provided
    * ``title`` -- auto-generated for ``definition`` type from ``term``
    * Activity defaults -- ``activity_type`` and ``estimated_minutes``
    """
    result = dict(scene)

    # Immutable server-side fields
    result["id"] = str(uuid.uuid4())
    result["order"] = index
    result["image_url"] = None
    result["audio_url"] = None
    result["duration_seconds"] = None

    # Image status
    image_keyword = result.get("image_keyword")
    has_keyword = isinstance(image_keyword, str) and image_keyword.strip()
    result["image_status"] = "pending" if has_keyword else "none"

    # Auto alt_text
    if not result.get("alt_text") and has_keyword:
        result["alt_text"] = f"Illustration for: {image_keyword.strip()}"

    # Definition: auto-generate title from term
    if result.get("type") == "definition" and not result.get("title"):
        term = result.get("term", "")
        if isinstance(term, str) and term.strip():
            result["title"] = f"Definition: {term.strip()}"

    # Activity defaults
    if result.get("type") == "activity":
        result.setdefault("activity_type", "individual")
        result.setdefault("estimated_minutes", 5)

    return result
