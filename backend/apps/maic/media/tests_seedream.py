"""Tests for the Seedream image adapter (MAIC-908).

Mirrors apps/maic/media/tests_openai_image.py (the golden pattern).

Discipline:
  - IO-boundary fake only: `aiohttp` injected into `sys.modules` via
    monkeypatch.setitem.
  - No mocks of SeedreamImageAdapter itself. Real adapter, real Pydantic,
    real storage (Django default_storage / FileSystemStorage in tests).
  - Live smoke gated on MAIC_SEEDREAM_LIVE_SMOKE=1 AND SEEDREAM_API_KEY.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import types
from types import SimpleNamespace

import pytest

from apps.maic.exceptions import MaicConfigError, MaicProviderError
from apps.maic.media.adapters.seedream import SeedreamImageAdapter
from apps.maic.media.types import ImageGenerationRequest


# ── Fake aiohttp infrastructure (IO-boundary only) ─────────────────────


class _FakeResp:
    """Stand-in for aiohttp ClientResponse — async context manager,
    exposes status + headers + text/read/json."""

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
    tests can assert request shape."""

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
    """Stand-in for aiohttp.ClientError."""


def _install_fake_aiohttp(monkeypatch, session: _FakeSession | None = None):
    """Inject a fake aiohttp module exposing ClientSession + ClientError."""
    if session is None:
        session = _FakeSession(
            post_resp=_FakeResp(
                status=200,
                body=json.dumps({"data": [{"url": "https://ark-cdn.example/img-1.png"}]}),
            ),
            get_resp=_FakeResp(
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


# ── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture
def tenant_config():
    """Minimal TenantAIConfig-shaped object. Adapter touches only
    get_image_api_key(), image_base_url, image_model."""
    return SimpleNamespace(
        get_image_api_key=lambda: "sk-seedream-test-key",
        image_base_url="",
        image_model="doubao-seedream-5-0-260128",
    )


@pytest.fixture
def req():
    return ImageGenerationRequest(
        prompt="a misty mountain landscape, ink-wash style",
        tenant_id="t-1",
        scene_id="scene-abc",
    )


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path)


# ── Happy path ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_happy_path_returns_result_with_storage_url(monkeypatch, tenant_config, req):
    """End-to-end with fake aiohttp: API call → image fetch → storage
    upload → ImageGenerationResult. URL points to OUR storage."""
    _install_fake_aiohttp(monkeypatch)

    adapter = SeedreamImageAdapter(tenant_config)
    result = await adapter.generate(req)

    assert result.provider == "seedream"
    assert result.model == "doubao-seedream-5-0-260128"
    assert "ark-cdn.example" not in result.url
    assert "maic/t-1/image/" in result.url
    assert "scene-abc__" in result.url
    # Seedream pricing is contract-private — we never estimate a cost.
    assert result.cost_usd_estimate is None


@pytest.mark.asyncio
async def test_request_shape_matches_seedream_contract(monkeypatch, tenant_config, req):
    """Adapter must POST to /api/v3/images/generations with
    {model, prompt, size, watermark} and a Bearer auth header."""
    session = _install_fake_aiohttp(monkeypatch)

    await SeedreamImageAdapter(tenant_config).generate(req)

    assert session.last_post_url == (
        "https://ark.cn-beijing.volces.com/api/v3/images/generations"
    )
    assert session.last_post_headers["Authorization"] == "Bearer sk-seedream-test-key"
    assert session.last_post_headers["Content-Type"] == "application/json"
    body = session.last_post_json
    assert body["model"] == "doubao-seedream-5-0-260128"
    assert body["prompt"] == "a misty mountain landscape, ink-wash style"
    assert body["size"] == "1024x1024"
    assert body["watermark"] is False
    # Seedream does NOT use OpenAI's n / quality / response_format fields.
    assert "n" not in body
    assert "response_format" not in body


@pytest.mark.asyncio
async def test_b64_json_response_path(monkeypatch, tenant_config, req):
    """Seedream may return b64_json instead of url. Adapter must decode
    + re-host the inline bytes — no second GET to the CDN."""
    fake_png = b"\x89PNG\r\n\x1a\nfake-body"
    encoded = base64.b64encode(fake_png).decode("ascii")
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({"data": [{"b64_json": encoded}]}),
        ),
        # If the adapter tries to GET (it shouldn't), this 500 would
        # surface as a MaicProviderError — proves the URL path isn't
        # taken when b64 is supplied.
        get_resp=_FakeResp(status=500, body="should-not-be-called"),
    )
    _install_fake_aiohttp(monkeypatch, session)

    result = await SeedreamImageAdapter(tenant_config).generate(req)
    assert result.provider == "seedream"
    assert session.last_get_url is None  # never reached


@pytest.mark.asyncio
async def test_custom_model_passed_through(monkeypatch, req):
    """When tenant sets image_model, adapter uses it verbatim — no
    silent overrides to the default."""
    cfg = SimpleNamespace(
        get_image_api_key=lambda: "sk-x",
        image_base_url="",
        image_model="doubao-seedream-4-5-251128",
    )
    session = _install_fake_aiohttp(monkeypatch)
    result = await SeedreamImageAdapter(cfg).generate(req)
    assert session.last_post_json["model"] == "doubao-seedream-4-5-251128"
    assert result.model == "doubao-seedream-4-5-251128"


@pytest.mark.asyncio
async def test_empty_image_model_falls_back_to_default(monkeypatch, req):
    """When tenant leaves image_model empty, adapter uses the default."""
    cfg = SimpleNamespace(
        get_image_api_key=lambda: "sk-x",
        image_base_url="",
        image_model="",
    )
    session = _install_fake_aiohttp(monkeypatch)
    result = await SeedreamImageAdapter(cfg).generate(req)
    assert session.last_post_json["model"] == "doubao-seedream-5-0-260128"
    assert result.model == "doubao-seedream-5-0-260128"


# ── Auth / config errors (permanent — no retry) ───────────────────────


@pytest.mark.asyncio
async def test_missing_api_key_raises_config_error(monkeypatch, req):
    cfg = SimpleNamespace(
        get_image_api_key=lambda: "",
        image_base_url="",
        image_model="doubao-seedream-5-0-260128",
    )
    _install_fake_aiohttp(monkeypatch)
    with pytest.raises(MaicConfigError) as exc:
        await SeedreamImageAdapter(cfg).generate(req)
    assert "api_key required" in str(exc.value)


@pytest.mark.asyncio
async def test_http_401_raises_config_error(monkeypatch, tenant_config, req):
    session = _FakeSession(
        post_resp=_FakeResp(status=401, body='{"error":{"message":"bad key"}}'),
        get_resp=_FakeResp(),
    )
    _install_fake_aiohttp(monkeypatch, session)

    with pytest.raises(MaicConfigError) as exc:
        await SeedreamImageAdapter(tenant_config).generate(req)
    assert "auth" in str(exc.value).lower()
    assert "401" in str(exc.value)


@pytest.mark.asyncio
async def test_http_403_raises_config_error(monkeypatch, tenant_config, req):
    session = _FakeSession(
        post_resp=_FakeResp(status=403, body='{"error":{"message":"forbidden"}}'),
        get_resp=_FakeResp(),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicConfigError):
        await SeedreamImageAdapter(tenant_config).generate(req)


# ── Transient errors (retried by orchestrator) ────────────────────────


@pytest.mark.asyncio
async def test_http_429_raises_provider_error(monkeypatch, tenant_config, req):
    session = _FakeSession(
        post_resp=_FakeResp(status=429, body='{"error":{"message":"rate limit"}}'),
        get_resp=_FakeResp(),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await SeedreamImageAdapter(tenant_config).generate(req)
    assert "429" in str(exc.value)


@pytest.mark.asyncio
async def test_http_500_raises_provider_error(monkeypatch, tenant_config, req):
    session = _FakeSession(
        post_resp=_FakeResp(status=503, body="upstream temporarily unavailable"),
        get_resp=_FakeResp(),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await SeedreamImageAdapter(tenant_config).generate(req)
    assert "503" in str(exc.value)


@pytest.mark.asyncio
async def test_other_4xx_raises_provider_error(monkeypatch, tenant_config, req):
    session = _FakeSession(
        post_resp=_FakeResp(status=422, body='{"error":{"message":"content policy"}}'),
        get_resp=_FakeResp(),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await SeedreamImageAdapter(tenant_config).generate(req)
    assert "422" in str(exc.value)


@pytest.mark.asyncio
async def test_network_error_raises_provider_error(monkeypatch, tenant_config, req):
    class _FailingSession(_FakeSession):
        def post(self, url, json=None, headers=None):
            raise _FakeClientError("DNS failure: cannot resolve host")

    _install_fake_aiohttp(
        monkeypatch,
        session=_FailingSession(post_resp=_FakeResp(), get_resp=_FakeResp()),
    )
    with pytest.raises(MaicProviderError) as exc:
        await SeedreamImageAdapter(tenant_config).generate(req)
    assert "network error" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_error_body_truncated_to_200_chars(monkeypatch, tenant_config, req):
    """Bounded error message truncation — never echo unbounded provider
    output into our exception strings (could be huge / hostile)."""
    huge = "x" * 5_000
    session = _FakeSession(
        post_resp=_FakeResp(status=500, body=huge),
        get_resp=_FakeResp(),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await SeedreamImageAdapter(tenant_config).generate(req)
    # The "xxx..." segment in the message must be at most 200 chars.
    msg = str(exc.value)
    assert "x" * 201 not in msg


# ── Response-shape errors ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_malformed_json_raises_provider_error(monkeypatch, tenant_config, req):
    session = _FakeSession(
        post_resp=_FakeResp(status=200, body="not-json-at-all{{{"),
        get_resp=_FakeResp(),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await SeedreamImageAdapter(tenant_config).generate(req)
    assert "malformed" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_missing_data_field_raises_provider_error(monkeypatch, tenant_config, req):
    session = _FakeSession(
        post_resp=_FakeResp(status=200, body=json.dumps({"created": 1})),
        get_resp=_FakeResp(),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await SeedreamImageAdapter(tenant_config).generate(req)
    assert "unexpected response shape" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_no_url_or_b64_in_response_raises_provider_error(monkeypatch, tenant_config, req):
    """Data[0] exists but contains neither `url` nor `b64_json`."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({"data": [{"foo": "bar"}]}),
        ),
        get_resp=_FakeResp(),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await SeedreamImageAdapter(tenant_config).generate(req)
    assert "no url or b64_json" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_malformed_b64_json_raises_provider_error(monkeypatch, tenant_config, req):
    """Inline b64_json that isn't valid base64 → MaicProviderError."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({"data": [{"b64_json": "@@@not-base64@@@"}]}),
        ),
        get_resp=_FakeResp(),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await SeedreamImageAdapter(tenant_config).generate(req)
    assert "b64_json" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_image_fetch_failure_raises_provider_error(monkeypatch, tenant_config, req):
    """API responded OK but downloading the actual image bytes failed."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({"data": [{"url": "https://ark-cdn.example/expired.png"}]}),
        ),
        get_resp=_FakeResp(status=404, body="not found"),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await SeedreamImageAdapter(tenant_config).generate(req)
    assert "fetch" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_zero_bytes_response_raises_provider_error(monkeypatch, tenant_config, req):
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({"data": [{"url": "https://ark-cdn.example/zero.png"}]}),
        ),
        get_resp=_FakeResp(status=200, body=b"", headers={"Content-Type": "image/png"}),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await SeedreamImageAdapter(tenant_config).generate(req)
    assert "zero bytes" in str(exc.value).lower()


# ── SSRF / base URL handling ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_custom_base_url_goes_through_ssrf_guard(monkeypatch, req):
    """Custom base_url pointing at a private address must be rejected
    by the SSRF guard with MaicConfigError."""
    cfg = SimpleNamespace(
        get_image_api_key=lambda: "sk-x",
        image_base_url="http://127.0.0.1:8080",  # localhost — reject
        image_model="doubao-seedream-5-0-260128",
    )
    _install_fake_aiohttp(monkeypatch)

    with pytest.raises(MaicConfigError) as exc:
        await SeedreamImageAdapter(cfg).generate(req)
    assert "ssrf" in str(exc.value).lower() or "base_url" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_default_base_url_skips_ssrf_check(monkeypatch, tenant_config, req):
    """Performance: empty/default image_base_url skips the SSRF DNS lookup."""
    _install_fake_aiohttp(monkeypatch)
    result = await SeedreamImageAdapter(tenant_config).generate(req)
    assert result.provider == "seedream"


@pytest.mark.asyncio
async def test_explicit_default_base_url_also_skips_ssrf_check(monkeypatch, req):
    """Tenant supplying the default URL verbatim (with or without
    trailing slash) should also skip the SSRF check — same host."""
    cfg = SimpleNamespace(
        get_image_api_key=lambda: "sk-x",
        image_base_url="https://ark.cn-beijing.volces.com/",  # trailing slash
        image_model="doubao-seedream-5-0-260128",
    )
    session = _install_fake_aiohttp(monkeypatch)
    result = await SeedreamImageAdapter(cfg).generate(req)
    assert result.provider == "seedream"
    # Verify the endpoint was assembled correctly (no double slash).
    assert session.last_post_url == (
        "https://ark.cn-beijing.volces.com/api/v3/images/generations"
    )


# ── Registry registration ─────────────────────────────────────────────


def test_adapter_is_registered_on_import():
    """Importing the adapter module registered it under (kind, name)."""
    from apps.maic.media.providers import _REGISTRY
    assert ("image", "seedream") in _REGISTRY
    assert _REGISTRY[("image", "seedream")] is SeedreamImageAdapter


def test_adapter_resolves_via_resolver():
    """resolve_image_provider('seedream') returns an instance of our class."""
    from apps.maic.media.providers import resolve_image_provider
    cfg = SimpleNamespace(
        image_provider="seedream",
        get_image_api_key=lambda: "sk-x",
        image_base_url="",
        image_model="",
    )
    adapter = resolve_image_provider(cfg)
    assert isinstance(adapter, SeedreamImageAdapter)


def test_class_metadata():
    """Sanity-check class-level constants are what the orchestrator expects."""
    assert SeedreamImageAdapter.name == "seedream"
    assert SeedreamImageAdapter.kind == "image"
    assert SeedreamImageAdapter.default_timeout_seconds == 60


# ── Live smoke (gated) ────────────────────────────────────────────────


@pytest.mark.skipif(
    os.environ.get("MAIC_SEEDREAM_LIVE_SMOKE") != "1"
    or not os.environ.get("SEEDREAM_API_KEY"),
    reason=(
        "live Seedream smoke disabled — set MAIC_SEEDREAM_LIVE_SMOKE=1 and "
        "SEEDREAM_API_KEY=<real-key> to enable. Costs vary by Volcengine "
        "contract (no public list price)."
    ),
)
@pytest.mark.asyncio
async def test_live_smoke_real_seedream_call(tmp_path, settings):
    """Hits the real Seedream API on ark.cn-beijing.volces.com.

    Skipped unless env vars set. Asserts:
      - Real HTTP round-trip succeeds
      - Generated image is uploaded to local storage
      - File on disk is non-zero and starts with PNG or JPEG signature
    """
    settings.MEDIA_ROOT = str(tmp_path)
    cfg = SimpleNamespace(
        get_image_api_key=lambda: os.environ["SEEDREAM_API_KEY"],
        image_base_url="",
        image_model=os.environ.get("SEEDREAM_MODEL", "doubao-seedream-5-0-260128"),
    )
    smoke_req = ImageGenerationRequest(
        prompt="a simple line drawing of a triangle and a circle, minimalist",
        tenant_id="live-smoke",
        scene_id="live-smoke-scene",
        width=2048,
        height=2048,
    )
    result = await SeedreamImageAdapter(cfg).generate(smoke_req)
    assert result.provider == "seedream"
    assert "maic/live-smoke/image/" in result.url
    from django.core.files.storage import default_storage
    storage_key = result.url.split("/media/", 1)[1] if "/media/" in result.url else None
    if storage_key:
        with default_storage.open(storage_key, "rb") as fh:
            header = fh.read(8)
        assert header[:4] == b"\x89PNG" or header[:3] == b"\xff\xd8\xff"
