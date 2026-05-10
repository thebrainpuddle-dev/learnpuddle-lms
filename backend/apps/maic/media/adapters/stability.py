"""Stability AI image generation adapter — MAIC-909 (Phase 9 sibling).

Source: Stability AI public API docs (https://platform.stability.ai/docs/api-reference)
        — NOT in upstream OpenMAIC. This is our addition for the
        LearnPuddle MAIC v2 stack. Re-implemented in Python following the
        golden pattern at apps/maic/media/adapters/openai_image.py
        (MAIC-903) — same class shape, same SSRF guard, same error matrix,
        same upload_media re-host.

Key deltas vs the OpenAI golden pattern:
  - Endpoint: POST {base}/v2beta/stable-image/generate/sd3 (Stability's
    "modern" v2beta surface). The path is parameterised by model family
    but we default to /sd3 which accepts the model= form-field; for /core
    and /ultra the model field is ignored by Stability so a tenant who
    wants those would change image_model AND we'd hit /sd3 anyway. The
    model param drives quality there.
  - Content type: multipart/form-data via aiohttp.FormData (NOT JSON).
    Stability's v2beta accepts ONLY multipart — application/json is
    rejected with a 400.
  - Accept header: ``image/*`` — Stability honours this by returning the
    raw image bytes directly in the response body (no JSON wrapping,
    no second GET). When Accept is application/json it returns a base64-
    encoded blob; we don't use that path because direct bytes is one
    less hop.
  - Response handler: read bytes from the response body when
    Content-Type is image/*. On error (4xx/5xx) the body is JSON with
    {name: "bad_request", errors: ["..."]}; we surface that.
  - Aspect ratio: derived from req.width × req.height via the helper
    `_aspect_ratio_for`. Stability's v2beta accepts ONE of the fixed
    strings; we snap to the closest. Default 1024×1024 → "1:1".
  - Output format: png (default; can be jpeg/webp). We always request
    png so the re-hosted bytes match what callers expect from siblings.

Discipline mirrors OpenAI adapter:
  - aiohttp lazy import inside generate() so tests inject a fake via
    monkeypatch.setitem(sys.modules, "aiohttp", fake)
  - SSRF guard on tenant-supplied base_url (skipped for the default URL)
  - HTTP status → typed exception (401/403→Config, 429/4xx/5xx→Provider)
  - Bounded error message truncation (200 chars)
  - Re-host bytes via upload_media — Stability does not host returned
    images at all (bytes come back inline), but the re-host step is
    still what gives the caller a stable URL on our storage backend
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


# Stability SD3.5 family list prices as of 2025-Q4 (public pricing page,
# expressed in credits @ $1/100 credits). Estimates only — actual billing
# is from Stability's credit ledger. Returns None for unknown models.
#   sd3.5-large         → 6.5 credits → $0.065 / image
#   sd3.5-large-turbo   → 4   credits → $0.04  / image
#   sd3.5-medium        → 3.5 credits → $0.035 / image
_STABILITY_SD35_PRICES_USD: dict[str, float] = {
    "sd3.5-large": 0.065,
    "sd3.5-large-turbo": 0.04,
    "sd3.5-medium": 0.035,
}


@register_adapter
class StabilityImageAdapter(MediaProviderAdapter):
    """Stability AI v2beta Images API adapter (SD3.5 family).

    Reads from TenantAIConfig:
        image_api_key (decrypted) — required; MaicConfigError if missing.
        image_base_url — optional; defaults to https://api.stability.ai.
        image_model — optional; defaults to "sd3.5-large".

    Returns an ImageGenerationResult with a URL pointing to OUR storage.
    Unlike OpenAI/Grok/Seedream/Minimax (which return URLs to their CDN
    that we then GET), Stability returns raw image bytes inline when we
    set ``Accept: image/*`` — saves one HTTP hop.
    """

    name: ClassVar[str] = "stability"
    kind: ClassVar = "image"
    # SD3.5-large typical latency is 10-30s. Cap at 60s for headroom —
    # same bound the OpenAI / Grok / Seedream adapters use.
    default_timeout_seconds: ClassVar[int] = 60

    _DEFAULT_BASE_URL: ClassVar[str] = "https://api.stability.ai"
    _DEFAULT_MODEL: ClassVar[str] = "sd3.5-large"
    # v2beta endpoint path. Stability has /sd3 (SD3 family — accepts model
    # form-field), /core, and /ultra. The /sd3 surface is what supports
    # the SD3.5 sub-models, so it's the default. Tenants that want /core
    # or /ultra would need a config knob we have not added (YAGNI).
    _ENDPOINT_PATH: ClassVar[str] = "/v2beta/stable-image/generate/sd3"
    _OUTPUT_FORMAT: ClassVar[str] = "png"

    async def generate(self, req: ImageGenerationRequest) -> ImageGenerationResult:
        api_key = self._require_api_key()
        base_url = self._resolved_base_url()
        model = self.tenant_config.image_model or self._DEFAULT_MODEL

        # Lazy import — sys.modules patching in tests requires this. Same
        # rule the other adapters follow.
        try:
            import aiohttp  # type: ignore[import-untyped]
        except ImportError as exc:
            raise MaicConfigError(
                "aiohttp is required for the Stability image adapter; "
                "pip install aiohttp"
            ) from exc

        headers = {
            "Authorization": f"Bearer {api_key}",
            # Accept image/* — Stability returns raw bytes directly in
            # the body. With application/json it would base64-wrap.
            "Accept": "image/*",
        }
        endpoint = f"{base_url}{self._ENDPOINT_PATH}"

        # Build the multipart form data. aiohttp.FormData accepts repeated
        # add_field calls. Stability requires multipart/form-data — JSON
        # is rejected.
        form = aiohttp.FormData()
        form.add_field("prompt", req.prompt)
        form.add_field("aspect_ratio", _aspect_ratio_for(req.width, req.height))
        form.add_field("model", model)
        form.add_field("output_format", self._OUTPUT_FORMAT)
        if req.seed is not None:
            # Stability accepts an integer seed in the form. We forward
            # ours straight through.
            form.add_field("seed", str(req.seed))

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(endpoint, data=form, headers=headers) as resp:
                    status = resp.status
                    content_type = resp.headers.get("Content-Type", "")
                    # On success Stability returns image bytes; on error
                    # it returns JSON. We read bytes either way; for JSON
                    # the decoded text feeds into the error path.
                    raw = await resp.read()

                    if not (200 <= status < 300):
                        self._raise_for_error_status(status, raw, content_type)

                    image_bytes, resolved_ct = self._extract_image_bytes(
                        raw, content_type,
                    )
        except aiohttp.ClientError as exc:
            raise MaicProviderError(
                f"stability image: network error talking to {endpoint}: {exc}"
            ) from exc

        # Re-host the inline bytes via upload_media so the caller gets a
        # stable URL on our storage backend. Stability does not host the
        # output themselves; the bytes are ephemeral once the response is
        # consumed.
        media_id, stored_url = await upload_media(
            data=image_bytes,
            content_type=resolved_ct,
            tenant_id=req.tenant_id,
            kind="image",
            scene_id=req.scene_id,
        )

        return ImageGenerationResult(
            media_id=media_id,
            url=stored_url,
            provider="stability",
            model=model,
            latency_ms=0,  # orchestrator stamps the real value
            cost_usd_estimate=self._estimate_cost(model),
        )

    # ── Internals ──────────────────────────────────────────────────────

    def _require_api_key(self) -> str:
        api_key = self.tenant_config.get_image_api_key()
        if not api_key:
            raise MaicConfigError(
                "stability image: api_key required (set image_api_key on "
                "TenantAIConfig via set_image_api_key()), or set "
                "image_provider='disabled' to skip image generation"
            )
        return api_key

    def _resolved_base_url(self) -> str:
        """Pick base URL, validate with SSRF guard if customised.

        Default Stability endpoint skips the SSRF check — known public
        host, no need to DNS-resolve it twice per call. Custom URLs
        (regional proxies, self-hosted gateways) MUST go through the
        guard."""
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
                f"stability image: image_base_url failed SSRF check: {exc}"
            ) from exc
        return base

    @staticmethod
    def _raise_for_error_status(status: int, raw: bytes, content_type: str) -> None:
        """Translate non-2xx HTTP into typed exceptions.

        Stability error envelopes are JSON: ``{name: "bad_request",
        errors: ["prompt is too long", ...]}``. We surface the ``name``
        and the first error string when parseable; otherwise we fall
        back to the raw body snippet."""
        snippet = _format_error_snippet(raw, content_type)
        if status in (401, 403):
            raise MaicConfigError(
                f"stability image: auth failed (HTTP {status}): {snippet}"
            )
        if status == 429:
            raise MaicProviderError(
                f"stability image: rate limited (HTTP 429): {snippet}"
            )
        if 400 <= status < 500:
            raise MaicProviderError(
                f"stability image: client error (HTTP {status}): {snippet}"
            )
        # 5xx
        raise MaicProviderError(
            f"stability image: server error (HTTP {status}): {snippet}"
        )

    @staticmethod
    def _extract_image_bytes(
        raw: bytes, content_type: str,
    ) -> tuple[bytes, str]:
        """Validate that we got image bytes back and return them.

        Stability with ``Accept: image/*`` returns the image directly in
        the response body. The Content-Type header tells us the format
        (image/png by default, image/jpeg or image/webp if we'd asked).
        If the server ignored our Accept and sent JSON, the bytes will
        be JSON — treat that as a malformed success (rare; Stability
        usually returns 4xx in that case)."""
        ct = (content_type or "").lower()
        # Empty content-type or non-image content-type with a successful
        # 2xx is unexpected. Stability has been observed (rarely) to send
        # 200 + JSON when an upstream worker degrades; surface that as
        # provider error rather than silently uploading garbage.
        if "application/json" in ct:
            snippet = _format_error_snippet(raw, ct)
            raise MaicProviderError(
                f"stability image: server returned JSON on a 2xx response: {snippet}"
            )
        if not raw:
            raise MaicProviderError("stability image: empty response body")
        # If Content-Type starts with image/ we use it; otherwise default
        # to image/png (matches our requested output_format).
        if ct.startswith("image/"):
            return raw, ct
        return raw, "image/png"

    @staticmethod
    def _estimate_cost(model: str) -> float | None:
        """SD3.5 family list price (USD). None for unknown models — we
        never fabricate cost numbers.

        See _STABILITY_SD35_PRICES_USD at module top for the source.
        """
        return _STABILITY_SD35_PRICES_USD.get(model)


# ── Helpers ────────────────────────────────────────────────────────────


# Stability v2beta accepts ONLY these aspect_ratio strings (rejected with
# 400 otherwise). Order is irrelevant — we pick by numerical proximity to
# the requested width/height ratio.
_KNOWN_ASPECT_RATIOS: tuple[str, ...] = (
    "1:1",
    "16:9",
    "9:16",
    "21:9",
    "9:21",
    "2:3",
    "3:2",
    "4:5",
    "5:4",
)


def _aspect_ratio_for(width: int, height: int) -> str:
    """Snap (width, height) to the closest Stability-accepted aspect_ratio
    string. Stability derives the actual output pixel dims from this
    bucket; we cannot pass arbitrary widths/heights to v2beta.

    Strategy: minimum absolute difference between requested ratio and
    each known ratio. Tie-breaks go to the first ratio in the tuple
    (1:1 first → square dominates ambiguous cases).

    Defensive: zero/negative or equal dims → "1:1" without iterating
    (Pydantic constraints in ImageGenerationRequest forbid <64 already,
    but this helper is also called directly in tests)."""
    if width <= 0 or height <= 0 or width == height:
        return "1:1"
    target = width / height
    best_ratio = "1:1"
    best_delta = float("inf")
    for ratio in _KNOWN_ASPECT_RATIOS:
        w_str, h_str = ratio.split(":")
        candidate = int(w_str) / int(h_str)
        delta = abs(candidate - target)
        if delta < best_delta:
            best_delta = delta
            best_ratio = ratio
    return best_ratio


def _format_error_snippet(raw: bytes, content_type: str) -> str:
    """Render a bounded, human-friendly error snippet from a Stability
    error response.

    Stability error envelope (JSON):
        {"name": "bad_request", "errors": ["prompt is too long"]}

    When we can parse JSON we surface ``name`` + the first ``errors``
    entry; otherwise we fall back to the raw body text truncated to
    200 chars. Always returns a string."""
    try:
        text = raw.decode("utf-8", errors="replace")
    except Exception:  # pragma: no cover — decode("utf-8", "replace") never raises
        text = ""
    ct = (content_type or "").lower()
    if "application/json" in ct or text.lstrip().startswith("{"):
        import json
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict):
            name = str(data.get("name") or "")
            errs = data.get("errors")
            first_err = ""
            if isinstance(errs, list) and errs:
                first_err = str(errs[0])
            parts = [p for p in (name, first_err) if p]
            if parts:
                return ": ".join(parts)[:200]
    # Fall back to the raw text body, bounded.
    return text[:200]
