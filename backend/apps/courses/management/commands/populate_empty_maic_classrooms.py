"""Populate empty MAIC classrooms through the real generation services.

This command is intentionally operational, not a fixture loader. It calls the
same tenant LLM generation functions used by the teacher portal, writes the
normal sharded classroom payload, and can optionally run the real TTS task code
inline for pre-generated audio.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.courses.maic_generation_service import (
    AgentValidationError,
    generate_agent_profiles_json,
    generate_outline_sse,
    generate_scene_actions,
    generate_scene_content,
)
from apps.courses.maic_models import MAICClassroom, TenantAIConfig
from apps.courses.maic_voices import pick_fallback_voice
from apps.maic.orchestration.registry import DEFAULT_AGENTS
from apps.tenants.models import Tenant
from apps.users.models import User
from utils.tenant_middleware import clear_current_tenant, set_current_tenant


class Command(BaseCommand):
    help = "Generate real content for empty MAICClassroom rows."

    def add_arguments(self, parser):
        parser.add_argument("--tenant", required=True, help="Tenant subdomain")
        parser.add_argument("--teacher-email", default="", help="Limit to one creator")
        parser.add_argument("--limit", type=int, default=0, help="Max classrooms to populate")
        parser.add_argument("--scene-count", type=int, default=2, help="Outline scenes per classroom")
        parser.add_argument("--agent-count", type=int, default=3, help="Agent count, 2-5")
        parser.add_argument(
            "--agent-source",
            choices=["auto", "llm", "default"],
            default="auto",
            help="Use LLM-generated agents, production default agents, or LLM with default fallback.",
        )
        parser.add_argument("--grade-level", default="Grade 10")
        parser.add_argument("--subject", default="")
        parser.add_argument("--syllabus-board", default="IB DP")
        parser.add_argument("--include-archived", action="store_true")
        parser.add_argument("--overwrite-failed", action="store_true")
        parser.add_argument("--audio-sync", action="store_true", help="Run real TTS task code inline")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        tenant = Tenant.objects.get(subdomain=options["tenant"])
        config = TenantAIConfig.objects.get(tenant=tenant)
        self._validate_config(config)

        teacher = None
        if options["teacher_email"]:
            teacher = User.objects.all_tenants().get(
                tenant=tenant,
                email=options["teacher_email"],
            )

        qs = MAICClassroom.all_objects.filter(tenant=tenant).order_by("created_at")
        if teacher is not None:
            qs = qs.filter(creator=teacher)
        statuses = ["DRAFT", "GENERATING"]
        if options["overwrite_failed"]:
            statuses.append("FAILED")
        if options["include_archived"]:
            statuses.append("ARCHIVED")
        qs = qs.filter(status__in=statuses)

        classrooms = [c for c in qs if self._is_empty(c)]
        if options["limit"] and options["limit"] > 0:
            classrooms = classrooms[: options["limit"]]

        self.stdout.write(
            f"Found {len(classrooms)} empty classroom(s) for tenant={tenant.subdomain}"
        )
        if options["dry_run"]:
            for classroom in classrooms:
                self.stdout.write(f"  would populate {classroom.id} {classroom.title!r}")
            return

        set_current_tenant(tenant)
        try:
            for idx, classroom in enumerate(classrooms, start=1):
                self.stdout.write(
                    f"[{idx}/{len(classrooms)}] Generating {classroom.title!r}"
                )
                try:
                    result = self._generate_classroom(
                        classroom=classroom,
                        config=config,
                        scene_count=max(1, min(8, int(options["scene_count"]))),
                        agent_count=max(2, min(5, int(options["agent_count"]))),
                        agent_source=options["agent_source"],
                        grade_level=options["grade_level"],
                        subject=options["subject"] or classroom.topic or classroom.title,
                        syllabus_board=options["syllabus_board"],
                    )
                    if options["audio_sync"]:
                        self._run_audio_sync(classroom)
                        classroom.refresh_from_db()
                    self.stdout.write(
                        self.style.SUCCESS(
                            "  populated "
                            f"{result['scene_count']} scene(s), "
                            f"{result['slide_count']} slide(s), "
                            f"status={classroom.status}"
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    classroom.status = "FAILED"
                    classroom.error_message = str(exc)[:2000]
                    classroom.save(update_fields=["status", "error_message", "updated_at"])
                    self.stderr.write(
                        self.style.ERROR(f"  failed {classroom.id}: {exc}")
                    )
        finally:
            clear_current_tenant()

    def _validate_config(self, config: TenantAIConfig) -> None:
        if not config.maic_enabled:
            raise CommandError("TenantAIConfig.maic_enabled is false")
        provider = (config.llm_provider or "").lower()
        if provider != "ollama" and not config.get_llm_api_key():
            raise CommandError(
                f"TenantAIConfig for provider {provider!r} has no LLM API key"
            )
        if (config.tts_provider or "disabled") == "disabled":
            self.stdout.write(
                self.style.WARNING(
                    "Tenant TTS provider is disabled; live playback will use timed text only "
                    "unless you enable a real TTS provider."
                )
            )

    def _is_empty(self, classroom: MAICClassroom) -> bool:
        meta = classroom.content_meta or {}
        slides = meta.get("slides") if isinstance(meta, dict) else None
        return not (classroom.content_scenes and isinstance(slides, list) and slides)

    def _generate_classroom(
        self,
        *,
        classroom: MAICClassroom,
        config: TenantAIConfig,
        scene_count: int,
        agent_count: int,
        agent_source: str,
        grade_level: str,
        subject: str,
        syllabus_board: str,
    ) -> dict[str, int]:
        topic = classroom.topic or classroom.title
        language = classroom.language or "en"
        agents = self._resolve_agents(
            topic=topic,
            language=language,
            role_slots=self._role_slots(agent_count),
            config=config,
            agent_count=agent_count,
            agent_source=agent_source,
        )

        outline = self._generate_outline(
            topic=topic,
            language=language,
            agents=agents,
            scene_count=scene_count,
            config=config,
            grade_level=grade_level,
            subject=subject,
            syllabus_board=syllabus_board,
        )
        outline["scenes"] = (outline.get("scenes") or [])[:scene_count]
        scenes, slides, bounds = self._generate_scenes(
            classroom=classroom,
            outline=outline,
            agents=agents,
            config=config,
            grade_level=grade_level,
            subject=subject,
            syllabus_board=syllabus_board,
        )

        now = timezone.now()
        with transaction.atomic():
            locked = MAICClassroom.all_objects.select_for_update().get(pk=classroom.pk)
            locked.status = "READY"
            locked.error_message = ""
            locked.scene_count = len(scenes)
            locked.estimated_minutes = int(outline.get("totalMinutes") or max(len(scenes) * 3, 1))
            locked.config = {
                **dict(locked.config or {}),
                "agents": agents,
                "sceneCount": len(scenes),
                "language": language,
                "grade_level": grade_level,
                "subject": subject,
                "syllabus_board": syllabus_board,
                "source": "populate_empty_maic_classrooms",
            }
            locked.content_scenes = scenes
            locked.content_agents = agents
            locked.content_meta = {
                **dict(locked.content_meta or {}),
                "slides": slides,
                "sceneSlideBounds": bounds,
                "source": "populate_empty_maic_classrooms",
                "generatedAt": now.isoformat(),
                "audioManifest": {
                    "status": "idle",
                    "progress": 0,
                    "totalActions": self._speech_count(scenes),
                    "completedActions": 0,
                    "failedAudioIds": [],
                    "generatedAt": None,
                },
            }
            locked.generation_phase = "complete"
            locked.phase_scene_index = len(scenes)
            locked.scenes_ready = len(scenes)
            locked.started_at = locked.started_at or now
            locked.last_progress_at = now
            locked.images_pending = False
            locked.save(
                update_fields=[
                    "status",
                    "error_message",
                    "scene_count",
                    "estimated_minutes",
                    "config",
                    "content_scenes",
                    "content_agents",
                    "content_meta",
                    "generation_phase",
                    "phase_scene_index",
                    "scenes_ready",
                    "started_at",
                    "last_progress_at",
                    "images_pending",
                    "updated_at",
                ]
            )
        classroom.refresh_from_db()
        return {"scene_count": len(scenes), "slide_count": len(slides)}

    def _generate_outline(self, **kwargs) -> dict[str, Any]:
        outline_payload = None
        for chunk in generate_outline_sse(
            pdf_text=None,
            audience_role="student",
            **kwargs,
        ):
            event, data = self._parse_sse_chunk(chunk)
            if event == "error":
                raise CommandError(data.get("message") or "outline generation failed")
            if event == "outline":
                outline_payload = data
        if not isinstance(outline_payload, dict) or not outline_payload.get("scenes"):
            raise CommandError("outline generation produced no scenes")
        return outline_payload

    def _generate_scenes(
        self,
        *,
        classroom: MAICClassroom,
        outline: dict[str, Any],
        agents: list[dict[str, Any]],
        config: TenantAIConfig,
        grade_level: str,
        subject: str,
        syllabus_board: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, int]]]:
        scenes: list[dict[str, Any]] = []
        flat_slides: list[dict[str, Any]] = []
        bounds: list[dict[str, int]] = []
        outline_scenes = outline.get("scenes") or []

        for scene_idx, outline_scene in enumerate(outline_scenes):
            content_payload = generate_scene_content(
                scene=outline_scene,
                agents=agents,
                language=classroom.language or "en",
                config=config,
                grade_level=grade_level,
                subject=subject,
                syllabus_board=syllabus_board,
                audience_role="student",
                classroom_id=str(classroom.id),
                tenant_id=str(classroom.tenant_id),
                scene_idx=scene_idx,
            )
            if not content_payload:
                raise CommandError(f"scene content failed for {outline_scene.get('title')}")

            scene_type = self._scene_type(outline_scene.get("type"))
            scene_slides = self._slides_from_payload(content_payload)
            if scene_slides:
                start = len(flat_slides)
                flat_slides.extend(scene_slides)
                bounds.append(
                    {
                        "sceneIdx": scene_idx,
                        "startSlide": start,
                        "endSlide": len(flat_slides) - 1,
                    }
                )

            scene_content = self._scene_content(scene_type, content_payload, scene_slides)
            scene = {
                "id": str(outline_scene.get("id") or f"scene-{scene_idx + 1}"),
                "type": scene_type,
                "title": str(outline_scene.get("title") or f"Scene {scene_idx + 1}"),
                "order": scene_idx + 1,
                "content": scene_content,
                "actions": [],
                "multiAgent": {
                    "enabled": True,
                    "agentIds": self._scene_agent_ids(outline_scene, agents),
                },
            }

            action_scene = {
                **scene,
                "content": {
                    **scene_content,
                    "slides": scene_slides,
                },
            }
            actions_payload = generate_scene_actions(
                scene=action_scene,
                agents=agents,
                language=classroom.language or "en",
                config=config,
                grade_level=grade_level,
                subject=subject,
                syllabus_board=syllabus_board,
                audience_role="student",
                classroom_id=str(classroom.id),
            )
            if actions_payload and isinstance(actions_payload.get("actions"), list):
                scene["actions"] = actions_payload["actions"]
            scenes.append(scene)

        if not flat_slides:
            raise CommandError("scene generation produced no slides")
        return scenes, flat_slides, bounds

    def _run_audio_sync(self, classroom: MAICClassroom) -> None:
        from apps.courses.maic_tasks import (
            _build_speech_payload,
            _finalize_classroom_tts,
            _tts_one_scene,
        )

        self._stamp_audio_ids(classroom)
        classroom.refresh_from_db()
        results = []
        for scene_idx, scene in enumerate(classroom.content_scenes or []):
            payload = _build_speech_payload(
                scene_idx,
                scene,
                str(classroom.id),
                classroom.tenant_id,
            )
            if payload["actions"]:
                results.append(_tts_one_scene.run(str(classroom.id), payload))
        _finalize_classroom_tts.run(results=results, classroom_id=str(classroom.id))

    def _stamp_audio_ids(self, classroom: MAICClassroom) -> None:
        with transaction.atomic():
            locked = MAICClassroom.all_objects.select_for_update().get(pk=classroom.pk)
            scenes = list(locked.content_scenes or [])
            agents = list(locked.content_agents or [])
            agents_by_id = {a.get("id"): a for a in agents if isinstance(a, dict)}
            agent_index_by_id = {a.get("id"): i for i, a in enumerate(agents) if isinstance(a, dict)}
            total = 0
            for scene_idx, scene in enumerate(scenes):
                for action_idx, action in enumerate(scene.get("actions", []) or []):
                    if action.get("type") != "speech":
                        continue
                    agent_id = action.get("agentId")
                    agent = agents_by_id.get(agent_id, {})
                    voice_id = agent.get("voiceId") or pick_fallback_voice(
                        name=agent.get("name", ""),
                        role=agent.get("role", ""),
                        agent_index=agent_index_by_id.get(agent_id, 0),
                    )
                    payload = (
                        f"{scene.get('id', scene_idx)}|{action_idx}|"
                        f"{action.get('text', '')}|{voice_id}"
                    )
                    action["voiceId"] = voice_id
                    action["audioId"] = hashlib.sha256(payload.encode()).hexdigest()[:12]
                    total += 1

            meta = dict(locked.content_meta or {})
            meta["audioManifest"] = {
                "status": "generating",
                "progress": 0,
                "totalActions": total,
                "completedActions": 0,
                "failedAudioIds": [],
                "generatedAt": None,
            }
            locked.content_scenes = scenes
            locked.content_meta = meta
            locked.status = "GENERATING"
            locked.save(update_fields=["content_scenes", "content_meta", "status", "updated_at"])

    def _role_slots(self, agent_count: int) -> list[dict[str, int | str]]:
        if agent_count <= 2:
            return [
                {"role": "professor", "count": 1},
                {"role": "student", "count": 1},
            ]
        return [
            {"role": "professor", "count": 1},
            {"role": "teaching_assistant", "count": 1},
            {"role": "student", "count": agent_count - 2},
        ]

    def _resolve_agents(
        self,
        *,
        topic: str,
        language: str,
        role_slots: list[dict[str, int | str]],
        config: TenantAIConfig,
        agent_count: int,
        agent_source: str,
    ) -> list[dict[str, Any]]:
        if agent_source == "default":
            return self._default_agents(agent_count)
        try:
            return generate_agent_profiles_json(
                topic=topic,
                language=language,
                role_slots=role_slots,
                config=config,
            )["agents"]
        except AgentValidationError:
            if agent_source == "llm":
                raise
            self.stdout.write(
                self.style.WARNING(
                    "  LLM agent roster failed validation; using production DEFAULT_AGENTS"
                )
            )
            return self._default_agents(agent_count)

    def _default_agents(self, agent_count: int) -> list[dict[str, Any]]:
        agents = []
        for agent in list(DEFAULT_AGENTS.values())[:agent_count]:
            payload = {
                "id": agent.id,
                "name": agent.name,
                "role": "professor" if agent.role == "teacher" else agent.role,
                "avatar": agent.avatar,
                "color": agent.color,
                "personality": agent.persona,
            }
            if agent.voiceConfig is not None:
                payload["voiceId"] = agent.voiceConfig.voiceId
                payload["voiceProvider"] = agent.voiceConfig.providerId
            agents.append(payload)
        return agents

    def _parse_sse_chunk(self, chunk: str) -> tuple[str | None, dict[str, Any]]:
        event = None
        data = None
        for line in str(chunk).splitlines():
            if line.startswith("event:"):
                event = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                raw = line.split(":", 1)[1].strip()
                if raw == "[DONE]":
                    return event, {}
                data = json.loads(raw)
        return event, data or {}

    def _scene_type(self, raw: Any) -> str:
        value = str(raw or "").lower()
        if value in {"quiz", "interactive", "pbl"}:
            return value
        return "slide"

    def _slides_from_payload(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        slides = payload.get("slides")
        if isinstance(slides, list):
            return [s for s in slides if isinstance(s, dict)]
        slide = payload.get("slide")
        return [slide] if isinstance(slide, dict) else []

    def _scene_content(
        self,
        scene_type: str,
        payload: dict[str, Any],
        slides: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if scene_type == "quiz":
            return {"type": "quiz", "questions": payload.get("questions") or []}
        if scene_type == "interactive":
            return {"type": "interactive", "html": payload.get("html") or ""}
        primary = slides[0] if slides else {}
        return {
            "type": "slide",
            "elements": primary.get("elements") or [],
            "background": primary.get("background"),
            "speakerScript": primary.get("speakerScript"),
        }

    def _scene_agent_ids(
        self,
        outline_scene: dict[str, Any],
        agents: list[dict[str, Any]],
    ) -> list[str]:
        allowed = {str(a.get("id")) for a in agents if a.get("id")}
        ids = [
            str(agent_id)
            for agent_id in (outline_scene.get("agentIds") or [])
            if str(agent_id) in allowed
        ]
        return ids or [str(a.get("id")) for a in agents if a.get("id")]

    def _speech_count(self, scenes: list[dict[str, Any]]) -> int:
        return sum(
            1
            for scene in scenes
            for action in (scene.get("actions") or [])
            if action.get("type") == "speech"
        )
