"""Focused tests for the MAIC v2 quiz-grade runtime gap."""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.courses.maic_models import TenantAIConfig
from apps.maic.runtime_gap_quiz import normalize_quiz_grade_payload
from apps.tenants.models import Tenant


@pytest.fixture(autouse=True)
def _enable_maic_v2(settings):
    settings.MAIC_V2_ENABLED = True
    settings.SECURE_SSL_REDIRECT = False


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(
        name="Quiz Gap School",
        slug="quiz-gap",
        subdomain="quiz-gap",
        email="admin@quiz-gap.test",
        feature_maic=True,
        feature_maic_v2=True,
    )


@pytest.fixture
def ai_config(db, tenant):
    return TenantAIConfig.objects.create(
        tenant=tenant,
        maic_enabled=True,
        llm_provider="openrouter",
        llm_model="openai/gpt-4o-mini",
    )


@pytest.fixture
def user(db, tenant):
    User = get_user_model()
    return User.objects.create_user(
        email="teacher@quiz-gap.test",
        password="x",
        first_name="Quiz",
        last_name="Teacher",
        tenant=tenant,
        role="TEACHER",
    )


@pytest.fixture
def client(user, tenant):
    api_client = APIClient()
    api_client.force_authenticate(user=user)
    api_client.defaults["HTTP_HOST"] = f"{tenant.subdomain}.learnpuddle.test"
    return api_client


def test_quiz_grade_accepts_openmaic_payload_and_scales_to_points(
    db,
    client,
    ai_config,
):
    response = client.post(
        "/api/maic/v2/quiz-grade/",
        data={
            "question": "What is the capital of France?",
            "userAnswer": "Paris",
            "expectedAnswer": "Paris",
            "points": 5,
        },
        format="json",
    )

    assert response.status_code == 200, response.data
    assert response.data["score"] == 5
    assert response.data["scorePercent"] == 100
    assert response.data["isCorrect"] is True
    assert response.data["comment"] == response.data["feedback"]


def test_quiz_grade_accepts_legacy_payload_without_points(
    db,
    client,
    ai_config,
):
    response = client.post(
        "/api/maic/v2/quiz/grade/",
        data={
            "question": "photosynthesis",
            "answer": "Photosynthesis",
        },
        format="json",
    )

    assert response.status_code == 200, response.data
    assert response.data["score"] == 100
    assert response.data["points"] == 100
    assert response.data["feedback"] == "Correct! Great job."


def test_quiz_grade_requires_v2_tenant_flag(db, client, tenant, ai_config):
    tenant.feature_maic_v2 = False
    tenant.save(update_fields=["feature_maic_v2"])

    response = client.post(
        "/api/maic/v2/quiz-grade/",
        data={"question": "Q", "userAnswer": "A"},
        format="json",
    )

    assert response.status_code == 403


def test_quiz_grade_requires_ai_classroom_config_enabled(db, client, ai_config):
    ai_config.maic_enabled = False
    ai_config.save(update_fields=["maic_enabled"])

    response = client.post(
        "/api/maic/v2/quiz-grade/",
        data={"question": "Q", "userAnswer": "A"},
        format="json",
    )

    assert response.status_code == 403
    assert "disabled" in response.data["error"]


@pytest.mark.parametrize(
    "body,error",
    [
        ({}, "question"),
        ({"question": "Q"}, "userAnswer"),
        ({"question": "Q", "userAnswer": "A", "points": 0}, "points"),
        ({"question": "Q", "userAnswer": "A", "points": "many"}, "points"),
    ],
)
def test_normalize_quiz_grade_payload_rejects_bad_input(body, error):
    payload, response = normalize_quiz_grade_payload(body)

    assert payload is None
    assert response is not None
    assert response.status_code == 400
    assert error in response.data["error"]
