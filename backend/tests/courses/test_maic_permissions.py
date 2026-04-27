"""Permission tests for the MAIC classroom endpoints.

Verifies that:
- Students can hit /api/v1/student/maic/chat/ and receive either a streamed
  response (200) or a sidecar-unavailable fallback (502). Either status means
  the permission layer let the request through.
- Students hitting the teacher-only endpoint /api/v1/teacher/maic/chat/ are
  rejected with 403 by the `@teacher_or_admin` decorator.
- Director turn endpoints (P3.1 port) enforce the same role boundaries:
    * Teacher endpoint → TEACHER/SCHOOL_ADMIN allowed; STUDENT rejected (403)
    * Student endpoint → STUDENT/SCHOOL_ADMIN allowed; TEACHER rejected (403)
- Unauthenticated requests to MAIC endpoints get 401/403 (no token → no access).
- When the MAIC feature flag is disabled on the tenant, all MAIC endpoints
  return 403 with `upgrade_required` in the response.
"""
import json
from unittest import mock

import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Local fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def student_user(db, tenant):
    """A STUDENT user belonging to the primary test tenant.

    The root conftest does not ship a student fixture, so we build one here.
    """
    from apps.users.models import User
    return User.objects.create_user(
        email="student@testschool.com",
        password="StudentPass!123",
        first_name="Student",
        last_name="User",
        tenant=tenant,
        role="STUDENT",
        is_active=True,
    )


@pytest.fixture
def ai_config(tenant):
    """MAIC-enabled TenantAIConfig + tenant feature flag so the chat views
    don't short-circuit at the `@check_feature('feature_maic')` guard."""
    from apps.courses.maic_models import TenantAIConfig
    tenant.feature_maic = True
    tenant.save(update_fields=["feature_maic"])
    return TenantAIConfig.objects.create(
        tenant=tenant,
        llm_provider="openrouter",
        llm_model="openai/gpt-4o-mini",
        tts_provider="disabled",
        maic_enabled=True,
    )


@pytest.fixture
def student_client(student_user, tenant):
    client = APIClient()
    client.force_authenticate(user=student_user)
    client.defaults["HTTP_HOST"] = f"{tenant.subdomain}.lms.com"
    return client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_student_chat_succeeds(student_client, ai_config):
    """A student hitting the student chat endpoint is let through the
    permission layer. The response may be 200 (streamed) or 502 (sidecar
    unavailable with fallback); either is acceptable — we only care that
    it is *not* a 403/404."""
    response = student_client.post(
        "/api/v1/student/maic/chat/",
        {"message": "Hi", "classroomId": None},
        format="json",
    )
    assert response.status_code in (200, 502), (
        f"Expected 200 or 502, got {response.status_code}: "
        f"{response.content[:200]!r}"
    )


def test_teacher_endpoint_rejects_student(student_client, ai_config):
    """A student MUST NOT be able to reach the teacher chat endpoint."""
    response = student_client.post(
        "/api/v1/teacher/maic/chat/",
        {"message": "Hi"},
        format="json",
    )
    assert response.status_code == 403
    assert "Teacher or admin" in response.content.decode()


# ---------------------------------------------------------------------------
# Director turn endpoint permission tests (P3.1 porting — BE-SEC-002 scope)
# ---------------------------------------------------------------------------

# The director_next_turn LLM call is mocked in all director turn tests so we
# do not need a real API key or network access. We only want to verify the
# permission layer (auth, role decorators, feature flag).

_DIRECTOR_MOCK_RESULT = {"next_speaker_id": "agent-1", "reasoning": "Test."}


@pytest.fixture
def teacher_client(teacher_user, tenant):
    """DRF APIClient pre-authenticated as the teacher user."""
    client = APIClient()
    client.force_authenticate(user=teacher_user)
    client.defaults["HTTP_HOST"] = f"{tenant.subdomain}.lms.com"
    return client


@pytest.fixture
def admin_client_for_maic(admin_user, tenant):
    """DRF APIClient pre-authenticated as the school admin."""
    client = APIClient()
    client.force_authenticate(user=admin_user)
    client.defaults["HTTP_HOST"] = f"{tenant.subdomain}.lms.com"
    return client


@pytest.fixture
def ai_config_maic_disabled(tenant):
    """TenantAIConfig with MAIC *disabled* — feature_maic=False."""
    from apps.courses.maic_models import TenantAIConfig
    tenant.feature_maic = False
    tenant.save(update_fields=["feature_maic"])
    return TenantAIConfig.objects.create(
        tenant=tenant,
        llm_provider="openrouter",
        llm_model="openai/gpt-4o-mini",
        tts_provider="disabled",
        maic_enabled=False,
    )


def _post_director_turn(client, url):
    """POST a minimal director-turn body and return the response."""
    body = {
        "agents": [{"id": "agent-1", "name": "Alice"}],
        "transcript": [],
        "topic": "Math",
    }
    return client.post(url, data=json.dumps(body), content_type="application/json")


# --- Teacher director endpoint ---

def test_teacher_director_turn_allowed_for_teacher(teacher_client, ai_config):
    """A TEACHER user can reach the teacher director-turn endpoint.
    The director LLM call is mocked — we only test the permission layer."""
    with mock.patch(
        "apps.courses.maic_views.director_next_turn",
        return_value=_DIRECTOR_MOCK_RESULT,
    ):
        resp = _post_director_turn(teacher_client, "/api/v1/teacher/maic/director/turn/")
    # 200 (LLM responded) or 204 (LLM returned falsy) — never 403/401.
    assert resp.status_code in (200, 204), (
        f"Expected 200/204, got {resp.status_code}: {resp.content[:200]!r}"
    )


def test_teacher_director_turn_allowed_for_admin(admin_client_for_maic, ai_config):
    """A SCHOOL_ADMIN user is permitted through @teacher_or_admin."""
    with mock.patch(
        "apps.courses.maic_views.director_next_turn",
        return_value=_DIRECTOR_MOCK_RESULT,
    ):
        resp = _post_director_turn(admin_client_for_maic, "/api/v1/teacher/maic/director/turn/")
    assert resp.status_code in (200, 204)


def test_teacher_director_turn_forbidden_for_student(student_client, ai_config):
    """A STUDENT user MUST be rejected (403) from the teacher director endpoint."""
    with mock.patch(
        "apps.courses.maic_views.director_next_turn",
        return_value=_DIRECTOR_MOCK_RESULT,
    ):
        resp = _post_director_turn(student_client, "/api/v1/teacher/maic/director/turn/")
    assert resp.status_code == 403
    body = resp.content.decode()
    assert "Teacher or admin" in body or "permission" in body.lower() or "403" in body


def test_teacher_director_turn_requires_authentication(tenant):
    """Unauthenticated request to teacher director endpoint returns 401/403."""
    anon = APIClient()
    anon.defaults["HTTP_HOST"] = f"{tenant.subdomain}.lms.com"
    resp = _post_director_turn(anon, "/api/v1/teacher/maic/director/turn/")
    assert resp.status_code in (401, 403)


def test_teacher_director_turn_returns_403_when_maic_disabled(
    teacher_client, ai_config_maic_disabled
):
    """MAIC feature disabled → 403 with upgrade_required flag."""
    resp = _post_director_turn(teacher_client, "/api/v1/teacher/maic/director/turn/")
    assert resp.status_code == 403
    body = resp.content.decode()
    assert "upgrade_required" in body or "feature" in body.lower()


# --- Student director endpoint ---

def test_student_director_turn_allowed_for_student(student_client, ai_config):
    """A STUDENT user can reach the student director-turn endpoint."""
    with mock.patch(
        "apps.courses.maic_views.director_next_turn",
        return_value=_DIRECTOR_MOCK_RESULT,
    ):
        resp = _post_director_turn(student_client, "/api/v1/student/maic/director/turn/")
    assert resp.status_code in (200, 204), (
        f"Expected 200/204, got {resp.status_code}: {resp.content[:200]!r}"
    )


def test_student_director_turn_allowed_for_admin(admin_client_for_maic, ai_config):
    """A SCHOOL_ADMIN user is allowed by @student_or_admin."""
    with mock.patch(
        "apps.courses.maic_views.director_next_turn",
        return_value=_DIRECTOR_MOCK_RESULT,
    ):
        resp = _post_director_turn(
            admin_client_for_maic, "/api/v1/student/maic/director/turn/"
        )
    assert resp.status_code in (200, 204)


def test_student_director_turn_forbidden_for_teacher(teacher_client, ai_config):
    """A TEACHER user MUST be rejected (403) from the student director endpoint.
    TEACHER is not in ['STUDENT', 'SCHOOL_ADMIN', 'SUPER_ADMIN']."""
    with mock.patch(
        "apps.courses.maic_views.director_next_turn",
        return_value=_DIRECTOR_MOCK_RESULT,
    ):
        resp = _post_director_turn(teacher_client, "/api/v1/student/maic/director/turn/")
    assert resp.status_code == 403


def test_student_director_turn_requires_authentication(tenant):
    """Unauthenticated request to student director endpoint returns 401/403."""
    anon = APIClient()
    anon.defaults["HTTP_HOST"] = f"{tenant.subdomain}.lms.com"
    resp = _post_director_turn(anon, "/api/v1/student/maic/director/turn/")
    assert resp.status_code in (401, 403)


def test_student_director_turn_returns_403_when_maic_disabled(
    student_client, ai_config_maic_disabled
):
    """MAIC feature disabled → 403 for student director turn too."""
    resp = _post_director_turn(student_client, "/api/v1/student/maic/director/turn/")
    assert resp.status_code == 403


def test_director_turn_llm_fallback_204_when_no_result(teacher_client, ai_config):
    """When director_next_turn returns a falsy value (LLM declined), the
    teacher endpoint responds 204 — clients fall back to round-robin."""
    with mock.patch(
        "apps.courses.maic_views.director_next_turn",
        return_value=None,
    ):
        resp = _post_director_turn(teacher_client, "/api/v1/teacher/maic/director/turn/")
    assert resp.status_code == 204
