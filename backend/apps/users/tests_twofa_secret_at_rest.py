"""
Encryption-at-rest for TOTP secrets and hashing of 2FA backup codes
(AUDIT-2026-04-26-PHASE3-7).

Two related defences against a database-compromise attacker:

  * **TOTP `bin_key` encrypted at rest.**  django-otp's stock
    ``TOTPDevice.key`` is hex-encoded plaintext.  We Fernet-encrypt the
    seed (using the same key derivation already used by
    :class:`apps.tenants.saml_models.TenantSAMLConfig`) and overwrite
    the in-row ``key`` with a sentinel placeholder.  The sidecar table
    ``EncryptedTOTPSecret`` carries the ciphertext; verification
    decrypts on demand and runs through django-otp's TOTP machinery.

  * **Backup codes hashed.**  django-otp's ``StaticToken`` stores the
    raw token.  We replace it with ``BackupCode`` rows whose ``code_hash``
    column carries a Django password hash (PBKDF2-SHA256 via
    ``make_password``) and a ``used_at`` timestamp.  Verification
    iterates active rows (``used_at IS NULL``) and ``check_password``-es
    the candidate; on first match the row is marked consumed.

These tests assert both directions: storage is opaque to a DB dump AND
verification still works end-to-end.
"""

from __future__ import annotations

import uuid

import pytest
from django.contrib.auth.hashers import check_password
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.tenants.models import Tenant
from apps.users.models import User

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tenant() -> Tenant:
    sub = uuid.uuid4().hex[:8]
    return Tenant.objects.create(
        name=f"School {sub}",
        slug=sub,
        subdomain=sub,
        email=f"admin@{sub}.test",
    )


def _make_user(tenant: Tenant) -> User:
    return User.objects.create_user(
        email=f"u-{uuid.uuid4().hex[:6]}@test.com",
        password="Password123!",
        first_name="Jane",
        last_name="Doe",
        tenant=tenant,
        role="TEACHER",
    )


# ---------------------------------------------------------------------------
# 1. TOTP secret is NOT plaintext in DB
# ---------------------------------------------------------------------------

def test_totp_bin_key_is_encrypted_at_rest():
    """After encrypted setup, the ``TOTPDevice.key`` column is a sentinel
    placeholder, NOT the original hex secret.  The original seed lives in
    the ``EncryptedTOTPSecret`` sidecar as Fernet ciphertext."""
    from apps.users.twofa_models import (
        EncryptedTOTPSecret, ENC_KEY_SENTINEL, create_encrypted_totp_device,
    )

    tenant = _make_tenant()
    user = _make_user(tenant)

    device, secret_b32 = create_encrypted_totp_device(user, name="default")

    # The TOTPDevice row's ``key`` field MUST be a sentinel, not the
    # original hex.
    fresh = TOTPDevice.objects.get(pk=device.pk)
    assert fresh.key == ENC_KEY_SENTINEL, (
        f"TOTPDevice.key should be sentinel placeholder; got {fresh.key!r}"
    )

    # The encrypted sidecar must exist and must NOT contain anything that
    # decodes to the device's original seed.
    sidecar = EncryptedTOTPSecret.objects.get(device=fresh)
    assert sidecar.ciphertext, "ciphertext must be persisted"

    # Fernet ciphertext is base64-url and starts with 'gAAAAA' (version 0x80).
    assert sidecar.ciphertext.startswith("gAAAAA"), (
        f"ciphertext does not look like a Fernet token: {sidecar.ciphertext[:20]}"
    )

    # The plaintext seed must NOT appear anywhere in the ciphertext.
    import base64
    plaintext_hex = base64.b32decode(secret_b32).hex()
    assert plaintext_hex not in sidecar.ciphertext


# ---------------------------------------------------------------------------
# 2. Round-trip: encrypted setup → verify_token still works
# ---------------------------------------------------------------------------

def test_totp_verify_round_trip_through_encrypted_storage():
    """A current TOTP code, computed against the in-memory seed, is
    accepted by the verify wrapper."""
    from apps.users.twofa_models import (
        create_encrypted_totp_device, verify_encrypted_totp,
    )
    from django_otp.oath import TOTP
    import base64
    import time

    tenant = _make_tenant()
    user = _make_user(tenant)
    device, secret_b32 = create_encrypted_totp_device(user, name="default")

    # Compute the current TOTP code from the seed we were handed.
    seed = base64.b32decode(secret_b32)
    totp = TOTP(seed, device.step, device.t0, device.digits, device.drift)
    totp.time = time.time()
    code = "{:0{digits}d}".format(totp.token(), digits=device.digits)

    # Verify through the wrapper which decrypts the sidecar.
    assert verify_encrypted_totp(device, code) is True

    # Wrong code rejected.
    bad = "0" * device.digits if code != "0" * device.digits else "1" * device.digits
    assert verify_encrypted_totp(device, bad) is False


# ---------------------------------------------------------------------------
# 3. Backup codes are hashed in the DB
# ---------------------------------------------------------------------------

def test_backup_codes_are_hashed_not_plaintext():
    """``BackupCode.code_hash`` must look like a Django password hash
    (algorithm prefix + parameters) and MUST NOT contain the plaintext."""
    from apps.users.twofa_models import BackupCode, generate_hashed_backup_codes

    tenant = _make_tenant()
    user = _make_user(tenant)

    plaintexts = generate_hashed_backup_codes(user, count=5)
    assert len(plaintexts) == 5
    assert all(isinstance(c, str) and len(c) >= 8 for c in plaintexts)

    rows = list(BackupCode.objects.filter(user=user, used_at__isnull=True))
    assert len(rows) == 5

    for row in rows:
        # The Django password-hash format is ``<algo>$<params>...``.
        assert "$" in row.code_hash
        # Plaintext must not appear in the persisted hash.
        for code in plaintexts:
            assert code not in row.code_hash, (
                "Plaintext backup code leaked into stored hash"
            )
        # Sanity: at least one of the plaintexts validates against this hash.
        assert any(check_password(code, row.code_hash) for code in plaintexts)


# ---------------------------------------------------------------------------
# 4. Backup-code verification accepts the right code, rejects wrong ones
# ---------------------------------------------------------------------------

def test_backup_code_verify_accepts_right_rejects_wrong():
    from apps.users.twofa_models import (
        generate_hashed_backup_codes, verify_and_consume_backup_code,
    )

    tenant = _make_tenant()
    user = _make_user(tenant)
    codes = generate_hashed_backup_codes(user, count=5)

    # A correct code returns True.
    assert verify_and_consume_backup_code(user, codes[2]) is True

    # A bogus code returns False.
    assert verify_and_consume_backup_code(user, "WRONGCODE12345") is False


# ---------------------------------------------------------------------------
# 5. Backup codes are single-use
# ---------------------------------------------------------------------------

def test_backup_code_is_single_use():
    """A successful verify marks ``used_at``; the same code cannot be
    consumed twice."""
    from apps.users.twofa_models import (
        BackupCode, generate_hashed_backup_codes, verify_and_consume_backup_code,
    )

    tenant = _make_tenant()
    user = _make_user(tenant)
    codes = generate_hashed_backup_codes(user, count=3)
    target = codes[0]

    assert verify_and_consume_backup_code(user, target) is True
    # Second use must be rejected.
    assert verify_and_consume_backup_code(user, target) is False

    # The exact row should now have used_at set.
    consumed = BackupCode.objects.filter(user=user, used_at__isnull=False).count()
    assert consumed == 1
    remaining = BackupCode.objects.filter(user=user, used_at__isnull=True).count()
    assert remaining == 2


# ---------------------------------------------------------------------------
# 6. Regenerating wipes prior unused codes
# ---------------------------------------------------------------------------

def test_regenerating_backup_codes_invalidates_prior_unused():
    """Calling generate_hashed_backup_codes a second time must invalidate
    every previously issued code (used or not).  Otherwise a leaked code
    survives a regeneration."""
    from apps.users.twofa_models import (
        BackupCode, generate_hashed_backup_codes, verify_and_consume_backup_code,
    )

    tenant = _make_tenant()
    user = _make_user(tenant)

    old_codes = generate_hashed_backup_codes(user, count=3)
    new_codes = generate_hashed_backup_codes(user, count=3)

    # No old code may verify any longer.
    for code in old_codes:
        assert verify_and_consume_backup_code(user, code) is False, (
            f"Old code {code} should have been invalidated by regeneration"
        )

    # All new codes verify.
    for code in new_codes:
        assert verify_and_consume_backup_code(user, code) is True

    # After all consumed, nothing is left.
    assert BackupCode.objects.filter(user=user, used_at__isnull=True).count() == 0


# ---------------------------------------------------------------------------
# 7. End-to-end: enrollment endpoint stores hashed backup codes & encrypted TOTP
# ---------------------------------------------------------------------------

def test_enrollment_endpoint_stores_encrypted_totp_and_hashed_codes():
    """Drives the actual ``/auth/2fa/setup/`` + ``/auth/2fa/confirm/``
    endpoints, then asserts that the persisted state matches
    encryption-at-rest invariants."""
    from django.test import Client
    from apps.users.twofa_models import (
        EncryptedTOTPSecret, BackupCode, ENC_KEY_SENTINEL,
    )
    from django_otp.oath import TOTP
    from rest_framework_simplejwt.tokens import RefreshToken
    import base64
    import time

    tenant = _make_tenant()
    user = _make_user(tenant)

    # Tenant subdomain is required by middleware; bearer JWT for auth.
    host = f"{tenant.subdomain}.localhost"
    access = str(RefreshToken.for_user(user).access_token)
    auth = f"Bearer {access}"
    c = Client(HTTP_HOST=host, HTTP_AUTHORIZATION=auth)

    # 1. start setup → gets secret + provisioning URI.
    resp = c.post("/api/users/auth/2fa/setup/")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    secret_b32 = body["secret"]
    seed = base64.b32decode(secret_b32)

    # The pending device is unconfirmed and already opaque on disk.
    pending = TOTPDevice.objects.get(user=user, confirmed=False)
    assert pending.key == ENC_KEY_SENTINEL
    assert EncryptedTOTPSecret.objects.filter(device=pending).exists()

    # 2. confirm setup with a correct code → returns backup codes.
    totp = TOTP(seed, pending.step, pending.t0, pending.digits, pending.drift)
    totp.time = time.time()
    code = "{:0{digits}d}".format(totp.token(), digits=pending.digits)

    resp = c.post(
        "/api/users/auth/2fa/confirm/",
        data={"code": code},
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    backup_codes = body["backup_codes"]
    assert len(backup_codes) == 10

    # The backup codes are hashed in the DB — none of the issued codes
    # appears verbatim.
    for row in BackupCode.objects.filter(user=user):
        for c_plain in backup_codes:
            assert c_plain not in row.code_hash
