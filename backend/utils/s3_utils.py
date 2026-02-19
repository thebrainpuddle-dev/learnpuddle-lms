# utils/s3_utils.py
"""
Single source of truth for generating signed S3/DO Spaces URLs.

All serializers should call `sign_url()` or `sign_file_field()` instead of
duplicating presign logic.
"""

import logging
from urllib.parse import urlparse

from django.conf import settings
from django.core.files.storage import default_storage

logger = logging.getLogger(__name__)


def _extract_s3_key(url_or_path: str, bucket_name: str) -> str:
    """
    Extract the pure S3 object key from any URL format we might have stored.

    Handles:
      1. CDN URL  : https://bucket.region.cdn.digitaloceanspaces.com/key
      2. Origin URL: https://region.digitaloceanspaces.com/bucket/key
      3. Absolute path: /media/key  or /key
      4. Bare key : tenant/xxx/file.mp4
    """
    if not url_or_path:
        return ""

    if url_or_path.startswith("http"):
        parsed = urlparse(url_or_path)
        key = parsed.path.lstrip("/")
    elif url_or_path.startswith("/"):
        key = url_or_path.lstrip("/")
    else:
        key = url_or_path

    # Strip bucket-name prefix that appears in origin-format URLs
    # e.g. "learnpuddle-media/tenant/..." -> "tenant/..."
    if bucket_name and key.startswith(f"{bucket_name}/"):
        key = key[len(bucket_name) + 1:]

    return key


def sign_url(url_or_path: str, expires_in: int = 14400) -> str:
    """
    Given any stored URL or S3 key, return a pre-signed S3 URL.

    Returns the original value unchanged when:
      - storage backend is not S3
      - url_or_path is empty
      - signing fails for any reason
    """
    if not url_or_path:
        return ""

    storage_backend = getattr(settings, "STORAGE_BACKEND", "local").lower()
    if storage_backend != "s3":
        return url_or_path

    try:
        storage = default_storage
        client = storage.connection.meta.client
        bucket_name = storage.bucket_name

        key = _extract_s3_key(url_or_path, bucket_name)
        if not key:
            return url_or_path

        return client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket_name, "Key": key},
            ExpiresIn=expires_in,
        )
    except Exception:
        logger.exception("Failed to sign URL: %s", url_or_path)
        return url_or_path


def sign_file_field(file_field, expires_in: int = 86400) -> str | None:
    """
    Generate a signed URL from a Django FileField / FieldFile.

    Uses the field's `.name` attribute which is the pure S3 key,
    avoiding all URL-parsing issues.

    Returns None if the field is empty.
    """
    if not file_field:
        return None

    storage_backend = getattr(settings, "STORAGE_BACKEND", "local").lower()
    if storage_backend != "s3":
        return file_field.url

    try:
        storage = default_storage
        client = storage.connection.meta.client
        bucket_name = storage.bucket_name

        return client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket_name, "Key": file_field.name},
            ExpiresIn=expires_in,
        )
    except Exception:
        logger.exception("Failed to sign file field: %s", file_field.name)
        return file_field.url
