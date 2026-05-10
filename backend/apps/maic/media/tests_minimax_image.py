"""Tests for the Minimax image adapter (MAIC-906).

Discipline:
  - IO-boundary fake only: ``aiohttp`` is injected into ``sys.modules``
    via monkeypatch.setitem — mirrors the Phase 5 Minimax TTS test
    pattern (apps/maic/tests_tts_service.py:_install_fake_aiohttp) and
    the Phase 9 reference (apps/maic/media/tests_openai_image.py).
  - No mocks of MinimaxImageAdapter itself. Real adapter, real Pydantic,
    real storage (Django default_storage / FileSystemStorage in tests).
  - Live smoke gated on ``MAIC_MINIMAX_IMAGE_LIVE_SMOKE=1`` AND
    ``MINIMAX_API_KEY`` env vars — skipped (not failed) when either
    is missing.

Test layout:
  - Fake aiohttp infrastructure (3 helper classes, inlined per task spec)
  - Happy path
  - Request-shape assertions (Minimax-specific headers/body)
  - Auth / config errors (HTTP 401/403 + base_resp auth-class codes)
  - Transient errors (HTTP 429/4xx/5xx + base_resp non-auth codes +
    network errors)
  - Response-shape errors (malformed JSON, missing data, image fetch
    failure, zero bytes)
  - Env-var key fallback (Phase 5 TTS pattern)
  - SSRF + base URL handling
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
from apps.maic.media.adapters.minimax_image import (
    MinimaxImageAdapter,
    _aspect_ratio_for,
)
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
        # Default to a success response (used by happy-path test).
        # Minimax response shape: {data: {image_urls: [...]}, base_resp:
        # {status_code: 0, status_msg: "success"}}.
        session = _FakeSession(
            post_resp=_FakeResp(
                status=200,
                body=json.dumps({
                    "data": {"image_urls": ["https://minimax-cdn.example/i-1.jpg"]},
                    "base_resp": {"status_code": 0, "status_msg": "success"},
                }),
            ),
            get_resp=_FakeResp(
                status=200,
                body=b"JPEG-bytes-fake",
                headers={"Content-Type": "image/jpeg"},
            ),
        )

    def _client_session_factory():
        return session

    fake = types.ModuleType("aiohttp")
    fake.ClientSession = _client_session_factory  # type: ignore[attr-defined]
    fake.ClientError = _FakeClientError  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "aiohttp", fake)
    return session


# ── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture
def tenant_config():
    """A minimal TenantAIConfig-shaped object. The adapter only touches:
    get_image_api_key(), image_base_url, image_model — plus the optional
    allow_env_key_fallback opt-out."""
    return SimpleNamespace(
        get_image_api_key=lambda: "mm-test-api-key",
        image_base_url="",
        image_model="image-01",
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


@pytest.fixture(autouse=True)
def clear_env_key(monkeypatch):
    """Ensure MINIMAX_API_KEY env var leakage from the host shell or a
    previous test never silently rescues an empty-tenant-key case.
    Tests that exercise the fallback set it explicitly."""
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)


# ── Happy path ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_happy_path_returns_result_with_storage_url(monkeypatch, tenant_config, req):
    """End-to-end with fake aiohttp: API call → image fetch → storage
    upload → ImageGenerationResult. URL points to OUR storage (NOT
    Minimax's CDN)."""
    _install_fake_aiohttp(monkeypatch)

    adapter = MinimaxImageAdapter(tenant_config)
    result = await adapter.generate(req)

    assert result.provider == "minimax"
    assert result.model == "image-01"
    # Result URL is from default_storage, NOT the Minimax CDN
    assert "minimax-cdn.example" not in result.url
    assert "maic/t-1/image/" in result.url
    # Scene id embedded in storage path
    assert "scene-abc__" in result.url
    # Cost estimator returns None for Minimax (no pricing table)
    assert result.cost_usd_estimate is None


@pytest.mark.asyncio
async def test_request_shape_matches_minimax_contract(monkeypatch, tenant_config, req):
    """The adapter must send {model, prompt, aspect_ratio, response_format,
    n, prompt_optimizer} per Minimax's contract. Capture via fake session.
    The endpoint is /v1/image_generation (NOT OpenAI's /v1/images/generations)."""
    session = _install_fake_aiohttp(monkeypatch)

    await MinimaxImageAdapter(tenant_config).generate(req)

    assert session.last_post_url == "https://api.minimaxi.com/v1/image_generation"
    assert session.last_post_headers["Authorization"] == "Bearer mm-test-api-key"
    # Minimax docs specify charset=utf-8 explicitly; we mirror that.
    assert "application/json" in session.last_post_headers["Content-Type"]
    body = session.last_post_json
    assert body["model"] == "image-01"
    assert body["prompt"] == "a colourful diagram of fractions"
    assert body["n"] == 1
    # 1024x1024 default → "1:1" aspect ratio
    assert body["aspect_ratio"] == "1:1"
    assert body["response_format"] == "url"
    assert body["prompt_optimizer"] is False


# ── Auth / config errors (permanent — orchestrator does NOT retry) ────


@pytest.mark.asyncio
async def test_missing_api_key_raises_config_error(monkeypatch, req):
    """No api_key on tenant AND no env fallback → MaicConfigError BEFORE
    any HTTP call."""
    cfg = SimpleNamespace(
        get_image_api_key=lambda: "",
        image_base_url="",
        image_model="image-01",
    )
    _install_fake_aiohttp(monkeypatch)
    with pytest.raises(MaicConfigError) as exc:
        await MinimaxImageAdapter(cfg).generate(req)
    assert "api_key required" in str(exc.value)


@pytest.mark.asyncio
async def test_http_401_raises_config_error(monkeypatch, tenant_config, req):
    """HTTP 401 → MaicConfigError (auth failed; orchestrator will NOT retry)."""
    session = _FakeSession(
        post_resp=_FakeResp(status=401, body='{"error":{"message":"bad key"}}'),
        get_resp=_FakeResp(),
    )
    _install_fake_aiohttp(monkeypatch, session)

    with pytest.raises(MaicConfigError) as exc:
        await MinimaxImageAdapter(tenant_config).generate(req)
    assert "auth" in str(exc.value).lower()
    assert "401" in str(exc.value)


@pytest.mark.asyncio
async def test_http_403_raises_config_error(monkeypatch, tenant_config, req):
    """HTTP 403 → MaicConfigError."""
    session = _FakeSession(
        post_resp=_FakeResp(status=403, body='{"error":{"message":"forbidden"}}'),
        get_resp=_FakeResp(),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicConfigError):
        await MinimaxImageAdapter(tenant_config).generate(req)


# ── Transient errors (retried by orchestrator) ────────────────────────


@pytest.mark.asyncio
async def test_http_429_raises_provider_error(monkeypatch, tenant_config, req):
    """HTTP 429 → MaicProviderError → orchestrator will retry."""
    session = _FakeSession(
        post_resp=_FakeResp(status=429, body='{"error":{"message":"rate limit"}}'),
        get_resp=_FakeResp(),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await MinimaxImageAdapter(tenant_config).generate(req)
    assert "429" in str(exc.value)


@pytest.mark.asyncio
async def test_http_500_raises_provider_error(monkeypatch, tenant_config, req):
    """HTTP 5xx → MaicProviderError (transient server fault)."""
    session = _FakeSession(
        post_resp=_FakeResp(status=503, body="upstream temporarily unavailable"),
        get_resp=_FakeResp(),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await MinimaxImageAdapter(tenant_config).generate(req)
    assert "503" in str(exc.value)


@pytest.mark.asyncio
async def test_other_4xx_raises_provider_error(monkeypatch, tenant_config, req):
    """4xx that isn't 401/403/429 (e.g. 422 content policy) → MaicProviderError."""
    session = _FakeSession(
        post_resp=_FakeResp(status=422, body='{"error":{"message":"content policy"}}'),
        get_resp=_FakeResp(),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await MinimaxImageAdapter(tenant_config).generate(req)
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
        await MinimaxImageAdapter(tenant_config).generate(req)
    assert "network error" in str(exc.value).lower()


# ── base_resp envelope (Minimax-specific 200-OK-but-error) ────────────


@pytest.mark.asyncio
async def test_base_resp_auth_code_1004_raises_config_error(monkeypatch, tenant_config, req):
    """base_resp.status_code=1004 (auth failed) → MaicConfigError. Even
    though HTTP is 200, this is a permanent failure — no retry."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({
                "base_resp": {"status_code": 1004, "status_msg": "account auth failed"},
            }),
        ),
        get_resp=_FakeResp(),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicConfigError) as exc:
        await MinimaxImageAdapter(tenant_config).generate(req)
    assert "1004" in str(exc.value)
    assert "auth" in str(exc.value).lower() or "quota" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_base_resp_auth_code_1008_raises_config_error(monkeypatch, tenant_config, req):
    """base_resp.status_code=1008 (insufficient balance) → MaicConfigError.
    Operator must top up — retry won't fix it."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({
                "base_resp": {"status_code": 1008, "status_msg": "insufficient balance"},
            }),
        ),
        get_resp=_FakeResp(),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicConfigError) as exc:
        await MinimaxImageAdapter(tenant_config).generate(req)
    assert "1008" in str(exc.value)


@pytest.mark.asyncio
async def test_base_resp_auth_code_2049_raises_config_error(monkeypatch, tenant_config, req):
    """base_resp.status_code=2049 (invalid api key — often wrong region)
    → MaicConfigError."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({
                "base_resp": {"status_code": 2049, "status_msg": "invalid api key"},
            }),
        ),
        get_resp=_FakeResp(),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicConfigError) as exc:
        await MinimaxImageAdapter(tenant_config).generate(req)
    assert "2049" in str(exc.value)


@pytest.mark.asyncio
async def test_base_resp_other_code_raises_provider_error(monkeypatch, tenant_config, req):
    """Non-auth base_resp.status_code (e.g. 2013 = invalid voice, or any
    code we don't recognise) → MaicProviderError (transient / unknown)."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({
                "base_resp": {"status_code": 2013, "status_msg": "invalid parameter"},
            }),
        ),
        get_resp=_FakeResp(),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await MinimaxImageAdapter(tenant_config).generate(req)
    assert "2013" in str(exc.value)


@pytest.mark.asyncio
async def test_base_resp_status_zero_treated_as_success(monkeypatch, tenant_config, req):
    """base_resp.status_code=0 is the success sentinel — must NOT raise."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({
                "data": {"image_urls": ["https://minimax-cdn.example/ok.jpg"]},
                "base_resp": {"status_code": 0, "status_msg": "success"},
            }),
        ),
        get_resp=_FakeResp(
            status=200,
            body=b"JPEG-bytes",
            headers={"Content-Type": "image/jpeg"},
        ),
    )
    _install_fake_aiohttp(monkeypatch, session)
    result = await MinimaxImageAdapter(tenant_config).generate(req)
    assert result.provider == "minimax"


@pytest.mark.asyncio
async def test_base_resp_absent_treated_as_success(monkeypatch, tenant_config, req):
    """If the provider omits base_resp entirely (older API version, proxy
    stripping it), we must still treat the response as success when
    image_urls are present. The HTTP status is the authoritative signal."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({
                "data": {"image_urls": ["https://minimax-cdn.example/no-base.jpg"]},
            }),
        ),
        get_resp=_FakeResp(
            status=200,
            body=b"bytes",
            headers={"Content-Type": "image/jpeg"},
        ),
    )
    _install_fake_aiohttp(monkeypatch, session)
    result = await MinimaxImageAdapter(tenant_config).generate(req)
    assert result.provider == "minimax"


# ── Response-shape errors ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_malformed_json_raises_provider_error(monkeypatch, tenant_config, req):
    """HTTP 200 but non-JSON body (proxy error page, mid-deploy) → MaicProviderError."""
    session = _FakeSession(
        post_resp=_FakeResp(status=200, body="not-json-at-all{{{"),
        get_resp=_FakeResp(),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await MinimaxImageAdapter(tenant_config).generate(req)
    assert "malformed" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_missing_data_field_raises_provider_error(monkeypatch, tenant_config, req):
    """Valid JSON, success base_resp, but no 'data' field → MaicProviderError."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({"base_resp": {"status_code": 0, "status_msg": "ok"}}),
        ),
        get_resp=_FakeResp(),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await MinimaxImageAdapter(tenant_config).generate(req)
    assert "unexpected response shape" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_empty_image_urls_raises_provider_error(monkeypatch, tenant_config, req):
    """data.image_urls = [] → MaicProviderError."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({
                "data": {"image_urls": []},
                "base_resp": {"status_code": 0, "status_msg": "ok"},
            }),
        ),
        get_resp=_FakeResp(),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await MinimaxImageAdapter(tenant_config).generate(req)
    assert "unexpected response shape" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_empty_url_string_raises_provider_error(monkeypatch, tenant_config, req):
    """data.image_urls[0] = '' (empty string) → MaicProviderError."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({
                "data": {"image_urls": [""]},
                "base_resp": {"status_code": 0, "status_msg": "ok"},
            }),
        ),
        get_resp=_FakeResp(),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError):
        await MinimaxImageAdapter(tenant_config).generate(req)


@pytest.mark.asyncio
async def test_image_fetch_failure_raises_provider_error(monkeypatch, tenant_config, req):
    """API responded OK but downloading the image bytes failed (CDN
    expired URL, etc.)."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({
                "data": {"image_urls": ["https://minimax-cdn.example/expired.jpg"]},
                "base_resp": {"status_code": 0, "status_msg": "ok"},
            }),
        ),
        get_resp=_FakeResp(status=404, body="not found"),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await MinimaxImageAdapter(tenant_config).generate(req)
    assert "fetch" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_zero_bytes_response_raises_provider_error(monkeypatch, tenant_config, req):
    """Image fetched OK (200) but with empty body."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({
                "data": {"image_urls": ["https://minimax-cdn.example/zero.jpg"]},
                "base_resp": {"status_code": 0, "status_msg": "ok"},
            }),
        ),
        get_resp=_FakeResp(status=200, body=b"", headers={"Content-Type": "image/jpeg"}),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await MinimaxImageAdapter(tenant_config).generate(req)
    assert "zero bytes" in str(exc.value).lower()


# ── Env-var key fallback (Phase 5 TTS pattern) ────────────────────────


@pytest.mark.asyncio
async def test_env_key_fallback_when_tenant_key_empty(monkeypatch, req):
    """Phase 5 TTS pattern: empty tenant key falls back to MINIMAX_API_KEY
    env var. Default tenant has no allow_env_key_fallback attribute, so
    the fallback IS active by default."""
    monkeypatch.setenv("MINIMAX_API_KEY", "env-fallback-key")
    cfg = SimpleNamespace(
        get_image_api_key=lambda: "",
        image_base_url="",
        image_model="image-01",
    )
    session = _install_fake_aiohttp(monkeypatch)

    result = await MinimaxImageAdapter(cfg).generate(req)
    assert result.provider == "minimax"
    assert session.last_post_headers["Authorization"] == "Bearer env-fallback-key"


@pytest.mark.asyncio
async def test_env_key_fallback_disabled_when_tenant_opts_out(monkeypatch, req):
    """Enterprise tenants set allow_env_key_fallback=False to require
    strict per-tenant keying. The env var must be ignored in that case."""
    monkeypatch.setenv("MINIMAX_API_KEY", "env-fallback-key")
    cfg = SimpleNamespace(
        get_image_api_key=lambda: "",
        image_base_url="",
        image_model="image-01",
        allow_env_key_fallback=False,
    )
    _install_fake_aiohttp(monkeypatch)
    with pytest.raises(MaicConfigError) as exc:
        await MinimaxImageAdapter(cfg).generate(req)
    assert "api_key required" in str(exc.value)


@pytest.mark.asyncio
async def test_tenant_key_preferred_over_env_key(monkeypatch, req):
    """When both are set, the tenant key wins. Critical for multi-tenant
    isolation — operator env var must never override an explicit tenant
    config."""
    monkeypatch.setenv("MINIMAX_API_KEY", "env-key-DO-NOT-USE")
    cfg = SimpleNamespace(
        get_image_api_key=lambda: "tenant-explicit-key",
        image_base_url="",
        image_model="image-01",
    )
    session = _install_fake_aiohttp(monkeypatch)

    await MinimaxImageAdapter(cfg).generate(req)
    assert session.last_post_headers["Authorization"] == "Bearer tenant-explicit-key"


# ── SSRF / base URL handling ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_custom_base_url_goes_through_ssrf_guard(monkeypatch, req):
    """Custom base_url pointing at a private address must be rejected
    by the SSRF guard with MaicConfigError."""
    cfg = SimpleNamespace(
        get_image_api_key=lambda: "mm-x",
        image_base_url="http://127.0.0.1:8080/v1",
        image_model="image-01",
    )
    _install_fake_aiohttp(monkeypatch)

    with pytest.raises(MaicConfigError) as exc:
        await MinimaxImageAdapter(cfg).generate(req)
    assert "ssrf" in str(exc.value).lower() or "base_url" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_default_base_url_skips_ssrf_check(monkeypatch, tenant_config, req):
    """Performance: when image_base_url is empty/default, we don't
    DNS-resolve api.minimaxi.com. Verified via happy path completing
    without hitting the guard."""
    _install_fake_aiohttp(monkeypatch)
    result = await MinimaxImageAdapter(tenant_config).generate(req)
    assert result.provider == "minimax"


@pytest.mark.asyncio
async def test_custom_public_base_url_accepted(monkeypatch, req):
    """Public regional endpoints (api.minimax.chat for CN tenants, etc.)
    must pass the SSRF guard. We can't DNS-resolve in tests, so we patch
    the guard to accept — proves the code path reaches it when the URL
    isn't the default."""
    cfg = SimpleNamespace(
        get_image_api_key=lambda: "mm-cn",
        image_base_url="https://api.minimax.chat/v1",
        image_model="image-01",
    )
    # Patch SSRF guard to accept this public host without doing real DNS.
    import apps.maic.media.adapters.minimax_image as adapter_mod
    monkeypatch.setattr(adapter_mod, "validate_webhook_host", lambda url: None)
    session = _install_fake_aiohttp(monkeypatch)

    await MinimaxImageAdapter(cfg).generate(req)
    assert session.last_post_url == "https://api.minimax.chat/v1/image_generation"


# ── Aspect ratio helper (pure unit) ───────────────────────────────────


def test_aspect_ratio_square():
    assert _aspect_ratio_for(1024, 1024) == "1:1"


def test_aspect_ratio_widescreen():
    assert _aspect_ratio_for(1920, 1080) == "16:9"


def test_aspect_ratio_portrait():
    assert _aspect_ratio_for(1080, 1920) == "9:16"


def test_aspect_ratio_classic_4_3():
    assert _aspect_ratio_for(1024, 768) == "4:3"


def test_aspect_ratio_zero_dims_defaults_square():
    """Defensive: zero/negative dims should not crash and not infinite-loop."""
    assert _aspect_ratio_for(0, 0) == "1:1"


# ── Cost estimator ────────────────────────────────────────────────────


def test_cost_estimator_returns_none_for_minimax():
    """No pricing table in upstream code — return None rather than
    fabricate. Operators compute spend from the Minimax dashboard."""
    assert MinimaxImageAdapter._estimate_cost("image-01", 1024, 1024, "standard") is None
    assert MinimaxImageAdapter._estimate_cost("image-01", 1920, 1080, "high") is None


# ── Registry registration ─────────────────────────────────────────────


def test_adapter_is_registered_on_import():
    """Importing the adapter module registered it under ('image', 'minimax')."""
    from apps.maic.media.providers import _REGISTRY
    assert ("image", "minimax") in _REGISTRY
    assert _REGISTRY[("image", "minimax")] is MinimaxImageAdapter


# ── Bounded error message truncation ──────────────────────────────────


@pytest.mark.asyncio
async def test_long_error_body_truncated_to_bound(monkeypatch, tenant_config, req):
    """Adversarial server returns a 1MB error body — adapter must
    truncate to ≤200 chars to keep logs sane."""
    long_body = "X" * 10_000
    session = _FakeSession(
        post_resp=_FakeResp(status=500, body=long_body),
        get_resp=_FakeResp(),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await MinimaxImageAdapter(tenant_config).generate(req)
    # Total error message has the "minimax image: server error (HTTP 500): "
    # prefix (~46 chars) plus at most 200 chars of body.
    assert len(str(exc.value)) <= 300


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
        get_resp=_FakeResp(),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await MinimaxImageAdapter(tenant_config).generate(req)
    assert len(str(exc.value)) <= 300


# ── Live smoke (gated) ────────────────────────────────────────────────


@pytest.mark.skipif(
    os.environ.get("MAIC_MINIMAX_IMAGE_LIVE_SMOKE") != "1"
    or not os.environ.get("MINIMAX_API_KEY"),
    reason=(
        "live Minimax image smoke disabled — set "
        "MAIC_MINIMAX_IMAGE_LIVE_SMOKE=1 and MINIMAX_API_KEY=<real-key> "
        "to enable. Cost varies by Minimax plan; consult dashboard."
    ),
)
@pytest.mark.asyncio
async def test_live_smoke_real_minimax_call(tmp_path, settings):
    """Hits the real Minimax Image API. Skipped unless env vars set.

    Asserts:
      - Real HTTP round-trip succeeds
      - Generated image is uploaded to local storage
      - File on disk is non-zero and starts with a JPEG or PNG signature
    """
    settings.MEDIA_ROOT = str(tmp_path)
    cfg = SimpleNamespace(
        get_image_api_key=lambda: os.environ["MINIMAX_API_KEY"],
        image_base_url="",
        image_model="image-01",
    )
    req = ImageGenerationRequest(
        prompt="a simple line drawing of a triangle and a circle, minimalist",
        tenant_id="live-smoke",
        scene_id="live-smoke-scene",
    )
    result = await MinimaxImageAdapter(cfg).generate(req)
    assert result.provider == "minimax"
    assert "maic/live-smoke/image/" in result.url
    # File on disk should start with PNG (89 50 4E 47) or JPEG (FF D8 FF) signature
    from django.core.files.storage import default_storage
    storage_key = result.url.split("/media/", 1)[1] if "/media/" in result.url else None
    if storage_key:
        with default_storage.open(storage_key, "rb") as fh:
            header = fh.read(8)
        assert header[:4] == b"\x89PNG" or header[:3] == b"\xff\xd8\xff"
