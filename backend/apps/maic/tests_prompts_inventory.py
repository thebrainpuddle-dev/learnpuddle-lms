"""Smoke + inventory tests for the ported prompt templates.

These tests verify the templates and snippets that were ported VERBATIM
from upstream OpenMAIC actually exist on disk and load through the
prompt loader. They catch:

  - Missing template directories (would silently fall back to None at
    runtime; we'd rather catch at CI time)
  - Missing system.md within a template directory
  - Snippet inclusions that reference a snippet not present on disk
    (raises MaicConfigError on load_prompt — we surface that here too)

These tests do NOT exercise variable interpolation or conditional
behavior — those are covered in tests_prompts_loader.py.
"""
from __future__ import annotations

import pytest

from apps.maic.exceptions import MaicConfigError
from apps.maic.prompts import (
    list_available_prompts,
    list_available_snippets,
    load_prompt,
)


# ── Expected inventory (lock-set) ─────────────────────────────────────


# Mirror of /Volumes/CrucialX9/OpenMAIC/lib/prompts/templates/, plus
# the local-only `pbl-content` STUB added at MAIC-422.4 so the
# generation prompt-loader diagnostic returns [] at Phase 4 close. The
# real upstream PBL content generator (lib/pbl/generate-pbl.ts) is an
# agentic-MCP loop deferred to Phase 5+ per MAIC-432 research; the stub
# template is a doc-only placeholder (no LLM call hits it).
EXPECTED_TEMPLATES = frozenset({
    "agent-system",
    "agent-system-wb-assistant",
    "agent-system-wb-student",
    "agent-system-wb-teacher",
    "code-content",
    "diagram-content",
    "director",
    "game-content",
    "interactive-actions",
    "interactive-outlines",
    "pbl-actions",
    "pbl-content",  # MAIC-422.4 STUB (Phase 4)
    "pbl-design",
    "quiz-actions",
    "quiz-content",
    "requirements-to-outlines",
    "simulation-content",
    "slide-actions",
    "slide-content",
    "visualization3d-content",
    "web-search-query-rewrite",
    "widget-teacher-actions",
})


def test_all_22_templates_present():
    """The full template-set mirrors upstream exactly. If you add or
    remove a template, update this set and the SOURCES.txt manifest."""
    actual = set(list_available_prompts())
    missing = EXPECTED_TEMPLATES - actual
    extra = actual - EXPECTED_TEMPLATES
    assert not missing, f"missing templates: {sorted(missing)}"
    assert not extra, (
        f"unexpected templates (update EXPECTED_TEMPLATES + SOURCES.txt): {sorted(extra)}"
    )


@pytest.mark.parametrize("prompt_id", sorted(EXPECTED_TEMPLATES))
def test_each_template_loads_without_error(prompt_id):
    """Every template's `system.md` is required and its snippet
    inclusions resolve. A MaicConfigError here is a real bug — either
    the template references a snippet not yet ported, or there's a typo."""
    try:
        loaded = load_prompt(prompt_id)
    except MaicConfigError as exc:
        pytest.fail(f"{prompt_id} system.md references a missing snippet: {exc}")
    assert loaded is not None, f"{prompt_id} failed to load"
    assert loaded.systemPrompt, f"{prompt_id} system.md is empty"


def test_agent_system_is_substantive():
    """agent-system is the workhorse — used by every agent. Sanity check
    its rendered length so a regressed/empty file is caught immediately."""
    loaded = load_prompt("agent-system")
    assert loaded is not None
    # Upstream agent-system/system.md is ~3 KB minimum; allow generous slack.
    assert len(loaded.systemPrompt) > 500, (
        f"agent-system seems suspiciously short ({len(loaded.systemPrompt)} chars)"
    )


# ── Snippet inventory (set in MAIC-205) ───────────────────────────────


# Will be populated and locked by MAIC-205 once snippet files are copied.
EXPECTED_SNIPPETS = frozenset({
    "action-types",
    "element-types",
    "image-instructions",
    "json-output-rules",
    "media-safety-guidelines",
    "slide-generated-image-instructions",
    "slide-image-instructions",
    "slide-video-instructions",
    "speech-guidelines",
    "video-instructions",
    "whiteboard-reference",
})


@pytest.mark.skipif(
    not list_available_snippets(),
    reason="MAIC-205 not yet shipped — snippets directory empty",
)
def test_all_11_snippets_present():
    actual = set(list_available_snippets())
    missing = EXPECTED_SNIPPETS - actual
    assert not missing, f"missing snippets: {sorted(missing)}"
