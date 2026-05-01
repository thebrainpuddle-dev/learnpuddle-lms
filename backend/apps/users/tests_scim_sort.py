"""
SCIM 2.0 sort support tests — AUDIT-2026-04-26-PHASE3-6.

Tests written RED-first before implementation.

Covers:
  - GET /scim/v2/Users  with sortBy=userName  asc / desc
  - GET /scim/v2/Users  with unknown sortBy field → 400
  - GET /scim/v2/Groups with sortBy=displayName asc / desc
  - GET /scim/v2/ServiceProviderConfig → sort.supported == True
"""

from __future__ import annotations

import json
import uuid

import pytest
from django.test import Client

from apps.courses.models import TeacherGroup
from apps.tenants.models import Tenant
from apps.users.models import User

pytestmark = pytest.mark.django_db

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tenant(subdomain: str = None) -> Tenant:
    sub = subdomain or ("sort-" + uuid.uuid4().hex[:8])
    return Tenant.objects.create(
        name=f"School {sub}",
        slug=sub,
        subdomain=sub,
        email=f"admin@{sub}.test",
    )


def _admin(tenant: Tenant, email: str = None) -> User:
    em = email or f"admin-{uuid.uuid4().hex[:6]}@sort.test"
    return User.objects.create_user(
        email=em,
        password="Password123!",
        first_name="Admin",
        last_name="User",
        tenant=tenant,
        role="SCHOOL_ADMIN",
    )


def _teacher(tenant: Tenant, email: str) -> User:
    return User.objects.create_user(
        email=email,
        password="Password123!",
        first_name="Teacher",
        last_name="Test",
        tenant=tenant,
        role="TEACHER",
    )


def _scim_token(tenant: Tenant, admin: User):
    from apps.users.scim_models import SCIMToken
    return SCIMToken.generate(tenant=tenant, name="Sort Test IdP", created_by=admin)


def _headers(raw: str) -> dict:
    return {"HTTP_AUTHORIZATION": f"Bearer {raw}"}


def _body(resp) -> dict:
    return json.loads(resp.content)


# ---------------------------------------------------------------------------
# ServiceProviderConfig — sort.supported must now be True
# ---------------------------------------------------------------------------

class TestServiceProviderConfigSortSupported:
    def test_serviceproviderconfig_now_advertises_sort_supported(self):
        """AUDIT-2026-04-26-PHASE3-6: flip sort.supported to True."""
        c = Client()
        resp = c.get("/scim/v2/ServiceProviderConfig")
        assert resp.status_code == 200
        data = _body(resp)
        assert data["sort"]["supported"] is True, (
            "ServiceProviderConfig must advertise sort.supported=true after PHASE3-6 fix"
        )


# ---------------------------------------------------------------------------
# Users — sortBy=userName
# ---------------------------------------------------------------------------

class TestSCIMUsersSort:
    def _setup(self):
        t = _tenant()
        a = _admin(t)
        _teacher(t, "alice@sort.test")
        _teacher(t, "bob@sort.test")
        _teacher(t, "charlie@sort.test")
        raw, _ = _scim_token(t, a)
        return t, a, raw

    def test_users_view_honours_sortby_email_asc(self):
        """sortBy=userName&sortOrder=ascending must return users in A→Z order."""
        _, _, raw = self._setup()
        c = Client()
        resp = c.get(
            "/scim/v2/Users",
            {"sortBy": "userName", "sortOrder": "ascending"},
            **_headers(raw),
        )
        assert resp.status_code == 200
        data = _body(resp)
        emails = [r["userName"] for r in data["Resources"]]
        assert emails == sorted(emails), f"Expected ascending order, got {emails}"

    def test_users_view_honours_sortby_email_desc(self):
        """sortBy=userName&sortOrder=descending must return users in Z→A order."""
        _, _, raw = self._setup()
        c = Client()
        resp = c.get(
            "/scim/v2/Users",
            {"sortBy": "userName", "sortOrder": "descending"},
            **_headers(raw),
        )
        assert resp.status_code == 200
        data = _body(resp)
        emails = [r["userName"] for r in data["Resources"]]
        assert emails == sorted(emails, reverse=True), (
            f"Expected descending order, got {emails}"
        )

    def test_users_view_rejects_unknown_sortby_with_400(self):
        """sortBy on a non-allowlisted field must return 400 SCIM error."""
        _, _, raw = self._setup()
        c = Client()
        resp = c.get(
            "/scim/v2/Users",
            {"sortBy": "password", "sortOrder": "ascending"},
            **_headers(raw),
        )
        assert resp.status_code == 400
        data = _body(resp)
        assert data["status"] == 400
        assert "schemas" in data and any("Error" in s for s in data["schemas"])

    def test_users_view_default_sort_unchanged_when_no_sortby(self):
        """Without sortBy, implicit email ordering still applies (no regression)."""
        _, _, raw = self._setup()
        c = Client()
        resp = c.get("/scim/v2/Users", **_headers(raw))
        assert resp.status_code == 200
        data = _body(resp)
        emails = [r["userName"] for r in data["Resources"]]
        assert emails == sorted(emails), "Default implicit sort should still be email ASC"


# ---------------------------------------------------------------------------
# Groups — sortBy=displayName
# ---------------------------------------------------------------------------

class TestSCIMGroupsSort:
    def _setup(self):
        t = _tenant()
        a = _admin(t)
        for name in ("Zebra Group", "Alpha Group", "Mango Group"):
            TeacherGroup.objects.create(tenant=t, name=name, description="")
        raw, _ = _scim_token(t, a)
        return t, a, raw

    def test_groups_view_honours_sortby_name_asc(self):
        """sortBy=displayName&sortOrder=ascending returns groups A→Z."""
        _, _, raw = self._setup()
        c = Client()
        resp = c.get(
            "/scim/v2/Groups",
            {"sortBy": "displayName", "sortOrder": "ascending"},
            **_headers(raw),
        )
        assert resp.status_code == 200
        data = _body(resp)
        names = [r["displayName"] for r in data["Resources"]]
        assert names == sorted(names), f"Expected ascending order, got {names}"

    def test_groups_view_honours_sortby_name_desc(self):
        """sortBy=displayName&sortOrder=descending returns groups Z→A."""
        _, _, raw = self._setup()
        c = Client()
        resp = c.get(
            "/scim/v2/Groups",
            {"sortBy": "displayName", "sortOrder": "descending"},
            **_headers(raw),
        )
        assert resp.status_code == 200
        data = _body(resp)
        names = [r["displayName"] for r in data["Resources"]]
        assert names == sorted(names, reverse=True), (
            f"Expected descending order, got {names}"
        )

    def test_groups_view_rejects_unknown_sortby_with_400(self):
        """sortBy on a non-allowlisted field must return 400 SCIM error."""
        _, _, raw = self._setup()
        c = Client()
        resp = c.get(
            "/scim/v2/Groups",
            {"sortBy": "created", "sortOrder": "ascending"},
            **_headers(raw),
        )
        assert resp.status_code == 400
        data = _body(resp)
        assert data["status"] == 400
