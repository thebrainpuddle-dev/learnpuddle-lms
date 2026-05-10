"""Nano Banana (Google Gemini native image generation) adapter — MAIC-907.

Source: THU-MAIC/OpenMAIC lib/media/adapters/nano-banana-adapter.ts (read
        for API contract; re-implemented in Python per ADR-001a).
Golden pattern: apps/maic/media/adapters/openai_image.py (MAIC-903).
Closest sibling: apps/maic/media/adapters/seedream.py (also handles a
        base64-inline response branch; we reuse that decode discipline).

CRITICAL DELTA vs the golden pattern: Gemini returns the generated image
**base64-inline** inside the JSON response — there is NO second HTTP fetch
against a CDN URL. The response shape is:

    {
      "candidates": [{
        "content": {
          "parts": [
            {"inlineData": {"mimeType": "image/png", "data": "<base64>"}}
          ]
        }
      }]
    }

So `generate()` does ONE POST, decodes inline base64 → bytes, then uploads
to our storage and returns the storage URL — never touches a Google CDN
host. This sidesteps the URL-expiry retry hazard the OpenAI / Seedream URL
branches contend with.

Other Gemini-specific points:
  - Auth header is `x-goog-api-key: <key>` (NOT `Authorization: Bearer …`
    and NOT the `?key=…` query-string form the upstream TS adapter uses
    as a connectivity-test fallback — for the production generate call
    the header form is what the TS adapter sends).
  - Request body uses Gemini's `contents` / `parts` shape with a
    `generationConfig.responseModalities = ["IMAGE"]` flag. Completely
    different from OpenAI's flat `{model, prompt, size}` POST body.
  - Endpoint is `<base>/v1beta/models/<model>:generateContent` — model
    name is embedded in the URL path (NOT in the body).
  - Errors can arrive two ways: as HTTP status codes (the usual 4xx/5xx)
    OR as a `data.error` block on a 200 response (Google API quirk).
    We handle both — the latter promotes to MaicProviderError.
  - A prompt that gets rejected for safety reasons returns parts with
    only text (no inlineData) — we surface that as MaicProviderError
    with the text snippet for debugging.

Used by:
  - apps/maic/media/orchestrator.py — calls .generate() after resolving
    this adapter from the registry
  - apps/maic/media/views.py — POST /api/maic/v2/media/generate-image/

Discipline (mirrors MAIC-903):
  - aiohttp lazy import for monkeypatch.setitem(sys.modules, ...) testing
  - SSRF guard on tenant-supplied base_url (default URL skips the check)
  - HTTP status → typed exception (401/403→Config, 429/4xx/5xx→Provider)
  - Bounded error message truncation (200 chars)
  - Re-host bytes via upload_media so the storage URL is stable
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
class NanoBananaImageAdapter(MediaProviderAdapter):
    """Google Gemini (Nano Banana) image generation adapter.

    Reads from TenantAIConfig:
        image_api_key (decrypted) — required; MaicConfigError if missing
        image_base_url — optional; defaults to generativelanguage.googleapis.com
        image_model — optional; defaults to "gemini-2.5-flash-image"
                      (Nano Banana original; tenant may override to
                      gemini-3.1-flash-image-preview / gemini-3-pro-image-preview)

    Returns an ImageGenerationResult whose URL points to OUR storage —
    the base64 payload is decoded + uploaded immediately. No Google CDN
    URL is ever returned to the caller.

    Cost estimate is always None — Gemini image pricing is published as
    a per-request rate but varies by model and request modality combo;
    we keep this off the hot path until a verified pricing table lives
    next to the adapter.
    """

    name: ClassVar[str] = "nano_banana"
    kind: ClassVar = "image"
    # Gemini image generation typically completes in 5-20s; cap at 60s
    # for headroom on Pro models / cold-start latency.
    default_timeout_seconds: ClassVar[int] = 60

    _DEFAULT_BASE_URL: ClassVar[str] = "https://generativelanguage.googleapis.com"
    _DEFAULT_MODEL: ClassVar[str] = "gemini-2.5-flash-image"

    async def generate(self, req: ImageGenerationRequest) -> ImageGenerationResult:
        api_key = self._require_api_key()
        base_url = self._resolved_base_url()
        model = self.tenant_config.image_model or self._DEFAULT_MODEL

        # Gemini's contents/parts shape — NOT OpenAI's flat prompt field.
        # The model name is in the URL path; the body carries the prompt
        # text inside a parts[] array and a responseModalities flag that
        # tells Gemini to return image bytes (default would be text).
        payload = {
            "contents": [
                {
                    "parts": [{"text": req.prompt}],
                },
            ],
            "generationConfig": {
                "responseModalities": ["IMAGE"],
            },
        }

        # Lazy import — sys.modules patching in tests requires this.
        try:
            import aiohttp  # type: ignore[import-untyped]
        except ImportError as exc:
            raise MaicConfigError(
                "aiohttp is required for the Nano Banana image adapter; "
                "pip install aiohttp"
            ) from exc

        # Gemini uses x-goog-api-key (NOT Authorization: Bearer). The
        # upstream TS adapter does fall back to a ?key=<api_key> query
        # param during a connectivity probe, but the production
        # generateContent call sends the header form — we match that
        # so the API key never appears in URL access logs.
        headers = {
            "x-goog-api-key": api_key,
            "Content-Type": "application/json",
        }
        endpoint = f"{base_url}/v1beta/models/{model}:generateContent"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(endpoint, json=payload, headers=headers) as resp:
                    body_text = await resp.text()
                    self._raise_for_status(resp.status, body_text)
                    parsed = self._parse_response_json(body_text)
        except aiohttp.ClientError as exc:
            # DNS failure, connection reset, etc. — orchestrator will retry.
            raise MaicProviderError(
                f"nano_banana image: network error talking to {endpoint}: {exc}"
            ) from exc

        # Gemini returns the image base64-inline. Decode, then upload to
        # our storage in one shot — no second HTTP fetch.
        content_type, image_bytes = self._extract_inline_image(parsed)

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
            provider="nano_banana",
            model=model,
            latency_ms=0,  # orchestrator stamps the real value
            cost_usd_estimate=None,  # Gemini pricing table not wired yet
        )

    # ── Internals ──────────────────────────────────────────────────────

    def _require_api_key(self) -> str:
        api_key = self.tenant_config.get_image_api_key()
        if not api_key:
            raise MaicConfigError(
                "nano_banana image: api_key required (set image_api_key on "
                "TenantAIConfig via set_image_api_key()), or set "
                "image_provider='disabled' to skip image generation"
            )
        return api_key

    def _resolved_base_url(self) -> str:
        """Pick base URL, validate with SSRF guard if customised.

        Default URL (Google's public generativelanguage host) skips the
        SSRF check — well-known public endpoint, no need to DNS-resolve
        it twice per request. Custom URLs (regional endpoints, gateway
        proxies, self-hosted relays) MUST go through the guard."""
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
                f"nano_banana image: image_base_url failed SSRF check: {exc}"
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
                f"nano_banana image: auth failed (HTTP {status}): {snippet}"
            )
        if status == 429:
            raise MaicProviderError(
                f"nano_banana image: rate limited (HTTP 429): {snippet}"
            )
        if 400 <= status < 500:
            # Other 4xx — invalid request, content policy, model not
            # found, etc. Treat as transient (orchestrator may retry).
            raise MaicProviderError(
                f"nano_banana image: client error (HTTP {status}): {snippet}"
            )
        # 5xx
        raise MaicProviderError(
            f"nano_banana image: server error (HTTP {status}): {snippet}"
        )

    @staticmethod
    def _parse_response_json(body: str) -> dict:
        """Defensive JSON parse — raise MaicProviderError on malformed body."""
        import json
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise MaicProviderError(
                f"nano_banana image: malformed JSON response: {exc}"
            ) from exc

    @staticmethod
    def _extract_inline_image(parsed: dict) -> tuple[str, bytes]:
        """Pull the base64-inline image out of Gemini's contents/parts shape.

        Expected:
            parsed["candidates"][0]["content"]["parts"]
              → list of parts; at least one has {"inlineData":
                {"mimeType": "image/png", "data": "<b64>"}}

        Failure modes (each → MaicProviderError):
          - top-level {"error": {...}} returned with HTTP 200 (Google quirk)
          - candidates missing / empty / wrong type
          - content.parts missing / empty
          - parts contains only text (safety rejection) — surface text
          - inlineData.data missing or non-string
          - base64 decode failure
          - decoded body is zero bytes
        """
        # Gemini sometimes returns 200 with an `error` block instead of
        # an HTTP error code. Promote it to MaicProviderError.
        err = parsed.get("error") if isinstance(parsed, dict) else None
        if isinstance(err, dict):
            code = err.get("code", "?")
            message = err.get("message", "")
            raise MaicProviderError(
                f"nano_banana image: gemini error in 200 body (code={code}): "
                f"{str(message)[:200]}"
            )

        candidates = parsed.get("candidates") if isinstance(parsed, dict) else None
        if not isinstance(candidates, list) or not candidates:
            raise MaicProviderError(
                f"nano_banana image: response missing candidates: "
                f"{list(parsed)[:5] if isinstance(parsed, dict) else type(parsed).__name__}"
            )

        first = candidates[0]
        if not isinstance(first, dict):
            raise MaicProviderError(
                "nano_banana image: candidates[0] was not an object"
            )

        content = first.get("content")
        if not isinstance(content, dict):
            raise MaicProviderError(
                "nano_banana image: candidates[0].content missing or not an object"
            )

        parts = content.get("parts")
        if not isinstance(parts, list) or not parts:
            raise MaicProviderError(
                "nano_banana image: candidates[0].content.parts missing or empty"
            )

        # Find the first part with inlineData (the image). If none, the
        # model likely returned a safety / refusal text — surface that.
        image_part = None
        for p in parts:
            if isinstance(p, dict) and isinstance(p.get("inlineData"), dict):
                image_part = p
                break

        if image_part is None:
            text_snippets = [
                p.get("text") for p in parts
                if isinstance(p, dict) and isinstance(p.get("text"), str)
            ]
            text_blob = " | ".join(text_snippets)[:200] if text_snippets else "none"
            raise MaicProviderError(
                f"nano_banana image: response had no inlineData part "
                f"(safety rejection?). Text: {text_blob}"
            )

        inline = image_part["inlineData"]
        b64 = inline.get("data")
        mime_type = inline.get("mimeType") or "image/png"
        if not isinstance(b64, str) or not b64:
            raise MaicProviderError(
                "nano_banana image: inlineData.data missing or not a string"
            )
        if not isinstance(mime_type, str) or not mime_type:
            mime_type = "image/png"

        import base64
        try:
            data = base64.b64decode(b64, validate=True)
        except (ValueError, TypeError) as exc:
            # Server returned a bad payload — orchestrator may retry.
            raise MaicProviderError(
                f"nano_banana image: malformed base64 in inlineData.data: {exc}"
            ) from exc
        if not data:
            raise MaicProviderError(
                "nano_banana image: inlineData.data decoded to zero bytes"
            )

        return mime_type, data
