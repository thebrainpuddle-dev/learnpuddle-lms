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
from uuid import UUID
from typing import Any

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.maic.exceptions import MaicConfigError
from apps.maic.llm_config import resolve_tenant_llm_runtime_config
from apps.maic.permissions import MaicV2TenantPermission


logger = logging.getLogger("apps.maic.views_generation")


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
        if not isinstance(agent_count, int) or not (1 <= agent_count <= 10):
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

        requirements = {
            "topic": topic,
            "agentCount": agent_count,
            "language": language,
            "level": level,
            "specifications": specifications,
            "languageModelId": language_model_id,
        }
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
