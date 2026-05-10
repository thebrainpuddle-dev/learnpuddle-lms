"""V2 storage helper for media bytes (images, videos, audio).

Source: apps/courses/maic_storage.py:storage_upload (v1 helper, scheduled
        for deletion in Phase 8 MAIC-802). This is the V2 rewrite — same
        contract, async-friendly, tenant-scoped keys, no caller boilerplate.

Used by:
  - apps/maic/media/adapters/*.py — every adapter uploads its bytes here
    after the provider returns
  - Future TTS audio persistence (currently TTS streams via WS without
    persistence; if cached-audio lands later it will use this same helper)

Discipline:
  - Tenant-scoped keys: ``maic/<tenant_id>/<kind>/<media_id>.<ext>`` —
    so a leaked URL still respects tenant boundary at the S3 ACL layer
  - secrets.token_urlsafe(8) for media IDs — collision-resistant, URL-safe,
    short enough for human-readable URLs
  - default_storage abstraction means dev runs on FileSystemStorage
    (local), prod runs on S3Boto3Storage — same code path
  - sync_to_async wraps the underlying sync storage call so async
    callers (orchestrator, adapters) don't block the event loop
"""
from __future__ import annotations

import secrets
from typing import Literal

from asgiref.sync import sync_to_async
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage


MediaKind = Literal["image", "video", "audio"]


_EXT_BY_CONTENT_TYPE: dict[str, str] = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
    "image/gif": "gif",
    "video/mp4": "mp4",
    "video/webm": "webm",
    "audio/mpeg": "mp3",
    "audio/wav": "wav",
}


def _ext_for(content_type: str) -> str:
    """Return the file extension matching a content type, or 'bin' as a
    last-resort fallback (lets us upload unknown types without crashing,
    while flagging the surprise in the filename)."""
    return _EXT_BY_CONTENT_TYPE.get(content_type.lower().strip(), "bin")


def _save_sync(key: str, data: bytes) -> str:
    """Synchronous core: overwrite-aware save + return the public URL.

    The overwrite-then-save dance mirrors v1's behavior (so a media-id
    collision, however unlikely, doesn't 500 on the second save). In
    practice ``secrets.token_urlsafe(8)`` gives 2^48 entropy — collisions
    are astronomical — but defensive code is cheap."""
    if default_storage.exists(key):
        default_storage.delete(key)
    default_storage.save(key, ContentFile(data))
    return default_storage.url(key)


async def upload_media(
    data: bytes,
    content_type: str,
    tenant_id: str,
    kind: MediaKind = "image",
    scene_id: str | None = None,
) -> tuple[str, str]:
    """Upload media bytes to the configured Django storage backend.

    Returns (media_id, url). The media_id is the URL-safe random suffix;
    callers persist it on the slide element / scene so subsequent
    renders can resolve back to the URL.

    Tenant-scoped, kind-scoped path so a misconfigured S3 ACL can't
    cross-leak: ``maic/<tenant_id>/<kind>/<media_id>.<ext>``.

    Scene id is reserved for a future eviction pass (Phase 8/13 work);
    today it's stored in the key only when supplied so we can grep by
    scene later. Not part of the returned URL because URLs are
    long-lived.
    """
    if not tenant_id:
        # Defensive: refusing tenantless writes preserves the boundary.
        # An adapter calling without a tenant is a bug in its caller, not
        # something we paper over with a "default" tenant.
        raise ValueError("upload_media requires a non-empty tenant_id")

    media_id = secrets.token_urlsafe(8)
    ext = _ext_for(content_type)
    if scene_id:
        # Embed scene id in the key as a flat slug so it shows up in
        # storage listings, but keep media_id as the primary identifier
        # callers reference.
        key = f"maic/{tenant_id}/{kind}/{scene_id}__{media_id}.{ext}"
    else:
        key = f"maic/{tenant_id}/{kind}/{media_id}.{ext}"

    url = await sync_to_async(_save_sync)(key, data)
    return media_id, url
