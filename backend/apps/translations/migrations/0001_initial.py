"""Initial migration for TASK-058 — Auto-Translation Service."""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("tenants", "0024_tenant_mode"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ContentTranslation",
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
                    "source_type",
                    models.CharField(
                        max_length=20,
                        choices=[
                            ("course", "Course"),
                            ("module", "Module"),
                            ("content", "Content"),
                        ],
                    ),
                ),
                ("source_id", models.UUIDField()),
                (
                    "field",
                    models.CharField(
                        max_length=20,
                        choices=[
                            ("title", "Title"),
                            ("description", "Description"),
                            ("body", "Body"),
                            ("transcript", "Transcript"),
                        ],
                    ),
                ),
                ("target_language", models.CharField(max_length=20)),
                ("translated_text", models.TextField(blank=True, default="")),
                ("provider", models.CharField(blank=True, default="", max_length=40)),
                ("model", models.CharField(blank=True, default="", max_length=200)),
                ("source_hash", models.CharField(db_index=True, max_length=64)),
                ("translated_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="content_translations",
                        to="tenants.tenant",
                    ),
                ),
            ],
            options={
                "db_table": "translations_content_translation",
                "ordering": ["-translated_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="contenttranslation",
            constraint=models.UniqueConstraint(
                fields=(
                    "tenant",
                    "source_type",
                    "source_id",
                    "field",
                    "target_language",
                ),
                name="trn_unique_per_src_field_lang",
            ),
        ),
        migrations.AddIndex(
            model_name="contenttranslation",
            index=models.Index(
                fields=["tenant", "source_type", "source_id"],
                name="trn_tnt_src_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="contenttranslation",
            index=models.Index(
                fields=["tenant", "target_language"],
                name="trn_tnt_lang_idx",
            ),
        ),
        migrations.CreateModel(
            name="TranslationJobRun",
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
                    "kind",
                    models.CharField(
                        max_length=20,
                        choices=[("course", "Course"), ("content", "Content")],
                    ),
                ),
                ("target_id", models.UUIDField()),
                ("target_languages", models.JSONField(default=list)),
                (
                    "status",
                    models.CharField(
                        max_length=20,
                        choices=[
                            ("pending", "Pending"),
                            ("running", "Running"),
                            ("success", "Success"),
                            ("failed", "Failed"),
                        ],
                        db_index=True,
                        default="pending",
                    ),
                ),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("fields_translated", models.PositiveIntegerField(default=0)),
                ("error", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=models.deletion.SET_NULL,
                        related_name="translation_job_runs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="translation_job_runs",
                        to="tenants.tenant",
                    ),
                ),
            ],
            options={
                "db_table": "translations_job_run",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="translationjobrun",
            index=models.Index(
                fields=["tenant", "created_at"], name="trn_job_tnt_ct_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="translationjobrun",
            index=models.Index(
                fields=["tenant", "status"], name="trn_job_tnt_stat_idx"
            ),
        ),
    ]
