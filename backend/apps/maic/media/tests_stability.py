"""Tests for the Stability AI image adapter (MAIC-909).

Stability is our addition — NOT in upstream OpenMAIC. The source of
truth is Stability's public API docs; this test file mirrors the shape
of tests_openai_image.py / tests_minimax_image.py / tests_seedream.py.

Discipline:
  - IO-boundary fake only: ``aiohttp`` is injected into ``sys.modules``
    via monkeypatch.setitem — same pattern as the sibling adapter tests.
  - No mocks of StabilityImageAdapter itself. Real adapter, real
    Pydantic, real storage (Django default_storage / FileSystemStorage
    in tests).
  - Stability returns image BYTES directly in the response body when we
    set ``Accept: image/*`` — there is no second GET like the URL-based
    siblings do. The fake response carries the bytes inline.
  - Stability accepts multipart/form-data ONLY. The fake _FakeSession.post
    accepts a ``data`` kwarg (in addition to ``json``) so we can capture
    the real aiohttp.FormData object and assert on the fields it carries.
  - Live smoke gated on ``MAIC_STABILITY_LIVE_SMOKE=1`` AND
    ``STABILITY_API_KEY`` env vars — skipped (not failed) when either
    is missing.

Test layout:
  - Fake aiohttp infrastructure (3 helper classes, inlined per task spec)
  - Happy path
  - Request-shape assertions (multipart form fields)
  - Aspect ratio derivation tests (pure unit + integration via request body)
  - Auth / config errors (HTTP 401/403)
  - Transient errors (HTTP 429/4xx/5xx + network errors)
  - Response-shape errors (malformed JSON error body, JSON-on-2xx,
    empty body)
  - SSRF + base URL handling
  - Registry registration
  - Cost estimator (3 SD3.5 tiers + unknown model)
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
from apps.maic.media.adapters.stability import (
    StabilityImageAdapter,
    _aspect_ratio_for,
)
from apps.maic.media.types import ImageGenerationRequest


# ── Fake aiohttp infrastructure (IO-boundary only) ─────────────────────


class _FakeResp:
    """Stand-in for an aiohttp ClientResponse. Async context manager that
    exposes status + headers + .text() / .read() / .json()."""

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
        return self._body.decode("utf-8", errors="replace")

    async def read(self) -> bytes:
        return self._body

    async def json(self):
        return json.loads(self._body.decode("utf-8"))


class _FakeFormData:
    """Stand-in for aiohttp.FormData — accumulates add_field calls into
    a dict so tests can assert on the multipart shape.

    aiohttp.FormData is internally a multipart writer; we don't need its
    serialisation, only the fields the adapter set. The real adapter
    only calls .add_field(); we mirror that surface."""

    def __init__(self, *args, **kwargs):
        # Mirror aiohttp.FormData constructor signature (ignored params).
        self.fields: dict[str, str] = {}

    def add_field(self, name: str, value, **kwargs):
        # The real aiohttp.FormData accepts more kwargs (filename,
        # content_type, etc.); the adapter only uses name+value, so we
        # don't bother with the rest.
        self.fields[name] = value


class _FakeSession:
    """Stand-in for aiohttp.ClientSession. Captures the last POST so
    tests can assert request shape. Stability is a single-POST adapter
    (no second GET) so we only need a post_resp."""

    def __init__(self, *, post_resp: _FakeResp):
        self._post_resp = post_resp
        self.last_post_url: str | None = None
        self.last_post_data = None  # the FormData (or json) the adapter sent
        self.last_post_json: dict | None = None
        self.last_post_headers: dict | None = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def post(self, url, data=None, json=None, headers=None):
        # Stability uses multipart (``data=``); JSON path is unused by
        # the real adapter but we accept it so the fake is forgiving.
        self.last_post_url = url
        self.last_post_data = data
        self.last_post_json = json
        self.last_post_headers = headers
        return self._post_resp


class _FakeClientError(Exception):
    """Stand-in for aiohttp.ClientError — tests that exercise the
    network failure path raise this from inside the fake session."""


def _install_fake_aiohttp(monkeypatch, session: _FakeSession | None = None):
    """Inject a fake aiohttp module exposing ClientSession + ClientError
    + FormData. Returns the session so tests can assert on captured
    request fields after generate() returns."""
    if session is None:
        # Default to a success response — 200 + image bytes + image/png.
        # PNG magic header so any "is this PNG-ish" check passes; the
        # adapter doesn't sniff but downstream code might.
        png_bytes = b"\x89PNG\r\n\x1a\nfake-stability-png-bytes"
        session = _FakeSession(
            post_resp=_FakeResp(
                status=200,
                body=png_bytes,
                headers={"Content-Type": "image/png"},
            ),
        )

    def _client_session_factory():
        return session

    fake = types.ModuleType("aiohttp")
    fake.ClientSession = _client_session_factory  # type: ignore[attr-defined]
    fake.ClientError = _FakeClientError  # type: ignore[attr-defined]
    fake.FormData = _FakeFormData  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "aiohttp", fake)
    return session


# ── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture
def tenant_config():
    """A minimal TenantAIConfig-shaped object. The adapter only touches
    get_image_api_key(), image_base_url, image_model."""
    return SimpleNamespace(
        get_image_api_key=lambda: "sk-stability-test-key",
        image_base_url="",
        image_model="sd3.5-large",
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
    """End-to-end with fake aiohttp: API call returns bytes directly →
    storage upload → ImageGenerationResult. URL points to OUR storage."""
    _install_fake_aiohttp(monkeypatch)

    result = await StabilityImageAdapter(tenant_config).generate(req)

    assert result.provider == "stability"
    assert result.model == "sd3.5-large"
    assert "maic/t-1/image/" in result.url
    assert "scene-abc__" in result.url
    # Cost: sd3.5-large list price is $0.065
    assert result.cost_usd_estimate == 0.065


@pytest.mark.asyncio
async def test_request_shape_uses_multipart_v2beta_endpoint(monkeypatch, tenant_config, req):
    """The adapter must POST multipart/form-data to the v2beta SD3
    endpoint with {prompt, aspect_ratio, model, output_format} fields
    and Bearer auth + Accept: image/* headers."""
    session = _install_fake_aiohttp(monkeypatch)

    await StabilityImageAdapter(tenant_config).generate(req)

    assert session.last_post_url == "https://api.stability.ai/v2beta/stable-image/generate/sd3"
    assert session.last_post_headers["Authorization"] == "Bearer sk-stability-test-key"
    assert session.last_post_headers["Accept"] == "image/*"
    # Adapter used FormData, not JSON
    assert session.last_post_json is None
    assert session.last_post_data is not None
    fields = session.last_post_data.fields
    assert fields["prompt"] == "a colourful diagram of fractions"
    # 1024x1024 default → 1:1
    assert fields["aspect_ratio"] == "1:1"
    assert fields["model"] == "sd3.5-large"
    assert fields["output_format"] == "png"
    # No seed was supplied — must not be in the form
    assert "seed" not in fields


@pytest.mark.asyncio
async def test_seed_forwarded_when_supplied(monkeypatch, tenant_config):
    """A request with seed=12345 must include seed in the multipart form
    as a string ("12345"), because aiohttp.FormData fields are strings."""
    seeded_req = ImageGenerationRequest(
        prompt="seeded prompt",
        tenant_id="t-1",
        scene_id="scene-seed",
        seed=12345,
    )
    session = _install_fake_aiohttp(monkeypatch)
    await StabilityImageAdapter(tenant_config).generate(seeded_req)
    assert session.last_post_data.fields["seed"] == "12345"


# ── Aspect ratio derivation (integration via request body) ────────────


@pytest.mark.asyncio
async def test_aspect_ratio_16_9_from_1920x1080(monkeypatch, tenant_config):
    r = ImageGenerationRequest(
        prompt="x", tenant_id="t-1", width=1920, height=1080,
    )
    session = _install_fake_aiohttp(monkeypatch)
    await StabilityImageAdapter(tenant_config).generate(r)
    assert session.last_post_data.fields["aspect_ratio"] == "16:9"


@pytest.mark.asyncio
async def test_aspect_ratio_9_16_from_1080x1920(monkeypatch, tenant_config):
    r = ImageGenerationRequest(
        prompt="x", tenant_id="t-1", width=1080, height=1920,
    )
    session = _install_fake_aiohttp(monkeypatch)
    await StabilityImageAdapter(tenant_config).generate(r)
    assert session.last_post_data.fields["aspect_ratio"] == "9:16"


@pytest.mark.asyncio
async def test_aspect_ratio_1500x1000_snaps_to_3_2(monkeypatch, tenant_config):
    """1500×1000 has a 1.5 ratio — snaps to 3:2 (1.5 exact)."""
    r = ImageGenerationRequest(
        prompt="x", tenant_id="t-1", width=1500, height=1000,
    )
    session = _install_fake_aiohttp(monkeypatch)
    await StabilityImageAdapter(tenant_config).generate(r)
    assert session.last_post_data.fields["aspect_ratio"] == "3:2"


# ── Aspect ratio helper unit tests ────────────────────────────────────


def test_aspect_ratio_helper_square():
    assert _aspect_ratio_for(1024, 1024) == "1:1"


def test_aspect_ratio_helper_widescreen():
    assert _aspect_ratio_for(1920, 1080) == "16:9"


def test_aspect_ratio_helper_portrait():
    assert _aspect_ratio_for(1080, 1920) == "9:16"


def test_aspect_ratio_helper_3_2():
    """3:2 = 1.5; 1500×1000 = exact 1.5."""
    assert _aspect_ratio_for(1500, 1000) == "3:2"


def test_aspect_ratio_helper_2_3_portrait():
    assert _aspect_ratio_for(1000, 1500) == "2:3"


def test_aspect_ratio_helper_4_5_portrait():
    assert _aspect_ratio_for(800, 1000) == "4:5"


def test_aspect_ratio_helper_5_4_landscape():
    assert _aspect_ratio_for(1000, 800) == "5:4"


def test_aspect_ratio_helper_21_9_ultrawide():
    assert _aspect_ratio_for(2100, 900) == "21:9"


def test_aspect_ratio_helper_9_21_ultratall():
    assert _aspect_ratio_for(900, 2100) == "9:21"


def test_aspect_ratio_helper_zero_dims_defaults_square():
    """Defensive: 0/0 dims must not crash."""
    assert _aspect_ratio_for(0, 0) == "1:1"


def test_aspect_ratio_helper_negative_defaults_square():
    """Defensive: negative dims must not crash either."""
    assert _aspect_ratio_for(-100, 200) == "1:1"


# ── Auth / config errors (permanent — orchestrator does NOT retry) ────


@pytest.mark.asyncio
async def test_missing_api_key_raises_config_error(monkeypatch, req):
    """No api_key → MaicConfigError BEFORE any HTTP call."""
    cfg = SimpleNamespace(
        get_image_api_key=lambda: "",
        image_base_url="",
        image_model="sd3.5-large",
    )
    _install_fake_aiohttp(monkeypatch)
    with pytest.raises(MaicConfigError) as exc:
        await StabilityImageAdapter(cfg).generate(req)
    assert "api_key required" in str(exc.value)


@pytest.mark.asyncio
async def test_http_401_raises_config_error(monkeypatch, tenant_config, req):
    """Stability returns 401 when the key is invalid — permanent failure."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=401,
            body=json.dumps({"name": "unauthorized", "errors": ["Invalid API key"]}),
            headers={"Content-Type": "application/json"},
        ),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicConfigError) as exc:
        await StabilityImageAdapter(tenant_config).generate(req)
    assert "auth" in str(exc.value).lower()
    assert "401" in str(exc.value)


@pytest.mark.asyncio
async def test_http_403_raises_config_error(monkeypatch, tenant_config, req):
    """403 = forbidden → MaicConfigError."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=403,
            body=json.dumps({"name": "forbidden", "errors": ["account suspended"]}),
            headers={"Content-Type": "application/json"},
        ),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicConfigError):
        await StabilityImageAdapter(tenant_config).generate(req)


# ── Transient errors (retried by orchestrator) ────────────────────────


@pytest.mark.asyncio
async def test_http_429_raises_provider_error(monkeypatch, tenant_config, req):
    """429 rate limit → MaicProviderError → orchestrator retries."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=429,
            body=json.dumps({"name": "rate_limited", "errors": ["slow down"]}),
            headers={"Content-Type": "application/json"},
        ),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await StabilityImageAdapter(tenant_config).generate(req)
    assert "429" in str(exc.value)


@pytest.mark.asyncio
async def test_http_500_raises_provider_error(monkeypatch, tenant_config, req):
    """5xx → MaicProviderError (transient server fault)."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=503,
            body="upstream temporarily unavailable",
            headers={"Content-Type": "text/plain"},
        ),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await StabilityImageAdapter(tenant_config).generate(req)
    assert "503" in str(exc.value)


@pytest.mark.asyncio
async def test_other_4xx_raises_provider_error(monkeypatch, tenant_config, req):
    """4xx that isn't 401/403/429 (e.g. 400 bad_request) → MaicProviderError.
    Stability's typical error body is {name, errors[]}; we surface it."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=400,
            body=json.dumps({
                "name": "bad_request",
                "errors": ["prompt is too long"],
            }),
            headers={"Content-Type": "application/json"},
        ),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await StabilityImageAdapter(tenant_config).generate(req)
    assert "400" in str(exc.value)
    # Error message includes the surfaced "name" and first errors entry
    assert "bad_request" in str(exc.value)
    assert "prompt is too long" in str(exc.value)


@pytest.mark.asyncio
async def test_network_error_raises_provider_error(monkeypatch, tenant_config, req):
    """aiohttp.ClientError (DNS, conn reset) → MaicProviderError."""

    class _FailingSession(_FakeSession):
        def post(self, url, data=None, json=None, headers=None):
            raise _FakeClientError("DNS failure: cannot resolve host")

    _install_fake_aiohttp(
        monkeypatch,
        session=_FailingSession(post_resp=_FakeResp()),
    )
    with pytest.raises(MaicProviderError) as exc:
        await StabilityImageAdapter(tenant_config).generate(req)
    assert "network error" in str(exc.value).lower()


# ── Response-shape errors ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_malformed_json_error_body_falls_back_to_raw(monkeypatch, tenant_config, req):
    """Stability returned a 4xx with a JSON Content-Type but malformed
    JSON body. Adapter must still surface a useful MaicProviderError —
    falling back to the raw text body."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=400,
            body="{not-valid-json{{",
            headers={"Content-Type": "application/json"},
        ),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await StabilityImageAdapter(tenant_config).generate(req)
    # 400 status surfaced
    assert "400" in str(exc.value)
    # Some of the raw body survives in the snippet (it isn't replaced
    # with a JSON parse error message)
    assert "not-valid-json" in str(exc.value)


@pytest.mark.asyncio
async def test_json_on_2xx_raises_provider_error(monkeypatch, tenant_config, req):
    """Stability degraded and returned a 200 with JSON instead of image
    bytes. We must not upload the JSON as an "image" — surface as a
    provider error."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({"warning": "image is mostly white"}),
            headers={"Content-Type": "application/json"},
        ),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await StabilityImageAdapter(tenant_config).generate(req)
    assert "json" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_empty_body_on_2xx_raises_provider_error(monkeypatch, tenant_config, req):
    """Stability returned 200 with an empty body — must not upload zero
    bytes as an image."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=b"",
            headers={"Content-Type": "image/png"},
        ),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await StabilityImageAdapter(tenant_config).generate(req)
    assert "empty" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_unknown_content_type_defaults_to_png(monkeypatch, tenant_config, req):
    """2xx with bytes but no Content-Type header → adapter defaults to
    image/png and accepts the bytes (best-effort: server is non-conforming
    but the image bytes are the real signal)."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=b"\x89PNG\r\n\x1a\nfake-png",
            headers={},  # no Content-Type at all
        ),
    )
    _install_fake_aiohttp(monkeypatch, session)
    result = await StabilityImageAdapter(tenant_config).generate(req)
    assert result.provider == "stability"


# ── SSRF / base URL handling ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_custom_base_url_goes_through_ssrf_guard(monkeypatch, req):
    """Custom base_url pointing at a private address must be rejected by
    the SSRF guard with MaicConfigError."""
    cfg = SimpleNamespace(
        get_image_api_key=lambda: "sk-x",
        image_base_url="http://127.0.0.1:8080",  # localhost — SSRF reject
        image_model="sd3.5-large",
    )
    _install_fake_aiohttp(monkeypatch)
    with pytest.raises(MaicConfigError) as exc:
        await StabilityImageAdapter(cfg).generate(req)
    assert "ssrf" in str(exc.value).lower() or "base_url" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_default_base_url_skips_ssrf_check(monkeypatch, tenant_config, req):
    """Performance: when image_base_url is empty/default, we don't
    DNS-resolve api.stability.ai. Tested via happy path completing
    without hitting the guard."""
    _install_fake_aiohttp(monkeypatch)
    result = await StabilityImageAdapter(tenant_config).generate(req)
    assert result.provider == "stability"


@pytest.mark.asyncio
async def test_custom_public_base_url_accepted(monkeypatch, req):
    """A public regional proxy URL must pass the SSRF guard. We patch
    the guard to accept here (can't do real DNS in tests) — proves the
    code path reaches it when the URL isn't the default."""
    cfg = SimpleNamespace(
        get_image_api_key=lambda: "sk-proxy",
        image_base_url="https://stability-proxy.example.com",
        image_model="sd3.5-large",
    )
    import apps.maic.media.adapters.stability as adapter_mod
    monkeypatch.setattr(adapter_mod, "validate_webhook_host", lambda url: None)
    session = _install_fake_aiohttp(monkeypatch)

    await StabilityImageAdapter(cfg).generate(req)
    assert (
        session.last_post_url
        == "https://stability-proxy.example.com/v2beta/stable-image/generate/sd3"
    )


# ── Registry registration ─────────────────────────────────────────────


def test_adapter_is_registered_on_import():
    """Importing the adapter module registered it under ('image', 'stability')."""
    from apps.maic.media.providers import _REGISTRY
    assert ("image", "stability") in _REGISTRY
    assert _REGISTRY[("image", "stability")] is StabilityImageAdapter


# ── Cost estimator (pure unit, no IO) ─────────────────────────────────


def test_cost_estimator_sd35_large():
    assert StabilityImageAdapter._estimate_cost("sd3.5-large") == 0.065


def test_cost_estimator_sd35_large_turbo():
    assert StabilityImageAdapter._estimate_cost("sd3.5-large-turbo") == 0.04


def test_cost_estimator_sd35_medium():
    assert StabilityImageAdapter._estimate_cost("sd3.5-medium") == 0.035


def test_cost_estimator_returns_none_for_unknown_model():
    """Unknown model id → None (never fabricate)."""
    assert StabilityImageAdapter._estimate_cost("sd3-medium-deprecated") is None
    assert StabilityImageAdapter._estimate_cost("") is None


# ── Bounded error message truncation ──────────────────────────────────


@pytest.mark.asyncio
async def test_long_error_body_truncated_to_bound(monkeypatch, tenant_config, req):
    """Adversarial server returns a huge error body — adapter must
    truncate to keep logs sane (snippet ≤200 chars)."""
    long_body = "X" * 10_000
    session = _FakeSession(
        post_resp=_FakeResp(
            status=500,
            body=long_body,
            headers={"Content-Type": "text/plain"},
        ),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await StabilityImageAdapter(tenant_config).generate(req)
    # Total error message has the "stability image: server error (HTTP 500): "
    # prefix plus at most 200 chars of body.
    assert len(str(exc.value)) <= 300


# ── Live smoke (gated) ────────────────────────────────────────────────


@pytest.mark.skipif(
    os.environ.get("MAIC_STABILITY_LIVE_SMOKE") != "1"
    or not os.environ.get("STABILITY_API_KEY"),
    reason=(
        "live Stability smoke disabled — set MAIC_STABILITY_LIVE_SMOKE=1 "
        "and STABILITY_API_KEY=<real-key> to enable. Costs ~$0.065 per "
        "run (sd3.5-large)."
    ),
)
@pytest.mark.asyncio
async def test_live_smoke_real_stability_call(tmp_path, settings):
    """Hits the real Stability v2beta API. Skipped unless env vars set.

    Cost: ~$0.065 per run (sd3.5-large @ 1024x1024).

    Asserts:
      - Real HTTP round-trip succeeds
      - Generated image bytes are uploaded to local storage
      - File on disk starts with a PNG / JPEG signature
    """
    settings.MEDIA_ROOT = str(tmp_path)
    cfg = SimpleNamespace(
        get_image_api_key=lambda: os.environ["STABILITY_API_KEY"],
        image_base_url="",
        image_model="sd3.5-large",
    )
    req_live = ImageGenerationRequest(
        prompt="a simple line drawing of a triangle and a circle, minimalist",
        tenant_id="live-smoke",
        scene_id="live-smoke-scene",
    )
    result = await StabilityImageAdapter(cfg).generate(req_live)
    assert result.provider == "stability"
    assert "maic/live-smoke/image/" in result.url
    from django.core.files.storage import default_storage
    storage_key = result.url.split("/media/", 1)[1] if "/media/" in result.url else None
    if storage_key:
        with default_storage.open(storage_key, "rb") as fh:
            header = fh.read(8)
        assert header[:4] == b"\x89PNG" or header[:3] == b"\xff\xd8\xff"
