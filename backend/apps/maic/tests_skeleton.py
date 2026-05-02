"""Phase 0 sanity tests for the apps.maic skeleton.

These tests guard against silent app-loading failures: that the app is
registered, that tenant scoping is wired correctly on the new model, and
that the orchestration / prompts / protocol packages are reachable.
"""
from __future__ import annotations

import pytest
from django.apps import apps

from apps.maic.models import MaicSessionV2
from utils.tenant_manager import TenantManager


def test_app_registered():
    """apps.maic must appear in the Django app registry under label 'maic'."""
    cfg = apps.get_app_config("maic")
    assert cfg.name == "apps.maic"
    assert cfg.verbose_name == "AI Classroom (MAIC v2)"


def test_orchestration_package_importable():
    """Lazy-import smoke for the package the LangGraph director_graph lives in."""
    from apps.maic import orchestration  # noqa: F401
    from apps.maic.orchestration import state  # noqa: F401


def test_prompts_package_importable():
    """Phase 1 will populate this; Phase 0 just checks reachability."""
    from apps.maic import prompts  # noqa: F401


def test_protocol_package_importable():
    """Phase 1 will define Pydantic action types here."""
    from apps.maic import protocol  # noqa: F401


def test_session_model_uses_tenant_manager():
    """MaicSessionV2 must auto-filter by current tenant — non-negotiable.

    Cross-tenant access is the most common silent regression on a
    multi-tenant model; this asserts the manager is the tenant-aware
    one, not Django's default Manager.
    """
    assert isinstance(MaicSessionV2.objects, TenantManager)


def test_session_model_meta():
    """Stable db_table + verbose_names — these are referenced in admin and
    in the migration; renames must be deliberate."""
    meta = MaicSessionV2._meta
    assert meta.db_table == "maic_session_v2"
    assert meta.verbose_name == "MAIC v2 session"


def test_session_model_instantiates_in_memory():
    """In-memory instantiation only (no DB).  Phase-0 coverage focuses on
    config + manager wiring; a DB-touching FK test would require pytest-django
    to build the test DB, which currently fails on a pre-existing repo
    migration issue (NewCourseSkipRequest.teacher field referenced in an
    older migration but no longer on the model — outside MAIC v2 scope per
    the V1 freeze).  When that repo issue lands a fix, upgrade this test to
    `@pytest.mark.django_db` and exercise `MaicSessionV2.objects.create(...)`
    against a real Tenant row.
    """
    s = MaicSessionV2(id="s-skel-1")
    assert s.id == "s-skel-1"
    # FK columns exist on the instance even without a saved relation
    assert hasattr(s, "tenant_id")
    assert hasattr(s, "course_id")
    assert hasattr(s, "opened_by_id")
