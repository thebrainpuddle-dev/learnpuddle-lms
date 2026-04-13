"""
Symmetric encryption for tenant API keys using Fernet + PBKDF2.

Uses Django's SECRET_KEY as the base for key derivation, ensuring
encrypted values are tied to this deployment. Rotation requires
re-encrypting all stored values.

Usage:
    from utils.encryption import encrypt_value, decrypt_value

    encrypted = encrypt_value("sk-abc123...")
    plaintext = decrypt_value(encrypted)
"""

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

logger = logging.getLogger(__name__)

_SALT = b"learnpuddle-tenant-ai-keys-v1"


def _derive_key() -> bytes:
    """Derive a 32-byte Fernet key from Django's SECRET_KEY via PBKDF2."""
    secret = settings.SECRET_KEY.encode("utf-8")
    dk = hashlib.pbkdf2_hmac("sha256", secret, _SALT, iterations=480_000, dklen=32)
    return base64.urlsafe_b64encode(dk)


def encrypt_value(plaintext: str) -> str:
    """Encrypt a plaintext string, return URL-safe base64 ciphertext."""
    if not plaintext:
        return ""
    f = Fernet(_derive_key())
    return f.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_value(ciphertext: str) -> str:
    """Decrypt a ciphertext string back to plaintext."""
    if not ciphertext:
        return ""
    f = Fernet(_derive_key())
    try:
        return f.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        logger.error("Failed to decrypt value — possible SECRET_KEY rotation or data corruption")
        return ""
