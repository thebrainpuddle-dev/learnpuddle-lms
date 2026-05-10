"""Tests for apps.maic.media.storage — tenant-scoped media uploads.

Discipline:
  - Uses Django's REAL default_storage (FileSystemStorage in dev/test).
    No mocks of storage — proves the upload actually writes a file
    callers can read back.
  - tmp_path fixture from pytest gives an isolated MEDIA_ROOT so tests
    don't pollute the dev media tree.
  - django_db marker means real Django settings; the actual storage
    backend is whatever's configured.
"""
from __future__ import annotations

import pytest
from django.core.files.storage import default_storage

from apps.maic.media.storage import _ext_for, upload_media


# ── _ext_for unit tests (no IO) ───────────────────────────────────────


def test_ext_for_known_image_types():
    assert _ext_for("image/png") == "png"
    assert _ext_for("image/jpeg") == "jpg"
    assert _ext_for("image/webp") == "webp"


def test_ext_for_known_video_types():
    assert _ext_for("video/mp4") == "mp4"
    assert _ext_for("video/webm") == "webm"


def test_ext_for_audio_types():
    """The TTS subsystem (Phase 5) may eventually use this helper for
    audio caching; supported content types include audio/*."""
    assert _ext_for("audio/mpeg") == "mp3"
    assert _ext_for("audio/wav") == "wav"


def test_ext_for_unknown_type_falls_back_to_bin():
    """Defensive — an adapter returning a weird content-type should
    still upload successfully (with a .bin filename); we don't 500 on
    surprise types."""
    assert _ext_for("application/octet-stream") == "bin"
    assert _ext_for("text/plain") == "bin"


def test_ext_for_handles_case_and_whitespace():
    """Content-Type headers in the wild come in mixed case + with
    whitespace. We normalize before lookup."""
    assert _ext_for("Image/PNG") == "png"
    assert _ext_for(" image/jpeg ") == "jpg"


# ── upload_media (real Django storage) ─────────────────────────────────


@pytest.mark.asyncio
async def test_upload_media_writes_file_and_returns_url(tmp_path, settings):
    """Sanity: 4 bytes go in, the same 4 bytes can be read back via
    default_storage.open(). Returned URL matches what default_storage.url
    would give for the key."""
    settings.MEDIA_ROOT = str(tmp_path)

    payload = b"PNG\x89"
    media_id, url = await upload_media(
        data=payload,
        content_type="image/png",
        tenant_id="t-1",
    )

    assert media_id
    assert url
    # Tenant-scoped key path
    assert "/maic/t-1/image/" in url
    assert url.endswith(".png")

    # Read-back via the same storage backend the upload used
    stored_key = f"maic/t-1/image/{media_id}.png"
    assert default_storage.exists(stored_key)
    with default_storage.open(stored_key, "rb") as fh:
        assert fh.read() == payload


@pytest.mark.asyncio
async def test_upload_media_with_scene_id_embeds_in_key(tmp_path, settings):
    """When scene_id is supplied, the key embeds it as a flat slug for
    grep-ability — useful when listing storage by scene later."""
    settings.MEDIA_ROOT = str(tmp_path)

    media_id, url = await upload_media(
        data=b"x",
        content_type="image/png",
        tenant_id="t-1",
        scene_id="scene-abc",
    )
    assert "scene-abc__" in url
    # Both segments present
    assert f"scene-abc__{media_id}" in url


@pytest.mark.asyncio
async def test_upload_media_isolates_by_tenant_and_kind(tmp_path, settings):
    """Two uploads, different tenants AND different kinds → keys don't
    collide. Proves the path scoping works."""
    settings.MEDIA_ROOT = str(tmp_path)

    _, url_a = await upload_media(
        data=b"a", content_type="image/png", tenant_id="tenant-a", kind="image",
    )
    _, url_b = await upload_media(
        data=b"b", content_type="video/mp4", tenant_id="tenant-b", kind="video",
    )

    assert "/maic/tenant-a/image/" in url_a
    assert "/maic/tenant-b/video/" in url_b
    assert url_a != url_b


@pytest.mark.asyncio
async def test_upload_media_rejects_empty_tenant_id():
    """Defensive: tenantless upload is a caller bug, not something to
    paper over. Raises ValueError before any IO."""
    with pytest.raises(ValueError) as exc:
        await upload_media(
            data=b"x", content_type="image/png", tenant_id="",
        )
    assert "tenant_id" in str(exc.value)


@pytest.mark.asyncio
async def test_upload_media_unknown_content_type_uploads_as_bin(tmp_path, settings):
    """Unknown content-type still uploads — just with .bin extension."""
    settings.MEDIA_ROOT = str(tmp_path)

    media_id, url = await upload_media(
        data=b"mystery", content_type="application/x-weird", tenant_id="t-1",
    )
    assert url.endswith(".bin")
    stored_key = f"maic/t-1/image/{media_id}.bin"
    assert default_storage.exists(stored_key)
