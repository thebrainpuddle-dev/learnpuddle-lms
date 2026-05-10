"""Qwen (Alibaba DashScope) image generation adapter — MAIC-904.

Source: THU-MAIC/OpenMAIC lib/media/adapters/qwen-image-adapter.ts (read for
        upstream HTTP contract; re-implemented in Python per ADR-001a — no
        AGPL code import).
Golden pattern: apps/maic/media/adapters/openai_image.py (MAIC-903) — same
        class shape, same error matrix, same SSRF guard, same upload_media
        re-host. The only structural delta from the golden pattern is the
        async-polling lifecycle described below; everything else is mirrored.

**THIS IS THE FIRST ASYNC-POLLING ADAPTER.** Phase 9's video adapters (Veo,
Kling, Minimax-video) will copy the polling helper here. If something here
is wrong, the bug replicates ×3+ — so the pattern is documented loud:

  Step 1: POST {base}/services/aigc/text2image/image-synthesis
          with header ``X-DashScope-Async: enable``
          → response body has ``{output: {task_id: "<id>"}}``
  Step 2: GET {base}/tasks/<task_id> every 2s until
          ``output.task_status`` is SUCCEEDED / FAILED / CANCELED.
          PENDING + RUNNING mean "keep polling". UNKNOWN means
          "something is broken upstream — fail loud, do not retry".
  Step 3: when SUCCEEDED, ``output.results[0].url`` is the image URL.
          We GET that URL, read the bytes, re-host via upload_media,
          and return an ImageGenerationResult pointing at OUR storage.

Used by:
  - apps/maic/media/orchestrator.py — calls .generate() after resolving
    this adapter via resolve_image_provider with image_provider="qwen"
  - apps/maic/media/views.py — POST /api/maic/v2/media/generate-image/

Discipline (mirrors MAIC-903 plus the polling additions):
  - aiohttp imported lazily inside generate() so tests can inject a fake
    via monkeypatch.setitem(sys.modules, "aiohttp", fake) — exact pattern
    Phase 5 Minimax TTS uses.
  - SSRF guard on tenant-supplied base_url (skipped for default
    dashscope.aliyuncs.com URL — well-known public endpoint).
  - HTTP-class error split on BOTH submit AND every poll response:
      401/403 → MaicConfigError  (auth — orchestrator does NOT retry)
      429    → MaicProviderError (rate limited — retry)
      4xx    → MaicProviderError (other 4xx — likely transient)
      5xx    → MaicProviderError (server fault — retry)
      ClientError → MaicProviderError (network — retry)
      Parse failure → MaicProviderError (server returned bad shape)
  - Polling has a HARD DEADLINE — uses asyncio.get_event_loop().time() +
    self._poll_timeout_seconds. We NEVER ``while True``; the loop body
    re-checks the deadline before sleeping AND before issuing the next
    GET. When the deadline trips we raise MaicProviderError so the
    orchestrator can retry the whole submit cycle (idempotent submits
    just produce a new task id).
  - Re-host bytes via upload_media so the storage URL outlives Alibaba's
    short-TTL CDN.
  - Bounded error message truncation (200 chars) so adversarial servers
    can't blow up logs.

Subclassing note: ``_poll_interval_seconds`` and ``_poll_timeout_seconds``
are ClassVars so future async video adapters can subclass and override
the cadence without re-implementing _poll_task_until_done. Video tasks
typically take 30-180s vs image ~5-15s, so the timeouts will differ.
"""
from __future__ import annotations

import asyncio
import logging
from typing import ClassVar

from apps.maic.exceptions import MaicConfigError, MaicProviderError
from apps.maic.media.providers import MediaProviderAdapter, register_adapter
from apps.maic.media.storage import upload_media
from apps.maic.media.types import ImageGenerationRequest, ImageGenerationResult
from apps.integrations_chat.ssrf_guard import SSRFError, validate_webhook_host


logger = logging.getLogger(__name__)


# DashScope task_status values, named exactly as the upstream API emits them.
# Source: https://help.aliyun.com/zh/model-studio/developer-reference/text-to-image
# Mapped to local categories so the polling loop has a tiny vocabulary.
_TERMINAL_SUCCESS: frozenset[str] = frozenset({"SUCCEEDED"})
_TERMINAL_FAILURE: frozenset[str] = frozenset({"FAILED", "CANCELED", "UNKNOWN"})
_IN_PROGRESS: frozenset[str] = frozenset({"PENDING", "RUNNING"})


@register_adapter
class QwenImageAdapter(MediaProviderAdapter):
    """Alibaba DashScope (Qwen / Wanx / Wan) Images API adapter.

    Reads from TenantAIConfig:
        image_api_key (decrypted) — required; MaicConfigError if missing.
            DashScope's canonical env var is DASHSCOPE_API_KEY but we
            require a per-tenant key (no env fallback) — this is the
            golden pattern, not the minimax pattern. Tenants that want
            env-var fallback should ask explicitly; defaulting to it on
            a multi-tenant LMS would leak the operator's personal key
            across courses.
        image_base_url — optional; defaults to dashscope.aliyuncs.com/api/v1
        image_model — optional; defaults to "wanx-v1" (the long-standing
            free-tier text-to-image model). For higher quality, tenants
            can set "wan2.2-t2i-flash" or "wan2.2-t2i-plus".

    Returns an ImageGenerationResult with a URL pointing to OUR storage
    (not DashScope's CDN). DashScope result URLs are short-TTL signed
    OSS URLs — usually 24h — so re-hosting is mandatory.
    """

    name: ClassVar[str] = "qwen"
    kind: ClassVar = "image"
    # Async polling needs more headroom than sync providers (the 60s default
    # for synchronous adapters would barely fit a single Wanx generation;
    # 120s lets the orchestrator finish on the first attempt for the common
    # 5-25s case AND ride out the occasional 60-90s tail).
    default_timeout_seconds: ClassVar[int] = 120

    _DEFAULT_BASE_URL: ClassVar[str] = "https://dashscope.aliyuncs.com/api/v1"
    _DEFAULT_MODEL: ClassVar[str] = "wanx-v1"

    # Polling cadence. ClassVar so subclasses (video adapters) can override
    # without copying the polling helper. The numbers below are tuned for
    # image generation (5-30s typical, occasional 60-90s tail). Video
    # subclasses will widen these.
    _poll_interval_seconds: ClassVar[float] = 2.0
    # Hard ceiling on time spent in _poll_task_until_done. Distinct from the
    # adapter's default_timeout_seconds (which is the orchestrator's
    # per-attempt cap including submit + bytes fetch). Setting this slightly
    # under default_timeout_seconds leaves headroom for the bytes fetch.
    _poll_timeout_seconds: ClassVar[float] = 100.0

    async def generate(self, req: ImageGenerationRequest) -> ImageGenerationResult:
        api_key = self._require_api_key()
        base_url = self._resolved_base_url()
        model = self.tenant_config.image_model or self._DEFAULT_MODEL

        # DashScope's text2image submit body shape — input/parameters split
        # is the DashScope convention (different from OpenAI's flat body).
        # We always request n=1; multi-image batches aren't part of the
        # adapter contract (orchestrator schedules N parallel calls instead).
        payload = {
            "model": model,
            "input": {
                "prompt": req.prompt,
            },
            "parameters": {
                "size": f"{req.width}*{req.height}",  # NOTE: '*' not 'x'
                "n": 1,
            },
        }

        # Lazy import — sys.modules patching in tests requires this. If we
        # imported aiohttp at the top of the module, tests couldn't inject
        # a fake.
        try:
            import aiohttp  # type: ignore[import-untyped]
        except ImportError as exc:
            raise MaicConfigError(
                "aiohttp is required for the Qwen image adapter; "
                "pip install aiohttp"
            ) from exc

        # X-DashScope-Async: enable is what makes this an async-polling
        # call. Without that header the same endpoint refuses to accept
        # the request for the wanx/wan models. The poll endpoint does
        # NOT need this header.
        submit_headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "X-DashScope-Async": "enable",
        }
        poll_headers = {
            "Authorization": f"Bearer {api_key}",
        }
        submit_endpoint = f"{base_url}/services/aigc/text2image/image-synthesis"

        try:
            async with aiohttp.ClientSession() as session:
                # Step 1: submit
                async with session.post(
                    submit_endpoint, json=payload, headers=submit_headers,
                ) as resp:
                    body_text = await resp.text()
                    self._raise_for_status(resp.status, body_text, phase="submit")
                    parsed = self._parse_response_json(body_text, phase="submit")

                task_id = self._extract_task_id(parsed)

                # Step 2: poll until terminal — bounded by _poll_timeout_seconds.
                # The helper is a method (not module-level) so video subclasses
                # can override the cadence without re-implementing.
                image_url = await self._poll_task_until_done(
                    session=session,
                    task_id=task_id,
                    headers=poll_headers,
                    base_url=base_url,
                )

                # Step 3: fetch the generated bytes.
                content_type, image_bytes = await self._fetch_image_bytes(
                    session, image_url,
                )
        except aiohttp.ClientError as exc:
            # DNS / connection reset / read error somewhere in the
            # submit-or-poll-or-fetch chain — orchestrator will retry.
            raise MaicProviderError(
                f"qwen image: network error talking to {submit_endpoint}: {exc}"
            ) from exc

        # Re-host the image in our storage so the URL outlives DashScope's
        # short-TTL OSS URL (signed URLs typically expire in 24h).
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
            provider="qwen",
            model=model,
            latency_ms=0,  # orchestrator stamps the real value
            cost_usd_estimate=self._estimate_cost(model, req.width, req.height, req.quality),
        )

    # ── Polling helper — the new pattern future async adapters will copy ─

    async def _poll_task_until_done(
        self,
        *,
        session,
        task_id: str,
        headers: dict[str, str],
        base_url: str,
    ) -> str:
        """Poll DashScope's task-status endpoint until terminal.

        Bounded by ``self._poll_timeout_seconds`` measured against the
        event-loop clock. The loop body checks the deadline BEFORE
        issuing each GET AND before each sleep — there is intentionally
        no ``while True`` here; the only way out is a terminal task
        status or the deadline tripping.

        Mapping:
            output.task_status == "SUCCEEDED"
                → return output.results[0].url
            output.task_status in {"FAILED", "CANCELED", "UNKNOWN"}
                → raise MaicProviderError (orchestrator may retry the
                  submit — submits are idempotent, FAILED on retry will
                  fail again but bounded)
            output.task_status in {"PENDING", "RUNNING"}
                → continue polling
            HTTP error during poll → typed exception per _raise_for_status
            unrecognised status → MaicProviderError (loud — better to fail
                  than spin)

        Returns:
            The image URL from output.results[0].url.

        Raises:
            MaicProviderError: task FAILED / CANCELED / UNKNOWN, poll
                response malformed, or polling exhausted the deadline.
            MaicConfigError: poll endpoint returned 401/403 (auth rotated
                mid-task — exceedingly rare but possible).
        """
        loop = asyncio.get_event_loop()
        deadline = loop.time() + self._poll_timeout_seconds
        poll_endpoint = f"{base_url}/tasks/{task_id}"

        # Tracks iterations purely for the error message — bounded by
        # the deadline check, so this counter never approaches infinity.
        attempt = 0
        while True:
            # Deadline check BEFORE issuing the GET — if we're already past
            # the deadline, don't waste a round-trip; raise immediately.
            if loop.time() >= deadline:
                raise MaicProviderError(
                    f"qwen image: polling timed out after "
                    f"{self._poll_timeout_seconds:.0f}s "
                    f"(task_id={task_id}, attempts={attempt})"
                )
            attempt += 1

            async with session.get(poll_endpoint, headers=headers) as resp:
                body_text = await resp.text()
                self._raise_for_status(resp.status, body_text, phase="poll")
                parsed = self._parse_response_json(body_text, phase="poll")

            status = self._extract_task_status(parsed)

            if status in _TERMINAL_SUCCESS:
                return self._extract_image_url(parsed)

            if status in _TERMINAL_FAILURE:
                # Surface the upstream error message if DashScope provided one
                # — operators reading the failure ticket need to know whether
                # this was a content-policy block, a quota issue, or a model
                # crash.
                output = parsed.get("output") if isinstance(parsed, dict) else None
                if isinstance(output, dict):
                    code = output.get("code") or ""
                    message = output.get("message") or ""
                else:
                    code = ""
                    message = ""
                detail = f" code={code} message={str(message)[:200]}" if (code or message) else ""
                raise MaicProviderError(
                    f"qwen image: task ended in non-success state "
                    f"{status!r} (task_id={task_id}){detail}"
                )

            if status not in _IN_PROGRESS:
                # Unknown status string — fail loud rather than spin. If
                # DashScope adds a new state, the operator will see this
                # in the error and decide whether to widen the set.
                raise MaicProviderError(
                    f"qwen image: unrecognised task_status {status!r} "
                    f"(task_id={task_id}); expected one of "
                    f"{sorted(_TERMINAL_SUCCESS | _TERMINAL_FAILURE | _IN_PROGRESS)}"
                )

            # Still in PENDING / RUNNING — wait the configured interval
            # before re-polling. Re-check deadline AFTER sleep so a long
            # interval doesn't push us past the cap silently.
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise MaicProviderError(
                    f"qwen image: polling timed out after "
                    f"{self._poll_timeout_seconds:.0f}s "
                    f"(task_id={task_id}, attempts={attempt})"
                )
            sleep_for = min(self._poll_interval_seconds, remaining)
            await asyncio.sleep(sleep_for)

    # ── Internals ──────────────────────────────────────────────────────

    def _require_api_key(self) -> str:
        api_key = self.tenant_config.get_image_api_key()
        if not api_key:
            raise MaicConfigError(
                "qwen image: api_key required (set image_api_key on "
                "TenantAIConfig via set_image_api_key()), or set "
                "image_provider='disabled' to skip image generation"
            )
        return api_key

    def _resolved_base_url(self) -> str:
        """Pick base URL, validate with SSRF guard if customised.

        Default URL skips the guard (well-known DashScope endpoint —
        no point DNS-resolving it twice per request). Custom URLs
        (self-hosted proxy, regional override, mock server) MUST go
        through the guard — same rule as every other adapter."""
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
                f"qwen image: image_base_url failed SSRF check: {exc}"
            ) from exc
        return base

    @staticmethod
    def _raise_for_status(status: int, body: str, *, phase: str) -> None:
        """Translate HTTP status into typed exceptions.

        ``phase`` is "submit" or "poll" — embedded in the error message
        so operators reading logs can tell which leg of the call failed.
        Both phases use the same mapping (DashScope's gateway returns
        the same 401/403/429/5xx shape for both endpoints).
        """
        if 200 <= status < 300:
            return
        snippet = body[:200] if body else ""
        if status in (401, 403):
            raise MaicConfigError(
                f"qwen image: auth failed during {phase} (HTTP {status}): {snippet}"
            )
        if status == 429:
            raise MaicProviderError(
                f"qwen image: rate limited during {phase} (HTTP 429): {snippet}"
            )
        if 400 <= status < 500:
            # 4xx during submit: invalid prompt, model not enabled for
            # this account, etc. During poll: typically a stale/wrong
            # task id (404). Either way orchestrator may retry.
            raise MaicProviderError(
                f"qwen image: client error during {phase} (HTTP {status}): {snippet}"
            )
        # 5xx
        raise MaicProviderError(
            f"qwen image: server error during {phase} (HTTP {status}): {snippet}"
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
                f"qwen image: malformed JSON response during {phase}: {exc}"
            ) from exc

    @staticmethod
    def _extract_task_id(data: dict) -> str:
        """DashScope submit response shape: {output: {task_id: "...",
        task_status: "PENDING"}, request_id: "..."}. The task_status on
        the submit response is almost always PENDING; we ignore it and
        always proceed to the polling phase to keep the lifecycle uniform.

        Defensive: missing/empty task_id → MaicProviderError so the
        orchestrator can retry the submit."""
        try:
            task_id = data["output"]["task_id"]
        except (KeyError, TypeError) as exc:
            raise MaicProviderError(
                f"qwen image: submit response missing output.task_id: "
                f"{list(data)[:5] if isinstance(data, dict) else type(data).__name__}"
            ) from exc
        if not isinstance(task_id, str) or not task_id:
            raise MaicProviderError(
                "qwen image: submit response had output.task_id but it was empty"
            )
        return task_id

    @staticmethod
    def _extract_task_status(data: dict) -> str:
        """Poll response shape: {output: {task_id: "...", task_status:
        "SUCCEEDED"|"FAILED"|..., results: [...]}, request_id: "..."}.

        Missing/non-string status → MaicProviderError. We do NOT default
        to RUNNING (that would silently swallow an upstream contract
        change)."""
        try:
            status = data["output"]["task_status"]
        except (KeyError, TypeError) as exc:
            raise MaicProviderError(
                f"qwen image: poll response missing output.task_status: "
                f"{list(data)[:5] if isinstance(data, dict) else type(data).__name__}"
            ) from exc
        if not isinstance(status, str) or not status:
            raise MaicProviderError(
                "qwen image: poll response had output.task_status but it was empty"
            )
        return status

    @staticmethod
    def _extract_image_url(data: dict) -> str:
        """When SUCCEEDED, the URL is at output.results[0].url. The
        results array can in principle hold multiple images (we request
        n=1 so it's always one), and each entry can carry either a url
        or a code+message error pair (if upstream returned a partial
        failure for a specific image in a batch).

        Defensive shape checks — any deviation → MaicProviderError so
        the orchestrator can retry."""
        try:
            results = data["output"]["results"]
            first = results[0]
        except (KeyError, IndexError, TypeError) as exc:
            raise MaicProviderError(
                f"qwen image: success response missing output.results[0]: "
                f"{list(data)[:5] if isinstance(data, dict) else type(data).__name__}"
            ) from exc
        # Per-image error inside a SUCCEEDED task — DashScope occasionally
        # emits {code, message} instead of {url}. Treat as transient.
        if isinstance(first, dict) and (first.get("code") or first.get("message")) and not first.get("url"):
            raise MaicProviderError(
                f"qwen image: per-image error in successful task: "
                f"code={first.get('code')!r} message={str(first.get('message'))[:200]!r}"
            )
        url = first.get("url") if isinstance(first, dict) else None
        if not isinstance(url, str) or not url:
            raise MaicProviderError(
                "qwen image: results[0].url missing or empty"
            )
        return url

    async def _fetch_image_bytes(
        self, session, image_url: str,
    ) -> tuple[str, bytes]:
        """Download the generated image from the URL DashScope returned.

        DashScope hosts on signed OSS URLs with a 24h TTL; we always
        re-host immediately. Default content_type to image/png if the
        OSS response omits the header (Wanx output is PNG by default).
        """
        async with session.get(image_url) as img_resp:
            if img_resp.status != 200:
                raise MaicProviderError(
                    f"qwen image: failed to fetch generated image bytes "
                    f"(HTTP {img_resp.status})"
                )
            content_type = img_resp.headers.get("Content-Type", "image/png")
            data = await img_resp.read()
        if not data:
            raise MaicProviderError("qwen image: fetched zero bytes")
        return content_type, data

    @staticmethod
    def _estimate_cost(model: str, width: int, height: int, quality: str) -> float | None:
        """No pricing table available — DashScope pricing is regional and
        contract-dependent (free tier on wanx-v1 for new accounts; paid
        tiers for wan2.2 with prices that vary by region and resolution
        in ways the adapter can't reliably predict). Telemetry is
        non-blocking, so a missing cost is fine — operators compute
        spend from the DashScope console.
        """
        return None
