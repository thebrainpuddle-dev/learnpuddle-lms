"""Tests for the Kling (Kuaishou) video adapter — MAIC-911.

Mirrors the test layout from tests_qwen_image.py (the async-polling
template), adapted for video + Kling's JWT-signed auth.

Discipline:
  - IO-boundary fake only: ``aiohttp`` is injected into ``sys.modules``
    via monkeypatch.setitem — mirrors the golden pattern from
    tests_qwen_image.py and tests_openai_image.py.
  - No mocks of KlingVideoAdapter itself. Real adapter, real Pydantic,
    real storage (Django default_storage / FileSystemStorage in tests).
  - Polling cadence is shortened in tests by overriding
    ``_poll_interval_seconds`` / ``_poll_timeout_seconds`` via subclass —
    keeps the suite fast while exercising the real asyncio.sleep path.
    asyncio.sleep is NOT monkeypatched (we want the real deadline math).
  - JWT generation is the REAL PyJWT path; we decode without verification
    in tests to assert the claim shape (iss / exp / nbf / iat).
  - Live smoke gated on MAIC_KLING_LIVE_SMOKE=1 AND KLING_API_KEY env
    vars — skipped (not failed) when either is missing. KLING_API_KEY
    must be in 'access:secret' format.

Test layout:
  - Fake aiohttp infrastructure with poll-sequence support
  - Happy path + request-shape contract checks + JWT shape
  - Polling state-machine (processing→succeed, failed, unrecognised,
    deadline exhaustion)
  - HTTP error matrix on BOTH submit and poll legs
  - Kling envelope code != 0 handling
  - Auth / SSRF / config edge cases (api_key format, missing key)
  - Registry registration
  - Live smoke (gated)
"""
from __future__ import annotations

import json
import os
import sys
import time
import types
from types import SimpleNamespace

import pytest

from apps.maic.exceptions import MaicConfigError, MaicProviderError
from apps.maic.media.adapters.kling import KlingVideoAdapter
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

    URL-pattern dispatch:
      POST /v1/videos/text2video         → post_resp
      GET  /v1/videos/text2video/<id>    → poll_resps[i++]
      GET  anything-else                 → bytes_resp
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
        if "/v1/videos/text2video/" in url:
            if self.poll_index >= len(self._poll_resps):
                raise AssertionError(
                    f"_FakeSession: polling GET #{self.poll_index + 1} but "
                    f"only {len(self._poll_resps)} poll responses provided. "
                    "Add more poll_resps or shorten the test."
                )
            resp = self._poll_resps[self.poll_index]
            self.poll_index += 1
            return resp
        return self._bytes_resp


class _FakeClientError(Exception):
    """Stand-in for aiohttp.ClientError."""


def _install_fake_aiohttp(monkeypatch, session: _FakeSession | None = None) -> _FakeSession:
    """Inject a fake aiohttp module. Returns the session so tests can
    assert on captured request shape."""
    if session is None:
        # Default: happy path — submit returns task_id, one poll returns
        # succeed with a video URL, bytes fetch returns mp4.
        session = _FakeSession(
            post_resp=_FakeResp(
                status=200,
                body=json.dumps({
                    "code": 0,
                    "message": "SUCCESS",
                    "data": {"task_id": "task-kling-001", "task_status": "submitted"},
                }),
            ),
            poll_resps=[
                _FakeResp(
                    status=200,
                    body=json.dumps({
                        "code": 0,
                        "message": "SUCCESS",
                        "data": {
                            "task_id": "task-kling-001",
                            "task_status": "succeed",
                            "task_result": {
                                "videos": [{
                                    "id": "vid-1",
                                    "url": "https://kling-cdn.example/clip-1.mp4",
                                    "duration": "5",
                                }],
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


class _FastPollKlingAdapter(KlingVideoAdapter):
    """Subclass that polls every ~0s so tests don't wait 5s/iteration.

    A non-zero deadline (1.5s) gives ~1500 iterations of headroom for
    happy-path tests, while still letting timeout-exhaustion tests trip
    a real deadline by overriding to a tiny value."""

    _poll_interval_seconds = 0.001
    _poll_timeout_seconds = 1.5


# ── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture
def tenant_config():
    """Minimal TenantAIConfig-shaped object with a valid 'access:secret'
    composite key."""
    return SimpleNamespace(
        get_video_api_key=lambda: "test-access-key:test-secret-key",
        video_base_url="",
        video_model="kling-v1",
    )


@pytest.fixture
def req():
    return VideoGenerationRequest(
        prompt="a serene mountain river at sunrise, slow tracking shot",
        duration_seconds=5,
        aspect_ratio="16:9",
        tenant_id="t-1",
        scene_id="scene-kling-1",
    )


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, settings):
    """Point MEDIA_ROOT at tmp to keep the test tree clean + isolated."""
    settings.MEDIA_ROOT = str(tmp_path)


# ── Happy path ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_happy_path_returns_result_with_storage_url(monkeypatch, tenant_config, req):
    """Submit → poll-once-succeed → fetch bytes → storage. Result URL
    points to OUR storage, not Kling's CDN."""
    session = _install_fake_aiohttp(monkeypatch)

    adapter = _FastPollKlingAdapter(tenant_config)
    result = await adapter.generate(req)

    assert result.provider == "kling"
    assert result.model == "kling-v1"
    assert "kling-cdn.example" not in result.url
    assert "maic/t-1/video/" in result.url
    assert "scene-kling-1__" in result.url
    # Duration reported by Kling ('5') overrides the request value (also 5).
    assert result.duration_seconds == 5
    # No pricing table — cost is None.
    assert result.cost_usd_estimate is None
    # The bytes GET went out to Kling's CDN URL.
    assert any("kling-cdn.example" in u for u in session.last_get_urls)


@pytest.mark.asyncio
async def test_submit_request_shape_matches_kling_contract(monkeypatch, tenant_config, req):
    """Submit body must use {model_name, prompt, negative_prompt, mode,
    duration (STRING), aspect_ratio} and target /v1/videos/text2video
    with Bearer-JWT auth."""
    session = _install_fake_aiohttp(monkeypatch)

    await _FastPollKlingAdapter(tenant_config).generate(req)

    assert session.last_post_url == "https://api.klingai.com/v1/videos/text2video"
    headers = session.last_post_headers or {}
    auth = headers.get("Authorization") or ""
    # Bearer JWT — three '.'-separated segments.
    assert auth.startswith("Bearer ")
    token = auth.removeprefix("Bearer ")
    assert token.count(".") == 2, f"expected JWT, got {token!r}"
    assert headers.get("Content-Type") == "application/json"

    body = session.last_post_json or {}
    assert body["model_name"] == "kling-v1"
    assert body["prompt"] == "a serene mountain river at sunrise, slow tracking shot"
    # Duration must be a STRING — Kling rejects integer durations.
    assert body["duration"] == "5"
    assert isinstance(body["duration"], str)
    assert body["aspect_ratio"] == "16:9"
    assert body["mode"] == "pro"
    assert "negative_prompt" in body


@pytest.mark.asyncio
async def test_poll_endpoint_url_uses_task_id(monkeypatch, tenant_config, req):
    """Poll GET targets /v1/videos/text2video/<task_id> with the same
    Bearer JWT but no Content-Type header."""
    session = _install_fake_aiohttp(monkeypatch)
    await _FastPollKlingAdapter(tenant_config).generate(req)

    assert session.last_get_urls[0] == (
        "https://api.klingai.com/v1/videos/text2video/task-kling-001"
    )
    poll_headers = session.last_get_headers[0] or {}
    assert poll_headers.get("Authorization", "").startswith("Bearer ")
    # Content-Type is meaningless on GETs and Kling's gateway occasionally
    # rejects polls that include it.
    assert "Content-Type" not in poll_headers


# ── JWT contract ──────────────────────────────────────────────────────


def test_jwt_payload_contains_access_key_and_30min_exp():
    """Decode the JWT (without signature verification) and assert the
    claims match Kling's spec: iss=access_key, exp~now+1800, nbf~now-5.

    Catches contract drift if someone changes the claim names or the
    expiry math."""
    import jwt

    now = int(time.time())
    token = KlingVideoAdapter._generate_jwt("AK-test", "SK-test")
    # decode without verification — we're inspecting our own output.
    claims = jwt.decode(token, options={"verify_signature": False})
    assert claims["iss"] == "AK-test"
    # exp should be ~30 minutes ahead (1800s). Allow 5s wall-clock slack.
    assert claims["exp"] == pytest.approx(now + 1800, abs=5)
    # nbf 5s in the past to absorb clock skew.
    assert claims["nbf"] == pytest.approx(now - 5, abs=5)
    # iat present for introspection parity with TS reference.
    assert "iat" in claims


def test_jwt_signed_with_secret_key_not_access_key():
    """Token signature must verify against the SECRET key (not the
    access key). Verifying with the wrong secret must fail."""
    import jwt

    token = KlingVideoAdapter._generate_jwt("AK-test", "SK-test")
    # Must verify with secret_key
    decoded = jwt.decode(token, "SK-test", algorithms=["HS256"])
    assert decoded["iss"] == "AK-test"
    # Must NOT verify with access_key
    with pytest.raises(jwt.InvalidSignatureError):
        jwt.decode(token, "AK-test", algorithms=["HS256"])


def test_jwt_uses_hs256_alg():
    """Header alg must be HS256 — Kling rejects other algorithms."""
    import jwt

    token = KlingVideoAdapter._generate_jwt("AK-x", "SK-x")
    header = jwt.get_unverified_header(token)
    assert header["alg"] == "HS256"
    assert header["typ"] == "JWT"


def test_each_generate_call_produces_a_fresh_jwt(monkeypatch, tenant_config, req):
    """Each call to ``generate()`` must regenerate the JWT — different
    exp/iat each time. We capture two consecutive generate() calls'
    Authorization headers and assert the tokens differ."""
    captured_tokens: list[str] = []

    def _factory():
        # Each call gets a brand-new session (mirroring the real aiohttp
        # ClientSession usage).
        session = _FakeSession(
            post_resp=_FakeResp(
                status=200,
                body=json.dumps({
                    "code": 0,
                    "data": {"task_id": "t-x", "task_status": "submitted"},
                }),
            ),
            poll_resps=[_FakeResp(
                status=200,
                body=json.dumps({
                    "code": 0,
                    "data": {
                        "task_id": "t-x",
                        "task_status": "succeed",
                        "task_result": {"videos": [{
                            "url": "https://k.example/v.mp4",
                            "duration": "5",
                        }]},
                    },
                }),
            )],
        )
        return _CapturingSession(session, captured_tokens)

    fake = types.ModuleType("aiohttp")
    fake.ClientSession = _factory  # type: ignore[attr-defined]
    fake.ClientError = _FakeClientError  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "aiohttp", fake)

    # Two calls, separated by a short sleep so iat advances.
    import asyncio
    async def _two_calls():
        await _FastPollKlingAdapter(tenant_config).generate(req)
        time.sleep(1.1)  # ensure iat differs by at least 1s
        await _FastPollKlingAdapter(tenant_config).generate(req)

    asyncio.get_event_loop().run_until_complete(_two_calls())

    assert len(captured_tokens) == 2
    assert captured_tokens[0] != captured_tokens[1], (
        "JWT must be regenerated per call — caching detected"
    )


class _CapturingSession(_FakeSession):
    """Wrapper that captures the Bearer token from the POST headers
    into an externally-supplied list. Used by the fresh-JWT test only."""

    def __init__(self, inner: _FakeSession, sink: list[str]):
        # Copy state from the inner session.
        super().__init__(
            post_resp=inner._post_resp,
            poll_resps=inner._poll_resps,
            bytes_resp=inner._bytes_resp,
        )
        self._sink = sink

    def post(self, url, json=None, headers=None):
        auth = (headers or {}).get("Authorization", "")
        if auth.startswith("Bearer "):
            self._sink.append(auth.removeprefix("Bearer "))
        return super().post(url, json=json, headers=headers)


# ── Polling state-machine ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_polling_succeeds_on_third_attempt(monkeypatch, tenant_config, req):
    """submitted → processing → succeed proves we don't take the first
    poll response. The poll counter advances through all three."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({
                "code": 0,
                "data": {"task_id": "task-slow", "task_status": "submitted"},
            }),
        ),
        poll_resps=[
            _FakeResp(status=200, body=json.dumps({
                "code": 0,
                "data": {"task_id": "task-slow", "task_status": "submitted"},
            })),
            _FakeResp(status=200, body=json.dumps({
                "code": 0,
                "data": {"task_id": "task-slow", "task_status": "processing"},
            })),
            _FakeResp(status=200, body=json.dumps({
                "code": 0,
                "data": {
                    "task_id": "task-slow",
                    "task_status": "succeed",
                    "task_result": {"videos": [{
                        "url": "https://kling-cdn.example/done.mp4",
                        "duration": "5",
                    }]},
                },
            })),
        ],
    )
    _install_fake_aiohttp(monkeypatch, session)

    result = await _FastPollKlingAdapter(tenant_config).generate(req)

    assert result.provider == "kling"
    assert session.poll_index == 3


@pytest.mark.asyncio
async def test_polling_failed_status_raises_provider_error(monkeypatch, tenant_config, req):
    """task_status == failed → MaicProviderError, with task_status_msg
    surfaced for operator debugging."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({
                "code": 0,
                "data": {"task_id": "task-fail", "task_status": "submitted"},
            }),
        ),
        poll_resps=[_FakeResp(status=200, body=json.dumps({
            "code": 0,
            "data": {
                "task_id": "task-fail",
                "task_status": "failed",
                "task_status_msg": "content moderation blocked the prompt",
            },
        }))],
    )
    _install_fake_aiohttp(monkeypatch, session)

    with pytest.raises(MaicProviderError) as exc:
        await _FastPollKlingAdapter(tenant_config).generate(req)
    msg = str(exc.value)
    assert "failed" in msg
    assert "content moderation" in msg


@pytest.mark.asyncio
async def test_polling_unrecognised_status_raises_provider_error(monkeypatch, tenant_config, req):
    """A brand-new task_status string → fail loud rather than spin."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({
                "code": 0,
                "data": {"task_id": "task-new", "task_status": "submitted"},
            }),
        ),
        poll_resps=[_FakeResp(status=200, body=json.dumps({
            "code": 0,
            "data": {"task_id": "task-new", "task_status": "QUANTUM_SUPERPOSITION"},
        }))],
    )
    _install_fake_aiohttp(monkeypatch, session)

    with pytest.raises(MaicProviderError) as exc:
        await _FastPollKlingAdapter(tenant_config).generate(req)
    assert "QUANTUM_SUPERPOSITION" in str(exc.value)
    assert "unrecognised" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_polling_times_out_when_deadline_exhausted(monkeypatch, tenant_config, req):
    """If the task never reaches terminal before the deadline,
    MaicProviderError. Deadline is a hard cap — no `while True`."""

    class _TinyDeadlineAdapter(KlingVideoAdapter):
        _poll_interval_seconds = 0.05
        _poll_timeout_seconds = 0.15

    pending_resp = _FakeResp(
        status=200,
        body=json.dumps({
            "code": 0,
            "data": {"task_id": "task-slow", "task_status": "processing"},
        }),
    )
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({
                "code": 0,
                "data": {"task_id": "task-slow", "task_status": "submitted"},
            }),
        ),
        poll_resps=[pending_resp for _ in range(500)],
    )
    _install_fake_aiohttp(monkeypatch, session)

    with pytest.raises(MaicProviderError) as exc:
        await _TinyDeadlineAdapter(tenant_config).generate(req)
    assert "timed out" in str(exc.value).lower()
    assert session.poll_index < 20


# ── HTTP error matrix on SUBMIT ──────────────────────────────────────


@pytest.mark.asyncio
async def test_submit_401_raises_config_error(monkeypatch, tenant_config, req):
    """Submit 401 → MaicConfigError (auth — no retry)."""
    session = _FakeSession(
        post_resp=_FakeResp(status=401, body='{"code":1001,"message":"invalid jwt"}'),
    )
    _install_fake_aiohttp(monkeypatch, session)

    with pytest.raises(MaicConfigError) as exc:
        await _FastPollKlingAdapter(tenant_config).generate(req)
    assert "auth" in str(exc.value).lower()
    assert "401" in str(exc.value)
    assert "submit" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_submit_403_raises_config_error(monkeypatch, tenant_config, req):
    session = _FakeSession(post_resp=_FakeResp(status=403, body="forbidden"))
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicConfigError):
        await _FastPollKlingAdapter(tenant_config).generate(req)


@pytest.mark.asyncio
async def test_submit_429_raises_provider_error(monkeypatch, tenant_config, req):
    session = _FakeSession(post_resp=_FakeResp(status=429, body='{"code":429}'))
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollKlingAdapter(tenant_config).generate(req)
    assert "429" in str(exc.value)


@pytest.mark.asyncio
async def test_submit_500_raises_provider_error(monkeypatch, tenant_config, req):
    session = _FakeSession(post_resp=_FakeResp(status=503, body="upstream unavailable"))
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollKlingAdapter(tenant_config).generate(req)
    assert "503" in str(exc.value)


@pytest.mark.asyncio
async def test_submit_other_4xx_raises_provider_error(monkeypatch, tenant_config, req):
    session = _FakeSession(post_resp=_FakeResp(status=400, body='{"code":400}'))
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollKlingAdapter(tenant_config).generate(req)
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
        await _FastPollKlingAdapter(tenant_config).generate(req)
    assert "network error" in str(exc.value).lower()


# ── Kling envelope code != 0 (within 2xx) ─────────────────────────────


@pytest.mark.asyncio
async def test_submit_envelope_code_nonzero_raises_provider_error(
    monkeypatch, tenant_config, req,
):
    """HTTP 200 but Kling envelope reports a logical failure
    (code != 0) — surface as MaicProviderError. Kling occasionally uses
    this for quota/validation errors at the application layer."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({
                "code": 1234,
                "message": "quota exceeded",
                "data": {},
            }),
        ),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollKlingAdapter(tenant_config).generate(req)
    assert "1234" in str(exc.value)
    assert "quota exceeded" in str(exc.value)


# ── HTTP error matrix on POLL ────────────────────────────────────────


@pytest.mark.asyncio
async def test_poll_401_raises_config_error(monkeypatch, tenant_config, req):
    """Poll 401 → MaicConfigError (auth rotated mid-task — rare but real)."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({
                "code": 0,
                "data": {"task_id": "t", "task_status": "submitted"},
            }),
        ),
        poll_resps=[_FakeResp(status=401, body="jwt expired")],
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicConfigError) as exc:
        await _FastPollKlingAdapter(tenant_config).generate(req)
    assert "poll" in str(exc.value).lower()
    assert "401" in str(exc.value)


@pytest.mark.asyncio
async def test_poll_429_raises_provider_error(monkeypatch, tenant_config, req):
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({
                "code": 0,
                "data": {"task_id": "t", "task_status": "submitted"},
            }),
        ),
        poll_resps=[_FakeResp(status=429, body="throttled")],
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollKlingAdapter(tenant_config).generate(req)
    assert "429" in str(exc.value)
    assert "poll" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_poll_5xx_raises_provider_error(monkeypatch, tenant_config, req):
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({
                "code": 0,
                "data": {"task_id": "t", "task_status": "submitted"},
            }),
        ),
        poll_resps=[_FakeResp(status=502, body="bad gateway")],
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollKlingAdapter(tenant_config).generate(req)
    assert "502" in str(exc.value)


# ── Response-shape errors ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_submit_malformed_json_raises_provider_error(monkeypatch, tenant_config, req):
    session = _FakeSession(post_resp=_FakeResp(status=200, body="not-json{{{"))
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollKlingAdapter(tenant_config).generate(req)
    assert "malformed" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_submit_missing_task_id_raises_provider_error(monkeypatch, tenant_config, req):
    """Submit returned envelope but no data.task_id → MaicProviderError."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({"code": 0, "data": {}}),
        ),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollKlingAdapter(tenant_config).generate(req)
    assert "task_id" in str(exc.value)


@pytest.mark.asyncio
async def test_poll_missing_task_status_raises_provider_error(monkeypatch, tenant_config, req):
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({
                "code": 0,
                "data": {"task_id": "t", "task_status": "submitted"},
            }),
        ),
        poll_resps=[_FakeResp(status=200, body=json.dumps({
            "code": 0,
            "data": {},
        }))],
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollKlingAdapter(tenant_config).generate(req)
    assert "task_status" in str(exc.value)


@pytest.mark.asyncio
async def test_succeeded_with_empty_url_raises_provider_error(monkeypatch, tenant_config, req):
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({
                "code": 0,
                "data": {"task_id": "t", "task_status": "submitted"},
            }),
        ),
        poll_resps=[_FakeResp(status=200, body=json.dumps({
            "code": 0,
            "data": {
                "task_id": "t",
                "task_status": "succeed",
                "task_result": {"videos": [{"url": ""}]},
            },
        }))],
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError):
        await _FastPollKlingAdapter(tenant_config).generate(req)


@pytest.mark.asyncio
async def test_succeeded_with_missing_videos_raises_provider_error(monkeypatch, tenant_config, req):
    """succeed but no task_result.videos array → MaicProviderError."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({
                "code": 0,
                "data": {"task_id": "t", "task_status": "submitted"},
            }),
        ),
        poll_resps=[_FakeResp(status=200, body=json.dumps({
            "code": 0,
            "data": {
                "task_id": "t",
                "task_status": "succeed",
                "task_result": {},
            },
        }))],
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollKlingAdapter(tenant_config).generate(req)
    assert "videos" in str(exc.value)


@pytest.mark.asyncio
async def test_video_fetch_404_raises_provider_error(monkeypatch, tenant_config, req):
    """SUCCEEDED, URL returned, but bytes GET returns 404 → MaicProviderError."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({
                "code": 0,
                "data": {"task_id": "t", "task_status": "submitted"},
            }),
        ),
        poll_resps=[_FakeResp(status=200, body=json.dumps({
            "code": 0,
            "data": {
                "task_id": "t",
                "task_status": "succeed",
                "task_result": {"videos": [{
                    "url": "https://kling-cdn.example/expired.mp4",
                    "duration": "5",
                }]},
            },
        }))],
        bytes_resp=_FakeResp(status=404, body="not found"),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollKlingAdapter(tenant_config).generate(req)
    assert "fetch" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_video_fetch_zero_bytes_raises_provider_error(monkeypatch, tenant_config, req):
    """Bytes GET returns 200 but empty body → MaicProviderError."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({
                "code": 0,
                "data": {"task_id": "t", "task_status": "submitted"},
            }),
        ),
        poll_resps=[_FakeResp(status=200, body=json.dumps({
            "code": 0,
            "data": {
                "task_id": "t",
                "task_status": "succeed",
                "task_result": {"videos": [{
                    "url": "https://kling-cdn.example/zero.mp4",
                    "duration": "5",
                }]},
            },
        }))],
        bytes_resp=_FakeResp(status=200, body=b"", headers={"Content-Type": "video/mp4"}),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollKlingAdapter(tenant_config).generate(req)
    assert "zero bytes" in str(exc.value).lower()


# ── Auth / api-key format / SSRF / config errors ─────────────────────


@pytest.mark.asyncio
async def test_missing_api_key_raises_config_error(monkeypatch, req):
    """No api_key → MaicConfigError BEFORE any HTTP."""
    cfg = SimpleNamespace(
        get_video_api_key=lambda: "",
        video_base_url="",
        video_model="kling-v1",
    )
    _install_fake_aiohttp(monkeypatch)
    with pytest.raises(MaicConfigError) as exc:
        await _FastPollKlingAdapter(cfg).generate(req)
    assert "api_key required" in str(exc.value)


@pytest.mark.asyncio
async def test_api_key_without_colon_raises_config_error(monkeypatch, req):
    """api_key with no ':' separator → MaicConfigError. Defensive proof
    that the adapter never silently uses the whole string as access key."""
    cfg = SimpleNamespace(
        get_video_api_key=lambda: "just-a-single-token-no-colon",
        video_base_url="",
        video_model="kling-v1",
    )
    _install_fake_aiohttp(monkeypatch)
    with pytest.raises(MaicConfigError) as exc:
        await _FastPollKlingAdapter(cfg).generate(req)
    assert "access_key:secret_key" in str(exc.value)


@pytest.mark.asyncio
async def test_api_key_with_empty_access_half_raises_config_error(monkeypatch, req):
    """api_key like ':secret' → MaicConfigError (access half empty)."""
    cfg = SimpleNamespace(
        get_video_api_key=lambda: ":only-secret",
        video_base_url="",
        video_model="kling-v1",
    )
    _install_fake_aiohttp(monkeypatch)
    with pytest.raises(MaicConfigError):
        await _FastPollKlingAdapter(cfg).generate(req)


@pytest.mark.asyncio
async def test_api_key_with_empty_secret_half_raises_config_error(monkeypatch, req):
    """api_key like 'access:' → MaicConfigError (secret half empty)."""
    cfg = SimpleNamespace(
        get_video_api_key=lambda: "only-access:",
        video_base_url="",
        video_model="kling-v1",
    )
    _install_fake_aiohttp(monkeypatch)
    with pytest.raises(MaicConfigError):
        await _FastPollKlingAdapter(cfg).generate(req)


@pytest.mark.asyncio
async def test_api_key_whitespace_halves_raises_config_error(monkeypatch, req):
    """Stripping reduces both halves to empty → MaicConfigError. Catches
    operators who paste 'key: secret ' with a stray space, then either
    half evaporates to ''."""
    cfg = SimpleNamespace(
        get_video_api_key=lambda: "   :   ",
        video_base_url="",
        video_model="kling-v1",
    )
    _install_fake_aiohttp(monkeypatch)
    with pytest.raises(MaicConfigError):
        await _FastPollKlingAdapter(cfg).generate(req)


@pytest.mark.asyncio
async def test_custom_base_url_goes_through_ssrf_guard(monkeypatch, req):
    """Tenant-supplied base URL pointing at localhost → SSRF guard rejects."""
    cfg = SimpleNamespace(
        get_video_api_key=lambda: "ak:sk",
        video_base_url="http://127.0.0.1:8080",
        video_model="kling-v1",
    )
    _install_fake_aiohttp(monkeypatch)
    with pytest.raises(MaicConfigError) as exc:
        await _FastPollKlingAdapter(cfg).generate(req)
    assert "ssrf" in str(exc.value).lower() or "base_url" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_default_base_url_skips_ssrf_check(monkeypatch, tenant_config, req):
    """Empty video_base_url uses the default Kling endpoint without
    invoking the SSRF guard."""
    _install_fake_aiohttp(monkeypatch)
    result = await _FastPollKlingAdapter(tenant_config).generate(req)
    assert result.provider == "kling"


# ── Cost estimator (pure unit, no IO) ─────────────────────────────────


def test_cost_estimator_returns_none_for_all_inputs():
    """No stable public pricing — always None. Telemetry is non-blocking."""
    assert KlingVideoAdapter._estimate_cost("kling-v1", 5) is None
    assert KlingVideoAdapter._estimate_cost("kling-v1-6", 10) is None
    assert KlingVideoAdapter._estimate_cost("unknown-model", 60) is None


# ── Registry registration ─────────────────────────────────────────────


def test_adapter_is_registered_on_import():
    """Importing the adapter module registered it under (video, kling)."""
    from apps.maic.media.providers import _REGISTRY
    assert ("video", "kling") in _REGISTRY
    assert _REGISTRY[("video", "kling")] is KlingVideoAdapter


def test_default_timeout_matches_video_budget():
    """Video adapters need a higher per-attempt cap than image. The
    brief requires 600s for Kling — regression-guard so a future refactor
    doesn't drop it back to the 60s sync default."""
    assert KlingVideoAdapter.default_timeout_seconds == 600


def test_poll_helper_is_a_method():
    """The polling helper must live on the adapter so future video
    adapters can override the cadence without re-implementing it.
    Regression-guard against a refactor pass that hoists it to module
    level."""
    assert hasattr(KlingVideoAdapter, "_poll_task_until_done")
    assert callable(KlingVideoAdapter._poll_task_until_done)
    import inspect
    assert inspect.iscoroutinefunction(KlingVideoAdapter._poll_task_until_done)


# ── Live smoke (gated) ────────────────────────────────────────────────


@pytest.mark.skipif(
    os.environ.get("MAIC_KLING_LIVE_SMOKE") != "1"
    or not os.environ.get("KLING_API_KEY"),
    reason=(
        "live Kling smoke disabled — set MAIC_KLING_LIVE_SMOKE=1 and "
        "KLING_API_KEY=<access:secret> (note the colon-separated "
        "composite format) to enable. Kling video generation has a "
        "per-clip cost; consult the Kling console before enabling."
    ),
)
@pytest.mark.asyncio
async def test_live_smoke_real_kling_call(tmp_path, settings):
    """Hits the real Kling API end-to-end. Skipped unless env vars set.

    KLING_API_KEY must be in 'access_key:secret_key' format (the same
    layout the adapter expects on TenantAIConfig.get_video_api_key()).

    Asserts:
      - Real submit + poll + bytes-fetch round-trip succeeds
      - Generated video is uploaded to local storage
      - File on disk is non-zero and starts with an MP4-ish header
    """
    settings.MEDIA_ROOT = str(tmp_path)
    api_key = os.environ["KLING_API_KEY"]
    assert ":" in api_key, "guarded above; KLING_API_KEY must be 'access:secret'"
    cfg = SimpleNamespace(
        get_video_api_key=lambda: api_key,
        video_base_url="",
        video_model=os.environ.get("KLING_MODEL", "kling-v1"),
    )
    req = VideoGenerationRequest(
        prompt="a gentle wave lapping on a sandy beach, slow motion",
        duration_seconds=5,
        aspect_ratio="16:9",
        tenant_id="live-smoke",
        scene_id="live-smoke-scene",
    )
    result = await KlingVideoAdapter(cfg).generate(req)
    assert result.provider == "kling"
    assert "maic/live-smoke/video/" in result.url
    # File on disk should start with MP4 'ftyp' atom signature.
    from django.core.files.storage import default_storage
    storage_key = result.url.split("/media/", 1)[1] if "/media/" in result.url else None
    if storage_key:
        with default_storage.open(storage_key, "rb") as fh:
            header = fh.read(12)
        # MP4 ISO-BMFF: bytes 4-8 are 'ftyp'
        assert header[4:8] == b"ftyp", f"expected MP4 ftyp atom, got {header!r}"
