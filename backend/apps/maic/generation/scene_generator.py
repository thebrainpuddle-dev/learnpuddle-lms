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

    # ── Quiz branch (MAIC-422.2) ──
    if scene_type == "quiz":
        return await _generate_quiz_content(
            outline,
            language_model_id=language_model_id,
            language_directive=options.get("languageDirective", ""),
        )

    # ── Interactive branch — MAIC-422.5 (Session 4) ──
    if scene_type == "interactive":
        _logger.info(
            "scene_type=interactive: branch lands in MAIC-422.5 "
            "(Session 4); returning None for now."
        )
        return None

    # ── PBL branch — MAIC-422.4 STUB ──
    if scene_type == "pbl":
        return _generate_pbl_content_stub(outline)

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
    key_points_text = "\n".join(
        f"{i + 1}. {p}" for i, p in enumerate(key_points)
    )
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

    _logger.debug(
        "Generating quiz content for: %s", outline.get("title", "?")
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
            "options": (
                None if is_text else _normalize_quiz_options(q.get("options"))
            ),
            "answer": (
                None if is_text else _normalize_quiz_answer(q)
            ),
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


# ── PBL content STUB (MAIC-422.4) ─────────────────────────────────


def _generate_pbl_content_stub(outline: SceneOutline) -> dict[str, Any]:
    """STUB — programmatic PBL content (no LLM call).

    The real PBL content generator is upstream's
    `lib/pbl/generate-pbl.ts` (414 LoC + 4 MCP modules: project-info,
    agent, issueboard, chat). It runs an agentic tool-calling loop
    that incrementally constructs a `PBLProjectConfig`. Per MAIC-432
    research, that work is **deferred to Phase 5+**.

    Phase 4 produces a minimal-but-well-formed `projectConfig` so
    the playback engine can render a placeholder PBL scene without
    a runtime crash. The output uses outline.title /
    outline.description / outline.pblConfig (when present) to seed
    `projectInfo`. Agents + issueboard + chat ship as empty lists —
    the frontend treats this as "PBL not configured yet".

    Returns a `{"projectConfig": ...}` dict matching the
    GeneratedPBLContent shape upstream's pbl-actions branch + scene-
    builder both expect.
    """
    pbl_config = outline.get("pblConfig") or {}
    project_topic = pbl_config.get("projectTopic") or outline.get("title", "")
    project_description = (
        pbl_config.get("projectDescription")
        or outline.get("description", "")
    )

    return {
        "projectConfig": {
            "projectInfo": {
                "title": project_topic,
                "description": project_description,
            },
            "agents": [],
            "issueboard": {
                "agent_ids": [],
                "issues": [],
                "current_issue_id": None,
            },
            "chat": {"messages": []},
            "selectedRole": None,
        }
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
      - slide → slide-actions LLM call (MAIC-422.1)
      - quiz → quiz-actions LLM call (MAIC-422.3)
      - interactive → interactive-actions (MAIC-422.6, Session 4)
      - pbl → pbl-actions LLM call (MAIC-422.4, this chunk)

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

    # ── Interactive branch — MAIC-422.6 (Session 4) ──
    if outline.get("type") == "interactive" and "html" in content:
        _logger.info(
            "generate_scene_actions: interactive branch lands in "
            "MAIC-422.6 (Session 4); returning [] for now."
        )
        return []

    # ── PBL branch (MAIC-422.4) ──
    if outline.get("type") == "pbl" and "projectConfig" in content:
        return await _generate_pbl_actions(
            outline,
            content,
            language_model_id=language_model_id,
            ctx=options.get("ctx"),
            agents=agents,
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
    key_points_text = "\n".join(
        f"{i + 1}. {p}" for i, p in enumerate(key_points)
    )

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
        _logger.warning(
            "Quiz-actions prompt missing — using default fallback."
        )
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

    actions = parse_actions_from_structured_output(
        response, scene_type="quiz"
    )

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
                f"{o.get('value', '?')}. {o.get('label', '')}"
                if isinstance(o, dict)
                else str(o)
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


async def _generate_pbl_actions(
    outline: SceneOutline,
    content: dict[str, Any],  # noqa: ARG001  # kept for shape parity
    *,
    language_model_id: str,
    ctx: SceneGenerationContext | None,
    agents: list[AgentInfo] | None,
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

    Note: `content` is unused in this branch — upstream also doesn't
    feed projectConfig into the actions prompt. The pbl-actions
    template uses pblConfig + outline metadata only.
    """
    pbl_config = outline.get("pblConfig") or {}
    project_topic = pbl_config.get("projectTopic") or outline.get("title", "")
    project_description = (
        pbl_config.get("projectDescription")
        or outline.get("description", "")
    )

    agents_text = format_agents_for_prompt(agents)
    course_context = build_course_context(ctx)

    key_points = outline.get("keyPoints") or []
    key_points_text = "\n".join(
        f"{i + 1}. {p}" for i, p in enumerate(key_points)
    )

    try:
        prompts = load_generation_prompt(
            "pbl-actions",
            {
                "title": outline.get("title", ""),
                "keyPoints": key_points_text,
                "description": outline.get("description", ""),
                "projectTopic": project_topic,
                "projectDescription": project_description,
                "courseContext": course_context,
                "agents": agents_text,
                "languageDirective": language_directive,
            },
        )
    except MaicConfigError:
        _logger.warning(
            "PBL-actions prompt missing — using default fallback."
        )
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

    actions = parse_actions_from_structured_output(
        response, scene_type="pbl"
    )

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
            "text": (
                "现在让我们开始一个项目式学习活动。"
                "请选择你的角色，查看任务看板，开始协作完成项目。"
            ),
            # ^ "Now let's start a project-based learning activity.
            # Please select your role, check the task board, and
            # begin collaborating to complete the project."
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
