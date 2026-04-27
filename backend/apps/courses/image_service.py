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
import time
from threading import Lock
from urllib.parse import quote

import requests
from decouple import config
from django.core.files.storage import default_storage

from apps.courses._log_helpers import MAICPhase, log_extra

# TEST-P1-10: Prometheus counter for image-fetch outcomes per provider.
from utils.metrics import maic_image_fetch_total

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


# ─── Circuit Breaker (per-provider rate-limit cooldown) ──────────────────────
#
# CG-P0-4: when a provider returns 429 or 5xx we must stop hitting it for a
# while, otherwise a single 429 on scene 1 → next scene hits the same provider
# → more 429s → paid-tier budget incinerated on deploy day.
#
# Design notes:
# - State is an in-process module-level dict keyed on provider name. Each
#   worker process keeps its own breaker; that's fine for round 1 — a Gunicorn
#   pool of ~8 workers × a 30s cooldown still bounds request rate per
#   provider dramatically, and avoids a hard Redis dependency on the image
#   path. If we ever see workers desynchronise badly under load, promote
#   this to Redis (keys like `image_service:cooling:<provider>`).
# - Cooldown ladder is exponential (30s, 60s, 120s, 240s, 480s, 900s cap).
# - `Retry-After` header on a 429 overrides the ladder (capped at 15min).
# - Success (HTTP 200 with usable payload) clears the failure count AND the
#   cooldown — this is the half-open → closed transition.
# - State transitions are logged at WARNING so ops can grep for provider
#   degradation.
_CIRCUIT_STATE: dict[str, dict[str, float]] = {}
_CIRCUIT_LOCK = Lock()

_COOLDOWN_LADDER_SECONDS = (30, 60, 120, 240, 480, 900)
_COOLDOWN_MAX_SECONDS = 900  # 15 minutes


def _now() -> float:
    """Monotonic-ish wall clock for circuit-breaker timing.

    Indirected so tests can monkeypatch `image_service._now` to freeze time
    without needing freezegun.
    """
    return time.time()


def _is_provider_cooling(provider: str) -> bool:
    """Return True iff `provider` is currently within its cooldown window."""
    with _CIRCUIT_LOCK:
        state = _CIRCUIT_STATE.get(provider)
        if not state:
            return False
        return state.get("cooling_until", 0.0) > _now()


def _mark_provider_failure(provider: str, retry_after: float | None = None) -> None:
    """Record a rate-limit / 5xx failure and set the cooldown window.

    Args:
        provider: provider name (matches dict key).
        retry_after: if the response carried a `Retry-After` header, the
            parsed seconds value. Overrides the exponential ladder (still
            capped at 15min).
    """
    with _CIRCUIT_LOCK:
        state = _CIRCUIT_STATE.setdefault(provider, {"failure_count": 0.0, "cooling_until": 0.0})
        was_closed = state.get("cooling_until", 0.0) <= _now()
        state["failure_count"] = state.get("failure_count", 0.0) + 1
        idx = min(int(state["failure_count"]) - 1, len(_COOLDOWN_LADDER_SECONDS) - 1)
        ladder_seconds = _COOLDOWN_LADDER_SECONDS[idx]
        if retry_after is not None and retry_after > 0:
            cooldown = min(float(retry_after), float(_COOLDOWN_MAX_SECONDS))
            source = "Retry-After"
        else:
            cooldown = float(ladder_seconds)
            source = "ladder"
        state["cooling_until"] = _now() + cooldown
        transition = "closed→open" if was_closed else "open→open(extended)"
        logger.warning(
            "image_service circuit breaker %s for provider=%s cooldown=%.0fs source=%s failure_count=%d",
            transition,
            provider,
            cooldown,
            source,
            int(state["failure_count"]),
            extra=log_extra(
                MAICPhase.IMAGE_FETCH,
                metric="circuit_breaker_open",
                outcome=transition,
                provider=provider,
                cooldown_seconds=int(cooldown),
                source=source,
                failure_count=int(state["failure_count"]),
            ),
        )


def _mark_provider_success(provider: str) -> None:
    """Reset the circuit for `provider` after a successful fetch."""
    with _CIRCUIT_LOCK:
        state = _CIRCUIT_STATE.get(provider)
        if not state:
            return
        was_open = state.get("cooling_until", 0.0) > _now() or state.get("failure_count", 0.0) > 0
        if was_open:
            logger.warning(
                "image_service circuit breaker open→closed for provider=%s (success after %d failures)",
                provider,
                int(state.get("failure_count", 0.0)),
                extra=log_extra(
                    MAICPhase.IMAGE_FETCH,
                    metric="circuit_breaker_closed",
                    outcome="open_to_closed",
                    provider=provider,
                    failure_count=int(state.get("failure_count", 0.0)),
                ),
            )
        state["failure_count"] = 0.0
        state["cooling_until"] = 0.0


def _parse_retry_after(value: str | None) -> float | None:
    """Parse a `Retry-After` header. Only supports the delta-seconds form
    (the HTTP-date form is rare for API rate-limits and not worth the
    dateutil dep). Returns None on any parse failure.
    """
    if not value:
        return None
    try:
        seconds = float(value.strip())
    except (TypeError, ValueError):
        return None
    if seconds < 0:
        return None
    return seconds


def reset_circuit_breaker_state() -> None:
    """Test helper — clear every provider's breaker state. Not called from
    production code.
    """
    with _CIRCUIT_LOCK:
        _CIRCUIT_STATE.clear()


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
        # TEST-P1-10: empty keyword → deterministic placeholder; record so
        # we can spot a regression that starts feeding empty keywords in.
        maic_image_fetch_total.labels(
            provider="placeholder", outcome="placeholder"
        ).inc()
        return f"https://placehold.co/{_WIDTH}x{_HEIGHT}?text=No+keyword"

    can_save = tenant_id and lesson_id and scene_index is not None

    # CG-P0-4: figure out which providers are currently "available" (not in
    # a cooldown window). If ALL of them are cooling, short-circuit to the
    # deterministic placeholder — do not sit in the cascade burning further
    # HTTP calls. Each provider's availability also depends on its API key.
    google_key = _get_api_key("GOOGLE_AI_API_KEY")
    unsplash_key = _get_api_key("UNSPLASH_ACCESS_KEY")
    pexels_key = _get_api_key("PEXELS_API_KEY")

    availability = {
        "imagen": bool(google_key) and not _is_provider_cooling("imagen"),
        "nanobanana": bool(google_key) and not _is_provider_cooling("nanobanana"),
        "unsplash": bool(unsplash_key) and not _is_provider_cooling("unsplash"),
        "pexels": bool(pexels_key) and not _is_provider_cooling("pexels"),
        "pollinations": not _is_provider_cooling("pollinations"),
    }
    any_provider_configured = bool(google_key or unsplash_key or pexels_key) or True  # pollinations always configured
    all_cooling = any_provider_configured and not any(availability.values())
    if all_cooling:
        logger.warning(
            "image_service all providers cooling; returning placeholder for '%s'",
            keyword,
            extra=log_extra(
                MAICPhase.IMAGE_FETCH,
                metric="all_providers_cooling",
                outcome="placeholder",
                keyword_len=len(keyword),
            ),
        )
        # TEST-P1-10: count one "cooling" sample per cooling provider so the
        # dashboard shows which providers contributed to the short-circuit.
        for provider_name, available in availability.items():
            if not available and _is_provider_cooling(provider_name):
                maic_image_fetch_total.labels(
                    provider=provider_name, outcome="cooling"
                ).inc()
        # Sentinel for the aggregate event itself.
        maic_image_fetch_total.labels(
            provider="all", outcome="cooling"
        ).inc()
        encoded = quote(keyword, safe="")
        return f"https://placehold.co/{_WIDTH}x{_HEIGHT}?text={encoded}"

    # 1. Imagen 4.0 (premium)
    if availability["imagen"]:
        image_bytes = _fetch_imagen(keyword, google_key)
        if image_bytes:
            maic_image_fetch_total.labels(provider="imagen", outcome="ok").inc()
            if can_save:
                url = _save_image_to_storage(image_bytes, tenant_id, lesson_id, scene_index, "imagen")
                if url:
                    return url
            return _bytes_to_data_url(image_bytes)
        else:
            # Provider returned None — counted as error; the breaker cooldown
            # handles backoff, the counter just records the per-call signal.
            maic_image_fetch_total.labels(provider="imagen", outcome="error").inc()

    # 2. Nano Banana Pro (premium fallback)
    if availability["nanobanana"]:
        image_bytes = _fetch_nano_banana(keyword, google_key)
        if image_bytes:
            maic_image_fetch_total.labels(provider="nanobanana", outcome="ok").inc()
            if can_save:
                url = _save_image_to_storage(image_bytes, tenant_id, lesson_id, scene_index, "nanobanana")
                if url:
                    return url
            return _bytes_to_data_url(image_bytes)
        else:
            maic_image_fetch_total.labels(provider="nanobanana", outcome="error").inc()

    # 3. Unsplash (stock photos)
    if availability["unsplash"]:
        url = _fetch_unsplash(keyword, unsplash_key)
        if url:
            maic_image_fetch_total.labels(provider="unsplash", outcome="ok").inc()
            return url
        else:
            maic_image_fetch_total.labels(provider="unsplash", outcome="error").inc()

    # 4. Pexels (stock photos)
    if availability["pexels"]:
        url = _fetch_pexels(keyword, pexels_key)
        if url:
            maic_image_fetch_total.labels(provider="pexels", outcome="ok").inc()
            return url
        else:
            maic_image_fetch_total.labels(provider="pexels", outcome="error").inc()

    # 5. Pollinations.ai (free AI generation)
    if availability["pollinations"]:
        url = _fetch_pollinations(keyword, tenant_id, lesson_id, scene_index)
        if url:
            maic_image_fetch_total.labels(provider="pollinations", outcome="ok").inc()
            return url
        else:
            maic_image_fetch_total.labels(provider="pollinations", outcome="error").inc()

    # 6. Placeholder (always works) — every provider failed or was unavailable.
    maic_image_fetch_total.labels(provider="placeholder", outcome="placeholder").inc()
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
                    logger.info(
                        "Imagen 4.0: generated image for '%s' (%d bytes)",
                        keyword, len(image_bytes),
                        extra=log_extra(
                            MAICPhase.IMAGE_FETCH,
                            metric="image_fetch_success",
                            outcome="success",
                            provider="imagen",
                            keyword_len=len(keyword),
                            bytes=len(image_bytes),
                        ),
                    )
                    _mark_provider_success("imagen")
                    return image_bytes
        elif resp.status_code == 429 or resp.status_code >= 500:
            logger.warning(
                "Imagen 4.0 error: HTTP %d for '%s'",
                resp.status_code, keyword,
                extra=log_extra(
                    MAICPhase.IMAGE_FETCH,
                    metric="image_fetch_error",
                    outcome="rate_limited" if resp.status_code == 429 else "server_error",
                    provider="imagen",
                    status_code=resp.status_code,
                    keyword_len=len(keyword),
                ),
            )
            retry_after = _parse_retry_after(resp.headers.get("Retry-After"))
            _mark_provider_failure("imagen", retry_after=retry_after)
        else:
            logger.warning(
                "Imagen 4.0 error: HTTP %d for '%s'",
                resp.status_code, keyword,
                extra=log_extra(
                    MAICPhase.IMAGE_FETCH,
                    metric="image_fetch_error",
                    outcome="http_error",
                    provider="imagen",
                    status_code=resp.status_code,
                    keyword_len=len(keyword),
                ),
            )
    except Exception as e:
        logger.warning(
            "Imagen 4.0 failed for '%s': %s",
            keyword, e,
            extra=log_extra(
                MAICPhase.IMAGE_FETCH,
                metric="image_fetch_error",
                outcome="exception",
                provider="imagen",
                keyword_len=len(keyword),
                error_type=type(e).__name__,
            ),
        )
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
                        logger.info(
                            "Nano Banana: generated image for '%s' (%d bytes)",
                            keyword, len(image_bytes),
                            extra=log_extra(
                                MAICPhase.IMAGE_FETCH,
                                metric="image_fetch_success",
                                outcome="success",
                                provider="nanobanana",
                                keyword_len=len(keyword),
                                bytes=len(image_bytes),
                            ),
                        )
                        _mark_provider_success("nanobanana")
                        return image_bytes
        elif resp.status_code == 429 or resp.status_code >= 500:
            logger.warning(
                "Nano Banana error: HTTP %d for '%s'",
                resp.status_code, keyword,
                extra=log_extra(
                    MAICPhase.IMAGE_FETCH,
                    metric="image_fetch_error",
                    outcome="rate_limited" if resp.status_code == 429 else "server_error",
                    provider="nanobanana",
                    status_code=resp.status_code,
                    keyword_len=len(keyword),
                ),
            )
            retry_after = _parse_retry_after(resp.headers.get("Retry-After"))
            _mark_provider_failure("nanobanana", retry_after=retry_after)
        else:
            logger.warning(
                "Nano Banana error: HTTP %d for '%s'",
                resp.status_code, keyword,
                extra=log_extra(
                    MAICPhase.IMAGE_FETCH,
                    metric="image_fetch_error",
                    outcome="http_error",
                    provider="nanobanana",
                    status_code=resp.status_code,
                    keyword_len=len(keyword),
                ),
            )
    except Exception as e:
        logger.warning(
            "Nano Banana failed for '%s': %s",
            keyword, e,
            extra=log_extra(
                MAICPhase.IMAGE_FETCH,
                metric="image_fetch_error",
                outcome="exception",
                provider="nanobanana",
                keyword_len=len(keyword),
                error_type=type(e).__name__,
            ),
        )
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
                    logger.info(
                        "Unsplash: found image for '%s'",
                        keyword,
                        extra=log_extra(
                            MAICPhase.IMAGE_FETCH,
                            metric="image_fetch_success",
                            outcome="success",
                            provider="unsplash",
                            keyword_len=len(keyword),
                        ),
                    )
                    _mark_provider_success("unsplash")
                    return url
        elif resp.status_code == 429 or resp.status_code >= 500:
            logger.warning(
                "Unsplash API error: HTTP %d for '%s'",
                resp.status_code, keyword,
                extra=log_extra(
                    MAICPhase.IMAGE_FETCH,
                    metric="image_fetch_error",
                    outcome="rate_limited" if resp.status_code == 429 else "server_error",
                    provider="unsplash",
                    status_code=resp.status_code,
                    keyword_len=len(keyword),
                ),
            )
            retry_after = _parse_retry_after(resp.headers.get("Retry-After"))
            _mark_provider_failure("unsplash", retry_after=retry_after)
        else:
            logger.warning(
                "Unsplash API error: HTTP %d for '%s'",
                resp.status_code, keyword,
                extra=log_extra(
                    MAICPhase.IMAGE_FETCH,
                    metric="image_fetch_error",
                    outcome="http_error",
                    provider="unsplash",
                    status_code=resp.status_code,
                    keyword_len=len(keyword),
                ),
            )
    except Exception as e:
        logger.warning(
            "Unsplash fetch failed for '%s': %s",
            keyword, e,
            extra=log_extra(
                MAICPhase.IMAGE_FETCH,
                metric="image_fetch_error",
                outcome="exception",
                provider="unsplash",
                keyword_len=len(keyword),
                error_type=type(e).__name__,
            ),
        )
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
                    logger.info(
                        "Pexels: found image for '%s'",
                        keyword,
                        extra=log_extra(
                            MAICPhase.IMAGE_FETCH,
                            metric="image_fetch_success",
                            outcome="success",
                            provider="pexels",
                            keyword_len=len(keyword),
                        ),
                    )
                    _mark_provider_success("pexels")
                    return url
        elif resp.status_code == 429 or resp.status_code >= 500:
            logger.warning(
                "Pexels API error: HTTP %d for '%s'",
                resp.status_code, keyword,
                extra=log_extra(
                    MAICPhase.IMAGE_FETCH,
                    metric="image_fetch_error",
                    outcome="rate_limited" if resp.status_code == 429 else "server_error",
                    provider="pexels",
                    status_code=resp.status_code,
                    keyword_len=len(keyword),
                ),
            )
            retry_after = _parse_retry_after(resp.headers.get("Retry-After"))
            _mark_provider_failure("pexels", retry_after=retry_after)
        else:
            logger.warning(
                "Pexels API error: HTTP %d for '%s'",
                resp.status_code, keyword,
                extra=log_extra(
                    MAICPhase.IMAGE_FETCH,
                    metric="image_fetch_error",
                    outcome="http_error",
                    provider="pexels",
                    status_code=resp.status_code,
                    keyword_len=len(keyword),
                ),
            )
    except Exception as e:
        logger.warning(
            "Pexels fetch failed for '%s': %s",
            keyword, e,
            extra=log_extra(
                MAICPhase.IMAGE_FETCH,
                metric="image_fetch_error",
                outcome="exception",
                provider="pexels",
                keyword_len=len(keyword),
                error_type=type(e).__name__,
            ),
        )
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
            logger.warning(
                "Pollinations.ai error: HTTP %d for '%s'",
                resp.status_code, keyword,
                extra=log_extra(
                    MAICPhase.IMAGE_FETCH,
                    metric="image_fetch_error",
                    outcome=(
                        "rate_limited" if resp.status_code == 429
                        else ("server_error" if resp.status_code >= 500 else "http_error")
                    ),
                    provider="pollinations",
                    status_code=resp.status_code,
                    keyword_len=len(keyword),
                ),
            )
            if resp.status_code == 429 or resp.status_code >= 500:
                retry_after = _parse_retry_after(resp.headers.get("Retry-After"))
                _mark_provider_failure("pollinations", retry_after=retry_after)
            return None

        content_type = resp.headers.get("Content-Type", "")
        if "image" not in content_type and "octet-stream" not in content_type:
            logger.warning(
                "Pollinations.ai returned non-image Content-Type '%s' for '%s'",
                content_type, keyword,
                extra=log_extra(
                    MAICPhase.IMAGE_FETCH,
                    metric="image_fetch_error",
                    outcome="bad_content_type",
                    provider="pollinations",
                    content_type=content_type[:80],
                    keyword_len=len(keyword),
                ),
            )
            return None

        image_bytes = resp.content
        if not image_bytes or len(image_bytes) < 1000:
            logger.warning(
                "Pollinations.ai returned small response (%d bytes) for '%s'",
                len(image_bytes) if image_bytes else 0, keyword,
                extra=log_extra(
                    MAICPhase.IMAGE_FETCH,
                    metric="image_fetch_error",
                    outcome="response_too_small",
                    provider="pollinations",
                    bytes=len(image_bytes) if image_bytes else 0,
                    keyword_len=len(keyword),
                ),
            )
            return None

        logger.info(
            "Pollinations.ai: generated image for '%s' (%d bytes)",
            keyword, len(image_bytes),
            extra=log_extra(
                MAICPhase.IMAGE_FETCH,
                metric="image_fetch_success",
                outcome="success",
                provider="pollinations",
                keyword_len=len(keyword),
                bytes=len(image_bytes),
            ),
        )
        _mark_provider_success("pollinations")

        can_save = tenant_id and lesson_id and scene_index is not None
        if can_save:
            url = _save_image_to_storage(image_bytes, tenant_id, lesson_id, scene_index, "pollinations")
            if url:
                return url

        return pollinations_url

    except requests.exceptions.Timeout:
        logger.warning(
            "Pollinations.ai timed out after %ds for '%s'",
            _POLLINATIONS_TIMEOUT, keyword,
            extra=log_extra(
                MAICPhase.IMAGE_FETCH,
                metric="image_fetch_error",
                outcome="timeout",
                provider="pollinations",
                timeout_seconds=_POLLINATIONS_TIMEOUT,
                keyword_len=len(keyword),
            ),
        )
        return None
    except requests.exceptions.ConnectionError as e:
        logger.warning(
            "Pollinations.ai connection error for '%s': %s",
            keyword, e,
            extra=log_extra(
                MAICPhase.IMAGE_FETCH,
                metric="image_fetch_error",
                outcome="connection_error",
                provider="pollinations",
                keyword_len=len(keyword),
                error_type=type(e).__name__,
            ),
        )
        return None
    except Exception as e:
        logger.warning(
            "Pollinations.ai fetch failed for '%s': %s",
            keyword, e,
            extra=log_extra(
                MAICPhase.IMAGE_FETCH,
                metric="image_fetch_error",
                outcome="exception",
                provider="pollinations",
                keyword_len=len(keyword),
                error_type=type(e).__name__,
            ),
        )
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
        logger.info(
            "%s: saved image to storage at %s",
            provider, storage_key,
            extra=log_extra(
                MAICPhase.IMAGE_FETCH,
                metric="image_storage_save",
                outcome="success",
                provider=provider,
                storage_key=storage_key,
            ),
        )
        return image_url

    except Exception as e:
        logger.warning(
            "%s: failed to save image to storage: %s",
            provider, e,
            extra=log_extra(
                MAICPhase.IMAGE_FETCH,
                metric="image_storage_save",
                outcome="error",
                provider=provider,
                error_type=type(e).__name__,
            ),
        )
        return None


def _bytes_to_data_url(image_bytes: bytes) -> str:
    """Convert raw image bytes to a base64 data URL for inline display."""
    b64 = base64.b64encode(image_bytes).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"
