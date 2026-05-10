"""Veo (Google) video generation adapter — MAIC-910.

Source: THU-MAIC/OpenMAIC lib/media/adapters/veo-adapter.ts (read for the
        upstream HTTP contract; re-implemented in Python per ADR-001a —
        no AGPL code import).
Golden pattern: apps/maic/media/adapters/qwen_image.py (MAIC-904) — the
        first async-polling adapter; this file is its video-shaped twin.
        We reuse the same polling lifecycle, deadline math, and HTTP
        error matrix; only the upstream-specific bits (endpoint, body
        shape, terminal condition) differ.
Auth pattern: apps/maic/media/adapters/nano_banana.py (MAIC-907) — also
        Google, also uses ``x-goog-api-key`` (NEVER ``?key=`` in URL,
        so the API key never appears in access logs).

**THIS IS THE FIRST VIDEO ADAPTER.** Kling / Minimax-video / Grok-video
(MAIC-911 / MAIC-912 / MAIC-913) copy this file's shape with minor tweaks
to the upstream contract. If something here is wrong, the bug replicates
×4 — so the lifecycle and types are documented loud.

Lifecycle (Google's long-running operations pattern):

  Step 1: POST {base}/v1beta/models/{model}:predictLongRunning
          body: {instances: [{prompt: <text>}], parameters: {...}}
          headers: x-goog-api-key, Content-Type
          → response body: {name: "operations/<op_id>"}
          The TS upstream and Google's docs both use a relative
          "operations/<id>" form. We treat the FULL ``name`` field as
          opaque — we always poll {base}/v1beta/<name> rather than
          trying to parse out the operation id, which sidesteps any
          Google quirk where the prefix shifts (e.g.
          "operations/" vs "projects/.../operations/...").

  Step 2: GET {base}/v1beta/<operation_name> every 5s until
          ``done: true``. While the operation is in progress, the body
          carries only ``{name, done: false, metadata: {...}}``; we
          ignore metadata. We do NOT use the alternate
          POST :fetchPredictOperation endpoint the upstream TS adapter
          uses — the canonical Google Long-Running Operations pattern
          is the GET form, and it's simpler to test + reason about.
          (If a future regional gateway demands the POST form we can
          add it behind a feature flag; right now no production tenant
          needs it.)

  Step 3: when done:true, branch on the body:
          ─ success: ``response.generateVideoResponse.generatedSamples[0].video.uri``
            ← yes, the nesting is real. ``generateVideoResponse`` is the
              Google-internal predictor name; ``generatedSamples`` is the
              array (always length 1 for us — we don't request batches);
              ``video.uri`` is a short-TTL Google Cloud Storage signed URL.
              We GET it (still with the x-goog-api-key header — Veo's
              GCS URLs require auth even though they look signed), read
              bytes, re-host via upload_media(kind="video"), return a
              VideoGenerationResult pointing at OUR storage.
          ─ error: ``error.{code, message}`` → MaicProviderError with the
              code+message embedded so operators reading the failure
              ticket know whether this was a content-policy block, quota
              issue, or model crash.

Used by:
  - apps/maic/media/orchestrator.py — calls .generate() after resolving
    this adapter via resolve_video_provider with video_provider="veo"
  - apps/maic/media/views.py — POST /api/maic/v2/media/generate-video/ (Phase 9 wire-up)

Discipline (mirrors MAIC-904 plus the video-cadence overrides):
  - aiohttp imported lazily inside generate() so tests can inject a fake
    via monkeypatch.setitem(sys.modules, "aiohttp", fake) — exact pattern
    Phase 5 Minimax TTS uses.
  - SSRF guard on tenant-supplied base_url (skipped for the default
    generativelanguage.googleapis.com URL — well-known public endpoint).
  - HTTP-class error split on BOTH submit AND every poll response:
      401/403 → MaicConfigError  (auth — orchestrator does NOT retry)
      429    → MaicProviderError (rate limited — retry)
      4xx    → MaicProviderError (other 4xx — likely transient)
      5xx    → MaicProviderError (server fault — retry)
      ClientError → MaicProviderError (network — retry)
      Parse failure → MaicProviderError (server returned bad shape)
  - Polling has a HARD DEADLINE — uses asyncio.get_event_loop().time() +
    self._poll_timeout_seconds. NEVER ``while True`` without a deadline
    check; the loop body re-checks the deadline BEFORE issuing the next
    GET AND BEFORE sleeping. When the deadline trips we raise
    MaicProviderError so the orchestrator can retry the whole submit
    cycle (submits are idempotent — they just produce a new op id).
  - Auth is ``x-goog-api-key`` header ONLY — NEVER ``?key=`` in the URL.
    Same reasoning as nano_banana: keeps the key out of access logs.
  - Re-host bytes via upload_media so the storage URL outlives Google's
    short-TTL signed URL.
  - Bounded error message truncation (200 chars) so adversarial servers
    can't blow up logs.

Subclassing note: ``_poll_interval_seconds`` and ``_poll_timeout_seconds``
are ClassVars so sibling video adapters (Kling / Minimax-video /
Grok-video) can subclass and override the cadence without re-implementing
``_poll_operation_until_done``. The numbers below are tuned for Veo's
typical 30-180s latency.
"""
from __future__ import annotations

import asyncio
import logging
from typing import ClassVar

from apps.maic.exceptions import MaicConfigError, MaicProviderError
from apps.maic.media.providers import MediaProviderAdapter, register_adapter
from apps.maic.media.storage import upload_media
from apps.maic.media.types import VideoGenerationRequest, VideoGenerationResult
from apps.integrations_chat.ssrf_guard import SSRFError, validate_webhook_host


logger = logging.getLogger(__name__)


@register_adapter
class VeoVideoAdapter(MediaProviderAdapter):
    """Google Veo video generation adapter (Gemini API long-running ops).

    Reads from TenantAIConfig:
        video_api_key (decrypted) — required; MaicConfigError if missing.
            Google's canonical env var is GOOGLE_API_KEY but we require
            a per-tenant key (no env fallback) — leaking the operator's
            personal key across courses in a multi-tenant LMS would be
            bad. Tenants that want env-var fallback should ask explicitly.
        video_base_url — optional; defaults to generativelanguage.googleapis.com
        video_model — optional; defaults to "veo-3.0-generate-preview"
            (Veo 3 preview; tenants may override to a current GA model
            once Google releases one).

    Returns a VideoGenerationResult whose URL points to OUR storage
    (not Google's signed URL). Veo's result URI is a short-TTL GCS URL,
    so re-hosting is mandatory.
    """

    name: ClassVar[str] = "veo"
    kind: ClassVar = "video"
    # Video takes 30-180s typically; cap at 360s gives headroom for retry
    # and for the "sometimes minutes" tail Google's docs warn about.
    default_timeout_seconds: ClassVar[int] = 360

    _DEFAULT_BASE_URL: ClassVar[str] = "https://generativelanguage.googleapis.com/v1beta"
    _DEFAULT_MODEL: ClassVar[str] = "veo-3.0-generate-preview"

    # Polling cadence. ClassVar so video siblings can override. Numbers
    # tuned for Veo: 5s interval (slower than image because video gens
    # are slower; we don't need to spam every 2s) and 300s deadline
    # (5min cap — Google says Veo can take "minutes"; default_timeout
    # of 360s leaves a small margin for the bytes fetch + storage write).
    _poll_interval_seconds: ClassVar[float] = 5.0
    _poll_timeout_seconds: ClassVar[float] = 300.0

    async def generate(self, req: VideoGenerationRequest) -> VideoGenerationResult:
        api_key = self._require_api_key()
        base_url = self._resolved_base_url()
        model = self.tenant_config.video_model or self._DEFAULT_MODEL

        # Veo's predictLongRunning body uses Google's predictor convention:
        # `instances` (an array — one entry per "thing to generate"; we
        # only ever submit one) and `parameters` (optional knobs).
        # We always request one clip; the orchestrator schedules N parallel
        # calls if a course needs multiple.
        parameters: dict = {
            "aspectRatio": req.aspect_ratio,
            "durationSeconds": req.duration_seconds,
        }
        if req.seed is not None:
            # Veo accepts an optional seed for reproducibility (Google
            # documents it on the v1beta predictLongRunning body).
            parameters["seed"] = req.seed
        payload: dict = {
            "instances": [{"prompt": req.prompt}],
            "parameters": parameters,
        }

        # Lazy import — sys.modules patching in tests requires this. If
        # we imported aiohttp at module top, tests couldn't inject a fake.
        try:
            import aiohttp  # type: ignore[import-untyped]
        except ImportError as exc:
            raise MaicConfigError(
                "aiohttp is required for the Veo video adapter; "
                "pip install aiohttp"
            ) from exc

        # Google API: x-goog-api-key header ONLY. NEVER ?key=<key> in the
        # URL — that form would leak the key into every CDN / proxy /
        # access log. Same rule as nano_banana.
        headers = {
            "x-goog-api-key": api_key,
            "Content-Type": "application/json",
        }
        submit_endpoint = f"{base_url}/models/{model}:predictLongRunning"

        try:
            async with aiohttp.ClientSession() as session:
                # Step 1: submit
                async with session.post(
                    submit_endpoint, json=payload, headers=headers,
                ) as resp:
                    body_text = await resp.text()
                    self._raise_for_status(resp.status, body_text, phase="submit")
                    parsed = self._parse_response_json(body_text, phase="submit")

                operation_name = self._extract_operation_name(parsed)

                # Step 2: poll until terminal — bounded by _poll_timeout_seconds.
                video_uri = await self._poll_operation_until_done(
                    session=session,
                    operation_name=operation_name,
                    headers=headers,
                    base_url=base_url,
                )

                # Step 3: fetch the generated bytes. Google's signed GCS
                # URLs for Veo require the x-goog-api-key header even
                # though they look signed — pass headers along.
                content_type, video_bytes = await self._fetch_video_bytes(
                    session, video_uri, headers,
                )
        except aiohttp.ClientError as exc:
            # DNS / connection reset / read error somewhere in the
            # submit-or-poll-or-fetch chain — orchestrator will retry.
            raise MaicProviderError(
                f"veo video: network error talking to {submit_endpoint}: {exc}"
            ) from exc

        # Re-host so our storage URL outlives Google's signed-URL TTL.
        media_id, stored_url = await upload_media(
            data=video_bytes,
            content_type=content_type,
            tenant_id=req.tenant_id,
            kind="video",
            scene_id=req.scene_id,
        )

        return VideoGenerationResult(
            media_id=media_id,
            url=stored_url,
            provider="veo",
            model=model,
            duration_seconds=req.duration_seconds,
            latency_ms=0,  # orchestrator stamps the real value
            cost_usd_estimate=self._estimate_cost(model, req.duration_seconds),
        )

    # ── Polling helper — mirrors qwen_image._poll_task_until_done ─────

    async def _poll_operation_until_done(
        self,
        *,
        session,
        operation_name: str,
        headers: dict[str, str],
        base_url: str,
    ) -> str:
        """Poll Veo's long-running operation endpoint until ``done: true``.

        Bounded by ``self._poll_timeout_seconds`` measured against the
        event-loop clock. The loop body checks the deadline BEFORE
        issuing each GET AND BEFORE each sleep — there is intentionally
        no ``while True`` without a guard; the only way out is a terminal
        operation state or the deadline tripping.

        Mapping:
            done == true and response.generateVideoResponse.generatedSamples
              → return generatedSamples[0].video.uri
            done == true and error.{code, message}
              → raise MaicProviderError (the orchestrator may retry the
                submit — submits are idempotent, FAILED on retry will
                fail again but bounded by retries config)
            done == false (or missing)
              → continue polling
            HTTP error during poll → typed exception per _raise_for_status

        Returns:
            The video URI from response.generateVideoResponse.generatedSamples[0].video.uri.

        Raises:
            MaicProviderError: operation ended in error, poll response
                malformed, or polling exhausted the deadline.
            MaicConfigError: poll endpoint returned 401/403 (auth rotated
                mid-operation — exceedingly rare but possible).
        """
        loop = asyncio.get_event_loop()
        deadline = loop.time() + self._poll_timeout_seconds
        # operation_name is e.g. "operations/abc-123" — we treat it as
        # opaque and just concat under the base URL. Strip any leading
        # slash so the URL stays well-formed.
        poll_endpoint = f"{base_url}/{operation_name.lstrip('/')}"

        # Tracks iterations purely for the error message — bounded by
        # the deadline check, so this never approaches infinity.
        attempt = 0
        while True:
            # Deadline check BEFORE issuing the GET — if we're already
            # past the deadline, don't waste a round-trip; raise.
            if loop.time() >= deadline:
                raise MaicProviderError(
                    f"veo video: polling timed out after "
                    f"{self._poll_timeout_seconds:.0f}s "
                    f"(operation={operation_name}, attempts={attempt})"
                )
            attempt += 1

            async with session.get(poll_endpoint, headers=headers) as resp:
                body_text = await resp.text()
                self._raise_for_status(resp.status, body_text, phase="poll")
                parsed = self._parse_response_json(body_text, phase="poll")

            # Terminal: done == true. We branch on success vs error.
            if isinstance(parsed, dict) and parsed.get("done") is True:
                err = parsed.get("error") if isinstance(parsed, dict) else None
                if isinstance(err, dict):
                    code = err.get("code", "?")
                    message = err.get("message", "")
                    raise MaicProviderError(
                        f"veo video: operation ended in error "
                        f"(operation={operation_name}, code={code}): "
                        f"{str(message)[:200]}"
                    )
                return self._extract_video_uri(parsed, operation_name=operation_name)

            # Still running — wait the configured interval, then re-poll.
            # Re-check the deadline AFTER sleep so a long interval doesn't
            # push us past the cap silently.
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise MaicProviderError(
                    f"veo video: polling timed out after "
                    f"{self._poll_timeout_seconds:.0f}s "
                    f"(operation={operation_name}, attempts={attempt})"
                )
            sleep_for = min(self._poll_interval_seconds, remaining)
            await asyncio.sleep(sleep_for)

    # ── Internals ──────────────────────────────────────────────────────

    def _require_api_key(self) -> str:
        api_key = self.tenant_config.get_video_api_key()
        if not api_key:
            raise MaicConfigError(
                "veo video: api_key required (set video_api_key on "
                "TenantAIConfig via set_video_api_key()), or set "
                "video_provider='disabled' to skip video generation"
            )
        return api_key

    def _resolved_base_url(self) -> str:
        """Pick base URL, validate with SSRF guard if customised.

        Default URL (Google's public generativelanguage host) skips the
        guard — well-known public endpoint, no point DNS-resolving
        twice per request. Custom URLs (regional override, gateway
        proxy, mock server) MUST go through the guard.
        """
        raw = (self.tenant_config.video_base_url or "").strip()
        if not raw:
            return self._DEFAULT_BASE_URL.rstrip("/")
        base = raw.rstrip("/")
        if base == self._DEFAULT_BASE_URL.rstrip("/"):
            return base
        try:
            validate_webhook_host(base)
        except SSRFError as exc:
            raise MaicConfigError(
                f"veo video: video_base_url failed SSRF check: {exc}"
            ) from exc
        return base

    @staticmethod
    def _raise_for_status(status: int, body: str, *, phase: str) -> None:
        """Translate HTTP status into typed exceptions.

        ``phase`` is "submit" or "poll" — embedded in the error message
        so operators reading logs can tell which leg of the call failed.
        Both phases use the same mapping (Google's gateway returns the
        same 401/403/429/5xx shape for both).
        """
        if 200 <= status < 300:
            return
        snippet = body[:200] if body else ""
        if status in (401, 403):
            raise MaicConfigError(
                f"veo video: auth failed during {phase} (HTTP {status}): {snippet}"
            )
        if status == 429:
            raise MaicProviderError(
                f"veo video: rate limited during {phase} (HTTP 429): {snippet}"
            )
        if 400 <= status < 500:
            raise MaicProviderError(
                f"veo video: client error during {phase} (HTTP {status}): {snippet}"
            )
        # 5xx
        raise MaicProviderError(
            f"veo video: server error during {phase} (HTTP {status}): {snippet}"
        )

    @staticmethod
    def _parse_response_json(body: str, *, phase: str) -> dict:
        """Defensive JSON parse — raise MaicProviderError on malformed
        body so the orchestrator can retry. Phase string lands in the
        error message for log correlation."""
        import json
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise MaicProviderError(
                f"veo video: malformed JSON response during {phase}: {exc}"
            ) from exc

    @staticmethod
    def _extract_operation_name(data: dict) -> str:
        """Veo submit response shape: {name: "operations/<op_id>", ...}.

        Some Google regional gateways prefix with the full
        ``projects/.../locations/.../operations/...`` form; we accept
        either and treat the whole thing as opaque. The poll URL just
        concatenates this string onto the base URL.

        Defensive: missing/empty name → MaicProviderError so the
        orchestrator can retry the submit.
        """
        if not isinstance(data, dict):
            raise MaicProviderError(
                f"veo video: submit response was not an object: "
                f"{type(data).__name__}"
            )
        # If Google returned an error block on a 200 response (the
        # quirk nano_banana documents), surface it as MaicProviderError.
        err = data.get("error")
        if isinstance(err, dict):
            code = err.get("code", "?")
            message = err.get("message", "")
            raise MaicProviderError(
                f"veo video: submit returned error in 200 body "
                f"(code={code}): {str(message)[:200]}"
            )
        name = data.get("name")
        if not isinstance(name, str) or not name:
            raise MaicProviderError(
                f"veo video: submit response missing or empty 'name': "
                f"{list(data)[:5]}"
            )
        return name

    @staticmethod
    def _extract_video_uri(data: dict, *, operation_name: str) -> str:
        """When done:true (success branch), the URI is at
        ``response.generateVideoResponse.generatedSamples[0].video.uri``.

        Yes, the nesting is unusual — ``generateVideoResponse`` is the
        Google-internal predictor name (each long-running predictor type
        has its own response wrapper). The ``generatedSamples`` array
        always has length 1 for us (we only submit one instance), and
        each sample carries a ``video.uri`` short-TTL GCS URL.

        Defensive shape checks at every level — any deviation →
        MaicProviderError so the orchestrator can retry.
        """
        response = data.get("response") if isinstance(data, dict) else None
        if not isinstance(response, dict):
            raise MaicProviderError(
                f"veo video: done:true but no 'response' object "
                f"(operation={operation_name}): {list(data)[:5]}"
            )
        gvr = response.get("generateVideoResponse")
        if not isinstance(gvr, dict):
            raise MaicProviderError(
                f"veo video: done:true but no 'response.generateVideoResponse' "
                f"(operation={operation_name}): {list(response)[:5]}"
            )
        samples = gvr.get("generatedSamples")
        if not isinstance(samples, list) or not samples:
            raise MaicProviderError(
                f"veo video: done:true but generatedSamples missing/empty "
                f"(operation={operation_name})"
            )
        first = samples[0]
        if not isinstance(first, dict):
            raise MaicProviderError(
                f"veo video: generatedSamples[0] was not an object "
                f"(operation={operation_name})"
            )
        video = first.get("video")
        if not isinstance(video, dict):
            raise MaicProviderError(
                f"veo video: generatedSamples[0].video missing or not an object "
                f"(operation={operation_name})"
            )
        uri = video.get("uri")
        if not isinstance(uri, str) or not uri:
            raise MaicProviderError(
                f"veo video: generatedSamples[0].video.uri missing or empty "
                f"(operation={operation_name})"
            )
        return uri

    async def _fetch_video_bytes(
        self, session, video_uri: str, headers: dict[str, str],
    ) -> tuple[str, bytes]:
        """Download the generated video bytes from the URI Veo returned.

        Google's Veo result URIs are short-TTL GCS URLs that require the
        x-goog-api-key header even though they look like signed URLs —
        we pass the same headers we used for submit/poll.

        Default content_type to video/mp4 if the response omits the
        header (Veo output is mp4 by default).
        """
        async with session.get(video_uri, headers=headers) as vid_resp:
            if vid_resp.status != 200:
                raise MaicProviderError(
                    f"veo video: failed to fetch generated video bytes "
                    f"(HTTP {vid_resp.status})"
                )
            content_type = vid_resp.headers.get("Content-Type", "video/mp4")
            data = await vid_resp.read()
        if not data:
            raise MaicProviderError("veo video: fetched zero bytes")
        return content_type, data

    @staticmethod
    def _estimate_cost(model: str, duration_seconds: int) -> float | None:
        """No verified per-tenant pricing — Veo pricing is tier-dependent
        (public Vertex pricing shows $0.40/s for veo-3.0-generate and
        $0.15/s for the -fast variant, but actual billing depends on the
        tenant's contract / credits / region). Telemetry is non-blocking,
        so a missing cost is fine — operators get spend numbers from the
        Google Cloud console.

        Returns None for all models until a verified pricing table lives
        next to the adapter.
        """
        return None
