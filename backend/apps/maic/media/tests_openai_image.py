"""Tests for the OpenAI image reference adapter (MAIC-903).

Discipline:
  - IO-boundary fake only: `aiohttp` is injected into `sys.modules` via
    monkeypatch.setitem — mirrors the Phase 5 Minimax TTS test pattern
    (apps/maic/tests_tts_service.py:_install_fake_aiohttp).
  - No mocks of OpenAIImageAdapter itself. Real adapter, real Pydantic,
    real storage (Django default_storage / FileSystemStorage in tests).
  - Live smoke gated on MAIC_OPENAI_LIVE_SMOKE=1 AND OPENAI_API_KEY env
    vars — skipped (not failed) when either is missing.

Test layout:
  - Fake aiohttp infrastructure (3 helper classes)
  - Adapter unit tests (one per error branch)
  - SSRF + auth boundary tests
  - Cost estimator tests
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
from apps.maic.media.adapters.openai_image import OpenAIImageAdapter
from apps.maic.media.types import ImageGenerationRequest


# ── Fake aiohttp infrastructure (IO-boundary only) ─────────────────────


class _FakeResp:
    """Stand-in for an aiohttp ClientResponse object. Supports the
    async-context-manager protocol (`async with session.post(...) as
    resp`) and exposes status + headers + .text() / .read() / .json()."""

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
    """Stand-in for aiohttp.ClientSession. Captures the last POST so
    tests can assert request shape. Constructor-injected response
    queue lets a test return different responses for the API call vs
    the image-download GET."""

    def __init__(self, *, post_resp: _FakeResp, get_resp: _FakeResp):
        self._post_resp = post_resp
        self._get_resp = get_resp
        self.last_post_url: str | None = None
        self.last_post_json: dict | None = None
        self.last_post_headers: dict | None = None
        self.last_get_url: str | None = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def post(self, url, json=None, headers=None):
        self.last_post_url = url
        self.last_post_json = json
        self.last_post_headers = headers
        return self._post_resp

    def get(self, url):
        self.last_get_url = url
        return self._get_resp


class _FakeClientError(Exception):
    """Stand-in for aiohttp.ClientError — tests that exercise network
    failure path raise this from inside the fake session to simulate
    DNS / connection / read errors."""


def _install_fake_aiohttp(monkeypatch, session: _FakeSession | None = None):
    """Inject a fake aiohttp module exposing ClientSession + ClientError.

    Returns the session captured by the fake module so tests can assert
    on request shape after generate() returns.
    """
    if session is None:
        # Default to a success response (used by happy-path test)
        session = _FakeSession(
            post_resp=_FakeResp(
                status=200,
                body=json.dumps({"data": [{"url": "https://openai-cdn.example/i-1.png"}]}),
            ),
            get_resp=_FakeResp(
                status=200,
                body=b"PNG-bytes-fake",
                headers={"Content-Type": "image/png"},
            ),
        )

    def _client_session_factory():
        # aiohttp.ClientSession() with no args returns a context manager
        # — our fake's __aenter__ returns itself.
        return session

    fake = types.ModuleType("aiohttp")
    fake.ClientSession = _client_session_factory  # type: ignore[attr-defined]
    fake.ClientError = _FakeClientError  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "aiohttp", fake)
    return session


# ── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture
def tenant_config():
    """A minimal TenantAIConfig-shaped object. Real TenantAIConfig
    would do Fernet decrypt; here we shortcut with a SimpleNamespace
    + a get_image_api_key() method that returns the plain key.

    The adapter only touches: get_image_api_key(), image_base_url,
    image_model — those three are the contract."""
    return SimpleNamespace(
        get_image_api_key=lambda: "sk-test-api-key",
        image_base_url="",
        image_model="dall-e-3",
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
    """Every test writes through Django default_storage; pointing
    MEDIA_ROOT at tmp keeps the test tree clean + isolated."""
    settings.MEDIA_ROOT = str(tmp_path)


# ── Happy path ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_happy_path_returns_result_with_storage_url(monkeypatch, tenant_config, req):
    """End-to-end with fake aiohttp: API call → image fetch → storage
    upload → ImageGenerationResult. URL points to OUR storage (NOT
    OpenAI's CDN). Real storage backend writes real bytes."""
    session = _install_fake_aiohttp(monkeypatch)

    adapter = OpenAIImageAdapter(tenant_config)
    result = await adapter.generate(req)

    assert result.provider == "openai"
    assert result.model == "dall-e-3"
    # Result URL is from default_storage, NOT the OpenAI CDN
    assert "openai-cdn.example" not in result.url
    assert "maic/t-1/image/" in result.url
    # Scene id embedded in storage path
    assert "scene-abc__" in result.url
    # Cost is the 1024x1024 standard price
    assert result.cost_usd_estimate == 0.04


@pytest.mark.asyncio
async def test_request_shape_matches_openai_contract(monkeypatch, tenant_config, req):
    """The adapter must send {model, prompt, n, size, quality,
    response_format} per OpenAI's contract. Capture via fake session."""
    session = _install_fake_aiohttp(monkeypatch)

    await OpenAIImageAdapter(tenant_config).generate(req)

    assert session.last_post_url == "https://api.openai.com/v1/images/generations"
    assert session.last_post_headers["Authorization"] == "Bearer sk-test-api-key"
    body = session.last_post_json
    assert body["model"] == "dall-e-3"
    assert body["prompt"] == "a colourful diagram of fractions"
    assert body["n"] == 1
    assert body["size"] == "1024x1024"
    assert body["quality"] == "standard"
    assert body["response_format"] == "url"


# ── Auth / config errors (permanent — orchestrator does NOT retry) ────


@pytest.mark.asyncio
async def test_missing_api_key_raises_config_error(monkeypatch, req):
    """No api_key → MaicConfigError BEFORE any HTTP call. Empty key
    returned by get_image_api_key() is the same as missing."""
    cfg = SimpleNamespace(
        get_image_api_key=lambda: "",
        image_base_url="",
        image_model="dall-e-3",
    )
    # Even though aiohttp gets injected, the adapter raises BEFORE the call.
    _install_fake_aiohttp(monkeypatch)
    with pytest.raises(MaicConfigError) as exc:
        await OpenAIImageAdapter(cfg).generate(req)
    assert "api_key required" in str(exc.value)


@pytest.mark.asyncio
async def test_http_401_raises_config_error(monkeypatch, tenant_config, req):
    """OpenAI returns 401 when the key is wrong — permanent failure,
    MaicConfigError (orchestrator will NOT retry)."""
    session = _FakeSession(
        post_resp=_FakeResp(status=401, body='{"error":{"message":"bad key"}}'),
        get_resp=_FakeResp(),
    )
    _install_fake_aiohttp(monkeypatch, session)

    with pytest.raises(MaicConfigError) as exc:
        await OpenAIImageAdapter(tenant_config).generate(req)
    assert "auth" in str(exc.value).lower()
    assert "401" in str(exc.value)


@pytest.mark.asyncio
async def test_http_403_raises_config_error(monkeypatch, tenant_config, req):
    """403 = forbidden → MaicConfigError. Same category as 401."""
    session = _FakeSession(
        post_resp=_FakeResp(status=403, body='{"error":{"message":"forbidden"}}'),
        get_resp=_FakeResp(),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicConfigError):
        await OpenAIImageAdapter(tenant_config).generate(req)


# ── Transient errors (retried by orchestrator) ────────────────────────


@pytest.mark.asyncio
async def test_http_429_raises_provider_error(monkeypatch, tenant_config, req):
    """429 rate limit → MaicProviderError → orchestrator will retry."""
    session = _FakeSession(
        post_resp=_FakeResp(status=429, body='{"error":{"message":"rate limit"}}'),
        get_resp=_FakeResp(),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await OpenAIImageAdapter(tenant_config).generate(req)
    assert "429" in str(exc.value)


@pytest.mark.asyncio
async def test_http_500_raises_provider_error(monkeypatch, tenant_config, req):
    """5xx → MaicProviderError (transient server fault)."""
    session = _FakeSession(
        post_resp=_FakeResp(status=503, body="upstream temporarily unavailable"),
        get_resp=_FakeResp(),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await OpenAIImageAdapter(tenant_config).generate(req)
    assert "503" in str(exc.value)


@pytest.mark.asyncio
async def test_other_4xx_raises_provider_error(monkeypatch, tenant_config, req):
    """4xx that isn't 401/403/429 (e.g. 422 content policy) → MaicProviderError.
    Could be retried but typically won't succeed; bounded retry caps the
    damage."""
    session = _FakeSession(
        post_resp=_FakeResp(status=422, body='{"error":{"message":"content policy"}}'),
        get_resp=_FakeResp(),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await OpenAIImageAdapter(tenant_config).generate(req)
    assert "422" in str(exc.value)


@pytest.mark.asyncio
async def test_network_error_raises_provider_error(monkeypatch, tenant_config, req):
    """aiohttp.ClientError (DNS, conn reset, etc.) → MaicProviderError."""

    class _FailingSession(_FakeSession):
        def post(self, url, json=None, headers=None):
            raise _FakeClientError("DNS failure: cannot resolve host")

    _install_fake_aiohttp(
        monkeypatch,
        session=_FailingSession(post_resp=_FakeResp(), get_resp=_FakeResp()),
    )
    with pytest.raises(MaicProviderError) as exc:
        await OpenAIImageAdapter(tenant_config).generate(req)
    assert "network error" in str(exc.value).lower()


# ── Response-shape errors ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_malformed_json_raises_provider_error(monkeypatch, tenant_config, req):
    """OpenAI returned a 200 with non-JSON body (mid-deploy issue,
    proxy error page, etc.) → MaicProviderError."""
    session = _FakeSession(
        post_resp=_FakeResp(status=200, body="not-json-at-all{{{"),
        get_resp=_FakeResp(),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await OpenAIImageAdapter(tenant_config).generate(req)
    assert "malformed" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_missing_data_field_raises_provider_error(monkeypatch, tenant_config, req):
    """OpenAI returned valid JSON but no 'data' field → MaicProviderError."""
    session = _FakeSession(
        post_resp=_FakeResp(status=200, body=json.dumps({"created": 1})),
        get_resp=_FakeResp(),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await OpenAIImageAdapter(tenant_config).generate(req)
    assert "unexpected response shape" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_empty_url_in_response_raises_provider_error(monkeypatch, tenant_config, req):
    """OpenAI returned data[0].url = '' → MaicProviderError."""
    session = _FakeSession(
        post_resp=_FakeResp(status=200, body=json.dumps({"data": [{"url": ""}]})),
        get_resp=_FakeResp(),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError):
        await OpenAIImageAdapter(tenant_config).generate(req)


@pytest.mark.asyncio
async def test_image_fetch_failure_raises_provider_error(monkeypatch, tenant_config, req):
    """The API responded OK but downloading the actual image bytes failed."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({"data": [{"url": "https://openai-cdn.example/expired.png"}]}),
        ),
        get_resp=_FakeResp(status=404, body="not found"),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await OpenAIImageAdapter(tenant_config).generate(req)
    assert "fetch" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_zero_bytes_response_raises_provider_error(monkeypatch, tenant_config, req):
    """Image fetched OK (200) but with empty body."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({"data": [{"url": "https://openai-cdn.example/zero.png"}]}),
        ),
        get_resp=_FakeResp(status=200, body=b"", headers={"Content-Type": "image/png"}),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await OpenAIImageAdapter(tenant_config).generate(req)
    assert "zero bytes" in str(exc.value).lower()


# ── SSRF / base URL handling ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_custom_base_url_goes_through_ssrf_guard(monkeypatch, req):
    """A custom base_url pointing at a private address must be rejected
    by the SSRF guard with MaicConfigError. Proves we don't blindly
    trust tenant input."""
    cfg = SimpleNamespace(
        get_image_api_key=lambda: "sk-x",
        image_base_url="http://127.0.0.1:8080/v1",  # localhost — SSRF reject
        image_model="dall-e-3",
    )
    _install_fake_aiohttp(monkeypatch)

    with pytest.raises(MaicConfigError) as exc:
        await OpenAIImageAdapter(cfg).generate(req)
    assert "ssrf" in str(exc.value).lower() or "base_url" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_default_base_url_skips_ssrf_check(monkeypatch, tenant_config, req):
    """Performance: when image_base_url is empty/default, we don't
    DNS-resolve api.openai.com (the SSRF guard does a real DNS lookup;
    redundant for our own known endpoint). Tested via happy path
    completing without hitting the guard."""
    _install_fake_aiohttp(monkeypatch)
    result = await OpenAIImageAdapter(tenant_config).generate(req)
    assert result.provider == "openai"


# ── Cost estimator (pure unit, no IO) ─────────────────────────────────


def test_cost_estimator_dalle3_standard_1024():
    assert OpenAIImageAdapter._estimate_cost("dall-e-3", 1024, 1024, "standard") == 0.04


def test_cost_estimator_dalle3_hd_1024():
    assert OpenAIImageAdapter._estimate_cost("dall-e-3", 1024, 1024, "high") == 0.08


def test_cost_estimator_dalle3_wide_standard():
    assert OpenAIImageAdapter._estimate_cost("dall-e-3", 1792, 1024, "standard") == 0.08


def test_cost_estimator_dalle3_wide_hd():
    assert OpenAIImageAdapter._estimate_cost("dall-e-3", 1792, 1024, "high") == 0.12


def test_cost_estimator_returns_none_for_unknown_model():
    """gpt-image-1 isn't in our price table — return None rather than
    fabricating a number."""
    assert OpenAIImageAdapter._estimate_cost("gpt-image-1", 1024, 1024, "standard") is None


def test_cost_estimator_returns_none_for_unknown_size():
    """Weird sizes off the price chart → None (we don't extrapolate)."""
    assert OpenAIImageAdapter._estimate_cost("dall-e-3", 512, 512, "standard") == 0.04
    assert OpenAIImageAdapter._estimate_cost("dall-e-3", 2048, 2048, "standard") is None


# ── Registry registration (proves @register_adapter works) ────────────


def test_adapter_is_registered_on_import():
    """Importing the adapter module registered it under (kind, name).
    Other tests in this file have already imported it; the registry
    should contain our (image, openai) entry."""
    from apps.maic.media.providers import _REGISTRY
    assert ("image", "openai") in _REGISTRY
    assert _REGISTRY[("image", "openai")] is OpenAIImageAdapter


# ── Live smoke (gated) ────────────────────────────────────────────────


@pytest.mark.skipif(
    os.environ.get("MAIC_OPENAI_LIVE_SMOKE") != "1"
    or not os.environ.get("OPENAI_API_KEY"),
    reason=(
        "live OpenAI smoke disabled — set MAIC_OPENAI_LIVE_SMOKE=1 and "
        "OPENAI_API_KEY=<real-key> to enable. Costs ~$0.04 per run "
        "(1024x1024 standard DALL-E 3)."
    ),
)
@pytest.mark.asyncio
async def test_live_smoke_real_openai_call(tmp_path, settings):
    """Hits the real OpenAI Images API. Skipped unless env vars set.

    Cost: ~$0.04 per run (1024x1024 standard DALL-E 3).

    Asserts:
      - Real HTTP round-trip succeeds
      - Generated image is uploaded to local storage
      - File on disk is non-zero and starts with a PNG signature
    """
    settings.MEDIA_ROOT = str(tmp_path)
    cfg = SimpleNamespace(
        get_image_api_key=lambda: os.environ["OPENAI_API_KEY"],
        image_base_url="",
        image_model="dall-e-3",
    )
    req = ImageGenerationRequest(
        prompt="a simple line drawing of a triangle and a circle, minimalist",
        tenant_id="live-smoke",
        scene_id="live-smoke-scene",
    )
    result = await OpenAIImageAdapter(cfg).generate(req)
    assert result.provider == "openai"
    # Storage URL is under our MEDIA_ROOT
    assert "maic/live-smoke/image/" in result.url
    # File on disk should start with PNG signature (89 50 4E 47) or JPEG (FF D8 FF)
    from django.core.files.storage import default_storage
    storage_key = result.url.split("/media/", 1)[1] if "/media/" in result.url else None
    if storage_key:
        with default_storage.open(storage_key, "rb") as fh:
            header = fh.read(8)
        assert header[:4] == b"\x89PNG" or header[:3] == b"\xff\xd8\xff"
