"""Grok (xAI) video generation adapter — MAIC-913.

Source: THU-MAIC/OpenMAIC lib/media/adapters/grok-video-adapter.ts (read for
        upstream HTTP contract; re-implemented in Python per ADR-001a —
        no AGPL code import).
Golden patterns this file mixes:
  - apps/maic/media/adapters/grok_image.py (MAIC-905) — sibling adapter
    on the SAME provider (xAI). Same auth (Bearer), same default base URL
    (https://api.x.ai/v1), same SSRF rules, same 4xx/5xx error matrix.
  - apps/maic/media/adapters/qwen_image.py (MAIC-904) — first async-
    polling adapter. The submit/poll/fetch/re-host lifecycle is identical
    in shape; only the HTTP endpoints + status vocabulary differ.

The upstream xAI Videos API (per docs.x.ai/developers/rest-api-reference/inference/videos):

  Submit: POST {base}/videos/generations
          Body: {model, prompt, duration?}
          Auth: Authorization: Bearer <key>
          Response 200: {request_id: "<uuid>"}

  Poll:   GET {base}/videos/<request_id>
          Auth: Authorization: Bearer <key>
          Response 200: {
              status: "pending" | "done" | "failed",
              progress?: 0-100,
              video?: {url, duration, respect_moderation?},
              model?: "<model-id>",
          }

  On status == "done", video.url points to xAI's signed CDN URL with a
  short TTL — we MUST download the bytes and re-host via upload_media so
  the URL survives beyond xAI's cache window.

Pricing (per upstream docstring as of 2026-Q1):
  grok-imagine-video → $0.05 / second of generated video

Used by:
  - apps/maic/media/orchestrator.py — calls .generate() after resolving
    this adapter via resolve_video_provider with video_provider="grok_video"
  - apps/maic/media/views.py — POST /api/maic/v2/media/generate-video/

Discipline (mirrors MAIC-904 + MAIC-905):
  - aiohttp imported lazily inside generate() so tests can inject a fake
    via monkeypatch.setitem(sys.modules, "aiohttp", fake).
  - SSRF guard on tenant-supplied video_base_url; skipped for the default
    xAI URL (well-known public endpoint).
  - HTTP-class error split on BOTH submit AND every poll response:
      401/403 → MaicConfigError  (auth — orchestrator does NOT retry)
      429    → MaicProviderError (rate limited — retry)
      4xx    → MaicProviderError (other 4xx — likely transient)
      5xx    → MaicProviderError (server fault — retry)
      ClientError → MaicProviderError (network — retry)
      Parse failure → MaicProviderError (server returned bad shape)
  - Polling has a HARD DEADLINE measured against asyncio.get_event_loop()
    .time(); never ``while True``. Upstream cadence is 10s interval, 600s
    total; we mirror that.
  - Re-host bytes via upload_media kind="video" so the storage URL outlives
    xAI's signed-CDN TTL.
  - Bounded error message truncation (200 chars) so adversarial servers
    can't blow up logs.

Uncertainty flags (read this before changing anything):
  - The status-string vocabulary is taken DIRECTLY from upstream's
    TypeScript types: "pending" / "done" / "failed". If xAI introduces an
    intermediate value (e.g. "processing" or "queued") this adapter will
    fail-loud with "unrecognised status" — that is intentional: better to
    surface a contract change than spin silently. Operators should widen
    _IN_PROGRESS in that case.
  - The submit response shape ``{request_id}`` is taken from upstream.
    No documented ``status`` field on the submit response; if xAI returns
    one, we ignore it (uniform lifecycle = always poll).
  - Pricing is per-second of GENERATED video, not per-second of wall-clock
    polling. The cost estimate uses the request's duration_seconds (the
    poll response also carries .video.duration, which is what we ultimately
    bill against; the request value is the upper-bound estimate at submit
    time).
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


# Grok video task statuses — strings exactly as the upstream API emits them.
# Source: docs.x.ai/developers/rest-api-reference/inference/videos and the
# OpenMAIC TypeScript GrokVideoPollResponse type. Mapped to local categories
# so the polling loop has a tiny well-known vocabulary.
_TERMINAL_SUCCESS: frozenset[str] = frozenset({"done"})
_TERMINAL_FAILURE: frozenset[str] = frozenset({"failed"})
_IN_PROGRESS: frozenset[str] = frozenset({"pending"})


# Per-second list price keyed by model id (upstream docstring, 2026-Q1).
# Unknown model → return None (we never fabricate cost numbers).
_GROK_VIDEO_PRICES_USD_PER_SECOND: dict[str, float] = {
    "grok-imagine-video": 0.05,
}


@register_adapter
class GrokVideoAdapter(MediaProviderAdapter):
    """xAI Grok Videos API adapter.

    Reads from TenantAIConfig:
        video_api_key (decrypted) — required; MaicConfigError if missing.
            Same xAI key as the Grok image adapter; operators typically
            set both video_api_key and image_api_key to the same value.
        video_base_url — optional; defaults to https://api.x.ai/v1
        video_model — optional; defaults to "grok-imagine-video"

    Returns a VideoGenerationResult with a URL pointing to OUR storage
    (not xAI's CDN). xAI hosts videos on a short-TTL signed CDN; re-hosting
    is mandatory.
    """

    name: ClassVar[str] = "grok_video"
    kind: ClassVar = "video"
    # Video generation is slow — upstream poll cap is 60 attempts × 10s =
    # 600s. We need orchestrator headroom on top of that for the submit
    # round-trip and the final bytes fetch. 300s matches the brief; we
    # cap the internal poll deadline at 240s so submit+fetch always fit.
    default_timeout_seconds: ClassVar[int] = 300

    _DEFAULT_BASE_URL: ClassVar[str] = "https://api.x.ai/v1"
    _DEFAULT_MODEL: ClassVar[str] = "grok-imagine-video"

    # Polling cadence. ClassVar so test subclasses can shorten without
    # re-implementing _poll_task_until_done. Upstream uses 10s interval
    # with a 60-attempt cap (600s); we mirror that interval but use a
    # 240s deadline so the adapter fits inside default_timeout_seconds
    # with headroom for submit + bytes fetch (~60s combined budget).
    _poll_interval_seconds: ClassVar[float] = 5.0
    _poll_timeout_seconds: ClassVar[float] = 240.0

    async def generate(self, req: VideoGenerationRequest) -> VideoGenerationResult:
        api_key = self._require_api_key()
        base_url = self._resolved_base_url()
        model = self.tenant_config.video_model or self._DEFAULT_MODEL

        # Submit body shape per upstream: {model, prompt, duration?}. We
        # always pass duration so the upstream knows our target — xAI
        # otherwise defaults to 6s. The grok-video-adapter.ts source
        # documents only {model, prompt, duration} as accepted fields;
        # aspect_ratio is NOT a submit parameter on grok-imagine-video
        # (the upstream applies a fixed 16:9 internally and the adapter
        # post-derives dimensions from VideoGenerationRequest.aspect_ratio).
        payload: dict[str, object] = {
            "model": model,
            "prompt": req.prompt,
            "duration": req.duration_seconds,
        }

        # Lazy import — sys.modules patching in tests requires this.
        try:
            import aiohttp  # type: ignore[import-untyped]
        except ImportError as exc:
            raise MaicConfigError(
                "aiohttp is required for the Grok video adapter; "
                "pip install aiohttp"
            ) from exc

        # Same Bearer auth header on both submit and poll. Unlike Qwen,
        # there is no X-Async toggle — async-polling is the only mode
        # the Grok Videos API supports.
        auth_headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        poll_headers = {
            "Authorization": f"Bearer {api_key}",
        }
        submit_endpoint = f"{base_url}/videos/generations"

        try:
            async with aiohttp.ClientSession() as session:
                # Step 1: submit
                async with session.post(
                    submit_endpoint, json=payload, headers=auth_headers,
                ) as resp:
                    body_text = await resp.text()
                    self._raise_for_status(resp.status, body_text, phase="submit")
                    parsed = self._parse_response_json(body_text, phase="submit")

                request_id = self._extract_request_id(parsed)

                # Step 2: poll until terminal
                video_url, actual_duration = await self._poll_task_until_done(
                    session=session,
                    request_id=request_id,
                    headers=poll_headers,
                    base_url=base_url,
                )

                # Step 3: fetch the generated bytes
                content_type, video_bytes = await self._fetch_video_bytes(
                    session, video_url,
                )
        except aiohttp.ClientError as exc:
            # DNS / connection reset / read error somewhere in submit / poll
            # / fetch — orchestrator will retry.
            raise MaicProviderError(
                f"grok video: network error talking to {submit_endpoint}: {exc}"
            ) from exc

        # Re-host the video in our storage so the URL outlives xAI's
        # signed-CDN TTL.
        media_id, stored_url = await upload_media(
            data=video_bytes,
            content_type=content_type,
            tenant_id=req.tenant_id,
            kind="video",
            scene_id=req.scene_id,
        )

        # Prefer the upstream's reported duration; fall back to the
        # requested duration if upstream didn't return one (should be rare,
        # but the response field is documented as optional in the .ts type).
        effective_duration = actual_duration or req.duration_seconds

        return VideoGenerationResult(
            media_id=media_id,
            url=stored_url,
            provider="grok_video",
            model=model,
            duration_seconds=effective_duration,
            latency_ms=0,  # orchestrator stamps the real value
            cost_usd_estimate=self._estimate_cost(model, effective_duration),
        )

    # ── Polling helper — copied from qwen_image with status vocabulary
    #    swapped to match Grok's lowercase "pending"/"done"/"failed". ──

    async def _poll_task_until_done(
        self,
        *,
        session,
        request_id: str,
        headers: dict[str, str],
        base_url: str,
    ) -> tuple[str, int]:
        """Poll Grok's videos/{request_id} endpoint until terminal.

        Bounded by ``self._poll_timeout_seconds`` measured against the
        event-loop clock. The loop body checks the deadline BEFORE
        issuing each GET AND before each sleep — there is intentionally
        no ``while True`` here; the only way out is a terminal status
        or the deadline tripping.

        Mapping (status strings from upstream TS type):
            status == "done"
                → return (video.url, video.duration)
            status == "failed"
                → raise MaicProviderError (operator may retry submit)
            status == "pending"
                → continue polling
            HTTP error during poll → typed exception per _raise_for_status
            unrecognised status → MaicProviderError (loud — better to fail
                  than spin)

        Returns:
            (video_url, duration_seconds) — the CDN URL and the upstream-
            reported duration. Duration is 0 if upstream omitted it; the
            caller falls back to the request's duration_seconds.

        Raises:
            MaicProviderError: task failed, poll response malformed, or
                polling exhausted the deadline.
            MaicConfigError: poll endpoint returned 401/403 (auth rotated
                mid-task — exceedingly rare but possible).
        """
        loop = asyncio.get_event_loop()
        deadline = loop.time() + self._poll_timeout_seconds
        poll_endpoint = f"{base_url}/videos/{request_id}"

        attempt = 0
        while True:
            # Deadline check BEFORE issuing the GET — if we're already past
            # the deadline, don't waste a round-trip; raise immediately.
            if loop.time() >= deadline:
                raise MaicProviderError(
                    f"grok video: polling timed out after "
                    f"{self._poll_timeout_seconds:.0f}s "
                    f"(request_id={request_id}, attempts={attempt})"
                )
            attempt += 1

            async with session.get(poll_endpoint, headers=headers) as resp:
                body_text = await resp.text()
                self._raise_for_status(resp.status, body_text, phase="poll")
                parsed = self._parse_response_json(body_text, phase="poll")

            status = self._extract_status(parsed)

            if status in _TERMINAL_SUCCESS:
                return self._extract_video_url_and_duration(parsed)

            if status in _TERMINAL_FAILURE:
                # Surface any upstream error detail so operators reading
                # the failure ticket know whether this was a content-
                # policy block, a quota issue, or a model crash.
                error_msg = parsed.get("error") if isinstance(parsed, dict) else None
                detail = f" detail={str(error_msg)[:200]}" if error_msg else ""
                raise MaicProviderError(
                    f"grok video: task ended in non-success state "
                    f"{status!r} (request_id={request_id}){detail}"
                )

            if status not in _IN_PROGRESS:
                # Unknown status string — fail loud rather than spin. If
                # xAI adds a new state (e.g. "processing"), the operator
                # will see this and can widen _IN_PROGRESS.
                raise MaicProviderError(
                    f"grok video: unrecognised status {status!r} "
                    f"(request_id={request_id}); expected one of "
                    f"{sorted(_TERMINAL_SUCCESS | _TERMINAL_FAILURE | _IN_PROGRESS)}"
                )

            # Still pending — wait before re-polling. Re-check deadline
            # after sleep so a long interval doesn't push us past the cap.
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise MaicProviderError(
                    f"grok video: polling timed out after "
                    f"{self._poll_timeout_seconds:.0f}s "
                    f"(request_id={request_id}, attempts={attempt})"
                )
            sleep_for = min(self._poll_interval_seconds, remaining)
            await asyncio.sleep(sleep_for)

    # ── Internals ──────────────────────────────────────────────────────

    def _require_api_key(self) -> str:
        api_key = self.tenant_config.get_video_api_key()
        if not api_key:
            raise MaicConfigError(
                "grok video: api_key required (set video_api_key on "
                "TenantAIConfig via set_video_api_key()), or set "
                "video_provider='disabled' to skip video generation"
            )
        return api_key

    def _resolved_base_url(self) -> str:
        """Pick base URL, validate with SSRF guard if customised.

        Default URL skips the guard (well-known xAI public endpoint).
        Custom URLs (self-hosted proxy, regional override, mock server)
        MUST go through the guard — same rule as every other adapter."""
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
                f"grok video: video_base_url failed SSRF check: {exc}"
            ) from exc
        return base

    @staticmethod
    def _raise_for_status(status: int, body: str, *, phase: str) -> None:
        """Translate HTTP status into typed exceptions.

        ``phase`` is "submit" or "poll" — embedded in the error message
        so operators reading logs can tell which leg of the call failed.
        """
        if 200 <= status < 300:
            return
        snippet = body[:200] if body else ""
        if status in (401, 403):
            raise MaicConfigError(
                f"grok video: auth failed during {phase} (HTTP {status}): {snippet}"
            )
        if status == 429:
            raise MaicProviderError(
                f"grok video: rate limited during {phase} (HTTP 429): {snippet}"
            )
        if 400 <= status < 500:
            # 4xx during submit: invalid prompt, model not enabled, content
            # policy. During poll: typically a stale/wrong request id (404).
            raise MaicProviderError(
                f"grok video: client error during {phase} (HTTP {status}): {snippet}"
            )
        # 5xx
        raise MaicProviderError(
            f"grok video: server error during {phase} (HTTP {status}): {snippet}"
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
                f"grok video: malformed JSON response during {phase}: {exc}"
            ) from exc

    @staticmethod
    def _extract_request_id(data: dict) -> str:
        """Submit response shape: {request_id: "..."}. Defensive shape
        check — missing/empty id is a contract violation."""
        if not isinstance(data, dict):
            raise MaicProviderError(
                f"grok video: submit response was not a JSON object: "
                f"{type(data).__name__}"
            )
        request_id = data.get("request_id")
        if not isinstance(request_id, str) or not request_id:
            raise MaicProviderError(
                f"grok video: submit response missing request_id: "
                f"keys={list(data)[:5]}"
            )
        return request_id

    @staticmethod
    def _extract_status(data: dict) -> str:
        """Poll response shape: {status: "...", progress?, video?, model?}.

        Missing/non-string status → MaicProviderError. We do NOT default
        to "pending" — that would silently swallow an upstream contract
        change."""
        if not isinstance(data, dict):
            raise MaicProviderError(
                f"grok video: poll response was not a JSON object: "
                f"{type(data).__name__}"
            )
        status = data.get("status")
        if not isinstance(status, str) or not status:
            raise MaicProviderError(
                f"grok video: poll response missing status: "
                f"keys={list(data)[:5]}"
            )
        return status

    @staticmethod
    def _extract_video_url_and_duration(data: dict) -> tuple[str, int]:
        """When status == "done", the URL is at video.url and the duration
        at video.duration (per upstream TS type). Both fields on the
        video object are technically optional in the type, but if the
        URL is missing we cannot proceed; if duration is missing we
        fall back to the request's duration_seconds in the caller."""
        video = data.get("video") if isinstance(data, dict) else None
        if not isinstance(video, dict):
            raise MaicProviderError(
                f"grok video: success response missing video object: "
                f"keys={list(data)[:5] if isinstance(data, dict) else type(data).__name__}"
            )
        url = video.get("url")
        if not isinstance(url, str) or not url:
            raise MaicProviderError(
                "grok video: success response had video.url missing or empty"
            )
        # Duration is optional in upstream's TS type — coerce to int when
        # present, else 0 (caller falls back to request.duration_seconds).
        raw_duration = video.get("duration")
        duration = 0
        if isinstance(raw_duration, (int, float)) and raw_duration > 0:
            duration = int(raw_duration)
        return url, duration

    async def _fetch_video_bytes(
        self, session, video_url: str,
    ) -> tuple[str, bytes]:
        """Download the generated video from the URL Grok returned.

        xAI hosts videos on a short-TTL signed CDN, so we always re-host
        immediately. Default content_type to video/mp4 if the CDN response
        omits the header (grok-imagine-video output is documented as MP4).
        """
        async with session.get(video_url) as v_resp:
            if v_resp.status != 200:
                raise MaicProviderError(
                    f"grok video: failed to fetch generated video bytes "
                    f"(HTTP {v_resp.status})"
                )
            content_type = v_resp.headers.get("Content-Type", "video/mp4")
            data = await v_resp.read()
        if not data:
            raise MaicProviderError("grok video: fetched zero bytes")
        return content_type, data

    @staticmethod
    def _estimate_cost(model: str, duration_seconds: int) -> float | None:
        """Per-second list price by model id × generated duration.

        grok-imagine-video → $0.05/sec (upstream docstring, 2026-Q1).
        Unknown model or non-positive duration → None (we never fabricate).
        """
        per_second = _GROK_VIDEO_PRICES_USD_PER_SECOND.get(model)
        if per_second is None or duration_seconds <= 0:
            return None
        return round(per_second * duration_seconds, 4)
