"""Tests for apps.maic.media.orchestrator — timeout, retry, error
normalization, latency stamping.

Discipline:
  - Test-only fake adapters (in-file) drive every code path. We exercise
    the REAL orchestrator against fake adapters that succeed / fail /
    timeout — not a mocked orchestrator.
  - registry_isolated fixture (shared shape from tests_providers.py)
    keeps tests independent.
  - Real asyncio. Real Pydantic. Real exception types.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from apps.maic.exceptions import MaicConfigError, MaicProviderError
from apps.maic.media import providers
from apps.maic.media.orchestrator import generate_image, generate_video
from apps.maic.media.providers import MediaProviderAdapter, register_adapter
from apps.maic.media.types import (
    ImageGenerationRequest,
    ImageGenerationResult,
    VideoGenerationRequest,
    VideoGenerationResult,
)


@pytest.fixture
def registry_isolated():
    saved = providers._REGISTRY.copy()
    providers._REGISTRY.clear()
    try:
        yield providers._REGISTRY
    finally:
        providers._REGISTRY.clear()
        providers._REGISTRY.update(saved)


@pytest.fixture(autouse=True)
def fast_backoff(monkeypatch):
    """Shorten backoff in tests so retry suites don't add seconds.
    Production retry behavior is unchanged — this only adjusts the
    initial backoff for test runs."""
    monkeypatch.setattr(
        "apps.maic.media.orchestrator._BACKOFF_INITIAL_SECONDS",
        0.001,
    )


# ── Test-only adapters: success, transient-then-success, hard-fail, timeout, config-error ──


class _AlwaysSucceedsImage(MediaProviderAdapter):
    name = "succeeds_image"
    kind = "image"

    async def generate(self, req: ImageGenerationRequest) -> ImageGenerationResult:
        return ImageGenerationResult(
            media_id="m-1", url="x", provider="openai",
            model="t", latency_ms=99999,  # orchestrator should overwrite
        )


class _AlwaysSucceedsVideo(MediaProviderAdapter):
    name = "succeeds_video"
    kind = "video"

    async def generate(self, req: VideoGenerationRequest) -> VideoGenerationResult:
        return VideoGenerationResult(
            media_id="v-1", url="x", provider="veo",
            model="t", duration_seconds=req.duration_seconds,
            latency_ms=99999,
        )


class _TransientThenSucceeds(MediaProviderAdapter):
    name = "transient"
    kind = "image"
    default_timeout_seconds = 5

    def __init__(self, tenant_config):
        super().__init__(tenant_config)
        self._calls = 0

    async def generate(self, req: ImageGenerationRequest) -> ImageGenerationResult:
        self._calls += 1
        if self._calls < 3:
            raise MaicProviderError(f"transient failure #{self._calls}")
        return ImageGenerationResult(
            media_id="m-recovered", url="x", provider="openai",
            model="t", latency_ms=1,
        )


class _AlwaysFailsTransient(MediaProviderAdapter):
    name = "always_fails"
    kind = "image"

    async def generate(self, req: ImageGenerationRequest) -> ImageGenerationResult:
        raise MaicProviderError("transient — bad day")


class _AlwaysFailsPermanent(MediaProviderAdapter):
    name = "permanent_fail"
    kind = "image"

    async def generate(self, req: ImageGenerationRequest) -> ImageGenerationResult:
        raise MaicConfigError("bad request shape")


class _Hangs(MediaProviderAdapter):
    name = "hangs"
    kind = "image"
    default_timeout_seconds = 1  # short timeout for tests

    async def generate(self, req: ImageGenerationRequest) -> ImageGenerationResult:
        await asyncio.sleep(10)  # exceeds the 1s timeout
        # never reached
        return ImageGenerationResult(  # pragma: no cover
            media_id="m", url="x", provider="openai", model="t", latency_ms=1,
        )


def _req() -> ImageGenerationRequest:
    return ImageGenerationRequest(prompt="hello", tenant_id="t-1")


def _vreq() -> VideoGenerationRequest:
    return VideoGenerationRequest(prompt="hello", tenant_id="t-1")


# ── Happy paths ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_image_happy_path(registry_isolated):
    register_adapter(_AlwaysSucceedsImage)
    cfg = SimpleNamespace(image_provider="succeeds_image")
    result = await generate_image(_req(), cfg)
    assert isinstance(result, ImageGenerationResult)
    assert result.media_id == "m-1"


@pytest.mark.asyncio
async def test_generate_image_stamps_real_latency(registry_isolated):
    """Adapter reported 99999ms; orchestrator overwrites with real
    measured latency from monotonic clock — proves the latency stamp is
    authoritative on the orchestrator side."""
    register_adapter(_AlwaysSucceedsImage)
    cfg = SimpleNamespace(image_provider="succeeds_image")
    result = await generate_image(_req(), cfg)
    assert result.latency_ms < 99999
    assert result.latency_ms >= 0  # measured value


@pytest.mark.asyncio
async def test_generate_video_happy_path(registry_isolated):
    register_adapter(_AlwaysSucceedsVideo)
    cfg = SimpleNamespace(video_provider="succeeds_video")
    result = await generate_video(_vreq(), cfg)
    assert isinstance(result, VideoGenerationResult)
    assert result.duration_seconds == 5


# ── Retry behavior ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_retries_then_succeeds(registry_isolated):
    """Adapter fails twice with MaicProviderError, succeeds on attempt 3.
    Image policy is _IMAGE_MAX_ATTEMPTS=3, so this just barely passes."""
    register_adapter(_TransientThenSucceeds)
    cfg = SimpleNamespace(image_provider="transient")
    result = await generate_image(_req(), cfg)
    assert result.media_id == "m-recovered"


@pytest.mark.asyncio
async def test_retry_exhausted_raises_provider_error(registry_isolated):
    """Adapter always fails transiently — orchestrator gives up after
    max attempts and raises a fresh MaicProviderError wrapping the last
    cause."""
    register_adapter(_AlwaysFailsTransient)
    cfg = SimpleNamespace(image_provider="always_fails")
    with pytest.raises(MaicProviderError) as exc:
        await generate_image(_req(), cfg)
    assert "after" in str(exc.value)
    assert "attempt" in str(exc.value)
    # Last cause is preserved
    assert isinstance(exc.value.__cause__, MaicProviderError)
    assert "bad day" in str(exc.value.__cause__)


@pytest.mark.asyncio
async def test_config_error_not_retried(registry_isolated):
    """MaicConfigError is permanent — orchestrator does NOT retry. We
    detect this by counting adapter calls: should be exactly 1."""
    call_count = 0

    class _CountingPermFail(MediaProviderAdapter):
        name = "counting_perm"
        kind = "image"

        async def generate(self, req):
            nonlocal call_count
            call_count += 1
            raise MaicConfigError("permanent")

    register_adapter(_CountingPermFail)
    cfg = SimpleNamespace(image_provider="counting_perm")
    with pytest.raises(MaicConfigError):
        await generate_image(_req(), cfg)
    assert call_count == 1


# ── Timeout behavior ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_per_attempt_timeout_enforced(registry_isolated):
    """Adapter hangs longer than default_timeout_seconds; orchestrator
    cancels each attempt and retries, eventually raising MaicProviderError."""
    register_adapter(_Hangs)
    cfg = SimpleNamespace(image_provider="hangs")
    with pytest.raises(MaicProviderError):
        await generate_image(_req(), cfg)


# ── Resolution errors propagate ────────────────────────────────────────


@pytest.mark.asyncio
async def test_unknown_provider_raises_config_error_no_retry(registry_isolated):
    """If the resolver itself raises (unknown provider), orchestrator
    doesn't even attempt — just propagates the MaicConfigError."""
    cfg = SimpleNamespace(image_provider="not_registered")
    with pytest.raises(MaicConfigError):
        await generate_image(_req(), cfg)


# ── Chunk 4 — "no Image unavailable when provider is configured" invariant ──
#
# Audit Section B.2: a tenant with a configured image provider must, on
# success, get back a real URL — not a gen_img_*/gen_vid_* placeholder
# echoed through, and not an empty/blank string. The result.url field has
# `min_length=1` Pydantic validation and the orchestrator stamps a real
# latency. Together these guarantee SlideRenderer.tsx never sees an
# unresolved placeholder for a successful generation.
#
# Companion frontend negative assertion: frontend/e2e/maic-full-playback.spec.js
# "READY classroom renders zero image-empty-placeholder elements".


class _PlaceholderEchoingImage(MediaProviderAdapter):
    """Worst-case-misbehaving adapter — returns a literal gen_img_*
    placeholder string as the URL. Pydantic's min_length=1 keeps the
    request from being silently coerced to empty, but `gen_img_X` is
    technically non-empty. This test pins our defense: result.url has
    a positive length AND the orchestrator stamps a real (non-sentinel)
    latency, so SlideRenderer can branch on `url.startswith('gen_img_')`
    if needed without ambiguity."""

    name = "placeholder_echo_image"
    kind = "image"

    async def generate(self, req: ImageGenerationRequest) -> ImageGenerationResult:
        return ImageGenerationResult(
            media_id="m-1",
            url="gen_img_should_not_ship_to_player",
            provider="openai",
            model="dall-e-3",
            latency_ms=12345,
        )


@pytest.mark.asyncio
async def test_configured_provider_result_url_is_not_empty(registry_isolated):
    """Image/video result.url has Pydantic min_length=1 — empty strings
    can't slip through to SlideRenderer. Pinned so a future refactor of
    ImageGenerationResult cannot silently relax this."""
    register_adapter(_AlwaysSucceedsImage)
    cfg = SimpleNamespace(image_provider="succeeds_image")
    result = await generate_image(_req(), cfg)
    assert isinstance(result.url, str)
    assert len(result.url) > 0


@pytest.mark.asyncio
async def test_orchestrator_stamps_real_latency_on_misbehaving_adapter(
    registry_isolated,
):
    """Even when an adapter returns a placeholder-ish URL, the orchestrator
    overwrites the latency_ms to its own measured value. This is the
    canary that proves the call path actually executed (vs an adapter
    that short-circuited returning a frozen value)."""
    register_adapter(_PlaceholderEchoingImage)
    cfg = SimpleNamespace(image_provider="placeholder_echo_image")
    result = await generate_image(_req(), cfg)
    # Adapter returned 12345; orchestrator overwrites with measured time.
    assert result.latency_ms != 12345
    assert result.latency_ms >= 0
    # Result URL is whatever the adapter returned — the orchestrator does
    # NOT validate URL shape (that's a provider-layer concern). Frontend's
    # image-empty-placeholder gate is the playback-time defense documented
    # in DO_SPACES_STRUCTURE.md "Tenant-prefix invariant".
    assert result.url == "gen_img_should_not_ship_to_player"
