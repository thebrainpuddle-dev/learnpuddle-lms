"""Tests for the PBLProjectCreateView (MAIC-704).

Validation tests use Django's APIClient — exercise the real HTTP
boundary including DRF auth + serializer + view dispatch. The
design loop itself is exercised through monkeypatched
generate_pbl_project so we don't need a real LLM here (covered by
tests_design_graph.py with the _ScriptedChatModel fake).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.maic_pbl.design_graph import GeneratePBLResult
from apps.maic_pbl.models import MaicPBLSession


def _make_tenant(slug: str = "t-views"):
    from apps.tenants.models import Tenant
    return Tenant.objects.create(
        name=slug.upper(), slug=slug, subdomain=slug, is_active=True,
    )


def _make_user_with_tenant(slug: str = "t-views"):
    from apps.users.models import User
    t = _make_tenant(slug)
    return User.objects.create(
        email=f"{slug}@dev.local", tenant=t, is_active=True, first_name="T",
    ), t


def _client_for(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


@pytest.mark.django_db
def test_anonymous_returns_401():
    """No auth → 401 from DRF before our view runs."""
    c = APIClient()
    res = c.post("/api/maic/v2/pbl/projects/", data={"topic": "X"}, format="json")
    assert res.status_code == 401


@pytest.mark.django_db
def test_user_with_no_tenant_returns_400():
    from apps.users.models import User
    u = User.objects.create(email="orphan@dev.local", is_active=True, first_name="X")
    res = _client_for(u).post(
        "/api/maic/v2/pbl/projects/", data={"topic": "X", "languageModelId": "claude-x"},
        format="json",
    )
    assert res.status_code == 400
    assert "tenant" in res.json().get("error", "")


@pytest.mark.django_db
def test_missing_topic_returns_400():
    u, _ = _make_user_with_tenant("t-mt")
    res = _client_for(u).post("/api/maic/v2/pbl/projects/", data={}, format="json")
    assert res.status_code == 400
    assert "topic" in res.json().get("error", "")


@pytest.mark.django_db
def test_blank_topic_returns_400():
    u, _ = _make_user_with_tenant("t-bt")
    res = _client_for(u).post(
        "/api/maic/v2/pbl/projects/", data={"topic": "   "}, format="json",
    )
    assert res.status_code == 400


@pytest.mark.django_db
def test_invalid_issue_count_returns_400():
    u, _ = _make_user_with_tenant("t-ic")
    res = _client_for(u).post(
        "/api/maic/v2/pbl/projects/",
        data={"topic": "X", "issueCount": 100},
        format="json",
    )
    assert res.status_code == 400
    assert "issueCount" in res.json().get("error", "")


@pytest.mark.django_db
def test_non_string_target_skills_returns_400():
    u, _ = _make_user_with_tenant("t-ts")
    res = _client_for(u).post(
        "/api/maic/v2/pbl/projects/",
        data={"topic": "X", "targetSkills": [1, 2, 3]},
        format="json",
    )
    assert res.status_code == 400


@pytest.mark.django_db
def test_stub_language_model_id_rejected_in_production():
    """The 'stub' model id is for design-graph unit tests, NOT
    production. The view rejects it so a stale frontend can't drive
    a hung loop in a real classroom."""
    u, _ = _make_user_with_tenant("t-stub")
    res = _client_for(u).post(
        "/api/maic/v2/pbl/projects/",
        data={"topic": "X", "languageModelId": "stub"},
        format="json",
    )
    assert res.status_code == 400
    assert "stub" in res.json().get("error", "").lower()


@pytest.mark.django_db
def test_unknown_model_id_returns_400():
    u, _ = _make_user_with_tenant("t-unk")
    res = _client_for(u).post(
        "/api/maic/v2/pbl/projects/",
        data={"topic": "X", "languageModelId": "made-up-model"},
        format="json",
    )
    assert res.status_code == 400


@pytest.mark.django_db
def test_happy_path_creates_session_and_returns_ws_url():
    """End-to-end: valid POST creates an ACTIVE MaicPBLSession,
    returns ws_url, persists project_config from the design loop."""
    u, t = _make_user_with_tenant("t-happy")

    fake_config = {
        "projectInfo": {"title": "Built by fake", "description": "d"},
        "agents": [{
            "name": "Dev", "actor_role": "x", "role_division": "development",
            "system_prompt": "p", "default_mode": "chat", "delay_time": 0,
            "env": {}, "is_user_role": True, "is_active": True,
            "is_system_agent": False,
        }],
        "issueboard": {"agent_ids": ["Dev"], "issues": [], "current_issue_id": None},
        "chat": {"messages": []},
        "selectedRole": None,
    }

    async def _fake_generate(_cfg, _model, *, on_progress=None):
        return GeneratePBLResult(
            project_config=fake_config,
            steps_taken=5,
            reached_idle=True,
            welcome_message_generated=False,
            error=None,
            schema_valid=True,
        )

    # Patch at the IMPORT site (apps.maic_pbl.views imported the symbol)
    # and the model resolver (we don't want to hit Anthropic's API in a
    # unit test — IO-boundary fake, acceptable per the no-mocks rule).
    with patch("apps.maic_pbl.views.generate_pbl_project", _fake_generate), \
         patch("apps.maic.orchestration.ai_adapter.resolve_chat_model",
               return_value=object()):
        res = _client_for(u).post(
            "/api/maic/v2/pbl/projects/",
            data={
                "topic": "Fractions",
                "languageModelId": "claude-x",
                "issueCount": 2,
            },
            format="json",
        )

    assert res.status_code == 201, res.json()
    body = res.json()
    assert "session_id" in body
    assert body["ws_url"].endswith(f"/ws/maic/pbl/{body['session_id']}/")
    assert body["status"] == "active"
    assert body["reached_idle"] is True
    assert body["schema_valid"] is True

    # Persisted row reflects the loop's output
    sess = MaicPBLSession.objects.all_tenants().get(id=body["session_id"])
    assert sess.tenant_id == t.id
    assert sess.owner_id == u.id
    assert sess.status == MaicPBLSession.STATUS_ACTIVE
    assert sess.project_config["projectInfo"]["title"] == "Built by fake"


@pytest.mark.django_db
def test_design_loop_error_persists_failed_status():
    """When the design loop returns an error, the row goes to FAILED
    status with error_message populated — admin can replay later."""
    u, _ = _make_user_with_tenant("t-fail")

    async def _fake_generate(_cfg, _model, *, on_progress=None):
        return GeneratePBLResult(
            project_config={"projectInfo": {"title": "", "description": ""},
                            "agents": [],
                            "issueboard": {"agent_ids": [], "issues": [], "current_issue_id": None},
                            "chat": {"messages": []}},
            steps_taken=2,
            reached_idle=False,
            welcome_message_generated=False,
            error="loop hit step ceiling",
            schema_valid=True,
        )

    with patch("apps.maic_pbl.views.generate_pbl_project", _fake_generate), \
         patch("apps.maic.orchestration.ai_adapter.resolve_chat_model",
               return_value=object()):
        res = _client_for(u).post(
            "/api/maic/v2/pbl/projects/",
            data={"topic": "X", "languageModelId": "claude-x"},
            format="json",
        )

    assert res.status_code == 201
    body = res.json()
    assert body["status"] == "failed"
    sess = MaicPBLSession.objects.all_tenants().get(id=body["session_id"])
    assert sess.status == MaicPBLSession.STATUS_FAILED
    assert "loop hit step ceiling" in sess.error_message


@pytest.mark.django_db
def test_design_loop_crash_500s_with_session_id():
    """An uncaught exception → 500 + the session row stays as FAILED
    so the admin can find it via session_id in the response."""
    u, _ = _make_user_with_tenant("t-crash")

    async def _fake_crash(*_a, **_kw):
        raise RuntimeError("simulated catastrophe")

    with patch("apps.maic_pbl.views.generate_pbl_project", _fake_crash), \
         patch("apps.maic.orchestration.ai_adapter.resolve_chat_model",
               return_value=object()):
        res = _client_for(u).post(
            "/api/maic/v2/pbl/projects/",
            data={"topic": "X", "languageModelId": "claude-x"},
            format="json",
        )

    assert res.status_code == 500
    body = res.json()
    assert "session_id" in body
    sess = MaicPBLSession.objects.all_tenants().get(id=body["session_id"])
    assert sess.status == MaicPBLSession.STATUS_FAILED
    assert "catastrophe" in sess.error_message


@pytest.mark.django_db
def test_language_directive_built_from_iso_code():
    """Verify the language → directive mapping. Empty for en/en-US/
    en-GB; explicit instruction for non-English codes."""
    from apps.maic_pbl.views import _build_language_directive
    assert _build_language_directive("en") == ""
    assert _build_language_directive("en-US") == ""
    assert _build_language_directive("EN-GB") == ""
    assert "es" in _build_language_directive("es")
    assert "ja" in _build_language_directive("ja")
