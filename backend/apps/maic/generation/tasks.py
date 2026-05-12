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

from celery import chain, chord, group, shared_task
from django.db import DatabaseError, OperationalError

from apps.maic.generation.pipeline_runner import (
    create_generation_session,
    run_generation_pipeline,
)
from apps.maic.generation.scene_generator import (
    _generate_single_scene,
    generate_full_scenes,
)
from apps.maic.generation.outline_generator import (
    generate_scene_outlines_from_requirements,
)
from apps.maic.generation.materializer import materialize_generation_artifact
from apps.maic.models import MaicGenerationJob
from apps.maic.orchestration.ai_adapter import use_llm_runtime_config
from apps.maic.llm_config import resolve_tenant_llm_runtime_config


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
    llm_config = _runtime_config_for_job(job, language_model_id)

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

    with use_llm_runtime_config(llm_config):
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
    bind=True,
)
def scene_dispatch_task(self, stage1_payload: dict) -> dict:
    """Stage 2 — fan out one scene_task per outline (MAIC-428.2).

    Refactored from MAIC-428.1's inline generate_full_scenes to a
    Celery chord:

        chord(group(scene_task.s(...) for each outline), scenes_finalize.s())

    Per-scene tasks run in parallel on Celery workers. Atomic progress
    counter via Redis INCR (django_redis.get_redis_connection()) so
    concurrent worker increments never race. The chord callback
    (scenes_finalize_task) waits for all scenes, sorts by index, and
    forwards the assembled list to finalize_task.

    Eager-mode fallback: when CELERY_TASK_ALWAYS_EAGER is set (tests
    + dev), the chord is executed in-process. Eager chord dispatch
    semantics differ slightly from the broker path — the result of
    `chord(group(...))(callback)` is still an AsyncResult, but with
    .get() we can block on the callback's return synchronously.

    The downstream finalize_task expects {"job_id", "scenes"} — we
    pre-build the per-scene "task payloads" with index attached so
    scenes_finalize_task can re-sort by original outline order.
    """
    job_id = stage1_payload["job_id"]
    outlines = stage1_payload["outlines"]
    language_directive = stage1_payload.get("languageDirective", "")
    language_model_id = stage1_payload.get("languageModelId", "stub")

    job = MaicGenerationJob.objects.get(pk=job_id)
    requirements = job.requirements or {}
    agents = requirements.get("agents") or []
    user_profile = requirements.get("userProfile") or ""

    total = len(outlines)
    stage_id = f"stage_{job_id}"

    job.progress = {
        "stage": 2,
        "completed": 0,
        "total": total,
        "message": f"Dispatching {total} scenes...",
    }
    job.save(update_fields=["progress", "updated_at"])

    # Reset the Redis progress counter for this job. Idempotent —
    # repeated chord dispatch (autoretry) starts from zero.
    _reset_progress_counter(job_id)

    # Per-scene context — same for every scene, just include index +
    # outline so scene_task can rebuild per-scene ctx.
    all_titles = [o.get("title", "") for o in outlines]
    base_args = {
        "job_id": job_id,
        "language_model_id": language_model_id,
        "language_directive": language_directive,
        "agents": agents,
        "user_profile": user_profile,
        "stage_id": stage_id,
        "total": total,
        "all_titles": all_titles,
    }

    # Empty outline = nothing to fan out. Return early so the chord
    # doesn't dispatch with an empty group (which would just no-op).
    if total == 0:
        return {"job_id": job_id, "scenes": []}

    header = group(
        scene_task.s(index=i, outline=outline, **base_args)
        for i, outline in enumerate(outlines)
    )
    callback = scenes_finalize_task.s(job_id=job_id, total=total)

    chord_result = chord(header)(callback)

    # In eager mode, chord returns an EagerResult — .get() returns
    # the callback's payload synchronously. In broker mode, the
    # outer chain captures this AsyncResult and the next task in the
    # chain (finalize_task) receives the callback's return.
    return chord_result.get(disable_sync_subtasks=False)


@shared_task(
    name="apps.maic.generation.tasks.scene_task",
    autoretry_for=(OperationalError, DatabaseError, ConnectionError),
    max_retries=2,
    retry_backoff=True,
    retry_backoff_max=60,
)
def scene_task(
    *,
    index: int,
    outline: dict,
    job_id: str,
    language_model_id: str,
    language_directive: str,
    agents: list,
    user_profile: str,
    stage_id: str,
    total: int,
    all_titles: list,
) -> dict:
    """Per-scene worker task. One per outline.

    Builds the per-scene ctx (pageIndex / totalPages / allTitles /
    previousSpeeches), runs _generate_single_scene, increments the
    Redis progress counter, emits a `scene_done` WS event with the
    new completed-count, and returns the assembled scene dict
    (index attached so scenes_finalize_task can sort).

    Failures bubble up — the chord callback receives a SCENE-FAILED
    sentinel via Celery's native task-failure path. We surface this
    as scene=None in the result so scenes_finalize_task drops it
    silently (matches the in-process generate_full_scenes contract).
    """
    ctx = {
        "pageIndex": index + 1,
        "totalPages": total,
        "allTitles": all_titles,
        # previousSpeeches is empty under chord parallel — same
        # constraint as generate_full_scenes (Pass-A parity already
        # locked this).
        "previousSpeeches": [],
    }

    async def _run():
        return await _generate_single_scene(
            outline,
            language_model_id=language_model_id,
            language_directive=language_directive,
            agents=agents,
            user_profile=user_profile,
            ctx=ctx,
            stage_id=stage_id,
        )

    try:
        llm_config = _runtime_config_for_job_id(job_id, language_model_id)
        with use_llm_runtime_config(llm_config):
            scene = asyncio.run(_run())
    except Exception as exc:  # noqa: BLE001
        _logger.error(
            "scene_task[%d] for %r failed: %s",
            index,
            outline.get("title", "?"),
            exc,
        )
        scene = None

    completed = _incr_progress_counter(job_id)
    _emit_progress(job_id, "scene_done", {
        "completed": completed,
        "total": total,
        "index": index,
    })

    return {"index": index, "scene": scene}


def _runtime_config_for_job(job: MaicGenerationJob, language_model_id: str) -> dict | None:
    if language_model_id in {"stub", "stub-director"}:
        return None
    return resolve_tenant_llm_runtime_config(
        tenant_id=job.tenant_id,
        requested=language_model_id,
    )


def _runtime_config_for_job_id(job_id: str, language_model_id: str) -> dict | None:
    if language_model_id in {"stub", "stub-director"}:
        return None
    job = MaicGenerationJob.objects.only("tenant_id").get(pk=job_id)
    return _runtime_config_for_job(job, language_model_id)


@shared_task(
    name="apps.maic.generation.tasks.scenes_finalize_task",
    # No autoretry — chord callbacks must run exactly once.
)
def scenes_finalize_task(
    scene_results: list[dict],
    *,
    job_id: str,
    total: int,
) -> dict:
    """Chord callback — collect scene_task results into ordered scene list.

    Sorts by original outline index (chord results may arrive in any
    order), drops any None scenes (failed scene_task runs), and hands
    a flat scene list to finalize_task via the outer chain.
    """
    scene_results = sorted(scene_results, key=lambda r: r["index"])
    scenes = [r["scene"] for r in scene_results if r.get("scene") is not None]

    job = MaicGenerationJob.objects.get(pk=job_id)
    job.progress = {
        "stage": 2,
        "completed": len(scenes),
        "total": total,
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
    artifact = materialize_generation_artifact(job, scenes)
    if artifact:
        existing_result.update(artifact)
        existing_result["artifact"] = artifact

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

    payload = {"sceneCount": len(scenes)}
    if artifact:
        payload.update({
            "classroomId": artifact.get("classroomId"),
            "contentId": artifact.get("contentId"),
            "url": artifact.get("url"),
        })
    _emit_progress(job_id, "finalized", payload)

    return {"job_id": job_id, "sceneCount": len(scenes), **artifact}


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


def _progress_key(job_id: str) -> str:
    return f"maic:generation:progress:{job_id}"


def _redis_connection():
    """Open a Redis connection from settings.REDIS_URL.

    The plan called for django_redis.get_redis_connection() but
    that package isn't in the project. Use the standard `redis`
    Python client directly — already a transitive dep via Celery
    and channels-redis.
    """
    import redis
    from django.conf import settings
    url = getattr(settings, "REDIS_URL", None) or "redis://localhost:6379/1"
    return redis.from_url(url)


def _reset_progress_counter(job_id: str) -> None:
    """Reset the per-job Redis INCR counter to 0.

    Called at the start of scene_dispatch_task so the chord starts
    counting from zero. Failure to reach Redis is logged but
    non-fatal — the WS progress events are a UX nice-to-have; the
    canonical state is the DB row updated by scenes_finalize_task.
    """
    try:
        conn = _redis_connection()
        conn.delete(_progress_key(job_id))
    except Exception as exc:  # noqa: BLE001
        _logger.warning(
            "Redis counter reset failed for %s: %s", job_id, exc
        )


def _incr_progress_counter(job_id: str) -> int:
    """Atomic INCR on the per-job Redis counter; returns the new value.

    Mirrors the plan's "Redis INCR for atomic progress counter" —
    concurrent worker increments never race because INCR is atomic
    at the Redis level.

    Returns 0 on Redis failure (caller treats as "couldn't update";
    the scene_done event still fires with completed=0 which the WS
    consumer ignores).
    """
    try:
        conn = _redis_connection()
        value = conn.incr(_progress_key(job_id))
        # Set TTL on the counter — 1h is plenty for any single
        # generation; the key auto-expires if the chord dies.
        conn.expire(_progress_key(job_id), 3600)
        return int(value)
    except Exception as exc:  # noqa: BLE001
        _logger.warning(
            "Redis counter incr failed for %s: %s", job_id, exc
        )
        return 0


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
