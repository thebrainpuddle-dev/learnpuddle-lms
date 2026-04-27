# Migration for TASK-023: SCIM 2.0 User Provisioning — SCIMToken model.

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0011_user_password_changed_at"),
        ("tenants", "0031_auditlog_course_gen_flagged"),
    ]

    operations = [
        migrations.CreateModel(
            name="SCIMToken",
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
                    "name",
                    models.CharField(
                        help_text="Human-readable label, e.g. 'Okta production'",
                        max_length=100,
                    ),
                ),
                (
                    "token_hash",
                    models.CharField(
                        help_text=(
                            "SHA-256 hex digest of the raw token — "
                            "never the plaintext."
                        ),
                        max_length=64,
                        unique=True,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("last_used_at", models.DateTimeField(blank=True, null=True)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_scim_tokens",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="scim_tokens",
                        to="tenants.tenant",
                    ),
                ),
            ],
            options={
                "db_table": "scim_tokens",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="scimtoken",
            index=models.Index(
                fields=["tenant", "is_active"],
                name="scim_tokens_tenant_active_idx",
            ),
        ),
    ]
