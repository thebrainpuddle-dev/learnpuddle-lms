# Migration for AUDIT-2026-04-26-PHASE3-7: encrypt TOTP secrets at rest
# and hash 2FA backup codes.
#
# Two new tables:
#   * ``users_encrypted_totp_secret`` — Fernet ciphertext of the TOTP
#     seed, OneToOne with ``django_otp.plugins.otp_totp.TOTPDevice``.
#   * ``users_2fa_backup_codes``      — Django-password-hashed backup
#     codes with single-use ``used_at`` consumption.
#
# The companion data migration ``0015_migrate_legacy_2fa_to_encrypted``
# encrypts in-place any TOTPDevice rows that pre-date this change and
# rehashes any plaintext StaticToken backup codes that survived.
#
# Authored by hand to keep this migration scoped strictly to the
# PHASE3-7 fix and to avoid bundling unrelated drift.

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0013_scimtoken_expires_at"),
        ("otp_totp", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="EncryptedTOTPSecret",
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
                ("ciphertext", models.TextField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "device",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="encrypted_secret",
                        to="otp_totp.totpdevice",
                    ),
                ),
            ],
            options={
                "verbose_name": "Encrypted TOTP secret",
                "verbose_name_plural": "Encrypted TOTP secrets",
                "db_table": "users_encrypted_totp_secret",
            },
        ),
        migrations.CreateModel(
            name="BackupCode",
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
                ("code_hash", models.CharField(max_length=255)),
                ("used_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="backup_codes",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "users_2fa_backup_codes",
                "indexes": [
                    models.Index(
                        fields=["user", "used_at"],
                        name="users_2fa_b_user_id_19b643_idx",
                    ),
                ],
            },
        ),
    ]
