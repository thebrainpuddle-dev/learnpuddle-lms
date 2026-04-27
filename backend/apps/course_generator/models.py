"""Models for TASK-060 — AI Course Generator.

CourseGenerationJob tracks the full lifecycle of an AI-assisted course
creation request: upload → text extraction → LLM outline → materialise.
"""

from __future__ import annotations

import uuid

from django.db import models
from django.utils import timezone

from utils.tenant_manager import TenantManager


class CourseGenerationJob(models.Model):
    """Tracks one end-to-end AI course generation pipeline run.

    Retention: 90 days (enforced by an external cleanup task or database policy;
    the DELETE endpoint allows on-demand purge of extracted_text_truncated).
    """

    # ── source type choices ─────────────────────────────────────────────────
    SOURCE_PDF = "pdf"
    SOURCE_DOCX = "docx"
    SOURCE_TEXT = "text"
    SOURCE_YOUTUBE = "youtube"
    SOURCE_VIMEO = "vimeo"

    SOURCE_TYPE_CHOICES = [
        (SOURCE_PDF, "PDF"),
        (SOURCE_DOCX, "DOCX"),
        (SOURCE_TEXT, "Plain Text"),
        (SOURCE_YOUTUBE, "YouTube URL"),
        (SOURCE_VIMEO, "Vimeo URL"),
    ]

    # ── status choices ───────────────────────────────────────────────────────
    STATUS_PENDING = "pending"
    STATUS_EXTRACTING = "extracting"
    STATUS_LLM_OUTLINING = "llm_outlining"
    STATUS_MATERIALISING = "materialising"
    STATUS_SUCCEEDED = "succeeded"
    STATUS_FAILED = "failed"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_EXTRACTING, "Extracting text"),
        (STATUS_LLM_OUTLINING, "Generating outline"),
        (STATUS_MATERIALISING, "Materialising course"),
        (STATUS_SUCCEEDED, "Succeeded"),
        (STATUS_FAILED, "Failed"),
    ]

    # ── primary key + tenant ─────────────────────────────────────────────────
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="course_generation_jobs",
    )
    created_by = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="course_generation_jobs",
    )

    # ── source ──────────────────────────────────────────────────────────────
    source_type = models.CharField(max_length=10, choices=SOURCE_TYPE_CHOICES)
    # JSON blob: {"filename": ..., "url": ..., "title_hint": ..., "target_module_count": 5, "truncated": false}
    source_metadata = models.JSONField(default=dict)

    # Extracted and capped at 100k chars. Purged on DELETE.
    extracted_text_truncated = models.TextField(blank=True, default="")
    extracted_char_count = models.PositiveIntegerField(default=0)

    # ── status ──────────────────────────────────────────────────────────────
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True
    )
    error = models.TextField(blank=True, default="")

    # ── LLM output ──────────────────────────────────────────────────────────
    # Raw validated outline JSON as returned by the LLM provider
    outline_json = models.JSONField(null=True, blank=True)

    # Provider tracking
    provider = models.CharField(max_length=50, blank=True, default="")
    model = models.CharField(max_length=100, blank=True, default="")
    tokens_prompt = models.PositiveIntegerField(null=True, blank=True)
    tokens_completion = models.PositiveIntegerField(null=True, blank=True)

    # ── materialised course ──────────────────────────────────────────────────
    draft_course = models.ForeignKey(
        "courses.Course",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="generation_jobs",
    )

    # ── timestamps ───────────────────────────────────────────────────────────
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = "course_generation_jobs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["tenant", "created_at"]),
            models.Index(fields=["created_by", "created_at"]),
        ]

    def __str__(self) -> str:
        return (
            f"CourseGenerationJob({self.id}, tenant={self.tenant_id}, "
            f"status={self.status})"
        )

    def mark_started(self) -> None:
        self.started_at = timezone.now()
        self.status = self.STATUS_EXTRACTING
        self.save(update_fields=["started_at", "status", "updated_at"])

    def set_status(self, status: str, *, error: str = "") -> None:
        self.status = status
        if error:
            self.error = error
        if status in (self.STATUS_SUCCEEDED, self.STATUS_FAILED):
            self.finished_at = timezone.now()
        update_fields = ["status", "updated_at"]
        if error:
            update_fields.append("error")
        if self.finished_at:
            update_fields.append("finished_at")
        self.save(update_fields=update_fields)
