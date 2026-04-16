# apps/courses/maic_tasks.py — Background tasks for MAIC AI Classrooms
#
# Pre-generates TTS audio for every speech action in a classroom so the
# player uses instant ``audioUrl`` fast-path instead of real-time server
# TTS. Drives the ``audioManifest`` state machine that the teacher detail
# endpoint + frontend progress bar consume.

import logging
import time
from datetime import datetime, timezone

from celery import shared_task

from apps.courses.maic_models import MAICClassroom, TenantAIConfig
from apps.courses.maic_generation_service import generate_tts_audio
from apps.courses.maic_storage import storage_upload
from utils.tenant_middleware import set_current_tenant, clear_current_tenant

logger = logging.getLogger(__name__)


@shared_task(name="apps.courses.maic_tasks.pre_generate_classroom_tts")
def pre_generate_classroom_tts(classroom_id: str) -> None:
    """Pre-generate TTS audio for every speech action. Idempotent on re-run.

    Contract:
    - The publish endpoint is expected to have stamped each speech action
      with ``audioId`` and ``voiceId`` and seeded ``audioManifest`` with
      ``status='generating'`` before enqueuing this task.
    - Actions already carrying an ``audioUrl`` are skipped so re-publishes
      reuse cached audio (idempotence).
    - Each TTS call is retried up to 3 times with exponential back-off
      (2 ** attempt seconds). A failure after retries adds the audioId
      to ``failedAudioIds`` but the loop continues.
    - Progress is persisted every 5 actions (and once at the end) so the
      frontend progress bar has something to poll even if the worker
      dies mid-run.
    - Final status:
        no failures            -> manifest.status='ready',   classroom='READY'
        some failures          -> manifest.status='partial', classroom='READY'
        all failed             -> manifest.status='failed',  classroom='FAILED'
    """
    classroom = MAICClassroom.objects.get(id=classroom_id)

    # Ensure tenant-scoped managers keep working for any nested queries
    set_current_tenant(classroom.tenant)
    try:
        content = classroom.content or {}
        scenes = content.get("scenes", [])
        manifest = content.setdefault(
            "audioManifest",
            {
                "status": "generating",
                "progress": 0,
                "totalActions": 0,
                "completedActions": 0,
                "failedAudioIds": [],
                "generatedAt": None,
            },
        )

        try:
            config = TenantAIConfig.objects.get(tenant=classroom.tenant)
        except TenantAIConfig.DoesNotExist:
            logger.info(
                "No TenantAIConfig for tenant %s — marking classroom failed",
                classroom.tenant_id,
            )
            manifest["status"] = "failed"
            manifest["generatedAt"] = datetime.now(timezone.utc).isoformat()
            classroom.content = content
            classroom.status = "FAILED"
            classroom.save(update_fields=["content", "status", "updated_at"])
            return

        speech_actions = [
            (scene_idx, action_idx, action)
            for scene_idx, scene in enumerate(scenes)
            for action_idx, action in enumerate(scene.get("actions", []))
            if action.get("type") == "speech"
        ]
        total = len(speech_actions)
        manifest["totalActions"] = total

        completed = 0
        failed: list[str] = []

        for scene_idx, action_idx, action in speech_actions:
            audio_id = action.get("audioId")
            voice_id = action.get("voiceId")
            if not audio_id or not voice_id:
                # Publish endpoint should have stamped these — skip loud
                logger.warning(
                    "Speech action missing audioId/voiceId in classroom %s (scene %d, action %d)",
                    classroom_id, scene_idx, action_idx,
                )
                completed += 1
                continue

            storage_key = (
                f"tenant/{classroom.tenant_id}/maic/tts/"
                f"{classroom_id}/{audio_id}.mp3"
            )

            # Idempotent re-publish: skip if we already have a URL
            if action.get("audioUrl"):
                completed += 1
                continue

            audio_bytes = None
            for attempt in range(3):
                try:
                    audio_bytes = generate_tts_audio(
                        action.get("text", ""), config, voice_id=voice_id,
                    )
                    if audio_bytes:
                        break
                except Exception as e:  # noqa: BLE001 — TTS provider errors vary wildly
                    logger.warning(
                        "TTS attempt %d failed for %s: %s",
                        attempt + 1, audio_id, e,
                    )
                    if attempt < 2:
                        time.sleep(2 ** attempt)

            if audio_bytes:
                try:
                    url = storage_upload(storage_key, audio_bytes, "audio/mpeg")
                    content["scenes"][scene_idx]["actions"][action_idx]["audioUrl"] = url
                except Exception as e:  # noqa: BLE001
                    logger.error(
                        "Storage upload failed for %s: %s", audio_id, e,
                    )
                    failed.append(audio_id)
            else:
                failed.append(audio_id)

            completed += 1

            # Checkpoint every 5 actions (and at the boundary) so the
            # frontend progress bar can poll meaningful numbers even if
            # the worker is killed mid-run.
            if completed % 5 == 0 or completed == total:
                manifest["progress"] = (
                    int(completed / total * 100) if total else 100
                )
                manifest["completedActions"] = completed
                manifest["failedAudioIds"] = list(failed)
                classroom.content = content
                classroom.save(update_fields=["content", "updated_at"])

        # Finalize
        if not failed:
            manifest["status"] = "ready"
            classroom.status = "READY"
        elif len(failed) < total:
            manifest["status"] = "partial"
            classroom.status = "READY"
        else:
            manifest["status"] = "failed"
            classroom.status = "FAILED"

        manifest["generatedAt"] = datetime.now(timezone.utc).isoformat()
        manifest["completedActions"] = completed
        manifest["failedAudioIds"] = list(failed)
        classroom.content = content
        classroom.save(update_fields=["content", "status", "updated_at"])
    finally:
        clear_current_tenant()
