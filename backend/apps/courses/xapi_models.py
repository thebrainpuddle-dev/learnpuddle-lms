"""
xAPI minimal LRS (Learning Record Store) model.

Stores incoming xAPI 1.0.3 statements. Only minimum fields are indexed; the
raw statement is preserved verbatim so higher-fidelity reporting can be built
later.
"""

import uuid

from django.db import models

from utils.tenant_manager import TenantManager


class XAPIStatement(models.Model):
    """A single xAPI statement as persisted by the minimal LRS endpoint."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="xapi_statements",
    )

    statement_id = models.UUIDField(
        default=uuid.uuid4,
        help_text="xAPI statement id (supplied by sender or generated)",
    )

    actor_mbox = models.CharField(max_length=320, blank=True, default="")
    actor_name = models.CharField(max_length=255, blank=True, default="")

    verb_id = models.CharField(max_length=500)
    verb_display = models.CharField(max_length=255, blank=True, default="")

    object_id = models.CharField(max_length=500)
    object_name = models.CharField(max_length=500, blank=True, default="")

    result = models.JSONField(default=dict, blank=True)
    context = models.JSONField(default=dict, blank=True)

    stored = models.DateTimeField(auto_now_add=True)
    raw = models.JSONField(default=dict, blank=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = "xapi_statements"
        indexes = [
            models.Index(fields=["tenant", "stored"]),
            models.Index(fields=["tenant", "actor_mbox"]),
            models.Index(fields=["tenant", "verb_id"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "statement_id"],
                name="xapi_statement_unique_per_tenant",
            ),
        ]

    def __str__(self):
        return f"XAPIStatement({self.statement_id})"
