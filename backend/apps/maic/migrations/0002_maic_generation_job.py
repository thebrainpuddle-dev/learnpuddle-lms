"""Add MaicGenerationJob (Phase 4 Session 6 — MAIC-428.1)."""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("maic", "0001_initial"),
        ("tenants", "0031_auditlog_course_gen_flagged"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="MaicGenerationJob",
            fields=[
                (
                    "id",
                    models.CharField(max_length=32, primary_key=True, serialize=False),
                ),
                ("requirements", models.JSONField(default=dict)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("in_progress", "In progress"),
                            ("succeeded", "Succeeded"),
                            ("failed", "Failed"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=16,
                    ),
                ),
                ("progress", models.JSONField(default=dict)),
                ("result", models.JSONField(default=dict)),
                ("error", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="maic_v2_generation_jobs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="tenants.tenant",
                    ),
                ),
            ],
            options={
                "verbose_name": "MAIC v2 generation job",
                "verbose_name_plural": "MAIC v2 generation jobs",
                "db_table": "maic_generation_job",
                "indexes": [
                    models.Index(
                        fields=["tenant", "created_at"],
                        name="maic_genjob_tenant_2c9d11_idx",
                    ),
                    models.Index(fields=["status"], name="maic_genjob_status_idx"),
                ],
            },
        ),
    ]
