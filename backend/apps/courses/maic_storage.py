"""Storage abstraction for MAIC TTS files.

Uses Django's ``default_storage`` so the same code path works for the local
filesystem in development and any S3-compatible backend in production.

Kept deliberately thin — the Celery pre-gen task imports these functions by
name so they can be patched in tests without monkey-patching Django's
storage singleton.
"""
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage


def storage_upload(key: str, data: bytes, content_type: str = "audio/mpeg") -> str:
    """Upload ``data`` to ``key`` and return the publicly resolvable URL.

    Overwrites any existing object at ``key`` so re-generations always win.
    ``content_type`` is accepted for API compatibility with callers but is
    not enforced here — S3-backed storages infer from the key extension.
    """
    if default_storage.exists(key):
        default_storage.delete(key)
    default_storage.save(key, ContentFile(data))
    return default_storage.url(key)


def storage_exists(key: str) -> bool:
    """Return True if an object already exists at ``key``."""
    return default_storage.exists(key)
