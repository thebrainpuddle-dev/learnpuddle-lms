"""Standalone scene building and element normalization.

Direct port of upstream `lib/generation/scene-builder.ts` (234 lines).

Source:
    https://github.com/THU-MAIC/OpenMAIC/blob/main/lib/generation/scene-builder.ts
    /Volumes/CrucialX9/OpenMAIC/lib/generation/scene-builder.ts

Two functions ported in Phase 4 / MAIC-423:
  - uniquify_media_element_ids(outlines) — replaces sequential
    `gen_img_N` / `gen_vid_N` IDs with globally unique nanoid-style
    IDs to prevent thumbnail contamination across courses.
  - build_complete_scene(outline, content, actions, stage_id) —
    assembles a Scene dict from outline + content + actions.
    Handles slide / quiz / interactive / pbl variants.

NOT ported in Phase 4:
  - build_scene_from_outline — SSE streaming variant that calls
    scene_generator. Phase 4 uses the Celery orchestrator path
    (Session 6 MAIC-428) which calls scene_generator directly +
    build_complete_scene. The SSE path can be re-added in Phase 5+
    if needed.

Used by:
    - apps.maic.generation.scene_generator (MAIC-422.x — generate_full_scenes
      assembles each scene's final dict via build_complete_scene)
    - apps.maic.generation.outline_generator (MAIC-421 — its no-op
      `_uniquify_media_element_ids` is now replaced by the real
      function from this module)
"""
from __future__ import annotations

import logging
import secrets
from typing import Any

from apps.maic.generation.types import SceneOutline


_logger = logging.getLogger("apps.maic.generation.scene_builder")


# ── uniquify_media_element_ids ────────────────────────────────────


def uniquify_media_element_ids(
    outlines: list[SceneOutline],
) -> list[SceneOutline]:
    """Replace sequential `gen_img_N` / `gen_vid_N` IDs in outlines
    with globally unique IDs.

    Mirrors upstream `uniquifyMediaElementIds`. The LLM generates
    sequential placeholder IDs (gen_img_1, gen_img_2, ...) which are
    only unique within a single course. Since the media store keys
    by elementId WITHOUT stage scoping, identical IDs across
    different courses cause thumbnail contamination on the homepage.
    nanoid-based IDs ensure global uniqueness.

    Two-pass implementation:
      1. Collect every sequential ID seen across all outlines'
         `mediaGenerations` arrays and assign each a unique
         replacement (so duplicate references within an outline
         resolve to the same new ID).
      2. Rewrite each outline's mediaGenerations entries with the
         replacement IDs.

    Returns the original list (unchanged) when no media IDs are seen
    — saves an unnecessary copy in the (very common) Phase 4 case
    where image generation isn't enabled.
    """
    id_map: dict[str, str] = {}

    # First pass: collect all sequential media IDs.
    for outline in outlines:
        media_generations = outline.get("mediaGenerations")
        if not media_generations:
            continue
        for mg in media_generations:
            element_id = mg.get("elementId")
            if not element_id or element_id in id_map:
                continue
            prefix = "gen_vid_" if mg.get("type") == "video" else "gen_img_"
            id_map[element_id] = f"{prefix}{_nanoid_8()}"

    if not id_map:
        return outlines

    # Second pass: replace IDs in mediaGenerations.
    rewritten: list[SceneOutline] = []
    for outline in outlines:
        media_generations = outline.get("mediaGenerations")
        if not media_generations:
            rewritten.append(outline)
            continue
        new_outline: dict[str, Any] = {**outline}
        new_outline["mediaGenerations"] = [
            {**mg, "elementId": id_map.get(mg.get("elementId"), mg.get("elementId"))}
            for mg in media_generations
        ]
        rewritten.append(new_outline)  # type: ignore[arg-type]
    return rewritten


# ── build_complete_scene ──────────────────────────────────────────


# Default slide theme — mirrors upstream `defaultTheme` in
# scene-builder.ts:143-149. Frozen here so any future tweak is a
# reviewable diff against this single constant.
DEFAULT_SLIDE_THEME: dict[str, Any] = {
    "backgroundColor": "#ffffff",
    "themeColors": ["#5b9bd5", "#ed7d31", "#a5a5a5", "#ffc000", "#4472c4"],
    "fontColor": "#333333",
    "fontName": "Microsoft YaHei",
    "outline": {"color": "#d14424", "width": 2, "style": "solid"},
    "shadow": {"h": 0, "v": 0, "blur": 10, "color": "#000000"},
}


def build_complete_scene(
    outline: SceneOutline,
    content: dict[str, Any],
    actions: list[dict[str, Any]],
    stage_id: str,
) -> dict[str, Any] | None:
    """Build a complete Scene dict from outline + content + actions.

    Mirrors upstream `buildCompleteScene`. Returns None when the
    outline.type doesn't match any expected branch (defensive — the
    caller should have run apply_outline_fallbacks first).

    Branches (one per scene type):
      - slide: wraps content.elements + content.background into a
        Slide dict, attaches DEFAULT_SLIDE_THEME, returns the Scene.
      - quiz: wraps content.questions into a quiz Scene.
      - interactive: wraps content.html (+ widget fields if present)
        into an interactive Scene.
      - pbl: wraps content.projectConfig into a pbl Scene.

    Each branch attaches the Scene-level metadata: id, stageId, type,
    title, order, actions, createdAt, updatedAt.
    """
    scene_id = _generate_scene_id()
    now = _utc_now_ms()

    base_scene: dict[str, Any] = {
        "id": scene_id,
        "stageId": stage_id,
        "title": outline.get("title", ""),
        "order": outline.get("order", 0),
        "actions": actions,
        "createdAt": now,
        "updatedAt": now,
    }

    scene_type = outline.get("type")

    if scene_type == "slide" and "elements" in content:
        slide: dict[str, Any] = {
            "id": _generate_scene_id(),
            "viewportSize": 1000,
            "viewportRatio": 0.5625,
            "theme": DEFAULT_SLIDE_THEME,
            "elements": content["elements"],
            "background": content.get("background"),
        }
        return {
            **base_scene,
            "type": "slide",
            "content": {
                "type": "slide",
                "canvas": slide,
            },
        }

    if scene_type == "quiz" and "questions" in content:
        return {
            **base_scene,
            "type": "quiz",
            "content": {
                "type": "quiz",
                "questions": content["questions"],
            },
        }

    if scene_type == "interactive" and "html" in content:
        return {
            **base_scene,
            "type": "interactive",
            "content": {
                "type": "interactive",
                "url": "",
                "html": content["html"],
                # Ultra Mode widget fields (optional)
                "widgetType": content.get("widgetType"),
                "widgetConfig": content.get("widgetConfig"),
                "teacherActions": content.get("teacherActions"),
            },
        }

    if scene_type == "pbl" and "projectConfig" in content:
        return {
            **base_scene,
            "type": "pbl",
            "content": {
                "type": "pbl",
                "projectConfig": content["projectConfig"],
            },
        }

    _logger.warning(
        "build_complete_scene: no matching branch for type=%r (content keys: %s)",
        scene_type,
        list(content.keys()),
    )
    return None


# ── Internal helpers ──────────────────────────────────────────────


def _nanoid_8() -> str:
    """8-char URL-safe ID — equivalent to upstream's `nanoid(8)`."""
    raw = secrets.token_urlsafe(6).replace("-", "").replace("_", "")[:8]
    if len(raw) < 8:
        raw = (raw + secrets.token_urlsafe(4))[:8]
    return raw


def _generate_scene_id() -> str:
    """12-char URL-safe ID — equivalent to upstream's `nanoid()` default."""
    raw = secrets.token_urlsafe(9).replace("-", "").replace("_", "")[:12]
    if len(raw) < 12:
        raw = (raw + secrets.token_urlsafe(8))[:12]
    return raw


def _utc_now_ms() -> int:
    """Current UTC time as integer milliseconds since epoch.
    Mirrors upstream `Date.now()`."""
    import time

    return int(time.time() * 1000)
