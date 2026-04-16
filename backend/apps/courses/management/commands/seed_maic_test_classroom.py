"""Seed a ready-to-play MAIC classroom for end-to-end test fixtures.

Creates (idempotent — safe to re-run):
  - a ``demo`` tenant with ``feature_maic`` enabled
  - ``teacher@demo.test`` / ``student@demo.test`` (password ``demo1234``)
  - a ``TenantAIConfig`` with Azure TTS + ``maic_enabled=True``
  - a public READY ``MAICClassroom`` with ≥ 5 speech actions + transitions
    and an ``audioManifest`` already in the ``ready`` state.

The speech actions get fake ``audioUrl`` values pointing at ``/media/fixt*.mp3``.
Those files don't exist in the test environment — the player is expected to
fetch, fail gracefully, and fall back to the reading-only mode. This matches
Chunk 6.1 of the plan: "the player won't fetch (will fail gracefully into
reading-fallback)".

Usage:
    python manage.py seed_maic_test_classroom
    python manage.py seed_maic_test_classroom --reset

On success the command prints the classroom id so e2e tests / manual QA can
navigate straight to it.
"""
from __future__ import annotations

import hashlib

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.courses.maic_models import MAICClassroom, TenantAIConfig
from apps.tenants.models import Tenant
from apps.users.models import User


TENANT_SUBDOMAIN = "demo"
TENANT_NAME = "Demo School (e2e)"
TEACHER_EMAIL = "teacher@demo.test"
STUDENT_EMAIL = "student@demo.test"
DEFAULT_PASSWORD = "demo1234"
CLASSROOM_TITLE = "E2E Demo Classroom"
VOICE_ID = "en-IN-PrabhatNeural"


def _speech_action(index: int, agent_id: str, text: str) -> dict:
    """Build a speech action with stable audioId + fake audioUrl."""
    payload = f"{agent_id}|{VOICE_ID}|{text}"
    audio_id = hashlib.sha256(payload.encode()).hexdigest()[:12]
    return {
        "type": "speech",
        "agentId": agent_id,
        "text": text,
        "audioId": audio_id,
        # Fake URL — the file does not exist. Student player is expected to
        # attempt to fetch, fail, and fall back to the subtitle-only reading
        # mode. This keeps e2e deterministic without depending on a real TTS
        # backend.
        "audioUrl": f"/media/fixt{index}.mp3",
        "voiceId": VOICE_ID,
    }


def _build_classroom_content() -> dict:
    """A single-scene classroom: 5 speech actions, 4 transitions, ready manifest."""
    agents = [
        {
            "id": "agent-1",
            "name": "Dr. Aarav Sharma",
            "role": "professor",
            "avatar": "👨‍🏫",
            "color": "#4338CA",
            "voiceId": VOICE_ID,
            "voiceProvider": "azure",
            "personality": "Patient and encouraging, builds intuition before formulas.",
            "expertise": "Leads the classroom and frames big-picture questions.",
            "speakingStyle": "Warm, steady, with Indian-English cadence.",
        },
    ]

    speeches = [
        _speech_action(0, "agent-1", "Welcome to our lesson on photosynthesis."),
        _speech_action(1, "agent-1", "Plants convert sunlight into chemical energy."),
        _speech_action(2, "agent-1", "The process happens in the chloroplasts of plant cells."),
        _speech_action(3, "agent-1", "Water and carbon dioxide are the inputs; glucose and oxygen the outputs."),
        _speech_action(4, "agent-1", "Let's review what we have learned so far."),
    ]

    # Transitions between slides (1..4). `slideIndex` signals the engine to
    # advance the whiteboard when the preceding speech finishes.
    transitions = [{"type": "transition", "slideIndex": i} for i in range(1, 5)]

    actions: list[dict] = []
    for i, speech in enumerate(speeches):
        actions.append(speech)
        if i < len(transitions):
            actions.append(transitions[i])

    return {
        "agents": agents,
        "scenes": [
            {
                "id": "scene-1",
                "title": "Photosynthesis Intro",
                "type": "introduction",
                "actions": actions,
            },
        ],
        "sceneSlideBounds": [
            {"sceneId": "scene-1", "startSlide": 0, "endSlide": 4},
        ],
        "audioManifest": {
            "status": "ready",
            "progress": 100,
            "totalActions": len(speeches),
            "completedActions": len(speeches),
            "failedAudioIds": [],
            "generatedAt": timezone.now().isoformat(),
        },
    }


class Command(BaseCommand):
    help = "Seed a ready-to-play MAIC classroom for e2e tests (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete any existing seed classroom with the same title before recreating.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        reset = options.get("reset", False)

        # ─── 1. Tenant ────────────────────────────────────────────────────
        tenant, tenant_created = Tenant.objects.get_or_create(
            subdomain=TENANT_SUBDOMAIN,
            defaults={
                "name": TENANT_NAME,
                "email": f"admin@{TENANT_SUBDOMAIN}.test",
                "plan": "FREE",
            },
        )
        changed = False
        if not tenant.feature_maic:
            tenant.feature_maic = True
            changed = True
        if not tenant.feature_students:
            tenant.feature_students = True
            changed = True
        if changed:
            tenant.save()

        self.stdout.write(
            self.style.SUCCESS(
                f"{'Created' if tenant_created else 'Using'} tenant '{tenant.subdomain}'"
            )
        )

        # ─── 2. Users ─────────────────────────────────────────────────────
        teacher, teacher_created = User.objects.get_or_create(
            email=TEACHER_EMAIL,
            defaults={
                "tenant": tenant,
                "role": "TEACHER",
                "first_name": "Demo",
                "last_name": "Teacher",
                "is_active": True,
            },
        )
        # Always (re)set the password so tests can rely on `demo1234`.
        teacher.set_password(DEFAULT_PASSWORD)
        # Ensure tenant + role are correct even if a fixture created the user
        # with different values earlier.
        teacher.tenant = tenant
        teacher.role = "TEACHER"
        teacher.is_active = True
        teacher.save()

        student, student_created = User.objects.get_or_create(
            email=STUDENT_EMAIL,
            defaults={
                "tenant": tenant,
                "role": "STUDENT",
                "first_name": "Demo",
                "last_name": "Student",
                "is_active": True,
            },
        )
        student.set_password(DEFAULT_PASSWORD)
        student.tenant = tenant
        student.role = "STUDENT"
        student.is_active = True
        student.save()

        self.stdout.write(
            self.style.SUCCESS(
                f"{'Created' if teacher_created else 'Updated'} teacher '{teacher.email}'"
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"{'Created' if student_created else 'Updated'} student '{student.email}'"
            )
        )

        # ─── 3. TenantAIConfig ────────────────────────────────────────────
        ai_config, ai_created = TenantAIConfig.objects.update_or_create(
            tenant=tenant,
            defaults={
                "llm_provider": "openrouter",
                "llm_model": "openai/gpt-4o-mini",
                "tts_provider": "azure",
                "maic_enabled": True,
            },
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"{'Created' if ai_created else 'Updated'} TenantAIConfig "
                f"(tts={ai_config.tts_provider}, maic_enabled={ai_config.maic_enabled})"
            )
        )

        # ─── 4. Classroom ─────────────────────────────────────────────────
        if reset:
            deleted, _ = (
                MAICClassroom.objects.all_tenants()
                .filter(tenant=tenant, title=CLASSROOM_TITLE)
                .delete()
            )
            if deleted:
                self.stdout.write(
                    self.style.WARNING(
                        f"Removed {deleted} prior seed classroom(s) titled '{CLASSROOM_TITLE}'"
                    )
                )

        existing = (
            MAICClassroom.objects.all_tenants()
            .filter(tenant=tenant, title=CLASSROOM_TITLE)
            .first()
        )

        content = _build_classroom_content()

        if existing:
            existing.creator = teacher
            existing.description = "Pre-seeded ready-to-play classroom for e2e tests."
            existing.topic = "Photosynthesis"
            existing.language = "en"
            existing.status = "READY"
            existing.is_public = True
            existing.scene_count = len(content["scenes"])
            existing.estimated_minutes = 5
            existing.config = {
                "agents": content["agents"],
                "language": "en",
            }
            existing.content = content
            existing.save()
            classroom = existing
            created_msg = "Refreshed"
        else:
            classroom = MAICClassroom.objects.create(
                tenant=tenant,
                creator=teacher,
                title=CLASSROOM_TITLE,
                description="Pre-seeded ready-to-play classroom for e2e tests.",
                topic="Photosynthesis",
                language="en",
                status="READY",
                is_public=True,
                scene_count=len(content["scenes"]),
                estimated_minutes=5,
                config={
                    "agents": content["agents"],
                    "language": "en",
                },
                content=content,
            )
            created_msg = "Created"

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(self.style.SUCCESS(f"  {created_msg} classroom"))
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(f"  id:      {classroom.id}")
        self.stdout.write(f"  title:   {classroom.title}")
        self.stdout.write(f"  tenant:  {tenant.subdomain}")
        self.stdout.write(f"  status:  {classroom.status} (public={classroom.is_public})")
        self.stdout.write(f"  scenes:  {classroom.scene_count}")
        speech_count = sum(
            1 for a in content["scenes"][0]["actions"] if a.get("type") == "speech"
        )
        transition_count = sum(
            1 for a in content["scenes"][0]["actions"] if a.get("type") == "transition"
        )
        self.stdout.write(
            f"  actions: {speech_count} speech + {transition_count} transitions"
        )
        self.stdout.write(
            f"  manifest status: {content['audioManifest']['status']} "
            f"({content['audioManifest']['completedActions']}/{content['audioManifest']['totalActions']})"
        )
        self.stdout.write("")
        self.stdout.write("  Login for e2e:")
        self.stdout.write(f"    teacher: {TEACHER_EMAIL} / {DEFAULT_PASSWORD}")
        self.stdout.write(f"    student: {STUDENT_EMAIL} / {DEFAULT_PASSWORD}")
        self.stdout.write("")
