# apps/courses/maic_tasks.py — Background tasks for MAIC AI Classrooms
#
# Pre-generates TTS audio for all speech actions in a classroom so playback
# uses instant audioUrl fast-path instead of real-time server TTS.

import logging

from celery import shared_task
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from utils.tenant_middleware import set_current_tenant, clear_current_tenant

logger = logging.getLogger(__name__)


def _safe_storage_url(path: str) -> str:
    """Return a public URL for a storage path."""
    return default_storage.url(path)


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def pre_generate_classroom_tts(self, classroom_id: str, tenant_id: int):
    """
    Pre-generate TTS audio for every speech action in a classroom.

    Iterates through all scenes → actions, generates MP3 via the tenant's
    configured TTS provider, saves to storage, and patches each action's
    audioUrl field. The updated content is saved back to the classroom.

    Dispatched after classroom content is saved (create or update).
    """
    from apps.courses.maic_models import MAICClassroom, TenantAIConfig
    from apps.courses.maic_generation_service import generate_tts_audio, AGENT_VOICE_MAP
    from apps.tenants.models import Tenant

    try:
        tenant = Tenant.objects.get(pk=tenant_id)
        set_current_tenant(tenant)

        classroom = MAICClassroom.objects.get(pk=classroom_id, tenant=tenant)
        content_data = classroom.content

        if not content_data or "scenes" not in content_data:
            logger.info("Classroom %s has no scenes — skipping TTS generation", classroom_id)
            return

        # Load tenant AI config for TTS provider settings
        try:
            config = TenantAIConfig.objects.get(tenant=tenant)
        except TenantAIConfig.DoesNotExist:
            logger.info("No TenantAIConfig for tenant %s — skipping TTS", tenant_id)
            return

        scenes = content_data["scenes"]
        generated_count = 0

        for scene_idx, scene in enumerate(scenes):
            actions = scene.get("actions", [])
            for action_idx, action in enumerate(actions):
                if action.get("type") != "speech":
                    continue
                # Skip if already has a pre-generated audio URL
                if action.get("audioUrl"):
                    continue

                text = action.get("text", "").strip()
                if not text:
                    continue

                # Resolve voice: agent-specific → role map → default
                agent_id = action.get("agentId", "")
                voice = AGENT_VOICE_MAP.get(agent_id, "en-US-GuyNeural")

                try:
                    audio_bytes = generate_tts_audio(text, config, voice_id=voice)
                except Exception as tts_err:
                    logger.warning(
                        "TTS failed for scene %d action %d: %s",
                        scene_idx, action_idx, tts_err,
                    )
                    continue

                if not audio_bytes:
                    continue

                # Save to storage
                storage_path = (
                    f"tenant/{tenant_id}/maic/tts/{classroom_id}/"
                    f"{scene_idx}_{action_idx}.mp3"
                )
                saved_path = default_storage.save(
                    storage_path, ContentFile(audio_bytes)
                )
                action["audioUrl"] = _safe_storage_url(saved_path)
                generated_count += 1

        if generated_count > 0:
            classroom.content = content_data
            classroom.save(update_fields=["content", "updated_at"])
            logger.info(
                "Pre-generated %d TTS audio files for classroom %s",
                generated_count, classroom_id,
            )
        else:
            logger.info("No new TTS audio needed for classroom %s", classroom_id)

    except Exception as exc:
        logger.error("TTS pre-generation failed for classroom %s: %s", classroom_id, exc)
        raise self.retry(exc=exc)
    finally:
        clear_current_tenant()
