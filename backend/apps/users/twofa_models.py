"""
Encryption-at-rest helpers for 2FA (AUDIT-2026-04-26-PHASE3-7).

Two complementary mitigations against a database-compromise attacker:

  1. **TOTP secret encrypted at rest.**  ``django_otp.TOTPDevice.key`` is
     normally a hex-encoded plaintext seed.  We add a sidecar
     :class:`EncryptedTOTPSecret` that carries a Fernet ciphertext of
     the seed, and overwrite ``TOTPDevice.key`` with a fixed sentinel so
     that a DB dump leaks no usable TOTP secret.  Verification reads the
     sidecar, decrypts, and feeds the result through
     ``django_otp.oath.TOTP`` directly — django-otp's own
     ``verify_token`` requires the key to live on the row and is
     therefore bypassed in favour of an explicit, equivalent check.

  2. **Backup codes hashed.**  ``django_otp.StaticToken`` stores tokens
     in plaintext.  We replace it with :class:`BackupCode`, which holds
     a Django password-hash (PBKDF2-SHA256 by default — argon2 if the
     deployment installs ``argon2-cffi``).  Verification iterates active
     rows and runs ``check_password``; on first match the row is marked
     consumed via ``used_at`` so the code is single-use.

Why a sidecar table instead of subclassing ``TOTPDevice``?  ``TOTPDevice``
is a third-party model whose ``key`` field cannot be replaced without a
schema-level monkey-patch that would diverge from upstream forever.  A
sidecar is small, audited, and lets us migrate the 2FA cohort
incrementally.
"""

from __future__ import annotations

import base64
import secrets
import time
import uuid
from typing import Iterable, List, Tuple

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import models, transaction
from django.utils import timezone
from django_otp.oath import TOTP
from django_otp.plugins.otp_totp.models import TOTPDevice

from utils.encryption import decrypt_value, encrypt_value


# ---------------------------------------------------------------------------
# Sentinels
# ---------------------------------------------------------------------------

# ``TOTPDevice.key`` is a CharField with ``hex_validator`` — it must be
# valid hex.  We use 40 hex zeroes so the field passes validation but
# leaks nothing (the real seed lives in the sidecar).
ENC_KEY_SENTINEL = "0" * 40


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class EncryptedTOTPSecret(models.Model):
    """Fernet-encrypted seed for a TOTPDevice.

    Linked one-to-one to ``django_otp.plugins.otp_totp.models.TOTPDevice``;
    deleting the device cascades.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    device = models.OneToOneField(
        TOTPDevice,
        on_delete=models.CASCADE,
        related_name="encrypted_secret",
    )
    # Fernet ciphertext of the raw 20-byte seed (base64-encoded inside
    # Fernet — we store the Fernet token verbatim).  TextField because
    # Fernet tokens are unbounded in principle.
    ciphertext = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "users_encrypted_totp_secret"
        verbose_name = "Encrypted TOTP secret"
        verbose_name_plural = "Encrypted TOTP secrets"

    def __str__(self) -> str:  # pragma: no cover
        return f"EncryptedTOTPSecret(device={self.device_id})"


class BackupCode(models.Model):
    """Single-use 2FA backup code, stored as a Django password hash."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="backup_codes",
    )
    code_hash = models.CharField(max_length=255)
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "users_2fa_backup_codes"
        indexes = [
            models.Index(
                fields=["user", "used_at"],
                name="users_2fa_b_user_id_19b643_idx",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"BackupCode(user={self.user_id}, used={self.used_at is not None})"

    @property
    def is_used(self) -> bool:
        return self.used_at is not None


# ---------------------------------------------------------------------------
# TOTP encryption helpers
# ---------------------------------------------------------------------------

@transaction.atomic
def create_encrypted_totp_device(
    user, *, name: str = "default", confirmed: bool = False
) -> Tuple[TOTPDevice, str]:
    """Create a TOTPDevice whose seed is stored encrypted at rest.

    Returns ``(device, secret_b32)`` — ``secret_b32`` is the base32 form
    suitable for handing to the user (QR code / manual entry).  The
    plaintext seed never re-touches the device row after this call.
    """
    # 20 bytes = 160 bits — django-otp's default and the RFC 6238 minimum.
    seed = secrets.token_bytes(20)
    seed_hex = seed.hex()

    device = TOTPDevice.objects.create(
        user=user,
        name=name,
        confirmed=confirmed,
        key=seed_hex,  # transient — overwritten in the same transaction
    )

    EncryptedTOTPSecret.objects.create(
        device=device,
        ciphertext=encrypt_value(seed_hex),
    )

    # Wipe plaintext from the device row.  We update directly to bypass
    # the hex validator running on save() in some django-otp versions.
    TOTPDevice.objects.filter(pk=device.pk).update(key=ENC_KEY_SENTINEL)
    device.key = ENC_KEY_SENTINEL

    secret_b32 = base64.b32encode(seed).decode("utf-8")
    return device, secret_b32


def _load_seed(device: TOTPDevice) -> bytes:
    """Return the device's plaintext binary seed.

    Falls back to the on-row hex key if no sidecar exists — this keeps
    legacy (pre-encryption) rows verifiable until the next regeneration.
    """
    try:
        sidecar = device.encrypted_secret  # type: ignore[attr-defined]
    except EncryptedTOTPSecret.DoesNotExist:
        return bytes.fromhex(device.key)

    seed_hex = decrypt_value(sidecar.ciphertext)
    if not seed_hex:
        # Decryption failed (e.g. SECRET_KEY rotated) — fail closed.
        return b""
    return bytes.fromhex(seed_hex)


def encrypted_provisioning_uri(device: TOTPDevice, secret_b32: str) -> str:
    """Build the otpauth:// URI from an out-of-band secret.

    We can't use ``device.config_url`` because that derives the secret
    from ``bin_key`` which is now a sentinel.  Caller passes the
    base32-encoded plaintext (the same value handed back to the user).
    """
    from urllib.parse import quote, urlencode

    label = str(device.user.get_username())
    params = {
        "secret": secret_b32,
        "algorithm": "SHA1",
        "digits": device.digits,
        "period": device.step,
    }
    urlencoded_params = urlencode(params)
    issuer = getattr(settings, "OTP_TOTP_ISSUER", None)
    if issuer:
        issuer = issuer.replace(":", "")
        label = f"{issuer}:{label}"
        urlencoded_params += f"&issuer={quote(issuer)}"
    return f"otpauth://totp/{quote(label)}?{urlencoded_params}"


def verify_encrypted_totp(device: TOTPDevice, token: str) -> bool:
    """Verify a TOTP code against the encrypted seed.

    Mirrors ``TOTPDevice.verify_token`` semantics: respects ``last_t``
    replay protection and updates drift on successful verification, but
    pulls the seed from the encrypted sidecar instead of the row's
    ``key`` column.
    """
    if not token:
        return False

    try:
        device.encrypted_secret  # type: ignore[attr-defined]
    except EncryptedTOTPSecret.DoesNotExist:
        # Legacy TOTPDevice rows still keep their seed on the device. Delegate
        # to django-otp's implementation so old installations and older tests
        # retain the same verification semantics until regenerated.
        return bool(device.verify_token(token))

    # django-otp throttling — keep it.
    verify_allowed, _ = device.verify_is_allowed()
    if not verify_allowed:
        return False

    try:
        token_int = int(token)
    except (TypeError, ValueError):
        device.throttle_increment(commit=True)
        return False

    seed = _load_seed(device)
    if not seed:
        device.throttle_increment(commit=True)
        return False

    totp = TOTP(seed, device.step, device.t0, device.digits, device.drift)
    totp.time = time.time()

    verified = totp.verify(token_int, device.tolerance, device.last_t + 1)
    if verified:
        device.last_t = totp.t()
        if getattr(settings, "OTP_TOTP_SYNC", True):
            device.drift = totp.drift
        device.throttle_reset(commit=False)
        device.save()
    else:
        device.throttle_increment(commit=True)
    return verified


# ---------------------------------------------------------------------------
# Backup-code helpers
# ---------------------------------------------------------------------------

def _generate_code_plaintext() -> str:
    """8-character uppercase hex — same shape the legacy implementation
    handed to users."""
    return secrets.token_hex(4).upper()


@transaction.atomic
def generate_hashed_backup_codes(user, *, count: int = 10) -> List[str]:
    """Issue ``count`` fresh backup codes for ``user``.

    Returns the plaintext codes (caller MUST display these once and
    discard).  Any prior backup codes — used or not — are deleted in
    the same transaction so a leaked code never survives a regeneration.
    """
    BackupCode.objects.filter(user=user).delete()

    plaintexts: List[str] = []
    rows = []
    for _ in range(count):
        code = _generate_code_plaintext()
        plaintexts.append(code)
        rows.append(BackupCode(user=user, code_hash=make_password(code)))
    BackupCode.objects.bulk_create(rows)
    return plaintexts


def verify_and_consume_backup_code(user, candidate: str) -> bool:
    """Verify ``candidate`` against the user's active backup codes.

    On match the row is atomically marked ``used_at=now`` and the
    function returns ``True``.  No-op for empty candidates.
    """
    if not candidate:
        return False

    candidate = candidate.strip()
    if not candidate:
        return False

    # Iterate active rows.  Cohorts are tiny (≤10) so the linear scan
    # is fine; the cost is dominated by the password-hash verifier.
    rows = list(
        BackupCode.objects
        .select_for_update(skip_locked=True)
        .filter(user=user, used_at__isnull=True)
    )

    for row in rows:
        if check_password(candidate, row.code_hash):
            # Single-use: mark consumed.  ``update`` (not ``save``)
            # ensures we don't write the hash back.
            now = timezone.now()
            updated = BackupCode.objects.filter(
                pk=row.pk, used_at__isnull=True
            ).update(used_at=now)
            if updated:
                return True
            # Race: someone else consumed it; keep scanning.

    return False


def remaining_backup_codes(user) -> int:
    return BackupCode.objects.filter(user=user, used_at__isnull=True).count()
