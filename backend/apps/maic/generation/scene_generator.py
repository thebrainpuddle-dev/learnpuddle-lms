"""Stage 2: Scene content and action generation.

Direct port of upstream `lib/generation/scene-generator.ts` (1,675
lines). MAIC-422 is sub-chunked across Sessions 3-5; this module
grows incrementally:

  MAIC-422.0 (THIS CHUNK): skeleton + scene-type dispatcher +
                           slide-content branch
  MAIC-422.1:              slide-actions branch
  MAIC-422.2:              quiz-content branch
  MAIC-422.3:              quiz-actions branch
  MAIC-422.4:              pbl-content + pbl-actions (STUBs per
                           MAIC-432 research; real port Phase 5+)
  MAIC-422.5:              interactive umbrella content (5 widget
                           types via switch on widgetType)
  MAIC-422.6:              unified scene-actions dispatcher
  MAIC-422.7:              widget teacher actions (optional path)
  MAIC-422.8:              generate_full_scenes orchestrator
                           (parallel via asyncio.gather) + LaTeX
                           wiring via interactive_post_processor

Source:
    https://github.com/THU-MAIC/OpenMAIC/blob/main/lib/generation/scene-generator.ts
    /Volumes/CrucialX9/OpenMAIC/lib/generation/scene-generator.ts

Phase 4 simplifications (deferred to Phase 5+):
    - Vision images / multimodal slides (visionImages parameter)
    - Image generation (generatedMediaMapping)
    - PDF image extraction / assignedImages
    - Image-id reference resolution (isImageIdReference, etc.)
    - Server-side LaTeX rendering for slide elements (frontend
      playback engine handles via existing KaTeX renderer)

Used by:
    - apps.maic.generation.pipeline_runner — Stage 2 STUB will
      forward to generate_full_scenes (MAIC-422.8) when available
"""
from __future__ import annotations

import logging
from typing import Any, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage

from apps.maic.exceptions import MaicConfigError
from apps.maic.generation.json_repair import parse_json_response
from apps.maic.generation.prompt_formatters import (
    format_teacher_persona_for_prompt,
)
from apps.maic.generation.prompt_loader import load_generation_prompt
from apps.maic.generation.types import (
    AgentInfo,
    SceneOutline,
)
from apps.maic.orchestration.ai_adapter import generate_text


_logger = logging.getLogger("apps.maic.generation.scene_generator")


# ── Constants ──────────────────────────────────────────────────────


# Canvas dimensions used by slide-content prompts. Mirrors upstream
# scene-generator.ts:675-676. Kept aligned with the Slide
# `viewportSize` + `viewportRatio` defaults baked into scene_builder's
# DEFAULT_SLIDE_THEME.
_CANVAS_WIDTH = 1000
_CANVAS_HEIGHT = 562.5  # 1000 × 0.5625 viewport ratio


# ── Options TypedDicts ────────────────────────────────────────────


class SceneContentOptions(TypedDict, total=False):
    """Optional knobs for `generate_scene_content`.

    Mirrors upstream `SceneContentOptions`. Phase 4 reads only
    `agents` + `languageDirective`; the rest are accepted but unused
    pending Phase 5+ image / vision support.
    """

    agents: list[AgentInfo]
    languageDirective: str
    # Phase 5+:
    assignedImages: list[dict]
    imageMapping: dict
    visionEnabled: bool
    generatedMediaMapping: dict
    languageModel: str
    thinkingConfig: dict


# ── Public API ────────────────────────────────────────────────────


async def generate_scene_content(
    outline: SceneOutline,
    *,
    language_model_id: str = "stub",
    options: SceneContentOptions | None = None,
) -> dict[str, Any] | None:
    """Generate the content section of a scene.

    Mirrors upstream `generateSceneContent`. Returns one of (per
    upstream's union):
      - GeneratedSlideContent: {elements, background, remark}
      - GeneratedQuizContent: {questions}        (MAIC-422.2)
      - GeneratedInteractiveContent: {html, ...}  (MAIC-422.5)
      - GeneratedPBLContent: {projectConfig}     (MAIC-422.4 STUB)

    Returns None when:
      - The scene type doesn't match any branch (defensive).
      - The LLM call or parse fails (per-branch behavior).

    The dispatcher applies upstream's "interactive → widget" routing:
    interactive scenes always go through `_generate_widget_content`
    (MAIC-422.5), regardless of whether they declare `widgetType` or
    a legacy `interactiveConfig`. The interactive branch is NOT
    implemented in this chunk (MAIC-422.0).
    """
    options = options or {}
    scene_type = outline.get("type")

    # ── Slide branch (MAIC-422.0) ──
    if scene_type == "slide":
        return await _generate_slide_content(
            outline,
            language_model_id=language_model_id,
            agents=options.get("agents"),
            language_directive=options.get("languageDirective", ""),
        )

    # ── Quiz branch — MAIC-422.2 (Session 3) ──
    if scene_type == "quiz":
        _logger.info(
            "scene_type=quiz: branch lands in MAIC-422.2 (Session 3); "
            "returning None for now."
        )
        return None

    # ── Interactive branch — MAIC-422.5 (Session 4) ──
    if scene_type == "interactive":
        _logger.info(
            "scene_type=interactive: branch lands in MAIC-422.5 "
            "(Session 4); returning None for now."
        )
        return None

    # ── PBL branch — MAIC-422.4 STUB (Session 4) ──
    if scene_type == "pbl":
        _logger.info(
            "scene_type=pbl: STUB lands in MAIC-422.4 (Session 4); "
            "returning None for now."
        )
        return None

    _logger.warning(
        "generate_scene_content: unknown scene type %r — returning None",
        scene_type,
    )
    return None


# ── Slide content (MAIC-422.0) ────────────────────────────────────


async def _generate_slide_content(
    outline: SceneOutline,
    *,
    language_model_id: str,
    agents: list[AgentInfo] | None = None,
    language_directive: str = "",
) -> dict[str, Any] | None:
    """Generate slide content.

    Direct port of upstream `generateSlideContent` (lines 600-774),
    minus the Phase 5+ image-handling paths:
      - vision-images / multimodal LLM call → DEFERRED
      - image-id resolution (`resolveImageIds`) → DEFERRED
      - server-side LaTeX rendering → DEFERRED (the frontend
        playback engine handles LaTeX rendering via the existing
        KaTeX renderer; slide elements ship with `latex` strings)

    Phase 4 path:
      1. Build the slide-content prompt with the outline's title /
         description / keyPoints + the teacher persona block.
      2. Call generate_text against the configured provider.
      3. Parse the response via parse_json_response.
      4. Validate `elements` is a list; return the
         GeneratedSlideContent dict shape.

    Returns None on prompt-load failure, LLM failure, or parse failure.
    """
    # No images in Phase 4 — emit upstream's "no images available"
    # message so the prompt's image-related sections render correctly.
    assigned_images_text = (
        "无可用图片，禁止插入任何 image 元素"
        # ^ "no images available, do not insert any image elements"
        # — verbatim from upstream line 611. Mixing Chinese is fine;
        # the LLM tolerates either language as long as the prompt is
        # self-consistent.
    )

    # Image / video element gating flags — all False in Phase 4.
    image_element_enabled = False
    generated_image_enabled = False
    generated_video_enabled = False
    media_element_enabled = False

    teacher_context = format_teacher_persona_for_prompt(agents)

    # Format outline keypoints for the prompt (mirrors upstream
    # line 683: `(outline.keyPoints || []).map((p, i) => …)`).
    key_points = outline.get("keyPoints") or []
    key_points_text = "\n".join(
        f"{i + 1}. {p}" for i, p in enumerate(key_points)
    )

    try:
        prompts = load_generation_prompt(
            "slide-content",
            {
                "title": outline.get("title", ""),
                "description": outline.get("description", ""),
                "keyPoints": key_points_text,
                "elements": "（根据要点自动生成）",
                # ^ "(auto-generated based on key points)" — verbatim
                # placeholder from upstream line 684.
                "assignedImages": assigned_images_text,
                "canvas_width": _CANVAS_WIDTH,
                "canvas_height": _CANVAS_HEIGHT,
                "teacherContext": teacher_context,
                "languageDirective": language_directive,
                "imageElementEnabled": image_element_enabled,
                "generatedImageEnabled": generated_image_enabled,
                "generatedVideoEnabled": generated_video_enabled,
                "mediaElementEnabled": media_element_enabled,
            },
        )
    except MaicConfigError as exc:
        _logger.error("Slide-content prompt missing: %s", exc)
        return None

    _logger.debug(
        "Generating slide content for: %s", outline.get("title", "?")
    )

    try:
        response = await generate_text(
            messages=[
                SystemMessage(content=prompts.system),
                HumanMessage(content=prompts.user),
            ],
            language_model_id=language_model_id,
        )
    except Exception as exc:  # noqa: BLE001
        _logger.error(
            "Slide-content LLM call failed for %s: %s",
            outline.get("title", "?"),
            exc,
        )
        return None

    generated_data = parse_json_response(response)
    if (
        not isinstance(generated_data, dict)
        or "elements" not in generated_data
        or not isinstance(generated_data["elements"], list)
    ):
        _logger.error(
            "Failed to parse slide-content AI response for: %s",
            outline.get("title", "?"),
        )
        return None

    elements = generated_data["elements"]
    _logger.debug(
        "Got %d elements for: %s",
        len(elements),
        outline.get("title", "?"),
    )

    # Phase 4: skip image-resolution + LaTeX-render passes (DEFERRED).
    # Element-fixing (defaults, dimensions) lands when needed for
    # parity. For Phase 4, pass elements through verbatim — the
    # frontend playback engine handles missing-default fallback.
    processed_elements = elements

    # Process background (mirrors upstream lines 757-767).
    background: dict[str, Any] | None = None
    raw_background = generated_data.get("background")
    if isinstance(raw_background, dict):
        bg_type = raw_background.get("type")
        if bg_type == "solid" and raw_background.get("color"):
            background = {
                "type": "solid",
                "color": raw_background["color"],
            }
        elif bg_type == "gradient" and raw_background.get("gradient"):
            background = {
                "type": "gradient",
                "gradient": raw_background["gradient"],
            }

    return {
        "elements": processed_elements,
        "background": background,
        "remark": generated_data.get("remark") or outline.get("description", ""),
    }
