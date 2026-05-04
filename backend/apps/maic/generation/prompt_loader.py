"""Generation-pipeline wrapper around `apps.maic.prompts.loader`.

The Phase 1 loader (`apps.maic.prompts.loader`) returns `None` when a
template directory or its `system.md` is missing — that's the right
behavior for the playback engine, where a missing prompt-builder
fragment can fall back to a default.

Generation is different. If `requirements-to-outlines/system.md` is
missing on disk, we cannot produce an outline at all; silently
returning `None` would surface as a confusing empty-string LLM call
two layers later. This wrapper raises `MaicConfigError` on the
None case so generation fails loudly + early.

The underlying template language is unchanged — same snippet
includes (`{{snippet:name}}`), same conditional blocks
(`{{#if flag}}...{{/if}}`), same variable interpolation
(`{{varName}}`). See the Phase 1 loader's docstring for full
language reference.

Source convention:
    Per ADR-001a, the upstream templates at
    `/Volumes/CrucialX9/OpenMAIC/lib/prompts/templates/` are direct-
    copied into `apps/maic/prompts/templates/` as each scene-type
    chunk in Sessions 3-5 needs them.

Used by:
    - apps.maic.generation.outline_generator (MAIC-421)
    - apps.maic.generation.scene_generator (MAIC-422.x)
"""
from __future__ import annotations

from typing import Any

from apps.maic.exceptions import MaicConfigError
from apps.maic.prompts.loader import (
    BuiltPrompt,
    build_prompt,
    list_available_prompts,
)


# ── Generation pipeline template IDs ──────────────────────────────


# Locked at MAIC-429.0 — the canonical list of templates the
# generation pipeline depends on. As each scene-type chunk ports its
# template, the entry is uncommented here and the test below stops
# skipping it. This gives us a single source of truth for "what
# templates does the generation pipeline need?".
GENERATION_TEMPLATE_IDS: tuple[str, ...] = (
    # Stage 1 — outline generator (MAIC-421)
    "requirements-to-outlines",
    # Stage 2 — scene-type content (MAIC-422.x)
    "slide-content",
    "quiz-content",
    "pbl-content",  # MAIC-422.4 — STUB per MAIC-432 research
    "simulation-content",
    "diagram-content",
    "code-content",
    "game-content",
    "visualization3d-content",
    # Stage 2 — scene-type actions (MAIC-422.x)
    "slide-actions",
    "quiz-actions",
    "pbl-actions",  # STUB
    "interactive-actions",
    # Optional widget teacher actions (MAIC-422.7)
    "widget-teacher-actions",
)


# ── Public API ────────────────────────────────────────────────────


def load_generation_prompt(
    template_id: str,
    variables: dict[str, Any] | None = None,
) -> BuiltPrompt:
    """Load a generation-pipeline prompt and fail loudly if missing.

    Wraps `apps.maic.prompts.loader.build_prompt` with a different
    error contract:

      Phase-1 loader: returns None on missing template (caller
        decides whether to fall back).
      This wrapper: raises MaicConfigError. Generation cannot proceed
        without a fully-loaded prompt.

    Args:
        template_id: kebab-case template id (e.g. `slide-content`).
            Must correspond to `apps/maic/prompts/templates/<id>/system.md`.
        variables: dict of placeholder values for `{{var}}` and
            `{{#if flag}}` substitution. Defaults to {}.

    Returns:
        BuiltPrompt(system, user) — both fully interpolated.

    Raises:
        MaicConfigError: template directory or system.md is missing.
    """
    if variables is None:
        variables = {}

    built = build_prompt(template_id, variables)
    if built is None:
        raise MaicConfigError(
            f"generation template not found: {template_id!r}. "
            f"Expected at apps/maic/prompts/templates/{template_id}/system.md. "
            f"Available templates: {', '.join(list_available_prompts()) or '(none)'}"
        )
    return built


def list_missing_generation_templates() -> list[str]:
    """Diagnostic: which generation templates are NOT yet on disk?

    Used in tests + closure-doc validation. Returns a list of
    template ids that `apps/maic/prompts/templates/` doesn't contain
    yet. As Sessions 3-5 land each port, this list shrinks.

    At Phase 4 close, this MUST return [] — every entry in
    `GENERATION_TEMPLATE_IDS` must have shipped.
    """
    available = set(list_available_prompts())
    return [tid for tid in GENERATION_TEMPLATE_IDS if tid not in available]
