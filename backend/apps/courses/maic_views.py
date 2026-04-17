"""
OpenMAIC AI Classroom -- Django proxy views.

Proxy endpoints relay requests to the OpenMAIC sidecar (http://openmaic:3000)
after authenticating the user, resolving the tenant, decrypting API keys from
TenantAIConfig, and injecting them as headers. The sidecar never stores keys.

Teacher endpoints:
    POST /api/v1/teacher/maic/chat/                    -- SSE chat proxy
    POST /api/v1/teacher/maic/generate/outlines/       -- SSE outline generation
    POST /api/v1/teacher/maic/generate/scene-content/  -- JSON scene content
    POST /api/v1/teacher/maic/generate/tts/            -- Binary TTS proxy
    POST /api/v1/teacher/maic/generate/classroom/      -- Async classroom gen
    POST /api/v1/teacher/maic/generate/image/          -- JSON image generation
    GET  /api/v1/teacher/maic/classrooms/              -- List classrooms
    POST /api/v1/teacher/maic/classrooms/create/       -- Create classroom
    GET  /api/v1/teacher/maic/classrooms/<id>/         -- Classroom detail
    PATCH /api/v1/teacher/maic/classrooms/<id>/update/ -- Update classroom
    DELETE /api/v1/teacher/maic/classrooms/<id>/delete/ -- Delete classroom

Student endpoints:
    GET  /api/v1/student/maic/classrooms/              -- Browse public
    GET  /api/v1/student/maic/classrooms/<id>/         -- Classroom detail
    POST /api/v1/student/maic/chat/                    -- SSE chat (student)
    POST /api/v1/student/maic/generate/tts/            -- TTS playback
"""

import hashlib
import json
import logging

import requests as http_requests
from django.db import transaction
from django.http import StreamingHttpResponse, HttpResponse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.courses.maic_models import TenantAIConfig, MAICClassroom
from apps.courses.maic_generation_service import (
    generate_outline_sse,
    generate_scene_content,
    generate_scene_actions,
    generate_chat_sse,
    generate_tts_audio,
    fallback_quiz_grade,
    generate_agent_profiles_json,
    regenerate_one_agent,
    AgentValidationError,
    AGENT_VOICE_MAP,
)
from apps.courses.maic_voices import AZURE_IN_VOICES
from apps.courses.image_service import fetch_scene_image
from apps.courses.content_guardrails import validate_topic, validate_pdf_content, validate_chat_message
from utils.decorators import teacher_or_admin, student_or_admin, tenant_required, check_feature
from utils.audit import log_audit

logger = logging.getLogger(__name__)


# ─── Rate Limiting ────────────────────────────────────────────────────────────
# StudentGenerationThrottle removed — no rate limit for student classroom generation


OPENMAIC_BASE = "http://openmaic:3000"
# Connection timeout (seconds) for sidecar reachability check.
# Low value so fallback to direct LLM is fast when sidecar is down.
_SIDECAR_CONNECT_TIMEOUT = 2


# ======================================================================
# Internal helpers
# ======================================================================

def _get_ai_config(tenant):
    """Load and validate TenantAIConfig, return (config, error_response)."""
    try:
        config = TenantAIConfig.objects.get(tenant=tenant)
    except TenantAIConfig.DoesNotExist:
        return None, Response(
            {"error": "AI Classroom is not configured. Ask your admin to set up AI Provider in Settings."},
            status=status.HTTP_403_FORBIDDEN,
        )
    if not config.maic_enabled:
        return None, Response(
            {"error": "AI Classroom is disabled for this school."},
            status=status.HTTP_403_FORBIDDEN,
        )
    return config, None


def _build_proxy_headers(config):
    """Build headers to inject into OpenMAIC sidecar requests."""
    headers = {
        "Content-Type": "application/json",
        "x-llm-provider": config.llm_provider,
        "x-llm-model": config.llm_model,
    }
    api_key = config.get_llm_api_key()
    if api_key:
        headers["x-api-key"] = api_key
    if config.llm_base_url:
        headers["x-base-url"] = config.llm_base_url
    if config.tts_provider and config.tts_provider != "disabled":
        headers["x-tts-provider"] = config.tts_provider
        tts_key = config.get_tts_api_key()
        if tts_key:
            headers["x-tts-api-key"] = tts_key
        if config.tts_voice_id:
            headers["x-tts-voice-id"] = config.tts_voice_id
    if config.image_provider and config.image_provider != "disabled":
        headers["x-image-provider"] = config.image_provider
        img_key = config.get_image_api_key()
        if img_key:
            headers["x-image-api-key"] = img_key
    return headers


def _proxy_sse(request, path, config):
    """Forward a POST to the sidecar and stream SSE back."""
    url = f"{OPENMAIC_BASE}{path}"
    headers = _build_proxy_headers(config)

    try:
        body = request.body.decode("utf-8") if request.body else "{}"
    except UnicodeDecodeError:
        body = "{}"

    try:
        upstream = http_requests.post(
            url, data=body, headers=headers, stream=True, timeout=(_SIDECAR_CONNECT_TIMEOUT, 300),
        )
    except http_requests.ConnectionError:
        logger.error("OpenMAIC sidecar unreachable at %s", url)
        return HttpResponse(
            json.dumps({"error": "AI Classroom service is temporarily unavailable."}),
            status=502,
            content_type="application/json",
        )
    except http_requests.Timeout:
        return HttpResponse(
            json.dumps({"error": "AI Classroom service timed out."}),
            status=504,
            content_type="application/json",
        )

    if upstream.status_code != 200:
        return HttpResponse(
            upstream.content,
            status=upstream.status_code,
            content_type=upstream.headers.get("Content-Type", "application/json"),
        )

    def stream():
        try:
            for chunk in upstream.iter_content(chunk_size=None):
                if chunk:
                    yield chunk
        finally:
            upstream.close()

    response = StreamingHttpResponse(
        stream(),
        content_type=upstream.headers.get("Content-Type", "text/event-stream"),
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


def _proxy_json(request, path, config, method="POST"):
    """Forward a request and return JSON."""
    url = f"{OPENMAIC_BASE}{path}"
    headers = _build_proxy_headers(config)

    try:
        body = request.body.decode("utf-8") if request.body else "{}"
    except UnicodeDecodeError:
        body = "{}"

    try:
        if method == "POST":
            upstream = http_requests.post(url, data=body, headers=headers, timeout=(_SIDECAR_CONNECT_TIMEOUT, 120))
        else:
            upstream = http_requests.get(url, headers=headers, timeout=(_SIDECAR_CONNECT_TIMEOUT, 120))
    except http_requests.ConnectionError:
        return Response(
            {"error": "AI Classroom service is temporarily unavailable."},
            status=status.HTTP_502_BAD_GATEWAY,
        )
    except http_requests.Timeout:
        return Response(
            {"error": "AI Classroom service timed out."},
            status=status.HTTP_504_GATEWAY_TIMEOUT,
        )

    try:
        data = upstream.json()
    except ValueError:
        data = {"raw": upstream.text}

    return Response(data, status=upstream.status_code)


def _proxy_binary(request, path, config):
    """Forward a request and return binary (audio) data."""
    url = f"{OPENMAIC_BASE}{path}"
    headers = _build_proxy_headers(config)

    try:
        body = request.body.decode("utf-8") if request.body else "{}"
    except UnicodeDecodeError:
        body = "{}"

    try:
        upstream = http_requests.post(url, data=body, headers=headers, timeout=(_SIDECAR_CONNECT_TIMEOUT, 120))
    except (http_requests.ConnectionError, http_requests.Timeout):
        return HttpResponse(
            json.dumps({"error": "AI Classroom service unavailable."}),
            status=502,
            content_type="application/json",
        )

    return HttpResponse(
        upstream.content,
        status=upstream.status_code,
        content_type=upstream.headers.get("Content-Type", "audio/mpeg"),
    )


def _fill_image_urls(data, *, image_provider: str = "disabled"):
    """Fill empty image src fields with actual image URLs.

    After scene content generation, image elements may have ``src: ""``
    because the LLM cannot produce real URLs.  This post-processor walks
    every slide and resolves empty ``src`` fields via the image service
    (Imagen / Nano Banana / Unsplash / Pexels / Pollinations / placeholder).

    When the tenant has `image_provider == "disabled"`, we skip the fetch
    and instead stamp `meta.imageProviderDisabled = true` on each image
    element so the frontend can render an honest "AI images disabled"
    placeholder instead of a random Unsplash photo the school didn't ask
    for.
    """
    disabled = (image_provider or "disabled").lower() == "disabled"
    slides = data.get("slides", [])
    for slide in slides:
        for element in slide.get("elements", []):
            if element.get("type") != "image":
                continue
            if element.get("src"):
                continue
            if disabled:
                meta = element.setdefault("meta", {})
                meta["imageProviderDisabled"] = True
                continue
            keyword = element.get("content", "educational illustration")
            try:
                url = fetch_scene_image(keyword)
                element["src"] = url
            except Exception as exc:  # noqa: BLE001 — log + fail open
                logger.warning(
                    "image fill failed keyword=%r err=%s", keyword, exc,
                )
    return data


# ======================================================================
# Teacher Proxy Endpoints
# ======================================================================

@api_view(["POST"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
@check_feature("feature_maic")
def teacher_maic_chat(request):
    """SSE proxy to OpenMAIC /api/chat — tries sidecar, then direct LLM."""
    config, err = _get_ai_config(request.tenant)
    if err:
        return err

    # Try sidecar first
    result = _proxy_sse(request, "/api/chat", config)
    if result.status_code != 502:
        return result

    # Sidecar unavailable — generate chat response directly via LLM
    logger.info("Sidecar unavailable, using direct chat generation")
    try:
        body = json.loads(request.body) if request.body else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        body = {}

    # Look up classroom for context — title + agents + scene outline.
    # Scene titles ground "summarize key concepts" queries even when
    # no prior chat turn has been recorded.
    classroom_title = ""
    agents = []
    scene_titles: list[str] = []
    classroom_id = body.get("classroomId")
    if classroom_id:
        try:
            classroom = MAICClassroom.objects.get(pk=classroom_id, tenant=request.tenant)
            classroom_title = classroom.title or classroom.topic
            agents = (classroom.config or {}).get("agents", [])
            content = classroom.content or {}
            for s in (content.get("scenes") or []):
                if isinstance(s, dict):
                    title = s.get("title")
                    if isinstance(title, str) and title.strip():
                        scene_titles.append(title.strip())
        except MAICClassroom.DoesNotExist:
            pass

    response = StreamingHttpResponse(
        generate_chat_sse(
            message=body.get("message", ""),
            classroom_title=classroom_title,
            agents=agents,
            config=config,
            history=body.get("history"),
            scene_titles=scene_titles or None,
        ),
        content_type="text/event-stream",
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
@check_feature("feature_maic")
def teacher_maic_generate_outlines(request):
    """SSE outline generation — tries sidecar first, then direct LLM."""
    config, err = _get_ai_config(request.tenant)
    if err:
        return err

    # Try sidecar first
    result = _proxy_sse(request, "/api/generate/scene-outlines-stream", config)
    if result.status_code != 502:
        return result

    # Sidecar unavailable — generate directly via LLM
    logger.info("Sidecar unavailable, using direct outline generation")
    try:
        body = json.loads(request.body) if request.body else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        body = {}

    agents_input = body.get("agents") or []
    if not agents_input:
        return HttpResponse(
            json.dumps({"error": "No agents provided. Generate agents first."}),
            status=400,
            content_type="application/json",
        )

    response = StreamingHttpResponse(
        generate_outline_sse(
            topic=body.get("topic", ""),
            language=body.get("language", "en"),
            agents=agents_input,
            scene_count=body.get("sceneCount", 6),
            pdf_text=body.get("pdfText"),
            config=config,
        ),
        content_type="text/event-stream",
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
@check_feature("feature_maic")
def teacher_maic_generate_scene_content(request):
    """Scene content generation — tries sidecar first, then direct LLM."""
    config, err = _get_ai_config(request.tenant)
    if err:
        return err

    # Try sidecar first
    result = _proxy_json(request, "/api/generate/scene-content", config)
    if result.status_code != 502:
        return result

    # Direct LLM fallback
    logger.info("Sidecar unavailable, using direct scene content generation")
    try:
        body = json.loads(request.body) if request.body else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        body = {}

    data = generate_scene_content(
        scene=body.get("scene", {}),
        agents=body.get("agents", []),
        language=body.get("language", "en"),
        config=config,
    )
    if data:
        # Post-process: fill empty image src fields with real URLs,
        # respecting the tenant's image_provider setting.
        _fill_image_urls(data, image_provider=config.image_provider)
        return Response(data)
    return Response(
        {"error": "Failed to generate scene content."},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
@check_feature("feature_maic")
def teacher_maic_generate_tts(request):
    """Binary proxy to OpenMAIC /api/generate/tts — tries sidecar, then direct TTS."""
    config, err = _get_ai_config(request.tenant)
    if err:
        return err

    result = _proxy_binary(request, "/api/generate/tts", config)
    if result.status_code != 502:
        return result

    # Sidecar unavailable — generate TTS directly
    logger.info("Sidecar unavailable, using direct TTS generation")
    try:
        body = json.loads(request.body) if request.body else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        body = {}

    text = body.get("text", "")
    if not text:
        return HttpResponse(
            json.dumps({"error": "No text provided"}),
            status=400,
            content_type="application/json",
        )

    # Resolve per-agent voice: explicit voiceId > agent role mapping > tenant default
    voice_id = body.get("voiceId")
    if not voice_id:
        agent_role = body.get("agentRole", "")
        if agent_role:
            voice_id = AGENT_VOICE_MAP.get(agent_role)

    audio_bytes = generate_tts_audio(text, config, voice_id=voice_id)
    if audio_bytes:
        return HttpResponse(audio_bytes, content_type="audio/mpeg")

    # No TTS available — return 204 so frontend uses timed silence
    return HttpResponse(status=204)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
@check_feature("feature_maic")
def teacher_maic_generate_classroom(request):
    """JSON proxy to OpenMAIC /api/generate-classroom -- async full generation."""
    config, err = _get_ai_config(request.tenant)
    if err:
        return err
    return _proxy_json(request, "/api/generate-classroom", config)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
@check_feature("feature_maic")
def teacher_maic_generate_image(request):
    """JSON proxy to OpenMAIC /api/generate/image."""
    config, err = _get_ai_config(request.tenant)
    if err:
        return err
    return _proxy_json(request, "/api/generate/image", config)


# ======================================================================
# Teacher Classroom CRUD
# ======================================================================

@api_view(["GET"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
@check_feature("feature_maic")
def teacher_maic_classroom_list(request):
    """List the current teacher's MAIC classrooms."""
    qs = MAICClassroom.objects.filter(
        tenant=request.tenant, creator=request.user,
    ).order_by("-updated_at")

    status_filter = request.query_params.get("status")
    if status_filter:
        qs = qs.filter(status=status_filter.upper())

    search = request.query_params.get("search")
    if search:
        qs = qs.filter(title__icontains=search)

    qs = qs.prefetch_related("assigned_sections__grade")

    classrooms = []
    for c in qs:
        classrooms.append({
            "id": str(c.id),
            "title": c.title,
            "description": c.description,
            "topic": c.topic,
            "status": c.status,
            "is_public": c.is_public,
            "scene_count": c.scene_count,
            "estimated_minutes": c.estimated_minutes,
            "course_id": str(c.course_id) if c.course_id else None,
            "assigned_sections": [
                {"id": str(s.id), "name": s.name, "grade_name": s.grade.name if s.grade else None}
                for s in c.assigned_sections.all()
            ],
            "created_at": c.created_at.isoformat(),
            "updated_at": c.updated_at.isoformat(),
        })

    return Response(classrooms)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
@check_feature("feature_maic")
def teacher_maic_classroom_create(request):
    """Create a new MAIC classroom record."""
    title = (request.data.get("title") or "").strip()
    if not title:
        return Response({"error": "title is required."}, status=status.HTTP_400_BAD_REQUEST)

    # Check classroom limit
    try:
        config = TenantAIConfig.objects.get(tenant=request.tenant)
        existing_count = MAICClassroom.objects.filter(
            tenant=request.tenant, creator=request.user,
        ).exclude(status="ARCHIVED").count()
        if existing_count >= config.max_classrooms_per_teacher:
            return Response(
                {"error": f"You have reached the maximum of {config.max_classrooms_per_teacher} classrooms."},
                status=status.HTTP_403_FORBIDDEN,
            )
    except TenantAIConfig.DoesNotExist:
        pass

    course_id = request.data.get("course_id")
    course = None
    if course_id:
        from apps.courses.models import Course
        try:
            course = Course.objects.get(pk=course_id, tenant=request.tenant)
        except Course.DoesNotExist:
            return Response({"error": "Course not found."}, status=status.HTTP_404_NOT_FOUND)

    classroom = MAICClassroom.objects.create(
        tenant=request.tenant,
        creator=request.user,
        title=title,
        description=request.data.get("description", ""),
        topic=request.data.get("topic", ""),
        language=request.data.get("language", "en"),
        course=course,
        config=request.data.get("config", {}),
        status="DRAFT",
    )

    return Response({
        "id": str(classroom.id),
        "title": classroom.title,
        "status": classroom.status,
        "created_at": classroom.created_at.isoformat(),
    }, status=status.HTTP_201_CREATED)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
@check_feature("feature_maic")
def teacher_maic_classroom_detail(request, classroom_id):
    """Get a single classroom's metadata."""
    try:
        classroom = MAICClassroom.objects.get(
            pk=classroom_id, tenant=request.tenant, creator=request.user,
        )
    except MAICClassroom.DoesNotExist:
        return Response({"error": "Classroom not found."}, status=status.HTTP_404_NOT_FOUND)

    sections = classroom.assigned_sections.select_related("grade").all()
    return Response({
        "id": str(classroom.id),
        "title": classroom.title,
        "description": classroom.description,
        "topic": classroom.topic,
        "language": classroom.language,
        "status": classroom.status,
        "error_message": classroom.error_message,
        "is_public": classroom.is_public,
        "scene_count": classroom.scene_count,
        "estimated_minutes": classroom.estimated_minutes,
        "course_id": str(classroom.course_id) if classroom.course_id else None,
        "assigned_sections": [
            {"id": str(s.id), "name": s.name, "grade_name": s.grade.name if s.grade else None}
            for s in sections
        ],
        "config": classroom.config,
        # Full generated payload (agents, scenes, actions, slides, audioManifest).
        # The player needs every nested field to render; a bare metadata
        # response made existing READY classrooms look empty in the UI.
        "content": classroom.content or {},
        "audioManifest": (classroom.content or {}).get("audioManifest"),
        "created_at": classroom.created_at.isoformat(),
        "updated_at": classroom.updated_at.isoformat(),
    })


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
@check_feature("feature_maic")
def teacher_maic_classroom_update(request, classroom_id):
    """Update classroom metadata."""
    try:
        classroom = MAICClassroom.objects.get(
            pk=classroom_id, tenant=request.tenant, creator=request.user,
        )
    except MAICClassroom.DoesNotExist:
        return Response({"error": "Classroom not found."}, status=status.HTTP_404_NOT_FOUND)

    updatable = ["title", "description", "topic", "language", "status",
                  "is_public", "scene_count", "estimated_minutes", "config", "error_message",
                  "content"]
    updated_fields = []
    for field in updatable:
        if field in request.data:
            setattr(classroom, field, request.data[field])
            updated_fields.append(field)

    if updated_fields:
        updated_fields.append("updated_at")
        classroom.save(update_fields=updated_fields)

    # Handle M2M assigned_sections separately
    if "assigned_section_ids" in request.data:
        section_ids = request.data["assigned_section_ids"]
        if isinstance(section_ids, list):
            from apps.academics.models import Section
            sections = Section.objects.filter(
                id__in=section_ids, tenant=request.tenant,
            )
            classroom.assigned_sections.set(sections)

    return Response({"id": str(classroom.id), "status": classroom.status})


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
@check_feature("feature_maic")
def teacher_maic_classroom_delete(request, classroom_id):
    """Delete (archive) a classroom."""
    try:
        classroom = MAICClassroom.objects.get(
            pk=classroom_id, tenant=request.tenant, creator=request.user,
        )
    except MAICClassroom.DoesNotExist:
        return Response({"error": "Classroom not found."}, status=status.HTTP_404_NOT_FOUND)

    classroom.status = "ARCHIVED"
    classroom.save(update_fields=["status", "updated_at"])

    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
@check_feature("feature_maic")
def teacher_maic_classroom_publish(request, classroom_id):
    """Trigger pre-gen audio pipeline; transitions DRAFT/READY → GENERATING → READY.

    Uses ``select_for_update`` to reject concurrent publish attempts with HTTP 409.
    Walks every speech action, stamps a deterministic ``audioId`` + resolved
    ``voiceId`` from the agent roster, writes an ``audioManifest`` onto
    ``classroom.content`` and enqueues the Celery pre-gen task (idempotent:
    if it runs again on a re-publish, actions that already carry ``audioUrl``
    are skipped).
    """
    with transaction.atomic():
        try:
            classroom = MAICClassroom.objects.select_for_update().get(
                pk=classroom_id, tenant=request.tenant, creator=request.user,
            )
        except MAICClassroom.DoesNotExist:
            return Response(
                {"error": "Classroom not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if classroom.status == "GENERATING":
            return Response(
                {"error": "Publish already in progress."},
                status=status.HTTP_409_CONFLICT,
            )

        content = classroom.content or {}
        scenes = content.get("scenes", [])
        agents_by_id = {a["id"]: a for a in content.get("agents", [])}

        # Walk speech actions, stamp audioId + voiceId.
        # If text or voice changed since the last publish, the new audioId
        # will differ from the previous one — clear the stale audioUrl so
        # the pre-gen task regenerates audio instead of reusing the old file.
        # (Fixes edit-and-republish playing stale audio — Chunk 4 review A/B.)
        total = 0
        for scene_idx, scene in enumerate(scenes):
            actions = scene.get("actions", [])
            for action_idx, action in enumerate(actions):
                if action.get("type") != "speech":
                    continue
                agent_id = action.get("agentId")
                agent = agents_by_id.get(agent_id, {})
                voice_id = agent.get("voiceId") or "en-IN-NeerjaNeural"
                payload = (
                    f"{scene.get('id', scene_idx)}|{action_idx}|"
                    f"{action.get('text', '')}|{voice_id}"
                )
                new_audio_id = hashlib.sha256(payload.encode()).hexdigest()[:12]
                old_audio_id = action.get("audioId")
                if old_audio_id and old_audio_id != new_audio_id:
                    # Content drifted — old audioUrl points to stale audio.
                    action.pop("audioUrl", None)
                action["voiceId"] = voice_id
                action["audioId"] = new_audio_id
                total += 1

        content["audioManifest"] = {
            "status": "generating",
            "progress": 0,
            "totalActions": total,
            "completedActions": 0,
            "failedAudioIds": [],
            "generatedAt": None,
        }
        classroom.content = content
        classroom.status = "GENERATING"
        classroom.save(update_fields=["content", "status", "updated_at"])

    # Enqueue after the transaction commits so the worker sees the new state
    from apps.courses.maic_tasks import pre_generate_classroom_tts
    pre_generate_classroom_tts.delay(str(classroom.id))

    return Response(
        {"audioManifest": content["audioManifest"]},
        status=status.HTTP_202_ACCEPTED,
    )


# Quiz grading
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
@check_feature("feature_maic")
def teacher_maic_quiz_grade(request):
    """JSON proxy to OpenMAIC /api/quiz-grade for AI-graded short answers.
    Falls back to direct LLM grading when the sidecar is unavailable."""
    config, err = _get_ai_config(request.tenant)
    if err:
        return err

    # Try sidecar first
    result = _proxy_json(request, "/api/quiz-grade", config)
    if result.status_code != 502:
        return result

    # Sidecar unavailable — grade directly via LLM
    logger.info("Sidecar unavailable, using direct LLM quiz grading")
    try:
        body = json.loads(request.body) if request.body else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        body = {}

    # Accept both frontend format (question/answer) and canonical format (studentAnswer/expectedAnswer)
    student_answer = body.get("studentAnswer") or body.get("answer", "")
    expected_answer = body.get("expectedAnswer") or body.get("question", "")
    rubric = body.get("rubric") or body.get("commentPrompt")

    if not student_answer or not expected_answer:
        return Response(
            {"error": "studentAnswer and expectedAnswer are required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    grade_result = fallback_quiz_grade(
        student_answer=student_answer,
        expected_answer=expected_answer,
        rubric=rubric,
        config=config,
    )
    return Response(grade_result)


# Export
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
@check_feature("feature_maic")
def teacher_maic_export_pptx(request):
    """Binary proxy to OpenMAIC /api/export/pptx."""
    config, err = _get_ai_config(request.tenant)
    if err:
        return err
    return _proxy_binary(request, "/api/export/pptx", config)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
@check_feature("feature_maic")
def teacher_maic_export_html(request):
    """Binary proxy to OpenMAIC /api/export/html."""
    config, err = _get_ai_config(request.tenant)
    if err:
        return err
    return _proxy_binary(request, "/api/export/html", config)


# Web search
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
@check_feature("feature_maic")
def teacher_maic_web_search(request):
    """JSON proxy to OpenMAIC /api/web-search."""
    config, err = _get_ai_config(request.tenant)
    if err:
        return err
    return _proxy_json(request, "/api/web-search", config)


# Scene actions generation
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
@check_feature("feature_maic")
def teacher_maic_generate_scene_actions(request):
    """Scene actions generation — tries sidecar first, then direct LLM."""
    config, err = _get_ai_config(request.tenant)
    if err:
        return err

    # Try sidecar first
    result = _proxy_json(request, "/api/generate/scene-actions", config)
    if result.status_code != 502:
        return result

    # Direct LLM fallback
    logger.info("Sidecar unavailable, using direct scene actions generation")
    try:
        body = json.loads(request.body) if request.body else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        body = {}

    data = generate_scene_actions(
        scene=body.get("scene", {}),
        agents=body.get("agents", []),
        language=body.get("language", "en"),
        config=config,
    )
    if data:
        return Response(data)
    return Response(
        {"error": "Failed to generate scene actions."},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


# Agent profiles generation — uses the direct LLM validator path.
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
@check_feature("feature_maic")
def teacher_maic_generate_agent_profiles(request):
    """Generate an agent roster using the validated LLM path."""
    config, err = _get_ai_config(request.tenant)
    if err:
        return err
    return _generate_agent_profiles_impl(request, config)


# ======================================================================
# Student Endpoints
# ======================================================================

@api_view(["GET"])
@permission_classes([IsAuthenticated])
@student_or_admin
@tenant_required
@check_feature("feature_maic")
def student_maic_classroom_list(request):
    """Browse READY classrooms visible to the student.

    Visibility rules:
    - is_public=True + no assigned_sections → visible to ALL students
    - assigned_sections contains student's section → visible (regardless of is_public)
    - is_public=False + no assigned_sections → not visible (teacher-only/draft)
    """
    from django.db.models import Q

    qs = MAICClassroom.objects.filter(
        tenant=request.tenant, status="READY",
    ).filter(
        # Gate on audioManifest — classrooms mid-generation are hidden from students.
        Q(content__audioManifest__status="ready") |
        Q(content__audioManifest__status="partial")
    ).order_by("-updated_at")

    student_section = getattr(request.user, "section_fk", None)
    if student_section:
        qs = qs.filter(
            Q(is_public=True, assigned_sections__isnull=True) |  # public to all
            Q(assigned_sections=student_section)                 # assigned to student's section
        ).distinct()
    else:
        # Student without a section — only see fully public classrooms
        qs = qs.filter(is_public=True, assigned_sections__isnull=True)

    course_id = request.query_params.get("course_id")
    if course_id:
        qs = qs.filter(course_id=course_id)

    search = request.query_params.get("search")
    if search:
        qs = qs.filter(title__icontains=search)

    classrooms = []
    for c in qs:
        classrooms.append({
            "id": str(c.id),
            "title": c.title,
            "description": c.description,
            "topic": c.topic,
            "scene_count": c.scene_count,
            "estimated_minutes": c.estimated_minutes,
            "course_id": str(c.course_id) if c.course_id else None,
            "created_at": c.created_at.isoformat(),
        })

    return Response(classrooms)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@student_or_admin
@tenant_required
@check_feature("feature_maic")
def student_maic_classroom_detail(request, classroom_id):
    """Get a classroom's metadata (respects section assignment + visibility)."""
    try:
        classroom = MAICClassroom.objects.get(
            pk=classroom_id, tenant=request.tenant, status="READY",
        )
    except MAICClassroom.DoesNotExist:
        return Response({"error": "Classroom not found."}, status=status.HTTP_404_NOT_FOUND)

    # Hide classrooms still mid-generation — audio manifest must be usable.
    manifest_status = (classroom.content or {}).get("audioManifest", {}).get("status")
    if manifest_status not in ("ready", "partial"):
        return Response({"error": "Classroom not found."}, status=status.HTTP_404_NOT_FOUND)

    # Check visibility: assigned sections grant access, otherwise must be public with no restrictions
    assigned = classroom.assigned_sections.all()
    student_section = getattr(request.user, "section_fk", None)
    if assigned.exists():
        if not student_section or student_section not in assigned:
            return Response({"error": "Classroom not found."}, status=status.HTTP_404_NOT_FOUND)
    elif not classroom.is_public:
        return Response({"error": "Classroom not found."}, status=status.HTTP_404_NOT_FOUND)

    return Response({
        "id": str(classroom.id),
        "title": classroom.title,
        "description": classroom.description,
        "topic": classroom.topic,
        "language": classroom.language,
        "status": classroom.status,
        "scene_count": classroom.scene_count,
        "estimated_minutes": classroom.estimated_minutes,
        "course_id": str(classroom.course_id) if classroom.course_id else None,
        "config": classroom.config,
        "content": classroom.content,
        "created_at": classroom.created_at.isoformat(),
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@student_or_admin
@tenant_required
@check_feature("feature_maic")
def student_maic_chat(request):
    """SSE proxy for student mode chat — tries sidecar, then direct LLM."""
    config, err = _get_ai_config(request.tenant)
    if err:
        return err

    result = _proxy_sse(request, "/api/chat", config)
    if result.status_code != 502:
        return result

    # Sidecar unavailable — direct LLM fallback
    logger.info("Sidecar unavailable, using direct chat generation (student)")
    try:
        body = json.loads(request.body) if request.body else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        body = {}

    classroom_title = ""
    agents = []
    scene_titles: list[str] = []
    classroom_id = body.get("classroomId")
    if classroom_id:
        try:
            classroom = MAICClassroom.objects.get(pk=classroom_id, tenant=request.tenant)
            classroom_title = classroom.title or classroom.topic
            agents = (classroom.config or {}).get("agents", [])
            content = classroom.content or {}
            for s in (content.get("scenes") or []):
                if isinstance(s, dict):
                    title = s.get("title")
                    if isinstance(title, str) and title.strip():
                        scene_titles.append(title.strip())
        except MAICClassroom.DoesNotExist:
            pass

    response = StreamingHttpResponse(
        generate_chat_sse(
            message=body.get("message", ""),
            classroom_title=classroom_title,
            agents=agents,
            config=config,
            history=body.get("history"),
            scene_titles=scene_titles or None,
        ),
        content_type="text/event-stream",
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@student_or_admin
@tenant_required
@check_feature("feature_maic")
def student_maic_generate_tts(request):
    """TTS proxy for student playback — tries sidecar, then direct TTS."""
    config, err = _get_ai_config(request.tenant)
    if err:
        return err

    result = _proxy_binary(request, "/api/generate/tts", config)
    if result.status_code != 502:
        return result

    # Direct fallback
    try:
        body = json.loads(request.body) if request.body else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        body = {}

    text = body.get("text", "")
    if not text:
        return HttpResponse(status=204)

    # Resolve per-agent voice: explicit voiceId > agent role mapping > tenant default
    voice_id = body.get("voiceId")
    if not voice_id:
        agent_role = body.get("agentRole", "")
        if agent_role:
            voice_id = AGENT_VOICE_MAP.get(agent_role)

    audio_bytes = generate_tts_audio(text, config, voice_id=voice_id)
    if audio_bytes:
        return HttpResponse(audio_bytes, content_type="audio/mpeg")

    return HttpResponse(status=204)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@student_or_admin
@tenant_required
@check_feature("feature_maic")
def student_maic_quiz_grade(request):
    """Quiz grading proxy for student mode.
    Falls back to direct LLM grading when sidecar is unavailable."""
    config, err = _get_ai_config(request.tenant)
    if err:
        return err

    # Try sidecar first
    result = _proxy_json(request, "/api/quiz-grade", config)
    if result.status_code != 502:
        return result

    # Sidecar unavailable — grade directly via LLM
    logger.info("Sidecar unavailable, using direct LLM quiz grading (student)")
    try:
        body = json.loads(request.body) if request.body else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        body = {}

    # Accept both frontend format (question/answer) and canonical format (studentAnswer/expectedAnswer)
    student_answer = body.get("studentAnswer") or body.get("answer", "")
    expected_answer = body.get("expectedAnswer") or body.get("question", "")
    rubric = body.get("rubric") or body.get("commentPrompt")

    if not student_answer or not expected_answer:
        return Response(
            {"error": "studentAnswer and expectedAnswer are required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    grade_result = fallback_quiz_grade(
        student_answer=student_answer,
        expected_answer=expected_answer,
        rubric=rubric,
        config=config,
    )
    return Response(grade_result)


# ======================================================================
# Student AI Classroom Creation (with guardrails)
# ======================================================================



@api_view(["POST"])
@permission_classes([IsAuthenticated])
@student_or_admin
@tenant_required
@check_feature("feature_maic")
def student_maic_validate_topic(request):
    """Validate a topic or PDF text before allowing classroom creation.

    POST body: { "topic": "...", "pdfText": "..." }
    Returns: { "allowed": bool, "subject_area": "...", "reason": "..." }

    Guardrails removed — all topics are allowed.
    """
    topic = (request.data.get("topic") or "").strip()
    pdf_text = (request.data.get("pdfText") or "").strip()

    if not topic and not pdf_text:
        return Response(
            {"allowed": False, "reason": "Please enter a topic or upload a PDF."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return Response({
        "allowed": True,
        "is_educational": True,
        "subject_area": "general",
        "confidence": 1.0,
        "reason": "Approved",
    }, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@student_or_admin
@tenant_required
@check_feature("feature_maic")
def student_maic_classroom_create(request):
    """Create a new AI Classroom as a student."""
    config, err = _get_ai_config(request.tenant)
    if err:
        return err

    title = (request.data.get("title") or "").strip()
    topic = (request.data.get("topic") or "").strip()
    pdf_text = (request.data.get("pdfText") or "").strip()

    if not title:
        return Response({"error": "title is required."}, status=status.HTTP_400_BAD_REQUEST)

    # ── Create classroom ──
    classroom = MAICClassroom.objects.create(
        tenant=request.tenant,
        creator=request.user,
        title=title,
        description=request.data.get("description", ""),
        topic=topic,
        language=request.data.get("language", "en"),
        config=request.data.get("config", {}),
        status="DRAFT",
        is_public=False,  # Student classrooms are always private
    )

    log_audit(
        "CREATE", "MAICClassroom",
        target_id=str(classroom.id),
        target_repr=f"student_classroom:{title[:100]}",
        changes={"topic": topic[:200]},
        request=request,
    )

    return Response({
        "id": str(classroom.id),
        "title": classroom.title,
        "status": classroom.status,
        "created_at": classroom.created_at.isoformat(),
    }, status=status.HTTP_201_CREATED)


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
@student_or_admin
@tenant_required
@check_feature("feature_maic")
def student_maic_classroom_update(request, classroom_id):
    """Update a student's own classroom (content sync after generation)."""
    try:
        classroom = MAICClassroom.objects.get(
            pk=classroom_id, tenant=request.tenant, creator=request.user,
        )
    except MAICClassroom.DoesNotExist:
        return Response({"error": "Classroom not found."}, status=status.HTTP_404_NOT_FOUND)

    updatable = ["title", "description", "status", "scene_count",
                  "estimated_minutes", "config", "content", "error_message"]
    updated_fields = []
    for field in updatable:
        if field in request.data:
            setattr(classroom, field, request.data[field])
            updated_fields.append(field)

    if updated_fields:
        updated_fields.append("updated_at")
        classroom.save(update_fields=updated_fields)

    return Response({"id": str(classroom.id), "status": classroom.status})


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
@student_or_admin
@tenant_required
@check_feature("feature_maic")
def student_maic_classroom_delete(request, classroom_id):
    """Delete (archive) a student's own classroom."""
    try:
        classroom = MAICClassroom.objects.get(
            pk=classroom_id, tenant=request.tenant, creator=request.user,
        )
    except MAICClassroom.DoesNotExist:
        return Response({"error": "Classroom not found."}, status=status.HTTP_404_NOT_FOUND)

    classroom.status = "ARCHIVED"
    classroom.save(update_fields=["status", "updated_at"])

    log_audit(
        "ARCHIVE", "MAICClassroom",
        target_id=str(classroom.id),
        target_repr=f"student_classroom:{classroom.title[:100]}",
        request=request,
    )
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@student_or_admin
@tenant_required
@check_feature("feature_maic")
def student_maic_my_classrooms(request):
    """List classrooms created by the current student."""
    qs = MAICClassroom.objects.filter(
        tenant=request.tenant, creator=request.user,
    ).exclude(status="ARCHIVED").order_by("-updated_at")

    classrooms = [{
        "id": str(c.id),
        "title": c.title,
        "description": c.description,
        "topic": c.topic,
        "status": c.status,
        "scene_count": c.scene_count,
        "estimated_minutes": c.estimated_minutes,
        "created_at": c.created_at.isoformat(),
    } for c in qs]

    return Response(classrooms)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@student_or_admin
@tenant_required
@check_feature("feature_maic")
def student_maic_generate_outlines(request):
    """SSE outline generation for student — same as teacher endpoint."""
    config, err = _get_ai_config(request.tenant)
    if err:
        return err

    try:
        body = json.loads(request.body) if request.body else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        body = {}

    topic = (body.get("topic") or "").strip()
    pdf_text = (body.get("pdfText") or "").strip()

    log_audit(
        "GENERATE_OUTLINE", "MAICClassroom",
        target_repr=f"topic={topic[:100]}",
        request=request,
    )

    # Try sidecar first
    result = _proxy_sse(request, "/api/generate/scene-outlines-stream", config)
    if result.status_code != 502:
        return result

    agents_input = body.get("agents") or []
    if not agents_input:
        return HttpResponse(
            json.dumps({"error": "No agents provided. Generate agents first."}),
            status=400,
            content_type="application/json",
        )

    # Direct fallback
    logger.info("Sidecar unavailable, using direct outline generation (student)")
    response = StreamingHttpResponse(
        generate_outline_sse(
            topic=topic,
            pdf_text=pdf_text,
            language=body.get("language", "en"),
            agents=agents_input,
            scene_count=min(int(body.get("sceneCount", 5)), 8),  # Cap at 8 for students
            config=config,
        ),
        content_type="text/event-stream",
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@student_or_admin
@tenant_required
@check_feature("feature_maic")
def student_maic_generate_scene_content(request):
    """Scene content generation for student — same as teacher endpoint."""
    config, err = _get_ai_config(request.tenant)
    if err:
        return err

    result = _proxy_json(request, "/api/generate/scene-content", config)
    if result.status_code != 502:
        return result

    # Direct fallback
    logger.info("Sidecar unavailable, using direct scene content generation (student)")
    try:
        body = json.loads(request.body) if request.body else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        body = {}

    scene = body.get("scene", {})
    agents = body.get("agents", [])
    language = body.get("language", "en")

    data = generate_scene_content(scene, agents, language, config)
    _fill_image_urls(data, image_provider=config.image_provider)
    return Response(data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@student_or_admin
@tenant_required
@check_feature("feature_maic")
def student_maic_generate_scene_actions(request):
    """Scene actions generation for student — same as teacher endpoint."""
    config, err = _get_ai_config(request.tenant)
    if err:
        return err

    result = _proxy_json(request, "/api/generate/scene-actions", config)
    if result.status_code != 502:
        return result

    # Direct fallback
    logger.info("Sidecar unavailable, using direct scene actions generation (student)")
    try:
        body = json.loads(request.body) if request.body else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        body = {}

    scene = body.get("scene", {})
    agents = body.get("agents", [])
    language = body.get("language", "en")

    data = generate_scene_actions(scene, agents, language, config)
    return Response(data)


# ======================================================================
# Public MAIC endpoints (authenticated, role-agnostic)
# ======================================================================

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def maic_list_voices(request):
    """Return the Azure en-IN voice roster so the wizard can show labels /
    swatches / previews without round-tripping through an LLM. Available to
    teachers *and* students (both roles use the agent picker)."""
    return Response({"voices": AZURE_IN_VOICES})


# ======================================================================
# Agent profile + regenerate-one + TTS preview (shared impls)
# ======================================================================

def _generate_agent_profiles_impl(request, config):
    """Shared logic for agent-profile generation. NO decorators — called by
    both the teacher and student view functions so decorators never fire twice."""
    body = request.data
    try:
        result = generate_agent_profiles_json(
            topic=body.get("topic", ""),
            language=body.get("language", "en"),
            role_slots=body.get("roleSlots", []),
            config=config,
        )
        return Response(result, status=status.HTTP_200_OK)
    except AgentValidationError as e:
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


def _regenerate_one_agent_impl(request, config):
    """Shared logic for regenerating a single agent distinct from the rest."""
    body = request.data
    try:
        result = regenerate_one_agent(
            topic=body.get("topic", ""),
            language=body.get("language", "en"),
            existing_agents=body.get("existingAgents", []),
            target_agent_id=body.get("targetAgentId", ""),
            locked_fields=body.get("lockedFields", []),
            config=config,
        )
        return Response(result, status=status.HTTP_200_OK)
    except AgentValidationError as e:
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
@check_feature("feature_maic")
def teacher_maic_regenerate_one_agent(request):
    """Regenerate one agent (teacher variant)."""
    config, err = _get_ai_config(request.tenant)
    if err:
        return err
    return _regenerate_one_agent_impl(request, config)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@student_or_admin
@tenant_required
@check_feature("feature_maic")
def student_maic_generate_agent_profiles(request):
    """Generate agent profiles (student variant — same logic as teacher)."""
    config, err = _get_ai_config(request.tenant)
    if err:
        return err
    return _generate_agent_profiles_impl(request, config)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@student_or_admin
@tenant_required
@check_feature("feature_maic")
def student_maic_regenerate_one_agent(request):
    """Regenerate one agent (student variant)."""
    config, err = _get_ai_config(request.tenant)
    if err:
        return err
    return _regenerate_one_agent_impl(request, config)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
@check_feature("feature_maic")
def teacher_maic_tts_preview(request):
    """Synthesize a short TTS preview for the wizard's voice-picker.

    Input JSON: {"voiceId": "en-IN-...", "text": "..."}
    Returns audio/mpeg bytes, or HTTP 204 when TTS is unavailable so the UI
    can fall back cleanly.

    The response always carries an `X-TTS-Status` header:
    - `ok`          — audio payload present
    - `unavailable` — provider not configured or returned empty; safe to
                      silently skip the preview without warning the user
    - `error`       — unexpected failure (should be rare; frontend may
                      surface a banner)
    Frontend treats only `error` as a reason to warn the user.
    """
    config, err = _get_ai_config(request.tenant)
    if err:
        return err
    body = request.data
    voice_id = body.get("voiceId")
    text = (body.get("text") or "")[:200]  # cap length — this is a preview
    try:
        audio_bytes = generate_tts_audio(text, config, voice_id=voice_id)
    except Exception as exc:  # noqa: BLE001 — defensive boundary
        logger.warning("tts_preview unexpected error: %s", exc)
        resp = HttpResponse(status=204)
        resp["X-TTS-Status"] = "error"
        return resp
    if not audio_bytes:
        resp = HttpResponse(status=204)
        resp["X-TTS-Status"] = "unavailable"
        return resp
    resp = HttpResponse(audio_bytes, content_type="audio/mpeg")
    resp["X-TTS-Status"] = "ok"
    return resp


# ======================================================================
# Admin AI Config Endpoints
# ======================================================================

@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
@tenant_required
def tenant_ai_config_view(request):
    """
    GET: Return current AI provider configuration (keys masked).
    PATCH: Update AI provider settings.
    Admin only.
    """
    if request.user.role not in ("SCHOOL_ADMIN", "SUPER_ADMIN"):
        return Response({"error": "Admin access required."}, status=status.HTTP_403_FORBIDDEN)

    config, created = TenantAIConfig.objects.get_or_create(
        tenant=request.tenant,
        defaults={"maic_enabled": False},
    )

    if request.method == "GET":
        llm_key = config.get_llm_api_key()
        tts_key = config.get_tts_api_key()
        img_key = config.get_image_api_key()

        return Response({
            "llm_provider": config.llm_provider,
            "llm_model": config.llm_model,
            "llm_api_key_set": bool(llm_key),
            "llm_api_key_preview": f"...{llm_key[-4:]}" if len(llm_key) > 4 else "",
            "llm_base_url": config.llm_base_url,
            "tts_provider": config.tts_provider,
            "tts_api_key_set": bool(tts_key),
            "tts_voice_id": config.tts_voice_id,
            "image_provider": config.image_provider,
            "image_api_key_set": bool(img_key),
            "maic_enabled": config.maic_enabled,
            "max_classrooms_per_teacher": config.max_classrooms_per_teacher,
        })

    # PATCH
    data = request.data
    if "llm_provider" in data:
        config.llm_provider = data["llm_provider"]
    if "llm_model" in data:
        config.llm_model = data["llm_model"]
    if "llm_api_key" in data and data["llm_api_key"]:
        config.set_llm_api_key(data["llm_api_key"])
    if "llm_base_url" in data:
        config.llm_base_url = data["llm_base_url"]
    if "tts_provider" in data:
        config.tts_provider = data["tts_provider"]
    if "tts_api_key" in data and data["tts_api_key"]:
        config.set_tts_api_key(data["tts_api_key"])
    if "tts_voice_id" in data:
        config.tts_voice_id = data["tts_voice_id"]
    if "image_provider" in data:
        config.image_provider = data["image_provider"]
    if "image_api_key" in data and data["image_api_key"]:
        config.set_image_api_key(data["image_api_key"])
    if "maic_enabled" in data:
        config.maic_enabled = bool(data["maic_enabled"])
    if "max_classrooms_per_teacher" in data:
        config.max_classrooms_per_teacher = int(data["max_classrooms_per_teacher"])

    config.save()

    from utils.audit import log_audit
    log_audit("SETTINGS_CHANGE", "TenantAIConfig", target_id=str(config.id),
              target_repr=str(config.tenant), request=request)

    return Response({"status": "updated"})
