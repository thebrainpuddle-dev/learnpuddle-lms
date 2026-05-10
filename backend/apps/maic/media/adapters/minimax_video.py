"""Minimax video generation adapter — MAIC-912 (Phase 9, first video adapter).

Source: THU-MAIC/OpenMAIC lib/media/adapters/minimax-video-adapter.ts
        (read for HTTP contract; re-implemented in Python per ADR-001a —
        no AGPL code import).
Sibling: apps/maic/media/adapters/minimax_image.py (MAIC-906) — same
        provider, same auth flow, same ``base_resp`` envelope handling,
        same env-var fallback pattern. The only structural delta is the
        3-step async lifecycle described below.
Polling template: apps/maic/media/adapters/qwen_image.py (MAIC-904) —
        the deadline-bounded polling helper; we reuse the pattern but
        the cadence and terminal-status names are Minimax-specific.

THE 3-STEP ASYNC FLOW (most procedurally complex adapter in Phase 9):

  Step 1 — Submit:
      POST {base}/video_generation
          body = {model, prompt, duration, resolution, prompt_optimizer:false}
          headers = {Authorization, Content-Type: application/json; charset=utf-8}
      → 200 + body {task_id, base_resp: {status_code, status_msg}}
      base_resp.status_code check (Minimax-style envelope).

  Step 2 — Poll task status:
      GET {base}/query/video_generation?task_id=<id>
      → 200 + body {task_id, status: "Preparing"|"Queueing"|"Processing"|
                   "Success"|"Fail", file_id?, video_width?, video_height?,
                   base_resp: {...}}
      Capitalisation matters — upstream emits TitleCase (NOT UPPERCASE
      like DashScope's task_status). Keep polling on Preparing /
      Queueing / Processing. Terminal Success → extract file_id.
      Terminal Fail / anything else → MaicProviderError. base_resp
      envelope-check at every poll response.

  Step 3 — File retrieve:
      GET {base}/files/retrieve?file_id=<id>
      → 200 + body {file: {file_id, download_url, filename}, base_resp:{...}}
      base_resp envelope-check. Extract file.download_url defensively.

  Step 4 — Download bytes:
      GET <download_url> (already-signed Minimax CDN URL)
      → video bytes. upload_media re-hosts into our storage so the
      result URL outlives Minimax's short-TTL CDN.

base_resp envelope handling appears at THREE places (submit response,
each poll response, retrieve response) — this is documented loudly
because dropping it on any leg would silently mask auth/quota errors
behind transient-looking failures.

Used by:
  - apps/maic/media/orchestrator.py — calls .generate() after resolving
    this adapter via resolve_video_provider with video_provider="minimax_video"
  - apps/maic/media/views.py — POST /api/maic/v2/media/generate-video/

Discipline (mirrors minimax_image + qwen_image):
  - aiohttp imported lazily inside generate() so tests can inject a
    fake via monkeypatch.setitem(sys.modules, "aiohttp", fake).
  - SSRF guard on tenant-supplied base_url (skipped for the default URL).
  - Env-var fallback for api_key — MINIMAX_API_KEY when the tenant key
    is empty AND allow_env_key_fallback is not explicitly False (Phase
    5 TTS pattern; same code reused across image + video Minimax adapters).
  - HTTP-class error split at every HTTP step:
        401/403 → MaicConfigError (auth — orchestrator does NOT retry)
        429    → MaicProviderError (rate limited)
        4xx    → MaicProviderError
        5xx    → MaicProviderError
        ClientError → MaicProviderError (network)
        Parse failure → MaicProviderError
  - base_resp envelope split at EVERY HTTP step (submit, each poll,
    retrieve):
        1004 / 1008 / 2049 → MaicConfigError (auth class)
        other non-zero    → MaicProviderError
  - Polling has a HARD DEADLINE (``_poll_timeout_seconds``); no
    ``while True``; deadline re-checked before each GET and before each
    sleep. Video is slow — typical 30-180s for Hailuo — so the timeout
    is much wider than image (300s vs 100s).
  - Bounded error message truncation (200 chars).
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import ClassVar

from apps.maic.exceptions import MaicConfigError, MaicProviderError
from apps.maic.media.providers import MediaProviderAdapter, register_adapter
from apps.maic.media.storage import upload_media
from apps.maic.media.types import VideoGenerationRequest, VideoGenerationResult
from apps.integrations_chat.ssrf_guard import SSRFError, validate_webhook_host


logger = logging.getLogger(__name__)


# Minimax base_resp.status_code values that mean "the request will never
# succeed without operator intervention" (auth / quota class). Mapped to
# MaicConfigError so the orchestrator does NOT retry. Sourced from the
# Phase 5 TTS comment block (apps/maic/tts/service.py:380-395). Same
# account model, same error codes apply to the video endpoint family.
_MINIMAX_AUTH_CLASS_CODES: frozenset[int] = frozenset({
    1004,  # account auth failed / api key revoked
    1008,  # insufficient balance — operator must top up
    2049,  # invalid api key (often wrong region — see comment below)
})


# Task-status string values from the upstream contract. CAPITALISATION
# MATTERS — Minimax emits TitleCase (not UPPERCASE like DashScope's
# qwen task_status). Source: minimax-video-adapter.ts:28.
_TERMINAL_SUCCESS: frozenset[str] = frozenset({"Success"})
_TERMINAL_FAILURE: frozenset[str] = frozenset({"Fail"})
_IN_PROGRESS: frozenset[str] = frozenset({"Preparing", "Queueing", "Processing"})


# Mapping from VideoGenerationRequest.aspect_ratio to Minimax's
# resolution bucket. Minimax accepts resolution strings like "768P",
# "720P", "1080P" — there is no explicit width/height knob from the
# request model, so we pick a sensible default ("768P") and let
# tenant config override the model selection. This keeps the public
# request contract aligned with the Pydantic schema (aspect_ratio
# only) while still passing a valid resolution to the upstream API.
_DEFAULT_RESOLUTION: str = "768P"


@register_adapter
class MinimaxVideoAdapter(MediaProviderAdapter):
    """Minimax Video API adapter (MiniMax-Hailuo family, text-to-video).

    Reads from TenantAIConfig:
        video_api_key (decrypted) — preferred. Falls back to the
            ``MINIMAX_API_KEY`` env var if the tenant key is empty AND
            the tenant config does not set ``allow_env_key_fallback =
            False``. Same key as the Minimax image adapter and the
            Phase 5 Minimax TTS — Minimax issues one platform-wide key
            per account, so re-using is intentional.
        video_base_url — optional; defaults to api.minimaxi.com/v1.
            Three regional endpoints exist (api.minimaxi.com,
            api.minimax.chat, api.minimax.io); a key issued in one
            region returns 2049 against the others, so tenants in
            non-default regions MUST set this field.
        video_model — optional; defaults to "MiniMax-Hailuo-2.3" (the
            current generation as of upstream commit).

    Returns a VideoGenerationResult with a URL pointing to OUR storage
    (not Minimax's CDN). The download_url Minimax returns is a signed
    URL with a short TTL — re-hosting is mandatory.
    """

    name: ClassVar[str] = "minimax_video"
    kind: ClassVar = "video"
    # Async-polling video generation needs significant headroom. Hailuo
    # typical latency is 30-90s with occasional 180s tails. 360s gives
    # the orchestrator a comfortable per-attempt budget that still fits
    # one retry inside a 10-minute scene-build target.
    default_timeout_seconds: ClassVar[int] = 360

    _DEFAULT_BASE_URL: ClassVar[str] = "https://api.minimaxi.com/v1"
    _DEFAULT_MODEL: ClassVar[str] = "MiniMax-Hailuo-2.3"
    _ENV_KEY_NAME: ClassVar[str] = "MINIMAX_API_KEY"

    # Polling cadence. ClassVar so tests can subclass and shorten
    # without re-implementing _poll_task_until_done. Real-world video
    # tasks take 30-180s, so a 5s poll interval keeps the round-trip
    # overhead low without spamming the upstream gateway.
    _poll_interval_seconds: ClassVar[float] = 5.0
    # Hard ceiling on time spent inside _poll_task_until_done. Set
    # comfortably below default_timeout_seconds (which includes submit
    # + retrieve + bytes-fetch on top of polling).
    _poll_timeout_seconds: ClassVar[float] = 300.0

    async def generate(self, req: VideoGenerationRequest) -> VideoGenerationResult:
        api_key = self._require_api_key()
        base_url = self._resolved_base_url()
        model = self._resolved_model()

        payload = {
            "model": model,
            "prompt": req.prompt,
            "duration": req.duration_seconds,
            "resolution": _DEFAULT_RESOLUTION,
            "prompt_optimizer": False,
        }

        # Lazy import — sys.modules patching in tests requires this.
        try:
            import aiohttp  # type: ignore[import-untyped]
        except ImportError as exc:
            raise MaicConfigError(
                "aiohttp is required for the Minimax video adapter; "
                "pip install aiohttp"
            ) from exc

        submit_headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json; charset=utf-8",
        }
        # Poll + retrieve only need Authorization (no Content-Type since
        # they are GETs). Minimax's gateway accepts a Content-Type on
        # GETs too but emits a noisy warning on some regional gateways,
        # so we omit it intentionally.
        get_headers = {
            "Authorization": f"Bearer {api_key}",
        }
        submit_endpoint = f"{base_url}/video_generation"

        try:
            async with aiohttp.ClientSession() as session:
                # ── Step 1: Submit ─────────────────────────────────────
                task_id = await self._submit_task(
                    session=session,
                    endpoint=submit_endpoint,
                    payload=payload,
                    headers=submit_headers,
                )

                # ── Step 2: Poll until terminal ────────────────────────
                file_id, video_meta = await self._poll_task_until_done(
                    session=session,
                    task_id=task_id,
                    headers=get_headers,
                    base_url=base_url,
                )

                # ── Step 3: Retrieve file URL ──────────────────────────
                download_url = await self._retrieve_file_url(
                    session=session,
                    file_id=file_id,
                    headers=get_headers,
                    base_url=base_url,
                )

                # ── Step 4: Download bytes ─────────────────────────────
                content_type, video_bytes = await self._fetch_video_bytes(
                    session, download_url,
                )
        except aiohttp.ClientError as exc:
            # DNS / connection reset / read error somewhere in the
            # submit-or-poll-or-retrieve-or-fetch chain — orchestrator
            # will retry. Submit is idempotent (gets a new task id);
            # retries during poll/retrieve simply re-submit.
            raise MaicProviderError(
                f"minimax video: network error talking to {submit_endpoint}: {exc}"
            ) from exc

        # Re-host bytes in our storage so the URL outlives Minimax's
        # short-TTL signed CDN URL.
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
            provider="minimax_video",
            model=model,
            duration_seconds=req.duration_seconds,
            latency_ms=0,  # orchestrator stamps the real value
            cost_usd_estimate=self._estimate_cost(
                model, req.duration_seconds, video_meta,
            ),
        )

    # ── Step 1: Submit ─────────────────────────────────────────────────

    async def _submit_task(
        self,
        *,
        session,
        endpoint: str,
        payload: dict,
        headers: dict[str, str],
    ) -> str:
        """POST the generation request. Returns the task id.

        base_resp envelope-check applies — even on HTTP 200, business
        logic errors (e.g. 1004 auth, 1008 quota) come back inside the
        envelope and must be promoted to typed exceptions before we
        try to read task_id from a failure body.
        """
        async with session.post(endpoint, json=payload, headers=headers) as resp:
            body_text = await resp.text()
            self._raise_for_status(resp.status, body_text, phase="submit")
            parsed = self._parse_response_json(body_text, phase="submit")

        # base_resp envelope (Minimax-specific) — HTTP 200 but
        # business-logic error.
        self._check_base_resp(parsed, phase="submit")

        return self._extract_task_id(parsed)

    # ── Step 2: Poll until done ────────────────────────────────────────

    async def _poll_task_until_done(
        self,
        *,
        session,
        task_id: str,
        headers: dict[str, str],
        base_url: str,
    ) -> tuple[str, dict]:
        """Poll Minimax's query endpoint until terminal.

        Bounded by ``self._poll_timeout_seconds``. The loop body re-
        checks the deadline BEFORE issuing each GET AND before each
        sleep — there is intentionally no ``while True``; the only way
        out is a terminal task status or the deadline tripping.

        Returns:
            (file_id, video_meta) — video_meta carries video_width /
            video_height so the cost estimator can use them later if a
            pricing table appears.

        Raises:
            MaicProviderError: task Fail / unrecognised status /
                response malformed / deadline exhausted.
            MaicConfigError: poll endpoint returned 401/403 or
                base_resp auth-class code (auth rotated mid-task — rare
                but possible).
        """
        loop = asyncio.get_event_loop()
        deadline = loop.time() + self._poll_timeout_seconds
        # NOTE: Minimax's poll endpoint uses query-string task_id, not
        # path-segment task_id like DashScope. Important difference
        # when reading the URL in logs.
        poll_endpoint = f"{base_url}/query/video_generation"

        attempt = 0
        while True:
            # Deadline check BEFORE the round-trip.
            if loop.time() >= deadline:
                raise MaicProviderError(
                    f"minimax video: polling timed out after "
                    f"{self._poll_timeout_seconds:.0f}s "
                    f"(task_id={task_id}, attempts={attempt})"
                )
            attempt += 1

            poll_url = f"{poll_endpoint}?task_id={task_id}"
            async with session.get(poll_url, headers=headers) as resp:
                body_text = await resp.text()
                self._raise_for_status(resp.status, body_text, phase="poll")
                parsed = self._parse_response_json(body_text, phase="poll")

            # base_resp envelope on the poll response (third place).
            self._check_base_resp(parsed, phase="poll")

            status = self._extract_task_status(parsed)

            if status in _TERMINAL_SUCCESS:
                file_id = self._extract_file_id(parsed)
                # Capture video_width / video_height for the cost
                # estimator. These can legitimately be missing on some
                # legacy responses — treat as optional.
                meta: dict = {}
                if isinstance(parsed, dict):
                    if isinstance(parsed.get("video_width"), int):
                        meta["video_width"] = parsed["video_width"]
                    if isinstance(parsed.get("video_height"), int):
                        meta["video_height"] = parsed["video_height"]
                return file_id, meta

            if status in _TERMINAL_FAILURE:
                # Surface upstream status_msg if Minimax provided one
                # — operators reading the failure ticket need the
                # reason (content moderation, quota, model worker
                # crash, etc.).
                base_resp = (
                    parsed.get("base_resp") if isinstance(parsed, dict) else None
                )
                msg = ""
                if isinstance(base_resp, dict):
                    msg = str(base_resp.get("status_msg") or "")
                detail = f" status_msg={msg[:200]!r}" if msg else ""
                raise MaicProviderError(
                    f"minimax video: task ended in non-success state "
                    f"{status!r} (task_id={task_id}){detail}"
                )

            if status not in _IN_PROGRESS:
                # Unknown status string — fail loud rather than spin. If
                # Minimax adds a new state, the operator will see this
                # in the error and decide whether to widen the set.
                raise MaicProviderError(
                    f"minimax video: unrecognised status {status!r} "
                    f"(task_id={task_id}); expected one of "
                    f"{sorted(_TERMINAL_SUCCESS | _TERMINAL_FAILURE | _IN_PROGRESS)}"
                )

            # Still Preparing / Queueing / Processing — wait then
            # re-check deadline so a long interval can't push us past
            # the cap silently.
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise MaicProviderError(
                    f"minimax video: polling timed out after "
                    f"{self._poll_timeout_seconds:.0f}s "
                    f"(task_id={task_id}, attempts={attempt})"
                )
            sleep_for = min(self._poll_interval_seconds, remaining)
            await asyncio.sleep(sleep_for)

    # ── Step 3: Retrieve file URL ──────────────────────────────────────

    async def _retrieve_file_url(
        self,
        *,
        session,
        file_id: str,
        headers: dict[str, str],
        base_url: str,
    ) -> str:
        """GET /files/retrieve?file_id=<id> to resolve the CDN URL.

        Minimax separates "task succeeded with a file_id" (poll response)
        from "give me the actual download URL for that file_id" (this
        endpoint). The retrieve response carries its OWN base_resp
        envelope — third place we run the envelope check.

        Defends against:
          - missing ``file`` field (response shape drift)
          - missing ``file.download_url`` (server bug, partial response)
          - empty download_url string
        """
        retrieve_endpoint = f"{base_url}/files/retrieve"
        url = f"{retrieve_endpoint}?file_id={file_id}"
        async with session.get(url, headers=headers) as resp:
            body_text = await resp.text()
            self._raise_for_status(resp.status, body_text, phase="retrieve")
            parsed = self._parse_response_json(body_text, phase="retrieve")

        # base_resp envelope on the retrieve response (third place).
        self._check_base_resp(parsed, phase="retrieve")

        return self._extract_download_url(parsed)

    # ── Step 4: Fetch bytes ────────────────────────────────────────────

    async def _fetch_video_bytes(
        self, session, download_url: str,
    ) -> tuple[str, bytes]:
        """Download the generated video bytes.

        Minimax hosts on a short-TTL signed CDN; always re-host
        immediately. Default content-type to video/mp4 (Minimax's
        encoding) if the CDN omits the header.
        """
        async with session.get(download_url) as resp:
            if resp.status != 200:
                raise MaicProviderError(
                    f"minimax video: failed to fetch generated video bytes "
                    f"(HTTP {resp.status})"
                )
            content_type = resp.headers.get("Content-Type", "video/mp4")
            data = await resp.read()
        if not data:
            raise MaicProviderError("minimax video: fetched zero bytes")
        return content_type, data

    # ── Internals ──────────────────────────────────────────────────────

    def _require_api_key(self) -> str:
        """Resolve the API key, honouring tenant-then-env fallback.

        Phase 5 TTS pattern + sibling Minimax image adapter pattern —
        same code, same opt-out. Tenants that explicitly forbid env
        fallback (enterprise isolation requirement) set
        ``allow_env_key_fallback = False`` on TenantAIConfig.
        """
        api_key = self.tenant_config.get_video_api_key() or ""
        if api_key:
            return api_key

        allow_env = getattr(self.tenant_config, "allow_env_key_fallback", True)
        if allow_env:
            env_key = os.environ.get(self._ENV_KEY_NAME, "") or ""
            if env_key:
                return env_key

        raise MaicConfigError(
            "minimax video: api_key required (set video_api_key on "
            "TenantAIConfig via set_video_api_key(), or set "
            f"{self._ENV_KEY_NAME} in the environment, or set "
            "video_provider='disabled' to skip video generation)"
        )

    def _resolved_model(self) -> str:
        raw = (self.tenant_config.video_model or "").strip()
        return raw or self._DEFAULT_MODEL

    def _resolved_base_url(self) -> str:
        """Pick base URL, validate with SSRF guard if customised.

        Default URL skips the guard (no point DNS-resolving our own
        known endpoint twice per call). Custom URLs MUST go through
        the guard — same rule as every other adapter."""
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
                f"minimax video: video_base_url failed SSRF check: {exc}"
            ) from exc
        return base

    @staticmethod
    def _raise_for_status(status: int, body: str, *, phase: str) -> None:
        """Translate HTTP status into typed exceptions.

        ``phase`` is "submit" / "poll" / "retrieve" — embedded in the
        error message so operators reading logs can tell which leg of
        the call failed. All three phases use the same mapping
        (Minimax's gateway returns the same 401/403/429/5xx shape for
        all three endpoints).
        """
        if 200 <= status < 300:
            return
        snippet = body[:200] if body else ""
        if status in (401, 403):
            raise MaicConfigError(
                f"minimax video: auth failed during {phase} (HTTP {status}): {snippet}"
            )
        if status == 429:
            raise MaicProviderError(
                f"minimax video: rate limited during {phase} (HTTP 429): {snippet}"
            )
        if 400 <= status < 500:
            raise MaicProviderError(
                f"minimax video: client error during {phase} (HTTP {status}): {snippet}"
            )
        # 5xx
        raise MaicProviderError(
            f"minimax video: server error during {phase} (HTTP {status}): {snippet}"
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
                f"minimax video: malformed JSON response during {phase}: {exc}"
            ) from exc

    @staticmethod
    def _check_base_resp(data: dict, *, phase: str) -> None:
        """Minimax wraps business-logic errors in a 200 HTTP response
        with a ``base_resp`` envelope. Non-zero status_code is a failure.

        Auth-class codes (1004, 1008, 2049) → MaicConfigError so the
        orchestrator does NOT retry — operator action required (rotate
        key, top up credits, change region).

        Other non-zero codes → MaicProviderError (could be transient
        rate limiting, server fault, etc.).

        ``phase`` is "submit" / "poll" / "retrieve" — embedded in the
        message so operators can tell which leg failed.
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
        msg_snippet = str(msg)[:200]
        if isinstance(code, int) and code in _MINIMAX_AUTH_CLASS_CODES:
            raise MaicConfigError(
                f"minimax video: auth/quota error {code} during {phase}: {msg_snippet}"
            )
        raise MaicProviderError(
            f"minimax video: provider error {code} during {phase}: {msg_snippet}"
        )

    @staticmethod
    def _extract_task_id(data: dict) -> str:
        """Submit response shape: {task_id: "...", base_resp: {...}}.
        Defensive: missing/empty task_id → MaicProviderError so the
        orchestrator can retry."""
        try:
            task_id = data["task_id"]
        except (KeyError, TypeError) as exc:
            raise MaicProviderError(
                f"minimax video: submit response missing task_id: "
                f"{list(data)[:5] if isinstance(data, dict) else type(data).__name__}"
            ) from exc
        if not isinstance(task_id, str) or not task_id:
            raise MaicProviderError(
                "minimax video: submit response had task_id but it was empty"
            )
        return task_id

    @staticmethod
    def _extract_task_status(data: dict) -> str:
        """Poll response shape: {task_id, status: "Success"|"Fail"|...,
        file_id?, video_width?, video_height?, base_resp: {...}}.

        Missing/non-string status → MaicProviderError. We do NOT default
        to Processing (that would silently swallow an upstream contract
        change)."""
        try:
            status = data["status"]
        except (KeyError, TypeError) as exc:
            raise MaicProviderError(
                f"minimax video: poll response missing status: "
                f"{list(data)[:5] if isinstance(data, dict) else type(data).__name__}"
            ) from exc
        if not isinstance(status, str) or not status:
            raise MaicProviderError(
                "minimax video: poll response had status but it was empty"
            )
        return status

    @staticmethod
    def _extract_file_id(data: dict) -> str:
        """When status == Success, the response carries file_id. Minimax
        types file_id as ``string | number`` in some regions, so we
        coerce to str for the retrieve URL. Missing/empty → MaicProviderError."""
        if not isinstance(data, dict):
            raise MaicProviderError(
                f"minimax video: success response is not a dict: {type(data).__name__}"
            )
        file_id = data.get("file_id")
        if file_id is None:
            raise MaicProviderError(
                "minimax video: success response missing file_id"
            )
        # Coerce to string defensively — some regions return an int.
        coerced = str(file_id).strip()
        if not coerced:
            raise MaicProviderError(
                "minimax video: success response had file_id but it was empty"
            )
        return coerced

    @staticmethod
    def _extract_download_url(data: dict) -> str:
        """Retrieve response shape: {file: {file_id, download_url,
        filename}, base_resp: {...}}.

        Defends against shape drift: missing ``file``, missing
        ``download_url``, non-string url, empty url."""
        if not isinstance(data, dict):
            raise MaicProviderError(
                f"minimax video: retrieve response is not a dict: {type(data).__name__}"
            )
        file_obj = data.get("file")
        if not isinstance(file_obj, dict):
            raise MaicProviderError(
                f"minimax video: retrieve response missing 'file' object: "
                f"{list(data)[:5]}"
            )
        url = file_obj.get("download_url")
        if not isinstance(url, str) or not url:
            raise MaicProviderError(
                "minimax video: retrieve response missing file.download_url"
            )
        return url

    @staticmethod
    def _estimate_cost(model: str, duration_seconds: int, video_meta: dict) -> float | None:
        """No public pricing table for Minimax video in upstream code.
        Telemetry is non-blocking — return None rather than fabricate.
        Operators compute spend from the Minimax dashboard.

        Signature accepts video_meta (video_width/video_height) so a
        future pricing table can use them without changing the call
        site."""
        return None
