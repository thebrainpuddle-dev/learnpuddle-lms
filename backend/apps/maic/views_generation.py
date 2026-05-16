"""POST /api/maic/v2/generate/ — enqueue a v2 generation run (Phase 4, MAIC-428.4).

The view validates a small request payload, inserts a
MaicGenerationJob row scoped to the user's tenant, enqueues the
Celery chain (outline_task → scene_dispatch_task → finalize_task),
and returns `{job_id, ws_url}` so the client can immediately open
the WebSocket and watch progress events stream by.

The chain runs asynchronously on a Celery worker. The HTTP response
returns within milliseconds — the client should NOT block on
generation completing; it watches the WS event stream instead.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.maic.exceptions import MaicConfigError
from apps.maic.llm_config import resolve_tenant_llm_runtime_config
from apps.maic.permissions import MaicV2TenantPermission


logger = logging.getLogger("apps.maic.views_generation")


_LANGUAGE_LABELS = {
    "en": "English",
    "hi": "Hindi",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "pt": "Portuguese",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "ar": "Arabic",
}


def _build_generation_ws_url(request: Request, job_id: str) -> str:
    proto = "wss" if request.is_secure() else "ws"
    host = request.get_host()
    return f"{proto}://{host}/ws/maic/generation/{job_id}/"


class MaicGenerationCreateView(APIView):
    """POST /api/maic/v2/generate/ — kick off a generation run.

    Request body:
      topic: str (required) — the classroom topic.
      agentCount: int (optional, default 4) — number of student
                   agents (1-10).
      language: str (optional, default "English") — target language
                 for the generated content.
      level: str (optional, default "intermediate") — target student
             level (beginner / intermediate / advanced).
      specifications: str (optional) — free-form text with extra
                       constraints / preferences (passed verbatim to
                       the outline-generation prompt).
      languageModelId: str (optional) — normally omitted. Production
                        resolves from the school's TenantAIConfig; a
                        request override is accepted only when the
                        deploy explicitly enables it.

    Response 202:
      { job_id: str, ws_url: str, tenant_id: str|int }

    Response 400:
      { error: "<reason>" }

    The view returns 202 (Accepted) since the work is queued, not
    completed. The client opens ws_url to watch progress.
    """

    permission_classes = [IsAuthenticated, MaicV2TenantPermission]

    def post(self, request: Request) -> Response:
        user = request.user
        tenant_id = getattr(user, "tenant_id", None)
        if tenant_id is None:
            return Response(
                {"error": "user has no tenant"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        body: dict[str, Any] = (
            request.data if isinstance(request.data, dict) else {}
        )

        # ── Validate required fields ──
        topic = body.get("topic")
        if not isinstance(topic, str) or not topic.strip():
            return Response(
                {"error": "topic is required (non-empty string)"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── Validate optional fields with defaults ──
        agent_count = body.get("agentCount", 4)
        if type(agent_count) is not int or not (1 <= agent_count <= 10):
            return Response(
                {"error": "agentCount must be an int in [1, 10]"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        language = body.get("language", "English")
        if not isinstance(language, str) or not language.strip():
            return Response(
                {"error": "language must be a non-empty string"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        level = body.get("level", "intermediate")
        if not isinstance(level, str) or not level.strip():
            return Response(
                {"error": "level must be a non-empty string"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        specifications = body.get("specifications", "") or ""
        if not isinstance(specifications, str):
            return Response(
                {"error": "specifications must be a string"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        scene_count = body.get("sceneCount", None)
        if scene_count is not None and (
            type(scene_count) is not int or not (1 <= scene_count <= 20)
        ):
            return Response(
                {"error": "sceneCount must be an int in [1, 20]"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        grade_level, grade_error = _optional_text(
            _first_present(body, "gradeLevel", "grade_level"),
            "gradeLevel",
            max_chars=120,
        )
        if grade_error:
            return Response({"error": grade_error}, status=status.HTTP_400_BAD_REQUEST)

        subject, subject_error = _optional_text(
            body.get("subject"),
            "subject",
            max_chars=160,
        )
        if subject_error:
            return Response(
                {"error": subject_error},
                status=status.HTTP_400_BAD_REQUEST,
            )

        syllabus_board, board_error = _optional_text(
            _first_present(body, "syllabusBoard", "syllabus_board"),
            "syllabusBoard",
            max_chars=120,
        )
        if board_error:
            return Response(
                {"error": board_error},
                status=status.HTTP_400_BAD_REQUEST,
            )

        class_guide, guide_error = _optional_text(
            _first_present(body, "classGuide", "class_guide"),
            "classGuide",
            max_chars=4000,
        )
        if guide_error:
            return Response(
                {"error": guide_error},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Chunk 3a — typed pedagogy fields. These surface the things the
        # planning contract already names ("misconceptions, checks,
        # PBL/activity brief, discussion handoffs") as structured input
        # rather than burying them in the free-form classGuide blob. All
        # optional; absent → behaves exactly like origin/main.
        learning_objective, lo_error = _optional_text(
            _first_present(body, "learningObjective", "learning_objective"),
            "learningObjective",
            max_chars=500,
        )
        if lo_error:
            return Response(
                {"error": lo_error},
                status=status.HTTP_400_BAD_REQUEST,
            )

        misconceptions, mis_error = _optional_string_list(
            _first_present(body, "misconceptions"),
            "misconceptions",
            max_items=5,
            max_chars=200,
        )
        if mis_error:
            return Response(
                {"error": mis_error},
                status=status.HTTP_400_BAD_REQUEST,
            )

        success_criteria, sc_error = _optional_string_list(
            _first_present(body, "successCriteria", "success_criteria"),
            "successCriteria",
            max_items=5,
            max_chars=200,
        )
        if sc_error:
            return Response(
                {"error": sc_error},
                status=status.HTTP_400_BAD_REQUEST,
            )

        pbl_brief, pbl_brief_error = _optional_text(
            _first_present(body, "pblBrief", "pbl_brief"),
            "pblBrief",
            max_chars=1000,
        )
        if pbl_brief_error:
            return Response(
                {"error": pbl_brief_error},
                status=status.HTTP_400_BAD_REQUEST,
            )

        pdf_text, pdf_error = _optional_text(
            _first_present(body, "pdfText", "pdf_text"),
            "pdfText",
            max_chars=50000,
        )
        if pdf_error:
            return Response(
                {"error": pdf_error},
                status=status.HTTP_400_BAD_REQUEST,
            )

        research_context, research_error = _optional_text(
            _first_present(body, "researchContext", "research_context"),
            "researchContext",
            max_chars=20000,
        )
        if research_error:
            return Response(
                {"error": research_error},
                status=status.HTTP_400_BAD_REQUEST,
            )

        agents, agents_error = _optional_agents(body.get("agents"))
        if agents_error:
            return Response(
                {"error": agents_error},
                status=status.HTTP_400_BAD_REQUEST,
            )

        enable_pbl, pbl_error = _optional_bool(
            body.get("enablePBL"),
            "enablePBL",
            default=True,
        )
        if pbl_error:
            return Response({"error": pbl_error}, status=status.HTTP_400_BAD_REQUEST)

        image_generation_default = _tenant_default_image_generation_enabled(tenant_id)
        enable_image_generation, image_error = _optional_bool(
            body.get("enableImageGeneration", body.get("enableImages")),
            "enableImageGeneration",
            default=image_generation_default,
        )
        if image_error:
            return Response({"error": image_error}, status=status.HTTP_400_BAD_REQUEST)

        enable_video_generation, video_error = _optional_bool(
            body.get("enableVideoGeneration", body.get("enableVideos")),
            "enableVideoGeneration",
            default=False,
        )
        if video_error:
            return Response({"error": video_error}, status=status.HTTP_400_BAD_REQUEST)

        content_title = body.get("contentTitle", None)
        if content_title is not None and not isinstance(content_title, str):
            return Response(
                {"error": "contentTitle must be a string"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        is_public = body.get("isPublic", None)
        if is_public is not None and not isinstance(is_public, bool):
            return Response(
                {"error": "isPublic must be a boolean"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        course_id, course_error = _optional_uuid(body.get("courseId"), "courseId")
        if course_error:
            return Response(
                {"error": course_error},
                status=status.HTTP_400_BAD_REQUEST,
            )
        module_id, module_error = _optional_uuid(body.get("moduleId"), "moduleId")
        if module_error:
            return Response(
                {"error": module_error},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if getattr(user, "role", None) == "STUDENT":
            if course_id or module_id:
                return Response(
                    {"error": "students cannot attach generated classrooms to LMS courses"},
                    status=status.HTTP_403_FORBIDDEN,
                )
            if is_public is True:
                return Response(
                    {"error": "students cannot publish generated classrooms"},
                    status=status.HTTP_403_FORBIDDEN,
                )

        target_error, target_ids = _validate_lms_targets(
            tenant_id=tenant_id,
            course_id=course_id,
            module_id=module_id,
        )
        if target_error:
            return Response(
                {"error": target_error},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            llm_config = resolve_tenant_llm_runtime_config(
                tenant=getattr(user, "tenant", None),
                tenant_id=tenant_id,
                requested=body.get("languageModelId"),
            )
            language_model_id = str(llm_config["language_model_id"])
        except MaicConfigError as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── Build canonical requirements payload + insert row + enqueue ──
        # Imports inside the method so the test runner can patch them
        # cleanly + so tasks.py doesn't get imported at module load
        # (Celery's @shared_task auto-registers when the module is
        # first imported, which we want to delay until app-ready).
        from apps.maic.generation.tasks import (
            create_job_session,
            enqueue_generation_chain,
        )

        topic = topic.strip()
        specifications = specifications.strip()
        language = language.strip()
        level = level.strip()
        teacher_context = _build_teacher_context(
            class_guide=class_guide,
            grade_level=grade_level,
            subject=subject,
            syllabus_board=syllabus_board,
            scene_count=scene_count,
            learning_objective=learning_objective,
            misconceptions=misconceptions,
            success_criteria=success_criteria,
            pbl_brief=pbl_brief,
        )
        requirement_text = _build_requirement_text(
            topic=topic,
            language=language,
            level=level,
            specifications=specifications,
            scene_count=scene_count,
            grade_level=grade_level,
            subject=subject,
            syllabus_board=syllabus_board,
            enable_pbl=enable_pbl,
        )

        requirements = {
            "topic": topic,
            "requirement": requirement_text,
            "agentCount": agent_count,
            "language": language,
            "languageLabel": _language_label(language),
            "level": level,
            "specifications": specifications,
            "languageModelId": language_model_id,
            "enablePBL": enable_pbl,
            "enableImageGeneration": enable_image_generation,
            "enableVideoGeneration": enable_video_generation,
        }
        if scene_count is not None:
            requirements["sceneCount"] = scene_count
        if grade_level:
            requirements["gradeLevel"] = grade_level
        if subject:
            requirements["subject"] = subject
        if syllabus_board:
            requirements["syllabusBoard"] = syllabus_board
        if class_guide:
            requirements["classGuide"] = class_guide
        # Chunk 3a — persist typed pedagogy fields onto requirements so
        # generation tasks downstream (outline / scene / pbl design) can
        # consult them directly, not just through the rendered teacher
        # context string.
        if learning_objective:
            requirements["learningObjective"] = learning_objective
        if misconceptions:
            requirements["misconceptions"] = misconceptions
        if success_criteria:
            requirements["successCriteria"] = success_criteria
        if pbl_brief:
            requirements["pblBrief"] = pbl_brief
        if teacher_context:
            requirements["teacherContext"] = teacher_context
        if pdf_text:
            requirements["pdfText"] = pdf_text
        if research_context:
            requirements["researchContext"] = research_context
        if agents:
            requirements["agents"] = agents
        if content_title is not None:
            requirements["contentTitle"] = content_title.strip()
        if is_public is not None:
            requirements["isPublic"] = is_public
        requirements.update(target_ids)

        job = create_job_session(
            tenant_id=tenant_id,
            user_id=getattr(user, "id", None),
            requirements=requirements,
        )

        try:
            enqueue_generation_chain(job.id)
        except Exception as exc:  # noqa: BLE001
            # Broker unreachable — surface as 503 so the client can
            # retry. The job row stays as `pending` for the operator
            # to inspect (a follow-up worker tick can still pick it
            # up if a janitor task is wired in Phase 5+).
            logger.error(
                "Generation enqueue failed for job=%s: %s", job.id, exc
            )
            return Response(
                {"error": "generation queue unavailable; try again later"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(
            {
                "job_id": job.id,
                "ws_url": _build_generation_ws_url(request, job.id),
                "tenant_id": tenant_id,
            },
            status=status.HTTP_202_ACCEPTED,
        )


class MaicGenerationDetailView(APIView):
    """GET /api/maic/v2/generate/<job_id>/ — poll job state.

    Mirrors OpenMAIC's async contract while keeping the heavy classroom
    artifact in ``MAICClassroom``. By default the response strips generated
    scene blobs from ``result``; pass ``?full=1`` for operator/debug reads.
    """

    permission_classes = [IsAuthenticated, MaicV2TenantPermission]

    def get(self, request: Request, job_id: str) -> Response:
        tenant_id = getattr(request.user, "tenant_id", None)
        if tenant_id is None:
            return Response(
                {"error": "user has no tenant"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from apps.maic.models import MaicGenerationJob

        try:
            job = MaicGenerationJob.objects.all_tenants().get(
                pk=job_id,
                tenant_id=tenant_id,
            )
        except MaicGenerationJob.DoesNotExist:
            return Response(
                {"error": "generation job not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        include_full = request.query_params.get("full") == "1"
        result = _public_result(job.result or {}, include_full=include_full)
        progress = job.progress or {}
        scenes_generated = _scene_count(job.result or {}, progress)
        total_scenes = (
            progress.get("total")
            or result.get("scenesCount")
            or scenes_generated
        )

        return Response(
            {
                "job_id": job.id,
                "status": job.status,
                "step": progress.get("stage"),
                "progress": progress,
                "message": progress.get("message", ""),
                "scenesGenerated": scenes_generated,
                "totalScenes": total_scenes,
                "result": result,
                "error": job.error or None,
                "done": job.status in {
                    MaicGenerationJob.STATUS_SUCCEEDED,
                    MaicGenerationJob.STATUS_FAILED,
                },
                "created_at": job.created_at.isoformat(),
                "updated_at": job.updated_at.isoformat(),
                "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            },
            status=status.HTTP_200_OK,
        )


def _optional_uuid(value: Any, field_name: str) -> tuple[str | None, str | None]:
    if value in (None, ""):
        return None, None
    if not isinstance(value, str):
        return None, f"{field_name} must be a UUID string"
    try:
        return str(UUID(value)), None
    except ValueError:
        return None, f"{field_name} must be a valid UUID"


def _first_present(body: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in body:
            return body[key]
    return None


def _optional_text(
    value: Any,
    field_name: str,
    *,
    max_chars: int,
) -> tuple[str | None, str | None]:
    if value in (None, ""):
        return None, None
    if not isinstance(value, str):
        return None, f"{field_name} must be a string"
    trimmed = value.strip()
    if not trimmed:
        return None, None
    if len(trimmed) > max_chars:
        return None, f"{field_name} must be at most {max_chars} characters"
    return trimmed, None


def _optional_bool(
    value: Any,
    field_name: str,
    *,
    default: bool,
) -> tuple[bool, str | None]:
    if value is None:
        return default, None
    if not isinstance(value, bool):
        return default, f"{field_name} must be a boolean"
    return value, None


def _tenant_default_image_generation_enabled(tenant_id: int) -> bool:
    """Default v2 image generation from the tenant's real image provider.

    Teachers should not have to know an implementation flag to get images in
    production classrooms. Explicit request values still win; this only fills
    the omitted-field case from TenantAIConfig.
    """
    from apps.courses.maic_models import TenantAIConfig

    config = TenantAIConfig.objects.filter(tenant_id=tenant_id).first()
    if config is None:
        return False
    provider = (config.image_provider or "").strip().lower()
    return bool(provider and provider != "disabled")


def _optional_agents(value: Any) -> tuple[list[dict[str, Any]], str | None]:
    if value in (None, ""):
        return [], None
    if not isinstance(value, list):
        return [], "agents must be a list"
    if len(value) > 10:
        return [], "agents must contain at most 10 items"
    for idx, item in enumerate(value):
        if not isinstance(item, dict):
            return [], f"agents[{idx}] must be an object"
    return value, None


def _optional_string_list(
    value: Any,
    field_name: str,
    *,
    max_items: int,
    max_chars: int,
) -> tuple[list[str], str | None]:
    """Parse an optional `list[str]` field with per-item length cap.

    Used by Chunk 3a pedagogy fields (misconceptions, successCriteria)
    to surface structured class-guide intent on the v2 generate POST.
    Empty / missing → empty list (no error). Non-string items, oversized
    items, or oversized lists → 400-style error string for the view to
    surface.

    Mirrors `_optional_agents` shape and `_optional_text` length-limit
    discipline so the surrounding parsing code stays uniform.
    """
    if value in (None, ""):
        return [], None
    if not isinstance(value, list):
        return [], f"{field_name} must be a list of strings"
    if len(value) > max_items:
        return [], f"{field_name} must contain at most {max_items} items"
    cleaned: list[str] = []
    for idx, item in enumerate(value):
        if not isinstance(item, str):
            return [], f"{field_name}[{idx}] must be a string"
        trimmed = item.strip()
        if not trimmed:
            # Blank entries are silently dropped — UI gives users 3-5
            # always-rendered input rows; submitting with 2 filled is
            # the common case, not an error.
            continue
        if len(trimmed) > max_chars:
            return [], (
                f"{field_name}[{idx}] must be at most {max_chars} characters"
            )
        cleaned.append(trimmed)
    return cleaned, None


def _language_label(language: str) -> str:
    value = language.strip()
    return _LANGUAGE_LABELS.get(value.lower(), value or "English")


def _build_requirement_text(
    *,
    topic: str,
    language: str,
    level: str,
    specifications: str,
    scene_count: int | None,
    grade_level: str | None,
    subject: str | None,
    syllabus_board: str | None,
    enable_pbl: bool,
) -> str:
    lines = [
        f"Topic: {topic}",
        f"Teaching language: {_language_label(language)}",
        f"Difficulty level: {level}",
    ]
    if scene_count is not None:
        lines.append(f"Create exactly {scene_count} scenes.")
    if grade_level:
        lines.append(f"Audience grade level: {grade_level}")
    if subject:
        lines.append(f"Subject: {subject}")
    if syllabus_board:
        lines.append(f"Syllabus/curriculum board: {syllabus_board}")
    if enable_pbl:
        lines.append(
            "Include one project-based learning or hands-on collaboration "
            "moment when the topic genuinely benefits from it; keep it "
            "tightly connected to the lesson goal."
        )
    else:
        lines.append(
            "Do not include project-based learning scenes; use slide, quiz, "
            "or interactive scenes only."
        )
    if specifications:
        lines.extend(["", "Additional teacher requirements:", specifications])
    return "\n".join(lines)


def _build_teacher_context(
    *,
    class_guide: str | None,
    grade_level: str | None,
    subject: str | None,
    syllabus_board: str | None,
    scene_count: int | None,
    learning_objective: str | None = None,
    misconceptions: list[str] | None = None,
    success_criteria: list[str] | None = None,
    pbl_brief: str | None = None,
) -> str:
    lines: list[str] = []
    class_frame = [
        f"Grade level: {grade_level}" if grade_level else "",
        f"Subject: {subject}" if subject else "",
        f"Syllabus/curriculum board: {syllabus_board}" if syllabus_board else "",
        f"Target scene count: {scene_count}" if scene_count is not None else "",
    ]
    class_frame = [line for line in class_frame if line]
    if class_frame:
        lines.append("## Teacher Class Context")
        lines.extend(f"- {line}" for line in class_frame)
    # Chunk 3a — typed pedagogy targets. Emit each populated field as
    # an explicit, labeled bullet so the LLM can honor the planning
    # contract's stated rules ("Reflect ... misconceptions, checks,
    # PBL/activity brief, and discussion handoffs"). The teacher-class-
    # guide free-text remains below as the human's narrative wrapper.
    pedagogy: list[str] = []
    if learning_objective:
        pedagogy.append(f"Learning objective: {learning_objective}")
    if misconceptions:
        pedagogy.append("Misconceptions to address:")
        pedagogy.extend(f"  - {item}" for item in misconceptions)
    if success_criteria:
        pedagogy.append("Success criteria:")
        pedagogy.extend(f"  - {item}" for item in success_criteria)
    if pbl_brief:
        pedagogy.append(f"PBL brief: {pbl_brief}")
    if pedagogy:
        if lines:
            lines.append("")
        lines.append("## Pedagogy Targets")
        lines.extend(f"- {line}" if not line.startswith(" ") else line for line in pedagogy)
    if class_guide:
        if lines:
            lines.append("")
        lines.append("## Teacher Class Guide")
        lines.append(class_guide)
    return "\n".join(lines)


def _validate_lms_targets(
    *,
    tenant_id: int,
    course_id: str | None,
    module_id: str | None,
) -> tuple[str | None, dict[str, str]]:
    from apps.courses.models import Course, Module

    resolved: dict[str, str] = {}
    course = None
    if course_id:
        course = (
            Course.all_objects.all_tenants()
            .filter(pk=course_id, tenant_id=tenant_id, is_deleted=False)
            .first()
        )
        if course is None:
            return "courseId does not belong to this tenant", {}
        resolved["courseId"] = str(course.id)

    if module_id:
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
            return "moduleId does not belong to this tenant", {}
        if course is not None and module.course_id != course.id:
            return "moduleId must belong to courseId", {}
        resolved["moduleId"] = str(module.id)
        resolved["courseId"] = str(module.course_id)

    return None, resolved


def _public_result(
    result: dict[str, Any],
    *,
    include_full: bool,
) -> dict[str, Any]:
    if include_full:
        return dict(result)
    return {
        key: value
        for key, value in result.items()
        if key not in {"scenes", "outlines"}
    }


def _scene_count(result: dict[str, Any], progress: dict[str, Any]) -> int:
    scenes = result.get("scenes")
    if isinstance(scenes, list):
        return len(scenes)
    completed = progress.get("completed")
    try:
        return int(completed)
    except (TypeError, ValueError):
        return 0
