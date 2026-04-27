"""
Migration 0001 — Initial ChatQuery model for TASK-059 RAG Chatbot.
"""

from __future__ import annotations

import uuid

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("tenants", "0029_auditlog_chatbot_query_actions"),
        ("courses", "0038_course_templates"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ChatQuery",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        primary_key=True,
                        default=uuid.uuid4,
                        editable=False,
                        serialize=False,
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="chat_queries",
                        to="tenants.tenant",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="chat_queries",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "course",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="chat_queries",
                        to="courses.course",
                    ),
                ),
                ("question", models.TextField(max_length=2000)),
                (
                    "retrieved_chunk_ids",
                    models.JSONField(
                        blank=True,
                        default=list,
                        help_text="List of EmbeddingChunk UUIDs used in this query.",
                    ),
                ),
                ("answer", models.TextField(blank=True, default="")),
                (
                    "citations",
                    models.JSONField(
                        blank=True,
                        default=list,
                        help_text="List of {block, source_type, source_id, title, score} dicts.",
                    ),
                ),
                (
                    "grounded",
                    models.BooleanField(
                        default=False,
                        help_text="True iff >=1 chunk was retrieved AND LLM did not emit the fallback sentence.",
                    ),
                ),
                ("provider", models.CharField(blank=True, default="", max_length=50)),
                ("model", models.CharField(blank=True, default="", max_length=100)),
                ("tokens_prompt", models.PositiveIntegerField(blank=True, null=True)),
                ("tokens_completion", models.PositiveIntegerField(blank=True, null=True)),
                ("latency_ms", models.PositiveIntegerField(blank=True, null=True)),
                ("error", models.CharField(blank=True, default="", max_length=500)),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, db_index=True),
                ),
            ],
            options={
                "db_table": "chatbot_chat_query",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="chatquery",
            index=models.Index(
                fields=["tenant", "user", "created_at"],
                name="chatquery_tenant_user_created_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="chatquery",
            index=models.Index(
                fields=["tenant", "created_at"],
                name="chatquery_tenant_created_idx",
            ),
        ),
    ]
