"""
Image service for AI Studio — fetches or generates images for lesson scenes.

Provider fallback chain (premium first, free last):
    1. Imagen 4.0 (GOOGLE_AI_API_KEY) — Google's best image model
    2. Nano Banana Pro (GOOGLE_AI_API_KEY) — Gemini native image generation
    3. Unsplash (UNSPLASH_ACCESS_KEY) — stock photos
    4. Pexels (PEXELS_API_KEY) — stock photos
    5. Pollinations.ai (free, no key) — AI image generation
    6. Placeholder (placehold.co — always available)

Usage:
    from apps.courses.image_service import fetch_scene_image

    url = fetch_scene_image("classroom engagement")

    # With storage (saves generated images to DO Spaces/local):
    url = fetch_scene_image(
        "classroom engagement",
        tenant_id="abc123",
        lesson_id="def456",
        scene_index=0,
    )
"""

import base64
import logging
import os
import tempfile
from urllib.parse import quote

import requests
from decouple import config
from django.core.files.storage import default_storage

logger = logging.getLogger(__name__)


def _get_api_key(name: str) -> str:
    """Resolve an API key from .env (via python-decouple, which reads
    backend/.env at call time) with a fallback to process env vars for
    container deployments that inject env directly.

    The codebase's Django settings use `config(...)` throughout — raw
    `os.getenv()` misses keys that only exist in .env and never make it
    into os.environ, which is how we ended up shipping with Imagen
    silently skipped on local dev.
    """
    try:
        value = config(name, default="").strip()
    except Exception:
        value = ""
    if not value:
        value = os.getenv(name, "").strip()
    return value

# Timeouts (seconds)
_API_TIMEOUT = 12
_GOOGLE_AI_TIMEOUT = 30
_POLLINATIONS_TIMEOUT = 30

# Image dimensions
_WIDTH = 800
_HEIGHT = 450
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

    Tries premium providers first, then free fallbacks.
    Returns a URL string (never None).
    """
    keyword = (keyword or "").strip()
    if not keyword:
        return f"https://placehold.co/{_WIDTH}x{_HEIGHT}?text=No+keyword"

    can_save = tenant_id and lesson_id and scene_index is not None

    # 1. Imagen 4.0 (premium)
    google_key = _get_api_key("GOOGLE_AI_API_KEY")
    if google_key:
        image_bytes = _fetch_imagen(keyword, google_key)
        if image_bytes:
            if can_save:
                url = _save_image_to_storage(image_bytes, tenant_id, lesson_id, scene_index, "imagen")
                if url:
                    return url
            return _bytes_to_data_url(image_bytes)

        # 2. Nano Banana Pro (premium fallback)
        image_bytes = _fetch_nano_banana(keyword, google_key)
        if image_bytes:
            if can_save:
                url = _save_image_to_storage(image_bytes, tenant_id, lesson_id, scene_index, "nanobanana")
                if url:
                    return url
            return _bytes_to_data_url(image_bytes)

    # 3. Unsplash (stock photos)
    unsplash_key = _get_api_key("UNSPLASH_ACCESS_KEY")
    if unsplash_key:
        url = _fetch_unsplash(keyword, unsplash_key)
        if url:
            return url

    # 4. Pexels (stock photos)
    pexels_key = _get_api_key("PEXELS_API_KEY")
    if pexels_key:
        url = _fetch_pexels(keyword, pexels_key)
        if url:
            return url

    # 5. Pollinations.ai (free AI generation)
    url = _fetch_pollinations(keyword, tenant_id, lesson_id, scene_index)
    if url:
        return url

    # 6. Placeholder (always works)
    encoded = quote(keyword, safe="")
    return f"https://placehold.co/{_WIDTH}x{_HEIGHT}?text={encoded}"


# ─── Premium: Google AI ──────────────────────────────────────────────────────

def _fetch_imagen(keyword: str, api_key: str) -> bytes | None:
    """Generate an image via Google Imagen 4.0."""
    prompt = f"Educational illustration for a classroom lesson: {keyword}. Clean, professional, suitable for students."
    try:
        resp = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/imagen-4.0-generate-001:predict?key={api_key}",
            headers={"Content-Type": "application/json"},
            json={
                "instances": [{"prompt": prompt}],
                "parameters": {"sampleCount": 1, "aspectRatio": "16:9"},
            },
            timeout=_GOOGLE_AI_TIMEOUT,
        )
        if resp.status_code == 200:
            predictions = resp.json().get("predictions", [])
            if predictions and predictions[0].get("bytesBase64Encoded"):
                image_bytes = base64.b64decode(predictions[0]["bytesBase64Encoded"])
                if len(image_bytes) > 1000:
                    logger.info("Imagen 4.0: generated image for '%s' (%d bytes)", keyword, len(image_bytes))
                    return image_bytes
        else:
            logger.warning("Imagen 4.0 error: HTTP %d for '%s'", resp.status_code, keyword)
    except Exception as e:
        logger.warning("Imagen 4.0 failed for '%s': %s", keyword, e)
    return None


def _fetch_nano_banana(keyword: str, api_key: str) -> bytes | None:
    """Generate an image via Nano Banana Pro (Gemini native image generation)."""
    prompt = f"Generate an educational illustration for: {keyword}. Clean, colorful, suitable for a classroom presentation."
    try:
        resp = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/nano-banana-pro-preview:generateContent?key={api_key}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]},
            },
            timeout=_GOOGLE_AI_TIMEOUT,
        )
        if resp.status_code == 200:
            parts = resp.json().get("candidates", [{}])[0].get("content", {}).get("parts", [])
            for part in parts:
                inline = part.get("inlineData")
                if inline and inline.get("data"):
                    image_bytes = base64.b64decode(inline["data"])
                    if len(image_bytes) > 1000:
                        logger.info("Nano Banana: generated image for '%s' (%d bytes)", keyword, len(image_bytes))
                        return image_bytes
        else:
            logger.warning("Nano Banana error: HTTP %d for '%s'", resp.status_code, keyword)
    except Exception as e:
        logger.warning("Nano Banana failed for '%s': %s", keyword, e)
    return None


# ─── Stock Photos ────────────────────────────────────────────────────────────

def _fetch_unsplash(keyword: str, api_key: str) -> str | None:
    """Fetch a landscape photo from Unsplash."""
    try:
        resp = requests.get(
            "https://api.unsplash.com/search/photos",
            params={
                "query": keyword,
                "per_page": 1,
                "orientation": "landscape",
                "content_filter": "high",
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
                url = results[0].get("urls", {}).get("regular")
                if url:
                    logger.info("Unsplash: found image for '%s'", keyword)
                    return url
        else:
            logger.warning("Unsplash API error: HTTP %d for '%s'", resp.status_code, keyword)
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
                url = photos[0].get("src", {}).get("large")
                if url:
                    logger.info("Pexels: found image for '%s'", keyword)
                    return url
        else:
            logger.warning("Pexels API error: HTTP %d for '%s'", resp.status_code, keyword)
    except Exception as e:
        logger.warning("Pexels fetch failed for '%s': %s", keyword, e)
    return None


# ─── Free Fallbacks ──────────────────────────────────────────────────────────

def _fetch_pollinations(
    keyword: str,
    tenant_id: str | None = None,
    lesson_id: str | None = None,
    scene_index: int | None = None,
) -> str | None:
    """Generate an AI image via Pollinations.ai (free, no API key required)."""
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
        resp = requests.get(pollinations_url, timeout=_POLLINATIONS_TIMEOUT, stream=True)

        if resp.status_code != 200:
            logger.warning("Pollinations.ai error: HTTP %d for '%s'", resp.status_code, keyword)
            return None

        content_type = resp.headers.get("Content-Type", "")
        if "image" not in content_type and "octet-stream" not in content_type:
            logger.warning("Pollinations.ai returned non-image Content-Type '%s' for '%s'", content_type, keyword)
            return None

        image_bytes = resp.content
        if not image_bytes or len(image_bytes) < 1000:
            logger.warning("Pollinations.ai returned small response (%d bytes) for '%s'", len(image_bytes) if image_bytes else 0, keyword)
            return None

        logger.info("Pollinations.ai: generated image for '%s' (%d bytes)", keyword, len(image_bytes))

        can_save = tenant_id and lesson_id and scene_index is not None
        if can_save:
            url = _save_image_to_storage(image_bytes, tenant_id, lesson_id, scene_index, "pollinations")
            if url:
                return url

        return pollinations_url

    except requests.exceptions.Timeout:
        logger.warning("Pollinations.ai timed out after %ds for '%s'", _POLLINATIONS_TIMEOUT, keyword)
        return None
    except requests.exceptions.ConnectionError as e:
        logger.warning("Pollinations.ai connection error for '%s': %s", keyword, e)
        return None
    except Exception as e:
        logger.warning("Pollinations.ai fetch failed for '%s': %s", keyword, e)
        return None


# ─── Storage Helpers ─────────────────────────────────────────────────────────

def _save_image_to_storage(
    image_bytes: bytes,
    tenant_id: str,
    lesson_id: str,
    scene_index: int,
    provider: str,
) -> str | None:
    """Save generated image bytes to Django's default storage. Returns URL or None."""
    from utils.storage_paths import ai_studio_lesson_scene_image_path

    storage_key = ai_studio_lesson_scene_image_path(tenant_id, lesson_id, scene_index)

    try:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp.write(image_bytes)
            tmp_path = tmp.name

        try:
            with open(tmp_path, "rb") as f:
                if default_storage.exists(storage_key):
                    default_storage.delete(storage_key)
                default_storage.save(storage_key, f)
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass

        image_url = default_storage.url(storage_key)
        logger.info("%s: saved image to storage at %s", provider, storage_key)
        return image_url

    except Exception as e:
        logger.warning("%s: failed to save image to storage: %s", provider, e)
        return None


def _bytes_to_data_url(image_bytes: bytes) -> str:
    """Convert raw image bytes to a base64 data URL for inline display."""
    b64 = base64.b64encode(image_bytes).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"
