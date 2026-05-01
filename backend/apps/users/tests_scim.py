"""
SCIM 2.0 User Provisioning — test suite (TASK-023).

TDD: these tests were written BEFORE any implementation code.
Every test should FAIL until the implementation is in place.

Covers:
  - SCIMToken model: creation, hashing, tenant scoping
  - Bearer-token authentication on all SCIM endpoints
  - GET  /scim/v2/Users           — list + userName filter
  - POST /scim/v2/Users           — provision a new user
  - GET  /scim/v2/Users/{id}      — retrieve single user
  - PUT  /scim/v2/Users/{id}      — full replace
  - PATCH /scim/v2/Users/{id}     — partial update via Operations
  - DELETE /scim/v2/Users/{id}    — deprovision (soft deactivate)
  - GET /scim/v2/ServiceProviderConfig
  - Admin token management API
"""

from __future__ import annotations

import hashlib
import uuid

import pytest
from django.test import Client
from django.urls import reverse

from apps.tenants.models import Tenant
from apps.users.models import User

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Helpers
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


def _make_teacher(tenant: Tenant, email: str = None, **kwargs) -> User:
    email = email or f"teacher-{uuid.uuid4().hex[:6]}@test.com"
    return User.objects.create_user(
        email=email,
        password="Password123!",
        first_name="Jane",
        last_name="Smith",
        tenant=tenant,
        role="TEACHER",
        **kwargs,
    )


def _scim_headers(token: str) -> dict:
    # Only the Authorization header — callers that need Content-Type pass it
    # explicitly on POST/PUT/PATCH to avoid a duplicate-keyword TypeError.
    return {
        "HTTP_AUTHORIZATION": f"Bearer {token}",
    }


# ---------------------------------------------------------------------------
# 1. SCIMToken model
# ---------------------------------------------------------------------------

class TestSCIMTokenModel:
    """Unit tests for the SCIMToken model."""

    def test_create_scim_token_stores_hash_not_plaintext(self):
        """The raw token value must never be stored; only its SHA-256 hash."""
        from apps.users.scim_models import SCIMToken

        tenant = _make_tenant()
        admin = _make_admin(tenant)
        raw_token, scim_token = SCIMToken.generate(tenant=tenant, name="Okta", created_by=admin)

        assert scim_token.token_hash != raw_token
        assert scim_token.token_hash == hashlib.sha256(raw_token.encode()).hexdigest()

    def test_verify_correct_token_returns_token_object(self):
        """SCIMToken.verify() returns the token row for a valid raw token."""
        from apps.users.scim_models import SCIMToken

        tenant = _make_tenant()
        admin = _make_admin(tenant)
        raw_token, scim_token = SCIMToken.generate(tenant=tenant, name="Okta", created_by=admin)

        result = SCIMToken.verify(raw_token)
        assert result is not None
        assert result.pk == scim_token.pk

    def test_verify_wrong_token_returns_none(self):
        """SCIMToken.verify() returns None for an unknown token."""
        from apps.users.scim_models import SCIMToken

        result = SCIMToken.verify("not-a-real-token")
        assert result is None

    def test_verify_inactive_token_returns_none(self):
        """Revoked tokens are rejected."""
        from apps.users.scim_models import SCIMToken

        tenant = _make_tenant()
        admin = _make_admin(tenant)
        raw_token, scim_token = SCIMToken.generate(tenant=tenant, name="Okta", created_by=admin)
        scim_token.is_active = False
        scim_token.save(update_fields=["is_active"])

        assert SCIMToken.verify(raw_token) is None

    def test_generate_returns_url_safe_token(self):
        """Generated token must be URL-safe (no +, /, or = chars)."""
        from apps.users.scim_models import SCIMToken

        tenant = _make_tenant()
        admin = _make_admin(tenant)
        raw_token, _ = SCIMToken.generate(tenant=tenant, name="Okta", created_by=admin)

        assert all(c not in raw_token for c in ("+", "/", "="))
        assert len(raw_token) >= 32

    def test_verify_rejected_when_tenant_is_inactive(self):
        """SCIMToken.verify() returns None when the tenant is deactivated.

        An inactive tenant must not accept SCIM provisioning — returning the
        token would allow IdPs to create/modify users on a suspended account.

        M6 fix (TASK-023-followup): ``SCIMToken.verify`` must check
        ``scim_token.tenant.is_active`` and reject requests to suspended tenants.
        """
        from apps.users.scim_models import SCIMToken

        tenant = _make_tenant()
        admin = _make_admin(tenant)
        raw_token, _ = SCIMToken.generate(tenant=tenant, name="Okta", created_by=admin)

        # Suspend the tenant (e.g., payment failed, admin deactivated account)
        tenant.is_active = False
        tenant.save(update_fields=["is_active"])

        result = SCIMToken.verify(raw_token)
        assert result is None, (
            "SCIMToken.verify() must return None when tenant.is_active=False. "
            "M6: suspended tenants must not accept SCIM provisioning."
        )


# ---------------------------------------------------------------------------
# 2. SCIM Authentication middleware
# ---------------------------------------------------------------------------

class TestSCIMAuthentication:
    """All SCIM endpoints require a valid Bearer token."""

    def test_missing_auth_header_returns_401(self):
        """Requests without Authorization header → 401."""
        c = Client()
        resp = c.get("/scim/v2/Users")
        assert resp.status_code == 401

    def test_wrong_scheme_returns_401(self):
        """Basic auth or other schemes are rejected."""
        c = Client()
        resp = c.get("/scim/v2/Users", HTTP_AUTHORIZATION="Basic dXNlcjpwYXNz")
        assert resp.status_code == 401

    def test_invalid_token_returns_401(self):
        """Unknown Bearer token → 401."""
        c = Client()
        resp = c.get("/scim/v2/Users", HTTP_AUTHORIZATION="Bearer invalid-token-xyz")
        assert resp.status_code == 401

    def test_valid_token_grants_access(self):
        """Valid Bearer token → 200."""
        from apps.users.scim_models import SCIMToken

        tenant = _make_tenant()
        admin = _make_admin(tenant)
        raw_token, _ = SCIMToken.generate(tenant=tenant, name="Okta", created_by=admin)

        c = Client()
        resp = c.get("/scim/v2/Users", **_scim_headers(raw_token))
        assert resp.status_code == 200

    def test_revoked_token_returns_401(self):
        """Revoked token → 401."""
        from apps.users.scim_models import SCIMToken

        tenant = _make_tenant()
        admin = _make_admin(tenant)
        raw_token, scim_token = SCIMToken.generate(tenant=tenant, name="Okta", created_by=admin)
        scim_token.is_active = False
        scim_token.save(update_fields=["is_active"])

        c = Client()
        resp = c.get("/scim/v2/Users", **_scim_headers(raw_token))
        assert resp.status_code == 401

    def test_inactive_tenant_token_returns_401(self):
        """Valid token for a deactivated tenant → 401.

        Verifies that the tenant.is_active check in SCIMToken.verify() flows
        through to the HTTP layer: an IdP cannot provision users on a suspended
        tenant even if it holds a valid (not-revoked) token.

        M6 fix (TASK-023-followup): guards SCIM provisioning on suspended accounts.
        """
        from apps.users.scim_models import SCIMToken

        tenant = _make_tenant()
        admin = _make_admin(tenant)
        raw_token, _ = SCIMToken.generate(tenant=tenant, name="Okta", created_by=admin)

        # Suspend the tenant (e.g., account suspended, payment failed)
        tenant.is_active = False
        tenant.save(update_fields=["is_active"])

        c = Client()
        resp = c.get("/scim/v2/Users", **_scim_headers(raw_token))
        assert resp.status_code == 401, (
            f"Expected 401 for inactive tenant, got {resp.status_code}. "
            "M6: suspended tenants must not accept SCIM provisioning."
        )


# ---------------------------------------------------------------------------
# 3. GET /scim/v2/Users — list
# ---------------------------------------------------------------------------

class TestSCIMListUsers:
    """Tests for SCIM user list endpoint."""

    def _setup(self):
        from apps.users.scim_models import SCIMToken

        tenant = _make_tenant()
        admin = _make_admin(tenant)
        raw_token, _ = SCIMToken.generate(tenant=tenant, name="Okta", created_by=admin)
        return tenant, raw_token

    def test_list_users_returns_scim_list_response_envelope(self):
        """Response must contain the SCIM ListResponse envelope."""
        tenant, raw_token = self._setup()
        _make_teacher(tenant)

        c = Client()
        resp = c.get("/scim/v2/Users", **_scim_headers(raw_token))
        data = resp.json()

        assert resp.status_code == 200
        assert "urn:ietf:params:scim:api:messages:2.0:ListResponse" in data["schemas"]
        assert "totalResults" in data
        assert "Resources" in data

    def test_list_users_only_returns_own_tenant_users(self):
        """SCIM list must not leak users from other tenants."""
        from apps.users.scim_models import SCIMToken

        tenant_a = _make_tenant()
        tenant_b = _make_tenant()
        admin_a = _make_admin(tenant_a)
        raw_token_a, _ = SCIMToken.generate(tenant=tenant_a, name="Okta", created_by=admin_a)

        teacher_a = _make_teacher(tenant_a, email="teacher-a@test.com")
        _make_teacher(tenant_b, email="teacher-b@test.com")

        c = Client()
        resp = c.get("/scim/v2/Users", **_scim_headers(raw_token_a))
        data = resp.json()

        emails = [r["userName"] for r in data["Resources"]]
        assert "teacher-a@test.com" in emails
        assert "teacher-b@test.com" not in emails

    def test_list_users_filter_by_username(self):
        """?filter=userName eq '...' must return only matching user."""
        tenant, raw_token = self._setup()
        teacher = _make_teacher(tenant, email="john.doe@example.com")
        _make_teacher(tenant, email="jane.smith@example.com")

        c = Client()
        resp = c.get(
            '/scim/v2/Users?filter=userName eq "john.doe@example.com"',
            **_scim_headers(raw_token),
        )
        data = resp.json()

        assert resp.status_code == 200
        assert data["totalResults"] == 1
        assert data["Resources"][0]["userName"] == "john.doe@example.com"

    def test_list_users_pagination_count(self):
        """count=1 returns at most 1 result, itemsPerPage reflects the limit."""
        tenant, raw_token = self._setup()
        _make_teacher(tenant)
        _make_teacher(tenant)

        c = Client()
        resp = c.get("/scim/v2/Users?count=1", **_scim_headers(raw_token))
        data = resp.json()

        assert resp.status_code == 200
        assert data["itemsPerPage"] == 1
        assert len(data["Resources"]) <= 1

    def test_list_users_user_schema_shape(self):
        """Each Resource must include required SCIM User schema fields."""
        tenant, raw_token = self._setup()
        _make_teacher(tenant, email="test@example.com")

        c = Client()
        resp = c.get("/scim/v2/Users", **_scim_headers(raw_token))
        data = resp.json()

        user = data["Resources"][0]
        assert "urn:ietf:params:scim:schemas:core:2.0:User" in user["schemas"]
        assert "id" in user
        assert "userName" in user
        assert "name" in user
        assert "givenName" in user["name"]
        assert "familyName" in user["name"]
        assert "active" in user
        assert "meta" in user
        assert user["meta"]["resourceType"] == "User"

    def test_list_users_sortby_username_ascending(self):
        """?sortBy=userName returns users ordered by email ascending (the
        SCIM userName maps to User.email in this implementation)."""
        tenant, raw_token = self._setup()
        _make_teacher(tenant, email="zebra@test.com")
        _make_teacher(tenant, email="apple@test.com")
        _make_teacher(tenant, email="mango@test.com")

        c = Client()
        resp = c.get("/scim/v2/Users?sortBy=userName", **_scim_headers(raw_token))
        data = resp.json()

        assert resp.status_code == 200
        emails = [r["userName"] for r in data["Resources"]]
        assert emails == sorted(emails), (
            f"Expected ascending order, got: {emails}"
        )

    def test_list_users_sortby_email_is_synonym_for_username(self):
        """?sortBy=email (case-insensitive) is treated as a synonym for
        sortBy=userName (both map to the email column)."""
        tenant, raw_token = self._setup()
        _make_teacher(tenant, email="z@test.com")
        _make_teacher(tenant, email="a@test.com")

        c = Client()
        resp = c.get("/scim/v2/Users?sortBy=email", **_scim_headers(raw_token))
        data = resp.json()

        assert resp.status_code == 200
        emails = [r["userName"] for r in data["Resources"]]
        assert emails == sorted(emails)

    def test_list_users_sortby_descending_order(self):
        """?sortBy=userName&sortOrder=descending returns users in reverse email order."""
        tenant, raw_token = self._setup()
        _make_teacher(tenant, email="alpha@test.com")
        _make_teacher(tenant, email="zeta@test.com")
        _make_teacher(tenant, email="mu@test.com")

        c = Client()
        resp = c.get(
            "/scim/v2/Users?sortBy=userName&sortOrder=descending",
            **_scim_headers(raw_token),
        )
        data = resp.json()

        assert resp.status_code == 200
        emails = [r["userName"] for r in data["Resources"]]
        assert emails == sorted(emails, reverse=True), (
            f"Expected descending order, got: {emails}"
        )

    def test_list_users_unknown_sortby_returns_400(self):
        """?sortBy=<unsupported-attr> must return 400 (invalidValue) per RFC 7644.

        This prevents IdP test-suites from silently receiving unsorted
        results when they request an attribute the implementation does not
        support — they get an explicit error instead.
        """
        tenant, raw_token = self._setup()

        c = Client()
        resp = c.get("/scim/v2/Users?sortBy=phoneNumber", **_scim_headers(raw_token))
        data = resp.json()

        assert resp.status_code == 400, (
            f"Expected 400 for unsupported sortBy, got {resp.status_code}"
        )
        assert data.get("scimType") == "invalidValue", (
            f"Expected scimType='invalidValue', got: {data}"
        )


# ---------------------------------------------------------------------------
# 4. POST /scim/v2/Users — provision
# ---------------------------------------------------------------------------

class TestSCIMCreateUser:
    """Tests for SCIM user provisioning (POST)."""

    def _setup(self):
        from apps.users.scim_models import SCIMToken

        tenant = _make_tenant()
        admin = _make_admin(tenant)
        raw_token, _ = SCIMToken.generate(tenant=tenant, name="Okta", created_by=admin)
        return tenant, raw_token

    def _scim_user_payload(self, email: str, first: str = "John", last: str = "Doe") -> dict:
        return {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
            "userName": email,
            "name": {"givenName": first, "familyName": last},
            "active": True,
            "emails": [{"value": email, "primary": True, "type": "work"}],
        }

    def test_create_user_returns_201_with_scim_user_body(self):
        """POST /scim/v2/Users → 201 Created with SCIM User schema."""
        tenant, raw_token = self._setup()
        payload = self._scim_user_payload("newteacher@example.com")

        c = Client()
        resp = c.post(
            "/scim/v2/Users",
            data=payload,
            content_type="application/scim+json",
            **_scim_headers(raw_token),
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "urn:ietf:params:scim:schemas:core:2.0:User" in data["schemas"]
        assert data["userName"] == "newteacher@example.com"
        assert "id" in data

    def test_create_user_creates_db_record(self):
        """Provisioned user must exist in the database."""
        tenant, raw_token = self._setup()
        payload = self._scim_user_payload("dbcheck@example.com", "Alice", "Walker")

        c = Client()
        c.post(
            "/scim/v2/Users",
            data=payload,
            content_type="application/scim+json",
            **_scim_headers(raw_token),
        )

        user = User.objects.get(email="dbcheck@example.com")
        assert user.first_name == "Alice"
        assert user.last_name == "Walker"
        assert user.tenant_id == tenant.id
        assert user.role == "TEACHER"
        assert user.is_active is True

    def test_create_user_maps_external_id(self):
        """externalId in payload maps to employee_id field."""
        tenant, raw_token = self._setup()
        payload = self._scim_user_payload("extid@example.com")
        payload["externalId"] = "okta-user-abc123"

        c = Client()
        c.post(
            "/scim/v2/Users",
            data=payload,
            content_type="application/scim+json",
            **_scim_headers(raw_token),
        )

        user = User.objects.get(email="extid@example.com")
        assert user.employee_id == "okta-user-abc123"

    def test_create_user_duplicate_email_returns_409(self):
        """POST with an already-existing userName → 409 Conflict."""
        tenant, raw_token = self._setup()
        _make_teacher(tenant, email="existing@example.com")
        payload = self._scim_user_payload("existing@example.com")

        c = Client()
        resp = c.post(
            "/scim/v2/Users",
            data=payload,
            content_type="application/scim+json",
            **_scim_headers(raw_token),
        )
        assert resp.status_code == 409

    def test_create_user_missing_username_returns_400(self):
        """POST without userName → 400 Bad Request."""
        tenant, raw_token = self._setup()
        payload = {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
            "name": {"givenName": "No", "familyName": "Email"},
        }

        c = Client()
        resp = c.post(
            "/scim/v2/Users",
            data=payload,
            content_type="application/scim+json",
            **_scim_headers(raw_token),
        )
        assert resp.status_code == 400

    def test_create_user_with_custom_extension(self):
        """Custom urn:learnpuddle extension fields map to User model."""
        tenant, raw_token = self._setup()
        payload = self._scim_user_payload("ext@example.com")
        payload["urn:learnpuddle:1.0:User"] = {
            "department": "Mathematics",
        }

        c = Client()
        c.post(
            "/scim/v2/Users",
            data=payload,
            content_type="application/scim+json",
            **_scim_headers(raw_token),
        )

        user = User.objects.get(email="ext@example.com")
        assert user.department == "Mathematics"


# ---------------------------------------------------------------------------
# 5. GET /scim/v2/Users/{id}
# ---------------------------------------------------------------------------

class TestSCIMGetUser:
    """Tests for SCIM GET single user."""

    def _setup(self):
        from apps.users.scim_models import SCIMToken

        tenant = _make_tenant()
        admin = _make_admin(tenant)
        raw_token, _ = SCIMToken.generate(tenant=tenant, name="Okta", created_by=admin)
        teacher = _make_teacher(tenant, email="getme@example.com")
        return tenant, raw_token, teacher

    def test_get_user_returns_scim_user(self):
        """GET /scim/v2/Users/{id} → 200 with SCIM User body."""
        _, raw_token, teacher = self._setup()

        c = Client()
        resp = c.get(f"/scim/v2/Users/{teacher.id}", **_scim_headers(raw_token))

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == str(teacher.id)
        assert data["userName"] == "getme@example.com"

    def test_get_user_cross_tenant_returns_404(self):
        """Cannot read another tenant's user — returns 404 (not 403)."""
        from apps.users.scim_models import SCIMToken

        tenant_a = _make_tenant()
        tenant_b = _make_tenant()
        admin_a = _make_admin(tenant_a)
        raw_token_a, _ = SCIMToken.generate(tenant=tenant_a, name="Okta", created_by=admin_a)

        teacher_b = _make_teacher(tenant_b)

        c = Client()
        resp = c.get(f"/scim/v2/Users/{teacher_b.id}", **_scim_headers(raw_token_a))
        assert resp.status_code == 404

    def test_get_user_nonexistent_returns_404(self):
        """GET for non-existent ID → 404."""
        _, raw_token, _ = self._setup()

        c = Client()
        resp = c.get(f"/scim/v2/Users/{uuid.uuid4()}", **_scim_headers(raw_token))
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 6. PUT /scim/v2/Users/{id} — full replace
# ---------------------------------------------------------------------------

class TestSCIMPutUser:
    """Tests for SCIM PUT (full replace)."""

    def _setup(self):
        from apps.users.scim_models import SCIMToken

        tenant = _make_tenant()
        admin = _make_admin(tenant)
        raw_token, _ = SCIMToken.generate(tenant=tenant, name="Okta", created_by=admin)
        teacher = _make_teacher(tenant, email="putme@example.com")
        return tenant, raw_token, teacher

    def test_put_user_updates_name_fields(self):
        """PUT replaces givenName and familyName."""
        _, raw_token, teacher = self._setup()

        payload = {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
            "userName": "putme@example.com",
            "name": {"givenName": "Updated", "familyName": "Name"},
            "active": True,
        }
        c = Client()
        resp = c.put(
            f"/scim/v2/Users/{teacher.id}",
            data=payload,
            content_type="application/scim+json",
            **_scim_headers(raw_token),
        )
        assert resp.status_code == 200
        teacher.refresh_from_db()
        assert teacher.first_name == "Updated"
        assert teacher.last_name == "Name"

    def test_put_user_deactivate_sets_is_active_false(self):
        """PUT with active=False deactivates the user."""
        _, raw_token, teacher = self._setup()

        payload = {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
            "userName": "putme@example.com",
            "name": {"givenName": "Jane", "familyName": "Smith"},
            "active": False,
        }
        c = Client()
        resp = c.put(
            f"/scim/v2/Users/{teacher.id}",
            data=payload,
            content_type="application/scim+json",
            **_scim_headers(raw_token),
        )
        assert resp.status_code == 200
        teacher.refresh_from_db()
        assert teacher.is_active is False

    def test_put_user_cross_tenant_returns_404(self):
        """PUT on another tenant's user → 404."""
        from apps.users.scim_models import SCIMToken

        tenant_a = _make_tenant()
        tenant_b = _make_tenant()
        admin_a = _make_admin(tenant_a)
        raw_token_a, _ = SCIMToken.generate(tenant=tenant_a, name="Okta", created_by=admin_a)
        teacher_b = _make_teacher(tenant_b)

        payload = {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
            "userName": teacher_b.email,
            "name": {"givenName": "Hacker", "familyName": "X"},
            "active": True,
        }
        c = Client()
        resp = c.put(
            f"/scim/v2/Users/{teacher_b.id}",
            data=payload,
            content_type="application/scim+json",
            **_scim_headers(raw_token_a),
        )
        assert resp.status_code == 404

    # -- SCIM-POLISH-2026-04-27: PUT replace semantics -----------------------

    def test_put_user_clears_first_name_when_given_name_is_empty_string(self):
        """
        PUT with name.givenName="" should clear first_name (replace semantics).

        Previously the handler used `or user.first_name` fallback, retaining
        the old value on empty string.  After the polish fix the `"givenName" in
        name_obj` branch overwrites unconditionally, so givenName="" → first_name="".
        """
        _, raw_token, teacher = self._setup()
        assert teacher.first_name != "", "pre-condition: teacher has a non-empty first name"

        c = Client()
        resp = c.put(
            f"/scim/v2/Users/{teacher.id}",
            data={
                "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
                "userName": teacher.email,
                "name": {"givenName": "", "familyName": teacher.last_name},
            },
            content_type="application/scim+json",
            **_scim_headers(raw_token),
        )
        assert resp.status_code == 200
        teacher.refresh_from_db()
        assert teacher.first_name == ""

    def test_put_user_retains_first_name_when_given_name_absent(self):
        """
        PUT body that omits the name.givenName key entirely should retain the
        existing first_name value.

        RFC 7644 §3.5.1 allows partial-PUT bodies; the `"givenName" in name_obj`
        check ensures absent keys are treated as "no change".
        """
        _, raw_token, teacher = self._setup()
        original_first_name = teacher.first_name

        c = Client()
        resp = c.put(
            f"/scim/v2/Users/{teacher.id}",
            data={
                "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
                "userName": teacher.email,
                # name key absent entirely — givenName should be retained
            },
            content_type="application/scim+json",
            **_scim_headers(raw_token),
        )
        assert resp.status_code == 200
        teacher.refresh_from_db()
        assert teacher.first_name == original_first_name


# ---------------------------------------------------------------------------
# 7. PATCH /scim/v2/Users/{id} — partial update via Operations
# ---------------------------------------------------------------------------

class TestSCIMPatchUser:
    """Tests for SCIM PATCH (partial update via Operations array)."""

    def _setup(self):
        from apps.users.scim_models import SCIMToken

        tenant = _make_tenant()
        admin = _make_admin(tenant)
        raw_token, _ = SCIMToken.generate(tenant=tenant, name="Okta", created_by=admin)
        teacher = _make_teacher(tenant, email="patchme@example.com")
        return tenant, raw_token, teacher

    def test_patch_deactivate_sets_is_active_false(self):
        """PATCH Replace active=false deactivates the user."""
        _, raw_token, teacher = self._setup()

        payload = {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [{"op": "replace", "path": "active", "value": False}],
        }
        c = Client()
        resp = c.patch(
            f"/scim/v2/Users/{teacher.id}",
            data=payload,
            content_type="application/scim+json",
            **_scim_headers(raw_token),
        )
        assert resp.status_code == 200
        teacher.refresh_from_db()
        assert teacher.is_active is False

    def test_patch_reactivate_sets_is_active_true(self):
        """PATCH Replace active=true re-activates a deactivated user."""
        _, raw_token, teacher = self._setup()
        teacher.is_active = False
        teacher.save(update_fields=["is_active"])

        payload = {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [{"op": "replace", "path": "active", "value": True}],
        }
        c = Client()
        resp = c.patch(
            f"/scim/v2/Users/{teacher.id}",
            data=payload,
            content_type="application/scim+json",
            **_scim_headers(raw_token),
        )
        assert resp.status_code == 200
        teacher.refresh_from_db()
        assert teacher.is_active is True

    def test_patch_replace_name(self):
        """PATCH Replace name.givenName updates the first_name field."""
        _, raw_token, teacher = self._setup()

        payload = {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [
                {"op": "replace", "path": "name.givenName", "value": "Patched"},
            ],
        }
        c = Client()
        resp = c.patch(
            f"/scim/v2/Users/{teacher.id}",
            data=payload,
            content_type="application/scim+json",
            **_scim_headers(raw_token),
        )
        assert resp.status_code == 200
        teacher.refresh_from_db()
        assert teacher.first_name == "Patched"

    def test_patch_with_no_operations_returns_400(self):
        """PATCH without Operations array → 400."""
        _, raw_token, teacher = self._setup()

        payload = {"schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"]}
        c = Client()
        resp = c.patch(
            f"/scim/v2/Users/{teacher.id}",
            data=payload,
            content_type="application/scim+json",
            **_scim_headers(raw_token),
        )
        assert resp.status_code == 400

    # -- M3: path-less replace (RFC 7644 §3.5.2.3) ----------------------------

    def test_patch_pathless_replace_deactivates_user(self):
        """
        M3 (RFC 7644 §3.5.2.3): PATCH replace without a 'path' key applies
        the value dict directly.

        Azure AD sends: {"op":"replace","value":{"active":false}}
        This must deactivate the user.
        """
        _, raw_token, teacher = self._setup()

        payload = {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [{"op": "replace", "value": {"active": False}}],
        }
        c = Client()
        resp = c.patch(
            f"/scim/v2/Users/{teacher.id}",
            data=payload,
            content_type="application/scim+json",
            **_scim_headers(raw_token),
        )
        assert resp.status_code == 200
        teacher.refresh_from_db()
        assert teacher.is_active is False

    def test_patch_pathless_replace_updates_name_dict(self):
        """
        M3: Path-less replace with a nested 'name' dict updates first/last name.

        Azure AD sometimes sends:
            {"op":"replace","value":{"name":{"givenName":"Jane","familyName":"Doe"}}}
        """
        _, raw_token, teacher = self._setup()

        payload = {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [
                {
                    "op": "replace",
                    "value": {
                        "name": {"givenName": "NewFirst", "familyName": "NewLast"},
                    },
                }
            ],
        }
        c = Client()
        resp = c.patch(
            f"/scim/v2/Users/{teacher.id}",
            data=payload,
            content_type="application/scim+json",
            **_scim_headers(raw_token),
        )
        assert resp.status_code == 200
        teacher.refresh_from_db()
        assert teacher.first_name == "NewFirst"
        assert teacher.last_name == "NewLast"

    def test_patch_pathless_replace_mixed_with_pathed_ops(self):
        """
        M3: Path-less and path-based operations can coexist in one Operations array.
        Both must be applied.
        """
        _, raw_token, teacher = self._setup()

        payload = {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [
                # path-less: deactivate
                {"op": "replace", "value": {"active": False}},
                # path-based: rename
                {"op": "replace", "path": "name.givenName", "value": "Mixed"},
            ],
        }
        c = Client()
        resp = c.patch(
            f"/scim/v2/Users/{teacher.id}",
            data=payload,
            content_type="application/scim+json",
            **_scim_headers(raw_token),
        )
        assert resp.status_code == 200
        teacher.refresh_from_db()
        assert teacher.is_active is False
        assert teacher.first_name == "Mixed"

    # -- M4: unknown op type logging -------------------------------------------

    def test_patch_unknown_op_type_logs_debug_and_returns_200(self, caplog):
        """
        M4: An unrecognised op type (e.g. 'add' for unsupported path, or a
        future IdP-specific op) must not crash or return 5xx.  It should log
        at DEBUG level so ops can identify quirky IdP behaviour, and the request
        as a whole must return 200 with no mutation.
        """
        import logging

        _, raw_token, teacher = self._setup()
        original_name = teacher.first_name

        payload = {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [
                {"op": "unknown_custom_op", "path": "active", "value": False},
            ],
        }
        c = Client()
        with caplog.at_level(logging.DEBUG, logger="apps.users.scim_views"):
            resp = c.patch(
                f"/scim/v2/Users/{teacher.id}",
                data=payload,
                content_type="application/scim+json",
                **_scim_headers(raw_token),
            )

        assert resp.status_code == 200
        teacher.refresh_from_db()
        # No mutation for unknown op
        assert teacher.first_name == original_name
        assert teacher.is_active is True  # unchanged
        # A debug log line mentioning the unknown op type must be emitted
        assert any(
            "unknown_custom_op" in record.message
            for record in caplog.records
            if record.levelno == logging.DEBUG
        )

    # -- _coerce_scim_str: null-givenName regression --------------------------

    def test_patch_null_given_name_via_pathless_replace_stores_empty_string(self):
        """
        PATCH path-less replace with null givenName must store "" not "None".

        Some IdPs (e.g. WorkDay) send null for attributes they wish to clear:
            {"op": "replace", "value": {"name": {"givenName": null}}}

        Before _coerce_scim_str, _apply_scim_replace_dict called str(None).strip()
        which persisted the literal string "None" to the database.
        """
        _, raw_token, teacher = self._setup()
        teacher.first_name = "Jane"
        teacher.save(update_fields=["first_name"])

        payload = {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [
                {
                    "op": "replace",
                    "value": {"name": {"givenName": None}},
                }
            ],
        }
        c = Client()
        resp = c.patch(
            f"/scim/v2/Users/{teacher.id}",
            data=payload,
            content_type="application/scim+json",
            **_scim_headers(raw_token),
        )
        assert resp.status_code == 200
        teacher.refresh_from_db()
        assert teacher.first_name == "", (
            f"Expected first_name='' after null givenName patch, got {teacher.first_name!r}. "
            "Regression: _coerce_scim_str must return '' not 'None' for null input."
        )

    def test_patch_null_given_name_via_pathed_replace_stores_empty_string(self):
        """
        PATCH pathed replace with null value must also store "" not "None".

        Covers the _apply_scim_replace_path branch:
            {"op": "replace", "path": "name.givenName", "value": null}
        """
        _, raw_token, teacher = self._setup()
        teacher.first_name = "John"
        teacher.save(update_fields=["first_name"])

        payload = {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [
                {
                    "op": "replace",
                    "path": "name.givenName",
                    "value": None,
                }
            ],
        }
        c = Client()
        resp = c.patch(
            f"/scim/v2/Users/{teacher.id}",
            data=payload,
            content_type="application/scim+json",
            **_scim_headers(raw_token),
        )
        assert resp.status_code == 200
        teacher.refresh_from_db()
        assert teacher.first_name == "", (
            f"Expected first_name='' after null pathed givenName patch, got {teacher.first_name!r}. "
            "Regression: _coerce_scim_str must return '' not 'None' for null input."
        )

    # -- SCIM-POLISH-2026-04-27: PATCH conditional save ----------------------

    def test_patch_unknown_ops_only_does_not_write_to_db(self):
        """
        PATCH whose Operations array contains only unrecognised op types must
        NOT issue a DB save.

        The optimisation introduced in the SCIM polish sprint sets _user_changed=True
        only when a recognised 'replace' op is processed.  All-unknown batches
        leave _user_changed=False and skip user.save(), so updated_at should not
        advance.

        Note: if the DB or test harness flushes sub-millisecond timestamps this
        assertion may be fragile — skip rather than xfail if it proves flaky in CI.
        """
        import time

        _, raw_token, teacher = self._setup()

        # Capture the timestamp BEFORE the PATCH — refresh ensures we read the
        # DB-persisted value, not a stale Python object.
        teacher.refresh_from_db()
        before_updated_at = teacher.updated_at

        # Small sleep so that any accidental save() would produce a strictly
        # later timestamp (auto_now=True uses timezone.now() at save time).
        time.sleep(0.05)

        payload = {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [
                # "add members" is an unrecognised op type in LearnPuddle SCIM
                {"op": "add", "path": "members", "value": []},
            ],
        }
        c = Client()
        resp = c.patch(
            f"/scim/v2/Users/{teacher.id}",
            data=payload,
            content_type="application/scim+json",
            **_scim_headers(raw_token),
        )
        assert resp.status_code == 200

        teacher.refresh_from_db()
        # updated_at must NOT have advanced (no save should have fired)
        assert teacher.updated_at == before_updated_at, (
            f"updated_at advanced from {before_updated_at} to {teacher.updated_at} "
            "— user.save() must have been called for all-unknown-op PATCH (regression)"
        )


# ---------------------------------------------------------------------------
# 8. DELETE /scim/v2/Users/{id} — deprovision
# ---------------------------------------------------------------------------

class TestSCIMDeleteUser:
    """Tests for SCIM DELETE (soft deprovision)."""

    def _setup(self):
        from apps.users.scim_models import SCIMToken

        tenant = _make_tenant()
        admin = _make_admin(tenant)
        raw_token, _ = SCIMToken.generate(tenant=tenant, name="Okta", created_by=admin)
        teacher = _make_teacher(tenant)
        return tenant, raw_token, teacher

    def test_delete_user_returns_204(self):
        """DELETE → 204 No Content."""
        _, raw_token, teacher = self._setup()

        c = Client()
        resp = c.delete(f"/scim/v2/Users/{teacher.id}", **_scim_headers(raw_token))
        assert resp.status_code == 204

    def test_delete_deactivates_not_hard_deletes(self):
        """Deprovisioned user is deactivated, not removed from DB."""
        _, raw_token, teacher = self._setup()

        c = Client()
        c.delete(f"/scim/v2/Users/{teacher.id}", **_scim_headers(raw_token))

        teacher.refresh_from_db()
        assert teacher.is_active is False
        assert User.objects.filter(pk=teacher.pk).exists()

    def test_delete_nonexistent_user_returns_404(self):
        """DELETE on a non-existent user → 404."""
        _, raw_token, _ = self._setup()

        c = Client()
        resp = c.delete(f"/scim/v2/Users/{uuid.uuid4()}", **_scim_headers(raw_token))
        assert resp.status_code == 404

    def test_delete_cross_tenant_returns_404(self):
        """Cannot deprovision another tenant's user."""
        from apps.users.scim_models import SCIMToken

        tenant_a = _make_tenant()
        tenant_b = _make_tenant()
        admin_a = _make_admin(tenant_a)
        raw_token_a, _ = SCIMToken.generate(tenant=tenant_a, name="Okta", created_by=admin_a)
        teacher_b = _make_teacher(tenant_b)

        c = Client()
        resp = c.delete(f"/scim/v2/Users/{teacher_b.id}", **_scim_headers(raw_token_a))
        assert resp.status_code == 404
        teacher_b.refresh_from_db()
        assert teacher_b.is_active is True  # unchanged


# ---------------------------------------------------------------------------
# 9. GET /scim/v2/ServiceProviderConfig
# ---------------------------------------------------------------------------

class TestSCIMServiceProviderConfig:
    """Tests for the SCIM ServiceProviderConfig endpoint."""

    def test_service_provider_config_returns_200(self):
        """GET /scim/v2/ServiceProviderConfig → 200 (no auth required)."""
        c = Client()
        resp = c.get("/scim/v2/ServiceProviderConfig")
        assert resp.status_code == 200

    def test_service_provider_config_schema(self):
        """Response must include the SCIM ServiceProviderConfig schema."""
        c = Client()
        resp = c.get("/scim/v2/ServiceProviderConfig")
        data = resp.json()

        assert "urn:ietf:params:scim:schemas:core:2.0:ServiceProviderConfig" in data["schemas"]
        assert "patch" in data
        assert data["patch"]["supported"] is True
        assert "filter" in data
        assert data["filter"]["supported"] is True
        assert "etag" in data
        assert "bulk" in data
        assert "changePassword" in data
        assert "sort" in data


# ---------------------------------------------------------------------------
# 9b. GET /scim/v2/Schemas  (RFC 7644 §7  — discovery endpoint, no auth)
# ---------------------------------------------------------------------------

class TestSCIMSchemasEndpoint:
    """
    Tests for the /scim/v2/Schemas discovery endpoint.

    Per RFC 7644 §4, this endpoint is public (no authentication required).
    It returns a ListResponse of Schema objects describing the resource
    schemas the service provider supports.
    """

    def test_schemas_returns_200_without_auth(self):
        """GET /scim/v2/Schemas → 200 without any Authorization header."""
        c = Client()
        resp = c.get("/scim/v2/Schemas")
        assert resp.status_code == 200, (
            f"Expected 200 for public Schemas endpoint, got {resp.status_code}"
        )

    def test_schemas_returns_list_response_envelope(self):
        """Response must be a SCIM ListResponse with schemas/Resources fields."""
        c = Client()
        resp = c.get("/scim/v2/Schemas")
        data = resp.json()

        assert "schemas" in data, "Missing 'schemas' key"
        assert "urn:ietf:params:scim:api:messages:2.0:ListResponse" in data["schemas"]
        assert "Resources" in data, "Missing 'Resources' key"
        assert isinstance(data["Resources"], list)

    def test_schemas_lists_user_schema(self):
        """Response must include the SCIM core User schema."""
        c = Client()
        resp = c.get("/scim/v2/Schemas")
        ids = [r["id"] for r in resp.json()["Resources"]]
        assert "urn:ietf:params:scim:schemas:core:2.0:User" in ids, (
            "User schema missing from /scim/v2/Schemas"
        )

    def test_schemas_lists_group_schema(self):
        """Response must include the SCIM core Group schema."""
        c = Client()
        resp = c.get("/scim/v2/Schemas")
        ids = [r["id"] for r in resp.json()["Resources"]]
        assert "urn:ietf:params:scim:schemas:core:2.0:Group" in ids, (
            "Group schema missing from /scim/v2/Schemas"
        )

    def test_schemas_lists_learnpuddle_extension(self):
        """Response must include the LearnPuddle User extension schema."""
        c = Client()
        resp = c.get("/scim/v2/Schemas")
        ids = [r["id"] for r in resp.json()["Resources"]]
        assert "urn:learnpuddle:1.0:User" in ids, (
            "LearnPuddle extension schema missing from /scim/v2/Schemas"
        )

    def test_schemas_content_type_is_scim_json(self):
        """Content-Type must be application/scim+json."""
        c = Client()
        resp = c.get("/scim/v2/Schemas")
        assert "application/scim+json" in resp.get("Content-Type", ""), (
            f"Expected application/scim+json content-type, got {resp.get('Content-Type')}"
        )

    def test_schemas_user_resource_has_attributes(self):
        """User schema entry must include an 'attributes' array."""
        c = Client()
        resp = c.get("/scim/v2/Schemas")
        resources = {r["id"]: r for r in resp.json()["Resources"]}
        user_schema = resources.get("urn:ietf:params:scim:schemas:core:2.0:User")
        assert user_schema is not None
        assert "attributes" in user_schema, "User schema must have 'attributes' array"
        assert len(user_schema["attributes"]) > 0

    def test_schemas_lookup_by_id(self):
        """GET /scim/v2/Schemas/{id} returns single schema (RFC 7644 §7)."""
        c = Client()
        schema_id = "urn:ietf:params:scim:schemas:core:2.0:User"
        resp = c.get(f"/scim/v2/Schemas/{schema_id}")
        assert resp.status_code == 200, (
            f"Expected 200 for single schema lookup, got {resp.status_code}"
        )
        data = resp.json()
        assert data.get("id") == schema_id


# ---------------------------------------------------------------------------
# 9c. GET /scim/v2/ResourceTypes  (RFC 7644 §6  — discovery endpoint, no auth)
# ---------------------------------------------------------------------------

class TestSCIMResourceTypesEndpoint:
    """
    Tests for the /scim/v2/ResourceTypes discovery endpoint.

    Per RFC 7644 §4, this endpoint is public (no authentication required).
    It returns a ListResponse of ResourceType objects describing the resources
    the service provider supports (User, Group, etc.).
    """

    def test_resource_types_returns_200_without_auth(self):
        """GET /scim/v2/ResourceTypes → 200 without any Authorization header."""
        c = Client()
        resp = c.get("/scim/v2/ResourceTypes")
        assert resp.status_code == 200, (
            f"Expected 200 for public ResourceTypes endpoint, got {resp.status_code}"
        )

    def test_resource_types_returns_list_response_envelope(self):
        """Response must be a SCIM ListResponse."""
        c = Client()
        resp = c.get("/scim/v2/ResourceTypes")
        data = resp.json()

        assert "schemas" in data
        assert "urn:ietf:params:scim:api:messages:2.0:ListResponse" in data["schemas"]
        assert "Resources" in data
        assert isinstance(data["Resources"], list)

    def test_resource_types_includes_user(self):
        """ResourceTypes must include a User entry pointing to /scim/v2/Users."""
        c = Client()
        resp = c.get("/scim/v2/ResourceTypes")
        names = {r["name"]: r for r in resp.json()["Resources"]}

        assert "User" in names, "User ResourceType missing"
        user_rt = names["User"]
        assert user_rt.get("endpoint") == "/scim/v2/Users"
        assert user_rt.get("schema") == "urn:ietf:params:scim:schemas:core:2.0:User"

    def test_resource_types_includes_group(self):
        """ResourceTypes must include a Group entry pointing to /scim/v2/Groups."""
        c = Client()
        resp = c.get("/scim/v2/ResourceTypes")
        names = {r["name"]: r for r in resp.json()["Resources"]}

        assert "Group" in names, "Group ResourceType missing"
        group_rt = names["Group"]
        assert group_rt.get("endpoint") == "/scim/v2/Groups"
        assert group_rt.get("schema") == "urn:ietf:params:scim:schemas:core:2.0:Group"

    def test_resource_types_content_type_is_scim_json(self):
        """Content-Type must be application/scim+json."""
        c = Client()
        resp = c.get("/scim/v2/ResourceTypes")
        assert "application/scim+json" in resp.get("Content-Type", "")

    def test_resource_types_lookup_by_name(self):
        """GET /scim/v2/ResourceTypes/User → single ResourceType (RFC 7644 §6)."""
        c = Client()
        resp = c.get("/scim/v2/ResourceTypes/User")
        assert resp.status_code == 200, (
            f"Expected 200 for single ResourceType lookup, got {resp.status_code}"
        )
        data = resp.json()
        assert data.get("name") == "User"

    def test_resource_types_user_has_schema_extensions(self):
        """User ResourceType must list the LearnPuddle extension in schemaExtensions."""
        c = Client()
        resp = c.get("/scim/v2/ResourceTypes")
        names = {r["name"]: r for r in resp.json()["Resources"]}
        user_rt = names.get("User", {})
        extensions = [
            ext.get("schema") for ext in user_rt.get("schemaExtensions", [])
        ]
        assert "urn:learnpuddle:1.0:User" in extensions, (
            "LearnPuddle extension must be listed in User schemaExtensions"
        )


# ---------------------------------------------------------------------------
# 10. Admin: SCIM Token management API
# ---------------------------------------------------------------------------

class TestSCIMTokenAdminAPI:
    """Tests for the admin token management endpoints."""

    def _make_admin_client(self, tenant: Tenant, admin: User) -> tuple:
        """Returns (client, admin_auth_headers) using JWT login.

        Uses .lms.com so TenantMiddleware can resolve the tenant via the
        autouse ``override_allowed_hosts`` fixture (PLATFORM_DOMAIN='lms.com').
        The class-level @override_settings was removed (M7): it set
        PLATFORM_DOMAIN='lms.test' which conflicted with these .lms.com hosts
        and the autouse fixture that already provides PLATFORM_DOMAIN='lms.com'.
        """
        from rest_framework_simplejwt.tokens import RefreshToken

        refresh = RefreshToken.for_user(admin)
        token = str(refresh.access_token)
        return Client(), {"HTTP_AUTHORIZATION": f"Bearer {token}", "HTTP_HOST": f"{tenant.subdomain}.lms.com"}

    def test_admin_can_create_scim_token(self):
        """POST /api/v1/admin/sso/scim-tokens/ → 201 with raw token in body."""
        tenant = _make_tenant()
        admin = _make_admin(tenant)
        client, headers = self._make_admin_client(tenant, admin)

        resp = client.post(
            "/api/v1/admin/sso/scim-tokens/",
            data={"name": "Okta production"},
            content_type="application/json",
            **headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "token" in data  # raw token returned once on creation
        assert "id" in data
        assert data["name"] == "Okta production"

    def test_admin_token_is_only_returned_on_creation(self):
        """Listing tokens does NOT return the raw token value."""
        from apps.users.scim_models import SCIMToken

        tenant = _make_tenant()
        admin = _make_admin(tenant)
        SCIMToken.generate(tenant=tenant, name="Okta", created_by=admin)
        client, headers = self._make_admin_client(tenant, admin)

        resp = client.get("/api/v1/admin/sso/scim-tokens/", **headers)
        data = resp.json()

        assert resp.status_code == 200
        for t in data["results"]:
            assert "token" not in t
            assert "token_hash" not in t

    def test_admin_can_revoke_scim_token(self):
        """DELETE /api/v1/admin/sso/scim-tokens/{id}/ sets is_active=False."""
        from apps.users.scim_models import SCIMToken

        tenant = _make_tenant()
        admin = _make_admin(tenant)
        _, scim_token = SCIMToken.generate(tenant=tenant, name="Okta", created_by=admin)
        client, headers = self._make_admin_client(tenant, admin)

        resp = client.delete(
            f"/api/v1/admin/sso/scim-tokens/{scim_token.id}/",
            **headers,
        )
        assert resp.status_code == 204
        scim_token.refresh_from_db()
        assert scim_token.is_active is False

    def test_teacher_cannot_create_scim_token(self):
        """Only SCHOOL_ADMIN can manage SCIM tokens — teachers get 403."""
        tenant = _make_tenant()
        teacher = _make_teacher(tenant)
        client, headers = self._make_admin_client(tenant, teacher)

        resp = client.post(
            "/api/v1/admin/sso/scim-tokens/",
            data={"name": "Bad actor"},
            content_type="application/json",
            **headers,
        )
        assert resp.status_code == 403

    def test_admin_cross_tenant_token_revoke_returns_404(self):
        """Admin from tenant A cannot revoke tenant B's SCIM token."""
        from apps.users.scim_models import SCIMToken

        tenant_a = _make_tenant()
        tenant_b = _make_tenant()
        admin_a = _make_admin(tenant_a)
        admin_b = _make_admin(tenant_b)

        _, token_b = SCIMToken.generate(tenant=tenant_b, name="Okta", created_by=admin_b)
        client, headers = self._make_admin_client(tenant_a, admin_a)

        resp = client.delete(
            f"/api/v1/admin/sso/scim-tokens/{token_b.id}/",
            **headers,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 11. M1 regression: POST with admin-soft-deleted email must return 409, not 500
# ---------------------------------------------------------------------------

class TestSCIMPostSoftDeletedEmailCollision:
    """
    Regression for TASK-023 M1: POST /scim/v2/Users with an email belonging to
    a user who was soft-deleted via the admin path (is_deleted=True) must return
    409 Uniqueness, NOT 500 IntegrityError.

    Background: User.email has unique=True at the DB level across ALL rows,
    including soft-deleted ones.  The old duplicate check used
    ``User.objects.all_tenants()`` which calls ``.alive()`` — excluding
    ``is_deleted=True`` rows — so the pre-check would pass and
    ``create_user`` would raise IntegrityError → 500.

    Note: SCIM DELETE (deprovision) only sets ``is_active=False``, so it is NOT
    affected by this bug (those rows still appear in ``.alive()``).  This
    regression covers the admin-soft-delete path (``is_deleted=True``).
    """

    @staticmethod
    def _post(path: str, data: dict, raw_token: str):
        c = Client()
        return c.post(
            path,
            data=data,
            content_type="application/scim+json",
            HTTP_AUTHORIZATION=f"Bearer {raw_token}",
        )

    def test_post_with_admin_soft_deleted_email_returns_409_not_500(self):
        """
        POST after admin-soft-delete of a user with the same email must return
        409 (uniqueness collision), not 500 (IntegrityError from DB constraint).
        """
        from apps.users.scim_models import SCIMToken

        tenant = _make_tenant()
        admin = _make_admin(tenant)
        raw, _ = SCIMToken.generate(tenant=tenant, name="TestIdP", created_by=admin)

        # Create a teacher then soft-delete via admin path (sets is_deleted=True)
        teacher = _make_teacher(tenant, email="zombie-sdm1@test.com")
        teacher.is_deleted = True
        teacher.is_active = False
        teacher.save(update_fields=["is_deleted", "is_active"])

        payload = {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
            "userName": "zombie-sdm1@test.com",
            "name": {"givenName": "New", "familyName": "Zombie"},
            "active": True,
        }
        resp = self._post("/scim/v2/Users", payload, raw)
        assert resp.status_code == 409, (
            f"Expected 409 for admin-soft-deleted email, got {resp.status_code}. "
            "This is M1 regression: all_tenants() excludes is_deleted rows → IntegrityError."
        )

    def test_post_with_admin_soft_deleted_email_returns_scim_error_envelope(self):
        """409 response must be a valid SCIM error body with scimType=uniqueness."""
        from apps.users.scim_models import SCIMToken

        tenant = _make_tenant()
        admin = _make_admin(tenant)
        raw, _ = SCIMToken.generate(tenant=tenant, name="TestIdP", created_by=admin)

        teacher = _make_teacher(tenant, email="zombie-sdm2@test.com")
        teacher.is_deleted = True
        teacher.is_active = False
        teacher.save(update_fields=["is_deleted", "is_active"])

        payload = {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
            "userName": "zombie-sdm2@test.com",
            "name": {"givenName": "New", "familyName": "Zombie"},
            "active": True,
        }
        resp = self._post("/scim/v2/Users", payload, raw)
        data = resp.json()
        assert "schemas" in data
        assert "urn:ietf:params:scim:api:messages:2.0:Error" in data["schemas"]
        assert data.get("scimType") == "uniqueness"

    def test_post_with_cross_tenant_soft_deleted_email_returns_400_not_500(self):
        """
        POST for an email that belongs to a soft-deleted user in ANOTHER tenant
        must return 400 invalidValue (no enumeration leak), NOT 500 IntegrityError.
        """
        from apps.users.scim_models import SCIMToken

        tenant_a = _make_tenant()
        tenant_b = _make_tenant()
        admin_a = _make_admin(tenant_a)
        admin_b = _make_admin(tenant_b)
        raw_a, _ = SCIMToken.generate(tenant=tenant_a, name="IdP-A", created_by=admin_a)

        # Create user in tenant B then soft-delete via admin path
        user_b = _make_teacher(tenant_b, email="zombie-sdm3@test.com")
        user_b.is_deleted = True
        user_b.is_active = False
        user_b.save(update_fields=["is_deleted", "is_active"])

        # Attempt to provision same email in tenant A
        payload = {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
            "userName": "zombie-sdm3@test.com",
            "name": {"givenName": "New", "familyName": "InA"},
            "active": True,
        }
        resp = self._post("/scim/v2/Users", payload, raw_a)
        assert resp.status_code == 400, (
            f"Expected 400 for cross-tenant soft-deleted email, got {resp.status_code}. "
            "This is M1 cross-tenant variant: must not 500 on IntegrityError."
        )
        data = resp.json()
        # Body must NOT leak the email address
        body_text = resp.content.decode()
        assert "zombie-sdm3@test.com" not in body_text, (
            "Response body must not contain the email (enumeration leak)"
        )

    def test_post_cross_tenant_live_email_returns_400_no_email_in_body(self):
        """
        POST for an email that belongs to an active user in ANOTHER tenant
        must return 400 invalidValue and body must NOT contain the email
        (prevents cross-tenant user enumeration).
        """
        from apps.users.scim_models import SCIMToken

        tenant_a = _make_tenant()
        tenant_b = _make_tenant()
        admin_a = _make_admin(tenant_a)
        admin_b = _make_admin(tenant_b)
        raw_a, _ = SCIMToken.generate(tenant=tenant_a, name="IdP-A", created_by=admin_a)

        # Create an active user in tenant B (not deleted)
        _make_teacher(tenant_b, email="active-b@test.com")

        payload = {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
            "userName": "active-b@test.com",
            "name": {"givenName": "X", "familyName": "Y"},
            "active": True,
        }
        resp = self._post("/scim/v2/Users", payload, raw_a)
        assert resp.status_code == 400, (
            f"Expected 400 for cross-tenant email collision, got {resp.status_code}"
        )
        # Body must NOT leak the email address
        body_text = resp.content.decode()
        assert "active-b@test.com" not in body_text, (
            "Response body must not contain the email (enumeration leak)"
        )
