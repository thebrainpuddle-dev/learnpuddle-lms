"""
ChatQuery model — TASK-059 RAG Chatbot.

Stores every chatbot interaction for audit and compliance. 30-day retention
enforced by the daily Celery Beat `purge_old_chat_queries` task.

PII note: `question` is stored in the DB row so that the teacher can delete
it via `DELETE /chatbot/history/{id}/`. It is NEVER written to application
logs — only structured metadata (query_id, tenant, user, latency_ms, grounded)
is logged.
"""

from __future__ import annotations

import uuid

from django.db import models

from utils.tenant_manager import TenantManager


class ChatQuery(models.Model):
    """
    One row per chatbot Q&A interaction.

    Indexed on ``(tenant, user, created_at)`` for history queries and
    ``(tenant, created_at)`` for the daily purge sweep.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="chat_queries",
    )
    user = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="chat_queries",
    )
    course = models.ForeignKey(
        "courses.Course",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chat_queries",
        help_text="Optional course scope for the query.",
    )

    # The question text — stored for compliance / user-driven purge.
    # NEVER log this field to stdout or Sentry.
    question = models.TextField(max_length=2000)

    # Retrieved chunk IDs captured for audit ("which documents did the bot cite?").
    # Allows exact prompt reproduction even if citations change.
    retrieved_chunk_ids = models.JSONField(
        default=list,
        blank=True,
        help_text="List of EmbeddingChunk UUIDs used in this query.",
    )

    answer = models.TextField(blank=True, default="")

    citations = models.JSONField(
        default=list,
        blank=True,
        help_text="List of {block, source_type, source_id, title, score} dicts.",
    )

    grounded = models.BooleanField(
        default=False,
        help_text="True iff >=1 chunk was retrieved AND LLM did not emit the fallback sentence.",
    )

    # LLM telemetry
    provider = models.CharField(max_length=50, blank=True, default="")
    model = models.CharField(max_length=100, blank=True, default="")
    tokens_prompt = models.PositiveIntegerField(null=True, blank=True)
    tokens_completion = models.PositiveIntegerField(null=True, blank=True)
    latency_ms = models.PositiveIntegerField(null=True, blank=True)

    # Non-empty when the RAG service raised an error.
    error = models.CharField(max_length=500, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    objects = TenantManager()
    all_objects = models.Manager()

    class Meta:
        db_table = "chatbot_chat_query"
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["tenant", "user", "created_at"],
                name="chq_tenant_user_created_idx",
            ),
            models.Index(
                fields=["tenant", "created_at"],
                name="chatquery_tenant_created_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"ChatQuery({self.id}) tenant={self.tenant_id} user={self.user_id}"
