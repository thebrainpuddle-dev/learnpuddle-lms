"""MAIC v2 models.

Phase 0 ships only `MaicSessionV2` — the minimal session pointer that the
WS consumer (MAIC-003) and the HTTP session route (Phase 1, MAIC-301)
use as a stable identifier. Richer state (scenes, agent configs,
generated content) lives in Phase 1+ models that FK to this one.

Tenant isolation: every row is tenant-scoped via TenantManager. There is
no notion of a global classroom; cross-tenant access is denied at the
queryset level.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.tenants.models import Tenant
from apps.courses.models import Course
from utils.tenant_manager import TenantManager


class MaicSessionV2(models.Model):
    """Live AI Classroom session (one per tenant + course + opener).

    Held minimal in Phase 0; Phase 1's MAIC-301 adds `agent_ids`,
    `language`, `level`, `topic` columns and the start-of-session
    snapshot fields.
    """

    id = models.CharField(primary_key=True, max_length=64)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, db_index=True)
    course = models.ForeignKey(
        Course, on_delete=models.SET_NULL, null=True, blank=True, db_index=True
    )
    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="maic_v2_sessions_opened",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    last_event_at = models.DateTimeField(auto_now=True)

    objects = TenantManager()

    class Meta:
        db_table = "maic_session_v2"
        indexes = [
            models.Index(fields=["tenant", "created_at"]),
        ]
        verbose_name = "MAIC v2 session"
        verbose_name_plural = "MAIC v2 sessions"

    def __str__(self) -> str:  # pragma: no cover — repr only
        return f"MaicSessionV2(id={self.id}, tenant={self.tenant_id})"
