"""
Create StudySummary model for AI-generated study materials.
"""

import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0030_maicclassroom_assigned_sections"),
        ("tenants", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="StudySummary",
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
                    "status",
                    models.CharField(
                        choices=[
                            ("PENDING", "Pending"),
                            ("GENERATING", "Generating"),
                            ("READY", "Ready"),
                            ("FAILED", "Failed"),
                        ],
                        default="PENDING",
                        max_length=12,
                    ),
                ),
                ("summary_data", models.JSONField(blank=True, default=dict)),
                (
                    "source_text_hash",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="SHA-256 hash of the source text used for generation (cache invalidation)",
                        max_length=64,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "content",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="study_summaries",
                        to="courses.content",
                    ),
                ),
                (
                    "student",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="study_summaries",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="study_summaries",
                        to="tenants.tenant",
                    ),
                ),
            ],
            options={
                "db_table": "study_summaries",
                "ordering": ["-created_at"],
                "unique_together": {("student", "content")},
                "indexes": [
                    models.Index(
                        fields=["tenant", "student"],
                        name="study_summ_tenant_student_idx",
                    ),
                    models.Index(
                        fields=["student", "content"],
                        name="study_summ_student_content_idx",
                    ),
                ],
            },
        ),
    ]
