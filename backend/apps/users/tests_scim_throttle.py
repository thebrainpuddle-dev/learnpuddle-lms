"""
Throttling tests for SCIM 2.0 endpoints (AUDIT-2026-04-26-PHASE3-5).

These tests assert that:
  - Unauthenticated SCIM requests are rate-limited per-IP at a strict rate
    (default 30/min) — protects against bearer-token guessing.
  - Authenticated SCIM requests are rate-limited per-token-hash at a high
    steady-state rate (default 600/min) — Okta/Azure can hit ~100/min.
  - Throttle scopes are shared between /Users and /Groups endpoints.
  - The rate is overridable through environment variables so ops can tune
    without a code change.

Implementation under test: throttle classes defined in
``apps/users/scim_throttles.py`` and applied to the SCIM Django views.
"""

from __future__ import annotations

import json
import uuid

import pytest
from django.core.cache import cache
from django.test import Client, override_settings

from apps.tenants.models import Tenant
from apps.users.models import User

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_tenant(subdomain: str = None) -> Tenant:
    subdomain = subdomain or uuid.uuid4().hex[:8]
    return Tenant.objects.create(
        name=f"School {subdomain}",
        slug=subdomain,
        subdomain=subdomain,
        email=f"admin@{subdomain}.test",
    )


def _make_admin(tenant: Tenant, email: str = None) -> User:
    email = email or f"admin-{uuid.uuid4().hex[:6]}@test.com"
    return User.objects.create_user(
        email=email,
        password="Password123!",
        first_name="Admin",
        last_name="User",
        tenant=tenant,
        role="SCHOOL_ADMIN",
    )


def _scim_token_for(tenant: Tenant, admin: User):
    from apps.users.scim_models import SCIMToken
    return SCIMToken.generate(tenant=tenant, name="Test IdP", created_by=admin)


@pytest.fixture(autouse=True)
def _flush_cache():
    """Throttles use the Django cache; flush before / after each test
    so counters from one test never leak into another."""
    cache.clear()
    yield
    cache.clear()


# ---------------------------------------------------------------------------
# 1. Unauthenticated burst — protects against token-guessing
# ---------------------------------------------------------------------------

@override_settings(
    REST_FRAMEWORK={
        "DEFAULT_THROTTLE_CLASSES": [
            "rest_framework.throttling.AnonRateThrottle",
            "rest_framework.throttling.UserRateThrottle",
        ],
        "DEFAULT_THROTTLE_RATES": {
            "anon": "1000/minute",
            "user": "1000/minute",
            "scim-token": "600/minute",
            "scim-unauth": "30/minute",
        },
    }
)
def test_scim_users_view_throttles_after_unauth_burst():
    """31st unauth request within a minute → 429."""
    c = Client()

    # Issue 30 unauthenticated requests — all should be 401 (no throttle yet).
    for _ in range(30):
        resp = c.get("/scim/v2/Users", HTTP_AUTHORIZATION="Bearer garbage")
        assert resp.status_code == 401

    # 31st must hit the per-IP unauth throttle and return 429.
    resp = c.get("/scim/v2/Users", HTTP_AUTHORIZATION="Bearer garbage")
    assert resp.status_code == 429


# ---------------------------------------------------------------------------
# 2. Authenticated steady-state is not throttled at typical IdP-sync rates
# ---------------------------------------------------------------------------

@override_settings(
    REST_FRAMEWORK={
        "DEFAULT_THROTTLE_CLASSES": [
            "rest_framework.throttling.AnonRateThrottle",
            "rest_framework.throttling.UserRateThrottle",
        ],
        "DEFAULT_THROTTLE_RATES": {
            "anon": "1000/minute",
            "user": "1000/minute",
            "scim-token": "600/minute",
            "scim-unauth": "30/minute",
        },
    }
)
def test_scim_users_view_does_not_throttle_authed_within_rate():
    """100 authed requests under a 600/min limit must all pass."""
    tenant = _make_tenant()
    admin = _make_admin(tenant)
    raw_token, _ = _scim_token_for(tenant, admin)

    c = Client()
    for _ in range(100):
        resp = c.get("/scim/v2/Users", HTTP_AUTHORIZATION=f"Bearer {raw_token}")
        assert resp.status_code == 200, (
            f"authed SCIM request unexpectedly failed: {resp.status_code} "
            f"{resp.content[:200]!r}"
        )


# ---------------------------------------------------------------------------
# 3. Rate is env-overridable (low rate via override_settings → 429 sooner)
# ---------------------------------------------------------------------------

@override_settings(
    REST_FRAMEWORK={
        "DEFAULT_THROTTLE_CLASSES": [
            "rest_framework.throttling.AnonRateThrottle",
            "rest_framework.throttling.UserRateThrottle",
        ],
        "DEFAULT_THROTTLE_RATES": {
            "anon": "1000/minute",
            "user": "1000/minute",
            # Very low rates to make this test fast and deterministic.
            "scim-token": "3/minute",
            "scim-unauth": "30/minute",
        },
    }
)
def test_scim_token_rate_can_be_overridden():
    """When the per-token throttle is set to 3/min, the 4th authed call → 429."""
    tenant = _make_tenant()
    admin = _make_admin(tenant)
    raw_token, _ = _scim_token_for(tenant, admin)

    c = Client()
    for i in range(3):
        resp = c.get("/scim/v2/Users", HTTP_AUTHORIZATION=f"Bearer {raw_token}")
        assert resp.status_code == 200, (
            f"call {i + 1} unexpectedly throttled: {resp.status_code}"
        )

    # Fourth should now be throttled by `scim-token`.
    resp = c.get("/scim/v2/Users", HTTP_AUTHORIZATION=f"Bearer {raw_token}")
    assert resp.status_code == 429


# ---------------------------------------------------------------------------
# 4. Throttle scope is shared between /Users and /Groups (same bucket)
# ---------------------------------------------------------------------------

@override_settings(
    REST_FRAMEWORK={
        "DEFAULT_THROTTLE_CLASSES": [
            "rest_framework.throttling.AnonRateThrottle",
            "rest_framework.throttling.UserRateThrottle",
        ],
        "DEFAULT_THROTTLE_RATES": {
            "anon": "1000/minute",
            "user": "1000/minute",
            "scim-token": "3/minute",
            "scim-unauth": "30/minute",
        },
    }
)
def test_scim_groups_endpoints_share_throttle_scope():
    """Burst on /Users/, then call /Groups/ — counts toward same scope."""
    tenant = _make_tenant()
    admin = _make_admin(tenant)
    raw_token, _ = _scim_token_for(tenant, admin)

    c = Client()
    # 3 calls to /Users — fills the bucket.
    for _ in range(3):
        resp = c.get("/scim/v2/Users", HTTP_AUTHORIZATION=f"Bearer {raw_token}")
        assert resp.status_code == 200

    # First call to /Groups must already be throttled because the scope
    # ("scim-token") is shared across both endpoints.
    resp = c.get("/scim/v2/Groups", HTTP_AUTHORIZATION=f"Bearer {raw_token}")
    assert resp.status_code == 429
