"""Production-shaped MAIC demo classroom seed helpers.

The demo classroom intentionally does not stamp fake audio URLs. Speech
actions carry stable audio IDs and voice IDs, then playback exercises the
real TTS endpoint when a student starts the class.
"""
from __future__ import annotations

import hashlib
from typing import Any

from django.utils import timezone

from apps.courses.maic_models import MAICClassroom, TenantAIConfig


DEMO_MAIC_CLASSROOM_TITLE = "E2E Demo Classroom"
DEMO_MAIC_TOPIC = "Photosynthesis"
DEMO_MAIC_VOICE_ID = "en-IN-PrabhatNeural"


def ensure_demo_ai_config(tenant) -> TenantAIConfig:
    """Ensure MAIC is enabled with providers that work in local demo stacks."""
    config, _ = TenantAIConfig.objects.update_or_create(
        tenant=tenant,
        defaults={
            "llm_provider": "openrouter",
            "llm_model": "openai/gpt-4o-mini",
            "tts_provider": "edge",
            "tts_voice_id": DEMO_MAIC_VOICE_ID,
            "image_provider": "disabled",
            "maic_enabled": True,
        },
    )
    return config


def ensure_demo_maic_classroom(
    *,
    tenant,
    teacher,
    title: str = DEMO_MAIC_CLASSROOM_TITLE,
) -> MAICClassroom:
    """Create or refresh the public demo classroom used by student e2e."""
    payload = build_demo_maic_content()
    now = timezone.now()
    classroom = (
        MAICClassroom.objects.all_tenants()
        .filter(tenant=tenant, title=title)
        .order_by("-updated_at")
        .first()
    )

    fields: dict[str, Any] = {
        "tenant": tenant,
        "creator": teacher,
        "title": title,
        "description": "Production-shaped demo classroom for student playback.",
        "topic": DEMO_MAIC_TOPIC,
        "language": "en",
        "status": "READY",
        "is_public": True,
        "scene_count": len(payload["scenes"]),
        "estimated_minutes": 5,
        "config": {
            "agents": payload["agents"],
            "language": "en",
            "sceneCount": len(payload["scenes"]),
            "estimated_minutes": 5,
        },
        "content": {},
        "content_scenes": payload["scenes"],
        "content_agents": payload["agents"],
        "content_meta": {
            "slides": payload["slides"],
            "sceneSlideBounds": payload["sceneSlideBounds"],
            "audioManifest": payload["audioManifest"],
        },
        "content_image_tasks": {},
        "images_pending": False,
        "generation_phase": "complete",
        "phase_scene_index": len(payload["scenes"]),
        "scenes_ready": len(payload["scenes"]),
        "started_at": now,
        "last_progress_at": now,
    }

    if classroom is None:
        return MAICClassroom.objects.create(**fields)

    for key, value in fields.items():
        setattr(classroom, key, value)
    classroom.save()
    return classroom


def build_demo_maic_content() -> dict[str, Any]:
    agents = [
        {
            "id": "agent-1",
            "name": "Dr. Aarav Sharma",
            "role": "professor",
            "avatar": "DR",
            "color": "#4338CA",
            "voiceId": DEMO_MAIC_VOICE_ID,
            "voiceProvider": "azure",
            "personality": "Patient and encouraging; builds intuition before formulas.",
            "expertise": "Science education and classroom facilitation.",
            "speakingStyle": "Warm, steady, and concise.",
        },
    ]

    slide_specs = [
        (
            "Photosynthesis",
            "Plants use light energy to build glucose, storing energy that living systems can use.",
            "Welcome to our lesson on photosynthesis. We will follow sunlight as it becomes stored chemical energy.",
        ),
        (
            "The Main Inputs",
            "Leaves take in carbon dioxide from air, water from roots, and light from the sun.",
            "The main inputs are carbon dioxide, water, and light. Each one has a clear role in the process.",
        ),
        (
            "Inside Chloroplasts",
            "Chlorophyll in chloroplasts captures light and starts the energy conversion.",
            "Inside chloroplasts, chlorophyll captures light energy and helps power the reactions.",
        ),
        (
            "Outputs",
            "Glucose stores energy for the plant, while oxygen is released back into the air.",
            "The outputs are glucose and oxygen. Glucose stores energy, and oxygen returns to the atmosphere.",
        ),
        (
            "Why It Matters",
            "Photosynthesis connects plant growth, food webs, and the oxygen we breathe.",
            "Photosynthesis matters because it supports food webs and helps maintain oxygen in the air.",
        ),
    ]

    slides = [
        _slide(index=index, title=title, body=body, speaker_script=speech)
        for index, (title, body, speech) in enumerate(slide_specs)
    ]

    actions: list[dict[str, Any]] = []
    for index, (_title, _body, speech) in enumerate(slide_specs):
        actions.append(_speech_action(index, "agent-1", speech))
        if index < len(slide_specs) - 1:
            actions.append({
                "id": f"transition-{index + 1}",
                "type": "transition",
                "slideIndex": index + 1,
                "duration": 250,
            })

    scenes = [
        {
            "id": "scene-1",
            "type": "slide",
            "title": "Photosynthesis Foundations",
            "order": 0,
            "content": {
                "type": "slide",
                "elements": slides[0]["elements"],
                "slides": slides,
                "speakerScript": slide_specs[0][2],
            },
            "actions": actions,
            "multiAgent": {
                "enabled": False,
                "agentIds": ["agent-1"],
            },
        },
    ]

    speech_count = sum(1 for action in actions if action.get("type") == "speech")
    return {
        "agents": agents,
        "slides": slides,
        "scenes": scenes,
        "sceneSlideBounds": [
            {"sceneIdx": 0, "startSlide": 0, "endSlide": len(slides) - 1},
        ],
        "audioManifest": {
            "status": "partial",
            "progress": 0,
            "totalActions": speech_count,
            "completedActions": 0,
            "failedAudioIds": [],
            "generatedAt": None,
        },
    }


def _slide(index: int, title: str, body: str, speaker_script: str) -> dict[str, Any]:
    accent = ["#4338CA", "#0F766E", "#B45309", "#BE123C", "#2563EB"][index % 5]
    return {
        "id": f"slide-{index + 1}",
        "title": title,
        "background": "#F8FAFC",
        "notes": speaker_script,
        "speakerScript": speaker_script,
        "elements": [
            {
                "id": f"slide-{index + 1}-title",
                "type": "text",
                "x": 8,
                "y": 10,
                "width": 84,
                "height": 14,
                "content": title,
                "style": {
                    "fontSize": 34,
                    "fontWeight": 700,
                    "color": "#111827",
                },
            },
            {
                "id": f"slide-{index + 1}-body",
                "type": "text",
                "x": 10,
                "y": 31,
                "width": 80,
                "height": 34,
                "content": body,
                "style": {
                    "fontSize": 21,
                    "lineHeight": 1.45,
                    "color": "#374151",
                },
            },
            {
                "id": f"slide-{index + 1}-accent",
                "type": "shape",
                "x": 10,
                "y": 72,
                "width": 80,
                "height": 5,
                "content": "",
                "style": {
                    "backgroundColor": accent,
                    "borderRadius": 8,
                },
            },
        ],
    }


def _speech_action(index: int, agent_id: str, text: str) -> dict[str, Any]:
    payload = f"{agent_id}|{DEMO_MAIC_VOICE_ID}|{text}"
    audio_id = hashlib.sha256(payload.encode()).hexdigest()[:12]
    return {
        "id": f"speech-{index + 1}",
        "type": "speech",
        "agentId": agent_id,
        "text": text,
        "audioId": audio_id,
        "voiceId": DEMO_MAIC_VOICE_ID,
        "durationMs": max(2200, min(9000, len(text) * 45)),
    }
