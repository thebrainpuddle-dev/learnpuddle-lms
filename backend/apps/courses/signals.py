# apps/courses/signals.py

import logging

from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import Content

logger = logging.getLogger(__name__)


@receiver(post_delete, sender=Content)
def cleanup_content_files(sender, instance, **kwargs):
    """Remove associated files when content is deleted."""
    file_url = getattr(instance, 'file_url', None)
    if not file_url:
        return

    # Only attempt deletion for storage-backed paths (not external URLs).
    # S3/storage-backed files typically start with the configured media prefix
    # or a relative path, while external links start with http(s).
    if file_url.startswith('http://') or file_url.startswith('https://'):
        # External URL -- check if it's our own storage URL
        from django.conf import settings
        storage_endpoint = getattr(settings, 'STORAGE_ENDPOINT', '') or ''
        storage_bucket = getattr(settings, 'STORAGE_BUCKET', '') or ''
        is_own_storage = (
            (storage_endpoint and storage_endpoint in file_url)
            or (storage_bucket and storage_bucket in file_url)
        )
        if not is_own_storage:
            return  # External link, nothing to clean up

    try:
        from django.core.files.storage import default_storage
        # Extract the storage key from the URL if needed
        storage_key = file_url
        # If it's a full URL to our storage, extract the path portion
        if storage_key.startswith('http'):
            from urllib.parse import urlparse
            parsed = urlparse(storage_key)
            storage_key = parsed.path.lstrip('/')

        if default_storage.exists(storage_key):
            default_storage.delete(storage_key)
            logger.info(
                "Deleted file %s for content %s", storage_key, instance.id
            )
    except Exception:
        logger.warning(
            "Failed to delete file %s for content %s",
            file_url,
            instance.id,
            exc_info=True,
        )
