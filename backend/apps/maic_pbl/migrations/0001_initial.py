"""MAIC-700 (Phase 7, 2026-05-05) — initial migration for maic_pbl app.

Creates a single table: `maic_pbl_sessions`. Holds the entire PBL
session state in JSONFields (project_config, chat_messages) so the
agentic design loop can mutate the in-memory PBLProjectConfig without
ORM round-trips per tool call. See models.py docstring for the
trade-off rationale.

Hand-written (not auto-generated) because the codebase has unrelated
pending model changes in other apps that auto-makemigrations tries
to scoop up. Same posture as Phase 5's MAIC-501 courses migration.
"""

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("tenants", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="MaicPBLSession",
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
                    "project_config",
                    models.JSONField(
                        default=dict,
                        help_text="Full PBLProjectConfig per apps/maic_pbl/types.py",
                    ),
                ),
                (
                    "chat_messages",
                    models.JSONField(
                        default=list,
                        help_text="list[PBLChatMessage] — append-only turn log",
                    ),
                ),
                ("topic", models.CharField(blank=True, default="", max_length=500)),
                ("language", models.CharField(blank=True, default="en", max_length=20)),
                ("agent_count", models.PositiveSmallIntegerField(default=4)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("draft", "Draft"),
                            ("active", "Active"),
                            ("completed", "Completed"),
                            ("failed", "Failed"),
                            ("archived", "Archived"),
                        ],
                        db_index=True,
                        default="draft",
                        max_length=20,
                    ),
                ),
                (
                    "error_message",
                    models.TextField(
                        blank=True,
                        default="",
                        help_text=(
                            "Populated when status=failed; first 500 chars of the loop's "
                            "exception or validation message. Long traces stay in logs."
                        ),
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "owner",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="maic_pbl_sessions",
                        to=settings.AUTH_USER_MODEL,
                        help_text=(
                            "Teacher who designed the project OR student who "
                            "opened it; Phase 7 doesn't distinguish — same "
                            "tenant scope either way."
                        ),
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        db_index=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="maic_pbl_sessions",
                        to="tenants.tenant",
                    ),
                ),
            ],
            options={
                "verbose_name": "MAIC v2 PBL session",
                "verbose_name_plural": "MAIC v2 PBL sessions",
                "db_table": "maic_pbl_sessions",
            },
        ),
        migrations.AddIndex(
            model_name="maicpblsession",
            index=models.Index(
                fields=["tenant", "status", "-created_at"],
                name="maic_pbl_se_tenant__a3c4f1_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="maicpblsession",
            index=models.Index(
                fields=["tenant", "owner", "-created_at"],
                name="maic_pbl_se_tenant__7d2e09_idx",
            ),
        ),
    ]
