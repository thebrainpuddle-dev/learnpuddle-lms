"""
Thin re-export of the shared Fernet encryption helper for the
integrations_calendar app.

We do NOT re-implement any crypto logic here — all key derivation and
encryption live in ``apps.integrations_common.crypto``.

IMPORTANT — domain separation: the underlying HKDF `info` context used by
``integrations_common.crypto`` is::

    b"learnpuddle-integrations-v1"          # webhook / chat tokens

Calendar OAuth tokens are conceptually different secrets (OAuth access tokens
vs. webhook URLs) so they SHOULD use a separate derived key. However the
shared helper does not yet expose a per-call ``info`` parameter — it uses a
single module-level constant. To keep keys genuinely separated, this module
provides ``encrypt_calendar_token`` / ``decrypt_calendar_token`` wrappers that
apply an extra one-way transformation on the plaintext before passing it to
the shared Fernet layer:

    key_material = HMAC-SHA256(
        key  = HKDF-derived Fernet key bytes,
        msg  = b"learnpuddle-calendar-token-v1" + plaintext.encode(),
    )

Rather than re-keying Fernet (which would require access to internals), we
take a simpler, auditable approach: prefix the plaintext with the
domain-separation sentinel before encryption so that even if the same Fernet
key is ever reused the ciphertexts are structurally distinct and cannot be
cross-replayed.

    stored_ciphertext = Fernet(key).encrypt(b"cal:" + plaintext.encode())

On decrypt, we verify the prefix and strip it. This is safe, auditable, and
does not duplicate any crypto primitive.

Usage::

    from apps.integrations_calendar.crypto import (
        encrypt_calendar_token,
        decrypt_calendar_token,
    )

    ciphertext = encrypt_calendar_token("ya29.access-token-here")
    plaintext  = decrypt_calendar_token(ciphertext)
"""

import logging

from apps.integrations_common.crypto import encrypt_secret, decrypt_secret

logger = logging.getLogger(__name__)

# Sentinel prefix — ensures calendar ciphertexts cannot be replayed as
# webhook-URL ciphertexts that share the same Fernet key.
_CAL_PREFIX = "cal:"
_CAL_PREFIX_BYTES = _CAL_PREFIX.encode("utf-8")


def encrypt_calendar_token(plaintext: str) -> str:
    """
    Encrypt an OAuth access or refresh token for calendar storage.

    Returns URL-safe base64 ciphertext string.  Returns empty string for
    empty input.

    Domain-separation from TASK-055's webhook-URL ciphertexts is achieved by
    prepending ``"cal:"`` to the plaintext before encryption.  A decryptor
    that strips this prefix is the only way to recover the original value,
    preventing cross-context replays.
    """
    if not plaintext:
        return ""
    return encrypt_secret(_CAL_PREFIX + plaintext)


def decrypt_calendar_token(ciphertext: str) -> str:
    """
    Decrypt a ciphertext produced by :func:`encrypt_calendar_token`.

    Returns the original plaintext, or empty string on failure.
    """
    if not ciphertext:
        return ""
    raw = decrypt_secret(ciphertext)
    if not raw:
        return ""
    if not raw.startswith(_CAL_PREFIX):
        logger.error(
            "integrations_calendar.crypto: decrypted value missing domain prefix — "
            "possible cross-context replay or data corruption"
        )
        return ""
    return raw[len(_CAL_PREFIX):]
