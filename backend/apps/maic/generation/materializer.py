"""Materialize v2 generation jobs into durable LMS classroom artifacts."""
from __future__ import annotations

import logging
from typing import Any

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.courses.maic_models import MAICClassroom
from apps.courses.models import Content, Course, Module
from apps.maic.models import MaicGenerationJob
from apps.maic.orchestration.registry import DEFAULT_AGENTS
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
    topic = _clean_title(requirements.get("topic") or "AI Classroom", max_len=500)
    title = _clean_title(
        requirements.get("contentTitle") or requirements.get("title") or topic,
        max_len=300,
    )

    with transaction.atomic():
        scenes = _attach_pbl_sessions(job, scenes, prior_result)
        # `finalize_task` has already placed the incoming list object
        # into job.result["scenes"]. Keep that contract intact by
        # replacing the list contents with the normalized/materialized
        # scenes, including pblSessionId attachments.
        caller_scenes[:] = scenes
        slides, scene_slide_bounds = _extract_slides_and_bounds(scenes)
        speech_count = _count_speech_actions(scenes)
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
        }
        classroom.generation_phase = "complete"
        classroom.phase_scene_index = len(scenes)
        classroom.scenes_ready = len(scenes)
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
                "started_at",
                "last_progress_at",
                "updated_at",
            ]
        )

        content = _materialize_content(
            prior_result=prior_result,
            module=module,
            classroom=classroom,
            title=title,
            job=job,
        )

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
    normalized: list[dict[str, Any]] = []
    for scene_index, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            continue
        next_scene = dict(scene)
        actions = scene.get("actions")
        if isinstance(actions, list):
            next_actions = []
            for action_index, action in enumerate(actions):
                if not isinstance(action, dict):
                    continue
                next_action = dict(action)
                if next_action.get("type") == "speech":
                    next_action.setdefault("agentId", default_agent_id)
                    next_action.setdefault(
                        "id",
                        f"speech_{scene.get('id', scene_index)}_{action_index}",
                    )
                next_actions.append(next_action)
            next_scene["actions"] = next_actions
        normalized.append(next_scene)
    return normalized


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
        else:
            start = max(len(slides) - 1, 0)
            end = start
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

    return {
        "id": str(raw_slide.get("id") or f"{scene.get('id', 'scene')}-slide-{index}"),
        "title": str(raw_slide.get("title") or scene.get("title") or "Slide"),
        "elements": [
            _normalize_element(element, element_index)
            for element_index, element in enumerate(elements)
            if isinstance(element, dict)
        ],
        "background": _normalize_background(raw_slide.get("background")),
        "speakerScript": _first_speech_text(scene.get("actions")),
    }


def _normalize_element(raw: dict[str, Any], index: int) -> dict[str, Any]:
    raw_type = str(raw.get("type") or "text").lower()
    element_type = raw_type if raw_type in {
        "text",
        "image",
        "shape",
        "chart",
        "latex",
        "code",
        "table",
        "video",
    } else "shape"

    content = raw.get("content")
    if content is None:
        content = raw.get("text") or raw.get("html") or raw.get("alt") or ""

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
