"""Tests for MaicPBLSession (MAIC-700).

Pure model + manager tests — no LLM, no graph, no API surface.
Validates the lifecycle skeleton (status enum, JSONField defaults,
tenant isolation via TenantManager, indexes via Meta).

These run with @pytest.mark.django_db so they hit a real Postgres
test DB. The cert-sqlite path doesn't apply here — Phase 7 is
Postgres-only for runserver/daphne (Phase 5 cert decision).
"""
from __future__ import annotations

import uuid

import pytest

from apps.maic_pbl.models import MaicPBLSession


def _make_tenant(slug: str = "t-a"):
    """Create a minimal Tenant row directly. Avoids importing fixtures
    that would pull in unrelated app setup."""
    from apps.tenants.models import Tenant
    return Tenant.objects.create(
        name=slug.upper(),
        slug=slug,
        subdomain=slug,
        is_active=True,
    )


def _make_user(tenant, email: str):
    from apps.users.models import User
    return User.objects.create(
        email=email,
        tenant=tenant,
        is_active=True,
        first_name="T",
        last_name="User",
    )


@pytest.mark.django_db
def test_session_defaults_to_draft_status_and_empty_blobs():
    t = _make_tenant("t-defaults")
    s = MaicPBLSession.objects.create(tenant=t, topic="fractions")
    assert s.status == "draft"
    assert s.project_config == {}
    assert s.chat_messages == []
    assert s.error_message == ""
    assert s.language == "en"
    assert s.agent_count == 4
    assert isinstance(s.id, uuid.UUID)


@pytest.mark.django_db
def test_status_transitions_through_lifecycle():
    """All five lifecycle states are valid; transitions are caller-
    enforced (no model-level state machine, intentional Phase 7 scope —
    Phase 8 polish may add a state machine if abuse cases emerge)."""
    t = _make_tenant("t-lifecycle")
    s = MaicPBLSession.objects.create(tenant=t)

    for state in ("draft", "active", "completed", "failed", "archived"):
        s.status = state
        s.save()
        s.refresh_from_db()
        assert s.status == state


def test_owner_fk_declared_as_set_null():
    """Sessions must survive teacher account deletion. The owner FK
    is declared SET_NULL so a hard-deleted user (or admin teardown)
    doesn't take down their PBL sessions.

    Tested as a static field-config assertion rather than via
    `u.delete()` because Django's User in this codebase implements
    soft-delete via TenantManager — `delete()` flips `is_deleted=True`
    but leaves the row + FKs intact. The FK `on_delete` policy still
    matters: it kicks in when an admin runs a hard delete (e.g. via
    `User.objects.all_tenants().filter(...).hard_delete()` or DB-level
    cleanup)."""
    from django.db.models.deletion import SET_NULL

    field = MaicPBLSession._meta.get_field("owner")
    assert field.remote_field.on_delete is SET_NULL
    assert field.null is True
    assert field.blank is True


def test_tenant_fk_declared_as_cascade():
    """Tenant teardown wipes the tenant's PBL sessions. CASCADE FK is
    the cornerstone of multi-tenant cleanup."""
    from django.db.models.deletion import CASCADE

    field = MaicPBLSession._meta.get_field("tenant")
    assert field.remote_field.on_delete is CASCADE
    assert field.null is False


@pytest.mark.django_db
def test_tenant_manager_isolates_querysets():
    """TenantManager — the cornerstone of multi-tenant security.
    Queries on .objects scope to current tenant via thread-local
    middleware; cross-tenant rows are invisible."""
    from utils.tenant_middleware import set_current_tenant

    a = _make_tenant("t-iso-a")
    b = _make_tenant("t-iso-b")
    MaicPBLSession.objects.create(tenant=a, topic="A's")
    MaicPBLSession.objects.create(tenant=b, topic="B's")

    set_current_tenant(a)
    try:
        rows = list(MaicPBLSession.objects.all())
        assert len(rows) == 1
        assert rows[0].topic == "A's"
    finally:
        set_current_tenant(None)

    # all_tenants() bypass for explicit cross-tenant queries (used by
    # admin tools + the consumer's cross-tenant cross-check; cf.
    # apps.maic.consumers._resolve_or_create_session).
    assert MaicPBLSession.objects.all_tenants().count() == 2


@pytest.mark.django_db
def test_json_blob_persists_nested_pbl_project_config_shape():
    """Project config can be the full upstream shape — agents,
    issueboard, chat — and round-trips through JSONField cleanly."""
    t = _make_tenant("t-json")
    config = {
        "projectInfo": {
            "title": "Fraction Calculator",
            "description": "Build a CLI fraction calculator.",
        },
        "agents": [
            {
                "name": "Question",
                "actor_role": "tutor",
                "role_division": "system",
                "system_prompt": "Ask probing questions.",
                "default_mode": "idle",
                "is_user_role": False,
                "is_active": True,
                "is_system_agent": True,
            },
        ],
        "issueboard": {
            "agent_ids": ["agent-1"],
            "issues": [
                {
                    "id": "issue-1",
                    "title": "Define API",
                    "is_done": False,
                    "is_active": True,
                    "index": 0,
                },
            ],
            "current_issue_id": "issue-1",
        },
        "chat": {"messages": []},
        "selectedRole": None,
    }
    s = MaicPBLSession.objects.create(
        tenant=t, project_config=config, status="active"
    )
    s.refresh_from_db()
    # Deep equality preserved by JSONField
    assert s.project_config["projectInfo"]["title"] == "Fraction Calculator"
    assert s.project_config["issueboard"]["issues"][0]["title"] == "Define API"
    assert s.project_config["agents"][0]["is_system_agent"] is True


@pytest.mark.django_db
def test_chat_messages_blob_appends():
    """chat_messages is the append-only log; mutations replace the
    whole list (JSONField doesn't support partial JSONB ops in our
    abstraction). Phase 7's chat consumer pattern: load → append →
    save. Concurrent writers are out of scope (single owner per
    session per upstream model)."""
    t = _make_tenant("t-chat")
    s = MaicPBLSession.objects.create(tenant=t, status="active")
    s.chat_messages.append(
        {"id": "m1", "agent_name": "Question", "message": "Hi"}
    )
    s.save()
    s.refresh_from_db()
    assert len(s.chat_messages) == 1
    assert s.chat_messages[0]["agent_name"] == "Question"


@pytest.mark.django_db
def test_str_repr_includes_id_and_tenant_and_status():
    t = _make_tenant("t-repr")
    s = MaicPBLSession.objects.create(tenant=t)
    text = str(s)
    assert "MaicPBLSession" in text
    assert str(s.id) in text
    assert str(t.id) in text
    assert "draft" in text


@pytest.mark.django_db
def test_indexes_present_in_meta():
    """Compile-time check that the two query-shape-driving indexes
    are declared. Index names are the auto-generated suffixes from
    migrations 0001_initial — keeping them stable across runs is a
    Phase 7 invariant."""
    meta = MaicPBLSession._meta
    declared_index_fields = sorted(tuple(idx.fields) for idx in meta.indexes)
    assert ("tenant", "owner", "-created_at") in declared_index_fields
    assert ("tenant", "status", "-created_at") in declared_index_fields
