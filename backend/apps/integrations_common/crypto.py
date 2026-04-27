"""
Shared Fernet encryption helper for integrations that store secrets
(webhook URLs, API keys) encrypted at rest.

Key derivation: HKDF-SHA256 applied to Django's SECRET_KEY.
We deliberately do NOT use SECRET_KEY directly as a Fernet key because:
  1. Fernet requires exactly 32 URL-safe base64-encoded bytes.
  2. SECRET_KEY length and entropy varies; HKDF normalises both.
  3. HKDF allows domain-separation via `info` so future integrations
     can derive independent sub-keys from the same root secret.

Reusable by TASK-054 (and any future integration that stores secrets).

Usage::

    from apps.integrations_common.crypto import encrypt_secret, decrypt_secret

    ciphertext = encrypt_secret("https://hooks.slack.com/services/T.../B.../xxx")
    plaintext  = decrypt_secret(ciphertext)
    masked     = mask_secret(plaintext)   # "https://hooks.slack.com/...abcd"
"""

import base64
import hashlib
import hmac
import logging
import struct

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

logger = logging.getLogger(__name__)

# Domain-separation label — changing this invalidates all existing ciphertext.
_HKDF_INFO = b"learnpuddle-integrations-v1"
_HKDF_SALT = b"learnpuddle-integrations-salt-v1"


def _hkdf_sha256(ikm: bytes, length: int = 32, salt: bytes = _HKDF_SALT, info: bytes = _HKDF_INFO) -> bytes:
    """
    Minimal HKDF-SHA256 (RFC 5869).

    We implement this directly rather than pulling in a new dependency
    (cryptography >= 1.0 already provides it, but the API changed across
    versions so a hand-rolled version avoids compatibility issues).
    """
    # Extract
    prk = hmac.HMAC(salt, ikm, hashlib.sha256).digest()

    # Expand
    okm = b""
    t = b""
    for i in range(1, -(-length // 32) + 1):  # ceil(length/32)
        t = hmac.HMAC(prk, t + info + struct.pack("B", i), hashlib.sha256).digest()
        okm += t

    return okm[:length]


def _derive_fernet_key() -> bytes:
    """Return a URL-safe base64-encoded 32-byte key derived from SECRET_KEY."""
    ikm = settings.SECRET_KEY.encode("utf-8")
    raw = _hkdf_sha256(ikm)
    return base64.urlsafe_b64encode(raw)


def encrypt_secret(plaintext: str) -> str:
    """
    Encrypt *plaintext* with Fernet (AES-128-CBC + HMAC-SHA256).
    Returns URL-safe base64 ciphertext string suitable for DB storage.
    Returns empty string for empty input.
    """
    if not plaintext:
        return ""
    key = _derive_fernet_key()
    return Fernet(key).encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(ciphertext: str) -> str:
    """
    Decrypt a ciphertext string produced by :func:`encrypt_secret`.
    Returns empty string if ciphertext is empty or decryption fails.
    """
    if not ciphertext:
        return ""
    key = _derive_fernet_key()
    try:
        return Fernet(key).decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        logger.error(
            "integrations_common.crypto: decryption failed — "
            "possible SECRET_KEY rotation or data corruption"
        )
        return ""


def mask_secret(plaintext: str, visible: int = 4) -> str:
    """
    Return a masked representation of *plaintext* that reveals only the last
    *visible* characters.  All preceding characters are replaced with ``…``.

    Example::

        mask_secret("https://hooks.slack.com/services/T123/B456/abcdefgh", 4)
        -> "…efgh"
    """
    if not plaintext:
        return ""
    if len(plaintext) <= visible:
        return plaintext
    return "…" + plaintext[-visible:]
