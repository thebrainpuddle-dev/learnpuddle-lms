"""Celery tasks for the v2 generation pipeline (Phase 4 Session 6).

This module wraps the synchronous in-process pipeline
(`pipeline_runner.run_generation_pipeline`) into a Celery chain so the
HTTP route can return a `{job_id}` immediately while the work runs in
a worker.

MAIC-428.1 (this chunk) ships the outer chain skeleton:

    chain(outline_task.s(job_id), scene_dispatch_task.s(), finalize_task.s())

  - outline_task: marks the job in_progress, runs Stage 1 (outlines)
    via run_generation_pipeline (Stage 2 happens in scene_dispatch_task
    instead). For 428.1 the simplest path is "Stage 1 here, scenes in
    next task" — keeps one task per stage. The ordering matches the WS
    consumer's expected progress events: outline_done → scene_done×N
    → finalized.

  - scene_dispatch_task: 428.1 runs generate_full_scenes inline (the
    in-process parallel asyncio.gather path). MAIC-428.2 fans out to
    a chord(group(scene_task.s() for each), scenes_finalize.s()) and
    drops the inline path.

  - finalize_task: writes status=succeeded, fills result.scenes, sets
    completed_at, and emits the WS finalized event.

Failure handling: any task raising bubbles up via Celery's task chain
semantics. We attach a `link_error` to the chain that flips the job
to status=failed and emits an WS error event. Transient infra errors
(OperationalError / ConnectionError) auto-retry up to 3× with
exponential backoff (mirrors apps/courses/maic_tasks.py's pattern).

Used by:
    - apps.maic.views_generation (POST endpoint, MAIC-428.4)
    - apps.maic.generation.consumers (WS reader, MAIC-428.3)
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from celery import chain, shared_task
from django.db import DatabaseError, OperationalError

from apps.maic.generation.pipeline_runner import (
    create_generation_session,
    run_generation_pipeline,
)
from apps.maic.generation.scene_generator import generate_full_scenes
from apps.maic.generation.outline_generator import (
    generate_scene_outlines_from_requirements,
)
from apps.maic.models import MaicGenerationJob


_logger = logging.getLogger("apps.maic.generation.tasks")


# ── Pipeline chain entry point ────────────────────────────────────


def enqueue_generation_chain(job_id: str) -> Any:
    """Build and apply_async the outline→dispatch→finalize chain.

    The DRF view (MAIC-428.4) calls this AFTER inserting the
    MaicGenerationJob row. Returns the AsyncResult of the chain so
    callers can store the task id if they want to track via Celery's
    inspect API (the WS consumer does NOT need this — it watches the
    DB row + pubsub group).
    """
    workflow = chain(
        outline_task.s(job_id=job_id),
        scene_dispatch_task.s(),
        finalize_task.s(),
    )
    workflow.link_error(mark_job_failed.s(job_id=job_id))
    return workflow.apply_async()


# ── Outline (Stage 1) ─────────────────────────────────────────────


@shared_task(
    name="apps.maic.generation.tasks.outline_task",
    autoretry_for=(OperationalError, DatabaseError, ConnectionError),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=120,
    retry_jitter=True,
)
def outline_task(job_id: str) -> dict:
    """Stage 1 — generate scene outlines.

    Loads the MaicGenerationJob row, marks it in_progress, runs Stage
    1 of the pipeline, persists the outlines + languageDirective on
    the row's `progress` JSON, and emits an `outline_done` WS event.

    Returns a dict pickled into the chain that scene_dispatch_task
    receives — it carries job_id, outlines, languageDirective, and
    language_model_id so the next task doesn't need to re-read the
    row to start.
    """
    job = MaicGenerationJob.objects.get(pk=job_id)
    requirements = job.requirements or {}
    language_model_id = requirements.get("languageModelId", "stub")

    job.status = MaicGenerationJob.STATUS_IN_PROGRESS
    job.progress = {
        "stage": 1,
        "completed": 0,
        "total": 0,
        "message": "Generating scene outlines...",
    }
    job.save(update_fields=["status", "progress", "updated_at"])

    async def _run():
        return await generate_scene_outlines_from_requirements(
            requirements,
            None,
            None,
            language_model_id=language_model_id,
            callbacks=None,
        )

    result = asyncio.run(_run())
    if not result.get("success") or "data" not in result:
        raise RuntimeError(result.get("error", "Stage 1 failed"))

    outlines = result["data"]["outlines"]
    language_directive = result["data"]["languageDirective"]

    job.progress = {
        "stage": 1,
        "completed": len(outlines),
        "total": len(outlines),
        "message": "Outlines complete; generating scenes...",
    }
    job.result = {"outlines": outlines, "languageDirective": language_directive}
    job.save(update_fields=["progress", "result", "updated_at"])

    _emit_progress(job_id, "outline_done", {
        "outlines": outlines,
        "languageDirective": language_directive,
    })

    return {
        "job_id": job_id,
        "outlines": outlines,
        "languageDirective": language_directive,
        "languageModelId": language_model_id,
    }


# ── Scene dispatch (Stage 2; MAIC-428.1 inline / MAIC-428.2 fan-out) ──


@shared_task(
    name="apps.maic.generation.tasks.scene_dispatch_task",
    autoretry_for=(OperationalError, DatabaseError, ConnectionError),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=120,
    retry_jitter=True,
)
def scene_dispatch_task(stage1_payload: dict) -> dict:
    """Stage 2 — generate full scenes.

    MAIC-428.1: runs generate_full_scenes inline (the in-process
    parallel path that already passed Pass-A parity at MAIC-430.A).
    MAIC-428.2 will refactor to a Celery chord that fans out one
    scene_task per outline + uses Redis INCR for atomic progress.
    """
    job_id = stage1_payload["job_id"]
    outlines = stage1_payload["outlines"]
    language_directive = stage1_payload.get("languageDirective", "")
    language_model_id = stage1_payload.get("languageModelId", "stub")

    job = MaicGenerationJob.objects.get(pk=job_id)
    requirements = job.requirements or {}
    agents = requirements.get("agents") or []

    job.progress = {
        "stage": 2,
        "completed": 0,
        "total": len(outlines),
        "message": "Generating scene content...",
    }
    job.save(update_fields=["progress", "updated_at"])

    completed_count = {"n": 0}

    def _on_progress(p):
        # generate_full_scenes emits stage=3 for its own ordering;
        # we re-stamp as stage=2 (Celery's per-job stage view).
        completed_count["n"] = p.get("completed", completed_count["n"])
        if (
            completed_count["n"] > 0
            and completed_count["n"] != p.get("total", 0)
        ):
            _emit_progress(job_id, "scene_done", {
                "completed": completed_count["n"],
                "total": p.get("total", len(outlines)),
            })

    async def _run():
        return await generate_full_scenes(
            outlines,
            language_model_id=language_model_id,
            language_directive=language_directive,
            agents=agents,
            user_profile=requirements.get("userProfile") or "",
            callbacks={"onProgress": _on_progress},
        )

    scenes = asyncio.run(_run())

    job.progress = {
        "stage": 2,
        "completed": len(scenes),
        "total": len(outlines),
        "message": f"Generated {len(scenes)} scenes; finalizing...",
    }
    job.save(update_fields=["progress", "updated_at"])

    return {"job_id": job_id, "scenes": scenes}


# ── Finalize ──────────────────────────────────────────────────────


@shared_task(
    name="apps.maic.generation.tasks.finalize_task",
    autoretry_for=(OperationalError, DatabaseError, ConnectionError),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=60,
)
def finalize_task(stage2_payload: dict) -> dict:
    """Stage 3 — mark the job succeeded.

    Records final result + completed_at. Emits the `finalized` WS
    event so connected clients pop into "ready to play" UI.
    """
    job_id = stage2_payload["job_id"]
    scenes = stage2_payload["scenes"]

    job = MaicGenerationJob.objects.get(pk=job_id)
    existing_result = job.result or {}
    existing_result["scenes"] = scenes

    job.status = MaicGenerationJob.STATUS_SUCCEEDED
    job.result = existing_result
    job.progress = {
        "stage": 3,
        "completed": len(scenes),
        "total": len(scenes),
        "message": "Generation complete!",
    }
    job.completed_at = datetime.now(timezone.utc)
    job.save(
        update_fields=[
            "status", "result", "progress", "completed_at", "updated_at",
        ]
    )

    _emit_progress(job_id, "finalized", {
        "sceneCount": len(scenes),
    })

    return {"job_id": job_id, "sceneCount": len(scenes)}


# ── Failure path ──────────────────────────────────────────────────


@shared_task(
    name="apps.maic.generation.tasks.mark_job_failed",
    # No autoretry — failure handlers must run exactly once.
)
def mark_job_failed(request, exc, traceback, *, job_id: str) -> None:
    """Chain `link_error` callback. Flips the row to status=failed
    and emits a WS error event so clients stop spinning.

    Celery passes (request, exc, traceback) when invoking the error
    handler; we pull job_id from the kwargs we set at chain build time.
    """
    error_message = f"{type(exc).__name__}: {exc}" if exc else "unknown error"
    try:
        job = MaicGenerationJob.objects.get(pk=job_id)
        job.status = MaicGenerationJob.STATUS_FAILED
        job.error = str(error_message)[:2000]
        job.completed_at = datetime.now(timezone.utc)
        job.save(
            update_fields=["status", "error", "completed_at", "updated_at"]
        )
    except MaicGenerationJob.DoesNotExist:
        _logger.error("mark_job_failed: job %s not found", job_id)
        return

    _emit_progress(job_id, "error", {"message": error_message})


# ── Helpers ───────────────────────────────────────────────────────


def _emit_progress(job_id: str, event: str, payload: dict) -> None:
    """Push a progress event onto the channel layer group for this job.

    The WS consumer (MAIC-428.3) subscribes to `maic_generation_{job_id}`
    and forwards group_send messages to connected clients. We
    `async_to_sync` the call so the worker stays sync-only.

    Failures are logged but don't abort the task — WS is a UX
    convenience; the DB row is the canonical source of truth and
    polling clients can recover state from it.
    """
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        layer = get_channel_layer()
        if layer is None:
            return
        async_to_sync(layer.group_send)(
            f"maic_generation_{job_id}",
            {"type": "generation.progress", "event": event, "payload": payload},
        )
    except Exception as exc:  # noqa: BLE001
        _logger.warning(
            "WS progress emit failed for %s/%s: %s", job_id, event, exc
        )


def create_job_session(
    *,
    tenant_id: int,
    user_id: int | None,
    requirements: dict,
) -> MaicGenerationJob:
    """Insert a fresh MaicGenerationJob row and return it.

    The HTTP view calls this before enqueuing the chain — the job_id
    flows through the chain and is also returned to the client so the
    WS subscription matches.
    """
    session = create_generation_session(requirements)
    job_id = session["id"]
    job = MaicGenerationJob.objects.create(
        id=job_id,
        tenant_id=tenant_id,
        created_by_id=user_id,
        requirements=requirements,
        status=MaicGenerationJob.STATUS_PENDING,
        progress={
            "stage": 0,
            "completed": 0,
            "total": 0,
            "message": "Queued",
        },
    )
    return job
