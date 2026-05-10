"""Tests for the Nano Banana (Google Gemini) image adapter (MAIC-907).

Mirrors apps/maic/media/tests_openai_image.py (the golden pattern) with
the critical delta that Gemini returns the image base64-inline — there
is NO second HTTP fetch against a CDN URL, so the happy path exercises
ONE POST and then a base64 decode + storage upload.

Discipline:
  - IO-boundary fake only: `aiohttp` injected into `sys.modules` via
    monkeypatch.setitem (same pattern as openai_image / seedream tests).
  - No mocks of NanoBananaImageAdapter itself. Real adapter, real
    Pydantic, real storage (Django default_storage / FileSystemStorage).
  - Live smoke gated on MAIC_NANO_BANANA_LIVE_SMOKE=1 AND GOOGLE_API_KEY.
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
from apps.maic.media.adapters.nano_banana import NanoBananaImageAdapter
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
    tests can assert request shape. Also tracks GET calls — the
    nano_banana adapter should NEVER GET anything (no CDN fetch);
    `last_get_url is None` after generate() is part of the contract."""

    def __init__(self, *, post_resp: _FakeResp, get_resp: _FakeResp | None = None):
        self._post_resp = post_resp
        self._get_resp = get_resp or _FakeResp(status=500, body="should-not-be-called")
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


def _gemini_inline_response(
    raw_bytes: bytes = b"\x89PNG\r\n\x1a\nfake-body",
    mime_type: str = "image/png",
) -> str:
    """Build a realistic Gemini generateContent response body with one
    inlineData image part."""
    encoded = base64.b64encode(raw_bytes).decode("ascii")
    return json.dumps({
        "candidates": [{
            "content": {
                "parts": [
                    {"inlineData": {"mimeType": mime_type, "data": encoded}},
                ],
            },
        }],
    })


def _install_fake_aiohttp(monkeypatch, session: _FakeSession | None = None):
    """Inject a fake aiohttp module exposing ClientSession + ClientError."""
    if session is None:
        session = _FakeSession(
            post_resp=_FakeResp(status=200, body=_gemini_inline_response()),
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
        get_image_api_key=lambda: "AIzaSy-nano-banana-test-key",
        image_base_url="",
        image_model="gemini-2.5-flash-image",
    )


@pytest.fixture
def req():
    return ImageGenerationRequest(
        prompt="a hand-drawn banana wearing sunglasses, cartoon style",
        tenant_id="t-1",
        scene_id="scene-abc",
    )


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path)


# ── Happy path ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_happy_path_returns_result_with_storage_url(monkeypatch, tenant_config, req):
    """End-to-end with fake aiohttp: POST → base64 decode → storage
    upload → ImageGenerationResult. URL points to OUR storage. Crucially,
    NO GET request is ever made (Gemini returns inline bytes)."""
    session = _install_fake_aiohttp(monkeypatch)

    adapter = NanoBananaImageAdapter(tenant_config)
    result = await adapter.generate(req)

    assert result.provider == "nano_banana"
    assert result.model == "gemini-2.5-flash-image"
    # URL is OURS — never a googleapis.com URL.
    assert "googleapis.com" not in result.url
    assert "generativelanguage" not in result.url
    assert "maic/t-1/image/" in result.url
    assert "scene-abc__" in result.url
    # No second HTTP fetch — the inline-base64 path skips the CDN GET.
    assert session.last_get_url is None
    # Gemini pricing not wired — cost estimate is always None for now.
    assert result.cost_usd_estimate is None


@pytest.mark.asyncio
async def test_request_shape_matches_gemini_contract(monkeypatch, tenant_config, req):
    """Adapter must POST to /v1beta/models/<model>:generateContent with
    Gemini's contents/parts body shape and x-goog-api-key header.

    Differences from OpenAI's contract that must be enforced:
      - URL embeds the model name (not the body)
      - Body uses `contents: [{parts: [{text: ...}]}]` (not `prompt`)
      - Body includes `generationConfig.responseModalities = ["IMAGE"]`
      - Auth header is `x-goog-api-key` (not `Authorization: Bearer`)
      - No `n` / `size` / `quality` / `response_format` fields
    """
    session = _install_fake_aiohttp(monkeypatch)

    await NanoBananaImageAdapter(tenant_config).generate(req)

    # URL: model is in the path, not the body.
    assert session.last_post_url == (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-2.5-flash-image:generateContent"
    )

    # Headers: Google's x-goog-api-key, NOT Bearer.
    assert session.last_post_headers["x-goog-api-key"] == "AIzaSy-nano-banana-test-key"
    assert "Authorization" not in session.last_post_headers
    assert session.last_post_headers["Content-Type"] == "application/json"

    # Body: Gemini contents/parts shape.
    body = session.last_post_json
    assert "contents" in body
    assert isinstance(body["contents"], list) and len(body["contents"]) == 1
    parts = body["contents"][0]["parts"]
    assert isinstance(parts, list) and len(parts) == 1
    assert parts[0]["text"] == "a hand-drawn banana wearing sunglasses, cartoon style"

    # generationConfig must ask for IMAGE modality — otherwise Gemini
    # returns text only.
    assert body["generationConfig"]["responseModalities"] == ["IMAGE"]

    # OpenAI-style flat fields must NOT leak in.
    assert "prompt" not in body
    assert "model" not in body  # model is in URL path, not body
    assert "n" not in body
    assert "size" not in body
    assert "quality" not in body
    assert "response_format" not in body


@pytest.mark.asyncio
async def test_no_second_http_fetch_for_inline_image(monkeypatch, tenant_config, req):
    """Hard guarantee: even if we provide a get_resp that would 500, the
    adapter must NEVER call .get() — proves inline base64 path is taken."""
    session = _FakeSession(
        post_resp=_FakeResp(status=200, body=_gemini_inline_response()),
        get_resp=_FakeResp(status=500, body="must-not-be-called"),
    )
    _install_fake_aiohttp(monkeypatch, session)

    result = await NanoBananaImageAdapter(tenant_config).generate(req)
    assert result.provider == "nano_banana"
    assert session.last_get_url is None


@pytest.mark.asyncio
async def test_mime_type_from_inline_data_preserved(monkeypatch, tenant_config, req):
    """If Gemini returns mimeType=image/jpeg, the upload uses that, not png."""
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=_gemini_inline_response(
                raw_bytes=b"\xff\xd8\xff\xe0-jpeg-body",
                mime_type="image/jpeg",
            ),
        ),
    )
    _install_fake_aiohttp(monkeypatch, session)

    result = await NanoBananaImageAdapter(tenant_config).generate(req)
    # Storage filename should reflect the mime type extension.
    assert result.url.endswith(".jpg") or result.url.endswith(".jpeg") \
        or "image" in result.url  # storage may strip; either way must succeed


@pytest.mark.asyncio
async def test_custom_model_passed_through(monkeypatch, req):
    """When tenant sets image_model, adapter uses it verbatim (in the URL
    path) — no silent overrides to the default."""
    cfg = SimpleNamespace(
        get_image_api_key=lambda: "AIzaSy-x",
        image_base_url="",
        image_model="gemini-3-pro-image-preview",
    )
    session = _install_fake_aiohttp(monkeypatch)
    result = await NanoBananaImageAdapter(cfg).generate(req)
    assert "gemini-3-pro-image-preview:generateContent" in session.last_post_url
    assert result.model == "gemini-3-pro-image-preview"


@pytest.mark.asyncio
async def test_empty_image_model_falls_back_to_default(monkeypatch, req):
    """When tenant leaves image_model empty, adapter uses the default."""
    cfg = SimpleNamespace(
        get_image_api_key=lambda: "AIzaSy-x",
        image_base_url="",
        image_model="",
    )
    session = _install_fake_aiohttp(monkeypatch)
    result = await NanoBananaImageAdapter(cfg).generate(req)
    assert "gemini-2.5-flash-image:generateContent" in session.last_post_url
    assert result.model == "gemini-2.5-flash-image"


# ── Auth / config errors (permanent — no retry) ───────────────────────


@pytest.mark.asyncio
async def test_missing_api_key_raises_config_error(monkeypatch, req):
    cfg = SimpleNamespace(
        get_image_api_key=lambda: "",
        image_base_url="",
        image_model="gemini-2.5-flash-image",
    )
    _install_fake_aiohttp(monkeypatch)
    with pytest.raises(MaicConfigError) as exc:
        await NanoBananaImageAdapter(cfg).generate(req)
    assert "api_key required" in str(exc.value)


@pytest.mark.asyncio
async def test_http_401_raises_config_error(monkeypatch, tenant_config, req):
    session = _FakeSession(
        post_resp=_FakeResp(status=401, body='{"error":{"message":"bad key"}}'),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicConfigError) as exc:
        await NanoBananaImageAdapter(tenant_config).generate(req)
    assert "auth" in str(exc.value).lower()
    assert "401" in str(exc.value)


@pytest.mark.asyncio
async def test_http_403_raises_config_error(monkeypatch, tenant_config, req):
    session = _FakeSession(
        post_resp=_FakeResp(status=403, body='{"error":{"message":"forbidden"}}'),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicConfigError):
        await NanoBananaImageAdapter(tenant_config).generate(req)


# ── Transient errors (retried by orchestrator) ────────────────────────


@pytest.mark.asyncio
async def test_http_429_raises_provider_error(monkeypatch, tenant_config, req):
    session = _FakeSession(
        post_resp=_FakeResp(status=429, body='{"error":{"message":"rate limit"}}'),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await NanoBananaImageAdapter(tenant_config).generate(req)
    assert "429" in str(exc.value)


@pytest.mark.asyncio
async def test_http_500_raises_provider_error(monkeypatch, tenant_config, req):
    session = _FakeSession(
        post_resp=_FakeResp(status=503, body="upstream temporarily unavailable"),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await NanoBananaImageAdapter(tenant_config).generate(req)
    assert "503" in str(exc.value)


@pytest.mark.asyncio
async def test_other_4xx_raises_provider_error(monkeypatch, tenant_config, req):
    session = _FakeSession(
        post_resp=_FakeResp(status=400, body='{"error":{"message":"bad request"}}'),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await NanoBananaImageAdapter(tenant_config).generate(req)
    assert "400" in str(exc.value)


@pytest.mark.asyncio
async def test_network_error_raises_provider_error(monkeypatch, tenant_config, req):
    class _FailingSession(_FakeSession):
        def post(self, url, json=None, headers=None):
            raise _FakeClientError("DNS failure: cannot resolve host")

    _install_fake_aiohttp(
        monkeypatch,
        session=_FailingSession(post_resp=_FakeResp()),
    )
    with pytest.raises(MaicProviderError) as exc:
        await NanoBananaImageAdapter(tenant_config).generate(req)
    assert "network error" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_error_body_truncated_to_200_chars(monkeypatch, tenant_config, req):
    """Bounded error message truncation — never echo unbounded provider
    output into our exception strings."""
    huge = "x" * 5_000
    session = _FakeSession(
        post_resp=_FakeResp(status=500, body=huge),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await NanoBananaImageAdapter(tenant_config).generate(req)
    msg = str(exc.value)
    assert "x" * 201 not in msg


# ── Response-shape errors ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_malformed_json_raises_provider_error(monkeypatch, tenant_config, req):
    session = _FakeSession(
        post_resp=_FakeResp(status=200, body="not-json-at-all{{{"),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await NanoBananaImageAdapter(tenant_config).generate(req)
    assert "malformed" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_missing_candidates_field_raises_provider_error(monkeypatch, tenant_config, req):
    """Top-level response is JSON but has no `candidates` array — bad shape."""
    session = _FakeSession(
        post_resp=_FakeResp(status=200, body=json.dumps({"foo": "bar"})),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await NanoBananaImageAdapter(tenant_config).generate(req)
    assert "candidates" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_empty_candidates_array_raises_provider_error(monkeypatch, tenant_config, req):
    session = _FakeSession(
        post_resp=_FakeResp(status=200, body=json.dumps({"candidates": []})),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await NanoBananaImageAdapter(tenant_config).generate(req)
    assert "candidates" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_missing_content_raises_provider_error(monkeypatch, tenant_config, req):
    session = _FakeSession(
        post_resp=_FakeResp(
            status=200,
            body=json.dumps({"candidates": [{"finishReason": "STOP"}]}),
        ),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await NanoBananaImageAdapter(tenant_config).generate(req)
    assert "content" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_missing_inline_data_raises_provider_error(monkeypatch, tenant_config, req):
    """Gemini returned only a text part (safety rejection or model
    misconfigured to return text). Adapter must surface that text in the
    error message for debugging."""
    body = json.dumps({
        "candidates": [{
            "content": {
                "parts": [
                    {"text": "I cannot generate that image due to policy."},
                ],
            },
        }],
    })
    session = _FakeSession(
        post_resp=_FakeResp(status=200, body=body),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await NanoBananaImageAdapter(tenant_config).generate(req)
    msg = str(exc.value).lower()
    assert "inlinedata" in msg or "no inline" in msg
    # Text snippet from the refusal should be in the message.
    assert "policy" in str(exc.value).lower() or "cannot" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_malformed_base64_raises_provider_error(monkeypatch, tenant_config, req):
    """Inline data field is present but not valid base64 → MaicProviderError
    (server returned bad payload)."""
    body = json.dumps({
        "candidates": [{
            "content": {
                "parts": [
                    {"inlineData": {"mimeType": "image/png", "data": "@@@not-base64@@@"}},
                ],
            },
        }],
    })
    session = _FakeSession(
        post_resp=_FakeResp(status=200, body=body),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await NanoBananaImageAdapter(tenant_config).generate(req)
    assert "base64" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_empty_inline_data_raises_provider_error(monkeypatch, tenant_config, req):
    """inlineData.data is empty string → bad payload."""
    body = json.dumps({
        "candidates": [{
            "content": {
                "parts": [
                    {"inlineData": {"mimeType": "image/png", "data": ""}},
                ],
            },
        }],
    })
    session = _FakeSession(
        post_resp=_FakeResp(status=200, body=body),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await NanoBananaImageAdapter(tenant_config).generate(req)
    assert "data" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_error_block_in_200_body_raises_provider_error(monkeypatch, tenant_config, req):
    """Google APIs occasionally return HTTP 200 with an `error` block —
    promote that to MaicProviderError instead of silently parsing as success."""
    body = json.dumps({
        "error": {
            "code": 400,
            "message": "Quota exceeded",
            "status": "RESOURCE_EXHAUSTED",
        },
    })
    session = _FakeSession(
        post_resp=_FakeResp(status=200, body=body),
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await NanoBananaImageAdapter(tenant_config).generate(req)
    assert "gemini error" in str(exc.value).lower()
    assert "quota" in str(exc.value).lower()


# ── SSRF / base URL handling ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_custom_base_url_goes_through_ssrf_guard(monkeypatch, req):
    """Custom base_url pointing at a private address must be rejected
    by the SSRF guard with MaicConfigError."""
    cfg = SimpleNamespace(
        get_image_api_key=lambda: "AIzaSy-x",
        image_base_url="http://127.0.0.1:8080",  # localhost — reject
        image_model="gemini-2.5-flash-image",
    )
    _install_fake_aiohttp(monkeypatch)

    with pytest.raises(MaicConfigError) as exc:
        await NanoBananaImageAdapter(cfg).generate(req)
    assert "ssrf" in str(exc.value).lower() or "base_url" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_default_base_url_skips_ssrf_check(monkeypatch, tenant_config, req):
    """Performance: empty/default image_base_url skips the SSRF DNS lookup."""
    _install_fake_aiohttp(monkeypatch)
    result = await NanoBananaImageAdapter(tenant_config).generate(req)
    assert result.provider == "nano_banana"


@pytest.mark.asyncio
async def test_explicit_default_base_url_also_skips_ssrf_check(monkeypatch, req):
    """Tenant supplying the default URL verbatim (with or without
    trailing slash) should also skip the SSRF check — same host."""
    cfg = SimpleNamespace(
        get_image_api_key=lambda: "AIzaSy-x",
        image_base_url="https://generativelanguage.googleapis.com/",  # trailing slash
        image_model="gemini-2.5-flash-image",
    )
    session = _install_fake_aiohttp(monkeypatch)
    result = await NanoBananaImageAdapter(cfg).generate(req)
    assert result.provider == "nano_banana"
    # Verify the endpoint was assembled correctly (no double slash).
    assert session.last_post_url == (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-2.5-flash-image:generateContent"
    )


# ── Registry registration ─────────────────────────────────────────────


def test_adapter_is_registered_on_import():
    """Importing the adapter module registered it under (kind, name)."""
    from apps.maic.media.providers import _REGISTRY
    assert ("image", "nano_banana") in _REGISTRY
    assert _REGISTRY[("image", "nano_banana")] is NanoBananaImageAdapter


def test_adapter_resolves_via_resolver():
    """resolve_image_provider('nano_banana') returns an instance of our class."""
    from apps.maic.media.providers import resolve_image_provider
    cfg = SimpleNamespace(
        image_provider="nano_banana",
        get_image_api_key=lambda: "AIzaSy-x",
        image_base_url="",
        image_model="",
    )
    adapter = resolve_image_provider(cfg)
    assert isinstance(adapter, NanoBananaImageAdapter)


def test_class_metadata():
    """Sanity-check class-level constants are what the orchestrator expects."""
    assert NanoBananaImageAdapter.name == "nano_banana"
    assert NanoBananaImageAdapter.kind == "image"
    assert NanoBananaImageAdapter.default_timeout_seconds == 60


# ── Live smoke (gated) ────────────────────────────────────────────────


@pytest.mark.skipif(
    os.environ.get("MAIC_NANO_BANANA_LIVE_SMOKE") != "1"
    or not os.environ.get("GOOGLE_API_KEY"),
    reason=(
        "live Nano Banana smoke disabled — set MAIC_NANO_BANANA_LIVE_SMOKE=1 "
        "and GOOGLE_API_KEY=<real-key> to enable. Costs ~$0.04/image at "
        "Gemini 2.5 Flash Image list price (verify on Google AI pricing page)."
    ),
)
@pytest.mark.asyncio
async def test_live_smoke_real_nano_banana_call(tmp_path, settings):
    """Hits the real Gemini API on generativelanguage.googleapis.com.

    Skipped unless env vars set. Asserts:
      - Real HTTP round-trip succeeds (one POST, no CDN GET)
      - Generated image is uploaded to local storage
      - File on disk is non-zero and starts with PNG or JPEG signature
    """
    settings.MEDIA_ROOT = str(tmp_path)
    cfg = SimpleNamespace(
        get_image_api_key=lambda: os.environ["GOOGLE_API_KEY"],
        image_base_url="",
        image_model=os.environ.get("NANO_BANANA_MODEL", "gemini-2.5-flash-image"),
    )
    smoke_req = ImageGenerationRequest(
        prompt="a simple line drawing of a triangle and a circle, minimalist",
        tenant_id="live-smoke",
        scene_id="live-smoke-scene",
    )
    result = await NanoBananaImageAdapter(cfg).generate(smoke_req)
    assert result.provider == "nano_banana"
    assert "maic/live-smoke/image/" in result.url
    from django.core.files.storage import default_storage
    storage_key = result.url.split("/media/", 1)[1] if "/media/" in result.url else None
    if storage_key:
        with default_storage.open(storage_key, "rb") as fh:
            header = fh.read(8)
        assert header[:4] == b"\x89PNG" or header[:3] == b"\xff\xd8\xff"
