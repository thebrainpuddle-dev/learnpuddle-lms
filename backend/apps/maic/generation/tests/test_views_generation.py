"""Tests for `apps.maic.views_generation` (MAIC-428.4).

Covers payload validation, tenant scoping, row creation, chain
enqueueing (mocked at the queue boundary so we don't drag a real
Celery worker into the test).
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model

from apps.maic.models import MaicGenerationJob
from apps.courses.maic_models import TenantAIConfig
from apps.courses.models import Course, Module
from apps.tenants.models import Tenant


@pytest.fixture(autouse=True)
def _enable_maic_v2(settings):
    settings.MAIC_V2_ENABLED = True
    settings.MAIC_V2_ALLOW_STUB = False
    settings.MAIC_V2_ALLOW_REQUEST_MODEL_OVERRIDE = False


@pytest.fixture
def tenant(db):
    tenant = Tenant.objects.create(
        name="test-tenant",
        slug="test-tenant",
        feature_maic_v2=True,
    )
    cfg = TenantAIConfig.objects.create(
        tenant=tenant,
        maic_enabled=True,
        llm_provider="openrouter",
        llm_model="openai/gpt-4o-mini",
    )
    cfg.set_llm_api_key("test-openrouter-key")
    cfg.save(update_fields=["llm_api_key_encrypted"])
    return tenant


@pytest.fixture
def user(db, tenant):
    User = get_user_model()
    user = User.objects.create_user(email="test@example.com", password="x")
    user.tenant_id = tenant.id
    user.save(update_fields=["tenant_id"])
    return user


@pytest.fixture
def student_user(db, tenant):
    User = get_user_model()
    user = User.objects.create_user(
        email="student@example.com",
        password="x",
        role="STUDENT",
    )
    user.tenant_id = tenant.id
    user.save(update_fields=["tenant_id"])
    return user


@pytest.fixture
def authed_client(user):
    from rest_framework.test import APIClient
    client = APIClient()
    client.force_authenticate(user=user)
    return client


# ── Payload validation ────────────────────────────────────────────


def test_post_requires_topic(db, authed_client):
    res = authed_client.post(
        "/api/maic/v2/generate/", data={}, format="json"
    )
    assert res.status_code == 400
    assert "topic" in res.data["error"]


def test_post_rejects_blank_topic(db, authed_client):
    res = authed_client.post(
        "/api/maic/v2/generate/", data={"topic": "   "}, format="json"
    )
    assert res.status_code == 400


def test_post_rejects_invalid_agent_count(db, authed_client):
    for bad in [0, 11, "four", -1]:
        res = authed_client.post(
            "/api/maic/v2/generate/",
            data={"topic": "T", "agentCount": bad},
            format="json",
        )
        assert res.status_code == 400, f"agentCount={bad!r} should reject"


def test_post_rejects_blank_language(db, authed_client):
    res = authed_client.post(
        "/api/maic/v2/generate/",
        data={"topic": "T", "language": ""},
        format="json",
    )
    assert res.status_code == 400


def test_post_rejects_non_string_specifications(db, authed_client):
    res = authed_client.post(
        "/api/maic/v2/generate/",
        data={"topic": "T", "specifications": 123},
        format="json",
    )
    assert res.status_code == 400


def test_post_rejects_invalid_scene_count(db, authed_client):
    for bad in [0, 21, "six", True]:
        res = authed_client.post(
            "/api/maic/v2/generate/",
            data={"topic": "T", "sceneCount": bad},
            format="json",
        )
        assert res.status_code == 400, f"sceneCount={bad!r} should reject"


def test_post_rejects_invalid_teacher_context_fields(db, authed_client):
    res = authed_client.post(
        "/api/maic/v2/generate/",
        data={"topic": "T", "classGuide": {"bad": "shape"}},
        format="json",
    )
    assert res.status_code == 400
    assert "classGuide" in res.data["error"]


# ── Auth + tenant scoping ─────────────────────────────────────────


def test_unauthenticated_request_rejected(db):
    from rest_framework.test import APIClient
    client = APIClient()
    res = client.post("/api/maic/v2/generate/", data={"topic": "T"}, format="json")
    assert res.status_code in (401, 403)


def test_user_with_no_tenant_rejected(db):
    from rest_framework.test import APIClient
    User = get_user_model()
    user = User.objects.create_user(email="notenant@example.com", password="x")
    # tenant_id stays None
    client = APIClient()
    client.force_authenticate(user=user)
    res = client.post(
        "/api/maic/v2/generate/", data={"topic": "T"}, format="json"
    )
    assert res.status_code == 403


def test_tenant_v2_flag_off_rejected(db, user, tenant):
    from rest_framework.test import APIClient

    tenant.feature_maic_v2 = False
    tenant.save(update_fields=["feature_maic_v2"])
    client = APIClient()
    client.force_authenticate(user=user)

    res = client.post(
        "/api/maic/v2/generate/", data={"topic": "T"}, format="json"
    )
    assert res.status_code == 403
    assert "tenant" in str(res.data.get("error") or res.data.get("detail")).lower()


def test_global_v2_gate_off_reports_deployment_reason(db, user, settings):
    from rest_framework.test import APIClient

    settings.MAIC_V2_ENABLED = False
    client = APIClient()
    client.force_authenticate(user=user)

    res = client.post(
        "/api/maic/v2/generate/", data={"topic": "T"}, format="json"
    )

    assert res.status_code == 403
    assert "deployment" in str(res.data.get("error") or res.data.get("detail")).lower()


# ── Happy path: row inserted + chain enqueued ─────────────────────


def test_post_inserts_row_and_returns_job_id(db, authed_client, tenant, user):
    """Happy path. We patch enqueue_generation_chain so the test
    doesn't need a Celery worker — the row insert + 202 response
    semantics are what's under test here."""
    with patch(
        "apps.maic.generation.tasks.enqueue_generation_chain"
    ) as enqueue:
        res = authed_client.post(
            "/api/maic/v2/generate/",
            data={
                "topic": "Numerator and Denominator",
                "agentCount": 4,
                "language": "English",
                "level": "beginner",
            },
            format="json",
        )

    assert res.status_code == 202, f"got {res.status_code}: {res.data}"
    assert "job_id" in res.data
    assert "ws_url" in res.data
    assert res.data["tenant_id"] == tenant.id
    assert res.data["ws_url"].endswith(f"/ws/maic/generation/{res.data['job_id']}/")

    # Row exists, scoped to the user's tenant.
    saved = MaicGenerationJob.objects.all_tenants().get(pk=res.data["job_id"])
    assert saved.tenant_id == tenant.id
    assert saved.created_by_id == user.id
    assert saved.status == MaicGenerationJob.STATUS_PENDING
    assert saved.requirements["topic"] == "Numerator and Denominator"
    assert saved.requirements["agentCount"] == 4

    # Chain was enqueued with the row's id.
    enqueue.assert_called_once_with(saved.id)


def test_post_accepts_valid_lms_targets(db, authed_client, tenant, user):
    course = Course.objects.create(
        tenant=tenant,
        title="Biology",
        description="Biology course",
        created_by=user,
    )
    module = Module.objects.create(course=course, title="Cells", order=1)

    with patch(
        "apps.maic.generation.tasks.enqueue_generation_chain"
    ):
        res = authed_client.post(
            "/api/maic/v2/generate/",
            data={
                "topic": "Cell division",
                "courseId": str(course.id),
                "moduleId": str(module.id),
                "contentTitle": "Mitosis classroom",
                "isPublic": True,
            },
            format="json",
        )

    assert res.status_code == 202, f"got {res.status_code}: {res.data}"
    saved = MaicGenerationJob.objects.all_tenants().get(pk=res.data["job_id"])
    assert saved.requirements["courseId"] == str(course.id)
    assert saved.requirements["moduleId"] == str(module.id)
    assert saved.requirements["contentTitle"] == "Mitosis classroom"
    assert saved.requirements["isPublic"] is True


def test_student_cannot_attach_v2_generation_to_lms_course(db, tenant, user, student_user):
    from rest_framework.test import APIClient

    course = Course.objects.create(
        tenant=tenant,
        title="Biology",
        description="Biology course",
        created_by=user,
    )
    module = Module.objects.create(course=course, title="Cells", order=1)
    client = APIClient()
    client.force_authenticate(user=student_user)

    res = client.post(
        "/api/maic/v2/generate/",
        data={
            "topic": "Cell division",
            "courseId": str(course.id),
            "moduleId": str(module.id),
        },
        format="json",
    )

    assert res.status_code == 403
    assert "students cannot attach" in res.data["error"]


def test_student_cannot_publish_v2_generation(db, student_user):
    from rest_framework.test import APIClient

    client = APIClient()
    client.force_authenticate(user=student_user)

    res = client.post(
        "/api/maic/v2/generate/",
        data={"topic": "Algebra review", "isPublic": True},
        format="json",
    )

    assert res.status_code == 403
    assert "students cannot publish" in res.data["error"]


def test_post_stores_class_guide_and_v2_pbl_context(
    db, authed_client, tenant
):
    agents = [
        {
            "id": "agent-1",
            "name": "Asha",
            "role": "student",
            "avatar": "A",
            "color": "#123456",
        }
    ]

    with patch(
        "apps.maic.generation.tasks.enqueue_generation_chain"
    ):
        res = authed_client.post(
            "/api/maic/v2/generate/",
            data={
                "topic": "  Photosynthesis  ",
                "agentCount": 1,
                "sceneCount": 6,
                "language": "en",
                "level": "Grade 6",
                "gradeLevel": "Grade 6",
                "subject": "Science",
                "syllabusBoard": "CBSE",
                "classGuide": "Open with a plant mystery and include a misconception check.",
                "pdfText": "Teacher notes from class guide PDF.",
                "researchContext": "Recent source: leaf starch demo.",
                "agents": agents,
                "enablePBL": True,
                "enableImageGeneration": True,
            },
            format="json",
        )

    assert res.status_code == 202, f"got {res.status_code}: {res.data}"
    saved = MaicGenerationJob.objects.all_tenants().get(pk=res.data["job_id"])
    req = saved.requirements
    assert req["topic"] == "Photosynthesis"
    assert req["requirement"].startswith("Topic: Photosynthesis")
    assert "Create exactly 6 scenes" in req["requirement"]
    assert "project-based learning" in req["requirement"]
    assert req["sceneCount"] == 6
    assert req["language"] == "en"
    assert req["languageLabel"] == "English"
    assert req["gradeLevel"] == "Grade 6"
    assert req["subject"] == "Science"
    assert req["syllabusBoard"] == "CBSE"
    assert req["classGuide"].startswith("Open with a plant mystery")
    assert "Teacher Class Guide" in req["teacherContext"]
    assert req["pdfText"].startswith("Teacher notes")
    assert req["researchContext"].startswith("Recent source")
    assert req["agents"] == agents
    assert req["enablePBL"] is True
    assert req["enableImageGeneration"] is True


def test_post_rejects_cross_tenant_lms_target(db, authed_client, user):
    other = Tenant.objects.create(
        name="other",
        slug="other",
        subdomain="other",
        feature_maic_v2=True,
    )
    course = Course.objects.create(
        tenant=other,
        title="Other Course",
        description="Nope",
        created_by=user,
    )
    module = Module.objects.create(course=course, title="Other Module", order=1)

    res = authed_client.post(
        "/api/maic/v2/generate/",
        data={"topic": "T", "moduleId": str(module.id)},
        format="json",
    )

    assert res.status_code == 400
    assert "moduleId" in res.data["error"]


def test_post_uses_defaults_when_optional_fields_omitted(db, authed_client):
    with patch(
        "apps.maic.generation.tasks.enqueue_generation_chain"
    ):
        res = authed_client.post(
            "/api/maic/v2/generate/",
            data={"topic": "Just a topic"},
            format="json",
        )
    assert res.status_code == 202
    saved = MaicGenerationJob.objects.all_tenants().get(pk=res.data["job_id"])
    assert saved.requirements["agentCount"] == 4
    assert saved.requirements["language"] == "English"
    assert saved.requirements["level"] == "intermediate"
    assert saved.requirements["specifications"] == ""
    assert saved.requirements["languageModelId"] == "openrouter/openai/gpt-4o-mini"
    assert saved.requirements["enableImageGeneration"] is True


def test_post_defaults_image_generation_off_when_tenant_provider_disabled(
    db,
    authed_client,
    tenant,
):
    tenant.ai_config.image_provider = "disabled"
    tenant.ai_config.save(update_fields=["image_provider"])

    with patch(
        "apps.maic.generation.tasks.enqueue_generation_chain"
    ):
        res = authed_client.post(
            "/api/maic/v2/generate/",
            data={"topic": "Just a topic"},
            format="json",
        )

    assert res.status_code == 202
    saved = MaicGenerationJob.objects.all_tenants().get(pk=res.data["job_id"])
    assert saved.requirements["enableImageGeneration"] is False


def test_post_records_no_pbl_requirement_when_disabled(db, authed_client):
    with patch(
        "apps.maic.generation.tasks.enqueue_generation_chain"
    ):
        res = authed_client.post(
            "/api/maic/v2/generate/",
            data={"topic": "Lab safety", "enablePBL": False},
            format="json",
        )

    assert res.status_code == 202
    saved = MaicGenerationJob.objects.all_tenants().get(pk=res.data["job_id"])
    assert saved.requirements["enablePBL"] is False
    assert "Do not include project-based learning scenes" in saved.requirements["requirement"]


def test_post_rejects_stub_language_model_in_production(db, authed_client):
    res = authed_client.post(
        "/api/maic/v2/generate/",
        data={"topic": "T", "languageModelId": "stub"},
        format="json",
    )
    assert res.status_code == 400
    assert "stub" in res.data["error"]


def test_post_rejects_model_override_in_production(db, authed_client):
    res = authed_client.post(
        "/api/maic/v2/generate/",
        data={"topic": "T", "languageModelId": "openrouter/anthropic/claude-3.5-sonnet"},
        format="json",
    )
    assert res.status_code == 400
    assert "TenantAIConfig" in res.data["error"]


def test_post_rejects_missing_tenant_llm_key(db, authed_client, tenant):
    cfg = tenant.ai_config
    cfg.llm_api_key_encrypted = ""
    cfg.save(update_fields=["llm_api_key_encrypted"])

    res = authed_client.post(
        "/api/maic/v2/generate/",
        data={"topic": "T"},
        format="json",
    )

    assert res.status_code == 400
    assert "llm_api_key" in res.data["error"]


def test_post_returns_503_when_broker_unavailable(db, authed_client):
    """If enqueue raises (broker down), the row is still inserted but
    the response is 503. This lets the client retry without leaking a
    half-state job (a janitor task can later pick the pending row
    up — Phase 5+)."""
    with patch(
        "apps.maic.generation.tasks.enqueue_generation_chain",
        side_effect=ConnectionError("redis down"),
    ):
        res = authed_client.post(
            "/api/maic/v2/generate/",
            data={"topic": "T"},
            format="json",
        )
    assert res.status_code == 503
    # Row should still be inserted in the pending state.
    rows = MaicGenerationJob.objects.all_tenants().filter(
        requirements__topic="T"
    )
    assert rows.count() == 1
    assert rows[0].status == MaicGenerationJob.STATUS_PENDING


def test_ws_url_uses_request_host(db, authed_client):
    """Sanity: the ws_url echoes the request host so multi-environment
    deployments (dev / staging / prod) Just Work."""
    with patch(
        "apps.maic.generation.tasks.enqueue_generation_chain"
    ):
        res = authed_client.post(
            "/api/maic/v2/generate/",
            data={"topic": "T"},
            format="json",
            HTTP_HOST="example.test",
        )
    assert res.status_code == 202
    assert res.data["ws_url"].startswith("ws://example.test/ws/maic/generation/")


def test_get_generation_job_poll_response_strips_heavy_result(
    db, authed_client, tenant, user
):
    job = MaicGenerationJob.objects.create(
        id="jobpoll1",
        tenant=tenant,
        created_by=user,
        requirements={"topic": "T"},
        status=MaicGenerationJob.STATUS_SUCCEEDED,
        progress={
            "stage": 3,
            "completed": 1,
            "total": 1,
            "message": "Generation complete!",
        },
        result={
            "scenes": [{"id": "s1"}],
            "outlines": [{"title": "S1"}],
            "classroomId": "classroom-1",
            "url": "/teacher/ai-classroom/classroom-1",
            "scenesCount": 1,
        },
    )

    res = authed_client.get(f"/api/maic/v2/generate/{job.id}/")

    assert res.status_code == 200
    assert res.data["done"] is True
    assert res.data["scenesGenerated"] == 1
    assert res.data["result"]["classroomId"] == "classroom-1"
    assert "scenes" not in res.data["result"]
    assert "outlines" not in res.data["result"]
