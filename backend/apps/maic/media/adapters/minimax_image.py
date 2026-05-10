"""Minimax image generation adapter — MAIC-906 (Phase 9 sibling).

Source: THU-MAIC/OpenMAIC lib/media/adapters/minimax-image-adapter.ts
        (read for HTTP contract; re-implemented in Python per ADR-001a,
        no AGPL copy). Mirrors the golden pattern at
        apps/maic/media/adapters/openai_image.py — only the parts that
        differ between OpenAI and Minimax are changed:

          1. Endpoint path:    /v1/image_generation (not /v1/images/generations)
          2. Default base URL: https://api.minimaxi.com/v1 (no trailing /v1
             added — already present)
          3. Default model:    image-01
          4. Request body:     aspect_ratio + prompt_optimizer fields;
                               no explicit size string (Minimax derives
                               width/height from the aspect ratio bucket).
          5. Response shape:   data.image_urls[0] (not data[0].url).
          6. Per-tenant key resolution falls back to MINIMAX_API_KEY
             env var when the tenant key is empty — mirrors Phase 5
             TTS at apps/maic/tts/service.py:229. The fallback is
             skipped when tenant_config exposes
             ``allow_env_key_fallback = False`` (explicit opt-out for
             enterprise tenants that require strict per-tenant keying).
          7. Minimax error envelope: even on HTTP 200, the response
             body may carry {"base_resp": {"status_code": <int>,
             "status_msg": "..."}}. Non-zero status_code is a failure;
             known auth-class codes (1004, 1008, 2049) map to
             MaicConfigError so the orchestrator does NOT retry. Other
             non-zero codes map to MaicProviderError. Source for the
             codes: Phase 5 TTS comment block at
             apps/maic/tts/service.py:380-395.

Used by:
  - apps/maic/media/orchestrator.py — calls .generate() after resolving
    this adapter via resolve_image_provider with image_provider="minimax"
  - apps/maic/media/views.py — POST /api/maic/v2/media/generate-image/

Discipline mirrors OpenAI adapter:
  - aiohttp imported lazily inside generate() so tests inject a fake
    via monkeypatch.setitem(sys.modules, "aiohttp", fake)
  - SSRF guard on tenant-supplied base_url (skipped for the default URL)
  - HTTP-class error split:
      401/403 → MaicConfigError (auth — permanent, no retry)
      429    → MaicProviderError (rate limited)
      4xx    → MaicProviderError
      5xx    → MaicProviderError
      ClientError → MaicProviderError (network)
      Parse failure → MaicProviderError
  - base_resp envelope split (200 OK but business-logic failure):
      1004 / 1008 / 2049 → MaicConfigError (auth / quota / wrong region)
      other non-zero    → MaicProviderError (transient or unknown)
  - Re-host bytes via upload_media so the URL outlives Minimax's CDN.
  - Bounded error message truncation (200 chars) so adversarial server
    responses can't blow up logs.
  - Cost estimator returns None — upstream code has no pricing table
    for Minimax image-01 (the Minimax pricing page is consulted manually).
"""
from __future__ import annotations

import logging
import os
from typing import ClassVar

from apps.maic.exceptions import MaicConfigError, MaicProviderError
from apps.maic.media.providers import MediaProviderAdapter, register_adapter
from apps.maic.media.storage import upload_media
from apps.maic.media.types import ImageGenerationRequest, ImageGenerationResult
from apps.integrations_chat.ssrf_guard import SSRFError, validate_webhook_host


logger = logging.getLogger(__name__)


# Minimax base_resp.status_code values that mean "the request will never
# succeed without operator intervention" (auth / quota class). Mapped to
# MaicConfigError so the orchestrator does NOT retry. Sourced from the
# Phase 5 TTS comment block (apps/maic/tts/service.py:380-395) — same
# account model, same error codes apply to the image endpoint.
_MINIMAX_AUTH_CLASS_CODES: frozenset[int] = frozenset({
    1004,  # account auth failed / api key revoked
    1008,  # insufficient balance — operator must top up
    2049,  # invalid api key (often wrong region — see comment below)
})


@register_adapter
class MinimaxImageAdapter(MediaProviderAdapter):
    """Minimax Images API adapter (image-01 model family).

    Reads from TenantAIConfig:
        image_api_key (decrypted) — preferred. Falls back to the
            ``MINIMAX_API_KEY`` env var if the tenant key is empty AND
            the tenant config does not set ``allow_env_key_fallback =
            False``. The fallback is the Phase 5 TTS pattern; documented
            here loudly because it surprises operators who expect strict
            per-tenant isolation.
        image_base_url — optional; defaults to api.minimaxi.com/v1.
            Three regional endpoints exist (api.minimaxi.com,
            api.minimax.chat, api.minimax.io); a key issued in one
            region returns 2049 against the others, so tenants in
            non-default regions MUST set this field.
        image_model — optional; defaults to "image-01".

    Returns an ImageGenerationResult with a URL pointing to OUR storage
    (not Minimax's CDN). The CDN URL has a short TTL.
    """

    name: ClassVar[str] = "minimax"
    kind: ClassVar = "image"
    # Minimax image-01 typical latency is 5-20s. Cap at 60s for headroom.
    default_timeout_seconds: ClassVar[int] = 60

    _DEFAULT_BASE_URL: ClassVar[str] = "https://api.minimaxi.com/v1"
    _DEFAULT_MODEL: ClassVar[str] = "image-01"
    _ENV_KEY_NAME: ClassVar[str] = "MINIMAX_API_KEY"

    async def generate(self, req: ImageGenerationRequest) -> ImageGenerationResult:
        api_key = self._require_api_key()
        base_url = self._resolved_base_url()
        model = self.tenant_config.image_model or self._DEFAULT_MODEL

        payload = {
            "model": model,
            "prompt": req.prompt,
            "aspect_ratio": _aspect_ratio_for(req.width, req.height),
            "response_format": "url",
            "n": 1,
            "prompt_optimizer": False,
        }

        # Lazy import — sys.modules patching in tests requires this.
        try:
            import aiohttp  # type: ignore[import-untyped]
        except ImportError as exc:
            raise MaicConfigError(
                "aiohttp is required for the Minimax image adapter; "
                "pip install aiohttp"
            ) from exc

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json; charset=utf-8",
        }
        endpoint = f"{base_url}/image_generation"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(endpoint, json=payload, headers=headers) as resp:
                    body_text = await resp.text()
                    self._raise_for_status(resp.status, body_text)
                    parsed = self._parse_response_json(body_text)

                # base_resp envelope check — Minimax-specific. Even on
                # HTTP 200, business-logic errors arrive as
                # base_resp.status_code != 0.
                self._check_base_resp(parsed)

                image_url = self._extract_image_url(parsed)
                content_type, image_bytes = await self._fetch_image_bytes(
                    session, image_url,
                )
        except aiohttp.ClientError as exc:
            raise MaicProviderError(
                f"minimax image: network error talking to {endpoint}: {exc}"
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
            provider="minimax",
            model=model,
            latency_ms=0,  # orchestrator stamps the real value
            cost_usd_estimate=self._estimate_cost(model, req.width, req.height, req.quality),
        )

    # ── Internals ──────────────────────────────────────────────────────

    def _require_api_key(self) -> str:
        """Resolve the API key, honouring the tenant-then-env fallback.

        Phase 5 TTS uses the same pattern (apps/maic/tts/service.py:229).
        Tenants that explicitly forbid the env fallback (enterprise
        isolation requirement) set ``allow_env_key_fallback = False``
        on their TenantAIConfig — when that attribute is set and
        falsy, we never reach for the env var.
        """
        api_key = self.tenant_config.get_image_api_key() or ""
        if api_key:
            return api_key

        # Explicit opt-out (enterprise tenants). Default behaviour is
        # "fallback enabled" — matching Phase 5 TTS.
        allow_env = getattr(self.tenant_config, "allow_env_key_fallback", True)
        if allow_env:
            env_key = os.environ.get(self._ENV_KEY_NAME, "") or ""
            if env_key:
                return env_key

        raise MaicConfigError(
            "minimax image: api_key required (set image_api_key on "
            "TenantAIConfig via set_image_api_key(), or set "
            f"{self._ENV_KEY_NAME} in the environment, or set "
            "image_provider='disabled' to skip image generation)"
        )

    def _resolved_base_url(self) -> str:
        """Pick base URL, validate with SSRF guard if customised.

        Default URL skips the guard (no point DNS-resolving our own
        known endpoint twice per call). Custom URLs MUST go through
        the guard — same rule as the OpenAI adapter."""
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
                f"minimax image: image_base_url failed SSRF check: {exc}"
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
                f"minimax image: auth failed (HTTP {status}): {snippet}"
            )
        if status == 429:
            raise MaicProviderError(
                f"minimax image: rate limited (HTTP 429): {snippet}"
            )
        if 400 <= status < 500:
            raise MaicProviderError(
                f"minimax image: client error (HTTP {status}): {snippet}"
            )
        # 5xx
        raise MaicProviderError(
            f"minimax image: server error (HTTP {status}): {snippet}"
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
                f"minimax image: malformed JSON response: {exc}"
            ) from exc

    @staticmethod
    def _check_base_resp(data: dict) -> None:
        """Minimax wraps business-logic errors in a 200 HTTP response
        with a ``base_resp`` envelope. Non-zero status_code is a failure.

        Auth-class codes (1004, 1008, 2049) → MaicConfigError so the
        orchestrator does NOT retry — these are not going to succeed
        on retry without operator action (rotate key, top up credits,
        change region).

        Other non-zero codes → MaicProviderError (could be transient
        rate limiting, server fault, etc.).
        """
        if not isinstance(data, dict):
            return
        base_resp = data.get("base_resp")
        if not isinstance(base_resp, dict):
            return
        code = base_resp.get("status_code")
        if code in (None, 0):
            return
        msg = base_resp.get("status_msg") or "unknown"
        # Bound the message — adversarial servers can inflate this.
        msg_snippet = str(msg)[:200]
        if isinstance(code, int) and code in _MINIMAX_AUTH_CLASS_CODES:
            raise MaicConfigError(
                f"minimax image: auth/quota error {code}: {msg_snippet}"
            )
        raise MaicProviderError(
            f"minimax image: provider error {code}: {msg_snippet}"
        )

    @staticmethod
    def _extract_image_url(data: dict) -> str:
        """Minimax response shape: {data: {image_urls: ['...']},
        metadata: ..., id: '...', base_resp: {...}}. We always request
        n=1 so image_urls[0] is what we want."""
        try:
            urls = data["data"]["image_urls"]
            url = urls[0]
        except (KeyError, IndexError, TypeError) as exc:
            raise MaicProviderError(
                f"minimax image: unexpected response shape: {list(data)[:5]}"
            ) from exc
        if not isinstance(url, str) or not url:
            raise MaicProviderError(
                "minimax image: response had data.image_urls[0] but it was empty"
            )
        return url

    async def _fetch_image_bytes(
        self, session, image_url: str,
    ) -> tuple[str, bytes]:
        """Download the generated image from the URL Minimax returned.

        Minimax hosts on a short-TTL CDN; always re-host immediately.
        Default content-type to image/jpeg (Minimax's typical encoding)
        if the CDN omits the header."""
        async with session.get(image_url) as img_resp:
            if img_resp.status != 200:
                raise MaicProviderError(
                    f"minimax image: failed to fetch generated image bytes "
                    f"(HTTP {img_resp.status})"
                )
            content_type = img_resp.headers.get("Content-Type", "image/jpeg")
            data = await img_resp.read()
        if not data:
            raise MaicProviderError("minimax image: fetched zero bytes")
        return content_type, data

    @staticmethod
    def _estimate_cost(model: str, width: int, height: int, quality: str) -> float | None:
        """No pricing table available for Minimax image-01 in upstream
        code. Telemetry is non-blocking — return None rather than
        fabricate a number. Operators can compute spend from the
        Minimax dashboard."""
        return None


# ── Helpers ────────────────────────────────────────────────────────────


_KNOWN_ASPECT_RATIOS: tuple[str, ...] = (
    "1:1",
    "16:9",
    "9:16",
    "4:3",
    "3:4",
    "3:2",
    "2:3",
    "21:9",
)


def _aspect_ratio_for(width: int, height: int) -> str:
    """Map (width, height) to one of Minimax's accepted aspect_ratio
    strings. Minimax derives the actual output dimensions from this
    bucket, not from an explicit size string.

    Strategy: find the known ratio whose width/height is closest to
    the requested ratio. Default to "1:1" if width == height or both
    are zero (defensive — Pydantic constraints in ImageGenerationRequest
    forbid <64 already)."""
    if width <= 0 or height <= 0 or width == height:
        return "1:1"
    target = width / height
    best_ratio = "1:1"
    best_delta = float("inf")
    for ratio in _KNOWN_ASPECT_RATIOS:
        w_str, h_str = ratio.split(":")
        w_part = int(w_str)
        h_part = int(h_str)
        candidate = w_part / h_part
        delta = abs(candidate - target)
        if delta < best_delta:
            best_delta = delta
            best_ratio = ratio
    return best_ratio
