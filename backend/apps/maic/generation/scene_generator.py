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
import random
import secrets
from typing import Any, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage

from apps.maic.exceptions import MaicConfigError
from apps.maic.generation.action_parser import (
    parse_actions_from_structured_output,
)
from apps.maic.generation.json_repair import parse_json_response
from apps.maic.generation.prompt_formatters import (
    build_course_context,
    format_agents_for_prompt,
    format_teacher_persona_for_prompt,
)
from apps.maic.generation.prompt_loader import load_generation_prompt
from apps.maic.generation.types import (
    AgentInfo,
    SceneGenerationContext,
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


class SceneActionsOptions(TypedDict, total=False):
    """Optional knobs for `generate_scene_actions`.

    Mirrors upstream `SceneActionsOptions`.
    """

    ctx: SceneGenerationContext
    agents: list[AgentInfo]
    userProfile: str
    languageDirective: str


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


# ── Scene actions dispatcher (MAIC-422.1) ─────────────────────────


async def generate_scene_actions(
    outline: SceneOutline,
    content: dict[str, Any],
    *,
    language_model_id: str = "stub",
    options: SceneActionsOptions | None = None,
) -> list[dict[str, Any]]:
    """Generate the action list for a scene.

    Mirrors upstream `generateSceneActions` (lines 1145-1291). Routes
    on outline.type:
      - slide → slide-actions LLM call (MAIC-422.1, this chunk)
      - quiz → quiz-actions (MAIC-422.3, Session 4)
      - interactive → interactive-actions (MAIC-422.6, Session 4)
      - pbl → pbl-actions (MAIC-422.4 STUB, Session 4)

    Returns an empty list when the scene type doesn't match any branch
    OR when the LLM call / parse fails AND no default fallback applies.

    For slide scenes, falls back to `_generate_default_slide_actions`
    when:
      - The slide-actions prompt template is missing (MaicConfigError)
      - The LLM call returns no actions

    Default actions: a spotlight on the first text element + a speech
    that reads the keyPoints (or description, or title).
    """
    options = options or {}
    agents = options.get("agents")

    # ── Slide branch (MAIC-422.1) ──
    if outline.get("type") == "slide" and "elements" in content:
        return await _generate_slide_actions(
            outline,
            content,
            language_model_id=language_model_id,
            ctx=options.get("ctx"),
            agents=agents,
            user_profile=options.get("userProfile", ""),
            language_directive=options.get("languageDirective", ""),
        )

    # ── Quiz branch — MAIC-422.3 (Session 4) ──
    if outline.get("type") == "quiz" and "questions" in content:
        _logger.info(
            "generate_scene_actions: quiz branch lands in MAIC-422.3 "
            "(Session 4); returning [] for now."
        )
        return []

    # ── Interactive branch — MAIC-422.6 (Session 4) ──
    if outline.get("type") == "interactive" and "html" in content:
        _logger.info(
            "generate_scene_actions: interactive branch lands in "
            "MAIC-422.6 (Session 4); returning [] for now."
        )
        return []

    # ── PBL branch — MAIC-422.4 STUB (Session 4) ──
    if outline.get("type") == "pbl" and "projectConfig" in content:
        _logger.info(
            "generate_scene_actions: pbl STUB lands in MAIC-422.4 "
            "(Session 4); returning [] for now."
        )
        return []

    return []


async def _generate_slide_actions(
    outline: SceneOutline,
    content: dict[str, Any],
    *,
    language_model_id: str,
    ctx: SceneGenerationContext | None,
    agents: list[AgentInfo] | None,
    user_profile: str,
    language_directive: str,
) -> list[dict[str, Any]]:
    """Slide-actions LLM call.

    Direct port of upstream `generateSceneActions` slide branch
    (lines 1176-1204). Builds the slide-actions prompt with the scene
    title / description / keyPoints + a per-element summary (so the
    LLM can pick valid `elementId` for spotlight actions) + course
    context + agents roster.

    Falls back to `_generate_default_slide_actions` when the prompt
    template is missing OR the LLM returns zero actions.
    """
    elements: list[dict[str, Any]] = content.get("elements") or []
    elements_text = _format_elements_for_prompt(elements)
    agents_text = format_agents_for_prompt(agents)
    course_context = build_course_context(ctx)

    key_points = outline.get("keyPoints") or []
    key_points_text = "\n".join(
        f"{i + 1}. {p}" for i, p in enumerate(key_points)
    )

    try:
        prompts = load_generation_prompt(
            "slide-actions",
            {
                "title": outline.get("title", ""),
                "keyPoints": key_points_text,
                "description": outline.get("description", ""),
                "elements": elements_text,
                "courseContext": course_context,
                "agents": agents_text,
                "userProfile": user_profile,
                "languageDirective": language_directive,
            },
        )
    except MaicConfigError:
        _logger.warning(
            "Slide-actions prompt missing — using default fallback."
        )
        return _generate_default_slide_actions(outline, elements)

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
            "Slide-actions LLM call failed for %s: %s",
            outline.get("title", "?"),
            exc,
        )
        return _generate_default_slide_actions(outline, elements)

    actions = parse_actions_from_structured_output(
        response, scene_type="slide"
    )

    if actions:
        return _process_actions(actions, elements, agents)
    return _generate_default_slide_actions(outline, elements)


# ── Action helpers (MAIC-422.1) ───────────────────────────────────


def _format_elements_for_prompt(elements: list[dict[str, Any]]) -> str:
    """Render slide elements as a per-element summary line.

    Mirrors upstream `formatElementsForPrompt` (lines 1310-1332). The
    LLM uses these IDs + summaries to pick valid `elementId` values
    for spotlight / laser actions.
    """
    import re as _re

    lines: list[str] = []
    for el in elements:
        el_type = el.get("type", "?")
        if el_type == "text" and "content" in el:
            # Strip HTML tags + trim to 50 chars (mirrors upstream).
            content_str = str(el.get("content") or "")
            text_content = _re.sub(r"<[^>]*>", "", content_str)[:50]
            ellipsis = "..." if len(text_content) >= 50 else ""
            summary = f'Content summary: "{text_content}{ellipsis}"'
        elif el_type == "chart" and "chartType" in el:
            summary = f"Chart type: {el.get('chartType')}"
        elif el_type == "image":
            summary = "Image element"
        elif el_type == "shape" and "shapeName" in el:
            summary = f"Shape: {el.get('shapeName') or 'unknown'}"
        elif el_type == "latex" and "latex" in el:
            latex_str = str(el.get("latex") or "")[:30]
            summary = f"Formula: {latex_str}"
        else:
            summary = f"{el_type} element"
        el_id = el.get("id", "")
        lines.append(f'- id: "{el_id}", type: "{el_type}", {summary}')
    return "\n".join(lines)


def _process_actions(
    actions: list[dict[str, Any]],
    elements: list[dict[str, Any]],
    agents: list[AgentInfo] | None = None,
) -> list[dict[str, Any]]:
    """Validate + fill action IDs / element refs / agent refs.

    Mirrors upstream `processActions` (lines 1470-1516). Two
    validations:

      1. spotlight.elementId must reference a real element. If
         missing or invalid, fall back to the first element's id
         (warning logged).
      2. discussion.agentId must reference a real agent (when agents
         are provided). If missing or invalid, pick a random student
         (or non-teacher) from the roster.
    """
    element_ids = {el.get("id") for el in elements if el.get("id")}
    agent_ids = {a.get("id") for a in (agents or []) if a.get("id")}
    student_agents = [a for a in (agents or []) if a.get("role") == "student"]
    non_teacher_agents = [
        a for a in (agents or []) if a.get("role") != "teacher"
    ]

    processed: list[dict[str, Any]] = []
    for action in actions:
        # Ensure each action has an ID.
        proc = dict(action)
        if not proc.get("id"):
            proc["id"] = f"action_{_nanoid_8()}"

        # Validate spotlight.elementId.
        if proc.get("type") == "spotlight":
            current = proc.get("elementId")
            if not current or current not in element_ids:
                if elements:
                    fallback = elements[0].get("id")
                    if fallback:
                        proc["elementId"] = fallback
                        _logger.warning(
                            "Invalid elementId %r, falling back to first element: %s",
                            current,
                            fallback,
                        )

        # Validate discussion.agentId.
        if proc.get("type") == "discussion" and agents:
            current = proc.get("agentId")
            if current and current in agent_ids:
                pass  # agent valid — keep
            else:
                pool = student_agents or non_teacher_agents
                if pool:
                    picked = random.choice(pool)
                    _logger.warning(
                        "Discussion agentId %r invalid, assigned: %s (%s)",
                        current or "(none)",
                        picked.get("id"),
                        picked.get("name"),
                    )
                    proc["agentId"] = picked.get("id")

        processed.append(proc)
    return processed


def _generate_default_slide_actions(
    outline: SceneOutline,
    elements: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Default slide actions when the LLM returns nothing usable.

    Mirrors upstream `generateDefaultSlideActions` (lines 1521-1547).
    Produces:
      - A spotlight on the first text element (if any).
      - A speech that reads the keyPoints joined by `。` (full-width
        Chinese period for compatibility with mixed-language content),
        falling back to description, then title.
    """
    actions: list[dict[str, Any]] = []

    text_elements = [el for el in elements if el.get("type") == "text"]
    if text_elements:
        first_id = text_elements[0].get("id")
        if first_id:
            actions.append({
                "id": f"action_{_nanoid_8()}",
                "type": "spotlight",
                "title": "聚焦重点",  # "focus on key points"
                "elementId": first_id,
            })

    key_points = outline.get("keyPoints") or []
    if key_points:
        speech_text = "。".join(key_points) + "。"
    else:
        speech_text = (
            outline.get("description") or outline.get("title") or ""
        )
    actions.append({
        "id": f"action_{_nanoid_8()}",
        "type": "speech",
        "title": "场景讲解",  # "scene narration"
        "text": speech_text,
    })

    return actions


def _nanoid_8() -> str:
    """8-char URL-safe ID. Same shape as scene_builder._nanoid_8."""
    raw = secrets.token_urlsafe(6).replace("-", "").replace("_", "")[:8]
    if len(raw) < 8:
        raw = (raw + secrets.token_urlsafe(4))[:8]
    return raw
