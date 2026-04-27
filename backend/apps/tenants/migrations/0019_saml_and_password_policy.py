# Generated for TASK-045 — SAML SSO + per-tenant password policies.

import uuid

import django.db.models.deletion
from django.db import migrations, models

import apps.tenants.saml_models


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0018_update_cert_types"),
    ]

    operations = [
        migrations.CreateModel(
            name="TenantSAMLConfig",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("enabled", models.BooleanField(default=False)),
                (
                    "idp_metadata_xml",
                    models.TextField(
                        blank=True, default="", help_text="Full IdP SAML 2.0 metadata XML."
                    ),
                ),
                ("idp_entity_id", models.CharField(blank=True, default="", max_length=500)),
                ("idp_sso_url", models.URLField(blank=True, default="", max_length=500)),
                ("idp_slo_url", models.URLField(blank=True, default="", max_length=500)),
                (
                    "idp_x509_certs",
                    models.JSONField(
                        blank=True,
                        default=list,
                        help_text="List of PEM-encoded X.509 certs extracted from IdP metadata.",
                    ),
                ),
                (
                    "sp_entity_id",
                    models.CharField(
                        help_text="This SP's entity ID (usually the tenant's ACS URL).",
                        max_length=500,
                    ),
                ),
                (
                    "sp_x509_cert",
                    models.TextField(
                        blank=True,
                        default="",
                        help_text="PEM-encoded SP certificate (optional, for signing AuthnRequests).",
                    ),
                ),
                (
                    "sp_private_key",
                    models.TextField(
                        blank=True,
                        default="",
                        help_text="PEM-encoded SP private key (encrypted at rest in production).",
                    ),
                ),
                (
                    "attribute_mapping",
                    models.JSONField(
                        blank=True,
                        default=apps.tenants.saml_models.default_attribute_mapping,
                        help_text="Keys restricted to: email, first_name, last_name, groups, role.",
                    ),
                ),
                (
                    "auto_provision",
                    models.BooleanField(
                        default=False,
                        help_text="If True, unknown users are created on successful SSO.",
                    ),
                ),
                (
                    "default_role",
                    models.CharField(
                        choices=[
                            ("TEACHER", "Teacher"),
                            ("HOD", "Head of Department"),
                            ("IB_COORDINATOR", "IB Coordinator"),
                            ("SCHOOL_ADMIN", "School Admin"),
                            ("STUDENT", "Student"),
                        ],
                        default="TEACHER",
                        help_text="Role assigned to auto-provisioned users.",
                        max_length=20,
                    ),
                ),
                (
                    "allowed_email_domains",
                    models.TextField(
                        blank=True,
                        default="",
                        help_text="Comma-separated domains; empty = allow any.",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "tenant",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="saml_config",
                        to="tenants.tenant",
                    ),
                ),
            ],
            options={
                "verbose_name": "Tenant SAML config",
                "verbose_name_plural": "Tenant SAML configs",
                "db_table": "tenant_saml_configs",
            },
        ),
        migrations.CreateModel(
            name="TenantPasswordPolicy",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("min_length", models.PositiveIntegerField(default=8)),
                ("require_uppercase", models.BooleanField(default=True)),
                ("require_lowercase", models.BooleanField(default=True)),
                ("require_digit", models.BooleanField(default=True)),
                ("require_special", models.BooleanField(default=False)),
                (
                    "prevent_common",
                    models.BooleanField(
                        default=True,
                        help_text="Reject passwords on Django's built-in common-password list.",
                    ),
                ),
                (
                    "prevent_reuse_last_n",
                    models.PositiveIntegerField(
                        default=0,
                        help_text="0 disables history checks; otherwise last N hashes are rejected.",
                    ),
                ),
                (
                    "max_age_days",
                    models.PositiveIntegerField(
                        default=0,
                        help_text="0 = passwords never expire; else number of days before forced rotation.",
                    ),
                ),
                (
                    "lockout_threshold",
                    models.PositiveIntegerField(
                        default=5,
                        help_text="Consecutive failed attempts before lockout.",
                    ),
                ),
                (
                    "lockout_duration_minutes",
                    models.PositiveIntegerField(
                        default=30,
                        help_text="Minutes to keep account locked after threshold hit.",
                    ),
                ),
                ("policy_rotated_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "tenant",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="password_policy",
                        to="tenants.tenant",
                    ),
                ),
            ],
            options={
                "verbose_name": "Tenant password policy",
                "verbose_name_plural": "Tenant password policies",
                "db_table": "tenant_password_policies",
            },
        ),
    ]
