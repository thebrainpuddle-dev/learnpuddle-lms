"""Materialize v2 generation jobs into durable LMS classroom artifacts."""
from __future__ import annotations

import logging
import re
from typing import Any

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.courses.maic_models import MAICClassroom, TenantAIConfig
from apps.courses.maic_media_safety import scrub_placeholder_image_srcs
from apps.courses.models import Content, Course, Module
from apps.maic.models import MaicGenerationJob
from apps.maic.orchestration.registry import DEFAULT_AGENTS
from apps.maic.runtime_contract import (
    RUNTIME_ACTION_TYPES,
    require_valid_classroom_runtime_contract,
)
from apps.maic_pbl.models import MaicPBLSession


logger = logging.getLogger("apps.maic.generation.materializer")


_LANGUAGE_CODES = {
    "english": "en",
    "spanish": "es",
    "french": "fr",
    "german": "de",
    "hindi": "hi",
    "arabic": "ar",
    "chinese": "zh",
    "japanese": "ja",
    "korean": "ko",
    "portuguese": "pt",
}

_DEFAULT_CANVAS_WIDTH = 1000.0
_DEFAULT_CANVAS_RATIO = 0.5625
_DEFAULT_CANVAS_HEIGHT = _DEFAULT_CANVAS_WIDTH * _DEFAULT_CANVAS_RATIO

_TEXT_TYPE_ALIASES = {
    "body",
    "bullet",
    "bullets",
    "caption",
    "content",
    "final",
    "formative",
    "heading",
    "paragraph",
    "pbl",
    "question",
    "richtext",
    "spotlight",
    "teacher",
    "textbox",
    "title",
    "whiteboard",
}
_IMAGE_TYPE_ALIASES = {"diagram", "illustration", "img", "photo", "picture"}
_SHAPE_NAMES = {"circle", "ellipse", "line", "rect", "rectangle", "triangle"}
_TARGETED_ACTIONS = {
    "highlight",
    "laser",
    "play_video",
    "spotlight",
    "wb_delete",
    "wb_edit_code",
}
_PROMPT_LEAK_PHRASES = (
    "all textelement height values",
    "aspect ratio 16:9",
    "block comments",
    "canvas size",
    "do not include explanations",
    "do not wrap your json",
    "json code",
    "output pure json",
    "provided generated image ids",
    "use an age-appropriate classroom diagram",
)
_GENERIC_FILLER_TEXTS = {
    "point one",
    "point two",
    "point three",
    "point four",
    "point five",
    "point six",
    "point seven",
    "point eight",
    "point nine",
    "point ten",
    "point eleven",
    "acknowledgments",
    "additional resources",
    "conclusion",
    "final thoughts",
    "glossary",
    "references",
}
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")


def materialize_generation_artifact(
    job: MaicGenerationJob,
    scenes: list[dict[str, Any]],
) -> dict[str, Any]:
    """Create/update the playable ``MAICClassroom`` for a v2 job.

    The generation pipeline's DB row is the durable job contract; the LMS
    artifact is the durable playback/assignment contract. This bridge is
    intentionally idempotent: retrying ``finalize_task`` updates the same
    classroom/content rows when their ids are already present in ``job.result``.
    """
    if not job.created_by_id:
        logger.info(
            "Skipping LMS materialization for job=%s because created_by is empty",
            job.id,
        )
        return {}

    caller_scenes = scenes
    requirements = dict(job.requirements or {})
    prior_result = dict(job.result or {})
    agents = _resolve_agents(requirements)
    scenes = _normalize_scenes_for_playback(scenes, agents)
    runtime_contract = require_valid_classroom_runtime_contract(
        scenes,
        agents,
        allow_unresolved_images=True,
    ).to_dict()
    topic = _clean_title(requirements.get("topic") or "AI Classroom", max_len=500)
    title = _clean_title(
        requirements.get("contentTitle") or requirements.get("title") or topic,
        max_len=300,
    )
    image_fill_classroom_id: str | None = None

    with transaction.atomic():
        scenes = _attach_pbl_sessions(job, scenes, prior_result)
        if scrub_placeholder_image_srcs(scenes):
            logger.warning(
                "Scrubbed placeholder image URLs while materializing MAIC job=%s",
                job.id,
            )
        # `finalize_task` has already placed the incoming list object
        # into job.result["scenes"]. Keep that contract intact by
        # replacing the list contents with the normalized/materialized
        # scenes, including pblSessionId attachments.
        caller_scenes[:] = scenes
        slides, scene_slide_bounds = _extract_slides_and_bounds(scenes)
        speech_count = _count_speech_actions(scenes)
        image_fill_required = _tenant_image_provider_enabled(
            job.tenant_id,
        ) and _has_unresolved_image_elements(slides)
        classroom = _get_existing_classroom(prior_result, job.tenant_id)
        module = _resolve_module(requirements.get("moduleId"), job.tenant_id)
        course = _resolve_course(requirements.get("courseId"), job.tenant_id)
        if module is not None:
            course = module.course

        if classroom is None:
            classroom = MAICClassroom.all_objects.create(
                tenant_id=job.tenant_id,
                creator_id=job.created_by_id,
                title=title,
                topic=topic,
            )

        classroom.title = title
        classroom.description = _clean_text(requirements.get("description"))
        classroom.topic = topic
        classroom.language = _language_code(requirements.get("language"))
        classroom.status = "READY"
        classroom.error_message = ""
        classroom.course = course
        classroom.is_public = _resolve_is_public(requirements)
        classroom.scene_count = len(scenes)
        classroom.estimated_minutes = _estimate_minutes(scenes, requirements)
        classroom.config = {
            **dict(classroom.config or {}),
            "schema": "maic_v2",
            "generationJobId": job.id,
            "source": "maic_v2_generation",
            "agents": agents,
            "language": requirements.get("language") or "English",
            "level": requirements.get("level") or "intermediate",
            "sceneCount": len(scenes),
            "ttsMode": "live",
            "runtimeContract": runtime_contract,
        }
        classroom.content_scenes = scenes
        classroom.content_agents = agents
        classroom.content_meta = {
            **dict(classroom.content_meta or {}),
            "slides": slides,
            "sceneSlideBounds": scene_slide_bounds,
            "source": "maic_v2_generation",
            "generationJobId": job.id,
            "languageDirective": prior_result.get("languageDirective", ""),
            "generatedAt": timezone.now().isoformat(),
            "audioManifest": _audio_manifest(speech_count),
            "runtimeContract": runtime_contract,
        }
        classroom.generation_phase = "complete"
        classroom.phase_scene_index = len(scenes)
        classroom.scenes_ready = len(scenes)
        classroom.images_pending = image_fill_required
        classroom.last_progress_at = timezone.now()
        if classroom.started_at is None:
            classroom.started_at = job.created_at
        classroom.save(
            update_fields=[
                "title",
                "description",
                "topic",
                "language",
                "status",
                "error_message",
                "course",
                "is_public",
                "scene_count",
                "estimated_minutes",
                "config",
                "content_scenes",
                "content_agents",
                "content_meta",
                "generation_phase",
                "phase_scene_index",
                "scenes_ready",
                "images_pending",
                "started_at",
                "last_progress_at",
                "updated_at",
            ]
        )

        if image_fill_required:
            image_fill_classroom_id = str(classroom.id)

        content = _materialize_content(
            prior_result=prior_result,
            module=module,
            classroom=classroom,
            title=title,
            job=job,
        )

    if image_fill_classroom_id:
        _enqueue_fill_classroom_images(image_fill_classroom_id)

    artifact = {
        "classroomId": str(classroom.id),
        "classroom_id": str(classroom.id),
        "contentId": str(content.id) if content else None,
        "content_id": str(content.id) if content else None,
        "courseId": str(classroom.course_id) if classroom.course_id else None,
        "course_id": str(classroom.course_id) if classroom.course_id else None,
        "url": f"/teacher/ai-classroom/{classroom.id}",
        "studentUrl": f"/student/ai-classroom/{classroom.id}",
        "scenesCount": len(scenes),
    }
    return artifact


def _get_existing_classroom(
    result: dict[str, Any],
    tenant_id: int,
) -> MAICClassroom | None:
    classroom_id = result.get("classroomId") or result.get("classroom_id")
    if not classroom_id:
        return None
    return (
        MAICClassroom.all_objects.select_for_update()
        .filter(pk=classroom_id, tenant_id=tenant_id)
        .first()
    )


_PLACEHOLDER_IMAGE_HOSTS = {
    "example.com",
    "www.example.com",
    "example.org",
    "www.example.org",
    "example.net",
    "www.example.net",
    "placehold.co",
    "placeholder.com",
    "via.placeholder.com",
    "source.unsplash.com",
}


def _tenant_image_provider_enabled(tenant_id: int) -> bool:
    config = TenantAIConfig.objects.filter(tenant_id=tenant_id).first()
    if config is None:
        return False
    provider = (config.image_provider or "").strip().lower()
    return bool(provider and provider != "disabled")


def _has_unresolved_image_elements(slides: list[dict[str, Any]]) -> bool:
    for slide in slides:
        if not isinstance(slide, dict):
            continue
        elements = slide.get("elements")
        if not isinstance(elements, list):
            continue
        for element in elements:
            if not isinstance(element, dict) or element.get("type") != "image":
                continue
            meta = element.get("meta")
            if isinstance(meta, dict) and meta.get("imageProviderDisabled"):
                continue
            src = str(element.get("src") or "").strip()
            content = str(element.get("content") or "").strip()
            if _is_safe_image_src(src):
                continue
            if src or content:
                return True
    return False


def _is_safe_image_src(src: str) -> bool:
    if not src:
        return False
    if src.startswith("/"):
        return True
    if not (src.startswith("https://") or src.startswith("http://")):
        return False
    try:
        host = src.split("/", 3)[2].split("@")[-1].split(":")[0].lower().rstrip(".")
    except IndexError:
        return False
    if host in _PLACEHOLDER_IMAGE_HOSTS:
        return False
    return not (
        host.endswith(".example.com")
        or host.endswith(".example.org")
        or host.endswith(".example.net")
    )


def _enqueue_fill_classroom_images(classroom_id: str) -> None:
    try:
        from apps.courses.maic_tasks import fill_classroom_images

        fill_classroom_images.delay(classroom_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Could not enqueue MAIC v2 image fill classroom_id=%s: %s",
            classroom_id,
            exc,
        )


def _materialize_content(
    *,
    prior_result: dict[str, Any],
    module: Module | None,
    classroom: MAICClassroom,
    title: str,
    job: MaicGenerationJob,
) -> Content | None:
    if module is None:
        return None

    content_id = prior_result.get("contentId") or prior_result.get("content_id")
    content = None
    if content_id:
        content = (
            Content.all_objects.select_for_update()
            .filter(
                pk=content_id,
                module__course__tenant_id=job.tenant_id,
            )
            .first()
        )

    if content is None:
        max_order = (
            Content.objects.filter(module=module)
            .aggregate(max_order=Max("order"))
            .get("max_order")
        )
        content = Content.objects.create(
            module=module,
            title=title,
            content_type="AI_CLASSROOM",
            order=(max_order or 0) + 1,
            maic_classroom=classroom,
            text_content="",
            meta_json={
                "source": "maic_v2_generation",
                "generation_job_id": job.id,
            },
        )
    else:
        content.module = module
        content.title = title
        content.content_type = "AI_CLASSROOM"
        content.maic_classroom = classroom
        content.is_active = True
        meta = dict(content.meta_json or {})
        meta.update({
            "source": "maic_v2_generation",
            "generation_job_id": job.id,
        })
        content.meta_json = meta
        content.save(
            update_fields=[
                "module",
                "title",
                "content_type",
                "maic_classroom",
                "is_active",
                "meta_json",
                "updated_at",
            ]
        )
    return content


def _attach_pbl_sessions(
    job: MaicGenerationJob,
    scenes: list[dict[str, Any]],
    prior_result: dict[str, Any],
) -> list[dict[str, Any]]:
    """Attach durable PBL sessions to generated PBL scenes.

    Generation produces an OpenMAIC-shaped `projectConfig`. SaaS playback
    needs a tenant-scoped row too so the frontend can use the real PBL
    WebSocket and issue/chat progress can persist across refreshes. This
    runs during materialization where tenant and creator are known.
    """
    prior_session_ids = _prior_pbl_session_ids_by_scene_id(prior_result)
    attached: list[dict[str, Any]] = []

    for scene in scenes:
        if not isinstance(scene, dict) or scene.get("type") != "pbl":
            attached.append(scene)
            continue

        content = scene.get("content")
        if not isinstance(content, dict):
            attached.append(scene)
            continue

        project_config = content.get("projectConfig")
        if not isinstance(project_config, dict):
            attached.append(scene)
            continue

        scene_id = str(scene.get("id") or "")
        existing_session_id = (
            content.get("pblSessionId")
            or prior_session_ids.get(scene_id)
        )
        session = _get_existing_pbl_session(existing_session_id, job.tenant_id)
        if session is None:
            session = MaicPBLSession.objects.create(
                tenant_id=job.tenant_id,
                owner_id=job.created_by_id,
                topic=_pbl_topic(project_config, scene),
                language=_language_code((job.requirements or {}).get("language")),
                agent_count=_pbl_issue_count(project_config),
                status=MaicPBLSession.STATUS_ACTIVE,
                project_config=project_config,
                chat_messages=_pbl_initial_chat(project_config),
            )
        else:
            session.project_config = project_config
            session.topic = _pbl_topic(project_config, scene)
            session.agent_count = _pbl_issue_count(project_config)
            if session.status in {
                MaicPBLSession.STATUS_DRAFT,
                MaicPBLSession.STATUS_FAILED,
            }:
                session.status = MaicPBLSession.STATUS_ACTIVE
            if session.owner_id is None:
                session.owner_id = job.created_by_id
            session.save(
                update_fields=[
                    "project_config",
                    "topic",
                    "agent_count",
                    "status",
                    "owner",
                    "updated_at",
                ]
            )

        next_scene = dict(scene)
        next_content = dict(content)
        next_content["pblSessionId"] = str(session.id)
        next_content["pblWsPath"] = f"/ws/maic/pbl/{session.id}/"
        next_scene["content"] = next_content
        attached.append(next_scene)

    return attached


def _prior_pbl_session_ids_by_scene_id(
    prior_result: dict[str, Any],
) -> dict[str, str]:
    ids: dict[str, str] = {}
    prior_scenes = prior_result.get("scenes")
    if not isinstance(prior_scenes, list):
        return ids
    for scene in prior_scenes:
        if not isinstance(scene, dict):
            continue
        content = scene.get("content")
        if not isinstance(content, dict):
            continue
        session_id = content.get("pblSessionId")
        scene_id = scene.get("id")
        if isinstance(scene_id, str) and isinstance(session_id, str):
            ids[scene_id] = session_id
    return ids


def _get_existing_pbl_session(
    session_id: Any,
    tenant_id: int,
) -> MaicPBLSession | None:
    if not session_id:
        return None
    return (
        MaicPBLSession.objects
        .all_tenants()
        .filter(pk=session_id, tenant_id=tenant_id)
        .first()
    )


def _pbl_topic(
    project_config: dict[str, Any],
    scene: dict[str, Any],
) -> str:
    info = project_config.get("projectInfo")
    title = info.get("title") if isinstance(info, dict) else None
    return _clean_title(title or scene.get("title") or "PBL Project", max_len=500)


def _pbl_issue_count(project_config: dict[str, Any]) -> int:
    board = project_config.get("issueboard")
    issues = board.get("issues") if isinstance(board, dict) else None
    return len(issues) if isinstance(issues, list) else 0


def _pbl_initial_chat(project_config: dict[str, Any]) -> list[dict[str, Any]]:
    chat = project_config.get("chat")
    messages = chat.get("messages") if isinstance(chat, dict) else None
    return list(messages) if isinstance(messages, list) else []


def _resolve_course(course_id: Any, tenant_id: int) -> Course | None:
    if not course_id:
        return None
    course = (
        Course.all_objects.all_tenants()
        .filter(pk=course_id, tenant_id=tenant_id, is_deleted=False)
        .first()
    )
    if course is None:
        logger.warning(
            "Ignoring invalid generation course target tenant=%s course=%s",
            tenant_id,
            course_id,
        )
    return course


def _resolve_module(module_id: Any, tenant_id: int) -> Module | None:
    if not module_id:
        return None
    module = (
        Module.objects.select_related("course")
        .filter(
            pk=module_id,
            course__tenant_id=tenant_id,
            course__is_deleted=False,
        )
        .first()
    )
    if module is None:
        logger.warning(
            "Ignoring invalid generation module target tenant=%s module=%s",
            tenant_id,
            module_id,
        )
    return module


def _resolve_agents(requirements: dict[str, Any]) -> list[dict[str, Any]]:
    raw_agents = requirements.get("agents")
    if isinstance(raw_agents, list) and raw_agents:
        return [a for a in raw_agents if isinstance(a, dict)]

    requested = requirements.get("agentCount")
    try:
        agent_count = int(requested)
    except (TypeError, ValueError):
        agent_count = 4
    agent_count = max(1, min(agent_count, len(DEFAULT_AGENTS)))

    return [
        _agent_config_to_maic(agent)
        for agent in list(DEFAULT_AGENTS.values())[:agent_count]
    ]


def _agent_config_to_maic(agent) -> dict[str, Any]:
    voice = agent.voiceConfig
    role = "professor" if agent.role == "teacher" else agent.role
    payload = {
        "id": agent.id,
        "name": agent.name,
        "role": role,
        "avatar": agent.avatar,
        "color": agent.color,
        "personality": agent.persona,
    }
    if voice is not None:
        payload["voiceId"] = voice.voiceId
        payload["voiceProvider"] = voice.providerId
    return payload


def _normalize_scenes_for_playback(
    scenes: list[dict[str, Any]],
    agents: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    default_agent_id = agents[0]["id"] if agents else "default-1"
    valid_agent_ids = {
        str(agent.get("id"))
        for agent in agents
        if isinstance(agent, dict) and agent.get("id")
    }
    normalized: list[dict[str, Any]] = []
    for scene_index, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            continue
        next_scene = dict(scene)
        next_scene = _sanitize_scene_content_for_playback(next_scene)
        valid_element_ids = _element_ids_for_scene(next_scene)
        actions = scene.get("actions")
        if isinstance(actions, list):
            next_actions = []
            seen_speech: set[str] = set()
            speech_count = 0
            max_speech_actions = _max_speech_actions_for_scene(
                next_scene,
                valid_element_ids,
            )
            for action_index, action in enumerate(actions):
                if not isinstance(action, dict):
                    continue
                next_action = dict(action)
                action_type = str(next_action.get("type") or "").strip()
                if action_type not in RUNTIME_ACTION_TYPES:
                    logger.warning(
                        "Dropping unsupported MAIC runtime action type=%r scene=%s",
                        action_type,
                        scene.get("id") or scene_index,
                    )
                    continue
                if action_type == "speech":
                    text = _clean_text(
                        next_action.get("text") or next_action.get("content")
                    )
                    text = _clean_speech_text(text)
                    if not text or _is_prompt_leak_text(text):
                        continue
                    speech_key = _plain_text(text).lower()
                    if (
                        speech_count >= max_speech_actions
                        or _is_generic_filler_text(text)
                        or speech_key in seen_speech
                    ):
                        continue
                    seen_speech.add(speech_key)
                    speech_count += 1
                    next_action["text"] = text
                    next_action.pop("content", None)
                    if str(next_action.get("agentId") or "") not in valid_agent_ids:
                        next_action["agentId"] = default_agent_id
                    next_action.setdefault(
                        "id",
                        f"speech_{scene.get('id', scene_index)}_{action_index}",
                    )
                elif action_type in _TARGETED_ACTIONS:
                    target_id = str(
                        next_action.get("elementId")
                        or next_action.get("targetId")
                        or next_action.get("target")
                        or ""
                    ).strip()
                    if not target_id or target_id not in valid_element_ids:
                        continue
                    next_action["elementId"] = target_id
                    next_action.pop("targetId", None)
                    next_action.pop("target", None)
                elif action_type == "discussion":
                    agent_id = str(next_action.get("agentId") or "").strip()
                    if agent_id not in valid_agent_ids:
                        agent_id = default_agent_id
                    raw_agent_ids = next_action.get("agentIds")
                    agent_ids = [
                        str(value)
                        for value in raw_agent_ids
                        if str(value) in valid_agent_ids
                    ] if isinstance(raw_agent_ids, list) else []
                    if not agent_ids:
                        agent_ids = [agent_id]
                    next_action["agentId"] = agent_id
                    next_action["agentIds"] = agent_ids
                    if next_action.get("sessionType") not in {
                        "classroom",
                        "qa",
                        "roundtable",
                    }:
                        next_action["sessionType"] = "roundtable"
                    if next_action.get("triggerMode") not in {"auto", "manual"}:
                        next_action["triggerMode"] = "auto"
                    next_action["topic"] = _clean_text(
                        next_action.get("topic") or scene.get("title") or "Discussion"
                    )
                    next_action.setdefault(
                        "id",
                        f"discussion_{scene.get('id', scene_index)}_{action_index}",
                    )
                elif action_type == "pause":
                    duration = _number(next_action.get("duration"), 0)
                    next_action["duration"] = max(0, duration)
                elif action_type == "transition":
                    if next_action.get("slideIndex") is not None:
                        try:
                            next_action["slideIndex"] = int(next_action["slideIndex"])
                        except (TypeError, ValueError):
                            next_action.pop("slideIndex", None)
                next_action.setdefault(
                    "id",
                    f"{action_type}_{scene.get('id', scene_index)}_{action_index}",
                )
                next_actions.append(next_action)
                if action_type == "discussion":
                    break
            next_scene["actions"] = next_actions
        normalized.append(next_scene)
    return normalized


def _sanitize_scene_content_for_playback(scene: dict[str, Any]) -> dict[str, Any]:
    content = scene.get("content")
    if not isinstance(content, dict) or content.get("type") != "slide":
        return scene

    next_scene = dict(scene)
    next_content = dict(content)
    raw_slides = next_content.get("slides")
    if isinstance(raw_slides, list):
        next_content["slides"] = [
            _normalize_slide(raw_slide, scene, index)
            for index, raw_slide in enumerate(raw_slides)
            if isinstance(raw_slide, dict)
        ]
    elif isinstance(next_content.get("canvas"), dict):
        next_content["canvas"] = _normalize_slide(next_content["canvas"], scene, 0)
    elif isinstance(next_content.get("elements"), list):
        normalized = _normalize_slide(next_content, scene, 0)
        next_content.update({
            "elements": normalized.get("elements", []),
            "background": normalized.get("background"),
            "viewportSize": normalized.get("viewportSize"),
            "viewportRatio": normalized.get("viewportRatio"),
            "canvasWidth": normalized.get("canvasWidth"),
            "canvasHeight": normalized.get("canvasHeight"),
        })

    next_scene["content"] = next_content
    return next_scene


def _element_ids_for_scene(scene: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for slide in _slides_for_scene(scene):
        for element in slide.get("elements", []):
            if isinstance(element, dict) and element.get("id"):
                ids.add(str(element["id"]))
    return ids


def _max_speech_actions_for_scene(
    scene: dict[str, Any],
    valid_element_ids: set[str],
) -> int:
    scene_type = str(scene.get("type") or "").lower()
    if scene_type == "slide":
        return max(5, min(10, (len(valid_element_ids) * 3) + 1))
    if scene_type == "quiz":
        return 5
    if scene_type in {"interactive", "pbl"}:
        return 8
    return 8


def _clean_speech_text(value: str) -> str:
    text = _clean_text(value)
    lowered = text.lower()
    prefix = "opening speech content:"
    if lowered.startswith(prefix):
        return text[len(prefix):].strip()
    return text


def _extract_slides_and_bounds(
    scenes: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, int]]]:
    slides: list[dict[str, Any]] = []
    bounds: list[dict[str, int]] = []

    for scene_idx, scene in enumerate(scenes):
        scene_slides = _slides_for_scene(scene)
        if scene_slides:
            start = len(slides)
            slides.extend(scene_slides)
            end = len(slides) - 1
            bounds.append({
                "sceneIdx": scene_idx,
                "startSlide": start,
                "endSlide": end,
            })

    return slides, bounds


def _slides_for_scene(scene: dict[str, Any]) -> list[dict[str, Any]]:
    content = scene.get("content") if isinstance(scene, dict) else None
    if not isinstance(content, dict) or content.get("type") != "slide":
        return []

    raw_slides = content.get("slides")
    if isinstance(raw_slides, list) and raw_slides:
        return [
            _normalize_slide(raw_slide, scene, index)
            for index, raw_slide in enumerate(raw_slides)
            if isinstance(raw_slide, dict)
        ]

    canvas = content.get("canvas")
    if isinstance(canvas, dict):
        return [_normalize_slide(canvas, scene, 0)]

    if isinstance(content.get("elements"), list):
        return [_normalize_slide(content, scene, 0)]

    return []


def _normalize_slide(
    raw_slide: dict[str, Any],
    scene: dict[str, Any],
    index: int,
) -> dict[str, Any]:
    elements = raw_slide.get("elements")
    if not isinstance(elements, list):
        elements = []

    viewport_size = _number(raw_slide.get("viewportSize"), 0)
    viewport_ratio = _number(raw_slide.get("viewportRatio"), 0)
    canvas_width = _number(raw_slide.get("canvasWidth"), 0)
    canvas_height = _number(raw_slide.get("canvasHeight"), 0)
    if canvas_width <= 0 and viewport_size > 0:
        canvas_width = viewport_size
    if canvas_height <= 0 and viewport_size > 0 and viewport_ratio > 0:
        canvas_height = viewport_size * viewport_ratio
    if canvas_width <= 0:
        canvas_width = _DEFAULT_CANVAS_WIDTH
    if canvas_height <= 0:
        canvas_height = _DEFAULT_CANVAS_HEIGHT
    normalized_elements = [
        _normalize_element(element, element_index)
        for element_index, element in enumerate(elements)
        if isinstance(element, dict)
    ]
    normalized = {
        "id": str(raw_slide.get("id") or f"{scene.get('id', 'scene')}-slide-{index}"),
        "title": str(raw_slide.get("title") or scene.get("title") or "Slide"),
        "elements": _sanitize_slide_elements(
            normalized_elements,
            canvas_width=canvas_width,
            canvas_height=canvas_height,
        ),
        "background": _normalize_background(raw_slide.get("background")),
        "speakerScript": _first_speech_text(scene.get("actions")),
        "canvasWidth": canvas_width,
        "canvasHeight": canvas_height,
    }
    if viewport_size > 0:
        normalized["viewportSize"] = viewport_size
    if viewport_size > 0 and viewport_ratio > 0:
        normalized["viewportRatio"] = viewport_ratio
    return normalized


def _normalize_element(raw: dict[str, Any], index: int) -> dict[str, Any]:
    raw_type = str(raw.get("type") or "text").lower()
    content = raw.get("content")
    if content is None:
        content = raw.get("text") or raw.get("html") or raw.get("alt") or ""

    if raw_type in {
        "text",
        "image",
        "shape",
        "chart",
        "latex",
        "code",
        "table",
        "video",
    }:
        element_type = raw_type
    elif raw_type in _IMAGE_TYPE_ALIASES:
        element_type = "image"
    elif raw_type in _TEXT_TYPE_ALIASES or _looks_like_text_content(content):
        element_type = "text"
    else:
        element_type = "shape"

    element = {
        "id": str(raw.get("id") or f"el_{index}"),
        "type": element_type,
        "x": _number(raw.get("x", raw.get("left")), 80),
        "y": _number(raw.get("y", raw.get("top")), 80 + (index * 40)),
        "width": _number(raw.get("width"), 360),
        "height": _number(raw.get("height"), 120),
        "content": str(content),
    }

    src = raw.get("src") or raw.get("url")
    if src:
        element["src"] = str(src)

    style = raw.get("style")
    if isinstance(style, dict):
        element["style"] = style

    meta = raw.get("meta")
    if isinstance(meta, dict):
        element["meta"] = meta

    return element


def _sanitize_slide_elements(
    elements: list[dict[str, Any]],
    *,
    canvas_width: float,
    canvas_height: float,
) -> list[dict[str, Any]]:
    sanitized: list[dict[str, Any]] = []
    had_layout_pressure = False
    seen_text: set[str] = set()

    for element in elements:
        next_element = dict(element)
        content = str(next_element.get("content") or "")
        if _is_prompt_leak_text(content) or _is_generic_filler_text(content):
            had_layout_pressure = True
            continue

        if next_element.get("type") == "shape" and _looks_like_text_content(content):
            next_element["type"] = "text"

        if next_element.get("type") == "image":
            src = str(next_element.get("src") or "").strip()
            if src and not _is_safe_image_src(src):
                next_element["src"] = ""
                had_layout_pressure = True
            image_content = str(next_element.get("content") or "").strip()
            if image_content and not _is_safe_image_src(image_content):
                # Preserve human image prompts such as "Diagram of osmosis" but
                # strip URL-looking placeholders copied into content.
                if "://" in image_content or image_content.startswith("/"):
                    next_element["content"] = ""
                    had_layout_pressure = True
            if (
                not str(next_element.get("src") or "").strip()
                and not str(next_element.get("content") or "").strip()
                and not (isinstance(next_element.get("meta"), dict)
                         and next_element["meta"].get("imageProviderDisabled"))
            ):
                had_layout_pressure = True
                continue

        x = _number(next_element.get("x"), 0)
        y = _number(next_element.get("y"), 0)
        width = _number(next_element.get("width"), 0)
        height = _number(next_element.get("height"), 0)
        if x < 0:
            width += x
            x = 0
            had_layout_pressure = True
        if y < 0:
            height += y
            y = 0
            had_layout_pressure = True
        if x >= canvas_width or y >= canvas_height:
            had_layout_pressure = True
            continue
        if x + width > canvas_width:
            width = canvas_width - x
            had_layout_pressure = True
        if y + height > canvas_height:
            height = canvas_height - y
            had_layout_pressure = True
        if width < 8 or height < 8:
            had_layout_pressure = True
            continue

        next_element["x"] = x
        next_element["y"] = y
        next_element["width"] = width
        next_element["height"] = height

        if next_element.get("type") == "text":
            text_key = _plain_text(str(next_element.get("content") or "")).lower()
            if text_key in seen_text:
                had_layout_pressure = True
                continue
            seen_text.add(text_key)

        sanitized.append(next_element)

    if _needs_layout_repair(elements, sanitized, had_layout_pressure):
        return _repair_slide_layout(sanitized, canvas_width, canvas_height)
    return sanitized


def _needs_layout_repair(
    original: list[dict[str, Any]],
    sanitized: list[dict[str, Any]],
    had_layout_pressure: bool,
) -> bool:
    if had_layout_pressure:
        return True
    if len(original) > 10 or len(sanitized) > 8:
        return True
    large_media = [
        element for element in sanitized
        if element.get("type") == "image"
        and _number(element.get("width"), 0) * _number(element.get("height"), 0)
        > (_DEFAULT_CANVAS_WIDTH * _DEFAULT_CANVAS_HEIGHT * 0.45)
    ]
    text_count = sum(1 for element in sanitized if element.get("type") == "text")
    return bool(large_media and text_count >= 2)


def _repair_slide_layout(
    elements: list[dict[str, Any]],
    canvas_width: float,
    canvas_height: float,
) -> list[dict[str, Any]]:
    title = _first_title_element(elements)
    texts = [
        element
        for element in elements
        if element.get("type") == "text" and element is not title
    ]
    images = [element for element in elements if element.get("type") == "image"]
    others = [
        element
        for element in elements
        if element.get("type") not in {"text", "image"}
    ]

    repaired: list[dict[str, Any]] = []
    margin = 60.0
    if title is not None:
        repaired.append({
            **title,
            "x": margin,
            "y": 42.0,
            "width": canvas_width - (margin * 2),
            "height": 74.0,
        })

    primary_image = _best_image_element(images)
    body_texts = texts[:2]

    if primary_image and body_texts:
        repaired.append({
            **body_texts[0],
            "x": margin,
            "y": 146.0,
            "width": 440.0,
            "height": 250.0,
        })
        repaired.append({
            **primary_image,
            "x": 540.0,
            "y": 142.0,
            "width": 400.0,
            "height": 270.0,
        })
        if len(body_texts) > 1:
            repaired.append({
                **body_texts[1],
                "x": margin,
                "y": 420.0,
                "width": canvas_width - (margin * 2),
                "height": max(70.0, canvas_height - 450.0),
            })
    elif primary_image:
        repaired.append({
            **primary_image,
            "x": 120.0,
            "y": 132.0,
            "width": canvas_width - 240.0,
            "height": min(360.0, canvas_height - 170.0),
        })
    elif body_texts:
        repaired.append({
            **body_texts[0],
            "x": 80.0,
            "y": 146.0,
            "width": canvas_width - 160.0,
            "height": 300.0,
        })
        if len(body_texts) > 1:
            repaired.append({
                **body_texts[1],
                "x": 80.0,
                "y": 456.0,
                "width": canvas_width - 160.0,
                "height": max(60.0, canvas_height - 486.0),
            })

    # Preserve compact charts/tables/code blocks that were already in-bounds.
    for element in others:
        if len(repaired) >= 6:
            break
        repaired.append(element)

    return repaired or elements


def _first_title_element(elements: list[dict[str, Any]]) -> dict[str, Any] | None:
    for element in elements:
        if element.get("type") == "text" and str(element.get("id") or "").startswith("title"):
            return element
    for element in elements:
        if element.get("type") == "text":
            return element
    return None


def _best_image_element(elements: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not elements:
        return None
    safe = [
        element for element in elements
        if _is_safe_image_src(str(element.get("src") or ""))
    ]
    pool = safe or elements
    return max(
        pool,
        key=lambda element: _number(element.get("width"), 0)
        * _number(element.get("height"), 0),
    )


def _looks_like_text_content(content: Any) -> bool:
    value = str(content or "").strip()
    if not value:
        return False
    lowered = value.lower()
    if lowered in _SHAPE_NAMES:
        return False
    return (
        "<p" in lowered
        or "<ul" in lowered
        or "•" in value
        or len(_plain_text(value).split()) >= 2
    )


def _is_prompt_leak_text(value: Any) -> bool:
    lowered = _plain_text(str(value or "")).lower()
    return any(phrase in lowered for phrase in _PROMPT_LEAK_PHRASES)


def _is_generic_filler_text(value: Any) -> bool:
    text = _plain_text(str(value or "")).lower()
    text = text.lstrip("•- ").strip()
    if text in _GENERIC_FILLER_TEXTS:
        return True
    bullet_parts = [
        part.strip().lstrip("- ").strip()
        for part in text.split("•")
        if part.strip()
    ]
    return bool(bullet_parts) and all(
        part in _GENERIC_FILLER_TEXTS for part in bullet_parts
    )


def _plain_text(value: str) -> str:
    stripped = _HTML_TAG_RE.sub(" ", value)
    stripped = stripped.replace("&nbsp;", " ")
    stripped = stripped.replace("•", " • ")
    return _SPACE_RE.sub(" ", stripped).strip()


def _normalize_background(raw: Any) -> str:
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    if not isinstance(raw, dict):
        return "#ffffff"
    if raw.get("type") == "solid" and raw.get("color"):
        return str(raw["color"])
    gradient = raw.get("gradient")
    if raw.get("type") == "gradient" and isinstance(gradient, dict):
        colors = gradient.get("colors")
        if isinstance(colors, list) and colors:
            stops = []
            for stop in colors:
                if not isinstance(stop, dict) or not stop.get("color"):
                    continue
                pos = stop.get("pos", 0)
                stops.append(f"{stop['color']} {pos}%")
            if stops:
                angle = gradient.get("rotate", 90)
                return f"linear-gradient({angle}deg, {', '.join(stops)})"
    return "#ffffff"


def _first_speech_text(actions: Any) -> str:
    if not isinstance(actions, list):
        return ""
    for action in actions:
        if isinstance(action, dict) and action.get("type") == "speech":
            return str(action.get("text") or "")
    return ""


def _count_speech_actions(scenes: list[dict[str, Any]]) -> int:
    count = 0
    for scene in scenes:
        actions = scene.get("actions") if isinstance(scene, dict) else None
        if not isinstance(actions, list):
            continue
        count += sum(
            1
            for action in actions
            if isinstance(action, dict) and action.get("type") == "speech"
        )
    return count


def _audio_manifest(speech_count: int) -> dict[str, Any]:
    if speech_count <= 0:
        return {
            "status": "ready",
            "progress": 100,
            "totalActions": 0,
            "completedActions": 0,
            "failedAudioIds": [],
            "generatedAt": timezone.now().isoformat(),
        }
    return {
        "status": "partial",
        "progress": 0,
        "totalActions": speech_count,
        "completedActions": 0,
        "failedAudioIds": [],
        "generatedAt": None,
    }


def _estimate_minutes(
    scenes: list[dict[str, Any]],
    requirements: dict[str, Any],
) -> int:
    explicit = requirements.get("estimatedMinutes")
    try:
        value = int(explicit)
    except (TypeError, ValueError):
        value = 0
    if value > 0:
        return value
    return max(1, len(scenes) * 2)


def _resolve_is_public(requirements: dict[str, Any]) -> bool:
    value = requirements.get("isPublic")
    if isinstance(value, bool):
        return value
    return False


def _language_code(raw: Any) -> str:
    value = str(raw or "English").strip()
    mapped = _LANGUAGE_CODES.get(value.lower())
    return (mapped or value or "en")[:10]


def _number(raw: Any, default: float) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _clean_title(raw: Any, *, max_len: int) -> str:
    value = _clean_text(raw) or "AI Classroom"
    return value[:max_len]


def _clean_text(raw: Any) -> str:
    if raw is None:
        return ""
    return str(raw).strip()
