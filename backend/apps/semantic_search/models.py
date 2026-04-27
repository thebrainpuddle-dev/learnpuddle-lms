"""
Models for the semantic_search app (TASK-057).

EmbeddingChunk    — tenant-scoped 1024-dim embedding row keyed by
                    (tenant, source_type, source_id, chunk_index).
EmbeddingJobRun   — audit trail for reindex jobs (content/course/tenant).

The ``embedding`` column is declared as pgvector ``vector(1024)`` via the
initial migration. We intentionally do NOT declare it as a Django field
here so the app still imports cleanly on dev boxes where the pgvector
Postgres extension is not installed (the migration degrades gracefully
in that case, and the RAG features become no-ops).
"""

from __future__ import annotations

import uuid

from django.db import models

from utils.tenant_manager import TenantManager


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EMBEDDING_DIM = 1024

SOURCE_TYPE_COURSE = "course"
SOURCE_TYPE_MODULE = "module"
SOURCE_TYPE_CONTENT = "content"
SOURCE_TYPE_TRANSCRIPT = "transcript"

SOURCE_TYPE_CHOICES = [
    (SOURCE_TYPE_COURSE, "Course"),
    (SOURCE_TYPE_MODULE, "Module"),
    (SOURCE_TYPE_CONTENT, "Content"),
    (SOURCE_TYPE_TRANSCRIPT, "Transcript"),
]


# ---------------------------------------------------------------------------
# EmbeddingChunk
# ---------------------------------------------------------------------------


class EmbeddingChunk(models.Model):
    """
    One vector row per (source_type, source_id, chunk_index) per tenant.

    Short source text (title + description) produces a single chunk with
    chunk_index=0. Transcript bodies are chunked by
    :mod:`apps.semantic_search.chunker`.

    ``text_hash`` is SHA256(text + model); re-embedding is skipped when the
    hash is unchanged (idempotent reindex).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="semantic_embedding_chunks",
    )

    source_type = models.CharField(
        max_length=20,
        choices=SOURCE_TYPE_CHOICES,
        db_index=True,
    )
    # UUID of the source row (Course / Module / Content / transcript FK).
    source_id = models.UUIDField(db_index=True)
    chunk_index = models.PositiveIntegerField(default=0)

    text = models.TextField()
    # SHA256(text + model). 64 hex chars.
    text_hash = models.CharField(max_length=64, db_index=True)

    # NOTE: ``embedding vector(1024)`` column is created by the 0001 migration.
    # We deliberately do NOT declare a VectorField here so model imports
    # never fail when the pgvector extension is unavailable.

    model = models.CharField(max_length=100, blank=True, default="")
    provider = models.CharField(max_length=30, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = "semantic_search_embeddingchunk"
        ordering = ["tenant", "source_type", "source_id", "chunk_index"]
        unique_together = [("tenant", "source_type", "source_id", "chunk_index")]
        indexes = [
            models.Index(
                fields=["tenant", "source_type", "source_id"],
                name="semsearch_tenant_src_idx",
            ),
            models.Index(
                fields=["tenant", "source_type"],
                name="semsearch_tenant_type_idx",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"EmbeddingChunk({self.source_type}:{self.source_id}"
            f"[{self.chunk_index}]) tenant={self.tenant_id}"
        )


# ---------------------------------------------------------------------------
# EmbeddingJobRun
# ---------------------------------------------------------------------------


class EmbeddingJobRun(models.Model):
    """
    Audit trail for reindex jobs — one row per task invocation.

    Retained for 90 days by an ops cleanup command (future ticket); no
    automatic cleanup for MVP.
    """

    KIND_CONTENT = "content"
    KIND_COURSE = "course"
    KIND_TENANT = "tenant"
    KIND_CHOICES = [
        (KIND_CONTENT, "Content"),
        (KIND_COURSE, "Course"),
        (KIND_TENANT, "Tenant"),
    ]

    STATUS_RUNNING = "running"
    STATUS_SUCCEEDED = "succeeded"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_RUNNING, "Running"),
        (STATUS_SUCCEEDED, "Succeeded"),
        (STATUS_FAILED, "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="semantic_job_runs",
        null=True,
        blank=True,
    )

    kind = models.CharField(max_length=10, choices=KIND_CHOICES, db_index=True)
    # Target row UUID (content/course/tenant id); for KIND_TENANT this equals tenant_id.
    target_id = models.CharField(max_length=64, blank=True, default="")

    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_RUNNING,
        db_index=True,
    )
    chunks_indexed = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True, default="")

    class Meta:
        db_table = "semantic_search_jobrun"
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["tenant", "-started_at"], name="semjob_tenant_started_idx"),
            models.Index(fields=["kind", "status"], name="semjob_kind_status_idx"),
        ]

    def __str__(self) -> str:
        return f"EmbeddingJobRun({self.kind}:{self.target_id} {self.status})"
