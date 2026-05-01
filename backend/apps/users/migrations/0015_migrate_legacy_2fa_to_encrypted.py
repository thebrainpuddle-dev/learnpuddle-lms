# Data migration: re-write existing 2FA state to encryption-at-rest
# (AUDIT-2026-04-26-PHASE3-7).
#
# 1. For every TOTPDevice row whose ``key`` is still a real hex seed
#    (i.e. there is no EncryptedTOTPSecret sidecar yet), encrypt the
#    seed into the sidecar and overwrite the row's ``key`` with the
#    sentinel placeholder.  Existing TOTP enrollments keep working —
#    the verify wrapper transparently reads the sidecar on lookup.
#
# 2. For every StaticDevice / StaticToken backup code, issue an
#    equivalent BackupCode row carrying a Django password hash of the
#    plaintext, then delete the plaintext StaticToken.  This is a
#    *one-shot* re-hash — after this migration the plaintext is gone,
#    and verification must use the new BackupCode helpers.
#
# The realistic 2FA cohort at this point in the product's lifecycle is
# single-digit users; the linear scan is fine.  Failure to encrypt
# (e.g. cryptography import error) is fatal — the migration aborts
# rather than leaving a partially-migrated cohort.

from django.db import migrations


def _encrypt_existing_totp(apps, schema_editor):
    TOTPDevice = apps.get_model("otp_totp", "TOTPDevice")
    EncryptedTOTPSecret = apps.get_model("users", "EncryptedTOTPSecret")

    # Late import — utils.encryption pulls django settings, which are
    # available at migration runtime.
    from utils.encryption import encrypt_value

    SENTINEL = "0" * 40

    for device in TOTPDevice.objects.all().iterator():
        if EncryptedTOTPSecret.objects.filter(device_id=device.pk).exists():
            continue
        if device.key == SENTINEL:
            # Already migrated by an earlier wave but the sidecar is
            # missing — we cannot recover the seed.  Fail loudly so the
            # operator can re-issue the device manually.
            raise RuntimeError(
                f"TOTPDevice {device.pk} carries the sentinel key but "
                "no EncryptedTOTPSecret sidecar exists.  Manual repair "
                "required: have the user re-enroll 2FA."
            )
        EncryptedTOTPSecret.objects.create(
            device_id=device.pk,
            ciphertext=encrypt_value(device.key),
        )
        device.key = SENTINEL
        device.save(update_fields=["key"])


def _rehash_existing_backup_codes(apps, schema_editor):
    StaticDevice = apps.get_model("otp_static", "StaticDevice")
    StaticToken = apps.get_model("otp_static", "StaticToken")
    BackupCode = apps.get_model("users", "BackupCode")

    from django.contrib.auth.hashers import make_password

    for device in StaticDevice.objects.all().iterator():
        tokens = list(StaticToken.objects.filter(device_id=device.pk))
        if not tokens:
            continue
        new_rows = [
            BackupCode(user_id=device.user_id, code_hash=make_password(t.token))
            for t in tokens
        ]
        BackupCode.objects.bulk_create(new_rows)
        # Wipe the plaintext.  The legacy StaticDevice / StaticToken
        # tables remain present (they're still in INSTALLED_APPS for
        # back-compat reads in the verify path) but no longer carry
        # any plaintext — the verify path now hits BackupCode first.
        StaticToken.objects.filter(device_id=device.pk).delete()


def _noop_reverse(apps, schema_editor):
    # Reverse is intentionally a no-op: we cannot reconstruct the
    # plaintext seed from the ciphertext-only state, and we never want
    # to *automatically* downgrade a security control.  Operators who
    # need to roll back this migration must restore from a database
    # snapshot taken before it ran.
    return


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0014_twofa_secret_at_rest"),
        ("otp_static", "0002_throttling"),
    ]

    operations = [
        migrations.RunPython(_encrypt_existing_totp, _noop_reverse),
        migrations.RunPython(_rehash_existing_backup_codes, _noop_reverse),
    ]
