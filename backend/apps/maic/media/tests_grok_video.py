"""Tests for the Grok (xAI) video adapter (MAIC-913).

Mirrors the structure of tests_qwen_image.py (first async-polling adapter)
with the status vocabulary swapped to Grok's lowercase
"pending"/"done"/"failed", and the endpoint shapes swapped to xAI's
``/videos/generations`` (submit) and ``/videos/<request_id>`` (poll).

Discipline:
  - IO-boundary fake only: ``aiohttp`` is injected into ``sys.modules``
    via monkeypatch.setitem — same pattern as every other adapter test.
  - No mocks of GrokVideoAdapter itself. Real adapter, real Pydantic,
    real storage (Django default_storage / FileSystemStorage in tests).
  - Polling cadence is shortened to nearly-zero in test subclass; we
    deliberately do NOT monkeypatch asyncio.sleep — the deadline math
    is part of what's under test.
  - Live smoke gated on MAIC_GROK_VIDEO_LIVE_SMOKE=1 + GROK_API_KEY
    (reuses the image-side key since the upstream API is the same key
    space).

Uncertainty notes (per the upstream-contract caveats in the production
docstring):
  - Tests below that assert specific upstream-error detail strings are
    marked with "TODO verify against live API at cert time" comments —
    those assertions exercise OUR error-formatting behaviour against
    well-defined inputs, but the exact upstream payload shape on failure
    may carry additional fields we can't fully predict without a live
    failure response.
"""
from __future__ import annotations

import json
import os
import sys
import types
from types import SimpleNamespace

import pytest

from apps.maic.exceptions import MaicConfigError, MaicProviderError
from apps.maic.media.adapters.grok_video import GrokVideoAdapter
from apps.maic.media.types import VideoGenerationRequest


# ── Fake aiohttp infrastructure (IO-boundary only) ─────────────────────


class _FakeResp:
    """Stand-in for an aiohttp ClientResponse — async-context-manager
    that exposes status + headers + text/read/json."""

    def __init__(
        self,
        *,
        status: int = 200,
        body: bytes | str = b"",
        headers: dict[str, str] | None = None,
    ):
        self.status = status
        self._body = body.encode() if isinstance(body, str) else body
        self.headers = headers or {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def text(self) -> str:
        return self._body.decode("utf-8")

    async def read(self) -> bytes:
        return self._body

    async def json(self):
        return json.loads(self._body.decode("utf-8"))


class _FakeSession:
    """Stand-in for aiohttp.ClientSession.

    Supports a SEQUENCE of GET responses (poll loop + final bytes fetch):
        post_resp: single response for the submit POST
        poll_resps: list of responses for each /videos/<id> GET
            (consumed in order — index advances on each call)
        bytes_resp: response for the final non-/videos/<id> GET (the
            CDN bytes fetch).

    The fake detects which GET is which by URL pattern: the poll URL
    contains ``/videos/`` AND does NOT end in ``/generations``; bytes
    URLs come from the upstream response and won't match that pattern.
    """

    def __init__(
        self,
        *,
        post_resp: _FakeResp,
        poll_resps: list[_FakeResp] | None = None,
        bytes_resp: _FakeResp | None = None,
    ):
        self._post_resp = post_resp
        self._poll_resps = list(poll_resps or [])
        self._bytes_resp = bytes_resp or _FakeResp(
            status=200,
            body=b"MP4-bytes-fake",
            headers={"Content-Type": "video/mp4"},
        )
        self.last_post_url: str | None = None
        self.last_post_json: dict | None = None
        self.last_post_headers: dict | None = None
        self.last_get_urls: list[str] = []
        self.last_get_headers: list[dict | None] = []
        self.poll_index: int = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def post(self, url, json=None, headers=None):
        self.last_post_url = url
        self.last_post_json = json
        self.last_post_headers = headers
        return self._post_resp

    def get(self, url, headers=None):
        self.last_get_urls.append(url)
        self.last_get_headers.append(headers)
        # Poll URLs look like ``{base}/videos/<id>``. Submit endpoint is
        # ``{base}/videos/generations`` and is POST-only, so it won't
        # arrive here. CDN bytes URLs are arbitrary external URLs that
        # won't contain ``/videos/`` (in the test fixtures we use a
        # ``grok-cdn.example`` host).
        if "/videos/" in url and not url.endswith("/generations"):
            if self.poll_index >= len(self._poll_resps):
                raise AssertionError(
                    f"_FakeSession: polling GET #{self.poll_index + 1} but "
                    f"only {len(self._poll_resps)} poll responses provided. "
                    "Add more poll_resps or shorten the test."
                )
            resp = self._poll_resps[self.poll_index]
            self.poll_index += 1
            return resp
        # Non-poll GET — must be the final video-bytes fetch.
        return self._bytes_resp


class _FakeClientError(Exception):
    """Stand-in for aiohttp.ClientError."""


def _install_fake_aiohttp(monkeypatch, session: _FakeSession | None = None) -> _FakeSession:
    """Inject a fake aiohttp module. Returns the session so tests can
    assert on captured request shape."""
    if session is None:
        # Default: happy path — submit returns request_id, one poll returns
        # done, bytes fetch returns MP4.
        session = _FakeSession(
            post_resp=_FakeResp(
                status=200,
                body=json.dumps({"request_id": "req-abc-123"}),
            ),
            poll_resps=[
                _FakeResp(
                    status=200,
                    body=json.dumps({
                        "status": "done",
                        "progress": 100,
                        "video": {
                            "url": "https://grok-cdn.example/video-1.mp4",
                            "duration": 6,
                        },
                        "model": "grok-imagine-video",
                    }),
                ),
            ],
            bytes_resp=_FakeResp(
                status=200,
                body=b"MP4-bytes-fake",
                headers={"Content-Type": "video/mp4"},
            ),
        )

    def _client_session_factory():
        return session

    fake = types.ModuleType("aiohttp")
    fake.ClientSession = _client_session_factory  # type: ignore[attr-defined]
    fake.ClientError = _FakeClientError  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "aiohttp", fake)
    return session


# ── Adapter subclass with shortened polling cadence for tests ─────────


class _FastPollGrokVideoAdapter(GrokVideoAdapter):
    """Subclass that polls every ~0s so tests don't wait 5s/iteration.

    1.5s deadline gives ~150 iterations of headroom for happy-path tests
    while remaining short enough that the deadline-exhaustion test
    completes in well under 2 seconds."""

    _poll_interval_seconds = 0.001
    _poll_timeout_seconds = 1.5


# ── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture
def tenant_config():
    """Minimal TenantAIConfig-shaped object — exposes only the three
    attrs the adapter actually reads."""
    return SimpleNamespace(
        get_video_api_key=lambda: "xai-test-video-key",
        video_base_url="",
        video_model="grok-imagine-video",
    )


@pytest.fixture
def req():
    return VideoGenerationRequest(
        prompt="a slow zoom on a sunflower in a wind-swept field",
        duration_seconds=6,
        aspect_ratio="16:9",
        tenant_id="t-1",
        scene_id="scene-abc",
    )


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, settings):
    """Every test writes through Django default_storage; pointing
    MEDIA_ROOT at tmp keeps the test tree clean + isolated."""
    settings.MEDIA_ROOT = str(tmp_path)


# ── Happy path ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_happy_path_returns_result_with_storage_url(monkeypatch, tenant_config, req):
    """Submit → poll-once-done → fetch bytes → re-host. URL points to
    OUR storage, not xAI's CDN."""
    session = _install_fake_aiohttp(monkeypatch)

    result = await _FastPollGrokVideoAdapter(tenant_config).generate(req)

    assert result.provider == "grok_video"
    assert result.model == "grok-imagine-video"
    assert result.duration_seconds == 6
    assert "grok-cdn.example" not in result.url
    assert "maic/t-1/video/" in result.url
    assert "scene-abc__" in result.url
    # $0.05/sec × 6s = $0.30
    assert result.cost_usd_estimate == 0.30
    # Confirm we actually issued the bytes GET to the CDN URL.
    assert any("grok-cdn.example" in u for u in session.last_get_urls)


@pytest.mark.asyncio
async def test_submit_request_shape_matches_grok_contract(monkeypatch, tenant_config, req):
    """The submit body must use {model, prompt, duration} per the upstream
    contract, with Bearer auth and JSON content-type."""
    session = _install_fake_aiohttp(monkeypatch)
    await _FastPollGrokVideoAdapter(tenant_config).generate(req)

    assert session.last_post_url == "https://api.x.ai/v1/videos/generations"
    headers = session.last_post_headers or {}
    assert headers.get("Authorization") == "Bearer xai-test-video-key"
    assert headers.get("Content-Type") == "application/json"
    body = session.last_post_json or {}
    assert body["model"] == "grok-imagine-video"
    assert body["prompt"] == "a slow zoom on a sunflower in a wind-swept field"
    assert body["duration"] == 6
    # TODO verify against live API at cert time: upstream's grok-video-adapter.ts
    # documents only {model, prompt, duration} as accepted submit fields;
    # if xAI later accepts an aspect_ratio param, this assertion can soften.
    assert "aspect_ratio" not in body


@pytest.mark.asyncio
async def test_poll_endpoint_url_uses_request_id(monkeypatch, tenant_config, req):
    """The poll GET must target /videos/<request_id> with Bearer auth."""
    session = _install_fake_aiohttp(monkeypatch)
    await _FastPollGrokVideoAdapter(tenant_config).generate(req)

    assert session.last_get_urls[0] == "https://api.x.ai/v1/videos/req-abc-123"
    poll_headers = session.last_get_headers[0] or {}
    assert poll_headers.get("Authorization") == "Bearer xai-test-video-key"


@pytest.mark.asyncio
async def test_duration_falls_back_to_request_when_upstream_omits(
    monkeypatch, tenant_config, req,
):
    """If upstream's done payload omits video.duration, the result
    falls back to req.duration_seconds (upstream's TS type marks
    duration as optional)."""
    session = _FakeSession(
        post_resp=_FakeResp(status=200, body=json.dumps({"request_id": "req-x"})),
        poll_resps=[
            _FakeResp(
                status=200,
                body=json.dumps({
                    "status": "done",
                    "video": {"url": "https://grok-cdn.example/v.mp4"},
                }),
            ),
        ],
    )
    _install_fake_aiohttp(monkeypatch, session)
    result = await _FastPollGrokVideoAdapter(tenant_config).generate(req)
    assert result.duration_seconds == 6  # from req fallback


# ── Polling state-machine ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_polling_succeeds_on_third_attempt(monkeypatch, tenant_config, req):
    """pending → pending → done proves we do NOT take the first poll
    response unconditionally. All three responses must be consumed."""
    session = _FakeSession(
        post_resp=_FakeResp(status=200, body=json.dumps({"request_id": "req-slow"})),
        poll_resps=[
            _FakeResp(status=200, body=json.dumps({"status": "pending", "progress": 10})),
            _FakeResp(status=200, body=json.dumps({"status": "pending", "progress": 60})),
            _FakeResp(
                status=200,
                body=json.dumps({
                    "status": "done",
                    "video": {"url": "https://grok-cdn.example/done.mp4", "duration": 6},
                }),
            ),
        ],
    )
    _install_fake_aiohttp(monkeypatch, session)

    result = await _FastPollGrokVideoAdapter(tenant_config).generate(req)
    assert result.provider == "grok_video"
    assert session.poll_index == 3


@pytest.mark.asyncio
async def test_polling_failed_status_raises_provider_error(monkeypatch, tenant_config, req):
    """status == "failed" → MaicProviderError. Operator may retry the
    whole submit (idempotent at the protocol level), but this single
    attempt is over."""
    session = _FakeSession(
        post_resp=_FakeResp(status=200, body=json.dumps({"request_id": "req-fail"})),
        poll_resps=[
            _FakeResp(
                status=200,
                body=json.dumps({
                    "status": "failed",
                    # TODO verify against live API at cert time: the exact
                    # error-payload shape on failed grok video tasks is not
                    # documented in detail upstream — this is our best
                    # extrapolation from the .ts type ({status: "failed"}
                    # plus whatever else upstream emits).
                    "error": "moderation rejected prompt",
                }),
            ),
        ],
    )
    _install_fake_aiohttp(monkeypatch, session)

    with pytest.raises(MaicProviderError) as exc:
        await _FastPollGrokVideoAdapter(tenant_config).generate(req)
    msg = str(exc.value)
    assert "failed" in msg
    assert "moderation" in msg


@pytest.mark.asyncio
async def test_polling_unrecognised_status_raises_provider_error(
    monkeypatch, tenant_config, req,
):
    """If xAI adds a brand-new status string, the adapter MUST fail loud
    rather than spin. Better to surface a contract change than silently
    loop forever.

    TODO verify against live API at cert time: if xAI adds a documented
    intermediate state like "processing" or "queued", _IN_PROGRESS in
    grok_video.py should be widened and this test updated."""
    session = _FakeSession(
        post_resp=_FakeResp(status=200, body=json.dumps({"request_id": "req-new"})),
        poll_resps=[
            _FakeResp(
                status=200,
                body=json.dumps({"status": "quantum_superposition"}),
            ),
        ],
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollGrokVideoAdapter(tenant_config).generate(req)
    assert "quantum_superposition" in str(exc.value)
    assert "unrecognised" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_polling_times_out_when_deadline_exhausted(monkeypatch, tenant_config, req):
    """If the task never reaches a terminal status before the deadline,
    raise MaicProviderError. Deadline is a HARD ceiling — bounded by
    self._poll_timeout_seconds.

    We provision way more pending responses than the deadline allows
    iterations — the deadline must trip before the queue empties.
    """

    class _TinyDeadlineAdapter(GrokVideoAdapter):
        _poll_interval_seconds = 0.05
        _poll_timeout_seconds = 0.15

    pending_resp = _FakeResp(status=200, body=json.dumps({"status": "pending"}))
    session = _FakeSession(
        post_resp=_FakeResp(status=200, body=json.dumps({"request_id": "req-slow"})),
        poll_resps=[pending_resp for _ in range(500)],
    )
    _install_fake_aiohttp(monkeypatch, session)

    with pytest.raises(MaicProviderError) as exc:
        await _TinyDeadlineAdapter(tenant_config).generate(req)
    assert "timed out" in str(exc.value).lower()
    # We tripped the deadline well before exhausting 500 responses.
    assert session.poll_index < 20


# ── HTTP error matrix on SUBMIT ──────────────────────────────────────


@pytest.mark.asyncio
async def test_submit_401_raises_config_error(monkeypatch, tenant_config, req):
    """Submit 401 → MaicConfigError (auth — permanent, no retry)."""
    session = _FakeSession(
        post_resp=_FakeResp(status=401, body='{"error":"bad key"}'),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicConfigError) as exc:
        await _FastPollGrokVideoAdapter(tenant_config).generate(req)
    assert "auth" in str(exc.value).lower()
    assert "401" in str(exc.value)
    assert "submit" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_submit_403_raises_config_error(monkeypatch, tenant_config, req):
    """Submit 403 → MaicConfigError. Same category as 401."""
    session = _FakeSession(post_resp=_FakeResp(status=403, body="forbidden"))
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicConfigError):
        await _FastPollGrokVideoAdapter(tenant_config).generate(req)


@pytest.mark.asyncio
async def test_submit_429_raises_provider_error(monkeypatch, tenant_config, req):
    """Submit 429 → MaicProviderError (orchestrator may retry)."""
    session = _FakeSession(post_resp=_FakeResp(status=429, body="rate limit"))
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollGrokVideoAdapter(tenant_config).generate(req)
    assert "429" in str(exc.value)


@pytest.mark.asyncio
async def test_submit_500_raises_provider_error(monkeypatch, tenant_config, req):
    """Submit 5xx → MaicProviderError."""
    session = _FakeSession(post_resp=_FakeResp(status=503, body="upstream unavailable"))
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollGrokVideoAdapter(tenant_config).generate(req)
    assert "503" in str(exc.value)


@pytest.mark.asyncio
async def test_submit_other_4xx_raises_provider_error(monkeypatch, tenant_config, req):
    """Submit 4xx (not 401/403/429) → MaicProviderError."""
    session = _FakeSession(post_resp=_FakeResp(status=400, body='{"error":"invalid"}'))
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollGrokVideoAdapter(tenant_config).generate(req)
    assert "400" in str(exc.value)


@pytest.mark.asyncio
async def test_submit_network_error_raises_provider_error(monkeypatch, tenant_config, req):
    """aiohttp.ClientError during submit → MaicProviderError."""

    class _FailingSession(_FakeSession):
        def post(self, url, json=None, headers=None):
            raise _FakeClientError("DNS failure")

    _install_fake_aiohttp(
        monkeypatch,
        session=_FailingSession(post_resp=_FakeResp()),
    )
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollGrokVideoAdapter(tenant_config).generate(req)
    assert "network error" in str(exc.value).lower()


# ── HTTP error matrix on POLL ────────────────────────────────────────


@pytest.mark.asyncio
async def test_poll_401_raises_config_error(monkeypatch, tenant_config, req):
    """Poll 401 → MaicConfigError. Exceedingly rare (auth rotated
    mid-task) but possible."""
    session = _FakeSession(
        post_resp=_FakeResp(status=200, body=json.dumps({"request_id": "r"})),
        poll_resps=[_FakeResp(status=401, body="auth expired")],
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicConfigError) as exc:
        await _FastPollGrokVideoAdapter(tenant_config).generate(req)
    assert "poll" in str(exc.value).lower()
    assert "401" in str(exc.value)


@pytest.mark.asyncio
async def test_poll_429_raises_provider_error(monkeypatch, tenant_config, req):
    """Poll 429 → MaicProviderError (orchestrator may retry)."""
    session = _FakeSession(
        post_resp=_FakeResp(status=200, body=json.dumps({"request_id": "r"})),
        poll_resps=[_FakeResp(status=429, body="throttled")],
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollGrokVideoAdapter(tenant_config).generate(req)
    assert "429" in str(exc.value)
    assert "poll" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_poll_5xx_raises_provider_error(monkeypatch, tenant_config, req):
    """Poll 5xx → MaicProviderError."""
    session = _FakeSession(
        post_resp=_FakeResp(status=200, body=json.dumps({"request_id": "r"})),
        poll_resps=[_FakeResp(status=502, body="bad gateway")],
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollGrokVideoAdapter(tenant_config).generate(req)
    assert "502" in str(exc.value)


# ── Response-shape errors ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_submit_malformed_json_raises_provider_error(monkeypatch, tenant_config, req):
    """Submit 200 with non-JSON body → MaicProviderError."""
    session = _FakeSession(post_resp=_FakeResp(status=200, body="not-json{{{"))
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollGrokVideoAdapter(tenant_config).generate(req)
    assert "malformed" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_submit_missing_request_id_raises_provider_error(
    monkeypatch, tenant_config, req,
):
    """Submit returned JSON but no request_id → MaicProviderError."""
    session = _FakeSession(post_resp=_FakeResp(status=200, body=json.dumps({"foo": "bar"})))
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollGrokVideoAdapter(tenant_config).generate(req)
    assert "request_id" in str(exc.value)


@pytest.mark.asyncio
async def test_poll_missing_status_raises_provider_error(monkeypatch, tenant_config, req):
    """Poll response missing status field → MaicProviderError."""
    session = _FakeSession(
        post_resp=_FakeResp(status=200, body=json.dumps({"request_id": "r"})),
        poll_resps=[_FakeResp(status=200, body=json.dumps({"progress": 50}))],
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollGrokVideoAdapter(tenant_config).generate(req)
    assert "status" in str(exc.value)


@pytest.mark.asyncio
async def test_done_with_missing_video_object_raises_provider_error(
    monkeypatch, tenant_config, req,
):
    """status == done but no video object → MaicProviderError. xAI's
    upstream marks video as optional in the TS type, but in practice a
    "done" status without a URL is unusable; we fail loud."""
    session = _FakeSession(
        post_resp=_FakeResp(status=200, body=json.dumps({"request_id": "r"})),
        poll_resps=[_FakeResp(status=200, body=json.dumps({"status": "done"}))],
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollGrokVideoAdapter(tenant_config).generate(req)
    assert "video" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_done_with_empty_url_raises_provider_error(monkeypatch, tenant_config, req):
    """done but video.url is empty → MaicProviderError."""
    session = _FakeSession(
        post_resp=_FakeResp(status=200, body=json.dumps({"request_id": "r"})),
        poll_resps=[_FakeResp(
            status=200,
            body=json.dumps({"status": "done", "video": {"url": "", "duration": 6}}),
        )],
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError):
        await _FastPollGrokVideoAdapter(tenant_config).generate(req)


@pytest.mark.asyncio
async def test_video_fetch_404_raises_provider_error(monkeypatch, tenant_config, req):
    """done, URL returned, but bytes GET returns 404 → MaicProviderError.
    Happens when the signed CDN URL expires between submit and fetch."""
    session = _FakeSession(
        post_resp=_FakeResp(status=200, body=json.dumps({"request_id": "r"})),
        poll_resps=[_FakeResp(
            status=200,
            body=json.dumps({
                "status": "done",
                "video": {"url": "https://grok-cdn.example/expired.mp4", "duration": 6},
            }),
        )],
        bytes_resp=_FakeResp(status=404, body="not found"),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollGrokVideoAdapter(tenant_config).generate(req)
    assert "fetch" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_video_fetch_zero_bytes_raises_provider_error(
    monkeypatch, tenant_config, req,
):
    """Bytes GET returns 200 but empty body → MaicProviderError."""
    session = _FakeSession(
        post_resp=_FakeResp(status=200, body=json.dumps({"request_id": "r"})),
        poll_resps=[_FakeResp(
            status=200,
            body=json.dumps({
                "status": "done",
                "video": {"url": "https://grok-cdn.example/zero.mp4", "duration": 6},
            }),
        )],
        bytes_resp=_FakeResp(status=200, body=b"", headers={"Content-Type": "video/mp4"}),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollGrokVideoAdapter(tenant_config).generate(req)
    assert "zero bytes" in str(exc.value).lower()


# ── Auth / SSRF / config errors ──────────────────────────────────────


@pytest.mark.asyncio
async def test_missing_api_key_raises_config_error(monkeypatch, req):
    """No video_api_key → MaicConfigError BEFORE any HTTP."""
    cfg = SimpleNamespace(
        get_video_api_key=lambda: "",
        video_base_url="",
        video_model="grok-imagine-video",
    )
    _install_fake_aiohttp(monkeypatch)
    with pytest.raises(MaicConfigError) as exc:
        await _FastPollGrokVideoAdapter(cfg).generate(req)
    assert "api_key required" in str(exc.value)


@pytest.mark.asyncio
async def test_custom_base_url_goes_through_ssrf_guard(monkeypatch, req):
    """Tenant-supplied base_url pointing at localhost must be rejected
    by the SSRF guard."""
    cfg = SimpleNamespace(
        get_video_api_key=lambda: "xai-x",
        video_base_url="http://127.0.0.1:8080/v1",
        video_model="grok-imagine-video",
    )
    _install_fake_aiohttp(monkeypatch)
    with pytest.raises(MaicConfigError) as exc:
        await _FastPollGrokVideoAdapter(cfg).generate(req)
    assert "ssrf" in str(exc.value).lower() or "base_url" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_default_base_url_skips_ssrf_check(monkeypatch, tenant_config, req):
    """Empty video_base_url uses the default xAI endpoint without the
    SSRF guard. Tested by happy-path completing — if the guard ran on
    the default, it would try to DNS-resolve api.x.ai under monkey-
    patched aiohttp."""
    _install_fake_aiohttp(monkeypatch)
    result = await _FastPollGrokVideoAdapter(tenant_config).generate(req)
    assert result.provider == "grok_video"


# ── Cost estimator (pure unit, no IO) ─────────────────────────────────


def test_cost_estimator_grok_imagine_video_per_second():
    """$0.05/sec on grok-imagine-video. 6s → $0.30; 10s → $0.50."""
    assert GrokVideoAdapter._estimate_cost("grok-imagine-video", 6) == 0.30
    assert GrokVideoAdapter._estimate_cost("grok-imagine-video", 10) == 0.50


def test_cost_estimator_returns_none_for_unknown_model():
    """Future/unknown model → None rather than fabricated number."""
    assert GrokVideoAdapter._estimate_cost("grok-imagine-video-2026", 6) is None
    assert GrokVideoAdapter._estimate_cost("", 6) is None


def test_cost_estimator_returns_none_for_non_positive_duration():
    """0 or negative duration → None (we don't bill for zero output)."""
    assert GrokVideoAdapter._estimate_cost("grok-imagine-video", 0) is None
    assert GrokVideoAdapter._estimate_cost("grok-imagine-video", -1) is None


# ── Registry registration + structural guards ─────────────────────────


def test_adapter_is_registered_on_import():
    """Importing the adapter module registered it under (video, grok_video)."""
    from apps.maic.media.providers import _REGISTRY
    assert ("video", "grok_video") in _REGISTRY
    assert _REGISTRY[("video", "grok_video")] is GrokVideoAdapter


def test_default_timeout_is_higher_than_image_adapters():
    """Video generation takes minutes, not seconds — the brief requires
    300s here. Regression-guard so a future refactor doesn't drop it
    back to image-tier (60s) or qwen-tier (120s)."""
    assert GrokVideoAdapter.default_timeout_seconds == 300


def test_poll_helper_is_a_method_not_module_function():
    """Polling helper must live on the class so future subclasses can
    override the cadence."""
    assert hasattr(GrokVideoAdapter, "_poll_task_until_done")
    assert callable(GrokVideoAdapter._poll_task_until_done)
    import inspect
    assert inspect.iscoroutinefunction(GrokVideoAdapter._poll_task_until_done)


def test_kind_and_name_are_correct():
    """Brief specifies name='grok_video', kind='video'. Pinning these
    is important because the registry key and the VideoProviderId
    literal both depend on the exact string."""
    assert GrokVideoAdapter.name == "grok_video"
    assert GrokVideoAdapter.kind == "video"


# ── Live smoke (gated) ────────────────────────────────────────────────


@pytest.mark.skipif(
    os.environ.get("MAIC_GROK_VIDEO_LIVE_SMOKE") != "1"
    or not os.environ.get("GROK_API_KEY"),
    reason=(
        "live Grok video smoke disabled — set MAIC_GROK_VIDEO_LIVE_SMOKE=1 "
        "and GROK_API_KEY=<real-key> to enable. Costs ~$0.30 per run "
        "(grok-imagine-video × 6s @ $0.05/sec). Reuses the same xAI key "
        "as the Grok image adapter."
    ),
)
@pytest.mark.asyncio
async def test_live_smoke_real_grok_video_call(tmp_path, settings):
    """Hits the real xAI Grok Videos API end-to-end. Skipped unless env
    vars set.

    Cost: ~$0.30 per run (grok-imagine-video × 6 seconds).

    Asserts:
      - Real submit + poll + bytes-fetch round-trip succeeds
      - Generated video is uploaded to local storage
      - File on disk is non-zero and looks like an MP4 (ftyp box near the
        start of the file).
    """
    settings.MEDIA_ROOT = str(tmp_path)
    cfg = SimpleNamespace(
        get_video_api_key=lambda: os.environ["GROK_API_KEY"],
        video_base_url="",
        video_model="grok-imagine-video",
    )
    req = VideoGenerationRequest(
        prompt="a slow zoom on a sunflower in a wind-swept field, sunset light",
        duration_seconds=6,
        aspect_ratio="16:9",
        tenant_id="live-smoke",
        scene_id="live-smoke-scene",
    )
    # Use the real adapter (NOT _FastPollGrokVideoAdapter) so we exercise
    # the production polling cadence against the real upstream.
    result = await GrokVideoAdapter(cfg).generate(req)
    assert result.provider == "grok_video"
    assert "maic/live-smoke/video/" in result.url
    assert result.duration_seconds >= 1
    # MP4 files contain an "ftyp" box within the first ~32 bytes.
    from django.core.files.storage import default_storage
    storage_key = result.url.split("/media/", 1)[1] if "/media/" in result.url else None
    if storage_key:
        with default_storage.open(storage_key, "rb") as fh:
            header = fh.read(32)
        assert b"ftyp" in header
