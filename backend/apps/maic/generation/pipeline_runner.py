"""Top-level pipeline orchestration.

Direct port of upstream `lib/generation/pipeline-runner.ts` (98 lines).

Source:
    https://github.com/THU-MAIC/OpenMAIC/blob/main/lib/generation/pipeline-runner.ts
    /Volumes/CrucialX9/OpenMAIC/lib/generation/pipeline-runner.ts

Two public functions:
  - `create_generation_session(requirements)` — builds an in-memory
    session dict tracking progress, outlines, and scenes.
  - `run_generation_pipeline(session, language_model_id, callbacks)` —
    runs Stage 1 (outline_generator) then Stage 2 (scene_generator).

Phase 4 status:
  - Stage 1 is fully wired (MAIC-421).
  - Stage 2 is fully wired (MAIC-422.0 through .8). Stage 2 forwards
    to scene_generator.generate_full_scenes, which runs all scenes
    through asyncio.gather (parallel). Celery wraps the call in
    Session 6 (MAIC-428.x) but doesn't change the in-process pipeline.

The upstream `StageStore` parameter is NOT carried forward in this
port. Upstream's stage store is the in-app classroom-editor state;
Phase 4 returns scene dicts directly via `data.scenes` so the Celery
finalize task can persist them via the WS HTTP route. The store
parameter is available again in Phase 5+ if we need editor-mode
generation.

Used by:
    - apps.maic.generation.tasks (Celery chain — Session 6)
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone
from typing import Any, TypedDict

from apps.maic.generation.outline_generator import (
    generate_scene_outlines_from_requirements,
)
from apps.maic.generation.scene_generator import generate_full_scenes
from apps.maic.generation.types import (
    GenerationCallbacks,
    GenerationProgress,
    GenerationResult,
    SceneOutline,
)


_logger = logging.getLogger("apps.maic.generation.pipeline_runner")


# ── GenerationSession TypedDict ───────────────────────────────────


class GenerationSession(TypedDict, total=False):
    """In-memory session state.

    Mirrors upstream's `GenerationSession` (lib/types/generation).
    Built by `create_generation_session`; populated by
    `run_generation_pipeline` as stages complete.
    """

    id: str
    requirements: dict[str, Any]
    progress: GenerationProgress
    sceneOutlines: list[SceneOutline]
    scenes: list[dict[str, Any]]
    languageDirective: str
    startedAt: str  # ISO 8601
    completedAt: str  # ISO 8601 (when set)
    errors: list[str]


# ── Public API ────────────────────────────────────────────────────


def create_generation_session(
    requirements: dict[str, Any],
) -> GenerationSession:
    """Build an in-memory session dict.

    Mirrors upstream `createGenerationSession`. Returns a session
    with a fresh id, the supplied requirements, and progress at
    Stage 1 / 0%.
    """
    return {
        "id": _generate_session_id(),
        "requirements": requirements,
        "progress": {
            "stage": 1,
            "completed": 0,
            "total": 0,
            "message": "Initializing...",
        },
        "sceneOutlines": [],
        "scenes": [],
        "languageDirective": "",
        "startedAt": datetime.now(timezone.utc).isoformat(),
    }


async def run_generation_pipeline(
    session: GenerationSession,
    *,
    language_model_id: str = "stub",
    callbacks: GenerationCallbacks | None = None,
) -> GenerationResult:
    """Run the full two-stage generation pipeline.

    Mirrors upstream `runGenerationPipeline`. Stage 1 calls
    `generate_scene_outlines_from_requirements`; Stage 2 currently
    returns an empty `scenes` list (DEFERRED — full Stage 2 lands
    in Session 3-5 via MAIC-422.x).

    Args:
        session: built via `create_generation_session`.
        language_model_id: provider id passed to both stages.
        callbacks: optional progress / stage-complete / error hooks.

    Returns:
        GenerationResult with `data` = the same `session` dict
        populated with outlines, scenes, and final progress.
    """
    on_progress = callbacks and callbacks.get("onProgress")
    on_stage_complete = callbacks and callbacks.get("onStageComplete")
    on_error = callbacks and callbacks.get("onError")

    try:
        # ── Stage 1 — Outlines ──
        if on_progress:
            on_progress({
                "stage": 1,
                "completed": 0,
                "total": 0,
                "message": "Analyzing requirements, generating outlines...",
            })

        outlines_result = await generate_scene_outlines_from_requirements(
            session["requirements"],
            None,  # pdf_text — DEFERRED
            None,  # pdf_images — DEFERRED
            language_model_id=language_model_id,
            callbacks=callbacks,
        )

        if not outlines_result.get("success") or "data" not in outlines_result:
            raise RuntimeError(
                outlines_result.get("error", "Failed to generate scene outlines")
            )

        outlines_data = outlines_result["data"]
        outlines: list[SceneOutline] = outlines_data["outlines"]
        language_directive: str = outlines_data["languageDirective"]
        session["sceneOutlines"] = outlines
        session["languageDirective"] = language_directive

        if on_stage_complete:
            on_stage_complete(1, outlines)

        # ── Stage 2 — Full Scenes (parallel; MAIC-422.8) ──
        if on_progress:
            on_progress({
                "stage": 2,
                "completed": 0,
                "total": len(outlines),
                "message": "Generating scene content...",
            })

        # Pull agents from the requirements (the v2 generation
        # endpoint forwards `agents` here when set; otherwise we
        # ship an empty list — scene_generator handles that).
        requirements = session.get("requirements") or {}
        agents = requirements.get("agents") or []
        user_profile = requirements.get("userProfile") or ""
        teacher_context = requirements.get("teacherContext") or ""

        scenes = await generate_full_scenes(
            outlines,
            language_model_id=language_model_id,
            language_directive=language_directive,
            agents=agents,
            user_profile=user_profile,
            teacher_context=teacher_context,
            callbacks=callbacks,
        )
        session["scenes"] = scenes

        if on_stage_complete:
            on_stage_complete(2, scenes)

        # ── Completion ──
        session["completedAt"] = datetime.now(timezone.utc).isoformat()
        session["progress"] = {
            "stage": 2,
            "completed": len(scenes),
            "total": len(outlines),
            "message": "Generation complete!",
        }

        return {"success": True, "data": session}

    except Exception as exc:  # noqa: BLE001 — wrap into GenerationResult
        error_message = str(exc)
        if on_error:
            on_error(error_message)
        session.setdefault("errors", []).append(error_message)
        return {"success": False, "error": error_message}


# ── Internal helpers ──────────────────────────────────────────────


def _generate_session_id() -> str:
    """12-char URL-safe id; equivalent to upstream's `nanoid()`."""
    return secrets.token_urlsafe(9).replace("-", "").replace("_", "")[:12]

