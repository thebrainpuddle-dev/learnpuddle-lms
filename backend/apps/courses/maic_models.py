"""
OpenMAIC integration models.

TenantAIConfig — Per-tenant AI provider settings (LLM, TTS, image).
MAICClassroom   — Classroom metadata (content lives in client-side IndexedDB).
"""

import uuid

from django.core.exceptions import PermissionDenied
from django.db import models

from utils.encryption import encrypt_value, decrypt_value
from utils.tenant_manager import TenantManager
from utils.tenant_middleware import get_current_tenant


class TenantAIConfig(models.Model):
    """
    Per-tenant AI provider configuration.

    API keys are stored Fernet-encrypted at rest. The proxy layer
    decrypts them on each request and injects into the OpenMAIC
    sidecar headers — keys never reach the browser.
    """

    LLM_PROVIDER_CHOICES = [
        ("openai", "OpenAI"),
        ("anthropic", "Anthropic"),
        ("google", "Google AI"),
        ("openrouter", "OpenRouter"),
        ("azure", "Azure OpenAI"),
    ]

    TTS_PROVIDER_CHOICES = [
        ("openai", "OpenAI TTS"),
        ("elevenlabs", "ElevenLabs"),
        ("azure", "Azure TTS"),
        ("edge", "Edge TTS (free)"),
        ("disabled", "Disabled"),
    ]

    IMAGE_PROVIDER_CHOICES = [
        ("openai", "DALL-E"),
        ("stability", "Stability AI"),
        ("disabled", "Disabled"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.OneToOneField(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="ai_config",
    )

    # ─── LLM ──────────────────────────────────────────────────────────────
    llm_provider = models.CharField(
        max_length=20, choices=LLM_PROVIDER_CHOICES, default="openai",
    )
    llm_model = models.CharField(
        max_length=100, default="openai/gpt-4o-mini",
        help_text="Model identifier, e.g. openai/gpt-4o-mini, google/gemini-2.5-flash-preview-05-20",
    )
    llm_api_key_encrypted = models.TextField(
        blank=True, default="",
        help_text="Fernet-encrypted API key",
    )
    llm_base_url = models.URLField(
        max_length=500, blank=True, default="",
        help_text="Custom base URL (for Azure, proxies, etc.)",
    )

    # ─── TTS ──────────────────────────────────────────────────────────────
    tts_provider = models.CharField(
        max_length=20, choices=TTS_PROVIDER_CHOICES, default="edge",
    )
    tts_api_key_encrypted = models.TextField(blank=True, default="")
    tts_voice_id = models.CharField(
        max_length=100, blank=True, default="",
        help_text="Voice identifier for the chosen TTS provider",
    )

    # ─── Image ────────────────────────────────────────────────────────────
    # New tenants default to Pollinations (free, no API key required, via
    # the fallback chain in image_service). Existing tenants keep whatever
    # was previously stamped on their row — we do NOT backfill.
    image_provider = models.CharField(
        max_length=20, choices=IMAGE_PROVIDER_CHOICES, default="pollinations",
    )
    image_api_key_encrypted = models.TextField(blank=True, default="")

    # ─── Feature Gating ───────────────────────────────────────────────────
    maic_enabled = models.BooleanField(
        default=False,
        help_text="Master switch for OpenMAIC AI Classroom feature",
    )
    max_classrooms_per_teacher = models.PositiveIntegerField(
        default=20,
        help_text="Maximum classrooms a single teacher can create",
    )
    max_chatbots_per_teacher = models.PositiveIntegerField(
        default=10,
        help_text="Maximum chatbots a teacher can create",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tenant_ai_configs"
        verbose_name = "Tenant AI Config"
        verbose_name_plural = "Tenant AI Configs"

    def __str__(self):
        return f"AIConfig({self.tenant})"

    # ─── Encrypted field helpers ──────────────────────────────────────────

    def set_llm_api_key(self, plaintext: str) -> None:
        self.llm_api_key_encrypted = encrypt_value(plaintext)

    def get_llm_api_key(self) -> str:
        return decrypt_value(self.llm_api_key_encrypted)

    def set_tts_api_key(self, plaintext: str) -> None:
        self.tts_api_key_encrypted = encrypt_value(plaintext)

    def get_tts_api_key(self) -> str:
        return decrypt_value(self.tts_api_key_encrypted)

    def set_image_api_key(self, plaintext: str) -> None:
        self.image_api_key_encrypted = encrypt_value(plaintext)

    def get_image_api_key(self) -> str:
        return decrypt_value(self.image_api_key_encrypted)


class MAICClassroom(models.Model):
    """
    Metadata for an OpenMAIC AI Classroom.

    Slide content, chat history, and audio caches live in the client's
    IndexedDB (Dexie) — matching OpenMAIC's stateless server pattern.
    Only metadata and generation state live in PostgreSQL.
    """

    STATUS_CHOICES = [
        ("DRAFT", "Draft"),
        ("GENERATING", "Generating"),
        ("READY", "Ready"),
        ("FAILED", "Failed"),
        ("ARCHIVED", "Archived"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="maic_classrooms",
    )
    creator = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="maic_classrooms",
    )

    title = models.CharField(max_length=300)
    description = models.TextField(blank=True, default="")
    topic = models.CharField(
        max_length=500, blank=True, default="",
        help_text="Original topic or PDF filename used for generation",
    )
    language = models.CharField(max_length=10, default="en")

    status = models.CharField(
        max_length=12, choices=STATUS_CHOICES, default="DRAFT",
    )
    error_message = models.TextField(blank=True, default="")

    # Optional link to a Course for discoverability
    course = models.ForeignKey(
        "courses.Course",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="maic_classrooms",
    )

    # Generation config snapshot (agent count, scene count, params)
    config = models.JSONField(default=dict, blank=True)

    # Visibility & assignment
    is_public = models.BooleanField(
        default=False,
        help_text="When True, students can browse and access this classroom",
    )
    assigned_sections = models.ManyToManyField(
        "academics.Section",
        blank=True,
        related_name="maic_classrooms",
        help_text="Sections that can access this classroom. If empty + is_public, all students see it.",
    )

    # ─── Legacy monolithic content field ─────────────────────────────────────
    # PERF-P0-4 (cutover 2026-04-26): This single JSONField was the original
    # storage for ALL classroom content. PostgreSQL TOASTs blobs >8 KB, so any
    # partial save (one slide's image src, one audioId) rewrote the entire
    # ~56 MB TOAST blob.
    #
    # The dual-write that kept this field in lock-step with the shards has
    # been retired — every read path now goes through ``composed_content``
    # (which still falls back to this field for any pre-backfill row) and
    # every write path uses ``update_content_section`` or the shard fields
    # directly. The column is intentionally left in place for one full
    # release as a safety net; a follow-up migration will drop it once
    # shard-only reads are confirmed in production.
    #
    # Reads:  use ``composed_content`` (shards + fallback).
    # Writes: forbidden — every shard has its own targeted save path.
    content = models.JSONField(
        default=dict, blank=True,
        help_text=(
            "Legacy monolithic content field (PERF-P0-4). "
            "Read-only post-cutover — composed_content / content_scenes / "
            "content_agents / content_meta are the source of truth."
        ),
    )

    # ─── Sharded content fields (PERF-P0-4) ──────────────────────────────────
    # Split from the monolithic `content` JSONField to enable partial saves
    # that only rewrite the changed TOAST segment instead of the whole blob.
    #
    # content_scenes  — scenes array (largest: slides, actions, image srcs,
    #                   TTS audioUrls). Updated per-scene during generation and
    #                   by fill_classroom_images. ~95% of write volume lands here.
    #
    # content_agents  — agent profile list (name, voiceId, avatar, color).
    #                   Written once at generation time; stable thereafter.
    #
    # content_meta    — small metadata: audioManifest status machine,
    #                   any top-level keys that are neither scenes nor agents.
    #                   Written on publish and at TTS progress checkpoints.
    content_scenes = models.JSONField(
        default=list, blank=True,
        help_text="PERF-P0-4 shard: scenes array (slides, actions, image srcs, audio URLs)",
    )
    content_agents = models.JSONField(
        default=list, blank=True,
        help_text="PERF-P0-4 shard: agent profile list",
    )
    content_meta = models.JSONField(
        default=dict, blank=True,
        help_text="PERF-P0-4 shard: audioManifest + miscellaneous top-level keys",
    )

    # ─── F2 (P0): per-element image task state ───────────────────────────────
    # Keyed by stable per-element string
    # ``"<scene_idx>:<slide_idx>:<element_idx>:<element_id_or_synth>"``.
    # Each entry shape:
    #     {"status": "pending"|"generating"|"done"|"failed",
    #      "src":   "<url>",          # present on done
    #      "error_code": "...",       # present on failed
    #      "updated_at": "<iso8601>"}
    # Coexists with the global ``images_pending`` boolean (CG-P0-3) — F3
    # will eventually move the gating signal here, but until then the
    # boolean is still the milestone trigger that the player reads.
    content_image_tasks = models.JSONField(
        default=dict, blank=True,
        help_text=(
            "F2 (P0): per-element image generation task state, keyed by "
            "``<scene_idx>:<slide_idx>:<element_idx>:<element_id>``. "
            "Status states: pending|generating|done|failed."
        ),
    )

    # Scene/slide count (cached from client for listing)
    scene_count = models.PositiveIntegerField(default=0)
    estimated_minutes = models.PositiveIntegerField(default=0)

    # CG-P0-3: deferred image-fill state.
    # Flipped to True by the per-scene content endpoint when image fetching is
    # deferred to the fill_classroom_images Celery task. Flipped back to False
    # once that task completes. Default False so existing rows need no backfill.
    images_pending = models.BooleanField(
        default=False,
        help_text=(
            "True while the fill_classroom_images Celery task is in-flight. "
            "Frontend polls this to know whether slide images are still loading."
        ),
    )

    # Live generation progress. Updated as the wizard posts progress pings
    # or saves partial content. MAICPlayerPage reads these to render an
    # honest progress bar + detect stalled generations.
    GENERATION_PHASES = [
        ("", "None"),
        ("queued", "Queued"),
        ("outline", "Generating outline"),
        ("content", "Generating scene content"),
        ("actions", "Generating scene actions"),
        ("saving", "Saving"),
        ("complete", "Complete"),
    ]
    generation_phase = models.CharField(
        max_length=16, choices=GENERATION_PHASES, default="", blank=True,
    )
    # 1-based index of the scene currently being worked on (0 = not started)
    phase_scene_index = models.PositiveIntegerField(default=0)
    # Count of scenes with fully materialized content + actions
    scenes_ready = models.PositiveIntegerField(default=0)
    # First time a generation step reported progress (distinct from
    # created_at, which is row-creation). Elapsed UI derives from this.
    started_at = models.DateTimeField(null=True, blank=True)
    # Most recent heartbeat. Frontend flags as stalled if older than ~3 min.
    last_progress_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = "maic_classrooms"
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["tenant", "creator", "-updated_at"]),
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["tenant", "is_public", "status"]),
            models.Index(fields=["tenant", "course"]),
        ]

    def __str__(self):
        return f"MAICClassroom({self.id}) — {self.title}"

    # ─── PERF-P0-4 shard helpers ──────────────────────────────────────────────

    @property
    def composed_content(self) -> dict:
        """Compose the full content dict from shards (preferred) or legacy field.

        Priority order:
        1. If any shard is non-empty → build from shards.
        2. Otherwise fall back to the legacy ``content`` field.

        This property is used wherever a full content payload is needed for
        the API response (teacher/student detail endpoints). Callers that only
        need one section (e.g. scenes) should read the shard directly.

        Partial-shard contract (SPRINT-2-BATCH-6-F6):
        Returns the composed view of sharded content. When ANY shard is
        non-empty, ONLY shard data is returned — partial shards (e.g.
        ``content_scenes`` populated but ``content_agents`` empty) yield a
        dict with the present keys ONLY. Consumers MUST treat every key as
        optional (use ``.get('agents', [])`` not ``composed_content['agents']``).
        Falls back to legacy ``content`` JSON only when ALL shards are empty
        (pre-backfill rows).
        """
        # Prefer shards when at least one is populated.
        if self.content_scenes or self.content_agents or self.content_meta:
            composed: dict = {}
            if self.content_agents:
                composed["agents"] = self.content_agents
            if self.content_scenes:
                composed["scenes"] = self.content_scenes
            # Merge all other top-level keys from meta (e.g. audioManifest).
            if self.content_meta:
                composed.update(self.content_meta)
            return composed
        # Fall back to legacy monolithic field.
        return self.content or {}

    def update_content_section(
        self,
        section: str,
        data,
        *,
        save: bool = True,
    ) -> list[str]:
        """Write a single content section to its shard and optionally save.

        Args:
            section:  One of ``"scenes"``, ``"agents"``, ``"meta"``, or
                      ``"image_tasks"``.
                      For ``"meta"`` and ``"image_tasks"`` the *data* dict is
                      merged (not replaced) so individual keys can be updated
                      without clobbering siblings (F2 — per-element image
                      task transitions).
            data:     The value to store (list for scenes/agents, dict for meta).
            save:     When True (default) immediately saves with update_fields
                      targeting only the changed shard + ``updated_at``.

        Returns:
            List of field names that were changed (useful when the caller
            wants to accumulate changes and do a single save).

        Raises:
            ValueError: If ``section`` is not one of the three supported values.
            django.core.exceptions.PermissionDenied: If the thread-local
                current tenant is set and does not match ``self.tenant_id``
                (cross-tenant write guard, SPRINT-2-BATCH-6-F7).

        Meta merge semantics (SPRINT-2-BATCH-6-F6):
            The ``"meta"`` section uses a single-level ``dict.update()`` merge,
            NOT a deep/recursive merge.  This means nested dicts (e.g.
            ``audioManifest``) must be passed in full if any of their internal
            keys need to change.  Passing ``{"audioManifest": {"status": "ready"}}``
            will REPLACE the entire ``audioManifest`` value, not patch a single key.

        Tenant guard (SPRINT-2-BATCH-6-F7):
            If a tenant is set in the thread-local context (via
            ``set_current_tenant``), this method enforces that the classroom
            belongs to that tenant before writing.  If no tenant is set (the
            normal state inside a Celery task that hasn't called
            ``set_current_tenant``), the check is skipped — that is intentional.

        Note on ``updated_at``:
            ``updated_at`` uses ``auto_now=True`` but must still be listed
            explicitly in ``update_fields`` when ``save()`` is called with that
            parameter — Django's ``auto_now`` only fires if the field appears in
            ``update_fields``.
        """
        # SPRINT-2-BATCH-6-F7: defensive tenant guard.
        # If a tenant is active in the thread-local context (i.e. we are
        # running inside a request or a task that explicitly called
        # set_current_tenant), verify the classroom belongs to that tenant.
        # If no tenant is set (the normal state inside a Celery task that
        # hasn't called set_current_tenant), skip the check — that is an
        # intentional, trusted state for background jobs.
        _current_tenant = get_current_tenant()
        if _current_tenant is not None and self.tenant_id != _current_tenant.id:
            raise PermissionDenied(
                f"update_content_section called on classroom belonging to tenant "
                f"{self.tenant_id!r} but current tenant is {_current_tenant.id!r}."
            )

        if section == "scenes":
            self.content_scenes = data
            changed = ["content_scenes"]
        elif section == "agents":
            self.content_agents = data
            changed = ["content_agents"]
        elif section == "meta":
            if not isinstance(data, dict):
                raise ValueError("update_content_section('meta', ...) requires a dict")
            meta = dict(self.content_meta or {})
            meta.update(data)
            self.content_meta = meta
            changed = ["content_meta"]
        elif section == "image_tasks":
            # F2 (P0): merge per-element image-task transitions. Same
            # single-level dict.update() semantics as ``meta`` — each
            # element_key entry is replaced wholesale, but unrelated
            # keys are preserved.
            if not isinstance(data, dict):
                raise ValueError(
                    "update_content_section('image_tasks', ...) requires a dict"
                )
            tasks = dict(self.content_image_tasks or {})
            tasks.update(data)
            self.content_image_tasks = tasks
            changed = ["content_image_tasks"]
        else:
            raise ValueError(
                f"Unknown content section {section!r}. "
                "Must be one of: 'scenes', 'agents', 'meta', 'image_tasks'."
            )

        if save:
            self.save(update_fields=changed + ["updated_at"])
        return changed
