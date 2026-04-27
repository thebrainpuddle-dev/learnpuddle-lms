"""
Content versioning models (TASK-048).

A single `ContentRevision` row captures a frozen snapshot of a Course,
Module, or Content after every save. Admins can list revisions and
restore a specific one.

Snapshot is JSON produced by `versioning_snapshot.serialize_*` helpers.
"""

from __future__ import annotations

import uuid

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from utils.tenant_manager import TenantManager


class ContentRevision(models.Model):
    """
    Immutable snapshot of a Course / Module / Content at a point in time.

    A new row is created automatically by `versioning_signals.capture_revision`
    after every post_save. A restore creates a new revision with
    `change_summary="restore-from-vN"` to keep the audit trail intact.

    Snapshot-equality deduplication
    -------------------------------
    Identical consecutive snapshots are deduplicated to avoid noise from
    Django-internal re-saves (e.g. PostgreSQL ``search_vector`` refreshes
    that call ``save()`` without changing any user-visible field).

    **Side effect:** a user save that changes zero snapshotted fields
    produces no revision row. The history panel should not interpret the
    absence of a revision as proof that the user did not click "Save".
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="content_revisions",
    )

    # GenericForeignKey pointing at Course | Module | Content
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        related_name="+",
    )
    object_id = models.UUIDField()
    target = GenericForeignKey("content_type", "object_id")

    # Monotonic per (content_type, object_id). 1-based.
    revision_number = models.PositiveIntegerField()

    # Frozen serialized state. Shape matches `versioning_snapshot.serialize_*`.
    snapshot_json = models.JSONField(default=dict)

    # Who / why
    changed_by = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    # Free-form short label: "create", "update", "restore-from-v3", etc.
    change_summary = models.CharField(max_length=120, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)

    # TenantManager + all-tenants manager (pattern used across the codebase).
    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = "content_revisions"
        unique_together = [("content_type", "object_id", "revision_number")]
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["tenant", "content_type", "object_id", "-created_at"],
                name="content_rev_tenant_obj_idx",
            ),
            models.Index(
                fields=["tenant", "created_at"],
                name="content_rev_tenant_time_idx",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return (
            f"ContentRevision({self.content_type.model}:"
            f"{self.object_id} v{self.revision_number})"
        )
