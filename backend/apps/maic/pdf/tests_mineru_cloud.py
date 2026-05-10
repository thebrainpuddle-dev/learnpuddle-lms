"""Tests for the Mineru cloud PDF adapter (MAIC-1002).

Pattern lifted from apps/maic/media/tests_qwen_image.py (async-polling)
and tests_openai_image.py (5-class error matrix). IO-boundary fake
aiohttp via monkeypatch.setitem(sys.modules,…). Real ABC, real
Pydantic, real polling logic with synthetic responses driven by a
fake _FakeSession.
"""
from __future__ import annotations

import json
import os
import sys
import types
from types import SimpleNamespace

import pytest

from apps.maic.exceptions import MaicConfigError, MaicProviderError
from apps.maic.pdf.adapters.mineru_cloud import MineruCloudAdapter
from apps.maic.pdf.types import PDFParseRequest


# ── Fake aiohttp infrastructure ────────────────────────────────────────


class _FakeResp:
    def __init__(self, *, status: int = 200, body: str | bytes = b""):
        self.status = status
        self._body = body.encode() if isinstance(body, str) else body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def text(self) -> str:
        return self._body.decode("utf-8")


class _FakeSession:
    """Captures the submit POST and dispatches GET-to-/extract/task/<id>
    through a configurable list of polling responses (sequence)."""

    def __init__(self, *, submit_resp: _FakeResp, poll_resps: list[_FakeResp]):
        self._submit_resp = submit_resp
        self._poll_resps = poll_resps
        self.poll_index = 0
        self.last_submit_url: str | None = None
        self.last_submit_json: dict | None = None
        self.last_submit_headers: dict | None = None
        self.last_poll_url: str | None = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def post(self, url, json=None, headers=None):
        self.last_submit_url = url
        self.last_submit_json = json
        self.last_submit_headers = headers
        return self._submit_resp

    def get(self, url, headers=None):
        self.last_poll_url = url
        if self.poll_index >= len(self._poll_resps):
            raise AssertionError(
                f"_FakeSession poll exhausted: tried to GET {url} but only "
                f"{len(self._poll_resps)} poll responses provided"
            )
        resp = self._poll_resps[self.poll_index]
        self.poll_index += 1
        return resp


class _FakeClientError(Exception):
    pass


def _install_fake_aiohttp(monkeypatch, session: _FakeSession):
    fake = types.ModuleType("aiohttp")
    fake.ClientSession = lambda: session  # type: ignore[attr-defined]
    fake.ClientError = _FakeClientError  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "aiohttp", fake)
    return session


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def tenant_config():
    """Minimal stand-in: only get_mineru_api_key + mineru_base_url
    needed."""
    return SimpleNamespace(
        get_mineru_api_key=lambda: "mr-test-key",
        mineru_base_url="",
    )


@pytest.fixture
def req():
    return PDFParseRequest(
        file_url="https://storage.example/textbook.pdf",
        tenant_id="t-1",
        scene_id="scene-1",
    )


@pytest.fixture(autouse=True)
def fast_polling(monkeypatch):
    """Make polling interval near-zero so tests don't sleep seconds."""
    monkeypatch.setattr(
        "apps.maic.pdf.adapters.mineru_cloud.MineruCloudAdapter."
        "_poll_interval_seconds",
        0.001,
    )


def _submit_ok(task_id: str = "task-abc") -> _FakeResp:
    return _FakeResp(
        status=200,
        body=json.dumps({"data": {"task_id": task_id}}),
    )


def _poll(state: str, **extras) -> _FakeResp:
    return _FakeResp(
        status=200,
        body=json.dumps({"data": {"state": state, **extras}}),
    )


def _poll_done_with_payload(**fields) -> _FakeResp:
    body = {"data": {"state": "done", **fields}}
    return _FakeResp(status=200, body=json.dumps(body))


# ── Happy path ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_happy_path_pending_running_done(monkeypatch, tenant_config, req):
    """3 poll responses (pending → running → done) → parsed PDFDocument
    with sections + figures + pages extracted."""
    session = _FakeSession(
        submit_resp=_submit_ok(task_id="t-happy"),
        poll_resps=[
            _poll("pending"),
            _poll("running"),
            _poll_done_with_payload(
                total_pages=12,
                title="Fractions Chapter",
                sections=[
                    {"id": "s-1", "title": "Intro", "level": 1,
                     "text": "intro body", "page_start": 1, "page_end": 3},
                ],
                figures=[
                    {"id": "f-1", "caption": "pie chart", "page": 2},
                ],
                pages=[
                    {"page_number": 1, "text": "page 1 text"},
                ],
            ),
        ],
    )
    _install_fake_aiohttp(monkeypatch, session)

    result = await MineruCloudAdapter(tenant_config).parse(req)

    # Used all 3 poll responses (no first-response short-circuit)
    assert session.poll_index == 3

    assert result.state.value == "done"
    assert result.document.document_id == "t-happy"
    assert result.document.title == "Fractions Chapter"
    assert result.document.total_pages == 12
    assert len(result.document.sections) == 1
    assert result.document.sections[0].title == "Intro"
    assert len(result.document.figures) == 1
    assert result.document.figures[0].caption == "pie chart"
    assert len(result.document.pages) == 1


@pytest.mark.asyncio
async def test_submit_request_shape(monkeypatch, tenant_config, req):
    """Captures the submit POST and asserts the body/headers shape
    matches what Mineru expects."""
    session = _FakeSession(
        submit_resp=_submit_ok(),
        poll_resps=[_poll_done_with_payload(total_pages=1)],
    )
    _install_fake_aiohttp(monkeypatch, session)

    await MineruCloudAdapter(tenant_config).parse(req)

    assert session.last_submit_url == "https://mineru.net/api/v4/extract/task"
    assert session.last_submit_headers["Authorization"] == "Bearer mr-test-key"
    body = session.last_submit_json
    assert body["url"] == "https://storage.example/textbook.pdf"
    assert body["is_ocr"] is True
    assert body["enable_formula"] is True
    assert body["enable_table"] is True
    assert body["language"] == "auto"
    # page_limit and extract_images NOT in body when defaults
    assert "page_limit" not in body
    assert "extract_images" not in body


@pytest.mark.asyncio
async def test_submit_request_includes_page_limit_when_set(monkeypatch, tenant_config):
    session = _FakeSession(
        submit_resp=_submit_ok(),
        poll_resps=[_poll_done_with_payload(total_pages=1)],
    )
    _install_fake_aiohttp(monkeypatch, session)
    req_limited = PDFParseRequest(
        file_url="https://storage.example/big.pdf",
        tenant_id="t-1",
        page_limit=10,
    )
    await MineruCloudAdapter(tenant_config).parse(req_limited)
    assert session.last_submit_json["page_limit"] == 10


@pytest.mark.asyncio
async def test_submit_request_disables_extract_images(monkeypatch, tenant_config):
    session = _FakeSession(
        submit_resp=_submit_ok(),
        poll_resps=[_poll_done_with_payload(total_pages=1)],
    )
    _install_fake_aiohttp(monkeypatch, session)
    req_no_figs = PDFParseRequest(
        file_url="https://storage.example/x.pdf",
        tenant_id="t-1",
        extract_figures=False,
    )
    await MineruCloudAdapter(tenant_config).parse(req_no_figs)
    assert session.last_submit_json["extract_images"] is False


# ── Auth / config errors (permanent) ─────────────────────────────────


@pytest.mark.asyncio
async def test_missing_api_key_raises_config_error(monkeypatch, req):
    cfg = SimpleNamespace(
        get_mineru_api_key=lambda: "",
        mineru_base_url="",
    )
    session = _FakeSession(submit_resp=_submit_ok(), poll_resps=[])
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicConfigError) as exc:
        await MineruCloudAdapter(cfg).parse(req)
    assert "api_key required" in str(exc.value)


@pytest.mark.asyncio
async def test_submit_401_raises_config_error(monkeypatch, tenant_config, req):
    session = _FakeSession(
        submit_resp=_FakeResp(status=401, body='{"error":"bad key"}'),
        poll_resps=[],
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicConfigError):
        await MineruCloudAdapter(tenant_config).parse(req)


@pytest.mark.asyncio
async def test_submit_403_raises_config_error(monkeypatch, tenant_config, req):
    session = _FakeSession(
        submit_resp=_FakeResp(status=403, body='{"error":"forbidden"}'),
        poll_resps=[],
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicConfigError):
        await MineruCloudAdapter(tenant_config).parse(req)


# ── Transient errors (provider) ──────────────────────────────────────


@pytest.mark.asyncio
async def test_submit_429_raises_provider_error(monkeypatch, tenant_config, req):
    session = _FakeSession(
        submit_resp=_FakeResp(status=429, body='{"error":"rate"}'),
        poll_resps=[],
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await MineruCloudAdapter(tenant_config).parse(req)
    assert "429" in str(exc.value)


@pytest.mark.asyncio
async def test_submit_5xx_raises_provider_error(monkeypatch, tenant_config, req):
    session = _FakeSession(
        submit_resp=_FakeResp(status=503, body="unavailable"),
        poll_resps=[],
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError):
        await MineruCloudAdapter(tenant_config).parse(req)


@pytest.mark.asyncio
async def test_network_error_raises_provider_error(monkeypatch, tenant_config, req):
    class _FailingSession(_FakeSession):
        def post(self, *a, **kw):
            raise _FakeClientError("DNS failure")

    _install_fake_aiohttp(
        monkeypatch,
        session=_FailingSession(submit_resp=_FakeResp(), poll_resps=[]),
    )
    with pytest.raises(MaicProviderError) as exc:
        await MineruCloudAdapter(tenant_config).parse(req)
    assert "network error" in str(exc.value).lower()


# ── Polling failures ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_polling_failed_state(monkeypatch, tenant_config, req):
    session = _FakeSession(
        submit_resp=_submit_ok(),
        poll_resps=[_poll("failed", err_msg="document corrupted")],
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await MineruCloudAdapter(tenant_config).parse(req)
    assert "failed" in str(exc.value).lower()
    assert "corrupted" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_polling_unrecognized_state(monkeypatch, tenant_config, req):
    """Mineru emits a state we don't know → fail loud, don't spin."""
    session = _FakeSession(
        submit_resp=_submit_ok(),
        poll_resps=[_poll("aliens_landed")],
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await MineruCloudAdapter(tenant_config).parse(req)
    assert "unrecognized" in str(exc.value).lower()
    assert "aliens_landed" in str(exc.value)


@pytest.mark.asyncio
async def test_polling_deadline_exhausted(monkeypatch, tenant_config, req):
    """Mineru never reaches a terminal state — adapter bails at deadline."""
    class _TinyDeadline(MineruCloudAdapter):
        _poll_interval_seconds = 0.001
        _poll_timeout_seconds = 0.05  # 50ms

    session = _FakeSession(
        submit_resp=_submit_ok(),
        poll_resps=[_poll("running")] * 500,  # never terminal
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await _TinyDeadline(tenant_config).parse(req)
    assert "deadline" in str(exc.value).lower()
    # Sanity: we tried polling many times but bounded
    assert session.poll_index < 500


# ── Response-shape errors ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_submit_missing_task_id(monkeypatch, tenant_config, req):
    session = _FakeSession(
        submit_resp=_FakeResp(status=200, body=json.dumps({"data": {}})),
        poll_resps=[],
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await MineruCloudAdapter(tenant_config).parse(req)
    assert "task_id" in str(exc.value)


@pytest.mark.asyncio
async def test_submit_malformed_json(monkeypatch, tenant_config, req):
    session = _FakeSession(
        submit_resp=_FakeResp(status=200, body="not-json{{{"),
        poll_resps=[],
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await MineruCloudAdapter(tenant_config).parse(req)
    assert "malformed" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_poll_missing_state(monkeypatch, tenant_config, req):
    session = _FakeSession(
        submit_resp=_submit_ok(),
        poll_resps=[_FakeResp(status=200, body=json.dumps({"data": {}}))],
    )
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicProviderError) as exc:
        await MineruCloudAdapter(tenant_config).parse(req)
    assert "state" in str(exc.value).lower()


# ── Document shaping (handles partial / missing fields gracefully) ───


@pytest.mark.asyncio
async def test_empty_payload_still_produces_valid_document(monkeypatch, tenant_config, req):
    """A scan-only PDF with no sections / figures / pages still parses
    to a valid (empty-list) document — total_pages defaults to 1."""
    session = _FakeSession(
        submit_resp=_submit_ok(),
        poll_resps=[_poll_done_with_payload()],
    )
    _install_fake_aiohttp(monkeypatch, session)
    result = await MineruCloudAdapter(tenant_config).parse(req)
    assert result.document.total_pages == 1
    assert result.document.sections == []
    assert result.document.figures == []
    assert result.document.pages == []


@pytest.mark.asyncio
async def test_skips_section_without_title(monkeypatch, tenant_config, req):
    """Mineru sometimes returns sections it couldn't extract a title
    for — these are useless downstream; skip them."""
    session = _FakeSession(
        submit_resp=_submit_ok(),
        poll_resps=[_poll_done_with_payload(
            total_pages=5,
            sections=[
                {"title": "", "level": 1, "page_start": 1, "page_end": 1},  # skip
                {"title": "Real Title", "level": 1, "page_start": 2, "page_end": 3},
            ],
        )],
    )
    _install_fake_aiohttp(monkeypatch, session)
    result = await MineruCloudAdapter(tenant_config).parse(req)
    assert len(result.document.sections) == 1
    assert result.document.sections[0].title == "Real Title"


@pytest.mark.asyncio
async def test_clamps_section_level_to_valid_range(monkeypatch, tenant_config, req):
    """Mineru returns level=12 (some over-eager heading detector) →
    clamped to max 6."""
    session = _FakeSession(
        submit_resp=_submit_ok(),
        poll_resps=[_poll_done_with_payload(
            total_pages=1,
            sections=[
                {"title": "T", "level": 12, "page_start": 1, "page_end": 1},
            ],
        )],
    )
    _install_fake_aiohttp(monkeypatch, session)
    result = await MineruCloudAdapter(tenant_config).parse(req)
    assert result.document.sections[0].level == 6


@pytest.mark.asyncio
async def test_handles_non_dict_section_entries(monkeypatch, tenant_config, req):
    """Defensive — malformed payload (string instead of dict) is skipped."""
    session = _FakeSession(
        submit_resp=_submit_ok(),
        poll_resps=[_poll_done_with_payload(
            total_pages=1,
            sections=["not-a-dict", None, {"title": "OK", "level": 1,
                                            "page_start": 1, "page_end": 1}],
        )],
    )
    _install_fake_aiohttp(monkeypatch, session)
    result = await MineruCloudAdapter(tenant_config).parse(req)
    assert len(result.document.sections) == 1
    assert result.document.sections[0].title == "OK"


# ── SSRF / base URL ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_localhost_base_url_rejected_by_ssrf_guard(monkeypatch, req):
    cfg = SimpleNamespace(
        get_mineru_api_key=lambda: "mr-x",
        mineru_base_url="http://127.0.0.1:8080/api/v4",
    )
    session = _FakeSession(submit_resp=_submit_ok(), poll_resps=[])
    _install_fake_aiohttp(monkeypatch, session)
    with pytest.raises(MaicConfigError) as exc:
        await MineruCloudAdapter(cfg).parse(req)
    msg = str(exc.value).lower()
    assert "ssrf" in msg or "base_url" in msg


@pytest.mark.asyncio
async def test_default_base_url_skips_ssrf_check(monkeypatch, tenant_config, req):
    """Default URL is well-known public; we shouldn't do a DNS round
    trip per request."""
    session = _FakeSession(
        submit_resp=_submit_ok(),
        poll_resps=[_poll_done_with_payload(total_pages=1)],
    )
    _install_fake_aiohttp(monkeypatch, session)
    result = await MineruCloudAdapter(tenant_config).parse(req)
    assert result.state.value == "done"


# ── Registry registration ─────────────────────────────────────────────


def test_mineru_is_registered_on_import():
    from apps.maic.pdf.providers import _REGISTRY
    assert "mineru" in _REGISTRY
    assert _REGISTRY["mineru"] is MineruCloudAdapter


# ── Live smoke (gated) ────────────────────────────────────────────────


@pytest.mark.skipif(
    os.environ.get("MAIC_MINERU_LIVE_SMOKE") != "1"
    or not os.environ.get("MINERU_API_KEY"),
    reason=(
        "live Mineru smoke disabled — set MAIC_MINERU_LIVE_SMOKE=1 + "
        "MINERU_API_KEY=<real-key> to enable. Costs depend on Mineru "
        "Cloud account tier (typically $0.005-$0.05 per page)."
    ),
)
@pytest.mark.asyncio
async def test_live_smoke_real_mineru_call():
    """Hits the real Mineru Cloud API. Uses a small public PDF URL."""
    cfg = SimpleNamespace(
        get_mineru_api_key=lambda: os.environ["MINERU_API_KEY"],
        mineru_base_url="",
    )
    req = PDFParseRequest(
        # Small public test PDF — Mineru itself provides one for smoke tests
        file_url="https://cdn-mineru.openxlab.org.cn/extract/demo.pdf",
        tenant_id="live-smoke",
        page_limit=3,
    )
    result = await MineruCloudAdapter(cfg).parse(req)
    assert result.state.value == "done"
    assert result.document.total_pages >= 1
