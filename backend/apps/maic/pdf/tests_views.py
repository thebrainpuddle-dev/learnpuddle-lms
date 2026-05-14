"""Tests for MAIC v2 PDF parse HTTP endpoint.

The view tests keep the real Django/DRF/auth/Pydantic/provider path in play.
Only the provider's outbound aiohttp boundary is replaced with a tiny fake,
matching the repo rule that network IO is the acceptable test-double seam.
"""
from __future__ import annotations

import json
import sys
import types

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient


PDF_PARSE_URL = "/api/maic/v2/pdf/parse/"


class _FakeResp:
    def __init__(self, *, status: int = 200, body: str = ""):
        self.status = status
        self._body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def text(self) -> str:
        return self._body


class _FakeSession:
    def __init__(self, *, submit_resp: _FakeResp, poll_resps: list[_FakeResp]):
        self._submit_resp = submit_resp
        self._poll_resps = poll_resps
        self.poll_index = 0
        self.last_submit_url: str | None = None
        self.last_submit_json: dict | None = None
        self.last_poll_url: str | None = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def post(self, url, json=None, headers=None):
        self.last_submit_url = url
        self.last_submit_json = json
        return self._submit_resp

    def get(self, url, headers=None):
        self.last_poll_url = url
        if self.poll_index >= len(self._poll_resps):
            raise AssertionError("fake MinerU poll responses exhausted")
        resp = self._poll_resps[self.poll_index]
        self.poll_index += 1
        return resp


class _FakeClientError(Exception):
    pass


def _install_fake_aiohttp(monkeypatch, session: _FakeSession) -> _FakeSession:
    fake = types.ModuleType("aiohttp")
    fake.ClientSession = lambda: session  # type: ignore[attr-defined]
    fake.ClientError = _FakeClientError  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "aiohttp", fake)
    return session


def _submit_ok(task_id: str = "pdf-task-1") -> _FakeResp:
    return _FakeResp(
        status=200,
        body=json.dumps({"data": {"task_id": task_id}}),
    )


def _poll_done(**fields) -> _FakeResp:
    return _FakeResp(
        status=200,
        body=json.dumps({"data": {"state": "done", **fields}}),
    )


def _make_pdf(name: str = "chapter.pdf") -> SimpleUploadedFile:
    return SimpleUploadedFile(
        name,
        b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n",
        content_type="application/pdf",
    )


@pytest.fixture(autouse=True)
def _enable_maic_v2(settings, tmp_path):
    settings.MAIC_V2_ENABLED = True
    settings.SECURE_SSL_REDIRECT = False
    settings.MEDIA_ROOT = tmp_path


@pytest.fixture
def tenant(db):
    from apps.tenants.models import Tenant

    return Tenant.objects.create(
        name="PDF Tenant",
        slug="pdf-tenant",
        subdomain="pdf-tenant",
        email="pdf@example.test",
        is_active=True,
        feature_maic_v2=True,
    )


@pytest.fixture
def tenant_config(db, tenant):
    from apps.courses.maic_models import TenantAIConfig

    cfg = TenantAIConfig.objects.create(tenant=tenant, pdf_provider="mineru")
    cfg.set_mineru_api_key("mr-test-key")
    cfg.save()
    return cfg


@pytest.fixture
def user(db, tenant):
    from apps.users.models import User

    return User.objects.create_user(
        email="teacher-pdf@example.test",
        password="x",
        first_name="Teacher",
        last_name="PDF",
        tenant=tenant,
        role="TEACHER",
        is_active=True,
    )


@pytest.fixture
def authed_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _mineru_success_session(monkeypatch) -> _FakeSession:
    session = _FakeSession(
        submit_resp=_submit_ok("doc-success"),
        poll_resps=[
            _poll_done(
                total_pages=3,
                title="Fractions",
                sections=[
                    {
                        "id": "sec-1",
                        "title": "Numerators",
                        "level": 1,
                        "text": "A numerator counts selected parts.",
                        "page_start": 1,
                        "page_end": 2,
                    }
                ],
                figures=[
                    {"id": "fig-1", "caption": "Fraction bar", "page": 2},
                ],
                pages=[
                    {"page_number": 1, "text": "Fractions page text"},
                ],
            )
        ],
    )
    return _install_fake_aiohttp(monkeypatch, session)


# -- Auth / tenant gating -------------------------------------------------


@pytest.mark.django_db
def test_parse_pdf_anonymous_returns_401():
    res = APIClient().post(PDF_PARSE_URL, data={"file_url": "https://93.184.216.34/a.pdf"})
    assert res.status_code == 401


@pytest.mark.django_db
def test_parse_pdf_403_when_tenant_flag_off(authed_client, tenant):
    tenant.feature_maic_v2 = False
    tenant.save(update_fields=["feature_maic_v2"])

    res = authed_client.post(
        PDF_PARSE_URL,
        data={"file_url": "https://93.184.216.34/a.pdf"},
        format="json",
    )

    assert res.status_code == 403


@pytest.mark.django_db
def test_parse_pdf_400_when_tenant_has_no_ai_config(db, settings):
    from apps.tenants.models import Tenant
    from apps.users.models import User

    tenant = Tenant.objects.create(
        name="No Config",
        slug="pdf-no-config",
        subdomain="pdf-no-config",
        email="nocfg@example.test",
        is_active=True,
        feature_maic_v2=True,
    )
    user = User.objects.create_user(
        email="nocfg-pdf@example.test",
        password="x",
        first_name="No",
        last_name="Config",
        tenant=tenant,
        role="TEACHER",
        is_active=True,
    )
    client = APIClient()
    client.force_authenticate(user=user)

    res = client.post(
        PDF_PARSE_URL,
        data={"file_url": "https://93.184.216.34/a.pdf"},
        format="json",
    )

    assert res.status_code == 400
    assert "TenantAIConfig" in res.json()["error"]


# -- Validation -----------------------------------------------------------


@pytest.mark.django_db
def test_parse_pdf_requires_exactly_one_input(authed_client, tenant_config):
    missing = authed_client.post(PDF_PARSE_URL, data={}, format="json")
    assert missing.status_code == 400

    both = authed_client.post(
        PDF_PARSE_URL,
        data={"file_url": "https://93.184.216.34/a.pdf", "file": _make_pdf()},
        format="multipart",
    )
    assert both.status_code == 400


@pytest.mark.django_db
def test_parse_pdf_rejects_non_pdf_upload(authed_client, tenant_config):
    txt = SimpleUploadedFile("notes.txt", b"hello", content_type="text/plain")

    res = authed_client.post(PDF_PARSE_URL, data={"file": txt}, format="multipart")

    assert res.status_code == 400
    assert "pdf" in res.json()["error"].lower()


@pytest.mark.django_db
def test_parse_pdf_rejects_private_file_url(authed_client, tenant_config):
    res = authed_client.post(
        PDF_PARSE_URL,
        data={"file_url": "http://127.0.0.1:8000/private.pdf"},
        format="json",
    )

    assert res.status_code == 400
    assert "ssrf" in res.json()["error"].lower()


# -- Happy paths ----------------------------------------------------------


@pytest.mark.django_db
def test_parse_pdf_url_201_returns_parse_result(authed_client, tenant_config, monkeypatch):
    session = _mineru_success_session(monkeypatch)

    res = authed_client.post(
        PDF_PARSE_URL,
        data={
            "file_url": "https://93.184.216.34/textbook.pdf",
            "page_limit": 3,
            "extract_figures": False,
        },
        format="json",
    )

    assert res.status_code == 201, res.json()
    body = res.json()
    assert body["document_id"] == "doc-success"
    assert body["state"] == "done"
    assert body["document"]["title"] == "Fractions"
    assert body["document"]["sections"][0]["title"] == "Numerators"
    assert body["document"]["figures"][0]["caption"] == "Fraction bar"
    assert session.last_submit_json["url"] == "https://93.184.216.34/textbook.pdf"
    assert session.last_submit_json["page_limit"] == 3
    assert session.last_submit_json["extract_images"] is False


@pytest.mark.django_db
def test_parse_pdf_upload_201_uses_server_tenant_path(
    authed_client,
    tenant_config,
    tenant,
    monkeypatch,
):
    session = _mineru_success_session(monkeypatch)

    res = authed_client.post(
        PDF_PARSE_URL,
        data={"file": _make_pdf(), "tenant_id": "spoofed-tenant"},
        format="multipart",
        HTTP_HOST="testserver",
    )

    assert res.status_code == 201, res.json()
    submitted_url = session.last_submit_json["url"]
    assert f"/course_content/tenant/{tenant.id}/ai_studio/pdf/" in submitted_url
    assert "spoofed-tenant" not in submitted_url


# -- Error matrix ---------------------------------------------------------


@pytest.mark.django_db
def test_parse_pdf_400_when_pdf_provider_disabled(authed_client, tenant_config):
    tenant_config.pdf_provider = "disabled"
    tenant_config.save(update_fields=["pdf_provider"])

    res = authed_client.post(
        PDF_PARSE_URL,
        data={"file_url": "https://93.184.216.34/a.pdf"},
        format="json",
    )

    assert res.status_code == 400
    assert "disabled" in res.json()["error"].lower()


@pytest.mark.django_db
def test_parse_pdf_502_when_provider_fails(authed_client, tenant_config, monkeypatch):
    session = _FakeSession(
        submit_resp=_FakeResp(status=503, body="upstream unavailable"),
        poll_resps=[],
    )
    _install_fake_aiohttp(monkeypatch, session)

    res = authed_client.post(
        PDF_PARSE_URL,
        data={"file_url": "https://93.184.216.34/a.pdf"},
        format="json",
    )

    assert res.status_code == 502
    assert "provider failed" in res.json()["error"].lower()
    assert "503" in res.json()["detail"]


def test_parse_pdf_url_resolves():
    from django.urls import reverse

    assert reverse("api:maic_pdf:parse") == PDF_PARSE_URL
