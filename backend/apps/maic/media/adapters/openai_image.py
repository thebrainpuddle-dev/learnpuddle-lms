"""OpenAI image generation adapter — the Phase 9 reference implementation.

Source: THU-MAIC/OpenMAIC lib/media/adapters/openai-image-adapter.ts
        (read for API contract; re-implemented in Python per ADR-001a).
        Phase 5 Minimax TTS adapter (apps/maic/tts/service.py) sets the
        lazy-aiohttp-import + bounded-timeout + structured-error pattern
        we mirror here.

THE GOLDEN PATTERN. MAIC-904 through MAIC-913 (the 10 sibling adapters)
copy this file's shape. Sub-agents implementing those tickets receive
this file as their reference. If something here is unclear or wrong,
the bug replicates ×10 — so the contract is documented loud, the
error handling is exhaustive, and every path is tested.

Used by:
  - apps/maic/media/orchestrator.py — calls .generate() after resolving
    this adapter from the registry
  - apps/maic/media/views.py — POST /api/maic/v2/media/generate-image/

Discipline:
  - aiohttp imported lazily inside generate() so tests can inject a
    fake via monkeypatch.setitem(sys.modules, "aiohttp", fake) — exact
    pattern Phase 5 Minimax uses (apps/maic/tests_tts_service.py).
  - SSRF guard on tenant-supplied base_url (skipped when using the
    default OpenAI URL to save a DNS round-trip).
  - Errors split by HTTP class:
      401/403 → MaicConfigError (auth — permanent, no retry)
      429    → MaicProviderError (rate limited — retry)
      4xx    → MaicProviderError (other 4xx; could be transient)
      5xx    → MaicProviderError (server fault — retry)
      ClientError → MaicProviderError (network — retry)
      Parse failure → MaicProviderError (server returned bad shape)
  - Cost estimate computed from the pricing table at module top; if
    the model isn't in the table, returns None (we don't fail the
    request on missing cost info — telemetry is non-blocking).
"""
from __future__ import annotations

import logging
from typing import ClassVar

from apps.maic.exceptions import MaicConfigError, MaicProviderError
from apps.maic.media.providers import MediaProviderAdapter, register_adapter
from apps.maic.media.storage import upload_media
from apps.maic.media.types import ImageGenerationRequest, ImageGenerationResult
from apps.integrations_chat.ssrf_guard import SSRFError, validate_webhook_host


logger = logging.getLogger(__name__)


# DALL-E 3 list prices as of 2025-Q4 (public pricing page). Estimates
# only — actual billing may include credits / discounts the adapter
# cannot see. Returns None when model is unknown.
_DALLE3_PRICES_USD: dict[tuple[str, str], float] = {
    # (size_bucket, quality) → $/image
    ("standard", "standard"): 0.04,
    ("standard", "high"):     0.08,
    ("wide", "standard"):     0.08,   # 1792x1024 / 1024x1792
    ("wide", "high"):         0.12,
}


@register_adapter
class OpenAIImageAdapter(MediaProviderAdapter):
    """OpenAI Images API adapter (DALL-E 3 / gpt-image-1).

    Reads from TenantAIConfig:
        image_api_key (decrypted) — required; MaicConfigError if missing
        image_base_url — optional; defaults to api.openai.com
        image_model — optional; defaults to "dall-e-3"

    Returns an ImageGenerationResult with a URL pointing to OUR storage
    (not OpenAI's). We always re-host the generated image so it doesn't
    disappear when OpenAI rotates their CDN URLs (their URLs expire).
    """

    name: ClassVar[str] = "openai"
    kind: ClassVar = "image"
    # DALL-E 3 typical latency is 10-25s end-to-end. Cap at 60s for headroom.
    default_timeout_seconds: ClassVar[int] = 60

    _DEFAULT_BASE_URL: ClassVar[str] = "https://api.openai.com/v1"
    _DEFAULT_MODEL: ClassVar[str] = "dall-e-3"

    async def generate(self, req: ImageGenerationRequest) -> ImageGenerationResult:
        api_key = self._require_api_key()
        base_url = self._resolved_base_url()
        model = self.tenant_config.image_model or self._DEFAULT_MODEL

        payload = {
            "model": model,
            "prompt": req.prompt,
            "n": 1,
            "size": f"{req.width}x{req.height}",
            "quality": req.quality,
            "response_format": "url",
        }

        # Lazy import — sys.modules patching in tests requires this. If
        # we imported aiohttp at the top of the module, tests couldn't
        # inject a fake.
        try:
            import aiohttp  # type: ignore[import-untyped]
        except ImportError as exc:
            raise MaicConfigError(
                "aiohttp is required for the OpenAI image adapter; "
                "pip install aiohttp"
            ) from exc

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        endpoint = f"{base_url}/images/generations"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(endpoint, json=payload, headers=headers) as resp:
                    body_text = await resp.text()
                    self._raise_for_status(resp.status, body_text)
                    parsed = self._parse_response_json(body_text)

                image_url = self._extract_image_url(parsed)
                content_type, image_bytes = await self._fetch_image_bytes(
                    session, image_url,
                )
        except aiohttp.ClientError as exc:
            # DNS failure, connection reset, etc. — orchestrator will retry.
            raise MaicProviderError(
                f"openai image: network error talking to {endpoint}: {exc}"
            ) from exc

        # Re-host the image in our storage so the URL outlives OpenAI's CDN TTL.
        media_id, stored_url = await upload_media(
            data=image_bytes,
            content_type=content_type,
            tenant_id=req.tenant_id,
            kind="image",
            scene_id=req.scene_id,
        )

        return ImageGenerationResult(
            media_id=media_id,
            url=stored_url,
            provider="openai",
            model=model,
            latency_ms=0,  # orchestrator stamps the real value
            cost_usd_estimate=self._estimate_cost(model, req.width, req.height, req.quality),
        )

    # ── Internals ──────────────────────────────────────────────────────

    def _require_api_key(self) -> str:
        api_key = self.tenant_config.get_image_api_key()
        if not api_key:
            raise MaicConfigError(
                "openai image: api_key required (set image_api_key on "
                "TenantAIConfig via set_image_api_key()), or set "
                "image_provider='disabled' to skip image generation"
            )
        return api_key

    def _resolved_base_url(self) -> str:
        """Pick base URL, validate with SSRF guard if customised.

        We skip the SSRF check when the URL is the default — that's a
        well-known public endpoint, no need to DNS-resolve it twice
        per request. Custom URLs (self-hosted proxies, regional
        endpoints) MUST go through the guard."""
        raw = (self.tenant_config.image_base_url or "").strip()
        if not raw:
            return self._DEFAULT_BASE_URL.rstrip("/")
        base = raw.rstrip("/")
        if base == self._DEFAULT_BASE_URL.rstrip("/"):
            return base
        try:
            validate_webhook_host(base)
        except SSRFError as exc:
            raise MaicConfigError(
                f"openai image: image_base_url failed SSRF check: {exc}"
            ) from exc
        return base

    @staticmethod
    def _raise_for_status(status: int, body: str) -> None:
        """Translate HTTP status into typed exceptions."""
        if 200 <= status < 300:
            return
        snippet = body[:200] if body else ""
        if status in (401, 403):
            raise MaicConfigError(
                f"openai image: auth failed (HTTP {status}): {snippet}"
            )
        if status == 429:
            raise MaicProviderError(
                f"openai image: rate limited (HTTP 429): {snippet}"
            )
        if 400 <= status < 500:
            # Other 4xx — could be invalid prompt, content policy violation,
            # etc. Treat as transient; orchestrator retries with same input
            # are unlikely to succeed but the bound is small (2-3 attempts).
            raise MaicProviderError(
                f"openai image: client error (HTTP {status}): {snippet}"
            )
        # 5xx
        raise MaicProviderError(
            f"openai image: server error (HTTP {status}): {snippet}"
        )

    @staticmethod
    def _parse_response_json(body: str) -> dict:
        """Defensive JSON parse — raise MaicProviderError on malformed
        body so the orchestrator can retry."""
        import json
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise MaicProviderError(
                f"openai image: malformed JSON response: {exc}"
            ) from exc

    @staticmethod
    def _extract_image_url(data: dict) -> str:
        """OpenAI's response shape: {created: ts, data: [{url: '...'}, ...]}.
        We always request n=1 so data[0] is what we want."""
        try:
            url = data["data"][0]["url"]
        except (KeyError, IndexError, TypeError) as exc:
            raise MaicProviderError(
                f"openai image: unexpected response shape: {list(data)[:5]}"
            ) from exc
        if not isinstance(url, str) or not url:
            raise MaicProviderError(
                "openai image: response had data[0].url but it was empty"
            )
        return url

    async def _fetch_image_bytes(
        self, session, image_url: str,
    ) -> tuple[str, bytes]:
        """Download the generated image from the URL OpenAI returned.

        OpenAI hosts images on a short-TTL CDN (typically 60 minutes),
        so we always re-host immediately. The returned content_type
        comes from the CDN response header; default to image/png if
        absent."""
        async with session.get(image_url) as img_resp:
            if img_resp.status != 200:
                raise MaicProviderError(
                    f"openai image: failed to fetch generated image bytes "
                    f"(HTTP {img_resp.status})"
                )
            content_type = img_resp.headers.get("Content-Type", "image/png")
            data = await img_resp.read()
        if not data:
            raise MaicProviderError("openai image: fetched zero bytes")
        return content_type, data

    @staticmethod
    def _estimate_cost(model: str, width: int, height: int, quality: str) -> float | None:
        """DALL-E 3 list price. None for gpt-image-1 (token-priced) or
        unknown models."""
        if model != "dall-e-3":
            return None
        # Size bucket: 1024×1024 (and below) is "standard"; 1792×1024 /
        # 1024×1792 is "wide". Other sizes return None (not in price table).
        if width <= 1024 and height <= 1024:
            bucket = "standard"
        elif {width, height} == {1024, 1792}:
            bucket = "wide"
        else:
            return None
        return _DALLE3_PRICES_USD.get((bucket, quality))
