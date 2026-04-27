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
