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

from apps.courses.maic_models import TenantAIConfig
from apps.maic_pbl.design_graph import GeneratePBLResult
from apps.maic_pbl.models import MaicPBLSession


@pytest.fixture(autouse=True)
def _enable_maic_v2(settings):
    settings.MAIC_V2_ENABLED = True
    settings.MAIC_V2_ALLOW_STUB = False
    settings.MAIC_V2_ALLOW_REQUEST_MODEL_OVERRIDE = False


def _make_tenant(slug: str = "t-views", feature_maic_v2: bool = True):
    """Create a Tenant with the v2 flag ON by default — tests assume the
    tenant can reach v2 routes unless they explicitly opt out (the
    MAIC-800 gating tests do)."""
    from apps.tenants.models import Tenant
    tenant = Tenant.objects.create(
        name=slug.upper(), slug=slug, subdomain=slug, is_active=True,
        feature_maic_v2=feature_maic_v2,
    )
    cfg = TenantAIConfig.objects.create(
        tenant=tenant,
        maic_enabled=True,
        llm_provider="anthropic",
        llm_model="claude-sonnet-4-5-20250929",
    )
    cfg.set_llm_api_key("test-anthropic-key")
    cfg.save(update_fields=["llm_api_key_encrypted"])
    return tenant


def _make_user_with_tenant(slug: str = "t-views", feature_maic_v2: bool = True):
    from apps.users.models import User
    t = _make_tenant(slug, feature_maic_v2=feature_maic_v2)
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
def test_user_with_no_tenant_returns_403():
    """User with no tenant fails the MaicV2TenantPermission gate (MAIC-800)
    BEFORE the view-level tenant_id check fires. Result is 403 (Forbidden)
    rather than 400. The earlier-firing gate is more secure: it does not
    distinguish 'no tenant' from 'tenant flag off' to a probing client."""
    from apps.users.models import User
    u = User.objects.create(email="orphan@dev.local", is_active=True, first_name="X")
    res = _client_for(u).post(
        "/api/maic/v2/pbl/projects/", data={"topic": "X", "languageModelId": "claude-x"},
        format="json",
    )
    assert res.status_code == 403


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
            data={"topic": "X"},
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
            data={"topic": "X"},
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


# ── PBLProjectRetrieveView (MAIC-707) ─────────────────────────────────


def _seed_session(user, tenant, **overrides):
    """Create a real MaicPBLSession row for retrieve-view tests."""
    defaults = {
        "tenant_id": tenant.id,
        "owner_id": user.id,
        "topic": "Fractions",
        "language": "en",
        "agent_count": 3,
        "status": MaicPBLSession.STATUS_ACTIVE,
        "project_config": {
            "projectInfo": {"title": "Math Tutor", "description": "d"},
            "agents": [],
            "issueboard": {"agent_ids": [], "issues": [], "current_issue_id": None},
            "chat": {"messages": []},
        },
        "chat_messages": [],
    }
    defaults.update(overrides)
    return MaicPBLSession.objects.create(**defaults)


@pytest.mark.django_db
def test_retrieve_anonymous_returns_401():
    c = APIClient()
    res = c.get("/api/maic/v2/pbl/projects/00000000-0000-0000-0000-000000000000/")
    assert res.status_code == 401


@pytest.mark.django_db
def test_retrieve_no_tenant_returns_403():
    """Same as the create-view variant — MaicV2TenantPermission catches
    no-tenant users before the view-level check (MAIC-800)."""
    from apps.users.models import User
    u = User.objects.create(email="orphan@dev.local", is_active=True, first_name="X")
    res = _client_for(u).get(
        "/api/maic/v2/pbl/projects/00000000-0000-0000-0000-000000000000/"
    )
    assert res.status_code == 403


@pytest.mark.django_db
def test_retrieve_returns_session_payload():
    u, t = _make_user_with_tenant("t-ret-ok")
    sess = _seed_session(u, t)
    res = _client_for(u).get(f"/api/maic/v2/pbl/projects/{sess.id}/")
    assert res.status_code == 200
    body = res.json()
    assert body["session_id"] == str(sess.id)
    assert body["status"] == "active"
    assert body["topic"] == "Fractions"
    assert body["language"] == "en"
    assert body["project_config"]["projectInfo"]["title"] == "Math Tutor"
    assert body["chat_messages"] == []
    assert body["ws_url"].endswith(f"/ws/maic/pbl/{sess.id}/")


@pytest.mark.django_db
def test_retrieve_unknown_session_returns_404():
    u, _ = _make_user_with_tenant("t-ret-404")
    res = _client_for(u).get(
        "/api/maic/v2/pbl/projects/00000000-0000-0000-0000-000000000000/"
    )
    assert res.status_code == 404


@pytest.mark.django_db
def test_retrieve_cross_tenant_collapses_to_404():
    """A session belonging to tenant A cannot be read by user from
    tenant B — and the response must be 404, not 403, so an attacker
    cannot enumerate session ids by probing for permission errors."""
    u_a, t_a = _make_user_with_tenant("t-ret-a")
    sess = _seed_session(u_a, t_a)
    u_b, _ = _make_user_with_tenant("t-ret-b")
    res = _client_for(u_b).get(f"/api/maic/v2/pbl/projects/{sess.id}/")
    assert res.status_code == 404


# ── MAIC-800: per-tenant feature_maic_v2 gating ──────────────────────


@pytest.mark.django_db
def test_create_view_403_when_tenant_v2_flag_off():
    """Tenant exists, user authenticated, but tenant.feature_maic_v2 is
    False → DRF MaicV2TenantPermission returns False → 403. Distinct
    from 401 (anonymous) and 400 (no tenant)."""
    u, _ = _make_user_with_tenant("t-flag-off-create", feature_maic_v2=False)
    res = _client_for(u).post(
        "/api/maic/v2/pbl/projects/",
        data={"topic": "X", "languageModelId": "claude-x"},
        format="json",
    )
    assert res.status_code == 403


@pytest.mark.django_db
def test_create_view_403_when_global_gate_off(settings):
    """The deploy-level kill switch blocks even an enabled tenant."""
    settings.MAIC_V2_ENABLED = False
    u, _ = _make_user_with_tenant("t-global-off", feature_maic_v2=True)
    res = _client_for(u).post(
        "/api/maic/v2/pbl/projects/",
        data={"topic": "X", "languageModelId": "claude-x"},
        format="json",
    )
    assert res.status_code == 403


@pytest.mark.django_db
def test_retrieve_view_403_when_tenant_v2_flag_off():
    """Same gating on the retrieve endpoint — symmetric so the cleanup
    deletion doesn't accidentally leave one of the two endpoints open."""
    u, _ = _make_user_with_tenant("t-flag-off-retrieve", feature_maic_v2=False)
    res = _client_for(u).get(
        "/api/maic/v2/pbl/projects/00000000-0000-0000-0000-000000000000/"
    )
    assert res.status_code == 403


@pytest.mark.django_db
def test_create_view_passes_when_tenant_v2_flag_on():
    """Default fixture sets feature_maic_v2=True. A failed-validation
    request still returns 400 (not 403) — proves the v2 gate is permissive
    for an enabled tenant and the deeper validation runs."""
    u, _ = _make_user_with_tenant("t-flag-on")
    res = _client_for(u).post(
        "/api/maic/v2/pbl/projects/", data={}, format="json",
    )
    # Missing topic → 400 from validation, NOT 403 from the v2 gate.
    assert res.status_code == 400
    assert "topic" in res.json().get("error", "")


# ── MAIC-800: permission helpers themselves ─────────────────────────


def test_tenant_has_v2_access_helper_logic():
    """Helper returns False for None / inactive / unflagged; True for
    active+flagged. Pure unit test, no DB."""
    from types import SimpleNamespace
    from apps.maic.permissions import tenant_has_v2_access

    assert tenant_has_v2_access(None) is False
    assert tenant_has_v2_access(
        SimpleNamespace(is_active=False, feature_maic_v2=True)
    ) is False
    assert tenant_has_v2_access(
        SimpleNamespace(is_active=True, feature_maic_v2=False)
    ) is False
    assert tenant_has_v2_access(
        SimpleNamespace(is_active=True, feature_maic_v2=True)
    ) is True


def test_require_tenant_v2_raises_when_disabled():
    """The hard-fail variant raises MaicTenantError, used by WS consumers
    that need an exception path rather than a False return."""
    from types import SimpleNamespace
    from apps.maic.exceptions import MaicTenantError
    from apps.maic.permissions import require_tenant_v2

    with pytest.raises(MaicTenantError):
        require_tenant_v2(
            SimpleNamespace(is_active=True, feature_maic_v2=False)
        )
    # Should not raise when flag is on
    require_tenant_v2(
        SimpleNamespace(is_active=True, feature_maic_v2=True)
    )


def test_user_has_maic_v2_access_checks_global_gate(settings):
    """Combined helper requires both global env gate and tenant flag."""
    from types import SimpleNamespace
    from apps.maic.permissions import user_has_maic_v2_access

    user = SimpleNamespace(
        is_authenticated=True,
        tenant=SimpleNamespace(is_active=True, feature_maic_v2=True),
    )
    settings.MAIC_V2_ENABLED = False
    assert user_has_maic_v2_access(user) is False
    settings.MAIC_V2_ENABLED = True
    assert user_has_maic_v2_access(user) is True
