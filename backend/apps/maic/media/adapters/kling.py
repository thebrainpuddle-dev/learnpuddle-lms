"""Kling (Kuaishou) text-to-video adapter — MAIC-911.

Source: THU-MAIC/OpenMAIC lib/media/adapters/kling-adapter.ts (read for
        the upstream HTTP + JWT contract; re-implemented in Python per
        ADR-001a — no AGPL code import).
Golden async pattern: apps/maic/media/adapters/qwen_image.py (MAIC-904)
        — same submit-then-poll lifecycle, same SSRF guard, same upload_media
        re-host, same typed-error matrix. The only structural delta from
        Qwen is the JWT-signed auth (HS256 over a TWO-part credential)
        described below; everything else is mirrored.

**ASYNC-POLLING VIDEO ADAPTER.** Kling text-to-video tasks take 30s-5min,
so the polling helper here inherits from QwenImageAdapter's pattern but
the cadence is widened (5s interval, 9-min ceiling) per Phase 9's video
budget. The lifecycle is identical to Qwen:

  Step 1: POST {base}/v1/videos/text2video with a fresh JWT
          → response body has ``{code, data: {task_id, task_status}}``.
  Step 2: GET {base}/v1/videos/text2video/<task_id> every 5s with the
          same JWT (regenerated per submit; valid for 30 min, so a
          single submit-poll cycle never re-signs) until
          ``data.task_status`` is "succeed" / "failed".
  Step 3: when succeed, ``data.task_result.videos[0].url`` is the
          video URL. We GET that URL, read the bytes, re-host via
          upload_media, and return a VideoGenerationResult pointing
          at OUR storage.

**KLING AUTH — TWO SECRETS, ONE FIELD.** Kling uses an Access Key + Secret
Key pair to sign HS256 JWTs (`iss=access_key`, `exp=now+1800`, `nbf=now-5`,
secret=secret_key). TenantAIConfig.get_video_api_key() returns a single
string, so we encode both halves into that field as ``access:secret`` and
split at adapter init. Format violations raise MaicConfigError before any
network I/O — the adapter never silently downgrades to "use the whole
string as access key".

JWT is generated fresh on every ``generate()`` call. The 30-min validity
means a single submit + poll cycle (~5 min worst case) never re-signs,
but caching across calls would couple latency to clock skew and make the
retry semantics non-idempotent — so we don't.

Used by:
  - apps/maic/media/orchestrator.py — calls .generate() after resolving
    this adapter via resolve_video_provider with video_provider="kling"
  - apps/maic/media/views.py — POST /api/maic/v2/media/generate-video/

Discipline (mirrors MAIC-904 plus the JWT additions):
  - aiohttp imported lazily inside generate() so tests can inject a fake
    via monkeypatch.setitem(sys.modules, "aiohttp", fake) — same pattern
    Phase 5 Minimax TTS and MAIC-904 Qwen use.
  - SSRF guard on tenant-supplied base_url (skipped for default
    api.klingai.com — well-known public endpoint).
  - HTTP-class error split on BOTH submit AND every poll response:
      401/403 → MaicConfigError  (auth — orchestrator does NOT retry)
      429    → MaicProviderError (rate limited — retry)
      4xx    → MaicProviderError (other 4xx — likely transient)
      5xx    → MaicProviderError (server fault — retry)
      ClientError → MaicProviderError (network — retry)
      Parse failure → MaicProviderError (server returned bad shape)
  - Kling wraps responses in {code, message, data}: code != 0 inside
    a 2xx response is still a failure — surface as MaicProviderError so
    the orchestrator can retry (auth-class codes are caught at the HTTP
    layer first).
  - Polling has a HARD DEADLINE — uses asyncio.get_event_loop().time() +
    self._poll_timeout_seconds. We NEVER ``while True``; the loop body
    re-checks the deadline before sleeping AND before issuing the next
    GET. When the deadline trips we raise MaicProviderError.
  - Re-host bytes via upload_media so the storage URL outlives Kling's
    short-TTL CDN.
  - Bounded error-message truncation (200 chars) so adversarial servers
    can't blow up logs.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import ClassVar

from apps.maic.exceptions import MaicConfigError, MaicProviderError
from apps.maic.media.providers import MediaProviderAdapter, register_adapter
from apps.maic.media.storage import upload_media
from apps.maic.media.types import VideoGenerationRequest, VideoGenerationResult
from apps.integrations_chat.ssrf_guard import SSRFError, validate_webhook_host


logger = logging.getLogger(__name__)


# Kling task_status values, named exactly as the upstream API emits them
# (lowercase strings, distinct from DashScope's uppercase). Mapped to
# local categories so the polling loop has a tiny vocabulary.
# Source: https://docs.klingai.com/api (kling-adapter.ts mirror).
_TERMINAL_SUCCESS: frozenset[str] = frozenset({"succeed"})
_TERMINAL_FAILURE: frozenset[str] = frozenset({"failed"})
_IN_PROGRESS: frozenset[str] = frozenset({"submitted", "processing"})

# JWT validity window. 30 minutes is what the upstream TS reference uses
# and matches Kling's documented expectation. nbf is set 5 seconds in
# the past to absorb clock skew between us and Kling's gateway.
_JWT_EXP_SECONDS: int = 1800
_JWT_NBF_SKEW_SECONDS: int = 5


@register_adapter
class KlingVideoAdapter(MediaProviderAdapter):
    """Kling text-to-video adapter.

    Reads from TenantAIConfig:
        video_api_key (decrypted) — REQUIRED. **MUST** be in
            ``access_key:secret_key`` format. Anything without a ':'
            separator (or where either half is empty) raises
            MaicConfigError before any network I/O. The first ':' splits
            access from secret; secrets containing ':' work because we
            split on the first occurrence only.
        video_base_url — optional; defaults to api.klingai.com.
        video_model — optional; defaults to "kling-v1".

    Returns a VideoGenerationResult with a URL pointing to OUR storage
    (not Kling's CDN). Kling video URLs are short-TTL CDN links — we
    always re-host immediately.
    """

    name: ClassVar[str] = "kling"
    kind: ClassVar = "video"
    # Video generation tail latency is 1-5 minutes (Kling docs cite
    # 30s-3min for the v1 free tier, up to 5min for v1.6/v2 pro mode).
    # 600s gives the orchestrator headroom for the worst-case run.
    default_timeout_seconds: ClassVar[int] = 600

    _DEFAULT_BASE_URL: ClassVar[str] = "https://api.klingai.com"
    _DEFAULT_MODEL: ClassVar[str] = "kling-v1"

    # Polling cadence. Video tasks are slower than image (Qwen used 2s/100s);
    # we widen to 5s interval / 540s ceiling. Class-level constants so
    # tests can subclass and compress without re-implementing the helper.
    _poll_interval_seconds: ClassVar[float] = 5.0
    _poll_timeout_seconds: ClassVar[float] = 540.0

    async def generate(self, req: VideoGenerationRequest) -> VideoGenerationResult:
        access_key, secret_key = self._require_access_and_secret()
        base_url = self._resolved_base_url()
        model = self.tenant_config.video_model or self._DEFAULT_MODEL

        # Generate a fresh JWT per submit. Tokens live 30 min; a single
        # submit+poll cycle is < 10 min so we never re-sign mid-call.
        # We intentionally do NOT cache the token between generate() calls
        # — different exp per call is a property the tests verify, and
        # caching would couple correctness to wall-clock semantics.
        token = self._generate_jwt(access_key, secret_key)

        # Kling submit body shape — model_name (NOT 'model'), prompt,
        # negative_prompt, mode, duration as a STRING, aspect_ratio.
        # The string-typed duration is a Kling quirk worth flagging; their
        # gateway rejects integer durations.
        payload: dict = {
            "model_name": model,
            "prompt": req.prompt,
            "negative_prompt": "",
            "mode": "pro",
            "duration": str(req.duration_seconds),
            "aspect_ratio": req.aspect_ratio,
        }

        # Lazy import — sys.modules patching in tests requires this.
        try:
            import aiohttp  # type: ignore[import-untyped]
        except ImportError as exc:
            raise MaicConfigError(
                "aiohttp is required for the Kling video adapter; "
                "pip install aiohttp"
            ) from exc

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        # Auth-only headers for poll/bytes-fetch (no Content-Type on GETs).
        poll_headers = {"Authorization": f"Bearer {token}"}
        submit_endpoint = f"{base_url}/v1/videos/text2video"

        try:
            async with aiohttp.ClientSession() as session:
                # Step 1: submit.
                async with session.post(
                    submit_endpoint, json=payload, headers=headers,
                ) as resp:
                    body_text = await resp.text()
                    self._raise_for_status(resp.status, body_text, phase="submit")
                    parsed = self._parse_response_json(body_text, phase="submit")

                task_id = self._extract_task_id(parsed)

                # Step 2: poll until terminal — bounded by _poll_timeout_seconds.
                video_url, video_duration = await self._poll_task_until_done(
                    session=session,
                    task_id=task_id,
                    headers=poll_headers,
                    base_url=base_url,
                )

                # Step 3: fetch the generated bytes.
                content_type, video_bytes = await self._fetch_video_bytes(
                    session, video_url,
                )
        except aiohttp.ClientError as exc:
            raise MaicProviderError(
                f"kling video: network error talking to {submit_endpoint}: {exc}"
            ) from exc

        # Re-host the video in our storage so the URL outlives Kling's CDN TTL.
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
            provider="kling",
            model=model,
            duration_seconds=video_duration or req.duration_seconds,
            latency_ms=0,  # orchestrator stamps the real value
            cost_usd_estimate=self._estimate_cost(model, req.duration_seconds),
        )

    # ── Polling helper — same shape as QwenImageAdapter ─────────────────

    async def _poll_task_until_done(
        self,
        *,
        session,
        task_id: str,
        headers: dict[str, str],
        base_url: str,
    ) -> tuple[str, int | None]:
        """Poll Kling's task-status endpoint until terminal.

        Bounded by ``self._poll_timeout_seconds`` measured against the
        event-loop clock. The loop body checks the deadline BEFORE
        issuing each GET AND before each sleep — there is intentionally
        no ``while True`` here; the only way out is a terminal task
        status or the deadline tripping.

        Mapping:
            data.task_status == "succeed"
                → return (data.task_result.videos[0].url, duration_int)
            data.task_status == "failed"
                → raise MaicProviderError (surface task_status_msg if any)
            data.task_status in {"submitted", "processing"}
                → continue polling
            HTTP error during poll → typed exception per _raise_for_status
            unrecognised status → MaicProviderError (loud — better to fail
                  than spin)

        Returns:
            (video_url, duration_seconds_or_None). The duration is what
            Kling reports for the rendered clip; the adapter falls back
            to req.duration_seconds when Kling omits it.

        Raises:
            MaicProviderError: task failed, poll response malformed,
                deadline exhausted.
            MaicConfigError: poll endpoint returned 401/403 (auth rotated
                mid-task — exceedingly rare).
        """
        loop = asyncio.get_event_loop()
        deadline = loop.time() + self._poll_timeout_seconds
        poll_endpoint = f"{base_url}/v1/videos/text2video/{task_id}"

        attempt = 0
        while True:
            if loop.time() >= deadline:
                raise MaicProviderError(
                    f"kling video: polling timed out after "
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
                return self._extract_video_url_and_duration(parsed)

            if status in _TERMINAL_FAILURE:
                # Surface task_status_msg if Kling provided one — operators
                # need to know whether this was content policy, quota, or
                # an upstream model crash.
                data = parsed.get("data") if isinstance(parsed, dict) else None
                msg = ""
                if isinstance(data, dict):
                    msg = str(data.get("task_status_msg") or "")
                detail = f" msg={msg[:200]!r}" if msg else ""
                raise MaicProviderError(
                    f"kling video: task ended in non-success state "
                    f"{status!r} (task_id={task_id}){detail}"
                )

            if status not in _IN_PROGRESS:
                raise MaicProviderError(
                    f"kling video: unrecognised task_status {status!r} "
                    f"(task_id={task_id}); expected one of "
                    f"{sorted(_TERMINAL_SUCCESS | _TERMINAL_FAILURE | _IN_PROGRESS)}"
                )

            remaining = deadline - loop.time()
            if remaining <= 0:
                raise MaicProviderError(
                    f"kling video: polling timed out after "
                    f"{self._poll_timeout_seconds:.0f}s "
                    f"(task_id={task_id}, attempts={attempt})"
                )
            sleep_for = min(self._poll_interval_seconds, remaining)
            await asyncio.sleep(sleep_for)

    # ── JWT generation ─────────────────────────────────────────────────

    @staticmethod
    def _generate_jwt(access_key: str, secret_key: str) -> str:
        """Sign an HS256 JWT for Kling auth.

        Claims (per upstream contract — see lib/media/adapters/kling-adapter.ts):
            iss: access_key
            exp: now + 1800
            nbf: now - 5
            iat: now  (added for parity with the TS reference; Kling
                  ignores it but it makes signed tokens introspectable)

        Uses PyJWT (already in requirements.txt as PyJWT==2.12.0). If the
        import ever breaks, the fallback is a 15-line hmac-based signer;
        we don't ship that today because the requirement is stable.
        """
        try:
            import jwt  # type: ignore[import-untyped]
        except ImportError as exc:  # pragma: no cover — PyJWT is a hard dep
            raise MaicConfigError(
                "PyJWT is required for the Kling video adapter; "
                "pip install PyJWT"
            ) from exc

        now = int(time.time())
        payload = {
            "iss": access_key,
            "exp": now + _JWT_EXP_SECONDS,
            "nbf": now - _JWT_NBF_SKEW_SECONDS,
            "iat": now,
        }
        # PyJWT returns str in 2.x; cast defensively in case a future
        # version reverts to bytes.
        token = jwt.encode(payload, secret_key, algorithm="HS256")
        return token.decode("utf-8") if isinstance(token, bytes) else token

    # ── Internals ──────────────────────────────────────────────────────

    def _require_access_and_secret(self) -> tuple[str, str]:
        """Pull the credential off TenantAIConfig, validate format, split.

        Kling uses TWO secrets (access_key + secret_key); TenantAIConfig
        only has one ``video_api_key`` slot, so we encode both as
        ``access:secret``. Anything that isn't in that exact shape is a
        configuration error — fail loud BEFORE making any network call.

        We split on the FIRST ':' so secrets containing additional ':'
        characters work. Both halves must be non-empty after stripping
        — an all-whitespace half is just as broken as an empty one.
        """
        raw = self.tenant_config.get_video_api_key()
        if not raw:
            raise MaicConfigError(
                "kling video: api_key required (set video_api_key on "
                "TenantAIConfig via set_video_api_key() in "
                "'access_key:secret_key' format), or set "
                "video_provider='disabled' to skip video generation"
            )
        sep = raw.find(":")
        if sep <= 0 or sep >= len(raw) - 1:
            raise MaicConfigError(
                "kling video: api_key must be in 'access_key:secret_key' "
                "format (single colon separator, both halves non-empty); "
                "got a value without that shape"
            )
        access = raw[:sep].strip()
        secret = raw[sep + 1:].strip()
        if not access or not secret:
            raise MaicConfigError(
                "kling video: api_key must be in 'access_key:secret_key' "
                "format with non-empty halves; one side was empty after "
                "stripping whitespace"
            )
        return access, secret

    def _resolved_base_url(self) -> str:
        """Pick base URL, validate with SSRF guard if customised.

        Default URL skips the guard (well-known Kling endpoint, no point
        DNS-resolving it twice per request). Custom URLs (self-hosted
        proxy, regional override, mock server) MUST go through the
        guard — same rule as every other adapter.
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
                f"kling video: video_base_url failed SSRF check: {exc}"
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
                f"kling video: auth failed during {phase} (HTTP {status}): {snippet}"
            )
        if status == 429:
            raise MaicProviderError(
                f"kling video: rate limited during {phase} (HTTP 429): {snippet}"
            )
        if 400 <= status < 500:
            raise MaicProviderError(
                f"kling video: client error during {phase} (HTTP {status}): {snippet}"
            )
        raise MaicProviderError(
            f"kling video: server error during {phase} (HTTP {status}): {snippet}"
        )

    @staticmethod
    def _parse_response_json(body: str, *, phase: str) -> dict:
        """Defensive JSON parse — raise MaicProviderError on malformed
        body so the orchestrator can retry."""
        import json
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise MaicProviderError(
                f"kling video: malformed JSON response during {phase}: {exc}"
            ) from exc

    @staticmethod
    def _check_kling_code(parsed: dict, *, phase: str) -> None:
        """Kling wraps every 2xx response in {code, message, data}.

        code == 0 means success; anything else is a logical error even
        when the HTTP status is 200. The auth-class codes (1000+) usually
        come with a 401/403 already (caught upstream in _raise_for_status);
        this layer catches the cases where Kling returns 200 + a non-zero
        code (validation failures, quota, etc.).
        """
        if not isinstance(parsed, dict):
            raise MaicProviderError(
                f"kling video: {phase} response not a JSON object"
            )
        code = parsed.get("code")
        if code in (0, None):
            # None is permissive: if Kling rolls out a new envelope, we
            # don't want this guard to false-positive. The downstream
            # data-shape checks will catch real breakage.
            return
        message = str(parsed.get("message") or "")[:200]
        raise MaicProviderError(
            f"kling video: {phase} returned error code={code} "
            f"message={message!r}"
        )

    @classmethod
    def _extract_task_id(cls, data: dict) -> str:
        """Kling submit response shape: {code: 0, message: "SUCCESS",
        data: {task_id: "...", task_status: "submitted", ...}}.

        Defensive: missing/empty task_id → MaicProviderError so the
        orchestrator can retry the submit (submits are idempotent).
        """
        cls._check_kling_code(data, phase="submit")
        try:
            task_id = data["data"]["task_id"]
        except (KeyError, TypeError) as exc:
            raise MaicProviderError(
                f"kling video: submit response missing data.task_id: "
                f"{list(data)[:5] if isinstance(data, dict) else type(data).__name__}"
            ) from exc
        if not isinstance(task_id, str) or not task_id:
            raise MaicProviderError(
                "kling video: submit response had data.task_id but it was empty"
            )
        return task_id

    @classmethod
    def _extract_task_status(cls, data: dict) -> str:
        """Poll response shape: {code: 0, data: {task_id, task_status,
        task_status_msg?, task_result?: {videos: [...]}}}.

        Missing/non-string status → MaicProviderError. We do NOT default
        to 'processing' (that would silently swallow a contract change).
        """
        cls._check_kling_code(data, phase="poll")
        try:
            status = data["data"]["task_status"]
        except (KeyError, TypeError) as exc:
            raise MaicProviderError(
                f"kling video: poll response missing data.task_status: "
                f"{list(data)[:5] if isinstance(data, dict) else type(data).__name__}"
            ) from exc
        if not isinstance(status, str) or not status:
            raise MaicProviderError(
                "kling video: poll response had data.task_status but it was empty"
            )
        return status

    @staticmethod
    def _extract_video_url_and_duration(data: dict) -> tuple[str, int | None]:
        """When succeed, the URL is at data.task_result.videos[0].url.

        videos is in principle a list (Kling could return multiple
        renders); we always submit one prompt so it's always one entry.
        Duration is returned as a string per Kling's contract; we
        int-cast where possible and fall back to None when the field is
        missing or non-numeric.
        """
        try:
            videos = data["data"]["task_result"]["videos"]
            first = videos[0]
        except (KeyError, IndexError, TypeError) as exc:
            raise MaicProviderError(
                f"kling video: success response missing "
                f"data.task_result.videos[0]: "
                f"{list(data)[:5] if isinstance(data, dict) else type(data).__name__}"
            ) from exc
        url = first.get("url") if isinstance(first, dict) else None
        if not isinstance(url, str) or not url:
            raise MaicProviderError(
                "kling video: videos[0].url missing or empty"
            )
        duration_raw = first.get("duration") if isinstance(first, dict) else None
        duration: int | None
        try:
            duration = int(float(duration_raw)) if duration_raw is not None else None
        except (TypeError, ValueError):
            duration = None
        return url, duration

    async def _fetch_video_bytes(
        self, session, video_url: str,
    ) -> tuple[str, bytes]:
        """Download the generated video from the URL Kling returned.

        Kling hosts videos on a short-TTL CDN; re-hosting is mandatory.
        Default content_type to video/mp4 if the CDN response omits the
        header (mp4 is Kling's documented output container).
        """
        async with session.get(video_url) as vid_resp:
            if vid_resp.status != 200:
                raise MaicProviderError(
                    f"kling video: failed to fetch generated video bytes "
                    f"(HTTP {vid_resp.status})"
                )
            content_type = vid_resp.headers.get("Content-Type", "video/mp4")
            data = await vid_resp.read()
        if not data:
            raise MaicProviderError("kling video: fetched zero bytes")
        return content_type, data

    @staticmethod
    def _estimate_cost(model: str, duration_seconds: int) -> float | None:
        """No stable public pricing for Kling — pricing is contract- and
        region-dependent, and changes with model tier ('std' vs 'pro').
        Telemetry is non-blocking, so a missing cost is fine — operators
        compute spend from the Kling console.
        """
        return None
