"""
Create Parent Portal models: ParentSession and ParentMagicToken.
"""

import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0032_study_summary_teacher_fields"),
        ("tenants", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # 1. Create ParentSession table
        migrations.CreateModel(
            name="ParentSession",
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
                ("parent_email", models.EmailField(max_length=254)),
                (
                    "session_token",
                    models.CharField(
                        db_index=True, max_length=255, unique=True,
                    ),
                ),
                (
                    "refresh_token",
                    models.CharField(
                        db_index=True, max_length=255, unique=True,
                    ),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("expires_at", models.DateTimeField()),
                ("last_accessed", models.DateTimeField(auto_now=True)),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="parent_sessions",
                        to="tenants.tenant",
                    ),
                ),
                (
                    "students",
                    models.ManyToManyField(
                        blank=True,
                        related_name="parent_sessions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "parent_sessions",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(
                        fields=["tenant", "parent_email"],
                        name="parent_sess_tenant_email_idx",
                    ),
                    models.Index(
                        fields=["session_token"],
                        name="parent_sess_token_idx",
                    ),
                ],
            },
        ),
        # 2. Create ParentMagicToken table
        migrations.CreateModel(
            name="ParentMagicToken",
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
                ("parent_email", models.EmailField(max_length=254)),
                (
                    "token",
                    models.CharField(
                        db_index=True, max_length=255, unique=True,
                    ),
                ),
                ("is_used", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("expires_at", models.DateTimeField()),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="tenants.tenant",
                    ),
                ),
            ],
            options={
                "db_table": "parent_magic_tokens",
            },
        ),
    ]
