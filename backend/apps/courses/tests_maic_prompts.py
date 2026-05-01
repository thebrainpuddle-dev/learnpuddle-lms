"""
Smoke tests for the audience-aware MAIC system-prompt builders.

Guards the contract that:
  * Each builder returns a string (not None, not a dict).
  * Grade-band guidance actually varies the prompt text — Grade 8 content
    gets "plain-language"/"concrete" phrasing, Grade 12 gets "rigorous"/
    "formal" phrasing.
  * Switching the syllabus_board produces a different prompt than the
    Generic default (board-specific phrases leak through).

No LLM calls, no Django DB — pure string inspection. Run with:
    pytest apps/courses/tests_maic_prompts.py
"""

from __future__ import annotations

from apps.courses.maic_generation_service import (
    build_actions_system_prompt,
    build_outline_system_prompt,
    build_scene_content_system_prompt,
)


BUILDERS = (
    build_outline_system_prompt,
    build_scene_content_system_prompt,
    build_actions_system_prompt,
)


def test_builders_return_strings():
    for build in BUILDERS:
        prompt = build()
        assert isinstance(prompt, str), f"{build.__name__} returned {type(prompt)}"
        assert prompt, f"{build.__name__} returned empty string"


def test_builders_accept_full_context():
    """Builders must accept all four kwargs without raising."""
    for build in BUILDERS:
        prompt = build(
            grade_level="Grade 8",
            subject="Physics",
            syllabus_board="CBSE",
            audience_role="student",
        )
        assert isinstance(prompt, str) and prompt


def test_grade_8_prompt_uses_accessible_register():
    """Grade 8 (middle band) should mention plain-language or concrete guidance."""
    for build in BUILDERS:
        prompt = build(grade_level="Grade 8", subject="Physics",
                       syllabus_board="Generic", audience_role="student")
        lower = prompt.lower()
        assert "plain-language" in lower or "concrete" in lower, (
            f"{build.__name__} at Grade 8 missing accessible-register cues:\n{prompt[:600]}"
        )


def test_grade_12_prompt_uses_rigorous_register():
    """Grade 12 (high band) should mention rigorous or formal guidance."""
    for build in BUILDERS:
        prompt = build(grade_level="Grade 12", subject="Physics",
                       syllabus_board="Generic", audience_role="student")
        lower = prompt.lower()
        assert "rigorous" in lower or "formal" in lower, (
            f"{build.__name__} at Grade 12 missing rigorous-register cues:\n{prompt[:600]}"
        )


def test_syllabus_board_changes_output():
    """Switching Generic -> CBSE must change the prompt string (NCERT phrasing
    leaks in) and similarly for IB (DP command terms)."""
    for build in BUILDERS:
        generic = build(grade_level="Grade 10", subject="Physics",
                        syllabus_board="Generic", audience_role="student")
        cbse = build(grade_level="Grade 10", subject="Physics",
                     syllabus_board="CBSE", audience_role="student")
        ib = build(grade_level="Grade 10", subject="Physics",
                   syllabus_board="IB", audience_role="student")

        assert generic != cbse, f"{build.__name__}: CBSE == Generic"
        assert generic != ib, f"{build.__name__}: IB == Generic"
        assert cbse != ib, f"{build.__name__}: CBSE == IB"
        assert "NCERT" in cbse, f"{build.__name__}: CBSE missing NCERT anchor"
        assert "IB" in ib, f"{build.__name__}: IB prompt missing IB anchor"


def test_teacher_cpd_register_surfaces():
    """Teacher CPD audiences should get pedagogy-centred guidance, not
    remedial instruction cues."""
    for build in BUILDERS:
        prompt = build(grade_level="Teacher CPD", subject="Biology",
                       syllabus_board="Generic", audience_role="teacher")
        lower = prompt.lower()
        assert "pedagogy" in lower, f"{build.__name__}: CPD missing pedagogy guidance"


def test_subject_guidance_varies():
    """Physics and History guidance should land in the prompt differently."""
    for build in BUILDERS:
        physics = build(grade_level="Grade 11", subject="Physics",
                        syllabus_board="Generic", audience_role="student")
        history = build(grade_level="Grade 11", subject="History",
                        syllabus_board="Generic", audience_role="student")
        assert physics != history
        assert "SI units" in physics, f"{build.__name__}: Physics missing SI-units cue"


def test_defaults_do_not_raise_and_are_non_empty():
    """Zero-arg calls preserve legacy behavior — critical for existing flows
    that don't pass the new wizard fields."""
    for build in BUILDERS:
        out = build()
        assert isinstance(out, str) and len(out) > 200


def test_actions_prompt_does_not_advertise_pause_action_type():
    """F7 follow-up: the LLM director prompt must not document, demonstrate, or
    recommend the `pause` action type. The frontend playback engine no-ops
    `{type: "pause", ...}` actions today (see frontend/src/lib/maicActionEngine.ts
    `executePause`). Keeping the directive in the prompt invites the model to
    keep emitting wasted actions and bloats stored classroom JSON.

    Asserts the assembled actions prompt contains no:
      * `"type": "pause"` example object literal
      * a numbered/bulleted action-schema entry of the form `pause —` or
        `pause:` describing it as a valid action type
      * any `{"type":"pause"...}` snippet inside narrative directive text
    Allows incidental uses of the english word "pause" (e.g. a persona
    `speakingStyle` like "warm, unhurried, pauses to check understanding"),
    which is voice direction, not an action-type directive.
    """
    import re

    for build in BUILDERS:
        prompt = build(grade_level="Grade 10", subject="Physics",
                       syllabus_board="Generic", audience_role="student")
        # Forbidden: example literal in JSON shape
        assert '"type": "pause"' not in prompt, (
            f"{build.__name__}: prompt still emits a `\"type\": \"pause\"` example. "
            f"Snippet: …{prompt[max(0, prompt.find('pause') - 60):prompt.find('pause') + 80]}…"
        )
        assert '"type":"pause"' not in prompt, (
            f"{build.__name__}: prompt still emits a `\"type\":\"pause\"` example."
        )
        # Forbidden: schema-entry style description (e.g. "4. pause — Dramatic …"
        # or "- pause: …"). Match action-list/bullet contexts only, not prose.
        schema_entry = re.search(
            r"(?im)^\s*(?:\d+\.|[-*])\s*pause\b\s*[—\-:]",
            prompt,
        )
        assert schema_entry is None, (
            f"{build.__name__}: prompt still describes `pause` in the action-type "
            f"schema list. Match: {schema_entry.group(0)!r}"
        )


def test_scene_content_prompt_advertises_body_image_right_template():
    """F4: the scene-content system prompt must mention `body-image-right` as a
    template option so the LLM knows the typed slot-based shape is allowed.

    Asserts the prompt string includes both:
      * the template literal `body-image-right` (the only allowed value
        in the smallest-first-cut), AND
      * a reference to the `slots` field shape so the model knows what to
        emit alongside the legacy `elements[]` array.

    Backwards compat: legacy free-form slides without a `template` keep
    rendering exactly as today — the prompt must NOT make `template`
    mandatory. The check below asserts the directive is described as
    optional.
    """
    prompt = build_scene_content_system_prompt(
        grade_level="Grade 10", subject="Physics",
        syllabus_board="Generic", audience_role="student",
    )
    assert "body-image-right" in prompt, (
        "scene-content prompt missing `body-image-right` template advertisement"
    )
    assert "slots" in prompt, (
        "scene-content prompt missing `slots` field reference"
    )
    # Optional, NOT mandatory — make sure the prompt frames the new
    # fields as additive (e.g. uses MAY / OPTIONAL / OPTIONAL TYPED).
    lower = prompt.lower()
    assert any(token in lower for token in ("optional", "may emit", "you may")), (
        "scene-content prompt makes typed-slot emission sound mandatory; "
        "it must stay additive so legacy free-form slides keep working"
    )
