"""Models for TASK-058 — Auto-Translation Service.

``ContentTranslation``   — stored translation per (source, field, target_language).
``TranslationJobRun``    — audit trail for admin-triggered translation runs.

TASK-064b additions
-------------------
``ContentTranslation`` gains per-field review state:
  * ``review_status``  — pending / approved / rejected (default: pending).
  * ``edited_text``    — admin's manual correction; overrides ``translated_text``
                         at publish time when non-null.
  * ``reviewed_by``    — FK(User, SET_NULL) — who approved/rejected/edited.
  * ``reviewed_at``    — when the last review action was taken.
  * ``published_at``   — set by POST .../publish/ when row is approved.

A composite index on ``(tenant, source_id, target_language, review_status)``
accelerates the review-page query.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models

from utils.tenant_manager import TenantManager


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SOURCE_TYPE_COURSE = "course"
SOURCE_TYPE_MODULE = "module"
SOURCE_TYPE_CONTENT = "content"

SOURCE_TYPE_CHOICES = [
    (SOURCE_TYPE_COURSE, "Course"),
    (SOURCE_TYPE_MODULE, "Module"),
    (SOURCE_TYPE_CONTENT, "Content"),
]

# Translatable fields — canonical names used in the API and storage layer.
FIELD_TITLE = "title"
FIELD_DESCRIPTION = "description"
FIELD_BODY = "body"
FIELD_TRANSCRIPT = "transcript"

FIELD_CHOICES = [
    (FIELD_TITLE, "Title"),
    (FIELD_DESCRIPTION, "Description"),
    (FIELD_BODY, "Body"),
    (FIELD_TRANSCRIPT, "Transcript"),
]


# ---------------------------------------------------------------------------
# ContentTranslation
# ---------------------------------------------------------------------------

# Review status choices (TASK-064b).
REVIEW_STATUS_PENDING = "pending"
REVIEW_STATUS_APPROVED = "approved"
REVIEW_STATUS_REJECTED = "rejected"

REVIEW_STATUS_CHOICES = [
    (REVIEW_STATUS_PENDING, "Pending"),
    (REVIEW_STATUS_APPROVED, "Approved"),
    (REVIEW_STATUS_REJECTED, "Rejected"),
]


class ContentTranslation(models.Model):
    """One translated text blob keyed by (tenant, source, field, language).

    ``source_hash`` captures ``sha256(source_text + src_lang + tgt_lang +
    model)`` — used both for idempotency (skip if row exists with same hash)
    and defence-in-depth stale detection on the teacher read path.

    TASK-064b review fields
    -----------------------
    ``review_status``  — workflow gate; teachers only see rows where
                         ``published_at IS NOT NULL`` (see VISIBILITY NOTE).
    ``edited_text``    — admin's manual correction; overrides
                         ``translated_text`` at publish time.
    ``reviewed_by``    — FK to User (nullable, SET_NULL on user deletion).
    ``reviewed_at``    — timestamp of the last approve / reject / edit action.
    ``published_at``   — set by POST .../publish/; NULL = draft / unpublished.

    VISIBILITY NOTE: before TASK-064b, teachers could see every
    ``ContentTranslation`` row regardless of review state, meaning rejected
    or pending (potentially incorrect) translations were already visible.
    The ``teacher_content_translation`` view now filters to
    ``published_at__isnull=False`` to close this gap.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="content_translations",
    )
    source_type = models.CharField(max_length=20, choices=SOURCE_TYPE_CHOICES)
    source_id = models.UUIDField()
    field = models.CharField(max_length=20, choices=FIELD_CHOICES)
    target_language = models.CharField(max_length=20)

    translated_text = models.TextField(blank=True, default="")
    provider = models.CharField(max_length=40, blank=True, default="")
    model = models.CharField(max_length=200, blank=True, default="")
    source_hash = models.CharField(max_length=64, db_index=True)

    translated_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # --- TASK-064b review fields -------------------------------------------
    review_status = models.CharField(
        max_length=20,
        choices=REVIEW_STATUS_CHOICES,
        default=REVIEW_STATUS_PENDING,
        db_index=True,
    )
    edited_text = models.TextField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="translation_reviews",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    # -----------------------------------------------------------------------

    objects = TenantManager()

    class Meta:
        db_table = "translations_content_translation"
        unique_together = [
            ("tenant", "source_type", "source_id", "field", "target_language"),
        ]
        indexes = [
            models.Index(
                fields=["tenant", "source_type", "source_id"],
                name="trn_tnt_src_idx",
            ),
            models.Index(
                fields=["tenant", "target_language"],
                name="trn_tnt_lang_idx",
            ),
            # TASK-064b: index for the review-page query.
            models.Index(
                fields=["tenant", "source_id", "target_language", "review_status"],
                name="trn_review_query_idx",
            ),
        ]
        ordering = ["-translated_at"]

    def __str__(self) -> str:  # pragma: no cover - representation helper
        return (
            f"ContentTranslation({self.source_type}:{self.source_id}:"
            f"{self.field} → {self.target_language})"
        )


# ---------------------------------------------------------------------------
# TranslationJobRun
# ---------------------------------------------------------------------------


class TranslationJobRun(models.Model):
    """Audit trail for a single admin-triggered translation run.

    ``kind`` distinguishes course-level fan-out from single-content runs.
    ``target_id`` is the UUID of the Course or Content the run applies to.
    """

    KIND_COURSE = "course"
    KIND_CONTENT = "content"
    KIND_CHOICES = [
        (KIND_COURSE, "Course"),
        (KIND_CONTENT, "Content"),
    ]

    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_RUNNING, "Running"),
        (STATUS_SUCCESS, "Success"),
        (STATUS_FAILED, "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="translation_job_runs",
    )
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    target_id = models.UUIDField()
    target_languages = models.JSONField(default=list)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    fields_translated = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True, default="")

    created_by = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="translation_job_runs",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TenantManager()

    class Meta:
        db_table = "translations_job_run"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "created_at"], name="trn_job_tnt_ct_idx"),
            models.Index(fields=["tenant", "status"], name="trn_job_tnt_stat_idx"),
        ]

    def __str__(self) -> str:  # pragma: no cover - representation helper
        return f"TranslationJobRun({self.kind}:{self.target_id}, {self.status})"
