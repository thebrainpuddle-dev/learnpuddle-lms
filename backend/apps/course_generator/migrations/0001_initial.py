"""Migration 0001 — TASK-060 CourseGenerationJob initial schema."""

from __future__ import annotations

import uuid

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("tenants", "0028_auditlog_course_gen_actions"),
        ("courses", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CourseGenerationJob",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="course_generation_jobs",
                        to="tenants.tenant",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="course_generation_jobs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "source_type",
                    models.CharField(
                        choices=[
                            ("pdf", "PDF"),
                            ("docx", "DOCX"),
                            ("text", "Plain Text"),
                            ("youtube", "YouTube URL"),
                            ("vimeo", "Vimeo URL"),
                        ],
                        max_length=10,
                    ),
                ),
                (
                    "source_metadata",
                    models.JSONField(default=dict),
                ),
                (
                    "extracted_text_truncated",
                    models.TextField(blank=True, default=""),
                ),
                (
                    "extracted_char_count",
                    models.PositiveIntegerField(default=0),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("extracting", "Extracting text"),
                            ("llm_outlining", "Generating outline"),
                            ("materialising", "Materialising course"),
                            ("succeeded", "Succeeded"),
                            ("failed", "Failed"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("error", models.TextField(blank=True, default="")),
                ("outline_json", models.JSONField(blank=True, null=True)),
                ("provider", models.CharField(blank=True, default="", max_length=50)),
                ("model", models.CharField(blank=True, default="", max_length=100)),
                ("tokens_prompt", models.PositiveIntegerField(blank=True, null=True)),
                (
                    "tokens_completion",
                    models.PositiveIntegerField(blank=True, null=True),
                ),
                (
                    "draft_course",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="generation_jobs",
                        to="courses.course",
                    ),
                ),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "course_generation_jobs",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(
                        fields=["tenant", "status"],
                        name="cgj_tenant_status_idx",
                    ),
                    models.Index(
                        fields=["tenant", "created_at"],
                        name="cgj_tenant_created_idx",
                    ),
                    models.Index(
                        fields=["created_by", "created_at"],
                        name="cgj_createdby_created_idx",
                    ),
                ],
            },
        ),
    ]
