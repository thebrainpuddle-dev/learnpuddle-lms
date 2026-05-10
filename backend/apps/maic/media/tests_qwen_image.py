"""Tests for the Qwen (Alibaba DashScope) image adapter (MAIC-904).

The first async-polling adapter — also the test template Veo / Kling /
Minimax-video tests will copy. The fake aiohttp infrastructure here
extends the OpenAI/Grok/Minimax fakes to model a SEQUENCE of GET
responses (so we can drive the polling state machine through
PENDING → RUNNING → SUCCEEDED).

Discipline:
  - IO-boundary fake only: ``aiohttp`` is injected into ``sys.modules``
    via monkeypatch.setitem — mirrors the golden pattern in
    tests_openai_image.py.
  - No mocks of QwenImageAdapter itself. Real adapter, real Pydantic,
    real storage (Django default_storage / FileSystemStorage in tests).
  - Polling cadence is shortened to nearly-zero in tests by overriding
    ``_poll_interval_seconds`` (and where needed, ``_poll_timeout_seconds``)
    via subclass — keeps the test suite fast while exercising the real
    asyncio.sleep path. We deliberately do NOT monkeypatch asyncio.sleep
    because the deadline math is what we want to verify.
  - Live smoke gated on MAIC_QWEN_LIVE_SMOKE=1 AND DASHSCOPE_API_KEY env
    vars — skipped (not failed) when either is missing. DASHSCOPE_API_KEY
    is the canonical Alibaba env var name; we accept QWEN_API_KEY as an
    alias for operators who prefer the brand name.

Test layout:
  - Fake aiohttp infrastructure with poll-sequence support
  - Happy path + request-shape contract checks
  - Polling state-machine tests (PENDING→RUNNING→SUCCEEDED, FAILED,
    CANCELED, UNKNOWN, deadline exhaustion)
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
from apps.maic.media.adapters.qwen_image import QwenImageAdapter
from apps.maic.media.types import ImageGenerationRequest


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

    Extends the OpenAI/Grok/Minimax fake to support a SEQUENCE of GET
    responses. Three GET call sites in the qwen adapter:
        1. polling — N successive calls to /tasks/<id> until terminal
        2. image bytes fetch — one call to the OSS URL

    The constructor accepts:
        post_resp: single response for the submit POST
        poll_resps: list of responses to return for each /tasks/<id> GET
            (consumed in order — index advances on each call)
        bytes_resp: response for the final bytes GET

    The fake detects which GET is which by URL pattern: /tasks/ → poll;
    anything else → bytes_resp. This keeps the test code declarative
    (you list out poll states in order; the bytes fetch is independent).
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
            body=b"PNG-bytes-fake",
            headers={"Content-Type": "image/png"},
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
        if "/tasks/" in url:
            # Polling call — consume from the queue. Past-the-end means
            # the test under-provisioned poll responses; we fail loud
            # rather than silently looping or returning a stale response.
            if self.poll_index >= len(self._poll_resps):
                raise AssertionError(
                    f"_FakeSession: polling GET #{self.poll_index + 1} but "
                    f"only {len(self._poll_resps)} poll responses provided. "
                    "Add more poll_resps or shorten the test."
                )
            resp = self._poll_resps[self.poll_index]
            self.poll_index += 1
            return resp
        # Non-/tasks/ GET — must be the final image-bytes fetch.
        return self._bytes_resp


class _FakeClientError(Exception):
    """Stand-in for aiohttp.ClientError."""


def _install_fake_aiohttp(monkeypatch, session: _FakeSession | None = None) -> _FakeSession:
    """Inject a fake aiohttp module. Returns the session so tests can
    assert on captured request shape."""
    if session is None:
        # Default: happy path — submit returns task_id, one poll returns
        # SUCCEEDED, bytes fetch returns PNG.
        session = _FakeSession(
            post_resp=_FakeResp(
                status=200,
                body=json.dumps({
                    "output": {"task_id": "task-abc-123", "task_status": "PENDING"},
                    "request_id": "req-1",
                }),
            ),
            poll_resps=[
                _FakeResp(
                    status=200,
                    body=json.dumps({
                        "output": {
                            "task_id": "task-abc-123",
                            "task_status": "SUCCEEDED",
                            "results": [{"url": "https://dashscope-cdn.example/img-1.png"}],
                        },
                        "request_id": "req-2",
                    }),
                ),
            ],
            bytes_resp=_FakeResp(
                status=200,
                body=b"PNG-bytes-fake",
                headers={"Content-Type": "image/png"},
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


class _FastPollQwenAdapter(QwenImageAdapter):
    """Subclass that polls every ~0s so tests don't wait 2s/iteration.

    We still want a non-zero deadline so the timeout-exhaustion test
    can hit it; 1.5s gives us ~150 iterations of headroom, which is
    plenty for any happy-path test."""

    _poll_interval_seconds = 0.001
    _poll_timeout_seconds = 1.5


# ── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture
def tenant_config():
    """Minimal TenantAIConfig-shaped object."""
    return SimpleNamespace(
        get_image_api_key=lambda: "sk-test-dashscope-key",
        image_base_url="",
        image_model="wanx-v1",
    )


@pytest.fixture
def req():
    return ImageGenerationRequest(
        prompt="a colourful diagram of fractions",
        tenant_id="t-1",
        scene_id="scene-abc",
    )


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, settings):
    """Point MEDIA_ROOT at tmp to keep the test tree clean + isolated."""
    settings.MEDIA_ROOT = str(tmp_path)


# ── Happy path ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_happy_path_returns_result_with_storage_url(monkeypatch, tenant_config, req):
    """Submit → poll-once-SUCCEEDED → fetch bytes → storage. URL points
    to OUR storage, not Alibaba's CDN."""
    session = _install_fake_aiohttp(monkeypatch)

    adapter = _FastPollQwenAdapter(tenant_config)
    result = await adapter.generate(req)

    assert result.provider == "qwen"
    assert result.model == "wanx-v1"
    assert "dashscope-cdn.example" not in result.url
    assert "maic/t-1/image/" in result.url
    assert "scene-abc__" in result.url
    # No pricing table for DashScope — cost is None.
    assert result.cost_usd_estimate is None
    # Confirm we actually issued the bytes GET to the DashScope CDN.
    assert any("dashscope-cdn.example" in u for u in session.last_get_urls)


@pytest.mark.asyncio
async def test_submit_request_shape_matches_dashscope_contract(monkeypatch, tenant_config, req):
    """The submit body must use DashScope's {model, input, parameters}
    shape with size as 'WxH' using '*' (not 'x'), AND must include the
    X-DashScope-Async: enable header."""
    session = _install_fake_aiohttp(monkeypatch)

    await _FastPollQwenAdapter(tenant_config).generate(req)

    assert session.last_post_url == (
        "https://dashscope.aliyuncs.com/api/v1"
        "/services/aigc/text2image/image-synthesis"
    )
    headers = session.last_post_headers or {}
    assert headers.get("Authorization") == "Bearer sk-test-dashscope-key"
    assert headers.get("X-DashScope-Async") == "enable"
    body = session.last_post_json or {}
    assert body["model"] == "wanx-v1"
    assert body["input"]["prompt"] == "a colourful diagram of fractions"
    # DashScope uses '*' as the size separator — bug-bait for anyone
    # copy-pasting from the OpenAI shape ('x').
    assert body["parameters"]["size"] == "1024*1024"
    assert body["parameters"]["n"] == 1


@pytest.mark.asyncio
async def test_poll_endpoint_url_uses_task_id(monkeypatch, tenant_config, req):
    """The poll GET must target /tasks/<task_id> with the auth header
    but WITHOUT the async-enable header."""
    session = _install_fake_aiohttp(monkeypatch)
    await _FastPollQwenAdapter(tenant_config).generate(req)

    # First GET is the poll; second is the bytes fetch.
    assert session.last_get_urls[0] == (
        "https://dashscope.aliyuncs.com/api/v1/tasks/task-abc-123"
    )
    poll_headers = session.last_get_headers[0] or {}
    assert poll_headers.get("Authorization") == "Bearer sk-test-dashscope-key"
    # X-DashScope-Async must NOT be on the poll request (DashScope rejects
    # the poll endpoint when this header is present on some regional gateways).
    assert "X-DashScope-Async" not in poll_headers


# ── Polling state-machine ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_polling_succeeds_on_third_attempt(monkeypatch, tenant_config, req):
    """PENDING → RUNNING → SUCCEEDED proves we do NOT just take the first
    poll response. The poll counter MUST advance through all three.
    """
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({
                "output": {"task_id": "task-slow", "task_status": "PENDING"},
            }),
        ),
        poll_resps=[
            _FakeResp(
                status=200,
                body=json.dumps({
                    "output": {"task_id": "task-slow", "task_status": "PENDING"},
                }),
            ),
            _FakeResp(
                status=200,
                body=json.dumps({
                    "output": {"task_id": "task-slow", "task_status": "RUNNING"},
                }),
            ),
            _FakeResp(
                status=200,
                body=json.dumps({
                    "output": {
                        "task_id": "task-slow",
                        "task_status": "SUCCEEDED",
                        "results": [{"url": "https://dashscope-cdn.example/done.png"}],
                    },
                }),
            ),
        ],
    )
    _install_fake_aiohttp(monkeypatch, session)

    result = await _FastPollQwenAdapter(tenant_config).generate(req)

    assert result.provider == "qwen"
    # All three poll responses consumed
    assert session.poll_index == 3


@pytest.mark.asyncio
async def test_polling_failed_status_raises_provider_error(monkeypatch, tenant_config, req):
    """task_status == FAILED → MaicProviderError. Operator may retry the
    whole submit (idempotent) but this single attempt is over."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({"output": {"task_id": "task-fail", "task_status": "PENDING"}}),
        ),
        poll_resps=[
            _FakeResp(
                status=200,
                body=json.dumps({
                    "output": {
                        "task_id": "task-fail",
                        "task_status": "FAILED",
                        "code": "InvalidParameter.PromptTooLong",
                        "message": "prompt exceeds the model's context window",
                    },
                }),
            ),
        ],
    )
    _install_fake_aiohttp(monkeypatch, session)

    with pytest.raises(MaicProviderError) as exc:
        await _FastPollQwenAdapter(tenant_config).generate(req)
    msg = str(exc.value)
    assert "FAILED" in msg
    # The upstream code+message must propagate so operators reading the
    # failure ticket know whether this is a content-policy block, quota
    # issue, or model crash.
    assert "InvalidParameter.PromptTooLong" in msg


@pytest.mark.asyncio
async def test_polling_canceled_status_raises_provider_error(monkeypatch, tenant_config, req):
    """task_status == CANCELED → MaicProviderError. Tasks can be canceled
    server-side under load shedding."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({"output": {"task_id": "task-cnl", "task_status": "PENDING"}}),
        ),
        poll_resps=[
            _FakeResp(
                status=200,
                body=json.dumps({
                    "output": {"task_id": "task-cnl", "task_status": "CANCELED"},
                }),
            ),
        ],
    )
    _install_fake_aiohttp(monkeypatch, session)

    with pytest.raises(MaicProviderError) as exc:
        await _FastPollQwenAdapter(tenant_config).generate(req)
    assert "CANCELED" in str(exc.value)


@pytest.mark.asyncio
async def test_polling_unknown_status_raises_provider_error(monkeypatch, tenant_config, req):
    """task_status == UNKNOWN → MaicProviderError. DashScope emits this
    when the upstream model worker crashes after the task was queued."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({"output": {"task_id": "task-unk", "task_status": "PENDING"}}),
        ),
        poll_resps=[
            _FakeResp(
                status=200,
                body=json.dumps({
                    "output": {"task_id": "task-unk", "task_status": "UNKNOWN"},
                }),
            ),
        ],
    )
    _install_fake_aiohttp(monkeypatch, session)

    with pytest.raises(MaicProviderError) as exc:
        await _FastPollQwenAdapter(tenant_config).generate(req)
    assert "UNKNOWN" in str(exc.value)


@pytest.mark.asyncio
async def test_polling_unrecognised_status_raises_provider_error(monkeypatch, tenant_config, req):
    """If DashScope adds a brand-new task_status string, the adapter
    must fail loud rather than spin. Better to surface the contract
    change to the operator than silently loop forever."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({"output": {"task_id": "task-new", "task_status": "PENDING"}}),
        ),
        poll_resps=[
            _FakeResp(
                status=200,
                body=json.dumps({
                    "output": {"task_id": "task-new", "task_status": "QUANTUM_SUPERPOSITION"},
                }),
            ),
        ],
    )
    _install_fake_aiohttp(monkeypatch, session)

    with pytest.raises(MaicProviderError) as exc:
        await _FastPollQwenAdapter(tenant_config).generate(req)
    assert "QUANTUM_SUPERPOSITION" in str(exc.value)
    assert "unrecognised" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_polling_times_out_when_deadline_exhausted(monkeypatch, tenant_config, req):
    """If the task never reaches a terminal status before the deadline,
    raise MaicProviderError. The deadline is a HARD ceiling — bounded
    by self._poll_timeout_seconds; no `while True`.

    We provision way more PENDING responses than the deadline allows
    iterations — the deadline must trip before the queue empties."""

    class _TinyDeadlineAdapter(QwenImageAdapter):
        # Polling cadence: 50ms wait, 150ms deadline → ~3 iterations max,
        # then the deadline trips. Real-world timeouts are 100s; here we
        # compress to keep the test fast while still exercising the real
        # asyncio.sleep + clock-check code path.
        _poll_interval_seconds = 0.05
        _poll_timeout_seconds = 0.15

    # 500 PENDING responses — way more than the deadline allows.
    pending_resp = _FakeResp(
        status=200,
        body=json.dumps({"output": {"task_id": "task-slow", "task_status": "PENDING"}}),
    )
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({"output": {"task_id": "task-slow", "task_status": "PENDING"}}),
        ),
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
        post_resp=_FakeResp(status=401, body='{"code":"InvalidApiKey","message":"key revoked"}'),
    )
    _install_fake_aiohttp(monkeypatch, session)

    with pytest.raises(MaicConfigError) as exc:
        await _FastPollQwenAdapter(tenant_config).generate(req)
    assert "auth" in str(exc.value).lower()
    assert "401" in str(exc.value)
    assert "submit" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_submit_403_raises_config_error(monkeypatch, tenant_config, req):
    """Submit 403 → MaicConfigError. Same category as 401."""
    session = _FakeSession(
        post_resp=_FakeResp(status=403, body="forbidden"),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicConfigError):
        await _FastPollQwenAdapter(tenant_config).generate(req)


@pytest.mark.asyncio
async def test_submit_429_raises_provider_error(monkeypatch, tenant_config, req):
    """Submit 429 → MaicProviderError (orchestrator may retry)."""
    session = _FakeSession(
        post_resp=_FakeResp(status=429, body='{"code":"Throttling"}'),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollQwenAdapter(tenant_config).generate(req)
    assert "429" in str(exc.value)


@pytest.mark.asyncio
async def test_submit_500_raises_provider_error(monkeypatch, tenant_config, req):
    """Submit 5xx → MaicProviderError."""
    session = _FakeSession(
        post_resp=_FakeResp(status=503, body="upstream unavailable"),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollQwenAdapter(tenant_config).generate(req)
    assert "503" in str(exc.value)


@pytest.mark.asyncio
async def test_submit_other_4xx_raises_provider_error(monkeypatch, tenant_config, req):
    """Submit 4xx (not 401/403/429) → MaicProviderError."""
    session = _FakeSession(
        post_resp=_FakeResp(status=400, body='{"code":"InvalidParameter"}'),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollQwenAdapter(tenant_config).generate(req)
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
        await _FastPollQwenAdapter(tenant_config).generate(req)
    assert "network error" in str(exc.value).lower()


# ── HTTP error matrix on POLL ────────────────────────────────────────


@pytest.mark.asyncio
async def test_poll_401_raises_config_error(monkeypatch, tenant_config, req):
    """Poll 401 → MaicConfigError. Exceedingly rare (auth rotated
    mid-task) but possible — and we want loud failure when it happens."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({"output": {"task_id": "t", "task_status": "PENDING"}}),
        ),
        poll_resps=[_FakeResp(status=401, body="auth expired")],
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicConfigError) as exc:
        await _FastPollQwenAdapter(tenant_config).generate(req)
    assert "poll" in str(exc.value).lower()
    assert "401" in str(exc.value)


@pytest.mark.asyncio
async def test_poll_429_raises_provider_error(monkeypatch, tenant_config, req):
    """Poll 429 → MaicProviderError (orchestrator may retry)."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({"output": {"task_id": "t", "task_status": "PENDING"}}),
        ),
        poll_resps=[_FakeResp(status=429, body="throttled")],
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollQwenAdapter(tenant_config).generate(req)
    assert "429" in str(exc.value)
    assert "poll" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_poll_5xx_raises_provider_error(monkeypatch, tenant_config, req):
    """Poll 5xx → MaicProviderError."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({"output": {"task_id": "t", "task_status": "PENDING"}}),
        ),
        poll_resps=[_FakeResp(status=502, body="bad gateway")],
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollQwenAdapter(tenant_config).generate(req)
    assert "502" in str(exc.value)


# ── Response-shape errors ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_submit_malformed_json_raises_provider_error(monkeypatch, tenant_config, req):
    """Submit 200 with non-JSON body → MaicProviderError."""
    session = _FakeSession(post_resp=_FakeResp(status=200, body="not-json{{{"))
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollQwenAdapter(tenant_config).generate(req)
    assert "malformed" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_submit_missing_task_id_raises_provider_error(monkeypatch, tenant_config, req):
    """Submit returned JSON but no output.task_id → MaicProviderError."""
    session = _FakeSession(
        post_resp=_FakeResp(status=200, body=json.dumps({"output": {}})),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollQwenAdapter(tenant_config).generate(req)
    assert "task_id" in str(exc.value)


@pytest.mark.asyncio
async def test_poll_missing_task_status_raises_provider_error(monkeypatch, tenant_config, req):
    """Poll response missing output.task_status → MaicProviderError."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({"output": {"task_id": "t", "task_status": "PENDING"}}),
        ),
        poll_resps=[_FakeResp(status=200, body=json.dumps({"output": {}}))],
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollQwenAdapter(tenant_config).generate(req)
    assert "task_status" in str(exc.value)


@pytest.mark.asyncio
async def test_succeeded_with_empty_url_raises_provider_error(monkeypatch, tenant_config, req):
    """SUCCEEDED but results[0].url is empty → MaicProviderError."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({"output": {"task_id": "t", "task_status": "PENDING"}}),
        ),
        poll_resps=[_FakeResp(
            status=200,
            body=json.dumps({
                "output": {
                    "task_id": "t",
                    "task_status": "SUCCEEDED",
                    "results": [{"url": ""}],
                },
            }),
        )],
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError):
        await _FastPollQwenAdapter(tenant_config).generate(req)


@pytest.mark.asyncio
async def test_succeeded_with_per_image_error_raises_provider_error(monkeypatch, tenant_config, req):
    """SUCCEEDED at task level but results[0] is a per-image error
    ({code, message} instead of {url}) → MaicProviderError. DashScope
    occasionally returns these for content-policy-triggered partial
    failures."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({"output": {"task_id": "t", "task_status": "PENDING"}}),
        ),
        poll_resps=[_FakeResp(
            status=200,
            body=json.dumps({
                "output": {
                    "task_id": "t",
                    "task_status": "SUCCEEDED",
                    "results": [{
                        "code": "DataInspectionFailed",
                        "message": "input flagged by content moderation",
                    }],
                },
            }),
        )],
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollQwenAdapter(tenant_config).generate(req)
    assert "DataInspectionFailed" in str(exc.value)


@pytest.mark.asyncio
async def test_image_fetch_404_raises_provider_error(monkeypatch, tenant_config, req):
    """SUCCEEDED, URL returned, but bytes GET returns 404 → MaicProviderError.
    Happens when the OSS signed URL expired between submit and fetch
    (24h gap on a stuck queue)."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({"output": {"task_id": "t", "task_status": "PENDING"}}),
        ),
        poll_resps=[_FakeResp(
            status=200,
            body=json.dumps({
                "output": {
                    "task_id": "t",
                    "task_status": "SUCCEEDED",
                    "results": [{"url": "https://dashscope-cdn.example/expired.png"}],
                },
            }),
        )],
        bytes_resp=_FakeResp(status=404, body="not found"),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollQwenAdapter(tenant_config).generate(req)
    assert "fetch" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_image_fetch_zero_bytes_raises_provider_error(monkeypatch, tenant_config, req):
    """Bytes GET returns 200 but empty body → MaicProviderError."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({"output": {"task_id": "t", "task_status": "PENDING"}}),
        ),
        poll_resps=[_FakeResp(
            status=200,
            body=json.dumps({
                "output": {
                    "task_id": "t",
                    "task_status": "SUCCEEDED",
                    "results": [{"url": "https://dashscope-cdn.example/zero.png"}],
                },
            }),
        )],
        bytes_resp=_FakeResp(status=200, body=b"", headers={"Content-Type": "image/png"}),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _FastPollQwenAdapter(tenant_config).generate(req)
    assert "zero bytes" in str(exc.value).lower()


# ── Auth / SSRF / config errors ──────────────────────────────────────


@pytest.mark.asyncio
async def test_missing_api_key_raises_config_error(monkeypatch, req):
    """No api_key → MaicConfigError BEFORE any HTTP. Note: unlike the
    minimax adapter, qwen does NOT fall back to an env var — explicit
    per-tenant keying only."""
    cfg = SimpleNamespace(
        get_image_api_key=lambda: "",
        image_base_url="",
        image_model="wanx-v1",
    )
    _install_fake_aiohttp(monkeypatch)
    with pytest.raises(MaicConfigError) as exc:
        await _FastPollQwenAdapter(cfg).generate(req)
    assert "api_key required" in str(exc.value)


@pytest.mark.asyncio
async def test_custom_base_url_goes_through_ssrf_guard(monkeypatch, req):
    """Tenant-supplied base URL pointing at localhost must be rejected
    by the SSRF guard. Proves we don't blindly trust tenant input."""
    cfg = SimpleNamespace(
        get_image_api_key=lambda: "sk-x",
        image_base_url="http://127.0.0.1:8080/api/v1",
        image_model="wanx-v1",
    )
    _install_fake_aiohttp(monkeypatch)
    with pytest.raises(MaicConfigError) as exc:
        await _FastPollQwenAdapter(cfg).generate(req)
    assert "ssrf" in str(exc.value).lower() or "base_url" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_default_base_url_skips_ssrf_check(monkeypatch, tenant_config, req):
    """Empty image_base_url uses the default DashScope endpoint without
    invoking the SSRF guard (no DNS resolution of a known endpoint).
    Tested by happy-path completing — if the guard ran on the default,
    it would try to DNS-resolve dashscope.aliyuncs.com under monkey-patched
    aiohttp, which is exactly what we want to avoid."""
    _install_fake_aiohttp(monkeypatch)
    result = await _FastPollQwenAdapter(tenant_config).generate(req)
    assert result.provider == "qwen"


# ── Cost estimator (pure unit, no IO) ─────────────────────────────────


def test_cost_estimator_returns_none_for_all_models():
    """No public pricing table for DashScope models — always None.
    Telemetry is non-blocking; operators get spend numbers from the
    DashScope console."""
    assert QwenImageAdapter._estimate_cost("wanx-v1", 1024, 1024, "standard") is None
    assert QwenImageAdapter._estimate_cost("wan2.2-t2i-flash", 1280, 720, "high") is None
    assert QwenImageAdapter._estimate_cost("unknown-model", 512, 512, "standard") is None


# ── Registry registration ─────────────────────────────────────────────


def test_adapter_is_registered_on_import():
    """Importing the adapter module registered it under (image, qwen)."""
    from apps.maic.media.providers import _REGISTRY
    assert ("image", "qwen") in _REGISTRY
    assert _REGISTRY[("image", "qwen")] is QwenImageAdapter


def test_default_timeout_is_higher_than_sync_adapters():
    """Async polling needs more headroom than sync providers — the brief
    requires 120s here. Regression-guard so a future refactor doesn't
    accidentally drop it back to 60s."""
    assert QwenImageAdapter.default_timeout_seconds == 120


def test_poll_helper_is_a_method_not_module_function():
    """The polling helper must live on the adapter so video subclasses
    can override the cadence without re-implementing. Regression-guard
    against someone refactoring it to a module-level function during a
    DRY pass."""
    assert hasattr(QwenImageAdapter, "_poll_task_until_done")
    assert callable(QwenImageAdapter._poll_task_until_done)
    # And it must be coroutine-defining:
    import inspect
    assert inspect.iscoroutinefunction(QwenImageAdapter._poll_task_until_done)


# ── Live smoke (gated) ────────────────────────────────────────────────


def _resolve_live_smoke_key() -> str | None:
    """Accept either DASHSCOPE_API_KEY (canonical Alibaba var) or
    QWEN_API_KEY (brand alias some operators prefer)."""
    return os.environ.get("DASHSCOPE_API_KEY") or os.environ.get("QWEN_API_KEY")


@pytest.mark.skipif(
    os.environ.get("MAIC_QWEN_LIVE_SMOKE") != "1"
    or not _resolve_live_smoke_key(),
    reason=(
        "live Qwen smoke disabled — set MAIC_QWEN_LIVE_SMOKE=1 and "
        "DASHSCOPE_API_KEY=<real-key> (or QWEN_API_KEY) to enable. "
        "wanx-v1 has a free tier on new DashScope accounts; cost on "
        "paid tiers varies by region — consult the DashScope console."
    ),
)
@pytest.mark.asyncio
async def test_live_smoke_real_dashscope_call(tmp_path, settings):
    """Hits the real DashScope API end-to-end. Skipped unless env vars set.

    Asserts:
      - Real submit + poll + bytes-fetch round-trip succeeds
      - Generated image is uploaded to local storage
      - File on disk is non-zero and starts with a known image signature
    """
    settings.MEDIA_ROOT = str(tmp_path)
    api_key = _resolve_live_smoke_key()
    assert api_key, "guarded above"
    cfg = SimpleNamespace(
        get_image_api_key=lambda: api_key,
        image_base_url="",
        image_model="wanx-v1",
    )
    req = ImageGenerationRequest(
        prompt="a simple line drawing of a triangle and a circle, minimalist",
        tenant_id="live-smoke",
        scene_id="live-smoke-scene",
    )
    result = await QwenImageAdapter(cfg).generate(req)
    assert result.provider == "qwen"
    assert "maic/live-smoke/image/" in result.url
    # File on disk should start with PNG (89 50 4E 47) or JPEG (FF D8 FF) magic.
    from django.core.files.storage import default_storage
    storage_key = result.url.split("/media/", 1)[1] if "/media/" in result.url else None
    if storage_key:
        with default_storage.open(storage_key, "rb") as fh:
            header = fh.read(8)
        assert header[:4] == b"\x89PNG" or header[:3] == b"\xff\xd8\xff"
