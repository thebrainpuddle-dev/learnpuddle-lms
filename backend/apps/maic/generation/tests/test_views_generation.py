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
from apps.tenants.models import Tenant


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="test-tenant", slug="test-tenant")


@pytest.fixture
def user(db, tenant):
    User = get_user_model()
    user = User.objects.create_user(email="test@example.com", password="x")
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
    assert res.status_code == 400
    assert "tenant" in res.data["error"].lower()


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
    assert saved.requirements["languageModelId"] == "stub"


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
