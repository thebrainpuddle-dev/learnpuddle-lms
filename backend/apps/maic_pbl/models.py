"""MAIC v2 PBL models (Phase 7, MAIC-700).

Single model: `MaicPBLSession`. Holds the entire PBL session state
in JSONFields:

  - project_config : PBLProjectConfig (full upstream shape — projectInfo,
                     agents, issueboard, chat container).
  - chat_messages  : list[PBLChatMessage] — append-only log of every
                     turn. Kept separate from project_config.chat for
                     query efficiency (counting / pagination /
                     lifecycle bound differently than the rest of the
                     config).

Tenant isolation: every row is tenant-scoped via TenantManager. There
is no notion of a global PBL session; cross-tenant access is denied at
the queryset level.

Why JSONField for project_config: PBL state is deeply nested
(projectInfo + agents[] + issueboard{issues[]} + selectedRole) and
mutates as a unit during the design loop. Splitting into normalized
tables would force ORM round-trips on every tool call, which makes
the agentic loop O(tool_calls × queries) instead of O(1). Trade-off
accepted per upstream's same posture (Vercel KV blob storage).
"""
from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models

from apps.tenants.models import Tenant
from utils.tenant_manager import TenantManager


class MaicPBLSession(models.Model):
    """One PBL workspace — created at design time, lives until archived.

    Lifecycle:
      DRAFT      → row created, design loop running OR design failed
                   before producing a usable config
      ACTIVE     → design complete, student can interact with chat
      COMPLETED  → all issues marked is_done by Judge agent
      FAILED     → design loop hit an unrecoverable error (LLM 5xx,
                   tool exception, schema validation failure)
      ARCHIVED   → admin/student soft-delete; kept for audit/replay
                   (Phase 8 cleanup will delete fully if desired)

    The `project_config` JSON is upstream's `PBLProjectConfig`
    verbatim per ADR-001a. Schema lives at
    `apps/maic_pbl/types.py` (Pydantic; landed in MAIC-701).
    """

    STATUS_DRAFT = "draft"
    STATUS_ACTIVE = "active"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_ARCHIVED = "archived"
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
        (STATUS_ARCHIVED, "Archived"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        Tenant, on_delete=models.CASCADE, db_index=True,
        related_name="maic_pbl_sessions",
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="maic_pbl_sessions",
        help_text=(
            "Teacher who designed the project OR student who opened it; "
            "Phase 7 doesn't distinguish — same tenant scope either way."
        ),
    )

    # The full upstream PBLProjectConfig blob. Schema validated at
    # write time via Pydantic (MAIC-701). Empty default is the DRAFT
    # state shape — design loop replaces it on success.
    project_config = models.JSONField(
        default=dict,
        help_text="Full PBLProjectConfig per apps/maic_pbl/types.py",
    )

    # Append-only chat log. Kept separate from project_config.chat so
    # pagination + counting + truncation can target this column without
    # touching the design state.
    chat_messages = models.JSONField(
        default=list,
        help_text="list[PBLChatMessage] — append-only turn log",
    )

    # Topic + language captured at design time so we can re-design
    # without re-asking. agent_count is an integer cap fed to the
    # design loop's prompt; upstream defaults to 4.
    topic = models.CharField(max_length=500, blank=True, default="")
    language = models.CharField(max_length=20, blank=True, default="en")
    agent_count = models.PositiveSmallIntegerField(default=4)

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
        db_index=True,
    )
    error_message = models.TextField(
        blank=True,
        default="",
        help_text=(
            "Populated when status=failed; first 500 chars of the loop's "
            "exception or validation message. Long traces stay in logs."
        ),
    )

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()

    class Meta:
        db_table = "maic_pbl_sessions"
        indexes = [
            models.Index(fields=["tenant", "status", "-created_at"]),
            models.Index(fields=["tenant", "owner", "-created_at"]),
        ]
        verbose_name = "MAIC v2 PBL session"
        verbose_name_plural = "MAIC v2 PBL sessions"

    def __str__(self) -> str:  # pragma: no cover — repr only
        return f"MaicPBLSession(id={self.id}, tenant={self.tenant_id}, status={self.status})"
