"""HTTP API for the PBL subsystem (Phase 7, MAIC-704).

POST /api/maic/v2/pbl/projects/
    Validate request, create a MaicPBLSession in DRAFT status,
    run the design agentic loop synchronously (a single LLM
    multi-step call; bounded to 30 LLM steps + 1 post-process call,
    typically 30-90s), persist the resulting PBLProjectConfig, and
    return the session row plus a chat WS URL the client opens to
    interact with the project.

Why synchronous (not Celery-queued like apps/maic/views_generation):
the design loop is a single conversation with a single LLM, not a
fan-out pipeline. Wrapping it in Celery would add infrastructure
overhead (broker, result backend, polling) for no parallelism gain.
The loop's 30-step ceiling caps tail latency. Long-running clients
keep the connection open — same posture as upstream OpenMAIC's
/api/pbl/* routes.

A future MAIC-704+ may move this to Celery if classroom usage
shows the synchronous timeout window is unacceptable; the design
loop's API is callable either way.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.maic.exceptions import MaicConfigError
from apps.maic_pbl.design_graph import (
    GeneratePBLConfig,
    generate_pbl_project,
)
from apps.maic_pbl.models import MaicPBLSession


logger = logging.getLogger("apps.maic_pbl.views")


def _build_pbl_chat_ws_url(request: Request, session_id: str) -> str:
    """Build the WS URL the client opens after project creation to
    interact with the PBL session via chat."""
    proto = "wss" if request.is_secure() else "ws"
    host = request.get_host()
    return f"{proto}://{host}/ws/maic/pbl/{session_id}/"


class PBLProjectCreateView(APIView):
    """POST /api/maic/v2/pbl/projects/ — create a PBL project.

    Request body:
        topic: str (required) — the project topic / lesson seed.
        description: str (optional, default "") — extra context for
            the LLM. Distinct from MaicPBLSession.topic; this lands in
            PBLProjectConfig.projectInfo via the design loop.
        targetSkills: list[str] (optional, default []) — learning-
            outcome keywords; joined with ", " into the prompt.
        issueCount: int (optional, default 3) — how many milestones
            the design loop should aim for. Upstream cap is loose —
            the LLM is free to deviate.
        language: str (optional, default "en") — the IETF tag
            stamped on MaicPBLSession; passed to the design loop as
            languageDirective via the prompt template.
        languageModelId: str (optional, default "stub") — same id
            scheme as apps/maic/views_generation; "stub" for tests,
            real provider ids for production.

    Response 201 (Created):
        {
          session_id: str,            # UUID4 of the new MaicPBLSession
          ws_url:     str,            # /ws/maic/pbl/<session_id>/
          status:     "active"|"failed",
          steps_taken: int,
          reached_idle: bool,
          welcome_generated: bool,
          schema_valid: bool,
        }

    Response 400 — validation error.
    Response 500 — design loop crashed for an unexpected reason.
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

        topic = body.get("topic")
        if not isinstance(topic, str) or not topic.strip():
            return Response(
                {"error": "topic is required (non-empty string)"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        description = body.get("description", "") or ""
        if not isinstance(description, str):
            return Response(
                {"error": "description must be a string"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        target_skills = body.get("targetSkills", [])
        if not isinstance(target_skills, list) or not all(
            isinstance(s, str) for s in target_skills
        ):
            return Response(
                {"error": "targetSkills must be a list of strings"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        issue_count = body.get("issueCount", 3)
        if not isinstance(issue_count, int) or not (1 <= issue_count <= 10):
            return Response(
                {"error": "issueCount must be an int in [1, 10]"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        language = body.get("language", "en")
        if not isinstance(language, str) or not language.strip():
            return Response(
                {"error": "language must be a non-empty string"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        language_model_id = body.get("languageModelId", "stub")
        if not isinstance(language_model_id, str):
            return Response(
                {"error": "languageModelId must be a string"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Resolve the LLM. "stub" is a sentinel that the design loop's
        # tests use; not a real LangChain model — bind_tools won't work.
        # Rejecting it here keeps the API contract honest in production.
        if language_model_id == "stub":
            return Response(
                {"error": "languageModelId 'stub' is for tests only; pick a real provider id"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            from apps.maic.orchestration.ai_adapter import resolve_chat_model

            model = resolve_chat_model(language_model_id)
        except MaicConfigError as exc:
            return Response(
                {"error": f"languageModelId invalid: {exc}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        session = MaicPBLSession.objects.create(
            tenant_id=tenant_id,
            owner_id=getattr(user, "id", None),
            topic=topic,
            language=language,
            agent_count=issue_count,  # field is repurposed for issue count budget
            status=MaicPBLSession.STATUS_DRAFT,
        )

        try:
            cfg = GeneratePBLConfig(
                project_topic=topic,
                project_description=description,
                target_skills=list(target_skills),
                issue_count=issue_count,
                language_directive=_build_language_directive(language),
            )
            result = asyncio.run(generate_pbl_project(cfg, model))
        except Exception as exc:  # noqa: BLE001 — boundary
            logger.exception("PBL design loop crashed for session=%s", session.id)
            session.status = MaicPBLSession.STATUS_FAILED
            session.error_message = str(exc)[:500]
            session.save(update_fields=["status", "error_message", "updated_at"])
            return Response(
                {"error": "design loop crashed", "session_id": str(session.id)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        session.project_config = result.project_config
        if result.error is not None:
            session.error_message = result.error[:500]
            session.status = MaicPBLSession.STATUS_FAILED
        else:
            session.status = MaicPBLSession.STATUS_ACTIVE
        session.save(
            update_fields=["project_config", "error_message", "status", "updated_at"],
        )

        return Response(
            {
                "session_id": str(session.id),
                "ws_url": _build_pbl_chat_ws_url(request, str(session.id)),
                "status": session.status,
                "steps_taken": result.steps_taken,
                "reached_idle": result.reached_idle,
                "welcome_generated": result.welcome_message_generated,
                "schema_valid": result.schema_valid,
            },
            status=status.HTTP_201_CREATED,
        )


def _build_language_directive(language: str) -> str:
    """Map an IETF tag to a one-line directive for the design loop's
    prompt template. Empty string for English (the prompt's default
    language); explicit instruction for non-en codes."""
    lang = language.strip().lower()
    if not lang or lang in {"en", "en-us", "en-gb"}:
        return ""
    return f"All generated content must be in language code: {language}."


class PBLProjectRetrieveView(APIView):
    """GET /api/maic/v2/pbl/projects/<session_id>/ — read-back a PBL
    session by id, tenant-scoped.

    Used by the dev probe (MAIC-707) so the frontend can hydrate
    `MAICPBLContent` from a previously-created session without re-
    running the design loop.

    Response 200:
      {
        session_id: str,
        ws_url:     str,
        status:     "draft"|"active"|"completed"|"failed"|"archived",
        topic:      str,
        language:   str,
        project_config: PBLProjectConfig,
        chat_messages: list[PBLChatMessage],
      }

    Response 404 — session not found OR cross-tenant (we collapse the
    two so an attacker cannot enumerate session ids).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request, session_id: str) -> Response:
        user = request.user
        tenant_id = getattr(user, "tenant_id", None)
        if tenant_id is None:
            return Response(
                {"error": "user has no tenant"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        sess = (
            MaicPBLSession.objects.all_tenants()
            .filter(id=session_id, tenant_id=tenant_id)
            .first()
        )
        if sess is None:
            raise NotFound("PBL session not found")

        return Response(
            {
                "session_id": str(sess.id),
                "ws_url": _build_pbl_chat_ws_url(request, str(sess.id)),
                "status": sess.status,
                "topic": sess.topic,
                "language": sess.language,
                "project_config": sess.project_config,
                "chat_messages": sess.chat_messages,
            },
            status=status.HTTP_200_OK,
        )
