"""Tests for the Veo (Google) video adapter (MAIC-910).

The first VIDEO adapter — and the test template Kling / Minimax-video /
Grok-video tests will copy. The fake aiohttp infrastructure here mirrors
the qwen_image template (sequence of poll responses) with one extra wrinkle:
the final bytes fetch goes through the same x-goog-api-key auth headers
as submit/poll, so the bytes-fetch fake just falls through to the
non-/operations URL branch.

Discipline:
  - IO-boundary fake only: ``aiohttp`` is injected into ``sys.modules``
    via monkeypatch.setitem — mirrors the golden pattern in
    tests_qwen_image.py.
  - No mocks of VeoVideoAdapter itself. Real adapter, real Pydantic,
    real storage (Django default_storage / FileSystemStorage in tests).
  - Polling cadence is shortened to nearly-zero in tests by overriding
    ``_poll_interval_seconds`` (and where needed, ``_poll_timeout_seconds``)
    via subclass — keeps the test suite fast while exercising the real
    asyncio.sleep path. We deliberately do NOT monkeypatch asyncio.sleep
    because the deadline math is what we want to verify.
  - Live smoke gated on MAIC_VEO_LIVE_SMOKE=1 AND GOOGLE_API_KEY env
    vars — skipped (not failed) when either is missing. GOOGLE_API_KEY
    is the canonical Google env var name.

Test layout:
  - Fake aiohttp infrastructure with poll-sequence support
  - Happy path + request-shape contract checks (auth header, body shape)
  - Polling state-machine tests (running → done-success, done-error,
    deadline exhaustion, missing required fields)
  - HTTP error matrix on BOTH submit and poll legs
  - SSRF + missing-key + response-shape edge cases
  - Cost estimator
  - Registry registration
  - Live smoke (gated)
"""
from __future__ import annotations

import json
import os
import sys
import types
from types import SimpleNamespace

import pytest

from apps.maic.exceptions import MaicConfigError, MaicProviderError
from apps.maic.media.adapters.veo import VeoVideoAdapter
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

    Three GET call sites in the Veo adapter:
        1. polling — N successive calls to /operations/<id> until done:true
        2. video bytes fetch — one call to the GCS URI

    The fake detects which GET is which by URL pattern: contains
    "/operations/" → poll (consume next poll_resps entry); anything else
    → bytes_resp. This keeps the test code declarative.
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
        if "/operations/" in url:
            # Polling call — consume from the queue. Past-the-end means
            # the test under-provisioned poll responses; fail loud rather
            # than silently looping.
            if self.poll_index >= len(self._poll_resps):
                raise AssertionError(
                    f"_FakeSession: polling GET #{self.poll_index + 1} but "
                    f"only {len(self._poll_resps)} poll responses provided. "
                    "Add more poll_resps or shorten the test."
                )
            resp = self._poll_resps[self.poll_index]
            self.poll_index += 1
            return resp
        # Non-/operations/ GET — must be the final bytes fetch.
        return self._bytes_resp


class _FakeClientError(Exception):
    """Stand-in for aiohttp.ClientError."""


def _install_fake_aiohttp(monkeypatch, session: _FakeSession | None = None) -> _FakeSession:
    """Inject a fake aiohttp module. Returns the session so tests can
    assert on captured request shape."""
    if session is None:
        # Default: happy path — submit returns operation name, one poll
        # returns done:true with a video URI, bytes fetch returns MP4.
        session = _FakeSession(
            post_resp=_FakeResp(
                status=200,
                body=json.dumps({"name": "operations/op-abc-123"}),
            ),
            poll_resps=[
                _FakeResp(
                    status=200,
                    body=json.dumps({
                        "name": "operations/op-abc-123",
                        "done": True,
                        "response": {
                            "generateVideoResponse": {
                                "generatedSamples": [
                                    {"video": {"uri": "https://veo-cdn.example/v1.mp4"}},
                                ],
                            },
                        },
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


class _FastPollVeoAdapter(VeoVideoAdapter):
    """Subclass that polls every ~0s so tests don't wait 5s/iteration.

    Real-world cadence is 5s interval, 300s deadline; in tests we compress
    to 1ms/1.5s, which gives ~1500 iterations of headroom — plenty for
    any happy-path test, and the timeout-exhaustion test uses an even
    tighter window to trip the deadline fast."""

    _poll_interval_seconds = 0.001
    _poll_timeout_seconds = 1.5


# ── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture
def tenant_config():
    """Minimal TenantAIConfig-shaped object for video."""
    return SimpleNamespace(
        get_video_api_key=lambda: "sk-test-google-key",
        video_base_url="",
        video_model="veo-3.0-generate-preview",
    )


@pytest.fixture
def req():
    return VideoGenerationRequest(
        prompt="a slow drone shot of a foggy forest at dawn",
        duration_seconds=5,
        aspect_ratio="16:9",
        tenant_id="t-1",
        scene_id="scene-veo",
    )


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, settings):
    """Point MEDIA_ROOT at tmp to keep the test tree clean + isolated."""
    settings.MEDIA_ROOT = str(tmp_path)


# ── Happy path ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_happy_path_returns_result_with_storage_url(monkeypatch, tenant_config, req):
    """Submit → poll-once-done → fetch bytes → storage. URL points to
    OUR storage, not Google's CDN."""
    session = _install_fake_aiohttp(monkeypatch)

    adapter = _FastPollVeoAdapter(tenant_config)
    result = await adapter.generate(req)

    assert result.provider == "veo"
    assert result.model == "veo-3.0-generate-preview"
    assert result.duration_seconds == 5
    assert "veo-cdn.example" not in result.url
    assert "maic/t-1/video/" in result.url
    assert "scene-veo__" in result.url
    # No verified pricing — cost is None.
    assert result.cost_usd_estimate is None
    # Confirm we actually issued the bytes GET to the Veo CDN.
    assert any("veo-cdn.example" in u for u in session.last_get_urls)


@pytest.mark.asyncio
async def test_submit_request_shape_matches_veo_contract(monkeypatch, tenant_config, req):
    """The submit body must use Google's predictor shape — {instances:
    [{prompt}], parameters: {aspectRatio, durationSeconds}} — and the
    auth header MUST be x-goog-api-key (NEVER ?key= in the URL)."""
    session = _install_fake_aiohttp(monkeypatch)
    await _FastPollVeoAdapter(tenant_config).generate(req)

    assert session.last_post_url == (
        "https://generativelanguage.googleapis.com/v1beta"
        "/models/veo-3.0-generate-preview:predictLongRunning"
    )
    # CRITICAL: no ?key= in the URL — auth via header only.
    assert "?key=" not in session.last_post_url
    headers = session.last_post_headers or {}
    assert headers.get("x-goog-api-key") == "sk-test-google-key"
    assert "Authorization" not in headers  # Bearer auth would be wrong here
    body = session.last_post_json or {}
    assert body["instances"] == [{"prompt": "a slow drone shot of a foggy forest at dawn"}]
    assert body["parameters"]["aspectRatio"] == "16:9"
    assert body["parameters"]["durationSeconds"] == 5


@pytest.mark.asyncio
async def test_submit_request_includes_seed_when_provided(monkeypatch, tenant_config):
    """When req.seed is set, it must be passed through in parameters.
    When unset (None), it must NOT appear in the body (omitting an
    unset param is different from sending null)."""
    session = _install_fake_aiohttp(monkeypatch)
    req_with_seed = VideoGenerationRequest(
        prompt="x",
        duration_seconds=5,
        aspect_ratio="16:9",
        seed=42,
        tenant_id="t-seed",
    )
    await _FastPollVeoAdapter(tenant_config).generate(req_with_seed)
    body = session.last_post_json or {}
    assert body["parameters"]["seed"] == 42


@pytest.mark.asyncio
async def test_submit_request_omits_seed_when_none(monkeypatch, tenant_config, req):
    """req.seed defaults to None — body must NOT include a seed key."""
    session = _install_fake_aiohttp(monkeypatch)
    await _FastPollVeoAdapter(tenant_config).generate(req)
    body = session.last_post_json or {}
    assert "seed" not in body["parameters"]


@pytest.mark.asyncio
async def test_poll_endpoint_url_uses_operation_name(monkeypatch, tenant_config, req):
    """The poll GET must target {base}/operations/<op_id> with the same
    x-goog-api-key auth header used at submit."""
    session = _install_fake_aiohttp(monkeypatch)
    await _FastPollVeoAdapter(tenant_config).generate(req)

    # First GET is the poll; second is the bytes fetch.
    assert session.last_get_urls[0] == (
        "https://generativelanguage.googleapis.com/v1beta/operations/op-abc-123"
    )
    poll_headers = session.last_get_headers[0] or {}
    assert poll_headers.get("x-goog-api-key") == "sk-test-google-key"


@pytest.mark.asyncio
async def test_bytes_fetch_uses_auth_headers(monkeypatch, tenant_config, req):
    """Veo's GCS URIs require the x-goog-api-key header even though they
    look signed — confirm we pass auth through to the bytes GET too."""
    session = _install_fake_aiohttp(monkeypatch)
    await _FastPollVeoAdapter(tenant_config).generate(req)
    # The bytes fetch is the second GET (index 1).
    bytes_headers = session.last_get_headers[1] or {}
    assert bytes_headers.get("x-goog-api-key") == "sk-test-google-key"


# ── Polling state-machine ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_polling_succeeds_after_running_iterations(monkeypatch, tenant_config, req):
    """done:false → done:false → done:true proves we do NOT just take
    the first poll response. The poll counter MUST advance all three."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({"name": "operations/op-slow"}),
        ),
        poll_resps=[
            _FakeResp(
                status=200,
                body=json.dumps({"name": "operations/op-slow", "done": False}),
            ),
            _FakeResp(
                status=200,
                body=json.dumps({
                    "name": "operations/op-slow",
                    "done": False,
                    "metadata": {"@type": "type.googleapis.com/google.cloud.aiplatform.v1.VideoGenerationOperationMetadata"},
                }),
            ),
            _FakeResp(
                status=200,
                body=json.dumps({
                    "name": "operations/op-slow",
                    "done": True,
                    "response": {
                        "generateVideoResponse": {
                            "generatedSamples": [
                                {"video": {"uri": "https://veo-cdn.example/done.mp4"}},
                            ],
                        },
                    },
                }),
            ),
        ],
    )
    _install_fake_aiohttp(monkeypatch, session)

    result = await _FastPollVeoAdapter(tenant_config).generate(req)
    assert result.provider == "veo"
    # All three poll responses consumed
    assert session.poll_index == 3


@pytest.mark.asyncio
async def test_polling_done_with_error_raises_provider_error(monkeypatch, tenant_config, req):
    """done:true with error.{code, message} → MaicProviderError. The
    upstream code + message must propagate so operators know whether
    this was a content-policy block, quota issue, or model crash."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({"name": "operations/op-fail"}),
        ),
        poll_resps=[
            _FakeResp(
                status=200,
                body=json.dumps({
                    "name": "operations/op-fail",
                    "done": True,
                    "error": {
                        "code": 9,
                        "message": "prompt failed content policy",
                        "status": "FAILED_PRECONDITION",
                    },
                }),
            ),
        ],
    )
    _install_fake_aiohttp(monkeypatch, session)

    with pytest.raises(MaicProviderError) as exc:
        await _FastPollVeoAdapter(tenant_config).generate(req)
    msg = str(exc.value)
    assert "error" in msg.lower()
    assert "content policy" in msg
    assert "code=9" in msg


@pytest.mark.asyncio
async def test_polling_times_out_when_deadline_exhausted(monkeypatch, tenant_config, req):
    """If the operation never reaches done:true before the deadline,
    raise MaicProviderError. The deadline is a HARD ceiling — bounded
    by self._poll_timeout_seconds; no unbounded while True."""

    class _TinyDeadlineAdapter(VeoVideoAdapter):
        _poll_interval_seconds = 0.05
        _poll_timeout_seconds = 0.15

    # 500 done:false responses — way more than the deadline allows.
    running_resp = _FakeResp(
        status=200,
        body=json.dumps({"name": "operations/op-stuck", "done": False}),
    )
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({"name": "operations/op-stuck"}),
        ),
        poll_resps=[running_resp for _ in range(500)],
    )
    _install_fake_aiohttp(monkeypatch, session)

    with pytest.raises(MaicProviderError) as exc:
        await _TinyDeadlineAdapter(tenant_config).generate(req)
    assert "timed out" in str(exc.value).lower()
    # We tripped the deadline well before exhausting 500 responses.
    assert session.poll_index < 20


@pytest.mark.asyncio
async def test_polling_done_true_missing_response_raises(monkeypatch, tenant_config, req):
    """done:true without a 'response' object AND without an 'error' is
    a contract violation — MaicProviderError so operators see it."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({"name": "operations/op-weird"}),
        ),
        poll_resps=[
            _FakeResp(
                status=200,
                body=json.dumps({"name": "operations/op-weird", "done": True}),
            ),
        ],
    )
    _install_fake_aiohttp(monkeypatch, session)

    with pytest.raises(MaicProviderError) as exc:
        await _FastPollVeoAdapter(tenant_config).generate(req)
    assert "response" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_polling_done_missing_generate_video_response_raises(monkeypatch, tenant_config, req):
    """done:true with response but no generateVideoResponse → MaicProviderError."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({"name": "operations/op-wrong"}),
        ),
        poll_resps=[
            _FakeResp(
                status=200,
                body=json.dumps({
                    "name": "operations/op-wrong",
                    "done": True,
                    "response": {"someOtherKey": "x"},
                }),
            ),
        ],
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollVeoAdapter(tenant_config).generate(req)
    assert "generateVideoResponse" in str(exc.value)


@pytest.mark.asyncio
async def test_polling_done_empty_generated_samples_raises(monkeypatch, tenant_config, req):
    """done:true with empty generatedSamples → MaicProviderError."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({"name": "operations/op-empty"}),
        ),
        poll_resps=[
            _FakeResp(
                status=200,
                body=json.dumps({
                    "name": "operations/op-empty",
                    "done": True,
                    "response": {
                        "generateVideoResponse": {"generatedSamples": []},
                    },
                }),
            ),
        ],
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollVeoAdapter(tenant_config).generate(req)
    assert "generatedSamples" in str(exc.value)


@pytest.mark.asyncio
async def test_polling_done_missing_video_uri_raises(monkeypatch, tenant_config, req):
    """done:true, samples[0].video present but .uri missing → MaicProviderError."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({"name": "operations/op-no-uri"}),
        ),
        poll_resps=[
            _FakeResp(
                status=200,
                body=json.dumps({
                    "name": "operations/op-no-uri",
                    "done": True,
                    "response": {
                        "generateVideoResponse": {
                            "generatedSamples": [{"video": {}}],
                        },
                    },
                }),
            ),
        ],
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollVeoAdapter(tenant_config).generate(req)
    assert "uri" in str(exc.value).lower()


# ── HTTP error matrix on SUBMIT ──────────────────────────────────────


@pytest.mark.asyncio
async def test_submit_401_raises_config_error(monkeypatch, tenant_config, req):
    """Submit 401 → MaicConfigError (auth — permanent, no retry)."""
    session = _FakeSession(
        post_resp=_FakeResp(status=401, body='{"error":{"code":401,"status":"UNAUTHENTICATED"}}'),
    )
    _install_fake_aiohttp(monkeypatch, session)

    with pytest.raises(MaicConfigError) as exc:
        await _FastPollVeoAdapter(tenant_config).generate(req)
    assert "auth" in str(exc.value).lower()
    assert "401" in str(exc.value)
    assert "submit" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_submit_403_raises_config_error(monkeypatch, tenant_config, req):
    """Submit 403 → MaicConfigError. Same category as 401."""
    session = _FakeSession(post_resp=_FakeResp(status=403, body="forbidden"))
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicConfigError):
        await _FastPollVeoAdapter(tenant_config).generate(req)


@pytest.mark.asyncio
async def test_submit_429_raises_provider_error(monkeypatch, tenant_config, req):
    """Submit 429 → MaicProviderError (orchestrator may retry)."""
    session = _FakeSession(post_resp=_FakeResp(status=429, body='{"error":"throttled"}'))
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollVeoAdapter(tenant_config).generate(req)
    assert "429" in str(exc.value)


@pytest.mark.asyncio
async def test_submit_5xx_raises_provider_error(monkeypatch, tenant_config, req):
    """Submit 5xx → MaicProviderError."""
    session = _FakeSession(post_resp=_FakeResp(status=503, body="upstream unavailable"))
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollVeoAdapter(tenant_config).generate(req)
    assert "503" in str(exc.value)


@pytest.mark.asyncio
async def test_submit_other_4xx_raises_provider_error(monkeypatch, tenant_config, req):
    """Submit 4xx (not 401/403/429) → MaicProviderError."""
    session = _FakeSession(post_resp=_FakeResp(status=400, body='{"error":"invalid"}'))
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollVeoAdapter(tenant_config).generate(req)
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
        await _FastPollVeoAdapter(tenant_config).generate(req)
    assert "network error" in str(exc.value).lower()


# ── HTTP error matrix on POLL ────────────────────────────────────────


@pytest.mark.asyncio
async def test_poll_401_raises_config_error(monkeypatch, tenant_config, req):
    """Poll 401 → MaicConfigError. Exceedingly rare (auth rotated
    mid-operation) but possible — and we want loud failure when it does."""
    session = _FakeSession(
        post_resp=_FakeResp(status=200, body=json.dumps({"name": "operations/op-x"})),
        poll_resps=[_FakeResp(status=401, body="auth expired")],
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicConfigError) as exc:
        await _FastPollVeoAdapter(tenant_config).generate(req)
    assert "poll" in str(exc.value).lower()
    assert "401" in str(exc.value)


@pytest.mark.asyncio
async def test_poll_429_raises_provider_error(monkeypatch, tenant_config, req):
    """Poll 429 → MaicProviderError (orchestrator may retry)."""
    session = _FakeSession(
        post_resp=_FakeResp(status=200, body=json.dumps({"name": "operations/op-x"})),
        poll_resps=[_FakeResp(status=429, body="throttled")],
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollVeoAdapter(tenant_config).generate(req)
    assert "429" in str(exc.value)
    assert "poll" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_poll_5xx_raises_provider_error(monkeypatch, tenant_config, req):
    """Poll 5xx → MaicProviderError."""
    session = _FakeSession(
        post_resp=_FakeResp(status=200, body=json.dumps({"name": "operations/op-x"})),
        poll_resps=[_FakeResp(status=502, body="bad gateway")],
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollVeoAdapter(tenant_config).generate(req)
    assert "502" in str(exc.value)


# ── Response-shape errors ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_submit_malformed_json_raises_provider_error(monkeypatch, tenant_config, req):
    """Submit 200 with non-JSON body → MaicProviderError."""
    session = _FakeSession(post_resp=_FakeResp(status=200, body="not-json{{{"))
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollVeoAdapter(tenant_config).generate(req)
    assert "malformed" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_submit_missing_operation_name_raises_provider_error(monkeypatch, tenant_config, req):
    """Submit returned JSON but no 'name' field → MaicProviderError."""
    session = _FakeSession(post_resp=_FakeResp(status=200, body=json.dumps({"foo": "bar"})))
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollVeoAdapter(tenant_config).generate(req)
    assert "name" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_submit_error_in_200_body_raises_provider_error(monkeypatch, tenant_config, req):
    """Google quirk: 200 status with {error: ...} body. Promote to
    MaicProviderError so operators see it instead of getting a confusing
    'missing name' error."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({"error": {"code": 400, "message": "quota exceeded"}}),
        ),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollVeoAdapter(tenant_config).generate(req)
    msg = str(exc.value)
    assert "quota exceeded" in msg
    assert "code=400" in msg


@pytest.mark.asyncio
async def test_video_fetch_404_raises_provider_error(monkeypatch, tenant_config, req):
    """done:true, URI returned, but bytes GET returns 404 → MaicProviderError.
    Happens when Google's signed URL expired between submit and fetch."""
    session = _FakeSession(
        post_resp=_FakeResp(status=200, body=json.dumps({"name": "operations/op-x"})),
        poll_resps=[_FakeResp(
            status=200,
            body=json.dumps({
                "name": "operations/op-x",
                "done": True,
                "response": {
                    "generateVideoResponse": {
                        "generatedSamples": [
                            {"video": {"uri": "https://veo-cdn.example/expired.mp4"}},
                        ],
                    },
                },
            }),
        )],
        bytes_resp=_FakeResp(status=404, body="not found"),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollVeoAdapter(tenant_config).generate(req)
    assert "fetch" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_video_fetch_zero_bytes_raises_provider_error(monkeypatch, tenant_config, req):
    """Bytes GET returns 200 but empty body → MaicProviderError."""
    session = _FakeSession(
        post_resp=_FakeResp(status=200, body=json.dumps({"name": "operations/op-x"})),
        poll_resps=[_FakeResp(
            status=200,
            body=json.dumps({
                "name": "operations/op-x",
                "done": True,
                "response": {
                    "generateVideoResponse": {
                        "generatedSamples": [
                            {"video": {"uri": "https://veo-cdn.example/zero.mp4"}},
                        ],
                    },
                },
            }),
        )],
        bytes_resp=_FakeResp(status=200, body=b"", headers={"Content-Type": "video/mp4"}),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollVeoAdapter(tenant_config).generate(req)
    assert "zero bytes" in str(exc.value).lower()


# ── Auth / SSRF / config errors ──────────────────────────────────────


@pytest.mark.asyncio
async def test_missing_api_key_raises_config_error(monkeypatch, req):
    """No api_key → MaicConfigError BEFORE any HTTP. No env fallback —
    explicit per-tenant keying only (same rule as qwen)."""
    cfg = SimpleNamespace(
        get_video_api_key=lambda: "",
        video_base_url="",
        video_model="veo-3.0-generate-preview",
    )
    _install_fake_aiohttp(monkeypatch)
    with pytest.raises(MaicConfigError) as exc:
        await _FastPollVeoAdapter(cfg).generate(req)
    assert "api_key required" in str(exc.value)


@pytest.mark.asyncio
async def test_custom_base_url_goes_through_ssrf_guard(monkeypatch, req):
    """Tenant-supplied base URL pointing at localhost MUST be rejected
    by the SSRF guard. Proves we don't blindly trust tenant input."""
    cfg = SimpleNamespace(
        get_video_api_key=lambda: "sk-x",
        video_base_url="http://127.0.0.1:8080/v1beta",
        video_model="veo-3.0-generate-preview",
    )
    _install_fake_aiohttp(monkeypatch)
    with pytest.raises(MaicConfigError) as exc:
        await _FastPollVeoAdapter(cfg).generate(req)
    assert "ssrf" in str(exc.value).lower() or "base_url" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_default_base_url_skips_ssrf_check(monkeypatch, tenant_config, req):
    """Empty video_base_url uses the default Google endpoint without
    invoking the SSRF guard (no DNS resolution of a known endpoint)."""
    _install_fake_aiohttp(monkeypatch)
    result = await _FastPollVeoAdapter(tenant_config).generate(req)
    assert result.provider == "veo"


# ── Cost estimator (pure unit, no IO) ─────────────────────────────────


def test_cost_estimator_returns_none_for_all_models():
    """No verified pricing table — always None. Telemetry is
    non-blocking; operators get spend numbers from the Google Cloud
    console."""
    assert VeoVideoAdapter._estimate_cost("veo-3.0-generate-preview", 5) is None
    assert VeoVideoAdapter._estimate_cost("veo-3.1-fast-generate-001", 8) is None
    assert VeoVideoAdapter._estimate_cost("unknown-model", 5) is None


# ── Registry registration ─────────────────────────────────────────────


def test_adapter_is_registered_on_import():
    """Importing the adapter module registered it under (video, veo).
    This is the FIRST video adapter to register — make sure the registry
    accepted it without collision."""
    from apps.maic.media.providers import _REGISTRY
    assert ("video", "veo") in _REGISTRY
    assert _REGISTRY[("video", "veo")] is VeoVideoAdapter


def test_default_timeout_is_higher_than_image_adapters():
    """Video gens are slower than images — the brief requires 360s here.
    Regression-guard so a future refactor doesn't drop this back to
    120s (the qwen image value) by accident."""
    assert VeoVideoAdapter.default_timeout_seconds == 360


def test_poll_helper_is_a_method_not_module_function():
    """The polling helper must live on the adapter so sibling video
    adapters can override the cadence without re-implementing.
    Regression-guard against a DRY-pass refactor moving it module-level."""
    assert hasattr(VeoVideoAdapter, "_poll_operation_until_done")
    assert callable(VeoVideoAdapter._poll_operation_until_done)
    import inspect
    assert inspect.iscoroutinefunction(VeoVideoAdapter._poll_operation_until_done)


def test_kind_is_video_not_image():
    """Veo is a video adapter. Regression guard so the file doesn't get
    accidentally copy-pasted into the image registry."""
    assert VeoVideoAdapter.kind == "video"
    assert VeoVideoAdapter.name == "veo"


# ── Live smoke (gated) ────────────────────────────────────────────────


@pytest.mark.skipif(
    os.environ.get("MAIC_VEO_LIVE_SMOKE") != "1"
    or not os.environ.get("GOOGLE_API_KEY"),
    reason=(
        "live Veo smoke disabled — set MAIC_VEO_LIVE_SMOKE=1 and "
        "GOOGLE_API_KEY=<real-key> to enable. Veo pricing is roughly "
        "$0.15-$0.40 per second of generated video at list price; a 5s "
        "smoke test costs ~$0.75-$2.00. Verify quota on the Google Cloud "
        "console before running."
    ),
)
@pytest.mark.asyncio
async def test_live_smoke_real_veo_call(tmp_path, settings):
    """Hits the real Veo API end-to-end. Skipped unless env vars set.

    Asserts:
      - Real submit + poll + bytes-fetch round-trip succeeds
      - Generated video is uploaded to local storage
      - File on disk is non-zero and starts with a known mp4 signature
        (ISO BMFF 'ftyp' atom at offset 4).
    """
    settings.MEDIA_ROOT = str(tmp_path)
    api_key = os.environ["GOOGLE_API_KEY"]
    cfg = SimpleNamespace(
        get_video_api_key=lambda: api_key,
        video_base_url="",
        video_model=os.environ.get("MAIC_VEO_LIVE_MODEL", "veo-3.0-generate-preview"),
    )
    req = VideoGenerationRequest(
        prompt="a single red balloon floating across a clear blue sky",
        duration_seconds=5,
        aspect_ratio="16:9",
        tenant_id="live-smoke",
        scene_id="live-smoke-scene",
    )
    result = await VeoVideoAdapter(cfg).generate(req)
    assert result.provider == "veo"
    assert "maic/live-smoke/video/" in result.url
    from django.core.files.storage import default_storage
    storage_key = result.url.split("/media/", 1)[1] if "/media/" in result.url else None
    if storage_key:
        with default_storage.open(storage_key, "rb") as fh:
            header = fh.read(12)
        # MP4 files have 'ftyp' at offset 4 (ISO BMFF box header).
        assert header[4:8] == b"ftyp", f"unexpected header: {header!r}"
