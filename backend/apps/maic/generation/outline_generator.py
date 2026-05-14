"""Stage 1: Generate scene outlines from user requirements.

Direct port of upstream `lib/generation/outline-generator.ts` (195 lines).

Source:
    https://github.com/THU-MAIC/OpenMAIC/blob/main/lib/generation/outline-generator.ts
    /Volumes/CrucialX9/OpenMAIC/lib/generation/outline-generator.ts

Stage 1 of the generation pipeline: ONE LLM call → all scene outlines.
The LLM receives the user requirement text + (optionally) PDF context,
and returns a JSON object containing a language directive + an
ordered list of scene outlines (one per scene-to-be-generated).

Phase 4 simplifications (deferred to Phase 5+):
    - PDF text + image plumbing (`pdfText`, `pdfImages`, `imageMapping`)
      → not supported. Phase 4 generates from the requirement text only.
    - Vision images → DEFERRED. The prompt receives "No images available".
    - Image / video generation flags → defaults to False.
    - `uniquifyMediaElementIds` (from scene_builder) → no-op passthrough.
      Phase 4 outlines have no media elements to uniquify; the call
      site is preserved for forward compatibility with Phase 5+.

Used by:
    - apps.maic.generation.pipeline_runner (MAIC-420)
"""
from __future__ import annotations

import logging
import secrets
from typing import Any, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage

from apps.maic.exceptions import MaicConfigError
from apps.maic.generation.json_repair import parse_json_response
from apps.maic.generation.prompt_loader import load_generation_prompt
from apps.maic.generation.types import (
    GenerationCallbacks,
    GenerationProgress,
    GenerationResult,
    SceneOutline,
)
from apps.maic.orchestration.ai_adapter import generate_text


_logger = logging.getLogger("apps.maic.generation.outline_generator")


# ── Constants ──────────────────────────────────────────────────────


# Mirrors upstream `lib/constants/generation.MAX_PDF_CONTENT_CHARS`.
# Truncation cap when the LLM context window is precious. PDF support
# is DEFERRED to Phase 5+; this constant is preserved for the call
# site to stay structurally identical.
_MAX_PDF_CONTENT_CHARS: int = 50_000

# Used when the outline stage fails to produce an explicit directive
# (LLM schema regression, empty response, upstream error). Downstream
# prompts still need *something* that steers the model toward the
# requirement's language rather than defaulting to the training-
# distribution prior.
DEFAULT_LANGUAGE_DIRECTIVE = "Teach in the language that matches the user requirement."
_OUTLINE_MIN_MAX_TOKENS = 2048
_OUTLINE_MAX_MAX_TOKENS = 8192
_OUTLINE_BASE_TOKENS = 1200
_OUTLINE_TOKENS_PER_SCENE = 450


# ── User requirements TypedDict ───────────────────────────────────


class UserRequirements(TypedDict, total=False):
    """Simplified requirements payload for Stage 1.

    Mirrors upstream's `UserRequirements` (lib/types/generation). The
    Phase 4 port supports the simplified shape (requirement + language);
    the richer fields (pdfText, etc.) are accepted as keys but
    DEFERRED in implementation.
    """

    requirement: str
    language: str
    userNickname: str
    userBio: str


# ── Public API ────────────────────────────────────────────────────


async def generate_scene_outlines_from_requirements(
    requirements: UserRequirements,
    pdf_text: str | None = None,
    pdf_images: list[dict] | None = None,
    *,
    language_model_id: str = "stub",
    callbacks: GenerationCallbacks | None = None,
    options: dict[str, Any] | None = None,
) -> GenerationResult:
    """Generate scene outlines from user requirements.

    Mirrors upstream `generateSceneOutlinesFromRequirements`. Returns
    a `GenerationResult{success, data, error}` where `data` is
    `{"languageDirective": str, "outlines": list[SceneOutline]}` on
    success.

    Args:
        requirements: simplified UserRequirements (requirement +
            language + optional userNickname/userBio).
        pdf_text: DEFERRED (Phase 5+). Currently ignored.
        pdf_images: DEFERRED (Phase 5+). Currently ignored.
        language_model_id: provider id for the LLM call (stub /
            stub-director / claude-... / gpt-... / openrouter/...).
            Generation defaults to deterministic stub for tests.
        callbacks: optional progress/error callbacks.
        options: forward-compat dict for Phase 5+ flags (image_*,
            video_*, vision_enabled, image_mapping, research_context,
            teacher_context). Phase 4 reads only `teacher_context` if
            present; the rest are accepted but unused.

    Returns:
        `{"success": True, "data": {"languageDirective", "outlines"}}` or
        `{"success": False, "error": str}`.
    """
    options = options or {}

    # Phase 4 defaults — most of these are DEFERRED to Phase 5+.
    available_images_text = "No images available"
    image_enabled = bool(options.get("image_generation_enabled", False))
    video_enabled = bool(options.get("video_generation_enabled", False))
    media_enabled = image_enabled or video_enabled
    has_source_images = bool(pdf_images and len(pdf_images) > 0)
    target_scene_count = _target_scene_count(requirements, options)

    # User profile string (per upstream lines 81-84).
    user_profile_text = ""
    user_nickname = requirements.get("userNickname")
    user_bio = requirements.get("userBio")
    if user_nickname or user_bio:
        bio_part = f" — {user_bio}" if user_bio else ""
        user_profile_text = (
            f"## Student Profile\n\n"
            f"Student: {user_nickname or 'Unknown'}{bio_part}\n\n"
            f"Consider this student's background when designing the "
            f"course. Adapt difficulty, examples, and teaching approach "
            f"accordingly.\n\n---"
        )

    # Build the prompt via the generation loader (raises MaicConfigError
    # if the template is missing — generation can't proceed without it).
    try:
        prompts = load_generation_prompt(
            "requirements-to-outlines",
            {
                "requirement": requirements.get("requirement", ""),
                "pdfContent": (
                    pdf_text[:_MAX_PDF_CONTENT_CHARS]
                    if pdf_text else "None"
                ),
                "availableImages": available_images_text,
                "userProfile": user_profile_text,
                "hasSourceImages": has_source_images,
                "imageEnabled": image_enabled,
                "videoEnabled": video_enabled,
                "mediaEnabled": media_enabled,
                "researchContext": options.get("research_context") or "None",
                "teacherContext": options.get("teacher_context", ""),
            },
        )
    except MaicConfigError as exc:
        return {"success": False, "error": str(exc)}

    # Optional progress callback (stage 1 mid-progress).
    on_progress = callbacks and callbacks.get("onProgress")
    if on_progress:
        progress: GenerationProgress = {
            "stage": 1,
            "completed": 0,
            "total": 0,
            "message": "Analyzing requirement, generating scene outlines...",
        }
        on_progress(progress)

    # Stage 1 LLM call.
    try:
        response = await generate_text(
            messages=[
                SystemMessage(content=prompts.system),
                HumanMessage(content=prompts.user),
            ],
            language_model_id=language_model_id,
            max_tokens=_outline_max_tokens(target_scene_count),
        )
    except Exception as exc:  # noqa: BLE001 — wrap into GenerationResult
        return {"success": False, "error": f"LLM call failed: {exc}"}

    # Parse the response.
    parsed = parse_json_response(response)

    # Two valid response shapes (mirrors upstream lines 130-143):
    #   1. Object: {"languageDirective": "...", "outlines": [...]}
    #   2. Legacy flat array: [...]  (treated as outlines, default lang)
    raw_outlines: list[Any] | None = None
    language_directive = DEFAULT_LANGUAGE_DIRECTIVE
    if isinstance(parsed, list):
        raw_outlines = parsed
    elif isinstance(parsed, dict) and parsed.get("outlines"):
        raw_outlines = parsed.get("outlines")
        language_directive = (
            parsed.get("languageDirective") or DEFAULT_LANGUAGE_DIRECTIVE
        )

    if not isinstance(raw_outlines, list):
        return {
            "success": False,
            "error": "Failed to parse scene outlines response",
        }

    # Enrich: ensure each outline has an id + 1-based order index.
    enriched: list[SceneOutline] = []
    for index, outline in enumerate(raw_outlines):
        if not isinstance(outline, dict):
            _logger.warning(
                "Skipping non-dict outline at index %d: %r", index, outline
            )
            continue
        if "id" not in outline or not outline["id"]:
            outline["id"] = _generate_outline_id()
        outline["order"] = index + 1
        enriched.append(outline)

    # If the teacher wizard supplied an exact scene count, enforce it here.
    # Extra outlines are usually the model following the generic duration
    # heuristic instead of the explicit teacher count; trimming keeps the job
    # bounded without inventing content. A shortfall fails loud so the caller
    # can retry with a better provider/prompt instead of shipping a partial
    # lesson by accident.
    if target_scene_count is not None:
        if len(enriched) < target_scene_count:
            return {
                "success": False,
                "error": (
                    f"Expected exactly {target_scene_count} scene outlines, "
                    f"got {len(enriched)}"
                ),
            }
        if len(enriched) > target_scene_count:
            _logger.warning(
                "Trimming outline response from %d to requested %d scenes",
                len(enriched),
                target_scene_count,
            )
            enriched = enriched[:target_scene_count]

    if image_enabled:
        enriched = _ensure_slide_media_generations(enriched)

    # Phase 4 stub: uniquify_media_element_ids is a no-op until
    # MAIC-423 (scene_builder) ships in Session 3. The call-site is
    # preserved for forward compatibility with Phase 5+ image-generation.
    result = _uniquify_media_element_ids(enriched)

    if on_progress:
        progress = {
            "stage": 1,
            "completed": len(result),
            "total": len(result),
            "message": f"Generated {len(result)} scene outlines",
        }
        on_progress(progress)

    return {
        "success": True,
        "data": {
            "languageDirective": language_directive,
            "outlines": result,
        },
    }


def _target_scene_count(
    requirements: UserRequirements,
    options: dict[str, Any],
) -> int | None:
    raw = (
        options.get("scene_count")
        or options.get("sceneCount")
        or requirements.get("sceneCount")  # type: ignore[typeddict-item]
    )
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    if value < 1:
        return None
    return min(value, 20)


def _ensure_slide_media_generations(
    outlines: list[SceneOutline],
) -> list[SceneOutline]:
    """Guarantee one contextual image request for every slide scene.

    Smaller local models often ignore the optional `mediaGenerations`
    schema even when image generation is enabled. Without that placeholder,
    slide-content generation either emits empty image boxes or no visual at
    all. This repair keeps the pipeline production-real: the configured
    provider still generates the media later, but it receives a concrete,
    lesson-specific prompt.
    """
    repaired: list[SceneOutline] = []
    for outline in outlines:
        if outline.get("type") != "slide":
            repaired.append(outline)
            continue
        media_generations = outline.get("mediaGenerations")
        has_image = any(
            isinstance(item, dict)
            and item.get("type") == "image"
            and str(item.get("elementId") or "").strip()
            and str(item.get("prompt") or "").strip()
            for item in (media_generations or [])
        )
        if has_image:
            repaired.append(outline)
            continue

        next_outline = {**outline}
        existing = media_generations if isinstance(media_generations, list) else []
        next_outline["mediaGenerations"] = [
            *existing,
            {
                "type": "image",
                "elementId": f"gen_img_{_generate_outline_id()}",
                "prompt": _media_prompt_for_outline(outline),
                "aspectRatio": "16:9",
            },
        ]
        repaired.append(next_outline)  # type: ignore[arg-type]
    return repaired


def _media_prompt_for_outline(outline: SceneOutline) -> str:
    title = str(outline.get("title") or "Lesson visual").strip()
    description = str(outline.get("description") or "").strip()
    key_points = outline.get("keyPoints") or []
    clean_points = [
        str(point).strip()
        for point in key_points
        if str(point).strip()
    ][:4]
    focus = "; ".join(clean_points)
    parts = [
        f"Create a clear instructional visual for: {title}.",
        description,
        f"Show these lesson ideas: {focus}." if focus else "",
        "Use an age-appropriate classroom diagram or realistic illustration, no decorative stock-photo style, no text-heavy poster.",
    ]
    return " ".join(part for part in parts if part).strip()[:900]


def _outline_max_tokens(target_scene_count: int | None) -> int:
    if target_scene_count is None:
        return 4096
    estimate = _OUTLINE_BASE_TOKENS + (target_scene_count * _OUTLINE_TOKENS_PER_SCENE)
    return max(_OUTLINE_MIN_MAX_TOKENS, min(estimate, _OUTLINE_MAX_MAX_TOKENS))


def apply_outline_fallbacks(
    outline: SceneOutline,
    has_language_model: bool,
) -> SceneOutline:
    """Apply type fallbacks for outlines that can't be generated as
    their declared type.

    Mirrors upstream `applyOutlineFallbacks` (lines 175-195). Falls
    back to `slide` for:
      - interactive outlines without interactiveConfig OR
        (widgetType + widgetOutline)
      - pbl outlines without pblConfig OR no languageModel

    Returns the (possibly modified) outline.
    """
    # Ultra Mode: interactive scenes with widgetType + widgetOutline
    # are valid even without interactiveConfig.
    has_widget_config = bool(outline.get("widgetType") and outline.get("widgetOutline"))

    if (
        outline.get("type") == "interactive"
        and not outline.get("interactiveConfig")
        and not has_widget_config
    ):
        _logger.warning(
            'Interactive outline "%s" missing interactiveConfig and widget '
            "config, falling back to slide",
            outline.get("title", "?"),
        )
        return {**outline, "type": "slide"}

    if (
        outline.get("type") == "pbl"
        and (not outline.get("pblConfig") or not has_language_model)
    ):
        _logger.warning(
            'PBL outline "%s" missing pblConfig or languageModel, falling '
            "back to slide",
            outline.get("title", "?"),
        )
        return {**outline, "type": "slide"}

    return outline


# ── Internal helpers ──────────────────────────────────────────────


def _generate_outline_id() -> str:
    """Outline ID — 12 chars, kebab-friendly. Equivalent to upstream's
    `nanoid()` default length."""
    return secrets.token_urlsafe(9).replace("-", "").replace("_", "")[:12]


def _uniquify_media_element_ids(
    outlines: list[SceneOutline],
) -> list[SceneOutline]:
    """Replace sequential `gen_img_N` / `gen_vid_N` with globally unique
    IDs.

    Forwards to the real implementation in
    `apps.maic.generation.scene_builder` (MAIC-423). Imported lazily
    to avoid any future circular-import surprise as scene_generator
    grows. Outlines without `mediaGenerations` entries pass through
    unchanged — Phase 4 doesn't ship image/video generation, so
    most outlines have no media IDs to uniquify.
    """
    from apps.maic.generation.scene_builder import uniquify_media_element_ids
    return uniquify_media_element_ids(outlines)
