"""Tests for apps.maic.views — POST /api/maic/v2/sessions/ (MAIC-301).

Uses APIRequestFactory + force_authenticate to bypass the
@pytest.mark.django_db full test-DB build (which is currently blocked
on a pre-existing repo migration issue — see MAIC-002 cert).  Mocks
the model-layer interactions so we can test the view logic in isolation.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.maic.views import MaicSessionCreateView, _is_valid_session_id


@pytest.fixture(autouse=True)
def _enable_maic_v2(settings):
    settings.MAIC_V2_ENABLED = True


# ── _is_valid_session_id ──────────────────────────────────────────────


@pytest.mark.parametrize("session_id,expected", [
    ("a", True),
    ("ABC_def-123", True),
    ("x" * 64, True),
    ("x" * 65, False),
    ("", False),
    ("has space", False),
    ("has/slash", False),
    ("has.dot", False),
    ("with-mixed_chars-123_OK", True),
])
def test_session_id_regex_matches_route_pattern(session_id, expected):
    """Mirror of [\\w-]{1,64} regex in apps/maic/routing.py.  Validation
    must agree with the WS route's path regex — otherwise frontend can
    create a session via HTTP that the WS later refuses to open."""
    assert _is_valid_session_id(session_id) == expected


# ── POST /api/maic/v2/sessions/ ───────────────────────────────────────


def _make_request_with_user(*, tenant_id=222, body=None, tenant_flag=True):
    factory = APIRequestFactory()
    request = factory.post(
        "/api/maic/v2/sessions/",
        body or {},
        format="json",
        HTTP_HOST="testserver",
    )
    # DRF throttling reads request.user.pk; SimpleNamespace mirrors User
    # well enough for non-DB code paths.  is_authenticated as a property
    # equivalent (not a method) — DRF reads it as a value.
    user = SimpleNamespace(
        id=42,
        pk=42,
        tenant_id=tenant_id,
        tenant=(
            SimpleNamespace(id=tenant_id, is_active=True, feature_maic_v2=tenant_flag)
            if tenant_id is not None
            else None
        ),
        is_authenticated=True,
        is_active=True,
    )
    force_authenticate(request, user=user)
    return request


def test_session_create_requires_tenant():
    request = _make_request_with_user(tenant_id=None)
    response = MaicSessionCreateView.as_view()(request)
    assert response.status_code == 403


def test_session_create_403_when_tenant_v2_flag_off():
    request = _make_request_with_user(tenant_flag=False)
    response = MaicSessionCreateView.as_view()(request)
    assert response.status_code == 403


@patch("apps.maic.views.Tenant")
@patch("apps.maic.views.MaicSessionV2")
def test_session_create_mints_session_id_when_omitted(mock_session_model, mock_tenant_model):
    mock_tenant_model.objects.filter.return_value.first.return_value = SimpleNamespace(id=222)
    mock_session_model.objects.all_tenants.return_value.filter.return_value.first.return_value = None
    mock_session_model.objects.create.return_value = SimpleNamespace(
        id="s-deadbeef00000000000000000000",
        tenant_id=222,
        course_id=None,
    )

    request = _make_request_with_user()
    response = MaicSessionCreateView.as_view()(request)

    assert response.status_code == 201
    assert response.data["sessionId"].startswith("s-")
    assert response.data["wsUrl"].endswith(f"/ws/maic/v2/classroom/{response.data['sessionId']}/")
    assert response.data["created"] is True


@patch("apps.maic.views.Tenant")
@patch("apps.maic.views.MaicSessionV2")
def test_session_create_uses_caller_session_id(mock_session_model, mock_tenant_model):
    mock_tenant_model.objects.filter.return_value.first.return_value = SimpleNamespace(id=222)
    mock_session_model.objects.all_tenants.return_value.filter.return_value.first.return_value = None
    mock_session_model.objects.create.return_value = SimpleNamespace(
        id="my-custom-id_123",
        tenant_id=222,
        course_id=None,
    )

    request = _make_request_with_user(body={"session_id": "my-custom-id_123"})
    response = MaicSessionCreateView.as_view()(request)
    assert response.status_code == 201
    assert response.data["sessionId"] == "my-custom-id_123"


def test_session_create_rejects_invalid_session_id():
    request = _make_request_with_user(body={"session_id": "has space"})
    response = MaicSessionCreateView.as_view()(request)
    assert response.status_code == 400
    assert "session_id" in response.data["error"]


@patch("apps.maic.views.Tenant")
@patch("apps.maic.views.MaicSessionV2")
def test_session_create_returns_existing_when_session_id_already_exists(
    mock_session_model, mock_tenant_model,
):
    """Same-tenant + existing session_id → 200 OK with the existing
    row (idempotent for clients that retry on flaky network)."""
    mock_tenant_model.objects.filter.return_value.first.return_value = SimpleNamespace(id=222)
    existing = SimpleNamespace(id="reuse-me", tenant_id=222, course_id=None)
    mock_session_model.objects.all_tenants.return_value.filter.return_value.first.return_value = existing

    request = _make_request_with_user(body={"session_id": "reuse-me"})
    response = MaicSessionCreateView.as_view()(request)

    assert response.status_code == 200
    assert response.data["sessionId"] == "reuse-me"
    assert response.data["created"] is False
    # MUST NOT create a new row
    mock_session_model.objects.create.assert_not_called()


@patch("apps.maic.views.Tenant")
@patch("apps.maic.views.MaicSessionV2")
def test_session_create_409_on_cross_tenant_session_id_collision(
    mock_session_model, mock_tenant_model,
):
    """Same session_id, DIFFERENT tenant exists → 409 Conflict + audit log.
    Defends against an attacker enumerating session_ids from other tenants."""
    mock_tenant_model.objects.filter.return_value.first.return_value = SimpleNamespace(id=222)
    foreign = SimpleNamespace(id="contested", tenant_id=999, course_id=None)  # different tenant
    mock_session_model.objects.all_tenants.return_value.filter.return_value.first.return_value = foreign

    request = _make_request_with_user(body={"session_id": "contested"})
    response = MaicSessionCreateView.as_view()(request)

    assert response.status_code == 409
    assert "different tenant" in response.data["error"]
    mock_session_model.objects.create.assert_not_called()


@patch("apps.maic.views.Tenant")
def test_session_create_400_when_user_tenant_deleted(mock_tenant_model):
    """Edge: user.tenant_id refers to a deleted Tenant row.  The view
    rejects with 400 rather than crashing on a None tenant."""
    mock_tenant_model.objects.filter.return_value.first.return_value = None
    request = _make_request_with_user(tenant_id=222)
    response = MaicSessionCreateView.as_view()(request)
    assert response.status_code == 400
    assert "deleted" in response.data["error"]


@patch("apps.maic.views.Course")
def test_session_create_404_when_course_not_found_in_tenant(mock_course_model):
    """Optional course_id binding: missing → 404 (TenantManager filtered
    it out so the FK target isn't visible in this tenant)."""
    mock_course_model.objects.filter.return_value.first.return_value = None
    request = _make_request_with_user(body={"course_id": "9999"})
    response = MaicSessionCreateView.as_view()(request)
    assert response.status_code == 404
    assert "course" in response.data["error"]


def test_session_create_anonymous_returns_401():
    """No force_authenticate → IsAuthenticated permission denies."""
    factory = APIRequestFactory()
    request = factory.post("/api/maic/v2/sessions/", {}, format="json")
    response = MaicSessionCreateView.as_view()(request)
    assert response.status_code in (401, 403)
