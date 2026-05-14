"""Celery tasks for the v2 generation pipeline (Phase 4 Session 6).

This module wraps the v2 outline/scene/materialization pipeline into a
Celery chain so the HTTP route can return a `{job_id}` immediately
while the work runs in a worker.

MAIC-428.1 (this chunk) ships the outer chain skeleton:

    chain(outline_task.s(job_id), scene_dispatch_task.s(), finalize_task.s())

  - outline_task: marks the job in_progress and runs Stage 1
    (outlines). Stage 2 happens in scene_dispatch_task. The ordering
    matches the WS consumer's expected progress events:
    outline_done → scene_done×N → finalized.

  - scene_dispatch_task: runs scene generation inside the stage task and
    returns the assembled scene payload to finalize_task. A previous
    fan-out implementation waited on a Celery chord from inside a worker;
    real local Ollama validation showed that was not stable enough.

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
import re
import time
from datetime import datetime, timezone
from typing import Any

from celery import chain, shared_task
from django.db import DatabaseError, OperationalError

from apps.maic.generation.pipeline_runner import create_generation_session
from apps.maic.generation.scene_generator import _generate_single_scene
from apps.maic.generation.outline_generator import (
    generate_scene_outlines_from_requirements,
)
from apps.maic.generation.materializer import materialize_generation_artifact
from apps.maic.models import MaicGenerationJob
from apps.maic.orchestration.ai_adapter import use_llm_runtime_config
from apps.maic.llm_config import resolve_tenant_llm_runtime_config
from apps.courses.maic_models import TenantAIConfig


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

    started = time.monotonic()

    async def _run():
        return await generate_scene_outlines_from_requirements(
            requirements,
            _pdf_text_for_requirements(requirements),
            None,
            language_model_id=language_model_id,
            callbacks=None,
            options=_outline_options_for_requirements(requirements),
        )

    with use_llm_runtime_config(llm_config):
        result = asyncio.run(_run())
    if not result.get("success") or "data" not in result:
        raise RuntimeError(result.get("error", "Stage 1 failed"))

    outlines = result["data"]["outlines"]
    language_directive = result["data"]["languageDirective"]
    metrics = {"outline_ms": int((time.monotonic() - started) * 1000)}

    job.progress = {
        "stage": 1,
        "completed": len(outlines),
        "total": len(outlines),
        "message": "Outlines complete; generating scenes...",
    }
    job.result = {
        "outlines": outlines,
        "languageDirective": language_directive,
        "metrics": metrics,
    }
    job.save(update_fields=["progress", "result", "updated_at"])

    _emit_progress(
        job_id,
        "outline_done",
        {
            "outlines": outlines,
            "languageDirective": language_directive,
        },
    )

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
    """Stage 2 — generate one scene per outline.

    Runs per-scene generation inline in this worker process and then calls
    the same collector used by the earlier chord path. Celery workers should
    not block waiting for subtasks dispatched into the same pool; that pattern
    caused worker-loss crashes during real macOS/Ollama validation.

    The downstream finalize_task expects {"job_id", "scenes"} — we
    preserve the per-scene result shape with index attached so
    scenes_finalize_task can re-sort by original outline order.
    """
    job_id = stage1_payload["job_id"]
    started = time.monotonic()
    outlines = stage1_payload["outlines"]
    language_directive = stage1_payload.get("languageDirective", "")
    language_model_id = stage1_payload.get("languageModelId", "stub")

    job = MaicGenerationJob.objects.get(pk=job_id)
    requirements = job.requirements or {}
    agents = requirements.get("agents") or []
    user_profile = _scene_user_profile_for_requirements(requirements)
    teacher_context = _scene_teacher_context_for_requirements(requirements)

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
    # repeated dispatch (autoretry) starts from zero.
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
        "teacher_context": teacher_context,
        "stage_id": stage_id,
        "total": total,
        "all_titles": all_titles,
        "image_generation_enabled": bool(
            requirements.get("enableImageGeneration")
            or requirements.get("enableImages")
        ),
        "video_generation_enabled": bool(
            requirements.get("enableVideoGeneration")
            or requirements.get("enableVideos")
        ),
    }

    # Empty outline = nothing to generate.
    if total == 0:
        return {"job_id": job_id, "scenes": []}

    scene_results = [
        scene_task.run(index=i, outline=outline, **base_args)
        for i, outline in enumerate(outlines)
    ]
    stage2_payload = scenes_finalize_task.run(scene_results, job_id=job_id, total=total)
    stage2_payload["scene_ms"] = int((time.monotonic() - started) * 1000)
    return stage2_payload


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
    teacher_context: str = "",
    image_generation_enabled: bool = False,
    video_generation_enabled: bool = False,
) -> dict:
    """Per-scene worker task. One per outline.

    Builds the per-scene ctx (pageIndex / totalPages / allTitles /
    previousSpeeches), runs _generate_single_scene, increments the
    Redis progress counter, emits a `scene_done` WS event with the
    new completed-count, and returns the assembled scene dict
    (index attached so scenes_finalize_task can sort).

    Failures are surfaced as scene=None in the result so
    scenes_finalize_task can fail the job loudly before materialization.
    Every attempt also persists progress to the DB so polling clients
    and page reloads do not appear stuck if the WebSocket event is missed.
    """
    ctx = {
        "pageIndex": index + 1,
        "totalPages": total,
        "allTitles": all_titles,
        # previousSpeeches is empty under task-level generation — same
        # constraint as generate_full_scenes (Pass-A parity already
        # locked this).
        "previousSpeeches": [],
    }
    media_config = _media_config_for_job_id(
        job_id,
        image_generation_enabled=image_generation_enabled,
        video_generation_enabled=video_generation_enabled,
    )
    image_media_enabled = bool(
        image_generation_enabled
        and media_config is not None
        and getattr(media_config, "image_provider", "disabled") != "disabled"
    )
    video_media_enabled = bool(
        video_generation_enabled
        and media_config is not None
        and getattr(media_config, "video_provider", "disabled") != "disabled"
    )

    async def _run():
        return await _generate_single_scene(
            outline,
            language_model_id=language_model_id,
            language_directive=language_directive,
            agents=agents,
            user_profile=user_profile,
            teacher_context=teacher_context,
            ctx=ctx,
            stage_id=stage_id,
            image_generation_enabled=image_media_enabled,
            video_generation_enabled=video_media_enabled,
            tenant_config=media_config,
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
    _persist_scene_progress(
        job_id,
        completed=completed,
        total=total,
        index=index,
        scene_ok=scene is not None,
    )
    _emit_progress(
        job_id,
        "scene_done",
        {
            "completed": completed,
            "total": total,
            "index": index,
        },
    )

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


def _media_config_for_job_id(
    job_id: str,
    *,
    image_generation_enabled: bool,
    video_generation_enabled: bool,
) -> TenantAIConfig | None:
    if not (image_generation_enabled or video_generation_enabled):
        return None
    job = MaicGenerationJob.objects.only("tenant_id").get(pk=job_id)
    manager = TenantAIConfig.objects
    qs = manager.all_tenants() if hasattr(manager, "all_tenants") else manager
    return qs.filter(tenant_id=job.tenant_id).first()


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
    """Collect scene_task results into ordered scene list.

    Sorts by original outline index and hands a flat scene list to
    finalize_task. Any missing scene is a hard failure: a production
    teacher classroom must not materialize with silently skipped pages.
    """
    scene_results = sorted(scene_results, key=lambda r: r["index"])
    scenes = [r["scene"] for r in scene_results if r.get("scene") is not None]
    failed_indexes = [
        int(r["index"]) + 1 for r in scene_results if r.get("scene") is None
    ]

    job = MaicGenerationJob.objects.get(pk=job_id)
    if failed_indexes:
        job.progress = {
            "stage": 2,
            "completed": len(scenes),
            "total": total,
            "message": (
                f"Generated {len(scenes)} of {total} scenes; failed scenes: "
                f"{', '.join(str(i) for i in failed_indexes)}."
            ),
        }
        job.save(update_fields=["progress", "updated_at"])
        raise RuntimeError(
            f"Generated {len(scenes)} of {total} scenes; "
            f"failed scene indexes: {failed_indexes}"
        )

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
    started = time.monotonic()

    job = MaicGenerationJob.objects.get(pk=job_id)
    existing_result = job.result or {}
    existing_result["scenes"] = scenes
    artifact = materialize_generation_artifact(job, scenes)
    if artifact:
        existing_result.update(artifact)
        existing_result["artifact"] = artifact
    metrics = dict(existing_result.get("metrics") or {})
    if stage2_payload.get("scene_ms") is not None:
        metrics["scene_ms"] = int(stage2_payload["scene_ms"])
    metrics["finalize_ms"] = int((time.monotonic() - started) * 1000)
    if job.created_at:
        metrics["total_ms"] = int(
            (datetime.now(timezone.utc) - job.created_at).total_seconds() * 1000
        )
    existing_result["metrics"] = metrics

    job.status = MaicGenerationJob.STATUS_SUCCEEDED
    job.result = existing_result
    job.progress = {
        "stage": 3,
        "completed": len(scenes),
        "total": len(scenes),
        "message": "Generation complete!",
        "metrics": metrics,
    }
    job.completed_at = datetime.now(timezone.utc)
    job.save(
        update_fields=[
            "status",
            "result",
            "progress",
            "completed_at",
            "updated_at",
        ]
    )

    payload = {"sceneCount": len(scenes)}
    if artifact:
        payload.update(
            {
                "classroomId": artifact.get("classroomId"),
                "contentId": artifact.get("contentId"),
                "url": artifact.get("url"),
            }
        )
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


def _pdf_text_for_requirements(requirements: dict) -> str | None:
    value = requirements.get("pdfText") or requirements.get("pdf_text")
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed or None


def _outline_options_for_requirements(requirements: dict) -> dict[str, Any]:
    teacher_context = _scene_teacher_context_for_requirements(requirements)
    options: dict[str, Any] = {
        "scene_count": _target_scene_count_for_requirements(requirements),
        "teacher_context": teacher_context,
        "research_context": requirements.get("researchContext")
        or requirements.get("research_context")
        or "",
        "image_generation_enabled": bool(
            requirements.get("enableImageGeneration")
            or requirements.get("enableImages")
        ),
        "video_generation_enabled": bool(
            requirements.get("enableVideoGeneration")
            or requirements.get("enableVideos")
        ),
    }
    return options


def _target_scene_count_for_requirements(requirements: dict) -> int | None:
    try:
        value = int(requirements.get("sceneCount") or requirements.get("scene_count"))
    except (TypeError, ValueError):
        value = 0
    if value > 0:
        return value

    requirement = requirements.get("requirement")
    if isinstance(requirement, str):
        match = re.search(
            r"\b(?:create|target|exactly)\s+exactly\s+(\d{1,2})\s+scenes?\b",
            requirement,
            re.IGNORECASE,
        )
        if not match:
            match = re.search(
                r"\b(?:create|target|exactly)\s+(\d{1,2})\s+scenes?\b",
                requirement,
                re.IGNORECASE,
            )
        if match:
            return int(match.group(1))
    return value if value > 0 else None


def _teacher_planning_contract() -> str:
    """Rules that turn Step 2 teacher guidance into generation constraints."""
    return "\n".join(
        [
            "## Teacher Planning Contract",
            "- Treat the teacher class context and class guide as the "
            "controlling planning document for this classroom.",
            "- Reflect grade level, subject, board, scene count, "
            "misconceptions, checks, PBL/activity brief, and discussion "
            "handoffs in scene choices.",
            "- Do not quote private planning notes unless the note is clearly "
            "student-facing.",
            "- When a PBL scene is appropriate, the outline must include "
            "pblConfig with projectTopic, projectDescription, targetSkills, "
            "and issueCount.",
            "- Put concrete handoff cues for agent discussion, teacher live "
            "discussion, spotlight/laser focus, or whiteboard use in "
            "descriptions and keyPoints.",
        ]
    )


def _with_teacher_planning_contract(context: str) -> str:
    text = context.strip()
    if not text or "## Teacher Planning Contract" in text:
        return text
    return f"{_teacher_planning_contract()}\n\n{text}"


def _scene_teacher_context_for_requirements(requirements: dict) -> str:
    value = requirements.get("teacherContext")
    if isinstance(value, str) and value.strip():
        return _with_teacher_planning_contract(value)

    lines: list[str] = []
    class_frame = [
        ("Grade level", requirements.get("gradeLevel") or requirements.get("grade_level")),
        ("Subject", requirements.get("subject")),
        (
            "Syllabus/curriculum board",
            requirements.get("syllabusBoard") or requirements.get("syllabus_board"),
        ),
        ("Target scene count", requirements.get("sceneCount")),
    ]
    clean_frame = [
        f"- {label}: {raw}"
        for label, raw in class_frame
        if raw not in (None, "")
    ]
    if clean_frame:
        lines.append("## Teacher Class Context")
        lines.extend(clean_frame)

    class_guide = requirements.get("classGuide") or requirements.get("class_guide")
    if isinstance(class_guide, str) and class_guide.strip():
        if lines:
            lines.append("")
        lines.append("## Teacher Class Guide")
        lines.append(class_guide.strip())

    return _with_teacher_planning_contract("\n".join(lines))


def _scene_user_profile_for_requirements(requirements: dict) -> str:
    parts: list[str] = []
    user_profile = requirements.get("userProfile")
    if isinstance(user_profile, str) and user_profile.strip():
        parts.append(user_profile.strip())

    teacher_context = _scene_teacher_context_for_requirements(requirements)
    if teacher_context:
        parts.append(
            "## Teacher planning context\n"
            "Use this for pacing, misconceptions, checks, discussion handoffs, "
            "and agent choreography. Do not quote private planning notes "
            "verbatim unless they are explicitly student-facing.\n"
            f"{teacher_context}"
        )
    return "\n\n".join(parts)


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
        _logger.warning("Redis counter reset failed for %s: %s", job_id, exc)


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
        _logger.warning("Redis counter incr failed for %s: %s", job_id, exc)
        return 0


def _persist_scene_progress(
    job_id: str,
    *,
    completed: int,
    total: int,
    index: int,
    scene_ok: bool,
) -> None:
    """Persist scene progress for polling clients and reload recovery."""
    if completed <= 0:
        return

    message = (
        f"Generated scene {completed} of {total}..."
        if scene_ok
        else f"Scene {index + 1} failed; continuing..."
    )
    try:
        job = MaicGenerationJob.objects.get(pk=job_id)
        current_completed = int((job.progress or {}).get("completed") or 0)
        if current_completed > completed:
            return
        job.progress = {
            "stage": 2,
            "completed": completed,
            "total": total,
            "message": message,
        }
        job.save(update_fields=["progress", "updated_at"])
    except Exception as exc:  # noqa: BLE001
        _logger.warning(
            "Scene progress persist failed for %s scene=%s: %s",
            job_id,
            index,
            exc,
        )


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
        _logger.warning("WS progress emit failed for %s/%s: %s", job_id, event, exc)


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
