"""Tests for `apps.maic.generation.prompt_loader` (MAIC-429.0).

The wrapper is thin — most behavior comes from the underlying
`apps.maic.prompts.loader`. These tests verify:
    1. The wrapper fails loudly (MaicConfigError) when the underlying
       loader returns None — generation must NOT silently proceed
       with a missing template.
    2. The GENERATION_TEMPLATE_IDS list is the canonical "what we
       need" — used by the closure-doc validation gate.
    3. `list_missing_generation_templates` correctly enumerates
       what's not yet on disk (a diagnostic; expected to return a
       partial list during Sessions 3-5 and [] at Phase 4 close).
"""
from __future__ import annotations

import pytest

from apps.maic.exceptions import MaicConfigError
from apps.maic.generation.prompt_loader import (
    GENERATION_TEMPLATE_IDS,
    list_missing_generation_templates,
    load_generation_prompt,
)


# ── Wrapper failure semantics ─────────────────────────────────────


def test_load_generation_prompt_raises_on_missing_template():
    """Generation cannot proceed without a fully-loaded prompt.
    The wrapper MUST raise — silent None would surface as an empty-
    string LLM call later."""
    with pytest.raises(MaicConfigError, match="not found"):
        load_generation_prompt("definitely-does-not-exist-xyz")


def test_load_generation_prompt_error_includes_expected_path():
    """The error message must point a developer at the directory
    they need to create. ADR-001a's "direct copy from upstream"
    workflow assumes this path."""
    try:
        load_generation_prompt("nonexistent-template")
    except MaicConfigError as e:
        msg = str(e)
        assert "apps/maic/prompts/templates/nonexistent-template/system.md" in msg
    else:
        pytest.fail("Expected MaicConfigError")


def test_load_generation_prompt_works_for_existing_template():
    """`agent-system` was ported in Phase 1 + has snippets fully
    resolved. Verify the wrapper returns a BuiltPrompt with the
    expected shape (proves the wrapper isn't silently broken)."""
    # Provide the variables agent-system uses; missing ones leave
    # `{{var}}` literals in place which is OK for this shape check.
    built = load_generation_prompt(
        "agent-system",
        variables={
            "agentName": "Test",
            "persona": "p",
            "roleGuideline": "r",
            "studentProfileSection": "",
            "peerContext": "",
            "languageConstraint": "",
            "formatExample": "",
            "orderingPrinciples": "",
            "spotlightExamples": "",
            "actionDescriptions": "",
            "slideActionGuidelines": "",
            "mutualExclusionNote": "",
            "stateContext": "",
            "virtualWhiteboardContext": "",
            "lengthGuidelines": "",
            "whiteboardGuidelines": "",
            "discussionContextSection": "",
        },
    )
    assert built is not None
    assert isinstance(built.system, str)
    assert isinstance(built.user, str)
    # Sanity: name interpolation worked
    assert "Test" in built.system or "Test" in built.user


# ── GENERATION_TEMPLATE_IDS lock ──────────────────────────────────


def test_generation_template_ids_lockset():
    """Lock the list of template ids the generation pipeline needs.
    Updates to this set are intentional + must be reviewed (each new
    id implies a new template + a new scene-type or stage port)."""
    expected = {
        # Stage 1
        "requirements-to-outlines",
        # Stage 2 — content
        "slide-content",
        "quiz-content",
        "pbl-content",
        "simulation-content",
        "diagram-content",
        "code-content",
        "game-content",
        "visualization3d-content",
        # Stage 2 — actions
        "slide-actions",
        "quiz-actions",
        "pbl-actions",
        "interactive-actions",
        # Optional
        "widget-teacher-actions",
    }
    actual = set(GENERATION_TEMPLATE_IDS)
    assert actual == expected, (
        f"GENERATION_TEMPLATE_IDS drift — "
        f"missing={expected - actual}, extra={actual - expected}"
    )


def test_generation_template_ids_count_is_fourteen():
    """Sanity: 9 content + 4 actions + 1 widget-teacher = 14."""
    assert len(GENERATION_TEMPLATE_IDS) == 14


# ── Diagnostic: which templates are missing ──────────────────────


def test_list_missing_returns_a_list():
    """The diagnostic returns a list (never None / never raises).
    During Sessions 3-5 this list will shrink; at Phase 4 close it
    must be empty (asserted in the closure validation suite)."""
    missing = list_missing_generation_templates()
    assert isinstance(missing, list)


def test_list_missing_contains_only_known_ids():
    """Sanity: missing template ids must be drawn from the canonical
    set — no stray ids leak into the diagnostic."""
    missing = list_missing_generation_templates()
    canonical = set(GENERATION_TEMPLATE_IDS)
    for tid in missing:
        assert tid in canonical, f"unknown template id in missing list: {tid}"


def test_list_missing_at_maic_429_0_is_only_pbl_content():
    """MAIC-429.0 ground truth: 13 of the 14 generation templates were
    already ported during Phase 1-3 prep work (they live alongside
    `agent-system`, `director`, etc. in the templates directory).

    Only `pbl-content` is missing. Per MAIC-432's research decision,
    `pbl-content` ships as a STUB at MAIC-422.4 (Session 4) — the real
    agentic-MCP loop is deferred to Phase 5+.

    When MAIC-422.4 lands the stub template, this test flips to
    `assert missing == []`."""
    missing = list_missing_generation_templates()
    assert missing == ["pbl-content"], (
        f"unexpected missing-templates set: {missing}. "
        "If MAIC-422.4 has shipped pbl-content, update this test to "
        "expect an empty list."
    )
