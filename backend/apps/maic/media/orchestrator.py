"""Async orchestrator — wraps adapter calls with timeout + retry + telemetry.

Source: THU-MAIC/OpenMAIC lib/media/media-orchestrator.ts (read for retry
        + fallback pattern; re-implemented in async Python per ADR-001a).
        Phase 5 TTS provider-fallback chain is the closest backend
        precedent (apps/maic/tts/service.py).

Used by:
  - apps/maic/media/views.py — POST /api/maic/v2/media/generate-*/
  - apps/maic/generation/scene_builder.py — resolves ``gen_img_<id>``
    placeholders during outline generation (MAIC-915 wires this in)

Discipline:
  - Bounded total time per request (per-attempt timeout × attempts +
    backoff). Even a misbehaving adapter cannot hang the director loop.
  - Retry only on MaicProviderError (transient). MaicConfigError is
    permanent — surface immediately.
  - Latency measured at the orchestrator, not the adapter — so retries
    are NOT counted in the reported latency (only the successful attempt
    contributes).
  - On final failure, surface a MaicProviderError with a structured
    message; the caller (view / generation pipeline) decides whether to
    fall back to a placeholder or propagate.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from apps.maic.exceptions import MaicConfigError, MaicProviderError
from apps.maic.media.providers import (
    MediaProviderAdapter,
    resolve_image_provider,
    resolve_video_provider,
)
from apps.maic.media.types import (
    ImageGenerationRequest,
    ImageGenerationResult,
    VideoGenerationRequest,
    VideoGenerationResult,
)


logger = logging.getLogger(__name__)


# Retry policy constants — tuned per provider kind. Conservative on
# purpose: media generation is expensive, and retry-storms are worse
# than a single failure surfaced to the user.
_IMAGE_MAX_ATTEMPTS = 3       # 1 initial + 2 retries
_VIDEO_MAX_ATTEMPTS = 2       # 1 initial + 1 retry — videos are expensive
_BACKOFF_INITIAL_SECONDS = 1.0
_BACKOFF_FACTOR = 2.0


# ── Public API ────────────────────────────────────────────────────────


async def generate_image(
    req: ImageGenerationRequest,
    tenant_config,
) -> ImageGenerationResult:
    """Generate one image for the given tenant. Resolves provider from
    tenant_config, runs with bounded retry, returns the result.

    Raises:
        MaicConfigError: provider missing/disabled, request invalid,
            adapter init failed. NOT retried — permanent.
        MaicProviderError: all retry attempts failed. Wraps the last
            provider error in its ``__cause__``.
    """
    adapter = resolve_image_provider(tenant_config)
    return await _run_with_retry(
        adapter=adapter,
        req=req,
        max_attempts=_IMAGE_MAX_ATTEMPTS,
    )


async def generate_video(
    req: VideoGenerationRequest,
    tenant_config,
) -> VideoGenerationResult:
    """Generate one video for the given tenant. Same retry shape as
    images but only 1 retry (videos are 10-30x more expensive per call)."""
    adapter = resolve_video_provider(tenant_config)
    return await _run_with_retry(
        adapter=adapter,
        req=req,
        max_attempts=_VIDEO_MAX_ATTEMPTS,
    )


# ── Internals ─────────────────────────────────────────────────────────


async def _run_with_retry(
    adapter: MediaProviderAdapter,
    req: Any,
    max_attempts: int,
) -> Any:
    """Wrap one adapter call with timeout-per-attempt and bounded retries.

    Timing:
      - Each attempt is wrapped in asyncio.timeout(adapter.default_timeout_seconds)
      - Between attempts: exponential backoff (1s, 2s, 4s, ...)
      - Latency reported in the result is from the SUCCESSFUL attempt only

    Errors:
      - MaicConfigError: permanent — raise immediately, no retry
      - MaicProviderError: transient — retry until max_attempts
      - asyncio.TimeoutError: treated as transient; wrapped in MaicProviderError

    On final failure, raises MaicProviderError with the last cause in __cause__.
    """
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        start_ts = time.monotonic()
        try:
            async with asyncio.timeout(adapter.default_timeout_seconds):
                result = await adapter.generate(req)

            # Stamp latency from the successful attempt only
            latency_ms = int((time.monotonic() - start_ts) * 1000)
            try:
                # Result is a Pydantic model — model_copy preserves immutability
                result = result.model_copy(update={"latency_ms": latency_ms})
            except AttributeError:
                # Defensive: if the adapter returned a non-Pydantic object,
                # log loud and let the type system surface the bug downstream.
                logger.error(
                    "adapter %s returned non-Pydantic result of type %s",
                    adapter.name, type(result).__name__,
                )
            return result

        except MaicConfigError:
            # Permanent — do not retry. Propagate up unchanged.
            raise

        except asyncio.TimeoutError as exc:
            last_error = exc
            logger.warning(
                "media generation timed out: provider=%s kind=%s attempt=%d/%d "
                "timeout=%ds",
                adapter.name, adapter.kind, attempt, max_attempts,
                adapter.default_timeout_seconds,
            )

        except MaicProviderError as exc:
            last_error = exc
            logger.warning(
                "media generation failed: provider=%s kind=%s attempt=%d/%d "
                "error=%s",
                adapter.name, adapter.kind, attempt, max_attempts, str(exc),
            )

        # Bail before sleeping if this was the final attempt
        if attempt >= max_attempts:
            break

        backoff = _BACKOFF_INITIAL_SECONDS * (_BACKOFF_FACTOR ** (attempt - 1))
        await asyncio.sleep(backoff)

    # All attempts exhausted
    raise MaicProviderError(
        f"media generation failed after {max_attempts} attempt(s): "
        f"provider={adapter.name} kind={adapter.kind}; "
        f"last error: {last_error}",
    ) from last_error
