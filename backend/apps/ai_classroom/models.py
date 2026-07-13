from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from utils.encryption import decrypt_value, encrypt_value
from utils.tenant_manager import TenantManager


class TenantAIRuntimeConfig(models.Model):
    RUNTIME_LEGACY = "legacy"
    RUNTIME_OPENMAIC = "openmaic_fork"
    RUNTIME_CHOICES = [
        (RUNTIME_LEGACY, "Legacy LearnPuddle runtime"),
        (RUNTIME_OPENMAIC, "OpenMAIC fork"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.OneToOneField(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="ai_runtime_config",
    )
    runtime = models.CharField(
        max_length=24,
        choices=RUNTIME_CHOICES,
        default=RUNTIME_LEGACY,
        db_index=True,
    )
    student_generation_enabled = models.BooleanField(default=False)
    provider_config_version = models.PositiveBigIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = "tenant_ai_runtime_configs"


class TenantAIProviderCredential(models.Model):
    MODALITY_CHOICES = [
        ("llm", "Large language model"),
        ("tts", "Text to speech"),
        ("asr", "Speech recognition"),
        ("image", "Image generation"),
        ("video", "Video generation"),
        ("pdf", "Document parsing"),
        ("web_search", "Web search"),
    ]
    VERIFICATION_CHOICES = [
        ("unverified", "Unverified"),
        ("verified", "Verified"),
        ("failed", "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="ai_provider_credentials",
    )
    modality = models.CharField(max_length=20, choices=MODALITY_CHOICES)
    provider_id = models.SlugField(max_length=80)
    display_name = models.CharField(max_length=120, blank=True, default="")
    api_key_encrypted = models.TextField(blank=True, default="")
    base_url = models.URLField(max_length=500, blank=True, default="")
    model_allowlist = models.JSONField(default=list, blank=True)
    provider_config = models.JSONField(default=dict, blank=True)
    is_enabled = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
    verification_status = models.CharField(
        max_length=16,
        choices=VERIFICATION_CHOICES,
        default="unverified",
    )
    verification_message = models.CharField(max_length=500, blank=True, default="")
    last_verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = "tenant_ai_provider_credentials"
        ordering = ["modality", "provider_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "modality", "provider_id"],
                name="uniq_tenant_ai_provider",
            ),
            models.UniqueConstraint(
                fields=["tenant", "modality"],
                condition=Q(is_default=True),
                name="uniq_tenant_ai_default_provider",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "modality", "is_enabled"]),
        ]

    def set_api_key(self, plaintext: str) -> None:
        self.api_key_encrypted = encrypt_value(plaintext)

    def get_api_key(self) -> str:
        return decrypt_value(self.api_key_encrypted)

    @property
    def api_key_preview(self) -> str:
        value = self.get_api_key()
        return f"...{value[-4:]}" if len(value) > 4 else ""


class OpenMAICJob(models.Model):
    STATUS_CHOICES = [
        ("queued", "Queued"),
        ("running", "Running"),
        ("succeeded", "Succeeded"),
        ("failed", "Failed"),
        ("cancelled", "Cancelled"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="openmaic_jobs",
    )
    classroom = models.ForeignKey(
        "courses.MAICClassroom",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="openmaic_jobs",
    )
    upstream_job_id = models.CharField(max_length=80)
    idempotency_key = models.CharField(max_length=120)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="queued")
    progress = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True, default="")
    attempt = models.PositiveSmallIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = "openmaic_jobs"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "upstream_job_id"],
                name="uniq_tenant_openmaic_job",
            ),
            models.UniqueConstraint(
                fields=["tenant", "idempotency_key"],
                name="uniq_tenant_openmaic_idempotency",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "status", "created_at"]),
        ]


class AIClassroomArtifact(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE)
    classroom = models.OneToOneField(
        "courses.MAICClassroom",
        on_delete=models.CASCADE,
        related_name="openmaic_artifact",
    )
    object_key = models.CharField(max_length=700)
    sha256 = models.CharField(max_length=64)
    size_bytes = models.PositiveBigIntegerField(default=0)
    schema_version = models.CharField(max_length=40, default="openmaic-1")
    runtime_version = models.CharField(max_length=80)
    upstream_classroom_id = models.CharField(max_length=120, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = "ai_classroom_artifacts"
        indexes = [models.Index(fields=["tenant", "classroom"])]


class AIClassroomMediaAsset(models.Model):
    KIND_CHOICES = [
        ("image", "Image"),
        ("video", "Video"),
        ("audio", "Audio"),
        ("poster", "Poster"),
        ("attachment", "Attachment"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE)
    classroom = models.ForeignKey(
        "courses.MAICClassroom",
        on_delete=models.CASCADE,
        related_name="openmaic_media_assets",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="openmaic_media_assets",
    )
    kind = models.CharField(max_length=16, choices=KIND_CHOICES)
    sha256 = models.CharField(max_length=64)
    extension = models.CharField(max_length=12)
    content_type = models.CharField(max_length=120)
    object_key = models.CharField(max_length=700)
    size_bytes = models.PositiveBigIntegerField(default=0)
    is_confirmed = models.BooleanField(default=False)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = "ai_classroom_media_assets"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "classroom", "kind", "sha256"],
                name="uniq_ai_classroom_media_content",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "classroom", "kind"]),
            models.Index(fields=["tenant", "is_confirmed", "created_at"]),
        ]


class AIUsageEvent(models.Model):
    MODALITY_CHOICES = TenantAIProviderCredential.MODALITY_CHOICES

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ai_usage_events",
    )
    classroom = models.ForeignKey(
        "courses.MAICClassroom",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ai_usage_events",
    )
    job = models.ForeignKey(
        OpenMAICJob,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="usage_events",
    )
    idempotency_key = models.CharField(max_length=160)
    modality = models.CharField(max_length=20, choices=MODALITY_CHOICES)
    provider_id = models.CharField(max_length=80)
    model_id = models.CharField(max_length=160, blank=True, default="")
    input_tokens = models.PositiveBigIntegerField(default=0)
    output_tokens = models.PositiveBigIntegerField(default=0)
    cache_read_tokens = models.PositiveBigIntegerField(default=0)
    cache_creation_tokens = models.PositiveBigIntegerField(default=0)
    reasoning_tokens = models.PositiveBigIntegerField(default=0)
    quantity = models.DecimalField(max_digits=20, decimal_places=6, default=0)
    unit = models.CharField(max_length=24, default="token")
    source = models.CharField(max_length=80, blank=True, default="")
    occurred_at = models.DateTimeField(default=timezone.now)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = "ai_usage_events"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "idempotency_key"],
                name="uniq_tenant_ai_usage_event",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "occurred_at"]),
            models.Index(fields=["tenant", "modality", "occurred_at"]),
        ]


class AIQuotaReservation(models.Model):
    STATUS_CHOICES = [
        ("reserved", "Reserved"),
        ("consumed", "Consumed"),
        ("released", "Released"),
        ("expired", "Expired"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ai_quota_reservations",
    )
    classroom = models.ForeignKey(
        "courses.MAICClassroom",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ai_quota_reservations",
    )
    job = models.OneToOneField(
        OpenMAICJob,
        on_delete=models.CASCADE,
        related_name="quota_reservation",
    )
    units = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="reserved")
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = "ai_quota_reservations"
        indexes = [models.Index(fields=["tenant", "status", "created_at"])]
