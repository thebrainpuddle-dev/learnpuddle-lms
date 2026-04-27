# Generated for TASK-045 — password history + SAML auth audit events.

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0019_saml_and_password_policy"),
        ("users", "0009_add_grade_section_fks"),
    ]

    operations = [
        migrations.CreateModel(
            name="PasswordHistory",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("hashed_password", models.CharField(max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="password_history",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "password_history",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(
                        fields=["user", "-created_at"],
                        name="password_hi_user_id_created_idx",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="SAMLAuthEvent",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("email", models.EmailField(blank=True, default="", max_length=254)),
                (
                    "decision",
                    models.CharField(
                        choices=[
                            ("ACCEPT", "Accepted"),
                            ("REJECT_SIGNATURE", "Rejected: bad signature"),
                            ("REJECT_EXPIRED", "Rejected: assertion expired"),
                            ("REJECT_NOT_YET_VALID", "Rejected: assertion not yet valid"),
                            ("REJECT_AUDIENCE", "Rejected: audience mismatch"),
                            ("REJECT_NO_EMAIL", "Rejected: no email attribute"),
                            ("REJECT_PROVISION_DISABLED", "Rejected: auto-provision disabled"),
                            ("REJECT_DOMAIN_NOT_ALLOWED", "Rejected: email domain not allowed"),
                            ("REJECT_DISABLED", "Rejected: SAML not enabled for tenant"),
                            ("REJECT_MALFORMED", "Rejected: malformed response"),
                            ("REJECT_REPLAY", "Rejected: replay detected"),
                        ],
                        max_length=40,
                    ),
                ),
                ("detail", models.CharField(blank=True, default="", max_length=500)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                (
                    "assertion_id",
                    models.CharField(
                        blank=True,
                        db_index=True,
                        default="",
                        help_text="SAML Response ID — used for replay detection.",
                        max_length=255,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                (
                    "tenant",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="saml_auth_events",
                        to="tenants.tenant",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="saml_auth_events",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "saml_auth_events",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(
                        fields=["tenant", "-created_at"],
                        name="saml_auth_e_tenant_created_idx",
                    ),
                    models.Index(
                        fields=["decision", "-created_at"],
                        name="saml_auth_e_decision_created_idx",
                    ),
                ],
            },
        ),
    ]
