"""Permission tests for the MAIC classroom chat endpoints.

Verifies that:
- Students can hit /api/v1/student/maic/chat/ and receive either a streamed
  response (200) or a sidecar-unavailable fallback (502). Either status means
  the permission layer let the request through.
- Students hitting the teacher-only endpoint /api/v1/teacher/maic/chat/ are
  rejected with 403 by the `@teacher_or_admin` decorator.
"""
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
