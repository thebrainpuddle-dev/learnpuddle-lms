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

import asyncio
import logging
import secrets
from typing import Any

from apps.maic.exceptions import MaicProtocolError
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
                **(
                    {"pblSessionId": content["pblSessionId"]}
                    if content.get("pblSessionId")
                    else {}
                ),
                **(
                    {"pblWsPath": content["pblWsPath"]}
                    if content.get("pblWsPath")
                    else {}
                ),
            },
        }

    _logger.warning(
        "build_complete_scene: no matching branch for type=%r (content keys: %s)",
        scene_type,
        list(content.keys()),
    )
    return None


# ── Media resolution (Phase 9, MAIC-915) ──────────────────────────


async def resolve_scene_media(
    scene: dict[str, Any] | None,
    outline: SceneOutline,
    tenant_config: Any | None,
) -> dict[str, Any] | None:
    """Resolve `gen_img_<id>` and `gen_vid_<id>` placeholders in a
    built slide scene by dispatching the media orchestrator (Phase 9).

    Walks every element in the slide canvas. For each element whose
    ``src`` starts with ``gen_img_`` or ``gen_vid_``, looks up the
    matching prompt from ``outline.mediaGenerations`` and asks the
    orchestrator for a real provider-generated asset. The placeholder
    ``src`` is replaced in place with the resolved URL.

    Discipline:
      - **scene type != "slide"** → return unchanged (no media in quiz/PBL/interactive)
      - **tenant_config is None** → return unchanged (caller opted out / no tenant context)
      - **placeholder has no matching mediaGenerations entry with a prompt**
        → raise ``MaicProtocolError`` (Chunk 2 closeout — audit Section B.1).
        This is a data-integrity violation: the LLM emitted an element
        referencing ``gen_img_X`` while the matching ``mediaGenerations``
        entry is absent or its ``prompt`` is empty. Failing loud at
        build time drops the bad scene at ``_run_one``'s exception
        boundary in scene_generator.py and surfaces the error to the
        teacher via ``on_error``, which is better than silently
        persisting a scene that will render "Image unavailable".
      - **orchestrator raises (MaicConfigError, MaicProviderError, etc)**
        → preserve placeholder, log warning, continue with other
        elements. One bad image must NEVER fail the whole scene.
        Provider failures are transient and Celery can retry; data-
        integrity violations are not transient and must not retry.
      - All image + video tasks for a scene run in parallel via
        ``asyncio.gather`` — the orchestrator's own bounded-retry +
        timeout protects against any single hang.

    Returns:
        The (possibly-mutated) scene dict, OR None if the input scene
        was None.
    """
    if scene is None:
        return None
    if scene.get("type") != "slide":
        return scene
    if tenant_config is None:
        return scene

    canvas = scene.get("content", {}).get("canvas", {})
    elements = canvas.get("elements") or []
    if not elements:
        return scene

    # Build prompt lookup keyed by elementId
    media_gens = outline.get("mediaGenerations") or []
    prompts_by_id: dict[str, dict[str, Any]] = {}
    for mg in media_gens:
        if not isinstance(mg, dict):
            continue
        elem_id = mg.get("elementId")
        if isinstance(elem_id, str):
            prompts_by_id[elem_id] = mg

    # Identify placeholder elements + collect unresolvable ones for the
    # strict pre-flight check (Chunk 2 closeout, audit Section B.1).
    image_tasks: list[tuple[int, str, str]] = []  # (idx, placeholder, prompt)
    video_tasks: list[tuple[int, str, str]] = []
    unresolvable: list[str] = []  # element srcs with no resolvable prompt
    for idx, elem in enumerate(elements):
        if not isinstance(elem, dict):
            continue
        src = elem.get("src")
        if not isinstance(src, str) or not src:
            continue
        if src.startswith("gen_img_"):
            mg = prompts_by_id.get(src)
            prompt = (mg or {}).get("prompt")
            if isinstance(prompt, str) and prompt:
                image_tasks.append((idx, src, prompt))
            else:
                unresolvable.append(src)
        elif src.startswith("gen_vid_"):
            mg = prompts_by_id.get(src)
            prompt = (mg or {}).get("prompt")
            if isinstance(prompt, str) and prompt:
                video_tasks.append((idx, src, prompt))
            else:
                unresolvable.append(src)

    if unresolvable:
        # Data-integrity violation — the scene_generator emitted slide
        # elements referencing placeholders without matching prompts.
        # Raise so scene_generator._run_one's exception boundary drops
        # the scene and the teacher sees a generation error (instead of
        # a silently-broken "Image unavailable" classroom). Mirrors the
        # audit's stated fix in _coordination/inbox/reviewer/
        # AI-CLASSROOM-PARITY-AUDIT-2026-05-16.md Section B.1.
        raise MaicProtocolError(
            "unresolvable media placeholder(s) in scene "
            f"{scene.get('id', '?')!r}: {sorted(set(unresolvable))} — "
            "element src references a gen_img_*/gen_vid_* placeholder "
            "but the matching mediaGenerations entry is missing or has "
            "no prompt. This is an LLM-output integrity violation; "
            "regenerate this scene rather than ship it with broken refs."
        )

    if not image_tasks and not video_tasks:
        return scene

    scene_id: str = scene.get("id", "") or ""

    # Lazy import — adapters/orchestrator module side-effect-registers
    # provider adapters at import time. Lazy here so test-only fake
    # adapters can be registered BEFORE this function imports the
    # orchestrator module (mirrors apps/maic/tts/service.py pattern).
    from apps.maic.media import adapters  # noqa: F401
    from apps.maic.media.orchestrator import generate_image, generate_video
    from apps.maic.media.types import (
        ImageGenerationRequest,
        VideoGenerationRequest,
    )

    async def _resolve_image(
        idx: int, placeholder: str, prompt: str,
    ) -> tuple[int, str, str | None]:
        try:
            req = ImageGenerationRequest(
                prompt=prompt,
                tenant_id=str(getattr(tenant_config, "tenant_id", "")),
                scene_id=scene_id or None,
            )
            result = await generate_image(req, tenant_config)
            return (idx, placeholder, result.url)
        except Exception as exc:  # noqa: BLE001 — boundary; preserve placeholder
            _logger.warning(
                "resolve_scene_media: image gen failed for %s (scene=%s): %s",
                placeholder, scene_id, exc,
            )
            return (idx, placeholder, None)

    async def _resolve_video(
        idx: int, placeholder: str, prompt: str,
    ) -> tuple[int, str, str | None]:
        try:
            req = VideoGenerationRequest(
                prompt=prompt,
                tenant_id=str(getattr(tenant_config, "tenant_id", "")),
                scene_id=scene_id or None,
            )
            result = await generate_video(req, tenant_config)
            return (idx, placeholder, result.url)
        except Exception as exc:  # noqa: BLE001
            _logger.warning(
                "resolve_scene_media: video gen failed for %s (scene=%s): %s",
                placeholder, scene_id, exc,
            )
            return (idx, placeholder, None)

    all_results = await asyncio.gather(
        *[_resolve_image(*t) for t in image_tasks],
        *[_resolve_video(*t) for t in video_tasks],
    )

    # Apply resolved URLs in place. Failures (url is None) leave the
    # placeholder src — frontend sees `gen_img_<id>` and shows a skeleton.
    for idx, _placeholder, url in all_results:
        if url:
            elements[idx]["src"] = url

    return scene


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
