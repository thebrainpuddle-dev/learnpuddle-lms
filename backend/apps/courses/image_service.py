"""
Image service for AI Studio — fetches real stock photos for lesson scenes.

Supports multiple providers with automatic fallback:
    1. Unsplash (UNSPLASH_ACCESS_KEY)
    2. Pexels (PEXELS_API_KEY)
    3. Pollinations.ai (free AI image generation, no API key needed)
    4. Placeholder (placehold.co — always available, no key needed)

Usage:
    from apps.courses.image_service import fetch_scene_image

    url = fetch_scene_image("classroom engagement")
    # Returns a real stock photo URL, or a placeholder if no API key is configured

    # With storage (saves Pollinations-generated images to DO Spaces/local):
    url = fetch_scene_image(
        "classroom engagement",
        tenant_id="abc123",
        lesson_id="def456",
        scene_index=0,
    )
"""

import logging
import os
import tempfile
from urllib.parse import quote

import requests
from django.core.files.storage import default_storage

logger = logging.getLogger(__name__)

# Timeout for stock photo API calls (seconds)
_API_TIMEOUT = 12

# Timeout for Pollinations.ai (generates images, takes longer)
_POLLINATIONS_TIMEOUT = 30

# Image dimensions
_WIDTH = 800
_HEIGHT = 450

# Pollinations dimensions (16:9, slightly larger for AI generation quality)
_POLLINATIONS_WIDTH = 1024
_POLLINATIONS_HEIGHT = 576


def fetch_scene_image(
    keyword: str,
    tenant_id: str | None = None,
    lesson_id: str | None = None,
    scene_index: int | None = None,
) -> str:
    """
    Fetch or generate an image URL for the given keyword.

    Tries providers in order: Unsplash → Pexels → Pollinations.ai → placeholder.
    Returns a URL string (never None).

    When tenant_id, lesson_id, and scene_index are provided, Pollinations-
    generated images are saved to the configured storage backend (DO Spaces
    or local filesystem) and a persistent storage URL is returned.

    Args:
        keyword: Search term / prompt for the image.
        tenant_id: Optional tenant UUID for storage path.
        lesson_id: Optional lesson UUID for storage path.
        scene_index: Optional scene index for storage path.

    Returns:
        URL string pointing to the image.
    """
    keyword = (keyword or "").strip()
    if not keyword:
        return f"https://placehold.co/{_WIDTH}x{_HEIGHT}?text=No+keyword"

    # Try Unsplash
    unsplash_key = os.getenv("UNSPLASH_ACCESS_KEY", "").strip()
    if unsplash_key:
        url = _fetch_unsplash(keyword, unsplash_key)
        if url:
            return url

    # Try Pexels
    pexels_key = os.getenv("PEXELS_API_KEY", "").strip()
    if pexels_key:
        url = _fetch_pexels(keyword, pexels_key)
        if url:
            return url

    # Try Pollinations.ai (free AI image generation)
    url = _fetch_pollinations(keyword, tenant_id, lesson_id, scene_index)
    if url:
        return url

    # Fallback to placeholder
    encoded = quote(keyword, safe="")
    return f"https://placehold.co/{_WIDTH}x{_HEIGHT}?text={encoded}"


def _fetch_unsplash(keyword: str, api_key: str) -> str | None:
    """Fetch a landscape photo from Unsplash."""
    try:
        resp = requests.get(
            "https://api.unsplash.com/search/photos",
            params={
                "query": keyword,
                "per_page": 1,
                "orientation": "landscape",
                "content_filter": "high",  # safe for education
            },
            headers={
                "Authorization": f"Client-ID {api_key}",
                "Accept-Version": "v1",
            },
            timeout=_API_TIMEOUT,
        )
        if resp.status_code == 200:
            results = resp.json().get("results", [])
            if results:
                # Use 'regular' size (1080px wide, good balance of quality/speed)
                url = results[0].get("urls", {}).get("regular")
                if url:
                    logger.info("Unsplash: found image for '%s'", keyword)
                    return url
        else:
            logger.warning(
                "Unsplash API error: HTTP %d for '%s'",
                resp.status_code, keyword,
            )
    except Exception as e:
        logger.warning("Unsplash fetch failed for '%s': %s", keyword, e)
    return None


def _fetch_pexels(keyword: str, api_key: str) -> str | None:
    """Fetch a landscape photo from Pexels."""
    try:
        resp = requests.get(
            "https://api.pexels.com/v1/search",
            params={
                "query": keyword,
                "per_page": 1,
                "orientation": "landscape",
                "size": "medium",
            },
            headers={"Authorization": api_key},
            timeout=_API_TIMEOUT,
        )
        if resp.status_code == 200:
            photos = resp.json().get("photos", [])
            if photos:
                # Use 'large' size (good quality, reasonable file size)
                url = photos[0].get("src", {}).get("large")
                if url:
                    logger.info("Pexels: found image for '%s'", keyword)
                    return url
        else:
            logger.warning(
                "Pexels API error: HTTP %d for '%s'",
                resp.status_code, keyword,
            )
    except Exception as e:
        logger.warning("Pexels fetch failed for '%s': %s", keyword, e)
    return None


def _fetch_pollinations(
    keyword: str,
    tenant_id: str | None = None,
    lesson_id: str | None = None,
    scene_index: int | None = None,
) -> str | None:
    """
    Generate an AI image via Pollinations.ai (free, no API key required).

    The API generates an image from a text prompt and returns it as binary
    data. If storage parameters are provided, the image is saved to the
    configured Django storage backend (DO Spaces / local filesystem) and a
    persistent URL is returned. Otherwise, the direct Pollinations URL is
    returned (which may be ephemeral).

    Args:
        keyword: The image prompt / search term.
        tenant_id: Optional tenant UUID for storage path.
        lesson_id: Optional lesson UUID for storage path.
        scene_index: Optional scene index for storage path.

    Returns:
        A storage URL if saved, a direct Pollinations URL as fallback,
        or None on failure.
    """
    # Build an educational prompt for better results
    prompt = f"Educational illustration of: {keyword}"
    encoded_prompt = quote(prompt, safe="")

    pollinations_url = (
        f"https://image.pollinations.ai/prompt/{encoded_prompt}"
        f"?width={_POLLINATIONS_WIDTH}"
        f"&height={_POLLINATIONS_HEIGHT}"
        f"&nologo=true"
        f"&model=flux"
    )

    try:
        resp = requests.get(
            pollinations_url,
            timeout=_POLLINATIONS_TIMEOUT,
            stream=True,
        )

        if resp.status_code != 200:
            logger.warning(
                "Pollinations.ai error: HTTP %d for '%s'",
                resp.status_code, keyword,
            )
            return None

        # Check we got an image (not an error page)
        content_type = resp.headers.get("Content-Type", "")
        if "image" not in content_type and "octet-stream" not in content_type:
            logger.warning(
                "Pollinations.ai returned non-image Content-Type '%s' for '%s'",
                content_type, keyword,
            )
            return None

        # Read image bytes
        image_bytes = resp.content
        if not image_bytes or len(image_bytes) < 1000:
            logger.warning(
                "Pollinations.ai returned suspiciously small response "
                "(%d bytes) for '%s'",
                len(image_bytes) if image_bytes else 0, keyword,
            )
            return None

        logger.info(
            "Pollinations.ai: generated image for '%s' (%d bytes)",
            keyword, len(image_bytes),
        )

        # Save to storage if we have enough context
        can_save = tenant_id and lesson_id and scene_index is not None
        if can_save:
            return _save_pollinations_image(
                image_bytes, tenant_id, lesson_id, scene_index,
            )

        # If we can't save to storage, return the direct URL (ephemeral but
        # still usable as a direct link since Pollinations caches results)
        return pollinations_url

    except requests.exceptions.Timeout:
        logger.warning(
            "Pollinations.ai timed out after %ds for '%s'",
            _POLLINATIONS_TIMEOUT, keyword,
        )
        return None
    except requests.exceptions.ConnectionError as e:
        logger.warning("Pollinations.ai connection error for '%s': %s", keyword, e)
        return None
    except Exception as e:
        logger.warning("Pollinations.ai fetch failed for '%s': %s", keyword, e)
        return None


def _save_pollinations_image(
    image_bytes: bytes,
    tenant_id: str,
    lesson_id: str,
    scene_index: int,
) -> str | None:
    """
    Save Pollinations-generated image bytes to Django's default storage.

    Returns the storage URL on success, or None on failure.
    """
    from utils.storage_paths import ai_studio_lesson_scene_image_path

    storage_key = ai_studio_lesson_scene_image_path(
        tenant_id, lesson_id, scene_index,
    )

    try:
        # Write to a temp file, then save to storage
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp.write(image_bytes)
            tmp_path = tmp.name

        try:
            with open(tmp_path, "rb") as f:
                # Overwrite if a previous attempt left a file
                if default_storage.exists(storage_key):
                    default_storage.delete(storage_key)
                default_storage.save(storage_key, f)
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass

        image_url = default_storage.url(storage_key)
        logger.info(
            "Pollinations.ai: saved image to storage at %s", storage_key,
        )
        return image_url

    except Exception as e:
        logger.warning(
            "Pollinations.ai: failed to save image to storage: %s", e,
        )
        return None
