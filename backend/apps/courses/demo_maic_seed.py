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


# Real 1x1 transparent PNG as a data URL. Used by the demo classroom's
# image-element scene so the player has an actual <img> with a real,
# resolvable src to render — letting the
# "no image-empty-placeholder" + "image element renders" E2E checks be
# meaningful instead of trivial. Data URL is preferred over a
# /media/-relative path because it has no auth gate and no filesystem
# dependency in the test stack. See PR #41 Codex review (2026-05-16):
# the previous seed had `image_provider: disabled` and zero image
# elements, so the "no Image unavailable" assertion proved nothing.
_DEMO_PNG_DATA_URL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNgYGD4DwABBAEAfbLI3wAAAABJRU5ErkJggg=="
)


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

    # ── Scene 2: a slide that carries a real <img> element ────────────────
    # Added 2026-05-16 (PR #41 Codex review). The previous seed had no image
    # elements at all, so the "no image-empty-placeholder" E2E assertion was
    # passing trivially. With this slide, both negative (no broken-ref
    # placeholder) AND positive (the <img> renders) assertions become real
    # signal. The src is a 1x1 data-URL PNG — no provider call required, no
    # /media/ auth gate, no flake risk; it just resolves and renders.
    image_slide_idx = len(slides)
    image_slide = {
        "id": f"slide-{image_slide_idx + 1}",
        "title": "Photosynthesis In One Frame",
        "background": "#F8FAFC",
        "notes": (
            "A single visual ties together inputs (light, water, CO2) and "
            "outputs (glucose, oxygen)."
        ),
        "speakerScript": (
            "Here is the whole process in one frame: light, water, and carbon "
            "dioxide become glucose and oxygen."
        ),
        "elements": [
            {
                "id": f"slide-{image_slide_idx + 1}-title",
                "type": "text",
                "x": 8,
                "y": 8,
                "width": 84,
                "height": 12,
                "content": "Photosynthesis In One Frame",
                "style": {"fontSize": 30, "fontWeight": 700, "color": "#111827"},
            },
            {
                "id": f"slide-{image_slide_idx + 1}-image",
                "type": "image",
                "x": 22,
                "y": 24,
                "width": 56,
                "height": 56,
                "content": "Photosynthesis diagram",
                "alt": "Photosynthesis diagram showing light, water, CO2, glucose, oxygen flow.",
                "src": _DEMO_PNG_DATA_URL,
            },
        ],
    }
    slides.append(image_slide)
    image_scene_actions: list[dict[str, Any]] = [
        _speech_action(image_slide_idx, "agent-1", image_slide["speakerScript"]),
    ]

    # ── Scene 3: a PBL scene that exercises role / issueboard / chat ──────
    # Added 2026-05-16 (PR #41 Codex review). Previously the seed had no PBL
    # scene, so `maic-pbl-flow.spec.js` skipped all 4 cases. The new scene
    # follows the upstream PBLProjectConfig shape (PBLAgent / PBLIssue /
    # PBLChat fields exactly), with 4 agents (2 selectable + Question + Judge)
    # and 3 issues (one active, two pending). The Question agent's
    # `generated_questions` on the active issue gives the chat panel its
    # welcome message so the panel is non-empty on first render.
    pbl_project_config = {
        "projectInfo": {
            "title": "Build A Terrarium That Stays Alive",
            "description": (
                "Design and test a sealed terrarium that sustains a "
                "small plant for one school week using only the inputs "
                "of photosynthesis."
            ),
        },
        "agents": [
            {
                "name": "Mentor",
                "actor_role": "Question",
                "role_division": "management",
                "system_prompt": (
                    "Guide students through scientific reasoning. Ask clarifying "
                    "questions before approving the next step."
                ),
                "default_mode": "question",
                "delay_time": 600,
                "env": {},
                "is_user_role": False,
                "is_active": True,
                "is_system_agent": True,
            },
            {
                "name": "Reviewer",
                "actor_role": "Judge",
                "role_division": "management",
                "system_prompt": (
                    "Decide whether each milestone meets the success criteria. "
                    "Be specific about what is missing or unclear."
                ),
                "default_mode": "judge",
                "delay_time": 300,
                "env": {},
                "is_user_role": False,
                "is_active": True,
                "is_system_agent": True,
            },
            {
                "name": "Lab Researcher",
                "actor_role": "Investigates plant biology",
                "role_division": "development",
                "system_prompt": (
                    "You research how plants survive sealed systems. You "
                    "propose hypotheses and design experiments."
                ),
                "default_mode": "investigate",
                "delay_time": 200,
                "env": {},
                "is_user_role": True,
                "is_active": True,
                "is_system_agent": False,
            },
            {
                "name": "Field Engineer",
                "actor_role": "Builds the terrarium and measures it",
                "role_division": "development",
                "system_prompt": (
                    "You build the physical terrarium and log measurements "
                    "(humidity, condensation, leaf colour)."
                ),
                "default_mode": "build",
                "delay_time": 200,
                "env": {},
                "is_user_role": True,
                "is_active": True,
                "is_system_agent": False,
            },
        ],
        "issueboard": {
            "agent_ids": ["Mentor", "Reviewer", "Lab Researcher", "Field Engineer"],
            "issues": [
                {
                    "id": "issue-1",
                    "title": "State the hypothesis",
                    "description": (
                        "Write one sentence predicting whether the sealed "
                        "terrarium will keep the plant alive for a week, and why."
                    ),
                    "person_in_charge": "Lab Researcher",
                    "participants": ["Lab Researcher", "Mentor"],
                    "notes": "",
                    "parent_issue": None,
                    "index": 0,
                    "is_done": False,
                    "is_active": True,
                    "generated_questions": (
                        "Welcome! Before we build anything, what do you predict "
                        "will happen inside a sealed terrarium over a week, and "
                        "what evidence are you basing that on?"
                    ),
                    "question_agent_name": "Mentor",
                    "judge_agent_name": "Reviewer",
                },
                {
                    "id": "issue-2",
                    "title": "Design the experiment",
                    "description": (
                        "Sketch the terrarium contents, list the measurements "
                        "you will take, and describe one control variable."
                    ),
                    "person_in_charge": "Field Engineer",
                    "participants": ["Field Engineer", "Lab Researcher"],
                    "notes": "",
                    "parent_issue": None,
                    "index": 1,
                    "is_done": False,
                    "is_active": False,
                    "generated_questions": "",
                    "question_agent_name": "Mentor",
                    "judge_agent_name": "Reviewer",
                },
                {
                    "id": "issue-3",
                    "title": "Report the result",
                    "description": (
                        "After a week, write a short report comparing your "
                        "hypothesis to what actually happened."
                    ),
                    "person_in_charge": "Lab Researcher",
                    "participants": ["Lab Researcher", "Field Engineer"],
                    "notes": "",
                    "parent_issue": None,
                    "index": 2,
                    "is_done": False,
                    "is_active": False,
                    "generated_questions": "",
                    "question_agent_name": "Mentor",
                    "judge_agent_name": "Reviewer",
                },
            ],
            "current_issue_id": "issue-1",
        },
        "chat": {"messages": []},
        "selectedRole": None,
    }

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
        {
            "id": "scene-2-image",
            "type": "slide",
            "title": "Photosynthesis In One Frame",
            "order": 1,
            "content": {
                "type": "slide",
                "elements": image_slide["elements"],
                "slides": slides,
                "speakerScript": image_slide["speakerScript"],
            },
            "actions": image_scene_actions,
            "multiAgent": {
                "enabled": False,
                "agentIds": ["agent-1"],
            },
        },
        {
            "id": "scene-3-pbl",
            "type": "pbl",
            "title": "Build A Terrarium That Stays Alive",
            "order": 2,
            "content": {
                "type": "pbl",
                "projectConfig": pbl_project_config,
            },
            "actions": [],
        },
    ]

    speech_count = sum(
        1 for action in actions + image_scene_actions if action.get("type") == "speech"
    )
    return {
        "agents": agents,
        "slides": slides,
        "scenes": scenes,
        "sceneSlideBounds": [
            {"sceneIdx": 0, "startSlide": 0, "endSlide": len(slides) - 2},
            {"sceneIdx": 1, "startSlide": image_slide_idx, "endSlide": image_slide_idx},
            # PBL scene has no slides; bound entry kept identical to the
            # previous scene so the resolver's "find any bound" fallback in
            # Stage.tsx maps stale currentSlideIndex sensibly during transit.
            {"sceneIdx": 2, "startSlide": image_slide_idx, "endSlide": image_slide_idx},
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
