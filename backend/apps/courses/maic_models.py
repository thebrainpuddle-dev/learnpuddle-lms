"""
OpenMAIC integration models.

TenantAIConfig — Per-tenant AI provider settings (LLM, TTS, image).
MAICClassroom   — Classroom metadata (content lives in client-side IndexedDB).
"""

import uuid

from django.db import models

from utils.encryption import encrypt_value, decrypt_value
from utils.tenant_manager import TenantManager


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

    # Full classroom content (slides, scenes, sceneSlideBounds).
    # Pushed by the teacher's browser after generation so students can
    # retrieve it via the API without needing the teacher's IndexedDB.
    content = models.JSONField(
        default=dict, blank=True,
        help_text="Full classroom content — slides, scenes, sceneSlideBounds",
    )

    # Scene/slide count (cached from client for listing)
    scene_count = models.PositiveIntegerField(default=0)
    estimated_minutes = models.PositiveIntegerField(default=0)

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
