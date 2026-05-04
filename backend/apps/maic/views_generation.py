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

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView


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
      languageModelId: str (optional, default "stub") — provider id;
                        "stub" is the deterministic test path,
                        anything else routes to OpenRouter / etc via
                        ai_adapter.resolve_chat_model.

    Response 202:
      { job_id: str, ws_url: str, tenant_id: str|int }

    Response 400:
      { error: "<reason>" }

    The view returns 202 (Accepted) since the work is queued, not
    completed. The client opens ws_url to watch progress.
    """

    permission_classes = [IsAuthenticated]

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

        language_model_id = body.get("languageModelId", "stub")
        if not isinstance(language_model_id, str):
            return Response(
                {"error": "languageModelId must be a string"},
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
