"""Tests for the Minimax video adapter (MAIC-912).

The first VIDEO adapter — also the test template Veo / Kling /
Seedance / Grok-Video tests will copy. Builds on the qwen async-polling
test template (tests_qwen_image.py) with one major extension: the fake
session dispatches GET responses by URL path because the 3-step flow
hits THREE different GET endpoints with three different response shapes:

    1. /query/video_generation?task_id=...    (polling — repeated)
    2. /files/retrieve?file_id=...            (retrieve — once)
    3. <signed CDN URL>                       (bytes download — once)

Discipline:
  - IO-boundary fake only: ``aiohttp`` is injected via
    monkeypatch.setitem(sys.modules, "aiohttp", fake) — same pattern as
    every other Phase 9 sibling adapter.
  - No mocks of MinimaxVideoAdapter itself. Real adapter, real Pydantic,
    real Django storage.
  - Polling cadence shortened via subclass override of
    ``_poll_interval_seconds`` + ``_poll_timeout_seconds`` — keeps
    tests fast while exercising the real asyncio.sleep + clock-check
    paths.
  - Live smoke gated on MAIC_MINIMAX_VIDEO_LIVE_SMOKE=1 AND
    MINIMAX_API_KEY env vars (Phase 5 key reuse — same Minimax account
    issues one platform-wide key).

Test layout:
  - Fake aiohttp infrastructure with URL-dispatching GET (poll vs
    retrieve vs CDN download)
  - Happy path + request-shape contract checks
  - Polling state-machine tests (Preparing → Processing → Success;
    Fail; unknown status; deadline exhaustion)
  - HTTP error matrix on each of submit / poll / retrieve
  - base_resp envelope checks on each of submit / poll / retrieve
  - Response-shape errors (malformed JSON, missing fields, etc.)
  - Env-var key fallback (Phase 5 TTS pattern)
  - SSRF + missing-key + base URL handling
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
from apps.maic.media.adapters.minimax_video import MinimaxVideoAdapter
from apps.maic.media.types import VideoGenerationRequest


# ── Fake aiohttp infrastructure (IO-boundary only) ─────────────────────


class _FakeResp:
    """Stand-in for an aiohttp ClientResponse. Supports the async
    context-manager protocol and exposes status + headers + text/read/json.
    """

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
    """Stand-in for aiohttp.ClientSession with URL-DISPATCHING GET.

    The 3-step Minimax video flow hits three distinct GET endpoints
    that return three different shapes. Rather than maintaining a
    flat sequence (which would couple the test to the exact order of
    poll attempts and the position of the retrieve / bytes calls), we
    dispatch by URL substring:

        "/query/video_generation"  → next poll response (sequence,
                                     consumed in order)
        "/files/retrieve"          → the retrieve response (single)
        anything else              → the bytes download response

    Test code can express "drive the polling state machine through N
    states, then retrieve, then download" purely declaratively.
    """

    def __init__(
        self,
        *,
        post_resp: _FakeResp,
        poll_resps: list[_FakeResp] | None = None,
        retrieve_resp: _FakeResp | None = None,
        bytes_resp: _FakeResp | None = None,
    ):
        self._post_resp = post_resp
        self._poll_resps = list(poll_resps or [])
        # Default retrieve / bytes responses keep the happy-path test
        # tiny — only tests that exercise non-default behaviour need
        # to override.
        self._retrieve_resp = retrieve_resp or _FakeResp(
            status=200,
            body=json.dumps({
                "file": {
                    "file_id": "file-123",
                    "download_url": "https://minimax-cdn.example/video-xyz.mp4",
                    "filename": "video-xyz.mp4",
                },
                "base_resp": {"status_code": 0, "status_msg": "success"},
            }),
        )
        self._bytes_resp = bytes_resp or _FakeResp(
            status=200,
            body=b"MP4-bytes-fake",
            headers={"Content-Type": "video/mp4"},
        )

        # Inspection hooks for tests.
        self.last_post_url: str | None = None
        self.last_post_json: dict | None = None
        self.last_post_headers: dict | None = None
        self.last_get_urls: list[str] = []
        self.last_get_headers: list[dict | None] = []
        self.poll_index: int = 0
        self.retrieve_calls: int = 0
        self.bytes_calls: int = 0

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
        if "/query/video_generation" in url:
            if self.poll_index >= len(self._poll_resps):
                raise AssertionError(
                    f"_FakeSession: poll GET #{self.poll_index + 1} but only "
                    f"{len(self._poll_resps)} poll responses provided. Add "
                    "more poll_resps or shorten the test."
                )
            resp = self._poll_resps[self.poll_index]
            self.poll_index += 1
            return resp
        if "/files/retrieve" in url:
            self.retrieve_calls += 1
            return self._retrieve_resp
        # Anything else must be the CDN bytes download.
        self.bytes_calls += 1
        return self._bytes_resp


class _FakeClientError(Exception):
    """Stand-in for aiohttp.ClientError — tests that exercise network
    failure raise this from inside the fake session."""


def _install_fake_aiohttp(monkeypatch, session: _FakeSession | None = None) -> _FakeSession:
    """Inject a fake aiohttp module exposing ClientSession + ClientError.

    Returns the session so tests can assert on captured request shape.
    """
    if session is None:
        # Default to a happy-path session: submit returns task_id,
        # one poll returns Success with file_id, retrieve returns a
        # CDN url, bytes download returns an MP4 payload.
        session = _FakeSession(
            post_resp=_FakeResp(
                status=200,
                body=json.dumps({
                    "task_id": "task-abc-123",
                    "base_resp": {"status_code": 0, "status_msg": "success"},
                }),
            ),
            poll_resps=[
                _FakeResp(
                    status=200,
                    body=json.dumps({
                        "task_id": "task-abc-123",
                        "status": "Success",
                        "file_id": "file-123",
                        "video_width": 1280,
                        "video_height": 720,
                        "base_resp": {"status_code": 0, "status_msg": "success"},
                    }),
                ),
            ],
        )

    def _client_session_factory():
        return session

    fake = types.ModuleType("aiohttp")
    fake.ClientSession = _client_session_factory  # type: ignore[attr-defined]
    fake.ClientError = _FakeClientError  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "aiohttp", fake)
    return session


# ── Adapter subclass with shortened polling cadence for tests ─────────


class _FastPollMinimaxVideoAdapter(MinimaxVideoAdapter):
    """Subclass that polls every ~0s so tests don't wait 5s/iteration.

    Still gives ~1.5s of total budget — plenty for any happy-path test
    while leaving room for the deadline-exhaustion test to trip its
    own (much tighter) deadline."""

    _poll_interval_seconds = 0.001
    _poll_timeout_seconds = 1.5


# ── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture
def tenant_config():
    """Minimal TenantAIConfig-shaped object. The adapter only touches:
    get_video_api_key(), video_base_url, video_model — plus the optional
    allow_env_key_fallback opt-out."""
    return SimpleNamespace(
        get_video_api_key=lambda: "mm-video-test-key",
        video_base_url="",
        video_model="MiniMax-Hailuo-2.3",
    )


@pytest.fixture
def req():
    return VideoGenerationRequest(
        prompt="a slow pan across a quiet mountain lake at dawn",
        tenant_id="t-1",
        scene_id="scene-abc",
        duration_seconds=6,
    )


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, settings):
    """Point MEDIA_ROOT at tmp so we don't pollute the dev tree."""
    settings.MEDIA_ROOT = str(tmp_path)


@pytest.fixture(autouse=True)
def clear_env_key(monkeypatch):
    """Ensure MINIMAX_API_KEY env var leakage from the host shell or a
    previous test never silently rescues an empty-tenant-key case.
    Tests that exercise the fallback set it explicitly."""
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)


# ── Happy path ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_happy_path_returns_result_with_storage_url(monkeypatch, tenant_config, req):
    """End-to-end: submit → poll Success → retrieve → bytes → storage.
    URL points to OUR storage (NOT Minimax's CDN)."""
    session = _install_fake_aiohttp(monkeypatch)

    adapter = _FastPollMinimaxVideoAdapter(tenant_config)
    result = await adapter.generate(req)

    assert result.provider == "minimax_video"
    assert result.model == "MiniMax-Hailuo-2.3"
    assert result.duration_seconds == 6
    assert "minimax-cdn.example" not in result.url
    assert "maic/t-1/video/" in result.url
    assert "scene-abc__" in result.url
    # File ends in .mp4 per the storage ext map.
    assert result.url.endswith(".mp4")
    # No pricing table for Minimax video — cost is None.
    assert result.cost_usd_estimate is None

    # Confirm the bytes GET hit the CDN URL the retrieve endpoint
    # returned (proves the 3-step flow wired up correctly).
    assert any("minimax-cdn.example/video-xyz.mp4" in u for u in session.last_get_urls)
    assert session.bytes_calls == 1
    assert session.retrieve_calls == 1


@pytest.mark.asyncio
async def test_submit_request_shape_matches_minimax_contract(monkeypatch, tenant_config, req):
    """The submit body must use Minimax's {model, prompt, duration,
    resolution, prompt_optimizer} shape with Authorization +
    Content-Type: application/json; charset=utf-8."""
    session = _install_fake_aiohttp(monkeypatch)

    await _FastPollMinimaxVideoAdapter(tenant_config).generate(req)

    assert session.last_post_url == "https://api.minimaxi.com/v1/video_generation"
    headers = session.last_post_headers or {}
    assert headers.get("Authorization") == "Bearer mm-video-test-key"
    # charset=utf-8 explicitly mirrored from upstream contract.
    assert "application/json" in headers.get("Content-Type", "")
    assert "charset=utf-8" in headers.get("Content-Type", "")
    body = session.last_post_json or {}
    assert body["model"] == "MiniMax-Hailuo-2.3"
    assert body["prompt"] == "a slow pan across a quiet mountain lake at dawn"
    assert body["duration"] == 6
    assert body["resolution"] == "768P"
    assert body["prompt_optimizer"] is False


@pytest.mark.asyncio
async def test_poll_endpoint_uses_task_id_as_query_string(monkeypatch, tenant_config, req):
    """The poll GET must target /query/video_generation?task_id=<id>
    with the auth header. Distinct from DashScope's path-style /tasks/<id>.
    """
    session = _install_fake_aiohttp(monkeypatch)
    await _FastPollMinimaxVideoAdapter(tenant_config).generate(req)

    poll_url = session.last_get_urls[0]
    assert "/query/video_generation" in poll_url
    assert "task_id=task-abc-123" in poll_url
    poll_headers = session.last_get_headers[0] or {}
    assert poll_headers.get("Authorization") == "Bearer mm-video-test-key"


@pytest.mark.asyncio
async def test_retrieve_endpoint_uses_file_id_as_query_string(monkeypatch, tenant_config, req):
    """The retrieve GET must target /files/retrieve?file_id=<id>."""
    session = _install_fake_aiohttp(monkeypatch)
    await _FastPollMinimaxVideoAdapter(tenant_config).generate(req)

    retrieve_urls = [u for u in session.last_get_urls if "/files/retrieve" in u]
    assert len(retrieve_urls) == 1
    assert "file_id=file-123" in retrieve_urls[0]


# ── Polling state-machine ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_polling_succeeds_after_multiple_in_progress_states(monkeypatch, tenant_config, req):
    """Preparing → Queueing → Processing → Success proves we walk through
    every in-progress state. Case sensitivity matters (Minimax emits
    TitleCase, not UPPERCASE)."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({"task_id": "task-slow", "base_resp": {"status_code": 0}}),
        ),
        poll_resps=[
            _FakeResp(
                status=200,
                body=json.dumps({
                    "task_id": "task-slow", "status": "Preparing",
                    "base_resp": {"status_code": 0},
                }),
            ),
            _FakeResp(
                status=200,
                body=json.dumps({
                    "task_id": "task-slow", "status": "Queueing",
                    "base_resp": {"status_code": 0},
                }),
            ),
            _FakeResp(
                status=200,
                body=json.dumps({
                    "task_id": "task-slow", "status": "Processing",
                    "base_resp": {"status_code": 0},
                }),
            ),
            _FakeResp(
                status=200,
                body=json.dumps({
                    "task_id": "task-slow",
                    "status": "Success",
                    "file_id": "file-slow",
                    "base_resp": {"status_code": 0},
                }),
            ),
        ],
        retrieve_resp=_FakeResp(
            status=200,
            body=json.dumps({
                "file": {"file_id": "file-slow",
                          "download_url": "https://minimax-cdn.example/slow.mp4"},
                "base_resp": {"status_code": 0},
            }),
        ),
    )
    _install_fake_aiohttp(monkeypatch, session)

    result = await _FastPollMinimaxVideoAdapter(tenant_config).generate(req)
    assert result.provider == "minimax_video"
    assert session.poll_index == 4  # all 4 poll responses consumed


@pytest.mark.asyncio
async def test_polling_fail_status_raises_provider_error(monkeypatch, tenant_config, req):
    """status == 'Fail' (TitleCase) → MaicProviderError with the
    upstream status_msg propagated."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({"task_id": "task-fail", "base_resp": {"status_code": 0}}),
        ),
        poll_resps=[
            _FakeResp(
                status=200,
                body=json.dumps({
                    "task_id": "task-fail",
                    "status": "Fail",
                    "base_resp": {
                        "status_code": 0,
                        "status_msg": "model worker crashed",
                    },
                }),
            ),
        ],
    )
    _install_fake_aiohttp(monkeypatch, session)

    with pytest.raises(MaicProviderError) as exc:
        await _FastPollMinimaxVideoAdapter(tenant_config).generate(req)
    msg = str(exc.value)
    assert "Fail" in msg
    assert "model worker crashed" in msg


@pytest.mark.asyncio
async def test_polling_unrecognised_status_raises_provider_error(monkeypatch, tenant_config, req):
    """An unrecognised status string → fail loud rather than spin."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({"task_id": "task-new", "base_resp": {"status_code": 0}}),
        ),
        poll_resps=[
            _FakeResp(
                status=200,
                body=json.dumps({
                    "task_id": "task-new",
                    "status": "QUANTUM_PURGATORY",
                    "base_resp": {"status_code": 0},
                }),
            ),
        ],
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollMinimaxVideoAdapter(tenant_config).generate(req)
    assert "QUANTUM_PURGATORY" in str(exc.value)
    assert "unrecognised" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_polling_times_out_when_deadline_exhausted(monkeypatch, tenant_config, req):
    """Polling must respect a HARD deadline — no while True. Provision
    way more in-progress responses than the deadline allows iterations."""

    class _TinyDeadlineAdapter(MinimaxVideoAdapter):
        _poll_interval_seconds = 0.05
        _poll_timeout_seconds = 0.15

    pending_resp = _FakeResp(
        status=200,
        body=json.dumps({
            "task_id": "task-slow", "status": "Processing",
            "base_resp": {"status_code": 0},
        }),
    )
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({"task_id": "task-slow", "base_resp": {"status_code": 0}}),
        ),
        poll_resps=[pending_resp for _ in range(500)],
    )
    _install_fake_aiohttp(monkeypatch, session)

    with pytest.raises(MaicProviderError) as exc:
        await _TinyDeadlineAdapter(tenant_config).generate(req)
    assert "timed out" in str(exc.value).lower()
    # We tripped the deadline well before exhausting 500 responses.
    assert session.poll_index < 20


@pytest.mark.asyncio
async def test_polling_success_without_file_id_raises_provider_error(monkeypatch, tenant_config, req):
    """Success status but no file_id field → MaicProviderError. The
    contract guarantees file_id on success; absence is a server bug
    we surface rather than crash later."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({"task_id": "t", "base_resp": {"status_code": 0}}),
        ),
        poll_resps=[
            _FakeResp(
                status=200,
                body=json.dumps({
                    "task_id": "t",
                    "status": "Success",
                    # file_id omitted
                    "base_resp": {"status_code": 0},
                }),
            ),
        ],
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollMinimaxVideoAdapter(tenant_config).generate(req)
    assert "file_id" in str(exc.value)


@pytest.mark.asyncio
async def test_polling_success_with_integer_file_id_coerced_to_string(monkeypatch, tenant_config, req):
    """Some Minimax regions return file_id as an integer. The adapter
    must coerce to string for the retrieve URL without raising."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({"task_id": "t", "base_resp": {"status_code": 0}}),
        ),
        poll_resps=[
            _FakeResp(
                status=200,
                body=json.dumps({
                    "task_id": "t",
                    "status": "Success",
                    "file_id": 4242,  # integer!
                    "base_resp": {"status_code": 0},
                }),
            ),
        ],
        retrieve_resp=_FakeResp(
            status=200,
            body=json.dumps({
                "file": {"file_id": 4242,
                          "download_url": "https://minimax-cdn.example/int.mp4"},
                "base_resp": {"status_code": 0},
            }),
        ),
    )
    _install_fake_aiohttp(monkeypatch, session)
    result = await _FastPollMinimaxVideoAdapter(tenant_config).generate(req)
    assert result.provider == "minimax_video"
    retrieve_urls = [u for u in session.last_get_urls if "/files/retrieve" in u]
    assert "file_id=4242" in retrieve_urls[0]


# ── HTTP error matrix on SUBMIT ──────────────────────────────────────


@pytest.mark.asyncio
async def test_submit_401_raises_config_error(monkeypatch, tenant_config, req):
    """Submit 401 → MaicConfigError (auth — orchestrator does NOT retry)."""
    session = _FakeSession(
        post_resp=_FakeResp(status=401, body='{"error":"bad key"}'),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicConfigError) as exc:
        await _FastPollMinimaxVideoAdapter(tenant_config).generate(req)
    assert "auth" in str(exc.value).lower()
    assert "401" in str(exc.value)
    assert "submit" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_submit_403_raises_config_error(monkeypatch, tenant_config, req):
    """Submit 403 → MaicConfigError."""
    session = _FakeSession(post_resp=_FakeResp(status=403, body="forbidden"))
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicConfigError):
        await _FastPollMinimaxVideoAdapter(tenant_config).generate(req)


@pytest.mark.asyncio
async def test_submit_429_raises_provider_error(monkeypatch, tenant_config, req):
    """Submit 429 → MaicProviderError (orchestrator may retry)."""
    session = _FakeSession(post_resp=_FakeResp(status=429, body="throttled"))
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollMinimaxVideoAdapter(tenant_config).generate(req)
    assert "429" in str(exc.value)


@pytest.mark.asyncio
async def test_submit_500_raises_provider_error(monkeypatch, tenant_config, req):
    """Submit 5xx → MaicProviderError."""
    session = _FakeSession(post_resp=_FakeResp(status=503, body="unavailable"))
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollMinimaxVideoAdapter(tenant_config).generate(req)
    assert "503" in str(exc.value)


@pytest.mark.asyncio
async def test_submit_base_resp_2049_raises_config_error(monkeypatch, tenant_config, req):
    """Submit 200 but base_resp.status_code=2049 → MaicConfigError.
    Permanent (wrong region or revoked key) — orchestrator must not retry."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({
                "base_resp": {"status_code": 2049, "status_msg": "invalid api key"},
            }),
        ),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicConfigError) as exc:
        await _FastPollMinimaxVideoAdapter(tenant_config).generate(req)
    assert "2049" in str(exc.value)
    assert "submit" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_submit_base_resp_1004_raises_config_error(monkeypatch, tenant_config, req):
    """Submit 200 + base_resp.status_code=1004 → MaicConfigError."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({
                "base_resp": {"status_code": 1004, "status_msg": "auth failed"},
            }),
        ),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicConfigError) as exc:
        await _FastPollMinimaxVideoAdapter(tenant_config).generate(req)
    assert "1004" in str(exc.value)


@pytest.mark.asyncio
async def test_submit_base_resp_other_raises_provider_error(monkeypatch, tenant_config, req):
    """Submit 200 + non-auth base_resp status_code → MaicProviderError."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({
                "base_resp": {"status_code": 2013, "status_msg": "invalid parameter"},
            }),
        ),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollMinimaxVideoAdapter(tenant_config).generate(req)
    assert "2013" in str(exc.value)


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
        await _FastPollMinimaxVideoAdapter(tenant_config).generate(req)
    assert "network error" in str(exc.value).lower()


# ── HTTP error matrix on POLL ────────────────────────────────────────


@pytest.mark.asyncio
async def test_poll_401_raises_config_error(monkeypatch, tenant_config, req):
    """Poll 401 → MaicConfigError (auth rotated mid-task)."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({"task_id": "t", "base_resp": {"status_code": 0}}),
        ),
        poll_resps=[_FakeResp(status=401, body="expired")],
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicConfigError) as exc:
        await _FastPollMinimaxVideoAdapter(tenant_config).generate(req)
    assert "poll" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_poll_5xx_raises_provider_error(monkeypatch, tenant_config, req):
    """Poll 5xx → MaicProviderError."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({"task_id": "t", "base_resp": {"status_code": 0}}),
        ),
        poll_resps=[_FakeResp(status=502, body="bad gateway")],
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollMinimaxVideoAdapter(tenant_config).generate(req)
    assert "502" in str(exc.value)


@pytest.mark.asyncio
async def test_poll_base_resp_2049_raises_config_error(monkeypatch, tenant_config, req):
    """Poll 200 but base_resp.status_code=2049 → MaicConfigError. Same
    auth-class promotion as submit; we check the envelope on every leg."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({"task_id": "t", "base_resp": {"status_code": 0}}),
        ),
        poll_resps=[
            _FakeResp(
                status=200,
                body=json.dumps({
                    "task_id": "t",
                    "status": "Processing",
                    "base_resp": {"status_code": 2049, "status_msg": "invalid key"},
                }),
            ),
        ],
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicConfigError) as exc:
        await _FastPollMinimaxVideoAdapter(tenant_config).generate(req)
    assert "2049" in str(exc.value)
    assert "poll" in str(exc.value).lower()


# ── HTTP error matrix on RETRIEVE ────────────────────────────────────


@pytest.mark.asyncio
async def test_retrieve_401_raises_config_error(monkeypatch, tenant_config, req):
    """Retrieve 401 → MaicConfigError."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({"task_id": "t", "base_resp": {"status_code": 0}}),
        ),
        poll_resps=[
            _FakeResp(
                status=200,
                body=json.dumps({
                    "task_id": "t", "status": "Success", "file_id": "f-1",
                    "base_resp": {"status_code": 0},
                }),
            ),
        ],
        retrieve_resp=_FakeResp(status=401, body="auth expired"),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicConfigError) as exc:
        await _FastPollMinimaxVideoAdapter(tenant_config).generate(req)
    assert "retrieve" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_retrieve_429_raises_provider_error(monkeypatch, tenant_config, req):
    """Retrieve 429 → MaicProviderError."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({"task_id": "t", "base_resp": {"status_code": 0}}),
        ),
        poll_resps=[
            _FakeResp(
                status=200,
                body=json.dumps({
                    "task_id": "t", "status": "Success", "file_id": "f-1",
                    "base_resp": {"status_code": 0},
                }),
            ),
        ],
        retrieve_resp=_FakeResp(status=429, body="throttled"),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollMinimaxVideoAdapter(tenant_config).generate(req)
    assert "429" in str(exc.value)


@pytest.mark.asyncio
async def test_retrieve_base_resp_1004_raises_config_error(monkeypatch, tenant_config, req):
    """Retrieve 200 + base_resp.status_code=1004 → MaicConfigError. Auth-
    class envelope error on the third HTTP leg."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({"task_id": "t", "base_resp": {"status_code": 0}}),
        ),
        poll_resps=[
            _FakeResp(
                status=200,
                body=json.dumps({
                    "task_id": "t", "status": "Success", "file_id": "f-1",
                    "base_resp": {"status_code": 0},
                }),
            ),
        ],
        retrieve_resp=_FakeResp(
            status=200,
            body=json.dumps({
                "base_resp": {"status_code": 1004, "status_msg": "auth failed"},
            }),
        ),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicConfigError) as exc:
        await _FastPollMinimaxVideoAdapter(tenant_config).generate(req)
    assert "1004" in str(exc.value)
    assert "retrieve" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_retrieve_base_resp_1008_raises_config_error(monkeypatch, tenant_config, req):
    """Retrieve 200 + base_resp.status_code=1008 → MaicConfigError."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({"task_id": "t", "base_resp": {"status_code": 0}}),
        ),
        poll_resps=[
            _FakeResp(
                status=200,
                body=json.dumps({
                    "task_id": "t", "status": "Success", "file_id": "f-1",
                    "base_resp": {"status_code": 0},
                }),
            ),
        ],
        retrieve_resp=_FakeResp(
            status=200,
            body=json.dumps({
                "base_resp": {"status_code": 1008, "status_msg": "insufficient balance"},
            }),
        ),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicConfigError) as exc:
        await _FastPollMinimaxVideoAdapter(tenant_config).generate(req)
    assert "1008" in str(exc.value)


@pytest.mark.asyncio
async def test_retrieve_base_resp_2049_raises_config_error(monkeypatch, tenant_config, req):
    """Retrieve 200 + base_resp.status_code=2049 → MaicConfigError."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({"task_id": "t", "base_resp": {"status_code": 0}}),
        ),
        poll_resps=[
            _FakeResp(
                status=200,
                body=json.dumps({
                    "task_id": "t", "status": "Success", "file_id": "f-1",
                    "base_resp": {"status_code": 0},
                }),
            ),
        ],
        retrieve_resp=_FakeResp(
            status=200,
            body=json.dumps({
                "base_resp": {"status_code": 2049, "status_msg": "invalid key"},
            }),
        ),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicConfigError) as exc:
        await _FastPollMinimaxVideoAdapter(tenant_config).generate(req)
    assert "2049" in str(exc.value)


@pytest.mark.asyncio
async def test_retrieve_missing_file_field_raises_provider_error(monkeypatch, tenant_config, req):
    """Retrieve 200 but no 'file' object → MaicProviderError."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({"task_id": "t", "base_resp": {"status_code": 0}}),
        ),
        poll_resps=[
            _FakeResp(
                status=200,
                body=json.dumps({
                    "task_id": "t", "status": "Success", "file_id": "f-1",
                    "base_resp": {"status_code": 0},
                }),
            ),
        ],
        retrieve_resp=_FakeResp(
            status=200,
            body=json.dumps({"base_resp": {"status_code": 0}}),
        ),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollMinimaxVideoAdapter(tenant_config).generate(req)
    assert "file" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_retrieve_missing_download_url_raises_provider_error(monkeypatch, tenant_config, req):
    """Retrieve 200, has 'file', but no download_url → MaicProviderError."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({"task_id": "t", "base_resp": {"status_code": 0}}),
        ),
        poll_resps=[
            _FakeResp(
                status=200,
                body=json.dumps({
                    "task_id": "t", "status": "Success", "file_id": "f-1",
                    "base_resp": {"status_code": 0},
                }),
            ),
        ],
        retrieve_resp=_FakeResp(
            status=200,
            body=json.dumps({
                "file": {"file_id": "f-1", "filename": "x.mp4"},
                "base_resp": {"status_code": 0},
            }),
        ),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollMinimaxVideoAdapter(tenant_config).generate(req)
    assert "download_url" in str(exc.value)


@pytest.mark.asyncio
async def test_retrieve_empty_download_url_raises_provider_error(monkeypatch, tenant_config, req):
    """Retrieve returned an EMPTY string download_url → MaicProviderError."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({"task_id": "t", "base_resp": {"status_code": 0}}),
        ),
        poll_resps=[
            _FakeResp(
                status=200,
                body=json.dumps({
                    "task_id": "t", "status": "Success", "file_id": "f-1",
                    "base_resp": {"status_code": 0},
                }),
            ),
        ],
        retrieve_resp=_FakeResp(
            status=200,
            body=json.dumps({
                "file": {"file_id": "f-1", "download_url": ""},
                "base_resp": {"status_code": 0},
            }),
        ),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError):
        await _FastPollMinimaxVideoAdapter(tenant_config).generate(req)


# ── File download (Step 4) ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_file_download_404_raises_provider_error(monkeypatch, tenant_config, req):
    """The signed CDN URL came back 404 (TTL expired between retrieve
    and download) → MaicProviderError."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({"task_id": "t", "base_resp": {"status_code": 0}}),
        ),
        poll_resps=[
            _FakeResp(
                status=200,
                body=json.dumps({
                    "task_id": "t", "status": "Success", "file_id": "f-1",
                    "base_resp": {"status_code": 0},
                }),
            ),
        ],
        bytes_resp=_FakeResp(status=404, body="not found"),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollMinimaxVideoAdapter(tenant_config).generate(req)
    assert "fetch" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_file_download_zero_bytes_raises_provider_error(monkeypatch, tenant_config, req):
    """Bytes GET 200 but empty body → MaicProviderError."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({"task_id": "t", "base_resp": {"status_code": 0}}),
        ),
        poll_resps=[
            _FakeResp(
                status=200,
                body=json.dumps({
                    "task_id": "t", "status": "Success", "file_id": "f-1",
                    "base_resp": {"status_code": 0},
                }),
            ),
        ],
        bytes_resp=_FakeResp(
            status=200, body=b"", headers={"Content-Type": "video/mp4"},
        ),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollMinimaxVideoAdapter(tenant_config).generate(req)
    assert "zero bytes" in str(exc.value).lower()


# ── Response-shape errors ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_submit_malformed_json_raises_provider_error(monkeypatch, tenant_config, req):
    """Submit 200 with non-JSON body → MaicProviderError."""
    session = _FakeSession(post_resp=_FakeResp(status=200, body="not-json{{{"))
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollMinimaxVideoAdapter(tenant_config).generate(req)
    assert "malformed" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_submit_missing_task_id_raises_provider_error(monkeypatch, tenant_config, req):
    """Submit returned JSON but no task_id field → MaicProviderError."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({"base_resp": {"status_code": 0}}),
        ),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollMinimaxVideoAdapter(tenant_config).generate(req)
    assert "task_id" in str(exc.value)


@pytest.mark.asyncio
async def test_poll_missing_status_raises_provider_error(monkeypatch, tenant_config, req):
    """Poll response missing 'status' field → MaicProviderError."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({"task_id": "t", "base_resp": {"status_code": 0}}),
        ),
        poll_resps=[
            _FakeResp(
                status=200,
                body=json.dumps({"task_id": "t", "base_resp": {"status_code": 0}}),
            ),
        ],
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollMinimaxVideoAdapter(tenant_config).generate(req)
    assert "status" in str(exc.value).lower()


# ── Auth / env-var fallback / SSRF / config ──────────────────────────


@pytest.mark.asyncio
async def test_missing_api_key_with_env_fallback_disabled_raises_config_error(monkeypatch, req):
    """Empty tenant key + allow_env_key_fallback=False → MaicConfigError
    BEFORE any HTTP call. Even if MINIMAX_API_KEY is set on the host,
    we must NOT read it."""
    monkeypatch.setenv("MINIMAX_API_KEY", "env-key-do-not-use")
    cfg = SimpleNamespace(
        get_video_api_key=lambda: "",
        video_base_url="",
        video_model="MiniMax-Hailuo-2.3",
        allow_env_key_fallback=False,
    )
    _install_fake_aiohttp(monkeypatch)
    with pytest.raises(MaicConfigError) as exc:
        await _FastPollMinimaxVideoAdapter(cfg).generate(req)
    assert "api_key required" in str(exc.value)


@pytest.mark.asyncio
async def test_env_key_fallback_when_tenant_key_empty(monkeypatch, req):
    """Empty tenant key + MINIMAX_API_KEY set + no opt-out → env var
    used as the Authorization header. Phase 5 TTS pattern reused."""
    monkeypatch.setenv("MINIMAX_API_KEY", "env-fallback-video-key")
    cfg = SimpleNamespace(
        get_video_api_key=lambda: "",
        video_base_url="",
        video_model="MiniMax-Hailuo-2.3",
    )
    session = _install_fake_aiohttp(monkeypatch)
    result = await _FastPollMinimaxVideoAdapter(cfg).generate(req)
    assert result.provider == "minimax_video"
    assert session.last_post_headers["Authorization"] == "Bearer env-fallback-video-key"


@pytest.mark.asyncio
async def test_tenant_key_preferred_over_env_key(monkeypatch, req):
    """When both are set, the tenant key wins."""
    monkeypatch.setenv("MINIMAX_API_KEY", "env-key-DO-NOT-USE")
    cfg = SimpleNamespace(
        get_video_api_key=lambda: "tenant-explicit-key",
        video_base_url="",
        video_model="MiniMax-Hailuo-2.3",
    )
    session = _install_fake_aiohttp(monkeypatch)
    await _FastPollMinimaxVideoAdapter(cfg).generate(req)
    assert session.last_post_headers["Authorization"] == "Bearer tenant-explicit-key"


@pytest.mark.asyncio
async def test_completely_missing_api_key_raises_config_error(monkeypatch, req):
    """No tenant key AND no env var → MaicConfigError, no HTTP call."""
    cfg = SimpleNamespace(
        get_video_api_key=lambda: "",
        video_base_url="",
        video_model="MiniMax-Hailuo-2.3",
    )
    _install_fake_aiohttp(monkeypatch)
    with pytest.raises(MaicConfigError) as exc:
        await _FastPollMinimaxVideoAdapter(cfg).generate(req)
    assert "api_key required" in str(exc.value)


@pytest.mark.asyncio
async def test_custom_base_url_goes_through_ssrf_guard(monkeypatch, req):
    """Custom base_url pointing at a private address must be rejected
    by the SSRF guard with MaicConfigError. Critical for the video
    adapter — it talks to three HTTP endpoints, all derived from this
    base URL."""
    cfg = SimpleNamespace(
        get_video_api_key=lambda: "mm-x",
        video_base_url="http://127.0.0.1:8080/v1",
        video_model="MiniMax-Hailuo-2.3",
    )
    _install_fake_aiohttp(monkeypatch)
    with pytest.raises(MaicConfigError) as exc:
        await _FastPollMinimaxVideoAdapter(cfg).generate(req)
    assert "ssrf" in str(exc.value).lower() or "base_url" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_default_base_url_skips_ssrf_check(monkeypatch, tenant_config, req):
    """Empty video_base_url uses the default Minimax endpoint without
    invoking the SSRF guard."""
    _install_fake_aiohttp(monkeypatch)
    result = await _FastPollMinimaxVideoAdapter(tenant_config).generate(req)
    assert result.provider == "minimax_video"


@pytest.mark.asyncio
async def test_custom_public_base_url_accepted(monkeypatch, req):
    """Public regional endpoints (api.minimax.chat for CN tenants, etc.)
    must pass the SSRF guard. We patch the guard to accept without doing
    real DNS so the code path is exercised."""
    cfg = SimpleNamespace(
        get_video_api_key=lambda: "mm-cn",
        video_base_url="https://api.minimax.chat/v1",
        video_model="MiniMax-Hailuo-2.3",
    )
    import apps.maic.media.adapters.minimax_video as adapter_mod
    monkeypatch.setattr(adapter_mod, "validate_webhook_host", lambda url: None)
    session = _install_fake_aiohttp(monkeypatch)

    await _FastPollMinimaxVideoAdapter(cfg).generate(req)
    assert session.last_post_url == "https://api.minimax.chat/v1/video_generation"


@pytest.mark.asyncio
async def test_default_model_when_tenant_model_empty(monkeypatch, req):
    """Empty tenant video_model falls back to the adapter default."""
    cfg = SimpleNamespace(
        get_video_api_key=lambda: "k",
        video_base_url="",
        video_model="",
    )
    session = _install_fake_aiohttp(monkeypatch)
    result = await _FastPollMinimaxVideoAdapter(cfg).generate(req)
    assert result.model == "MiniMax-Hailuo-2.3"
    assert (session.last_post_json or {})["model"] == "MiniMax-Hailuo-2.3"


# ── Bounded error message truncation ──────────────────────────────────


@pytest.mark.asyncio
async def test_long_error_body_truncated_to_bound(monkeypatch, tenant_config, req):
    """Adversarial 1MB error body → at most ~300 chars in the exception
    message (200 char snippet + prefix overhead)."""
    long_body = "X" * 10_000
    session = _FakeSession(post_resp=_FakeResp(status=500, body=long_body))
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollMinimaxVideoAdapter(tenant_config).generate(req)
    assert len(str(exc.value)) <= 320


@pytest.mark.asyncio
async def test_long_base_resp_msg_truncated(monkeypatch, tenant_config, req):
    """Adversarial base_resp.status_msg must also be bounded."""
    long_msg = "Y" * 10_000
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({
                "base_resp": {"status_code": 9999, "status_msg": long_msg},
            }),
        ),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollMinimaxVideoAdapter(tenant_config).generate(req)
    assert len(str(exc.value)) <= 320


# ── Cost estimator ────────────────────────────────────────────────────


def test_cost_estimator_returns_none_for_all_inputs():
    """No public pricing table — always None. Telemetry is non-blocking."""
    assert MinimaxVideoAdapter._estimate_cost("MiniMax-Hailuo-2.3", 6, {}) is None
    assert MinimaxVideoAdapter._estimate_cost(
        "MiniMax-Hailuo-2.3", 10, {"video_width": 1920, "video_height": 1080},
    ) is None


# ── Registry registration ─────────────────────────────────────────────


def test_adapter_is_registered_on_import():
    """Importing the adapter module registered it under (video, minimax_video)."""
    from apps.maic.media.providers import _REGISTRY
    assert ("video", "minimax_video") in _REGISTRY
    assert _REGISTRY[("video", "minimax_video")] is MinimaxVideoAdapter


def test_default_timeout_matches_brief():
    """Brief mandates 360s default timeout for video — significantly
    higher than image because Hailuo typically runs 30-180s."""
    assert MinimaxVideoAdapter.default_timeout_seconds == 360


def test_poll_intervals_match_brief():
    """Brief mandates 5s poll interval and 300s poll deadline."""
    assert MinimaxVideoAdapter._poll_interval_seconds == 5.0
    assert MinimaxVideoAdapter._poll_timeout_seconds == 300.0


def test_three_step_methods_exist():
    """The 3-step flow must be exposed as separate methods so subclasses
    can override one leg without rewriting the whole flow."""
    import inspect
    for name in ("_submit_task", "_poll_task_until_done", "_retrieve_file_url"):
        assert hasattr(MinimaxVideoAdapter, name), f"missing method: {name}"
        assert inspect.iscoroutinefunction(getattr(MinimaxVideoAdapter, name))


# ── Live smoke (gated) ────────────────────────────────────────────────


@pytest.mark.skipif(
    os.environ.get("MAIC_MINIMAX_VIDEO_LIVE_SMOKE") != "1"
    or not os.environ.get("MINIMAX_API_KEY"),
    reason=(
        "live Minimax video smoke disabled — set "
        "MAIC_MINIMAX_VIDEO_LIVE_SMOKE=1 and MINIMAX_API_KEY=<real-key> "
        "to enable. Video generation costs significantly more than image; "
        "consult the Minimax dashboard. Phase 5 Minimax TTS uses the same "
        "key — reuse intentionally."
    ),
)
@pytest.mark.asyncio
async def test_live_smoke_real_minimax_video_call(tmp_path, settings):
    """Hits the real Minimax Video API end-to-end. Skipped unless env
    vars set.

    Asserts:
      - Real submit + poll + retrieve + bytes-fetch round-trip succeeds
      - Generated video is uploaded to local storage
      - File on disk is non-zero and has the MP4 ftyp signature
        (bytes 4-7 == 'ftyp' for a standard MP4 container)
    """
    settings.MEDIA_ROOT = str(tmp_path)
    cfg = SimpleNamespace(
        get_video_api_key=lambda: os.environ["MINIMAX_API_KEY"],
        video_base_url="",
        video_model="MiniMax-Hailuo-2.3",
    )
    smoke_req = VideoGenerationRequest(
        prompt="a triangle slowly rotating on a white background",
        tenant_id="live-smoke",
        scene_id="live-smoke-scene",
        duration_seconds=6,
    )
    result = await MinimaxVideoAdapter(cfg).generate(smoke_req)
    assert result.provider == "minimax_video"
    assert "maic/live-smoke/video/" in result.url
    from django.core.files.storage import default_storage
    storage_key = result.url.split("/media/", 1)[1] if "/media/" in result.url else None
    if storage_key:
        with default_storage.open(storage_key, "rb") as fh:
            header = fh.read(12)
        # ISO Base Media File Format (MP4) signature: 4 bytes box size,
        # then 'ftyp' at offset 4.
        assert header[4:8] == b"ftyp"
