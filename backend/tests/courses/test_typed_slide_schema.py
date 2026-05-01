"""F4 (P0) — typed slide schema validator/normalizer tests.

Source: 2026-04-28 OpenMAIC deep-dive followups (F4).

Verifies the additive contract for ``slide.template`` + ``slide.slots``:

  type SlideTemplateId = 'body-image-right' | 'free-form';
  interface SlideSlots {
    title?: { text: string };
    body?:  { text?: string; bullets?: string[] };
    image?: { src?: string; alt?: string; meta?: Record<string, unknown> };
    footer?: { text: string };
  }

The smallest first cut renders ``body-image-right`` only; ``free-form``
is accepted for forward-compat. Anything else must raise. Slides without
``template`` keep working exactly as today (no validation surface).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from apps.courses.maic_generation_service import (
    ALLOWED_SLIDE_TEMPLATES,
    SlideSchemaValidationError,
    normalize_slide_schema,
    validate_slide_template,
)


# ── 1. validator accepts a slide with template + valid slots ────────────────


def test_validator_accepts_body_image_right_with_valid_slots():
    """A slide with ``template: 'body-image-right'`` and a populated ``slots``
    dict must pass validation untouched. Empty/missing slot keys are OK —
    the renderer falls back to ``elements[]`` for any slot that's absent.
    """
    slide = {
        "id": "slide-1",
        "template": "body-image-right",
        "slots": {
            "title": {"text": "Photosynthesis"},
            "body": {
                "text": "Plants convert sunlight into chemical energy.",
                "bullets": ["Light reactions", "Calvin cycle"],
            },
            "image": {
                "src": "",
                "alt": "Diagram of a chloroplast",
                "meta": {"keyword": "chloroplast"},
            },
            "footer": {"text": "Key takeaway: photosynthesis is two-stage"},
        },
        "elements": [],
    }
    # No exception means validation passed.
    validate_slide_template(slide)
    out = normalize_slide_schema(slide)
    # Returned in place; no breaking mutations to the valid slot shape.
    assert out is slide
    assert out["template"] == "body-image-right"
    assert out["slots"]["title"] == {"text": "Photosynthesis"}
    assert out["slots"]["image"]["alt"] == "Diagram of a chloroplast"


def test_validator_accepts_free_form_template():
    """``free-form`` is the explicit "no typed layout" sentinel. Must validate."""
    slide = {"id": "slide-1", "template": "free-form", "elements": []}
    validate_slide_template(slide)
    assert normalize_slide_schema(slide) is slide


# ── 2. validator rejects an unknown template value ──────────────────────────


def test_validator_rejects_unknown_template_value():
    slide = {"id": "slide-1", "template": "two-column", "elements": []}
    with pytest.raises(SlideSchemaValidationError) as excinfo:
        validate_slide_template(slide)
    # The error message is for ops, not end-users — assert it surfaces both
    # the bad value and the allowed set for a useful log line.
    assert "two-column" in str(excinfo.value)
    assert "body-image-right" in str(excinfo.value)


def test_validator_rejects_non_string_template():
    """Non-string templates (None handled separately, but ints/dicts aren't
    valid because the renderer dispatch is a string switch)."""
    for bad in (123, ["body-image-right"], {"id": "body-image-right"}):
        slide = {"id": "slide-1", "template": bad, "elements": []}
        with pytest.raises(SlideSchemaValidationError):
            validate_slide_template(slide)


# ── 3. validator accepts legacy slide (no template, no slots) ───────────────


def test_validator_accepts_legacy_slide_unchanged():
    """A slide without ``template`` or ``slots`` must pass through untouched —
    that's the backward-compat invariant for every existing classroom in
    production."""
    slide = {
        "id": "slide-legacy",
        "title": "Legacy Slide",
        "elements": [
            {
                "type": "text",
                "id": "el-1",
                "x": 40,
                "y": 30,
                "width": 720,
                "height": 50,
                "content": "Legacy heading",
            },
            {
                "type": "image",
                "id": "el-2",
                "x": 460,
                "y": 90,
                "width": 300,
                "height": 240,
                "src": "https://example.com/x.jpg",
                "content": "x",
            },
        ],
        "background": "#FFFFFF",
        "duration": 45,
    }
    # No exception.
    validate_slide_template(slide)
    out = normalize_slide_schema(slide)
    # Legacy slides must come back IDENTICAL — no template added, no slots
    # synthesized (the heuristic backfill only fires when template is set).
    assert out is slide
    assert "template" not in out
    assert "slots" not in out
    # elements[] preserved as-is.
    assert len(out["elements"]) == 2
    assert out["elements"][1]["src"] == "https://example.com/x.jpg"


# ── 4. heuristic backfill: derive slots from elements[] when template set ───


def test_normalize_backfills_slots_from_elements_when_template_set():
    """When the LLM emits ``template: 'body-image-right'`` but leaves ``slots``
    missing/partial, the normalizer should heuristically fill ``slots.title``,
    ``slots.body``, ``slots.image`` from clear elements[] entries.
    """
    slide = {
        "id": "slide-backfill",
        "template": "body-image-right",
        "elements": [
            {
                "type": "text",
                "id": "el-title",
                "x": 40,
                "y": 30,
                "width": 720,
                "height": 50,
                "content": "Energy in Living Systems",
                "style": {"fontSize": 32, "fontWeight": "bold"},
            },
            {
                "type": "text",
                "id": "el-body",
                "x": 40,
                "y": 90,
                "width": 400,
                "height": 280,
                "content": "Cells use ATP as their energy currency.",
                "style": {"fontSize": 18, "color": "#334155"},
            },
            {
                "type": "image",
                "id": "el-img",
                "x": 460,
                "y": 90,
                "width": 300,
                "height": 240,
                "src": "https://images.unsplash.com/photo-cell",
                "content": "Diagram of a mitochondrion",
            },
        ],
    }
    out = normalize_slide_schema(slide)
    assert "slots" in out
    assert out["slots"]["title"] == {"text": "Energy in Living Systems"}
    # Body falls back to the second text element (not the title).
    assert out["slots"]["body"]["text"] == "Cells use ATP as their energy currency."
    # Image slot picks up src + alt from the image element.
    assert out["slots"]["image"]["src"] == "https://images.unsplash.com/photo-cell"
    assert out["slots"]["image"]["alt"] == "Diagram of a mitochondrion"


def test_normalize_does_not_overwrite_existing_slots():
    """If the LLM already populated ``slots.title``, the heuristic backfill
    must NOT clobber it with the elements[]-derived value."""
    slide = {
        "id": "slide-merge",
        "template": "body-image-right",
        "slots": {
            "title": {"text": "LLM-supplied title"},
        },
        "elements": [
            {
                "type": "text",
                "id": "el-title",
                "content": "Different title in elements",
                "style": {"fontSize": 32, "fontWeight": "bold"},
            },
            {
                "type": "image",
                "id": "el-img",
                "src": "",
                "content": "alt text",
            },
        ],
    }
    out = normalize_slide_schema(slide)
    # LLM-supplied slot wins.
    assert out["slots"]["title"] == {"text": "LLM-supplied title"}
    # Image slot still gets backfilled because it was absent.
    assert out["slots"]["image"]["alt"] == "alt text"


# ── WAVE-6-F4-F2: extend idempotency coverage to body + image slots ─────────


def test_normalize_does_not_overwrite_existing_body_slot():
    """REGRESSION (WAVE-6-F4-F2): body-slot idempotency was not exercised by
    the existing title-only test, so a typo in ``_backfill_slots_from_elements``
    body guard could slip through.  This test pre-populates ``slots.body``
    with a known string and asserts the helper does NOT overwrite it after
    running.
    """
    slide = {
        "id": "slide-body-merge",
        "template": "body-image-right",
        "slots": {
            "body": {"text": "LLM-supplied body text"},
        },
        "elements": [
            # Title element (would feed slots.title — that's NOT under test).
            {
                "type": "text",
                "id": "el-title",
                "content": "Title from elements",
                "style": {"fontSize": 32, "fontWeight": "bold"},
            },
            # Plain (non-title) text element — the body-backfill heuristic
            # picks the first non-title text.  If the body-guard is broken,
            # this string will overwrite the LLM-supplied body.
            {
                "type": "text",
                "id": "el-body",
                "content": "Different body in elements — must NOT overwrite",
                "style": {"fontSize": 18},
            },
        ],
    }
    out = normalize_slide_schema(slide)
    # LLM-supplied body slot wins; elements[] body never reaches slots.body.
    assert out["slots"]["body"] == {"text": "LLM-supplied body text"}
    # Title still got backfilled because it was absent (smoke check the
    # heuristic still ran).
    assert out["slots"]["title"] == {"text": "Title from elements"}


def test_normalize_does_not_overwrite_existing_image_slot_src():
    """Sibling to the body test — confirms the image-slot guard preserves
    a pre-populated ``slots.image.src`` and does not let the elements[]
    image-element src overwrite it.

    The helper is permitted to backfill missing sub-keys (alt, meta) onto
    an existing image slot, but ``src`` is the load-bearing field for the
    renderer and a pre-existing one MUST win.
    """
    slide = {
        "id": "slide-image-merge",
        "template": "body-image-right",
        "slots": {
            "image": {
                "src": "https://example.com/llm-supplied-image.png",
                "alt": "LLM alt",
            },
        },
        "elements": [
            {
                "type": "image",
                "id": "el-img",
                "src": "https://example.com/elements-derived.png",
                "content": "Different alt from elements",
            },
        ],
    }
    out = normalize_slide_schema(slide)
    # LLM-supplied src wins.
    assert out["slots"]["image"]["src"] == "https://example.com/llm-supplied-image.png"
    # And the LLM-supplied alt is also preserved.
    assert out["slots"]["image"]["alt"] == "LLM alt"


def test_normalize_does_not_synthesize_footer_slot():
    """Backfill helper covers ``title|body|image`` only — ``footer`` is
    NOT auto-derived from elements[].  This test pins the contract: a
    footer slot the LLM omitted stays omitted, and one the LLM supplied
    stays untouched.

    If a future change extends the helper to backfill footer, update
    this test along with ``_backfill_slots_from_elements``.
    """
    # Case 1: no footer supplied — none should be synthesised.
    slide_no_footer = {
        "id": "slide-no-footer",
        "template": "body-image-right",
        "elements": [
            {
                "type": "text",
                "id": "el-title",
                "content": "Title",
                "style": {"fontSize": 32, "fontWeight": "bold"},
            },
        ],
    }
    out_no_footer = normalize_slide_schema(slide_no_footer)
    assert "footer" not in out_no_footer.get("slots", {})

    # Case 2: footer supplied — must round-trip unchanged.
    slide_with_footer = {
        "id": "slide-with-footer",
        "template": "body-image-right",
        "slots": {"footer": {"text": "Key takeaway"}},
        "elements": [
            {
                "type": "text",
                "id": "el-title",
                "content": "Title",
                "style": {"fontSize": 32, "fontWeight": "bold"},
            },
        ],
    }
    out_with_footer = normalize_slide_schema(slide_with_footer)
    assert out_with_footer["slots"]["footer"] == {"text": "Key takeaway"}


def test_normalize_strips_unknown_top_level_slot_keys():
    """Forward-compat: future renderer might add slot keys. Today, only
    ``title|body|image|footer`` are recognised; anything else at the slot
    top level is dropped silently so a typo (``slots.titel``) cannot
    silently miss the renderer's slot map."""
    slide = {
        "id": "slide-typo",
        "template": "body-image-right",
        "slots": {
            "title": {"text": "Real title"},
            "titel": {"text": "Typo"},  # unknown — must be dropped.
            "video": {"src": "x"},  # unknown — must be dropped.
        },
        "elements": [],
    }
    out = normalize_slide_schema(slide)
    assert "title" in out["slots"]
    assert "titel" not in out["slots"]
    assert "video" not in out["slots"]


def test_allowed_templates_constant_includes_body_image_right():
    """Smoke check the public constant — frontend ContentSchema lives in
    sync with this set, so a typo here would break both ends."""
    assert "body-image-right" in ALLOWED_SLIDE_TEMPLATES
    assert "free-form" in ALLOWED_SLIDE_TEMPLATES


# ── BUNDLE-2026-04-29-FX-5: load-bearing ordering invariant ─────────────────


def test_normalize_slide_schema_validates_before_backfill():
    """Pin the load-bearing ordering inside ``normalize_slide_schema``.

    Validation MUST run BEFORE the heuristic backfill. Callers wrap this in
    ``try/except SlideSchemaValidationError`` and recover by popping
    ``template``/``slots`` — if backfill ran first, the pop wouldn't undo
    the synthesised slots and the slide would carry orphaned slot data
    after a "failed" validation.

    This test patches ``_backfill_slots_from_elements`` and asserts that
    when validation raises, the backfill helper was never invoked.
    """
    slide = {
        "id": "slide-bad",
        "template": "two-column",  # not in ALLOWED_SLIDE_TEMPLATES — must raise
        "elements": [
            {
                "type": "text",
                "id": "el-title",
                "content": "Title",
                "style": {"fontSize": 32, "fontWeight": "bold"},
            },
        ],
    }
    with patch(
        "apps.courses.maic_generation_service._backfill_slots_from_elements"
    ) as backfill_spy:
        with pytest.raises(SlideSchemaValidationError):
            normalize_slide_schema(slide)
    # The escape hatch only works because backfill never ran.
    assert backfill_spy.call_count == 0
    # And ``slots`` was never synthesised onto the slide.
    assert "slots" not in slide
