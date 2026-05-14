"""Stage 2: Scene content and action generation.

Direct port of upstream `lib/generation/scene-generator.ts` (1,675
lines). MAIC-422 is sub-chunked across Sessions 3-5; this module
grows incrementally:

  MAIC-422.0 (THIS CHUNK): skeleton + scene-type dispatcher +
                           slide-content branch
  MAIC-422.1:              slide-actions branch
  MAIC-422.2:              quiz-content branch
  MAIC-422.3:              quiz-actions branch
  MAIC-422.4:              pbl-content + pbl-actions (real PBL design
                           loop for live models; deterministic stub for
                           stub/dev model ids)
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

import hashlib
import logging
import secrets
from typing import Any, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage

from apps.maic.exceptions import MaicConfigError
import asyncio

from apps.maic.generation.action_parser import (
    parse_actions_from_structured_output,
)
from apps.maic.generation.interactive_post_processor import (
    post_process_interactive_html,
)
from apps.maic.generation.json_repair import parse_json_response
from apps.maic.generation.prompt_formatters import (
    build_course_context,
    format_agents_for_prompt,
    format_teacher_persona_for_prompt,
)
from apps.maic.generation.prompt_loader import load_generation_prompt
from apps.maic.generation.scene_builder import (
    build_complete_scene,
    resolve_scene_media,
    uniquify_media_element_ids,
)
from apps.maic.generation.widget_types import (
    validate_widget_config as _validate_widget_config,
)
from apps.maic.generation.types import GenerationCallbacks
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


def _combine_teacher_prompt_context(
    agent_context: str,
    lesson_context: str,
) -> str:
    """Merge visible teacher persona with private planning constraints."""
    chunks = []
    if agent_context.strip():
        chunks.append(agent_context.strip())
    if lesson_context.strip():
        chunks.append(
            "## Lesson Planning Context\n"
            "Use this to choose examples, misconceptions, checks, pacing, "
            "and agent handovers. Do not quote or reveal these planning "
            "notes verbatim unless the note is explicitly student-facing.\n"
            f"{lesson_context.strip()}"
        )
    return "\n\n".join(chunks)


# ── Options TypedDicts ────────────────────────────────────────────


class SceneContentOptions(TypedDict, total=False):
    """Optional knobs for `generate_scene_content`.

    Mirrors upstream `SceneContentOptions`. Phase 4 reads
    `agents` + `languageDirective` + LearnPuddle's teacherContext
    bridge; the rest are accepted but unused
    pending Phase 5+ image / vision support.
    """

    agents: list[AgentInfo]
    languageDirective: str
    teacherContext: str
    # Phase 5+:
    assignedImages: list[dict]
    imageMapping: dict
    visionEnabled: bool
    imageGenerationEnabled: bool
    image_generation_enabled: bool
    videoGenerationEnabled: bool
    video_generation_enabled: bool
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
    teacherContext: str
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
      - GeneratedPBLContent: {projectConfig}     (MAIC-422.4)

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
            teacher_context=options.get("teacherContext", ""),
            language_directive=options.get("languageDirective", ""),
            image_generation_enabled=bool(
                options.get("imageGenerationEnabled") or options.get("image_generation_enabled")
            ),
            video_generation_enabled=bool(
                options.get("videoGenerationEnabled") or options.get("video_generation_enabled")
            ),
        )

    # ── Quiz branch (MAIC-422.2) ──
    if scene_type == "quiz":
        return await _generate_quiz_content(
            outline,
            language_model_id=language_model_id,
            language_directive=options.get("languageDirective", ""),
        )

    # ── Interactive branch (MAIC-422.5) — widget umbrella ──
    if scene_type == "interactive":
        # Defensive: outline_generator's apply_outline_fallbacks
        # already converts interactive outlines without widget config
        # to slide. If somehow we still see one here, fall back to
        # a `simulation` widget using the title as concept (mirrors
        # upstream lines 307-316).
        if not (outline.get("widgetType") and outline.get("widgetOutline")):
            _logger.warning(
                'Interactive outline "%s" missing widget config; '
                "defaulting to simulation widget keyed on title.",
                outline.get("title", "?"),
            )
            outline = {
                **outline,
                "widgetType": "simulation",
                "widgetOutline": {"concept": outline.get("title", "")},
            }
        return await _generate_widget_content(
            outline,
            language_model_id=language_model_id,
            language_directive=options.get("languageDirective", ""),
        )

    # ── PBL branch (MAIC-422.4) ──
    if scene_type == "pbl":
        return await _generate_pbl_content(
            outline,
            language_model_id=language_model_id,
            language_directive=options.get("languageDirective", ""),
            teacher_context=options.get("teacherContext", ""),
        )

    _logger.warning(
        "generate_scene_content: unknown scene type %r — returning None",
        scene_type,
    )
    return None


def _format_media_generation_options(outline: SceneOutline) -> str:
    media_generations = outline.get("mediaGenerations") or []
    lines: list[str] = []
    for item in media_generations:
        if not isinstance(item, dict):
            continue
        media_type = item.get("type")
        element_id = item.get("elementId")
        prompt = item.get("prompt")
        if media_type not in {"image", "video"}:
            continue
        if not isinstance(element_id, str) or not element_id.strip():
            continue
        if not isinstance(prompt, str) or not prompt.strip():
            continue
        details = [f"placeholder `{element_id.strip()}`", prompt.strip()]
        aspect_ratio = item.get("aspectRatio")
        if isinstance(aspect_ratio, str) and aspect_ratio.strip():
            details.append(f"aspect ratio {aspect_ratio.strip()}")
        duration = item.get("duration_seconds") or item.get("durationSeconds")
        if media_type == "video" and duration:
            details.append(f"duration {duration}s")
        lines.append(f"- {media_type}: " + " - ".join(details))
    return "\n".join(lines) if lines else "None"


# ── Slide content (MAIC-422.0) ────────────────────────────────────


async def _generate_slide_content(
    outline: SceneOutline,
    *,
    language_model_id: str,
    agents: list[AgentInfo] | None = None,
    teacher_context: str = "",
    language_directive: str = "",
    image_generation_enabled: bool = False,
    video_generation_enabled: bool = False,
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

    media_generations_text = _format_media_generation_options(outline)
    has_generated_images = any(
        isinstance(item, dict) and item.get("type") == "image"
        for item in (outline.get("mediaGenerations") or [])
    )
    has_generated_videos = any(
        isinstance(item, dict) and item.get("type") == "video"
        for item in (outline.get("mediaGenerations") or [])
    )

    # Source image support is still deferred, but generated media can flow
    # through the Phase 9 orchestrator when the teacher enabled it.
    image_element_enabled = False
    generated_image_enabled = image_generation_enabled and has_generated_images
    generated_video_enabled = video_generation_enabled and has_generated_videos
    media_element_enabled = generated_image_enabled or generated_video_enabled

    teacher_context = _combine_teacher_prompt_context(
        format_teacher_persona_for_prompt(agents),
        teacher_context,
    )

    # Format outline keypoints for the prompt (mirrors upstream
    # line 683: `(outline.keyPoints || []).map((p, i) => …)`).
    key_points = outline.get("keyPoints") or []
    key_points_text = "\n".join(f"{i + 1}. {p}" for i, p in enumerate(key_points))

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
                "generatedMedia": media_generations_text,
            },
        )
    except MaicConfigError as exc:
        _logger.error("Slide-content prompt missing: %s", exc)
        return None

    _logger.debug("Generating slide content for: %s", outline.get("title", "?"))

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
    processed_elements = _apply_generated_image_contract(
        elements,
        outline,
        image_generation_enabled=image_generation_enabled,
    )

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


def _apply_generated_image_contract(
    elements: list[dict[str, Any]],
    outline: SceneOutline,
    *,
    image_generation_enabled: bool,
) -> list[dict[str, Any]]:
    """Ensure enabled generated media has a resolvable slide element.

    The prompt asks the model to reference `gen_img_*` placeholders, but
    local models frequently emit empty image boxes instead. The media
    resolver can only call a provider when an element `src` matches an
    outline `mediaGenerations[].elementId`, so repair the element list into
    that contract deterministically.
    """
    if not image_generation_enabled:
        return elements

    image_generations = [
        item for item in (outline.get("mediaGenerations") or [])
        if isinstance(item, dict)
        and item.get("type") == "image"
        and isinstance(item.get("elementId"), str)
        and str(item.get("elementId")).strip()
    ]
    if not image_generations:
        return elements

    first_media = image_generations[0]
    placeholder = str(first_media["elementId"]).strip()
    prompt = str(first_media.get("prompt") or outline.get("title") or "Lesson visual").strip()
    assigned = False
    repaired: list[dict[str, Any]] = []

    for raw in elements:
        if not isinstance(raw, dict):
            continue
        if raw.get("type") != "image":
            repaired.append(raw)
            continue

        src = str(raw.get("src") or "").strip()
        content = str(raw.get("content") or "").strip()
        if src.startswith("gen_img_"):
            assigned = True
            repaired.append(raw)
            continue

        if not assigned:
            image = {**raw}
            image["src"] = placeholder
            image["content"] = content or prompt
            image.setdefault("fixedRatio", True)
            assigned = True
            repaired.append(image)
            continue

        # Drop duplicate empty image boxes. They create giant placeholders
        # that obscure slide text without adding any media value.
        if src or content:
            repaired.append(raw)

    if not assigned:
        repaired.append({
            "id": f"image_{_nanoid_8()}",
            "type": "image",
            "left": 560,
            "top": 150,
            "width": 380,
            "height": 220,
            "src": placeholder,
            "content": prompt,
            "fixedRatio": True,
        })

    return repaired


# ── Quiz content (MAIC-422.2) ─────────────────────────────────────


# Default quizConfig — mirrors upstream lines 784-788. Used when the
# outline doesn't carry an explicit quizConfig (which is the common
# Phase 4 case since UserRequirements doesn't ship that field).
_DEFAULT_QUIZ_CONFIG: dict[str, Any] = {
    "questionCount": 3,
    "difficulty": "medium",
    "questionTypes": ["single"],
}


async def _generate_quiz_content(
    outline: SceneOutline,
    *,
    language_model_id: str,
    language_directive: str = "",
) -> dict[str, Any] | None:
    """Generate quiz content.

    Direct port of upstream `generateQuizContent` (lines 779-828).

    Builds the quiz-content prompt with title / description /
    keyPoints + quizConfig (questionCount / difficulty /
    questionTypes), calls generate_text + parse_json_response
    (expects an array of QuizQuestion dicts), and normalizes each
    question:
      - Ensures stable id (`q_<8chars>` if missing).
      - For non-short-answer types: normalizes options to
        `[{value: 'A', label: '...'}, ...]` and answers to `string[]`.
      - For short-answer types: drops options + answer + sets
        hasAnswer=False (free-form student response).

    Returns `{"questions": [...]}` on success OR None on prompt-load
    / LLM / parse failure.
    """
    quiz_config = outline.get("quizConfig") or _DEFAULT_QUIZ_CONFIG

    key_points = outline.get("keyPoints") or []
    key_points_text = "\n".join(f"{i + 1}. {p}" for i, p in enumerate(key_points))
    question_types = quiz_config.get("questionTypes") or ["single"]

    try:
        prompts = load_generation_prompt(
            "quiz-content",
            {
                "title": outline.get("title", ""),
                "description": outline.get("description", ""),
                "keyPoints": key_points_text,
                "questionCount": quiz_config.get("questionCount", 3),
                "difficulty": quiz_config.get("difficulty", "medium"),
                "questionTypes": ", ".join(question_types),
                "languageDirective": language_directive,
            },
        )
    except MaicConfigError as exc:
        _logger.error("Quiz-content prompt missing: %s", exc)
        return None

    _logger.debug("Generating quiz content for: %s", outline.get("title", "?"))

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
            "Quiz-content LLM call failed for %s: %s",
            outline.get("title", "?"),
            exc,
        )
        return None

    generated_questions = parse_json_response(response)
    if not isinstance(generated_questions, list):
        _logger.error(
            "Failed to parse quiz-content AI response for: %s",
            outline.get("title", "?"),
        )
        return None

    _logger.debug(
        "Got %d questions for: %s",
        len(generated_questions),
        outline.get("title", "?"),
    )

    questions: list[dict[str, Any]] = []
    for q in generated_questions:
        if not isinstance(q, dict):
            _logger.warning("Skipping non-dict quiz question: %r", q)
            continue
        is_text = q.get("type") == "short_answer"
        normalized = {
            **q,
            "id": q.get("id") or f"q_{_nanoid_8()}",
            "options": (None if is_text else _normalize_quiz_options(q.get("options"))),
            "answer": (None if is_text else _normalize_quiz_answer(q)),
            "hasAnswer": not is_text,
        }
        questions.append(normalized)

    return {"questions": questions}


def _normalize_quiz_options(
    options: list[Any] | None,
) -> list[dict[str, str]] | None:
    """Normalize quiz options from an AI response.

    Mirrors upstream `normalizeQuizOptions` (lines 835-857). Coerces
    plain strings or partial dicts into the `{value, label}` shape.
    Letter assignment defaults to A, B, C, D, ... when missing.

    Returns None when input isn't a list.
    """
    if not isinstance(options, list):
        return None

    normalized: list[dict[str, str]] = []
    for index, opt in enumerate(options):
        letter = chr(65 + index)  # A, B, C, ...

        if isinstance(opt, str):
            normalized.append({"value": letter, "label": opt})
            continue

        if isinstance(opt, dict):
            value = opt.get("value") if isinstance(opt.get("value"), str) else letter
            # label fallback chain: opt.label > opt.value > opt.text > letter
            raw_label = opt.get("label")
            if isinstance(raw_label, str):
                label = raw_label
            else:
                fallback = opt.get("value") or opt.get("text") or letter
                label = str(fallback)
            normalized.append({"value": value, "label": label})
            continue

        # Anything else (int, None, etc.) — coerce to string
        normalized.append({"value": letter, "label": str(opt)})

    return normalized


def _normalize_quiz_answer(
    question: dict[str, Any],
) -> list[str] | None:
    """Normalize the answer field from an AI response.

    Mirrors upstream `normalizeQuizAnswer` (lines 864-876). The AI may
    use any of: `answer`, `correctAnswer`, `correct_answer`. Returns
    a list of strings (always — even when the source is a single
    value) so downstream code can treat it uniformly.
    """
    raw = (
        question.get("answer")
        if question.get("answer") is not None
        else question.get("correctAnswer")
        if question.get("correctAnswer") is not None
        else question.get("correct_answer")
    )
    if raw is None:
        return None

    if isinstance(raw, list):
        return [str(x) for x in raw]
    return [str(raw)]


# ── PBL content (MAIC-422.4) ──────────────────────────────────────


async def _generate_pbl_content(
    outline: SceneOutline,
    *,
    language_model_id: str,
    language_directive: str = "",
    teacher_context: str = "",
) -> dict[str, Any] | None:
    """Generate a PBLProjectConfig through the real PBL design loop.

    `stub` and malformed outlines keep the old deterministic fallback so
    unit/dev smoke paths remain credential-free. Production model ids run
    the tool-calling design graph ported from OpenMAIC and fail loudly
    enough for the scene to be dropped if the model cannot produce a
    schema-valid PBL config.
    """
    if language_model_id in {"stub", "stub-director"}:
        return _generate_pbl_content_stub(
            outline,
            language_directive=language_directive,
        )

    pbl_config = outline.get("pblConfig") or {}
    if not isinstance(pbl_config, dict):
        _logger.error(
            'PBL outline "%s" has non-object pblConfig; dropping scene',
            outline.get("title", "?"),
        )
        return None

    project_topic = str(pbl_config.get("projectTopic") or outline.get("title") or "").strip()
    if not project_topic:
        _logger.error("PBL outline missing project topic; dropping scene")
        return None

    target_skills = pbl_config.get("targetSkills") or []
    if not isinstance(target_skills, list):
        target_skills = []
    target_skills = [str(s).strip() for s in target_skills if str(s).strip()]

    issue_count_raw = pbl_config.get("issueCount", 3)
    try:
        issue_count = int(issue_count_raw)
    except (TypeError, ValueError):
        issue_count = 3
    issue_count = max(1, min(issue_count, 10))

    try:
        from apps.maic.orchestration.ai_adapter import resolve_chat_model
        from apps.maic_pbl.design_graph import GeneratePBLConfig, generate_pbl_project
    except Exception as exc:  # noqa: BLE001 — import/runtime boundary
        _logger.exception("PBL design imports failed: %s", exc)
        return None

    try:
        model = resolve_chat_model(language_model_id)
    except MaicConfigError as exc:
        if _is_outline_fallback_allowed_for_pbl(language_model_id):
            _logger.warning(
                "PBL design cannot resolve tool-calling model %r for %r; "
                "using outline-derived PBL config fallback: %s",
                language_model_id,
                project_topic,
                exc,
            )
            return _generate_pbl_content_stub(
                outline,
                language_directive=language_directive,
            )
        _logger.error(
            "PBL design cannot resolve model %r for %r: %s",
            language_model_id,
            project_topic,
            exc,
        )
        return None

    project_description = _build_pbl_project_description(outline, pbl_config)
    try:
        result = await generate_pbl_project(
            GeneratePBLConfig(
                project_topic=project_topic,
                project_description=project_description,
                target_skills=target_skills,
                issue_count=issue_count,
                language_directive=language_directive,
                teacher_context=teacher_context,
            ),
            model,
        )
    except Exception as exc:  # noqa: BLE001 — model/tool loop boundary
        _logger.exception(
            "PBL design loop crashed for outline=%r: %s",
            outline.get("title", "?"),
            exc,
        )
        return None

    if result.error or not result.schema_valid:
        _logger.error(
            "PBL design returned unusable config for %r: error=%r schema_valid=%s",
            outline.get("title", "?"),
            result.error,
            result.schema_valid,
        )
        return None

    return {"projectConfig": result.project_config}


def _is_outline_fallback_allowed_for_pbl(language_model_id: str) -> bool:
    """Return True when a local model cannot support the PBL tool loop.

    Ollama is handled by the text-streaming adapter in this codebase, but
    the PBL design graph needs a LangChain chat model with `bind_tools`.
    Keep cloud model failures loud; use this only for local teacher-dev
    runs that would otherwise drop the PBL scene entirely.
    """
    return language_model_id.startswith("ollama/")


def _build_pbl_project_description(
    outline: SceneOutline,
    pbl_config: dict[str, Any],
) -> str:
    """Compose the design-loop description from classroom context.

    OpenMAIC feeds the PBL generator with the project description. In a
    teacher-created SaaS classroom we also have scene intent and key
    points from the class guide/outline. Folding those in is what makes
    the generated issueboard feel in-context rather than attached later.
    """
    parts: list[str] = []
    for value in (
        pbl_config.get("projectDescription"),
        outline.get("description"),
    ):
        if isinstance(value, str) and value.strip() and value.strip() not in parts:
            parts.append(value.strip())

    key_points = outline.get("keyPoints") or []
    if isinstance(key_points, list):
        clean_points = [str(p).strip() for p in key_points if str(p).strip()]
        if clean_points:
            parts.append("Lesson focus points: " + "; ".join(clean_points[:6]))

    return "\n\n".join(parts)


def _generate_pbl_content_stub(
    outline: SceneOutline,
    *,
    language_directive: str = "",
) -> dict[str, Any]:
    """Deterministic, schema-valid PBL config from outline context."""
    pbl_config = outline.get("pblConfig") or {}
    project_topic = pbl_config.get("projectTopic") or outline.get("title", "")
    project_description = pbl_config.get("projectDescription") or outline.get("description", "")

    project_config = _build_outline_driven_pbl_config(
        outline,
        project_topic=str(project_topic or "Project Challenge"),
        project_description=str(project_description or ""),
        language_directive=language_directive,
    )
    return {"projectConfig": project_config}


def _build_outline_driven_pbl_config(
    outline: SceneOutline,
    *,
    project_topic: str,
    project_description: str,
    language_directive: str,
) -> dict[str, Any]:
    """Build a usable PBL workspace when tool-calling is unavailable."""
    from apps.maic_pbl.mcp import AgentMCP, IssueboardMCP
    from apps.maic_pbl.types import PBLProjectConfig

    pbl_config = outline.get("pblConfig") or {}
    if not isinstance(pbl_config, dict):
        pbl_config = {}

    key_points = _coerce_string_list(outline.get("keyPoints"))
    target_skills = _coerce_string_list(pbl_config.get("targetSkills"))
    focus_points = target_skills or key_points

    issue_count = _coerce_int(pbl_config.get("issueCount"), default=3)
    issue_count = max(1, min(issue_count, 6))

    config: dict[str, Any] = {
        "projectInfo": {
            "title": project_topic.strip() or "Project Challenge",
            "description": (
                project_description.strip()
                or _build_pbl_project_description(outline, pbl_config)
                or "Work as a team to investigate the challenge, build a "
                "reasoned solution, and defend it with evidence."
            ),
        },
        "agents": [],
        "issueboard": {"agent_ids": [], "issues": [], "current_issue_id": None},
        "chat": {"messages": []},
        "selectedRole": None,
    }

    agent_mcp = AgentMCP(config)
    issueboard_mcp = IssueboardMCP(config, agent_mcp, language_directive)

    role_blueprints = _pbl_role_blueprints(focus_points)
    role_names: list[str] = []
    for role in role_blueprints:
        result = agent_mcp.create_agent(
            name=role["name"],
            actor_role=role["actor_role"],
            role_division="development",
            default_mode="chat",
            system_prompt=role["system_prompt"],
        )
        if result.success:
            role_names.append(role["name"])

    config["issueboard"]["agent_ids"] = role_names

    issue_blueprints = _pbl_issue_blueprints(
        project_topic=config["projectInfo"]["title"],
        project_description=config["projectInfo"]["description"],
        focus_points=focus_points,
        issue_count=issue_count,
    )
    for index, issue in enumerate(issue_blueprints):
        lead = role_names[index % len(role_names)] if role_names else "Research Lead"
        issueboard_mcp.create_issue(
            title=issue["title"],
            description=issue["description"],
            person_in_charge=lead,
            participants=role_names,
            notes=issue["notes"],
            index=index,
        )

    issueboard_mcp.activate_next_issue()
    _seed_pbl_welcome_message(config)

    # Validate before handing the blob to materialization. model_dump keeps
    # Pydantic defaults explicit and protects against drift in the fallback.
    return PBLProjectConfig.model_validate(config).model_dump()


def _pbl_role_blueprints(focus_points: list[str]) -> list[dict[str, str]]:
    focus_text = "; ".join(focus_points[:4]) if focus_points else "the project brief"
    return [
        {
            "name": "Research Lead",
            "actor_role": "Research and Evidence Lead",
            "system_prompt": (
                "Help the team gather trustworthy evidence, name assumptions, "
                f"and connect research back to {focus_text}."
            ),
        },
        {
            "name": "Design Lead",
            "actor_role": "Prototype and Solution Lead",
            "system_prompt": (
                "Help the team turn evidence into a practical design, compare "
                "trade-offs, and keep the solution testable."
            ),
        },
        {
            "name": "Evidence Analyst",
            "actor_role": "Data and Reflection Lead",
            "system_prompt": (
                "Help the team check observations, summarize evidence, and "
                "prepare a clear explanation for peer critique."
            ),
        },
    ]


def _pbl_issue_blueprints(
    *,
    project_topic: str,
    project_description: str,
    focus_points: list[str],
    issue_count: int,
) -> list[dict[str, str]]:
    if not focus_points:
        focus_points = [
            "understand the challenge",
            "develop a prototype",
            "test with evidence",
        ]

    base_sequence = [
        (
            "Frame the Challenge",
            "Clarify the project goal, success criteria, constraints, and "
            "what evidence the team will need.",
        ),
        (
            "Investigate the Evidence",
            "Collect and compare information that can guide the team toward "
            "a defensible solution.",
        ),
        (
            "Design and Test a Solution",
            "Build a proposed solution, test it against the evidence, and "
            "record what changes are needed.",
        ),
        (
            "Defend and Improve",
            "Present the solution, respond to peer critique, and identify "
            "the strongest next improvement.",
        ),
    ]

    issues: list[dict[str, str]] = []
    for index in range(issue_count):
        title, default_description = base_sequence[index % len(base_sequence)]
        focus = focus_points[index % len(focus_points)]
        issues.append(
            {
                "title": f"{title}: {focus[:72]}",
                "description": (
                    f"{default_description} Project context: {project_topic}. "
                    f"Focus this milestone on {focus}."
                ),
                "notes": (
                    f"Project brief: {project_description[:240]}. "
                    "Ask students for observable evidence before accepting claims."
                ),
            }
        )
    return issues


def _seed_pbl_welcome_message(config: dict[str, Any]) -> None:
    issueboard = config.get("issueboard") or {}
    current_issue_id = issueboard.get("current_issue_id")
    issues = issueboard.get("issues") or []
    current_issue = next(
        (i for i in issues if i.get("id") == current_issue_id),
        None,
    )
    if not current_issue:
        return

    questions = (
        f"Start with {current_issue.get('title')}. What do we already know, "
        "what evidence is missing, and what would make the solution convincing?"
    )
    current_issue["generated_questions"] = questions
    config.setdefault("chat", {}).setdefault("messages", []).append(
        {
            "id": f"msg_{current_issue['id']}_welcome",
            "agent_name": current_issue["question_agent_name"],
            "message": questions,
            "timestamp": 1.0,
            "read_by": [],
        }
    )


def _coerce_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    clean: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = str(item).strip()
        key = text.casefold()
        if text and key not in seen:
            clean.append(text)
            seen.add(key)
    return clean


def _coerce_int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# ── Interactive / widget content (MAIC-422.5) ────────────────────


# Widget-type → (template-id, variable-builder) map. Each builder
# takes (outline, widget_outline, language_directive) and returns
# the variable dict the template expects. Mirrors upstream's
# `switch (widgetType)` block (lines 986-1052). The 5 templates are
# already on disk (ported during Phase 1-3 prep work).
_WIDGET_TEMPLATE_IDS: dict[str, str] = {
    "simulation": "simulation-content",
    "diagram": "diagram-content",
    "code": "code-content",
    "game": "game-content",
    "visualization3d": "visualization3d-content",
}


async def _generate_widget_content(
    outline: SceneOutline,
    *,
    language_model_id: str,
    language_directive: str = "",
) -> dict[str, Any] | None:
    """Generate interactive widget content.

    Direct port of upstream `generateWidgetContent` (lines 969-1095).
    Routes on `outline.widgetType` to one of 5 templates, calls
    generate_text, extracts the HTML response, runs LaTeX delim
    conversion via `post_process_interactive_html`, and pulls any
    embedded `<script id="widget-config">` JSON.

    Returns:
        {"html", "widgetType", "widgetConfig", "teacherActions"}
        on success, None on:
          - Missing widget config (caller already defaulted to
            simulation; this path stays defensive)
          - Unknown widget type
          - Missing prompt template
          - LLM call failure
          - HTML extraction failure

    Phase 4 simplification: `teacherActions` ships as None. The
    optional second LLM call (MAIC-422.7) generates teacher actions
    for Ultra Mode, deferred to Session 5.
    """
    widget_type = outline.get("widgetType")
    widget_outline = outline.get("widgetOutline") or {}

    if not widget_type or not widget_outline:
        _logger.warning(
            "Interactive outline missing widget config — caller should "
            "have defaulted before reaching here."
        )
        return None

    template_id = _WIDGET_TEMPLATE_IDS.get(widget_type)
    if not template_id:
        _logger.warning("Unknown widget type: %s", widget_type)
        return None

    variables = _build_widget_variables(widget_type, outline, widget_outline, language_directive)

    try:
        prompts = load_generation_prompt(template_id, variables)
    except MaicConfigError as exc:
        _logger.error("Widget-content prompt %s missing: %s", template_id, exc)
        return None

    _logger.debug(
        "Generating %s widget for: %s",
        widget_type,
        outline.get("title", "?"),
    )

    html: str | None = None
    widget_config: dict[str, Any] | None = None
    invalid_widget_config: dict[str, Any] | None = None
    validation_reason: str | None = None
    for attempt in range(2):
        retry_note = (
            "\n\nPrevious widget-config schema validation failed: "
            f"{validation_reason}. Regenerate the complete HTML document and "
            "make the embedded widget-config JSON match the documented schema "
            "exactly; remove extra fields instead of inventing alternatives."
            if validation_reason
            else ""
        )
        try:
            response = await generate_text(
                messages=[
                    SystemMessage(content=prompts.system),
                    HumanMessage(content=f"{prompts.user}{retry_note}"),
                ],
                language_model_id=language_model_id,
            )
        except Exception as exc:  # noqa: BLE001
            _logger.error(
                "Widget-content (%s) LLM call failed for %s: %s",
                widget_type,
                outline.get("title", "?"),
                exc,
            )
            return None

        html = _extract_html(response)
        if not html:
            _logger.error(
                "Failed to extract HTML from %s response for: %s",
                widget_type,
                outline.get("title", "?"),
            )
            return None

        widget_config = _normalize_widget_config(
            widget_type,
            _extract_widget_config(html),
        )
        if widget_config is None:
            break

        ok, reason = _validate_widget_config(widget_type, widget_config)
        if ok:
            break

        validation_reason = reason or "unknown validation error"
        invalid_widget_config = widget_config
        repaired = _repair_widget_config(
            widget_type,
            invalid_widget_config,
            outline,
            widget_outline,
        )
        repaired_ok, repaired_reason = _validate_widget_config(widget_type, repaired)
        if repaired_ok:
            _logger.warning(
                "Widget-content (%s) repaired widget-config for %s after "
                "schema validation failed on attempt %d: %s",
                widget_type,
                outline.get("title", "?"),
                attempt + 1,
                validation_reason,
            )
            widget_config = repaired
            break
        _logger.warning(
            "Widget config validation failed for %s/%s on attempt %d: %s",
            widget_type,
            outline.get("title", "?"),
            attempt + 1,
            repaired_reason or validation_reason,
        )
        widget_config = None
    else:
        repaired = _repair_widget_config(
            widget_type,
            invalid_widget_config,
            outline,
            widget_outline,
        )
        ok, reason = _validate_widget_config(widget_type, repaired)
        if not ok:
            _logger.error(
                "Widget-content (%s) failed strict widget-config validation "
                "for %s after retry and repair: %s",
                widget_type,
                outline.get("title", "?"),
                reason,
            )
            return None
        _logger.warning(
            "Widget-content (%s) used repaired widget-config for %s after "
            "LLM schema retries failed.",
            widget_type,
            outline.get("title", "?"),
        )
        widget_config = repaired

    # MAIC-422.7: optional second LLM call to produce Ultra Mode
    # teacher actions. None on missing template OR LLM failure OR
    # parse failure — the playback engine treats absent teacherActions
    # as "no Ultra Mode actions" and falls through to the standard
    # interactive-actions LLM call (MAIC-422.6).
    teacher_actions = await _generate_widget_teacher_actions(
        widget_type=widget_type,
        outline=outline,
        widget_config=widget_config,
        language_model_id=language_model_id,
        language_directive=language_directive,
    )

    return {
        "html": post_process_interactive_html(html),
        "widgetType": widget_type,
        "widgetConfig": widget_config,
        "teacherActions": teacher_actions,
    }


async def _generate_widget_teacher_actions(
    *,
    widget_type: str,
    outline: SceneOutline,
    widget_config: dict[str, Any] | None,
    language_model_id: str,
    language_directive: str,
) -> list[dict[str, Any]] | None:
    """Generate Ultra Mode teacher actions for a widget.

    Direct port of upstream `generateWidgetTeacherActions` (lines
    1116-1140). Calls the widget-teacher-actions template, expects
    `{"actions": [...TeacherAction]}`. Returns None on missing
    template, LLM failure, or parse failure — caller treats None
    as "fall through to standard interactive-actions LLM call".

    The returned list is shape-only here; conversion to Action[] is
    performed by `_convert_teacher_actions_to_actions` (called from
    the actions dispatcher's Ultra Mode early-exit).
    """
    import json as _json

    key_points = outline.get("keyPoints") or []
    key_points_text = "\n".join(key_points)

    try:
        prompts = load_generation_prompt(
            "widget-teacher-actions",
            {
                "widgetType": widget_type,
                "description": outline.get("description", ""),
                "keyPoints": key_points_text,
                "widgetConfig": _json.dumps(widget_config or {}),
                "languageDirective": language_directive,
            },
        )
    except MaicConfigError as exc:
        _logger.warning(
            "widget-teacher-actions prompt missing: %s — Ultra Mode disabled.",
            exc,
        )
        return None

    try:
        response = await generate_text(
            messages=[
                SystemMessage(content=prompts.system),
                HumanMessage(content=prompts.user),
            ],
            language_model_id=language_model_id,
        )
    except Exception as exc:  # noqa: BLE001
        _logger.warning(
            "widget-teacher-actions LLM call failed for %s: %s — "
            "falling through to standard interactive-actions.",
            outline.get("title", "?"),
            exc,
        )
        return None

    parsed = parse_json_response(response)
    if not isinstance(parsed, dict):
        return None
    actions = parsed.get("actions")
    if not isinstance(actions, list):
        return None
    return [a for a in actions if isinstance(a, dict)]


def _convert_teacher_actions_to_actions(
    teacher_actions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert Ultra Mode TeacherAction[] to Action[].

    Direct port of upstream `convertTeacherActionsToActions` (lines
    1361-1465).

    Conversion rules:
      - speech → single speech Action.
      - highlight / setState / annotation / reveal → widget_<type>
        Action (visual/state change). If the TeacherAction has
        `content`, ALSO emit a paired speech Action with
        `id = "{base.id}_speech"` so TTS can narrate the change.
      - Unknown types → fallback to a single speech Action with
        `text = ta.content or ""`.
    """
    out: list[dict[str, Any]] = []

    for ta in teacher_actions:
        action_id = f"action_{_nanoid_8()}"
        base_title = ta.get("label") or ""
        ta_type = ta.get("type")
        content = ta.get("content") or ""

        if ta_type == "speech":
            out.append(
                {
                    "id": action_id,
                    "type": "speech",
                    "title": base_title,
                    "text": content,
                }
            )
            continue

        if ta_type in ("highlight", "annotation", "reveal"):
            out.append(
                {
                    "id": action_id,
                    "type": f"widget_{ta_type}",
                    "title": base_title,
                    "target": ta.get("target") or "",
                }
            )
            if content:
                out.append(
                    {
                        "id": f"{action_id}_speech",
                        "type": "speech",
                        "title": base_title,
                        "text": content,
                    }
                )
            continue

        if ta_type == "setState":
            out.append(
                {
                    "id": action_id,
                    "type": "widget_setState",
                    "title": base_title,
                    "state": ta.get("state") or {},
                }
            )
            if content:
                out.append(
                    {
                        "id": f"{action_id}_speech",
                        "type": "speech",
                        "title": base_title,
                        "text": content,
                    }
                )
            continue

        # Unknown type — fall back to speech.
        out.append(
            {
                "id": action_id,
                "type": "speech",
                "title": base_title,
                "text": content,
            }
        )

    return out


def _build_widget_variables(
    widget_type: str,
    outline: SceneOutline,
    widget_outline: dict[str, Any],
    language_directive: str,
) -> dict[str, Any]:
    """Build the prompt variable dict for a widget template.

    Mirrors upstream's `switch (widgetType)` variable-builder block
    (lines 986-1052). Each branch matches the on-disk template's
    `{{var}}` placeholders exactly.
    """
    key_points = outline.get("keyPoints") or []
    key_points_text = "\n".join(key_points)

    if widget_type == "simulation":
        return {
            "conceptName": widget_outline.get("concept") or outline.get("title", ""),
            "conceptOverview": outline.get("description", ""),
            "keyPoints": key_points_text,
            "variables": ", ".join(widget_outline.get("keyVariables") or []),
            "designIdea": "",
            "languageDirective": language_directive,
        }
    if widget_type == "diagram":
        return {
            "title": outline.get("title", ""),
            "diagramType": widget_outline.get("diagramType") or "flowchart",
            "description": outline.get("description", ""),
            "keyPoints": key_points_text,
            "languageDirective": language_directive,
        }
    if widget_type == "code":
        return {
            "title": outline.get("title", ""),
            "programmingLanguage": widget_outline.get("language") or "python",
            "description": outline.get("description", ""),
            "keyPoints": key_points_text,
            "starterCode": "",
            "testCases": "",
            "hints": "",
            "languageDirective": language_directive,
        }
    if widget_type == "game":
        return {
            "title": outline.get("title", ""),
            "gameType": widget_outline.get("gameType") or "quiz",
            "description": outline.get("description", ""),
            "keyPoints": key_points_text,
            # Upstream passes a dict literal here; the template uses
            # the rendered string. JSON-encode for prompt readability.
            "scoring": '{"correctPoints": 10, "speedBonus": 5}',
            "languageDirective": language_directive,
        }
    if widget_type == "visualization3d":
        objects = widget_outline.get("objects") or []
        interactions = widget_outline.get("interactions") or []
        return {
            "title": outline.get("title", ""),
            "visualizationType": widget_outline.get("visualizationType") or "custom",
            "description": outline.get("description", ""),
            "keyPoints": key_points_text,
            "objects": ", ".join(objects) if objects else "",
            "interactions": ", ".join(interactions) if interactions else "",
            "languageDirective": language_directive,
        }
    # _generate_widget_content already gates on _WIDGET_TEMPLATE_IDS
    # — this is unreachable in practice, but keep the contract crisp.
    return {}


def _extract_html(response: str) -> str | None:
    """Extract an HTML document from an LLM response.

    Direct port of upstream `extractHtml` (lines 928-963). Three
    strategies in order:
      1. Find `<!DOCTYPE html>` or `<html` and slice through `</html>`.
      2. Pull the first triple-backtick code block (with or without
         the `html` tag), keep it only if it contains `<html` or
         `<!DOCTYPE`.
      3. If the trimmed response itself starts with `<!DOCTYPE` or
         `<html`, return as-is.

    Returns None if none of the strategies find HTML.
    """
    import re as _re

    # Strategy 1: complete HTML document.
    doctype_start = response.find("<!DOCTYPE html>")
    html_tag_start = response.find("<html")
    start = doctype_start if doctype_start != -1 else html_tag_start
    if start != -1:
        html_end = response.rfind("</html>")
        if html_end != -1:
            return response[start : html_end + len("</html>")]

    # Strategy 2: code block extraction.
    match = _re.search(r"```(?:html)?\s*([\s\S]*?)```", response, flags=_re.MULTILINE)
    if match:
        content = match.group(1).strip()
        if "<html" in content or "<!DOCTYPE" in content:
            return content

    # Strategy 3: response itself is HTML.
    trimmed = response.strip()
    if trimmed.startswith("<!DOCTYPE") or trimmed.startswith("<html"):
        return trimmed

    return None


def _extract_widget_config(html: str) -> dict[str, Any] | None:
    """Extract embedded widget config JSON from HTML.

    Direct port of upstream `extractWidgetConfig` (lines 1100-1111).
    Looks for `<script type="application/json" id="widget-config">…
    </script>` and parses the inner JSON. Returns None on no match
    or parse failure.
    """
    import json
    import re as _re

    match = _re.search(
        r'<script type="application/json" id="widget-config">' r"([\s\S]*?)</script>",
        html,
    )
    if not match:
        return None

    try:
        return json.loads(match.group(1))
    except (ValueError, TypeError):
        return None


def _normalize_widget_config(
    widget_type: str,
    widget_config: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Repair safe widget-config drift using authoritative outline metadata."""
    if not isinstance(widget_config, dict):
        return widget_config
    if widget_config.get("type"):
        return widget_config
    return {"type": widget_type, **widget_config}


def _repair_widget_config(
    widget_type: str,
    widget_config: dict[str, Any] | None,
    outline: SceneOutline,
    widget_outline: dict[str, Any],
) -> dict[str, Any]:
    """Build a valid widget config from trusted outline metadata.

    This is the final production safety net after LLM schema retries:
    keep the generated HTML, but never expose malformed widgetConfig
    through the API. The repair intentionally uses only the current
    outline and safely shaped values from the model response.
    """
    raw = widget_config if isinstance(widget_config, dict) else {}
    title = str(
        raw.get("concept")
        or widget_outline.get("concept")
        or outline.get("title")
        or "Interactive concept"
    )
    description = str(
        raw.get("description") or outline.get("description") or "Explore the concept interactively."
    )

    if widget_type == "simulation":
        variables = _repair_simulation_variables(
            raw.get("variables"),
            widget_outline.get("keyVariables"),
        )
        repaired: dict[str, Any] = {
            "type": "simulation",
            "concept": title,
            "description": description,
            "variables": variables,
        }
        presets = _repair_simulation_presets(raw.get("presets"), variables)
        if presets:
            repaired["presets"] = presets
        return repaired

    if widget_type == "diagram":
        return _repair_diagram_config(raw, title, description, widget_outline)

    if widget_type == "code":
        language = raw.get("language") or widget_outline.get("language") or "python"
        if language not in {"python", "javascript", "typescript", "java", "cpp"}:
            language = "python"
        return {
            "type": "code",
            "language": language,
            "description": description,
            "starterCode": str(raw.get("starterCode") or "# Try your solution here\n"),
            "testCases": _repair_code_test_cases(raw.get("testCases")),
            "hints": _coerce_string_list(raw.get("hints"))
            or ["Start with the example from the lesson."],
            "solution": str(raw.get("solution") or "# One possible solution goes here\n"),
        }

    if widget_type == "game":
        game_type = raw.get("gameType") or widget_outline.get("gameType") or "quiz"
        if game_type not in {"quiz", "puzzle", "strategy", "card"}:
            game_type = "quiz"
        return {
            "type": "game",
            "gameType": game_type,
            "description": description,
            "questions": _repair_game_questions(raw.get("questions"), title),
            "scoring": _repair_game_scoring(raw.get("scoring")),
        }

    if widget_type == "visualization3d":
        viz_type = (
            raw.get("visualizationType") or widget_outline.get("visualizationType") or "custom"
        )
        if viz_type not in {
            "molecular",
            "solar",
            "anatomy",
            "geometry",
            "physics",
            "custom",
        }:
            viz_type = "custom"
        return {
            "type": "visualization3d",
            "visualizationType": viz_type,
            "description": description,
            "objects": _repair_3d_objects(raw.get("objects"), title),
            "interactions": _repair_3d_interactions(raw.get("interactions")),
        }

    return {"type": widget_type}


def _repair_simulation_variables(
    raw_variables: Any,
    outline_variables: Any,
) -> list[dict[str, Any]]:
    variables: list[dict[str, Any]] = []
    if isinstance(raw_variables, list):
        for index, item in enumerate(raw_variables[:6]):
            if isinstance(item, dict):
                name = str(item.get("name") or f"variable_{index + 1}")
                label = str(item.get("label") or name.replace("_", " ").title())
                minimum = _coerce_number(item.get("min"), default=0.0)
                maximum = _coerce_number(item.get("max"), default=10.0)
                if maximum <= minimum:
                    maximum = minimum + 10.0
                default = _coerce_number(
                    item.get("default"),
                    default=minimum + ((maximum - minimum) / 2),
                )
                default = min(max(default, minimum), maximum)
                variable = {
                    "name": name,
                    "label": label,
                    "min": minimum,
                    "max": maximum,
                    "default": default,
                }
                unit = item.get("unit")
                if isinstance(unit, str) and unit.strip():
                    variable["unit"] = unit.strip()
                step = item.get("step")
                if step is not None:
                    variable["step"] = _coerce_number(step, default=1.0)
                variables.append(variable)
            elif isinstance(item, str) and item.strip():
                variables.append(_default_simulation_variable(item, index))

    if not variables:
        names = _coerce_string_list(outline_variables)
        variables = [
            _default_simulation_variable(name, index) for index, name in enumerate(names[:4])
        ]
    return variables or [_default_simulation_variable("value", 0)]


def _default_simulation_variable(name: str, index: int) -> dict[str, Any]:
    safe_name = str(name).strip() or f"variable_{index + 1}"
    return {
        "name": safe_name.lower().replace(" ", "_"),
        "label": safe_name.replace("_", " ").title(),
        "min": 0.0 if index == 0 else 1.0,
        "max": 10.0 if index == 0 else 12.0,
        "default": 1.0,
        "step": 1.0,
    }


def _repair_simulation_presets(
    raw_presets: Any,
    variables: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not isinstance(raw_presets, list):
        return []
    valid_names = {str(var["name"]) for var in variables}
    presets: list[dict[str, Any]] = []
    for item in raw_presets[:4]:
        if not isinstance(item, dict):
            continue
        values = item.get("variables")
        if not isinstance(values, dict):
            continue
        clean_values = {
            str(key): _coerce_number(value, default=0.0)
            for key, value in values.items()
            if str(key) in valid_names
        }
        if clean_values:
            presets.append(
                {
                    "name": str(item.get("name") or f"Preset {len(presets) + 1}"),
                    "variables": clean_values,
                }
            )
    return presets


def _repair_diagram_config(
    raw: dict[str, Any],
    title: str,
    description: str,
    widget_outline: dict[str, Any],
) -> dict[str, Any]:
    diagram_type = raw.get("diagramType") or widget_outline.get("diagramType") or "flowchart"
    if diagram_type not in {"flowchart", "mindmap", "hierarchy", "system"}:
        diagram_type = "flowchart"
    nodes = _repair_diagram_nodes(raw.get("nodes"), title)
    return {
        "type": "diagram",
        "diagramType": diagram_type,
        "description": description,
        "nodes": nodes,
        "edges": _repair_diagram_edges(raw.get("edges"), nodes),
    }


def _repair_diagram_nodes(raw_nodes: Any, title: str) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    if isinstance(raw_nodes, list):
        for index, item in enumerate(raw_nodes[:8]):
            if not isinstance(item, dict):
                continue
            node_id = str(item.get("id") or f"node_{index + 1}")
            label = str(item.get("label") or item.get("title") or node_id)
            node: dict[str, Any] = {"id": node_id, "label": label}
            position = item.get("position")
            if isinstance(position, dict):
                node["position"] = {
                    "x": _coerce_number(position.get("x"), default=index * 160.0),
                    "y": _coerce_number(position.get("y"), default=80.0),
                }
            details = item.get("details")
            if isinstance(details, str) and details.strip():
                node["details"] = details.strip()
            node_type = item.get("type")
            if node_type in {"default", "decision", "start", "end"}:
                node["type"] = node_type
            nodes.append(node)
    return nodes or [
        {"id": "start", "label": title, "type": "start"},
        {"id": "explore", "label": "Explore and explain", "type": "default"},
    ]


def _repair_diagram_edges(
    raw_edges: Any,
    nodes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    node_ids = {str(node["id"]) for node in nodes}
    edges: list[dict[str, Any]] = []
    if isinstance(raw_edges, list):
        for index, item in enumerate(raw_edges[:10]):
            if not isinstance(item, dict):
                continue
            from_id = str(item.get("from") or item.get("from_") or "")
            to_id = str(item.get("to") or "")
            if from_id not in node_ids or to_id not in node_ids:
                continue
            edge = {
                "id": str(item.get("id") or f"edge_{index + 1}"),
                "from": from_id,
                "to": to_id,
            }
            label = item.get("label")
            if isinstance(label, str) and label.strip():
                edge["label"] = label.strip()
            edges.append(edge)
    if not edges and len(nodes) >= 2:
        edges.append({"id": "edge_1", "from": nodes[0]["id"], "to": nodes[1]["id"]})
    return edges


def _repair_code_test_cases(raw_cases: Any) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    if isinstance(raw_cases, list):
        for index, item in enumerate(raw_cases[:5]):
            if not isinstance(item, dict):
                continue
            cases.append(
                {
                    "id": str(item.get("id") or f"case_{index + 1}"),
                    "input": str(item.get("input") or ""),
                    "expected": str(item.get("expected") or ""),
                    "description": str(item.get("description") or "Check the result."),
                }
            )
    return cases or [
        {
            "id": "case_1",
            "input": "",
            "expected": "",
            "description": "Run the starter example.",
        }
    ]


def _repair_game_questions(raw_questions: Any, title: str) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    if isinstance(raw_questions, list):
        for index, item in enumerate(raw_questions[:6]):
            if not isinstance(item, dict):
                continue
            options = _coerce_string_list(item.get("options"))
            if len(options) < 2:
                continue
            correct = item.get("correct")
            if not isinstance(correct, int) and not (
                isinstance(correct, list) and all(isinstance(i, int) for i in correct)
            ):
                correct = 0
            questions.append(
                {
                    "id": str(item.get("id") or f"question_{index + 1}"),
                    "question": str(item.get("question") or f"Review {title}."),
                    "type": item.get("type")
                    if item.get("type") in {"single", "multiple"}
                    else "single",
                    "options": options,
                    "correct": correct,
                    "explanation": str(item.get("explanation") or "Check the lesson evidence."),
                    "points": _coerce_int(item.get("points"), default=10),
                }
            )
    return questions or [
        {
            "id": "question_1",
            "question": f"Which choice best matches {title}?",
            "type": "single",
            "options": ["The lesson's core idea", "An unrelated detail"],
            "correct": 0,
            "explanation": "The correct choice follows the scene's main concept.",
            "points": 10,
        }
    ]


def _repair_game_scoring(raw_scoring: Any) -> dict[str, Any]:
    scoring = raw_scoring if isinstance(raw_scoring, dict) else {}
    return {
        "correctPoints": _coerce_number(scoring.get("correctPoints"), default=10.0),
        "speedBonus": _coerce_number(scoring.get("speedBonus"), default=0.0),
    }


def _repair_3d_objects(raw_objects: Any, title: str) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    allowed_types = {"sphere", "box", "cylinder", "cone", "torus", "plane", "custom"}
    if isinstance(raw_objects, list):
        for index, item in enumerate(raw_objects[:8]):
            if not isinstance(item, dict):
                continue
            object_type = item.get("type") if item.get("type") in allowed_types else "box"
            clean: dict[str, Any] = {
                "id": str(item.get("id") or f"object_{index + 1}"),
                "type": object_type,
                "name": str(item.get("name") or item.get("id") or title),
            }
            position = _repair_vec3(item.get("position"))
            if position:
                clean["position"] = position
            material = item.get("material")
            if isinstance(material, dict):
                mat_type = (
                    material.get("type")
                    if material.get("type")
                    in {
                        "basic",
                        "lambert",
                        "phong",
                        "standard",
                        "emissive",
                    }
                    else "standard"
                )
                clean["material"] = {
                    "type": mat_type,
                    "color": str(material.get("color") or "#4f46e5"),
                }
            objects.append(clean)
    return objects or [
        {
            "id": "concept_model",
            "type": "box",
            "name": title,
            "position": {"x": 0.0, "y": 0.0, "z": 0.0},
            "material": {"type": "standard", "color": "#4f46e5"},
        }
    ]


def _repair_3d_interactions(raw_interactions: Any) -> list[dict[str, Any]]:
    allowed = {"orbit", "zoom", "pan", "slider", "button", "toggle"}
    interactions: list[dict[str, Any]] = []
    if isinstance(raw_interactions, list):
        for item in raw_interactions[:6]:
            if not isinstance(item, dict):
                continue
            kind = item.get("type")
            if kind not in allowed:
                continue
            clean: dict[str, Any] = {"type": kind}
            for key in ("target", "label", "param"):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    clean[key] = value.strip()
            for key in ("min", "max", "default", "step"):
                if item.get(key) is not None:
                    clean[key] = _coerce_number(item.get(key), default=0.0)
            interactions.append(clean)
    return interactions or [{"type": "orbit", "label": "Rotate view"}]


def _repair_vec3(raw: Any) -> dict[str, float] | None:
    if not isinstance(raw, dict):
        return None
    return {
        "x": _coerce_number(raw.get("x"), default=0.0),
        "y": _coerce_number(raw.get("y"), default=0.0),
        "z": _coerce_number(raw.get("z"), default=0.0),
    }


def _coerce_number(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


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
      - slide → slide-actions LLM call (MAIC-422.1)
      - quiz → quiz-actions LLM call (MAIC-422.3)
      - interactive → interactive-actions LLM call (MAIC-422.6).
        Ultra Mode `teacherActions`-conversion early-exit lands at
        MAIC-422.7 (this chunk).
      - pbl → pbl-actions LLM call (MAIC-422.4)

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

    # ── Quiz branch (MAIC-422.3) ──
    if outline.get("type") == "quiz" and "questions" in content:
        return await _generate_quiz_actions(
            outline,
            content,
            language_model_id=language_model_id,
            ctx=options.get("ctx"),
            agents=agents,
            language_directive=options.get("languageDirective", ""),
        )

    # ── Interactive branch (MAIC-422.6 + .7) ──
    # Ultra Mode early-exit (MAIC-422.7): if the widget content
    # carried teacher actions, convert them directly to Action[] and
    # SKIP the standard interactive-actions LLM call. Mirrors upstream
    # lines 1167-1174.
    if outline.get("type") == "interactive" and "html" in content and content.get("teacherActions"):
        teacher_actions = content["teacherActions"]
        _logger.info(
            "[Ultra Mode] Converting %d teacherActions to Actions for: %s",
            len(teacher_actions),
            outline.get("title", "?"),
        )
        return _convert_teacher_actions_to_actions(teacher_actions)

    if outline.get("type") == "interactive" and "html" in content:
        return await _generate_interactive_actions(
            outline,
            content,
            language_model_id=language_model_id,
            ctx=options.get("ctx"),
            agents=agents,
            language_directive=options.get("languageDirective", ""),
        )

    # ── PBL branch (MAIC-422.4) ──
    if outline.get("type") == "pbl" and "projectConfig" in content:
        return await _generate_pbl_actions(
            outline,
            content,
            language_model_id=language_model_id,
            ctx=options.get("ctx"),
            agents=agents,
            teacher_context=options.get("teacherContext", ""),
            language_directive=options.get("languageDirective", ""),
        )

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
    key_points_text = "\n".join(f"{i + 1}. {p}" for i, p in enumerate(key_points))

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
        _logger.warning("Slide-actions prompt missing — using default fallback.")
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

    actions = parse_actions_from_structured_output(response, scene_type="slide")

    if actions:
        return _process_actions(actions, elements, agents)
    return _generate_default_slide_actions(outline, elements)


# ── Quiz actions (MAIC-422.3) ─────────────────────────────────────


async def _generate_quiz_actions(
    outline: SceneOutline,
    content: dict[str, Any],
    *,
    language_model_id: str,
    ctx: SceneGenerationContext | None,
    agents: list[AgentInfo] | None,
    language_directive: str,
) -> list[dict[str, Any]]:
    """Quiz-actions LLM call.

    Direct port of upstream `generateSceneActions` quiz branch
    (lines 1206-1232). Builds the quiz-actions prompt with title /
    description / keyPoints + a per-question summary (so the LLM can
    reference questions in narration) + course context + agents
    roster.

    Falls back to `_generate_default_quiz_actions` when the prompt
    template is missing OR the LLM returns zero actions.

    `processActions` runs with an empty elements list — quiz scenes
    don't have spotlightable elements; only discussion.agentId
    validation matters here.
    """
    questions: list[dict[str, Any]] = content.get("questions") or []
    questions_text = _format_questions_for_prompt(questions)
    agents_text = format_agents_for_prompt(agents)
    course_context = build_course_context(ctx)

    key_points = outline.get("keyPoints") or []
    key_points_text = "\n".join(f"{i + 1}. {p}" for i, p in enumerate(key_points))

    try:
        prompts = load_generation_prompt(
            "quiz-actions",
            {
                "title": outline.get("title", ""),
                "keyPoints": key_points_text,
                "description": outline.get("description", ""),
                "questions": questions_text,
                "courseContext": course_context,
                "agents": agents_text,
                "languageDirective": language_directive,
            },
        )
    except MaicConfigError:
        _logger.warning("Quiz-actions prompt missing — using default fallback.")
        return _generate_default_quiz_actions(outline)

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
            "Quiz-actions LLM call failed for %s: %s",
            outline.get("title", "?"),
            exc,
        )
        return _generate_default_quiz_actions(outline)

    actions = parse_actions_from_structured_output(response, scene_type="quiz")

    if actions:
        return _process_actions(actions, [], agents)
    return _generate_default_quiz_actions(outline)


def _format_questions_for_prompt(
    questions: list[dict[str, Any]],
) -> str:
    """Render quiz questions as a per-question summary line.

    Mirrors upstream `formatQuestionsForPrompt` (lines 1337-1346). The
    LLM uses these summaries to write quiz-narration text that
    references specific questions.
    """
    lines: list[str] = []
    for i, q in enumerate(questions):
        q_type = q.get("type") or "?"
        q_text = q.get("question") or ""
        options = q.get("options")
        if isinstance(options, list) and options:
            opts_rendered = ", ".join(
                f"{o.get('value', '?')}. {o.get('label', '')}" if isinstance(o, dict) else str(o)
                for o in options
            )
            options_text = f"Options: {opts_rendered}"
        else:
            options_text = ""
        lines.append(f"Q{i + 1} ({q_type}): {q_text}\n{options_text}")
    return "\n\n".join(lines)


def _generate_default_quiz_actions(
    _outline: SceneOutline,
) -> list[dict[str, Any]]:
    """Default quiz actions when the LLM returns nothing usable.

    Mirrors upstream `generateDefaultQuizActions` (lines 1552-1561). A
    single speech that frames the quiz as a check-in.
    """
    return [
        {
            "id": f"action_{_nanoid_8()}",
            "type": "speech",
            "title": "测验引导",  # "quiz introduction"
            "text": "现在让我们来做一个小测验，检验一下学习成果。",
            # ^ "Now let's do a small quiz to check what we've learned."
        }
    ]


# ── PBL actions (MAIC-422.4) ──────────────────────────────────────


def _short_prompt_value(value: Any, *, max_chars: int = 220) -> str:
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    return f"{text[: max_chars - 3].rstrip()}..."


def _format_pbl_project_for_prompt(project_config: Any) -> str:
    """Summarize the generated PBL workspace for the handoff speech prompt."""
    if not isinstance(project_config, dict):
        return "No generated PBL workspace details are available."

    lines: list[str] = ["## Generated PBL Workspace"]
    project_info = project_config.get("projectInfo") or {}
    if isinstance(project_info, dict):
        title = _short_prompt_value(project_info.get("title"))
        description = _short_prompt_value(project_info.get("description"))
        if title:
            lines.append(f"- Project title: {title}")
        if description:
            lines.append(f"- Project description: {description}")

    agents = project_config.get("agents") or []
    if isinstance(agents, list) and agents:
        lines.append("- Roles:")
        for agent in agents[:6]:
            if not isinstance(agent, dict):
                continue
            name = _short_prompt_value(agent.get("name") or agent.get("id"))
            role = _short_prompt_value(
                agent.get("actor_role")
                or agent.get("actorRole")
                or agent.get("role_division")
                or agent.get("roleDivision")
            )
            system_prompt = _short_prompt_value(agent.get("system_prompt"))
            role_bits = [bit for bit in (role, system_prompt) if bit]
            detail = f" - {'; '.join(role_bits)}" if role_bits else ""
            if name:
                lines.append(f"  - {name}{detail}")

    issueboard = project_config.get("issueboard") or {}
    if isinstance(issueboard, dict):
        current_issue_id = _short_prompt_value(issueboard.get("current_issue_id"))
        if current_issue_id:
            lines.append(f"- Current issue: {current_issue_id}")
        issues = issueboard.get("issues") or []
        if isinstance(issues, list) and issues:
            lines.append("- Issues:")
            for issue in issues[:6]:
                if not isinstance(issue, dict):
                    continue
                title = _short_prompt_value(issue.get("title") or issue.get("id"))
                description = _short_prompt_value(issue.get("description"))
                owner = _short_prompt_value(issue.get("person_in_charge"))
                parts = [part for part in (description, f"owner: {owner}" if owner else "") if part]
                if title:
                    suffix = f" - {'; '.join(parts)}" if parts else ""
                    lines.append(f"  - {title}{suffix}")

    chat = project_config.get("chat") or {}
    messages = chat.get("messages") if isinstance(chat, dict) else None
    if isinstance(messages, list) and messages:
        lines.append("- Generated kickoff/questions:")
        for message in messages[:3]:
            if not isinstance(message, dict):
                continue
            agent_name = _short_prompt_value(message.get("agent_name"))
            content = _short_prompt_value(message.get("content"))
            if content:
                prefix = f"{agent_name}: " if agent_name else ""
                lines.append(f"  - {prefix}{content}")

    if len(lines) == 1:
        lines.append("No generated PBL workspace details are available.")
    return "\n".join(lines)


async def _generate_pbl_actions(
    outline: SceneOutline,
    content: dict[str, Any],
    *,
    language_model_id: str,
    ctx: SceneGenerationContext | None,
    agents: list[AgentInfo] | None,
    teacher_context: str,
    language_directive: str,
) -> list[dict[str, Any]]:
    """PBL-actions LLM call.

    Direct port of upstream `generateSceneActions` pbl branch
    (lines 1262-1288). Builds the pbl-actions prompt with title /
    description / keyPoints + projectTopic / projectDescription
    pulled from outline.pblConfig (or outline title/description when
    pblConfig is absent — the Phase 4 stub case).

    Falls back to `_generate_default_pbl_actions` when the prompt
    template is missing OR the LLM returns zero actions OR the LLM
    call fails.

    LearnPuddle also feeds the generated projectConfig and private
    teacher context into this prompt so the handoff names the actual
    roles, first issue, deliverable, and class-guide constraints.
    """
    pbl_config = outline.get("pblConfig") or {}
    project_topic = pbl_config.get("projectTopic") or outline.get("title", "")
    project_description = pbl_config.get("projectDescription") or outline.get("description", "")

    agents_text = format_agents_for_prompt(agents)
    course_context = build_course_context(ctx)

    key_points = outline.get("keyPoints") or []
    key_points_text = "\n".join(f"{i + 1}. {p}" for i, p in enumerate(key_points))

    try:
        prompts = load_generation_prompt(
            "pbl-actions",
            {
                "title": outline.get("title", ""),
                "keyPoints": key_points_text,
                "description": outline.get("description", ""),
                "projectTopic": project_topic,
                "projectDescription": project_description,
                "projectWorkspace": _format_pbl_project_for_prompt(content.get("projectConfig")),
                "teacherContext": teacher_context,
                "hasTeacherContext": bool(teacher_context.strip()),
                "courseContext": course_context,
                "agents": agents_text,
                "languageDirective": language_directive,
            },
        )
    except MaicConfigError:
        _logger.warning("PBL-actions prompt missing — using default fallback.")
        return _generate_default_pbl_actions(outline)

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
            "PBL-actions LLM call failed for %s: %s",
            outline.get("title", "?"),
            exc,
        )
        return _generate_default_pbl_actions(outline)

    actions = parse_actions_from_structured_output(response, scene_type="pbl")

    if actions:
        return _process_actions(actions, [], agents)
    return _generate_default_pbl_actions(outline)


def _generate_default_pbl_actions(
    _outline: SceneOutline,
) -> list[dict[str, Any]]:
    """Default PBL actions when the LLM returns nothing usable.

    Mirrors upstream `generateDefaultPBLActions` (lines 1296-1305). A
    single speech that frames the PBL phase as a project kickoff.
    """
    return [
        {
            "id": f"action_{_nanoid_8()}",
            "type": "speech",
            "title": "PBL 项目介绍",  # "PBL project introduction"
            "text": ("现在让我们开始一个项目式学习活动。" "请选择你的角色，查看任务看板，开始协作完成项目。"),
            # ^ "Now let's start a project-based learning activity.
            # Please select your role, check the task board, and
            # begin collaborating to complete the project."
        }
    ]


# ── Interactive actions (MAIC-422.6) ──────────────────────────────


async def _generate_interactive_actions(
    outline: SceneOutline,
    content: dict[str, Any],  # noqa: ARG001  # kept for shape parity
    *,
    language_model_id: str,
    ctx: SceneGenerationContext | None,
    agents: list[AgentInfo] | None,
    language_directive: str,
) -> list[dict[str, Any]]:
    """Interactive-actions LLM call.

    Direct port of upstream `generateSceneActions` interactive branch
    (lines 1234-1260). Builds the interactive-actions prompt with
    title / description / keyPoints + conceptName + designIdea +
    course context + agents roster.

    Phase 4 sources `conceptName` and `designIdea` from
    `outline.widgetOutline` (Ultra Mode shape) with a fallback to
    legacy `outline.interactiveConfig` if present. Default
    `conceptName = outline.title` and `designIdea = ""` mirror
    upstream lines 1241-1242.

    Falls back to `_generate_default_interactive_actions` when the
    prompt template is missing OR the LLM returns zero actions OR
    the LLM call fails.
    """
    widget_outline = outline.get("widgetOutline") or {}
    legacy_config = outline.get("interactiveConfig") or {}

    concept_name = (
        widget_outline.get("concept")
        or legacy_config.get("conceptName")
        or outline.get("title", "")
    )
    design_idea = widget_outline.get("designIdea") or legacy_config.get("designIdea") or ""

    agents_text = format_agents_for_prompt(agents)
    course_context = build_course_context(ctx)

    key_points = outline.get("keyPoints") or []
    key_points_text = "\n".join(f"{i + 1}. {p}" for i, p in enumerate(key_points))

    try:
        prompts = load_generation_prompt(
            "interactive-actions",
            {
                "title": outline.get("title", ""),
                "keyPoints": key_points_text,
                "description": outline.get("description", ""),
                "conceptName": concept_name,
                "designIdea": design_idea,
                "courseContext": course_context,
                "agents": agents_text,
                "languageDirective": language_directive,
            },
        )
    except MaicConfigError:
        _logger.warning("Interactive-actions prompt missing — using default fallback.")
        return _generate_default_interactive_actions(outline)

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
            "Interactive-actions LLM call failed for %s: %s",
            outline.get("title", "?"),
            exc,
        )
        return _generate_default_interactive_actions(outline)

    actions = parse_actions_from_structured_output(response, scene_type="interactive")

    if actions:
        return _process_actions(actions, [], agents)
    return _generate_default_interactive_actions(outline)


def _generate_default_interactive_actions(
    _outline: SceneOutline,
) -> list[dict[str, Any]]:
    """Default interactive actions when the LLM returns nothing usable.

    Mirrors upstream `generateDefaultInteractiveActions` (lines
    1566-1575). A single speech that frames the widget as an
    exploration prompt.
    """
    return [
        {
            "id": f"action_{_nanoid_8()}",
            "type": "speech",
            "title": "交互引导",  # "interactive introduction"
            "text": ("现在让我们通过交互式可视化来探索这个概念。" "请尝试操作页面中的元素，观察变化。"),
            # ^ "Now let's explore this concept through an interactive
            # visualization. Try operating the elements on the page
            # and observe how things change."
        }
    ]


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
         are provided). If missing or invalid, pick a deterministic
         student (or non-teacher) from the roster.
    """
    element_ids = {el.get("id") for el in elements if el.get("id")}
    agent_ids = {a.get("id") for a in (agents or []) if a.get("id")}
    student_agents = [a for a in (agents or []) if a.get("role") == "student"]
    non_teacher_agents = [a for a in (agents or []) if a.get("role") != "teacher"]

    processed: list[dict[str, Any]] = []
    speech_index = 0
    for action in actions:
        # Ensure each action has an ID.
        proc = dict(action)
        if not proc.get("id"):
            proc["id"] = f"action_{_nanoid_8()}"

        # Validate slide element targets.
        if proc.get("type") in {"spotlight", "laser", "play_video"}:
            current = proc.get("elementId")
            if not current or current not in element_ids:
                if elements:
                    typed_elements = [
                        el for el in elements
                        if proc.get("type") != "play_video" or el.get("type") == "video"
                    ]
                    fallback_source = typed_elements or elements
                    fallback = fallback_source[0].get("id")
                    if fallback:
                        proc["elementId"] = fallback
                        _logger.warning(
                            "Invalid %s elementId %r, falling back to: %s",
                            proc.get("type"),
                            current,
                            fallback,
                        )

        # Validate speech.agentId. Text objects in the upstream action
        # schema may omit a speaker, but LearnPuddle needs explicit
        # speaker IDs for TTS voice, handoff UI, and transcript sync.
        if proc.get("type") == "speech" and agents:
            current = proc.get("agentId")
            if current and current in agent_ids:
                pass
            else:
                pool = agents or []
                if pool:
                    picked = pool[speech_index % len(pool)]
                    proc["agentId"] = picked.get("id")
                    _logger.warning(
                        "Speech agentId %r invalid, assigned: %s (%s)",
                        current or "(none)",
                        picked.get("id"),
                        picked.get("name"),
                    )
            speech_index += 1

        # Validate discussion.agentId.
        if proc.get("type") == "discussion" and agents:
            current = proc.get("agentId")
            if current and current in agent_ids:
                pass  # agent valid — keep
            else:
                pool = student_agents or non_teacher_agents
                if pool:
                    picked = _stable_agent_pick(pool, proc)
                    _logger.warning(
                        "Discussion agentId %r invalid, assigned: %s (%s)",
                        current or "(none)",
                        picked.get("id"),
                        picked.get("name"),
                    )
                    proc["agentId"] = picked.get("id")

        processed.append(proc)
    return processed


def _stable_agent_pick(
    agents: list[AgentInfo],
    action: dict[str, Any],
) -> AgentInfo:
    """Pick a deterministic repair target for invalid discussion agent ids."""
    if len(agents) == 1:
        return agents[0]
    seed = "|".join(
        str(action.get(key) or "") for key in ("id", "topic", "prompt", "title", "text")
    )
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return agents[int(digest[:8], 16) % len(agents)]


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
            actions.append(
                {
                    "id": f"action_{_nanoid_8()}",
                    "type": "spotlight",
                    "title": "聚焦重点",  # "focus on key points"
                    "elementId": first_id,
                }
            )

    key_points = outline.get("keyPoints") or []
    if key_points:
        speech_text = "。".join(key_points) + "。"
    else:
        speech_text = outline.get("description") or outline.get("title") or ""
    actions.append(
        {
            "id": f"action_{_nanoid_8()}",
            "type": "speech",
            "title": "场景讲解",  # "scene narration"
            "text": speech_text,
        }
    )

    return actions


def _nanoid_8() -> str:
    """8-char URL-safe ID. Same shape as scene_builder._nanoid_8."""
    raw = secrets.token_urlsafe(6).replace("-", "").replace("_", "")[:8]
    if len(raw) < 8:
        raw = (raw + secrets.token_urlsafe(4))[:8]
    return raw


# ── Stage 3 orchestrator (MAIC-422.8) ─────────────────────────────


async def generate_full_scenes(
    outlines: list[SceneOutline],
    *,
    language_model_id: str = "stub",
    language_directive: str = "",
    agents: list[AgentInfo] | None = None,
    user_profile: str = "",
    teacher_context: str = "",
    stage_id: str | None = None,
    callbacks: GenerationCallbacks | None = None,
) -> list[dict[str, Any]]:
    """Stage 3: generate full scenes (parallel).

    Direct port of upstream `generateFullScenes` (lines 94-150). Runs
    every outline through `_generate_single_scene` in parallel via
    `asyncio.gather`; preserves outline order in the returned list;
    drops scenes whose generation failed (logged via callbacks.onError).

    Phase 4 simplification: no `StageStore` parameter. The upstream
    stage store is the in-app classroom-editor state; Phase 4 returns
    Scene dicts directly so the Celery finalize task (Session 6) can
    persist them via the WS HTTP route.

    The `ctx` per-scene is built from outline ordering — pageIndex /
    totalPages / allTitles / previousSpeeches let the actions LLM
    write narration that flows naturally between scenes.

    Args:
        outlines: from Stage 1 (outline_generator).
        language_model_id: forwarded to every LLM call.
        language_directive: shared across all scenes (set by Stage 1).
        agents: forwarded to scene-actions for discussion validation.
        user_profile: optional per-student profile string.
        teacher_context: private teacher planning context from Step 2.
        callbacks: onProgress fires after each scene completes (best-
                   effort — concurrent updates are non-atomic but the
                   final count converges to the total).

    Returns:
        List of Scene dicts (the build_complete_scene output) in
        outline order, with failures elided. The caller in
        pipeline_runner stores these on session["scenes"].
    """
    on_progress = callbacks and callbacks.get("onProgress")
    on_error = callbacks and callbacks.get("onError")

    # Stage id for build_complete_scene. The Celery finalize task
    # (Session 6) will attach the real Classroom Stage; until then
    # generation runs against a placeholder so the output Scene dict
    # is well-formed.
    if stage_id is None:
        stage_id = f"stage_{_nanoid_8()}"

    # Mirror upstream's media-id uniquification pass (line 92 of
    # outline_generator forwards but Stage 3 also runs it as a
    # belt+suspenders before content generation).
    outlines = uniquify_media_element_ids(outlines)

    total = len(outlines)
    completed = {"n": 0}

    if on_progress:
        on_progress(
            {
                "stage": 3,
                "completed": 0,
                "total": total,
                "message": f"Generating {total} scenes in parallel...",
            }
        )

    all_titles = [o.get("title", "") for o in outlines]
    # Per-scene `previousSpeeches` is best-effort because scenes run
    # in parallel — we can't know what an earlier scene's speech
    # actions will be at dispatch time. For Phase 4 we ship the empty
    # list (matches the v1 service behavior). When the Celery chain
    # lands in Session 6, the chord can serialize this if needed.
    previous_speeches: list[str] = []

    async def _run_one(index: int, outline: SceneOutline) -> tuple[int, dict[str, Any] | None]:
        ctx: SceneGenerationContext = {
            "pageIndex": index + 1,
            "totalPages": total,
            "allTitles": all_titles,
            "previousSpeeches": previous_speeches,
        }
        try:
            scene = await _generate_single_scene(
                outline,
                language_model_id=language_model_id,
                language_directive=language_directive,
                agents=agents,
                user_profile=user_profile,
                ctx=ctx,
                stage_id=stage_id,
                teacher_context=teacher_context,
            )
        except Exception as exc:  # noqa: BLE001
            _logger.error("Failed to generate scene %r: %s", outline.get("title", "?"), exc)
            if on_error:
                on_error(f"Failed to generate scene {outline.get('title', '?')}: {exc}")
            scene = None

        completed["n"] += 1
        if on_progress:
            on_progress(
                {
                    "stage": 3,
                    "completed": completed["n"],
                    "total": total,
                    "message": f"Completed {completed['n']}/{total} scenes",
                }
            )
        return index, scene

    results = await asyncio.gather(*[_run_one(i, o) for i, o in enumerate(outlines)])

    # Sort by original index; drop failures.
    results.sort(key=lambda r: r[0])
    return [scene for _, scene in results if scene is not None]


async def _generate_single_scene(
    outline: SceneOutline,
    *,
    language_model_id: str,
    language_directive: str,
    agents: list[AgentInfo] | None,
    user_profile: str,
    ctx: SceneGenerationContext | None,
    stage_id: str,
    teacher_context: str = "",
    tenant_config: Any | None = None,
    image_generation_enabled: bool = False,
    video_generation_enabled: bool = False,
) -> dict[str, Any] | None:
    """Two-step single-scene generator.

    Direct port of upstream `generateSingleScene` (lines 158-179):
        Step 3.1: generate_scene_content
        Step 3.2: generate_scene_actions
    Then assembles via `build_complete_scene`.
    Then resolves `gen_img_*` / `gen_vid_*` placeholders via the
    Phase 9 media orchestrator (MAIC-915) when ``tenant_config`` is
    supplied. A None tenant_config is the "no media gen" opt-out;
    placeholders are preserved verbatim in the scene.

    Returns None when content generation fails (caller drops the
    scene + emits an onError). Actions failure → falls back to the
    per-type default (handled inside generate_scene_actions).
    """
    _logger.info("Step 3.1: generating content for: %s", outline.get("title", "?"))
    content = await generate_scene_content(
        outline,
        language_model_id=language_model_id,
        options={
            "agents": agents or [],
            "teacherContext": teacher_context,
            "languageDirective": language_directive,
            "imageGenerationEnabled": image_generation_enabled,
            "videoGenerationEnabled": video_generation_enabled,
        },
    )
    if not content:
        _logger.error("Failed to generate content for: %s", outline.get("title", "?"))
        return None

    _logger.info("Step 3.2: generating actions for: %s", outline.get("title", "?"))
    actions = await generate_scene_actions(
        outline,
        content,
        language_model_id=language_model_id,
        options={
            "ctx": ctx,
            "agents": agents or [],
            "userProfile": user_profile,
            "teacherContext": teacher_context,
            "languageDirective": language_directive,
        },
    )
    _logger.info("Generated %d actions for: %s", len(actions), outline.get("title", "?"))

    scene = build_complete_scene(outline, content, actions, stage_id)
    # Phase 9 MAIC-915: dispatch media orchestrator to resolve any
    # gen_img_*/gen_vid_* placeholders. No-op when tenant_config is
    # None or scene type is non-slide; failures preserve placeholders.
    scene = await resolve_scene_media(scene, outline, tenant_config)
    return scene
