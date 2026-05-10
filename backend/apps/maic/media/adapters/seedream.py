"""Seedream (ByteDance / Doubao / Ark) image generation adapter — MAIC-908.

Source: THU-MAIC/OpenMAIC lib/media/adapters/seedream-adapter.ts (read for
        API contract; re-implemented in Python per ADR-001a).
Golden pattern: apps/maic/media/adapters/openai_image.py (MAIC-903).

Seedream uses an OpenAI-compatible synchronous Images API on the Volcengine
"Ark" platform. Auth is the SIMPLE form — a Bearer token (the platform API
key) in the Authorization header — NOT Volcengine SigV4 request signing.
(Volcengine SigV4 signing is required by some other Volcengine product
APIs but Ark's Bearer-token surface is what the upstream TS adapter and
the official Volcengine docs use for this endpoint.) That means structurally
this adapter is the OpenAI image adapter with:
  - different default base URL (ark.cn-beijing.volces.com)
  - different default model (doubao-seedream-5-0-260128)
  - different endpoint path suffix (/api/v3/images/generations)
  - response can include either `url` or `b64_json`; we handle both
  - no list-price cost estimator (Seedream pricing is contract-private)

Used by:
  - apps/maic/media/orchestrator.py — calls .generate() after resolving
  - apps/maic/media/views.py — POST /api/maic/v2/media/generate-image/

Discipline (mirrors MAIC-903):
  - aiohttp lazy import for monkeypatch.setitem(sys.modules, ...) testing
  - SSRF guard on tenant-supplied base_url (default URL skips the check)
  - HTTP status → typed exception (401/403→Config, 429/4xx/5xx→Provider)
  - Bounded error message truncation (200 chars)
  - Re-host bytes via upload_media so storage URL outlives Ark CDN TTL
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


@register_adapter
class SeedreamImageAdapter(MediaProviderAdapter):
    """Seedream (ByteDance Doubao / Ark) Images API adapter.

    Reads from TenantAIConfig:
        image_api_key (decrypted) — required; MaicConfigError if missing
        image_base_url — optional; defaults to ark.cn-beijing.volces.com
        image_model — optional; defaults to "doubao-seedream-5-0-260128"

    Returns an ImageGenerationResult with a URL pointing to OUR storage
    (not Ark's CDN). Ark image URLs have a short TTL like OpenAI's, so
    we always re-host immediately.

    Cost estimate is always None — Seedream/Doubao pricing is contract-
    private and varies by tenant agreement with Volcengine. Telemetry
    is non-blocking, so a missing cost is fine.
    """

    name: ClassVar[str] = "seedream"
    kind: ClassVar = "image"
    # Seedream end-to-end latency is comparable to DALL-E 3 (10-25s typical);
    # 60s leaves headroom for the larger 2K outputs the model supports.
    default_timeout_seconds: ClassVar[int] = 60

    _DEFAULT_BASE_URL: ClassVar[str] = "https://ark.cn-beijing.volces.com"
    _DEFAULT_MODEL: ClassVar[str] = "doubao-seedream-5-0-260128"
    # Seedream minimum total pixels per the upstream TS adapter. Below this,
    # we send the requested W×H verbatim — the upstream behaviour is to
    # scale up, but we prefer to honour caller-supplied dims and let the
    # provider 4xx if it rejects (caller can fix the request).
    _MIN_PIXELS: ClassVar[int] = 3_686_400

    async def generate(self, req: ImageGenerationRequest) -> ImageGenerationResult:
        api_key = self._require_api_key()
        base_url = self._resolved_base_url()
        model = self.tenant_config.image_model or self._DEFAULT_MODEL

        payload = {
            "model": model,
            "prompt": req.prompt,
            "size": f"{req.width}x{req.height}",
            # No watermark on the returned image (we re-host so attribution
            # lives in our DB, not stamped into pixels).
            "watermark": False,
        }

        # Lazy import — sys.modules patching in tests requires this.
        try:
            import aiohttp  # type: ignore[import-untyped]
        except ImportError as exc:
            raise MaicConfigError(
                "aiohttp is required for the Seedream image adapter; "
                "pip install aiohttp"
            ) from exc

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        endpoint = f"{base_url}/api/v3/images/generations"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(endpoint, json=payload, headers=headers) as resp:
                    body_text = await resp.text()
                    self._raise_for_status(resp.status, body_text)
                    parsed = self._parse_response_json(body_text)

                content_type, image_bytes = await self._extract_image_bytes(
                    session, parsed,
                )
        except aiohttp.ClientError as exc:
            raise MaicProviderError(
                f"seedream image: network error talking to {endpoint}: {exc}"
            ) from exc

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
            provider="seedream",
            model=model,
            latency_ms=0,  # orchestrator stamps the real value
            cost_usd_estimate=None,  # Seedream pricing is contract-private
        )

    # ── Internals ──────────────────────────────────────────────────────

    def _require_api_key(self) -> str:
        api_key = self.tenant_config.get_image_api_key()
        if not api_key:
            raise MaicConfigError(
                "seedream image: api_key required (set image_api_key on "
                "TenantAIConfig via set_image_api_key()), or set "
                "image_provider='disabled' to skip image generation"
            )
        return api_key

    def _resolved_base_url(self) -> str:
        """Pick base URL, validate with SSRF guard if customised.

        Default URL (Ark public endpoint) skips the SSRF check — known
        public host, no need to DNS-resolve it twice per request. Custom
        URLs (regional endpoints, self-hosted gateways) MUST go through
        the guard."""
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
                f"seedream image: image_base_url failed SSRF check: {exc}"
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
                f"seedream image: auth failed (HTTP {status}): {snippet}"
            )
        if status == 429:
            raise MaicProviderError(
                f"seedream image: rate limited (HTTP 429): {snippet}"
            )
        if 400 <= status < 500:
            raise MaicProviderError(
                f"seedream image: client error (HTTP {status}): {snippet}"
            )
        raise MaicProviderError(
            f"seedream image: server error (HTTP {status}): {snippet}"
        )

    @staticmethod
    def _parse_response_json(body: str) -> dict:
        """Defensive JSON parse — raise MaicProviderError on malformed body."""
        import json
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise MaicProviderError(
                f"seedream image: malformed JSON response: {exc}"
            ) from exc

    async def _extract_image_bytes(
        self, session, parsed: dict,
    ) -> tuple[str, bytes]:
        """Seedream's response shape is OpenAI-compatible:
            {data: [{url: '...'} or {b64_json: '...'}]}

        We accept either form. URL is the common case (handled like
        OpenAI: GET the URL, return bytes). b64_json is a fallback for
        when the caller asked for inline bytes — decode and return."""
        try:
            entry = parsed["data"][0]
        except (KeyError, IndexError, TypeError) as exc:
            raise MaicProviderError(
                f"seedream image: unexpected response shape: {list(parsed)[:5]}"
            ) from exc

        if not isinstance(entry, dict):
            raise MaicProviderError(
                "seedream image: response data[0] was not an object"
            )

        url = entry.get("url")
        b64 = entry.get("b64_json")

        if isinstance(url, str) and url:
            return await self._fetch_image_bytes(session, url)
        if isinstance(b64, str) and b64:
            import base64
            try:
                data = base64.b64decode(b64, validate=True)
            except (ValueError, TypeError) as exc:
                raise MaicProviderError(
                    f"seedream image: malformed b64_json in response: {exc}"
                ) from exc
            if not data:
                raise MaicProviderError("seedream image: b64_json decoded to zero bytes")
            # Seedream b64_json is typically PNG; default to that. Caller-
            # supplied content type would be nicer but the API doesn't
            # include it inline.
            return "image/png", data

        raise MaicProviderError(
            "seedream image: response had no url or b64_json in data[0]"
        )

    async def _fetch_image_bytes(
        self, session, image_url: str,
    ) -> tuple[str, bytes]:
        """Download the generated image from the URL Seedream returned.

        Ark image URLs are short-TTL CDN URLs (like OpenAI's), so we
        always re-host. content_type comes from the CDN response header;
        default to image/png if absent."""
        async with session.get(image_url) as img_resp:
            if img_resp.status != 200:
                raise MaicProviderError(
                    f"seedream image: failed to fetch generated image bytes "
                    f"(HTTP {img_resp.status})"
                )
            content_type = img_resp.headers.get("Content-Type", "image/png")
            data = await img_resp.read()
        if not data:
            raise MaicProviderError("seedream image: fetched zero bytes")
        return content_type, data
