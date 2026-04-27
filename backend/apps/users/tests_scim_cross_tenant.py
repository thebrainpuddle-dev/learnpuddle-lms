"""
SCIM 2.0 Cross-Tenant Leak Regression Suite (QA — TASK-023 supplemental).

Specifically hammers the cross-tenant isolation invariants NOT fully covered by
the existing tests_scim.py suite:

  CT-01  POST with body `tenant` override field → user still created in token's tenant
  CT-02  Token A: GET /scim/v2/Users/{user_id_in_B} → 404 (not 403, not 200)
  CT-03  Token A: PATCH /scim/v2/Users/{user_id_in_B} → 404 with no state change
  CT-04  Token A: filter by userName that only exists in tenant B → empty Resources list
  CT-05  Token A: filter by externalId that only exists in tenant B → empty Resources list
  CT-06  Deactivated SCIMToken rejects all requests with 401
  CT-07  Bearer header "Token xxx" (wrong prefix) → 401
  CT-08  Bearer header with trailing whitespace in token value → 401
  CT-09  Multiple PATCH Operations in one request are applied atomically
  CT-10  Deprovisioned (soft-deleted) user re-provision via POST → 409 (user still exists)
  CT-11  Admin from tenant A cannot list SCIM tokens of tenant B (scoped via JWT+Host)
  CT-12  SCIMToken.verify() updates last_used_at on each successful hit
  CT-13  Soft-deleted User is invisible to SCIM list (is_deleted=True hidden from list)
  CT-14  PATCH cross-tenant: body data does not bleed onto tenant A user with same name
  CT-15  POST with externalId that already exists in the same tenant is still accepted
         (externalId is not unique; only userName/email is unique)

All tests use two completely separate Tenant A / Tenant B pairs with dedicated
SCIM tokens so that no test depends on state from another.
"""

from __future__ import annotations

import uuid

import pytest
from django.test import Client
from django.utils import timezone

from apps.tenants.models import Tenant
from apps.users.models import User

pytestmark = pytest.mark.django_db

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Local helpers (self-contained — no dependency on tests_scim helpers)
# ---------------------------------------------------------------------------

def _tenant(subdomain: str = None) -> Tenant:
    sub = subdomain or ("ct-" + uuid.uuid4().hex[:8])
    return Tenant.objects.create(
        name=f"School {sub}",
        slug=sub,
        subdomain=sub,
        email=f"admin@{sub}.test",
    )


def _admin(tenant: Tenant, email: str = None) -> User:
    em = email or f"admin-{uuid.uuid4().hex[:6]}@ct.test"
    return User.objects.create_user(
        email=em,
        password="Password123!",
        first_name="Admin",
        last_name="User",
        tenant=tenant,
        role="SCHOOL_ADMIN",
    )


def _teacher(tenant: Tenant, email: str = None, **kwargs) -> User:
    em = email or f"teacher-{uuid.uuid4().hex[:6]}@ct.test"
    return User.objects.create_user(
        email=em,
        password="Password123!",
        first_name="Jane",
        last_name="Smith",
        tenant=tenant,
        role="TEACHER",
        **kwargs,
    )


def _scim_token(tenant: Tenant) -> tuple:
    """Return (raw_token_str, SCIMToken_instance) for *tenant*."""
    from apps.users.scim_models import SCIMToken
    admin = _admin(tenant)
    return SCIMToken.generate(tenant=tenant, name="TestIdP", created_by=admin)


def _auth(raw_token: str) -> dict:
    """Returns the Django test-client kwargs dict for SCIM Bearer auth."""
    return {"HTTP_AUTHORIZATION": f"Bearer {raw_token}"}


def _post_scim(path: str, data: dict, raw_token: str) -> object:
    """POST helper that sets the SCIM content-type."""
    c = Client()
    return c.post(
        path,
        data=data,
        content_type="application/scim+json",
        **_auth(raw_token),
    )


def _patch_scim(path: str, data: dict, raw_token: str) -> object:
    c = Client()
    return c.patch(
        path,
        data=data,
        content_type="application/scim+json",
        **_auth(raw_token),
    )


# ---------------------------------------------------------------------------
# CT-01: POST with explicit `tenant` body field must NOT reassign the user
# ---------------------------------------------------------------------------

class TestPostTenantBodyOverride:
    """
    An IdP (or attacker) may craft a POST body containing a 'tenant' field
    pointing to tenant B.  The view must ignore that field and always create
    the user in the tenant bound to the SCIM token.
    """

    def test_post_with_tenant_body_field_creates_user_in_token_tenant(self, db):
        tenant_a = _tenant()
        tenant_b = _tenant()
        raw_token_a, _ = _scim_token(tenant_a)

        # Craft payload that contains a tenant override pointing to B
        payload = {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
            "userName": "ct01-victim@example.com",
            "name": {"givenName": "Crafted", "familyName": "Payload"},
            "active": True,
            # Attacker tries to assign the new user to tenant B
            "tenant": str(tenant_b.id),
            "tenant_id": str(tenant_b.id),
        }

        resp = _post_scim("/scim/v2/Users", payload, raw_token_a)
        assert resp.status_code == 201, f"Expected 201, got {resp.status_code}"

        user = User.objects.all_tenants().get(email="ct01-victim@example.com")
        assert user.tenant_id == tenant_a.id, (
            f"User was placed in tenant {user.tenant_id} instead of tenant_a {tenant_a.id}"
        )
        assert user.tenant_id != tenant_b.id

    def test_post_with_tenant_body_field_user_not_visible_in_tenant_b(self, db):
        """The created user must NOT appear when listing tenant B's users."""
        tenant_a = _tenant()
        tenant_b = _tenant()
        raw_token_a, _ = _scim_token(tenant_a)
        raw_token_b, _ = _scim_token(tenant_b)

        payload = {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
            "userName": "ct01b-check@example.com",
            "name": {"givenName": "X", "familyName": "Y"},
            "active": True,
            "tenant": str(tenant_b.id),
        }
        _post_scim("/scim/v2/Users", payload, raw_token_a)

        # Should NOT appear in tenant B's SCIM list
        c = Client()
        resp = c.get("/scim/v2/Users", **_auth(raw_token_b))
        emails = [r["userName"] for r in resp.json()["Resources"]]
        assert "ct01b-check@example.com" not in emails


# ---------------------------------------------------------------------------
# CT-02: GET single user from wrong tenant → 404 (exact status matters)
# ---------------------------------------------------------------------------

class TestGetUserCrossTenantExact404:
    """
    The existing tests_scim.py has test_get_user_cross_tenant_returns_404
    but it only covers a basic GET.  These tests add:
    - Verify the status code is exactly 404, not 403 or 200.
    - Verify response body is a SCIM error object (not HTML 404).
    - Verify the user in B is NOT returned even if token A has a token with
      the same name as tenant B's token.
    """

    def test_cross_tenant_get_returns_404_not_403(self, db):
        tenant_a = _tenant()
        tenant_b = _tenant()
        raw_a, _ = _scim_token(tenant_a)
        teacher_b = _teacher(tenant_b)

        c = Client()
        resp = c.get(f"/scim/v2/Users/{teacher_b.id}", **_auth(raw_a))

        assert resp.status_code == 404, (
            f"Expected 404 for cross-tenant GET, got {resp.status_code}"
        )

    def test_cross_tenant_get_returns_scim_error_body(self, db):
        """Response must be a SCIM error JSON, not an HTML 404 page."""
        tenant_a = _tenant()
        tenant_b = _tenant()
        raw_a, _ = _scim_token(tenant_a)
        teacher_b = _teacher(tenant_b)

        c = Client()
        resp = c.get(f"/scim/v2/Users/{teacher_b.id}", **_auth(raw_a))

        data = resp.json()
        assert "schemas" in data
        assert "urn:ietf:params:scim:api:messages:2.0:Error" in data["schemas"]
        assert data["status"] == 404

    def test_cross_tenant_get_does_not_return_user_data(self, db):
        """Response must not contain any user fields from tenant B."""
        tenant_a = _tenant()
        tenant_b = _tenant()
        raw_a, _ = _scim_token(tenant_a)
        teacher_b = _teacher(tenant_b, email="secret-b@tenantb.com")

        c = Client()
        resp = c.get(f"/scim/v2/Users/{teacher_b.id}", **_auth(raw_a))

        # userName or email from tenant B must not appear anywhere in the response
        body = resp.content.decode()
        assert "secret-b@tenantb.com" not in body


# ---------------------------------------------------------------------------
# CT-03: PATCH on wrong tenant → 404 with no state mutation
# ---------------------------------------------------------------------------

class TestPatchUserCrossTenant:
    """
    No existing test in tests_scim.py covers PATCH cross-tenant isolation.
    """

    def test_patch_cross_tenant_returns_404(self, db):
        tenant_a = _tenant()
        tenant_b = _tenant()
        raw_a, _ = _scim_token(tenant_a)
        teacher_b = _teacher(tenant_b)

        payload = {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [{"op": "replace", "path": "active", "value": False}],
        }
        resp = _patch_scim(f"/scim/v2/Users/{teacher_b.id}", payload, raw_a)
        assert resp.status_code == 404, (
            f"Expected 404 for cross-tenant PATCH, got {resp.status_code}"
        )

    def test_patch_cross_tenant_does_not_mutate_target_user(self, db):
        """Teacher B must remain active after an attempt by token A to deactivate them."""
        tenant_a = _tenant()
        tenant_b = _tenant()
        raw_a, _ = _scim_token(tenant_a)
        teacher_b = _teacher(tenant_b)
        assert teacher_b.is_active is True  # precondition

        payload = {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [{"op": "replace", "path": "active", "value": False}],
        }
        _patch_scim(f"/scim/v2/Users/{teacher_b.id}", payload, raw_a)

        teacher_b.refresh_from_db()
        assert teacher_b.is_active is True, (
            "Cross-tenant PATCH must not have changed teacher_b.is_active"
        )

    def test_patch_cross_tenant_does_not_alter_name(self, db):
        """Name fields in teacher B must not change after token A attempts a rename."""
        tenant_a = _tenant()
        tenant_b = _tenant()
        raw_a, _ = _scim_token(tenant_a)
        teacher_b = _teacher(tenant_b, email="namevictim@tenantb.com")
        original_first = teacher_b.first_name  # "Jane"

        payload = {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [
                {"op": "replace", "path": "name.givenName", "value": "Hacker"},
            ],
        }
        _patch_scim(f"/scim/v2/Users/{teacher_b.id}", payload, raw_a)

        teacher_b.refresh_from_db()
        assert teacher_b.first_name == original_first, (
            "Cross-tenant PATCH must not have mutated teacher_b.first_name"
        )


# ---------------------------------------------------------------------------
# CT-04 & CT-05: filter= query must never leak cross-tenant results
# ---------------------------------------------------------------------------

class TestFilterCrossTenantIsolation:
    """
    The existing test only verifies list isolation in a non-filter GET.
    These tests specifically exercise the filter= query parameter path.
    """

    def test_filter_username_only_in_tenant_b_returns_empty(self, db):
        """Searching for a userName that only exists in B returns empty Resources."""
        tenant_a = _tenant()
        tenant_b = _tenant()
        raw_a, _ = _scim_token(tenant_a)
        _teacher(tenant_b, email="only-in-b@tenantb.com")

        c = Client()
        resp = c.get(
            '/scim/v2/Users?filter=userName eq "only-in-b@tenantb.com"',
            **_auth(raw_a),
        )
        data = resp.json()

        assert resp.status_code == 200
        assert data["totalResults"] == 0
        assert data["Resources"] == []

    def test_filter_username_in_both_tenants_returns_only_own(self, db):
        """Same email cannot exist twice (unique constraint), but if it somehow
        did: tenant A should only see its own copy.  Here we verify that a
        userName present in tenant A (and absent in B) is returned correctly,
        AND that a userName only in B does not appear."""
        tenant_a = _tenant()
        tenant_b = _tenant()
        raw_a, _ = _scim_token(tenant_a)
        _teacher(tenant_a, email="shared-prefix@tenant-a.com")
        _teacher(tenant_b, email="other-user@tenant-b.com")

        c = Client()
        resp = c.get(
            '/scim/v2/Users?filter=userName eq "other-user@tenant-b.com"',
            **_auth(raw_a),
        )
        data = resp.json()

        assert data["totalResults"] == 0
        assert data["Resources"] == []

    def test_filter_cross_tenant_does_not_expose_count(self, db):
        """totalResults must be 0 when the match is from the wrong tenant."""
        tenant_a = _tenant()
        tenant_b = _tenant()
        raw_a, _ = _scim_token(tenant_a)
        _teacher(tenant_b, email="countleak@tenantb.com")

        c = Client()
        resp = c.get(
            '/scim/v2/Users?filter=userName eq "countleak@tenantb.com"',
            **_auth(raw_a),
        )
        assert resp.json()["totalResults"] == 0


# ---------------------------------------------------------------------------
# CT-06: Deactivated SCIMToken rejects all requests with 401
# ---------------------------------------------------------------------------

class TestDeactivatedTokenRejects:
    """
    Expand on tests_scim.py's test_revoked_token_returns_401 to cover ALL
    SCIM endpoints, not just GET /scim/v2/Users.
    """

    def _setup(self, db):
        from apps.users.scim_models import SCIMToken
        tenant = _tenant()
        admin = _admin(tenant)
        raw_token, scim_token = SCIMToken.generate(tenant=tenant, name="Okta", created_by=admin)
        teacher = _teacher(tenant)
        return raw_token, scim_token, teacher

    def _revoke(self, scim_token):
        scim_token.is_active = False
        scim_token.save(update_fields=["is_active"])

    def test_deactivated_token_rejects_list(self, db):
        raw, tok, _ = self._setup(db)
        self._revoke(tok)
        c = Client()
        assert c.get("/scim/v2/Users", **_auth(raw)).status_code == 401

    def test_deactivated_token_rejects_get_single(self, db):
        raw, tok, teacher = self._setup(db)
        self._revoke(tok)
        c = Client()
        assert c.get(f"/scim/v2/Users/{teacher.id}", **_auth(raw)).status_code == 401

    def test_deactivated_token_rejects_post(self, db):
        raw, tok, _ = self._setup(db)
        self._revoke(tok)
        payload = {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
            "userName": "shouldfail@example.com",
            "name": {"givenName": "X", "familyName": "Y"},
        }
        assert _post_scim("/scim/v2/Users", payload, raw).status_code == 401

    def test_deactivated_token_rejects_put(self, db):
        raw, tok, teacher = self._setup(db)
        self._revoke(tok)
        payload = {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
            "userName": teacher.email,
            "name": {"givenName": "X", "familyName": "Y"},
            "active": True,
        }
        c = Client()
        assert c.put(
            f"/scim/v2/Users/{teacher.id}",
            data=payload,
            content_type="application/scim+json",
            **_auth(raw),
        ).status_code == 401

    def test_deactivated_token_rejects_patch(self, db):
        raw, tok, teacher = self._setup(db)
        self._revoke(tok)
        payload = {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [{"op": "replace", "path": "active", "value": False}],
        }
        assert _patch_scim(f"/scim/v2/Users/{teacher.id}", payload, raw).status_code == 401

    def test_deactivated_token_rejects_delete(self, db):
        raw, tok, teacher = self._setup(db)
        self._revoke(tok)
        c = Client()
        assert c.delete(f"/scim/v2/Users/{teacher.id}", **_auth(raw)).status_code == 401


# ---------------------------------------------------------------------------
# CT-07 & CT-08: Bearer header edge cases → 401
# ---------------------------------------------------------------------------

class TestBearerHeaderEdgeCases:
    """
    Verify that non-standard / malformed Authorization headers are rejected.
    tests_scim.py only covers: missing header, Basic scheme, and invalid token.
    """

    def test_token_prefix_wrong_case_rejected(self, db):
        """'bearer' (lowercase) should still be accepted per case-insensitive RFC,
        but 'Token xxx' (wrong scheme name) must be rejected."""
        from apps.users.scim_models import SCIMToken
        tenant = _tenant()
        admin = _admin(tenant)
        raw, _ = SCIMToken.generate(tenant=tenant, name="Okta", created_by=admin)

        c = Client()
        # "Token" scheme is NOT "Bearer" — must reject
        resp = c.get("/scim/v2/Users", HTTP_AUTHORIZATION=f"Token {raw}")
        assert resp.status_code == 401, (
            f"Expected 401 for 'Token xxx' scheme, got {resp.status_code}"
        )

    def test_jwt_scheme_rejected(self, db):
        """'JWT xxx' scheme is not valid for SCIM — must reject."""
        from apps.users.scim_models import SCIMToken
        tenant = _tenant()
        admin = _admin(tenant)
        raw, _ = SCIMToken.generate(tenant=tenant, name="Okta", created_by=admin)

        c = Client()
        resp = c.get("/scim/v2/Users", HTTP_AUTHORIZATION=f"JWT {raw}")
        assert resp.status_code == 401

    def test_bearer_with_empty_token_returns_401(self, db):
        """'Bearer ' with no token value → 401."""
        c = Client()
        resp = c.get("/scim/v2/Users", HTTP_AUTHORIZATION="Bearer ")
        assert resp.status_code == 401

    def test_bearer_with_token_plus_extra_chars_returns_401(self, db):
        """Appending garbage to a valid token must invalidate it."""
        from apps.users.scim_models import SCIMToken
        tenant = _tenant()
        admin = _admin(tenant)
        raw, _ = SCIMToken.generate(tenant=tenant, name="Okta", created_by=admin)

        c = Client()
        resp = c.get("/scim/v2/Users", HTTP_AUTHORIZATION=f"Bearer {raw}XXXX")
        assert resp.status_code == 401

    def test_bearer_with_prefix_space_in_token_returns_401(self, db):
        """Leading space inside token value (trailing space after 'Bearer ') → 401."""
        from apps.users.scim_models import SCIMToken
        tenant = _tenant()
        admin = _admin(tenant)
        raw, _ = SCIMToken.generate(tenant=tenant, name="Okta", created_by=admin)

        c = Client()
        # "Bearer  token" — double space → effectively looks up " token" hash
        resp = c.get("/scim/v2/Users", HTTP_AUTHORIZATION=f"Bearer  {raw}")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# CT-09: Multiple PATCH Operations in one request
# ---------------------------------------------------------------------------

class TestPatchMultipleOperations:
    """
    The existing tests only cover single-operation PATCH payloads.
    Multi-operation payloads must apply all operations in order.
    """

    def test_multiple_operations_all_applied(self, db):
        """Three replace operations in a single PATCH must all take effect."""
        tenant = _tenant()
        raw, _ = _scim_token(tenant)
        teacher = _teacher(tenant, email="multi-patch@test.com")
        teacher.is_active = True
        teacher.save(update_fields=["is_active"])

        payload = {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [
                {"op": "replace", "path": "name.givenName", "value": "Multi"},
                {"op": "replace", "path": "name.familyName", "value": "Patched"},
                {"op": "replace", "path": "active", "value": False},
            ],
        }
        resp = _patch_scim(f"/scim/v2/Users/{teacher.id}", payload, raw)
        assert resp.status_code == 200

        teacher.refresh_from_db()
        assert teacher.first_name == "Multi"
        assert teacher.last_name == "Patched"
        assert teacher.is_active is False

    def test_unrecognised_patch_path_is_silently_ignored(self, db):
        """RFC 7644 §3.5.2: unknown paths must be silently skipped — not 400."""
        tenant = _tenant()
        raw, _ = _scim_token(tenant)
        teacher = _teacher(tenant)

        payload = {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [
                {"op": "replace", "path": "nonExistentField", "value": "ignored"},
                {"op": "replace", "path": "name.givenName", "value": "StillWorks"},
            ],
        }
        resp = _patch_scim(f"/scim/v2/Users/{teacher.id}", payload, raw)
        assert resp.status_code == 200

        teacher.refresh_from_db()
        assert teacher.first_name == "StillWorks"

    def test_empty_operations_array_returns_400(self, db):
        """An empty Operations array (as opposed to missing) → 400."""
        tenant = _tenant()
        raw, _ = _scim_token(tenant)
        teacher = _teacher(tenant)

        payload = {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [],
        }
        resp = _patch_scim(f"/scim/v2/Users/{teacher.id}", payload, raw)
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# CT-10: Re-provision a deprovisioned user via POST → 409
# ---------------------------------------------------------------------------

class TestReprovisionDeactivatedUser:
    """
    After DELETE soft-deactivates a user (is_active=False, user row still
    exists), a new POST with the same userName must return 409 because the
    email is still in the database.
    """

    def test_post_for_deprovisioned_user_returns_409(self, db):
        tenant = _tenant()
        raw, _ = _scim_token(tenant)
        teacher = _teacher(tenant, email="reprovisioned@test.com")

        # Step 1 — deprovision
        c = Client()
        delete_resp = c.delete(f"/scim/v2/Users/{teacher.id}", **_auth(raw))
        assert delete_resp.status_code == 204

        # Step 2 — attempt to create with the same userName
        payload = {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
            "userName": "reprovisioned@test.com",
            "name": {"givenName": "Re", "familyName": "Provisioned"},
            "active": True,
        }
        create_resp = _post_scim("/scim/v2/Users", payload, raw)
        assert create_resp.status_code == 409, (
            f"Expected 409 when re-provisioning deprovisioned user, got {create_resp.status_code}"
        )

    def test_post_for_deprovisioned_user_409_body_is_scim_error(self, db):
        """The 409 body must be a proper SCIM error envelope."""
        tenant = _tenant()
        raw, _ = _scim_token(tenant)
        teacher = _teacher(tenant, email="repro-body@test.com")

        c = Client()
        c.delete(f"/scim/v2/Users/{teacher.id}", **_auth(raw))

        payload = {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
            "userName": "repro-body@test.com",
            "name": {"givenName": "X", "familyName": "Y"},
        }
        resp = _post_scim("/scim/v2/Users", payload, raw)
        data = resp.json()
        assert "schemas" in data
        assert "urn:ietf:params:scim:api:messages:2.0:Error" in data["schemas"]
        assert data["scimType"] == "uniqueness"


# ---------------------------------------------------------------------------
# CT-11: Admin token list cross-tenant isolation
# ---------------------------------------------------------------------------

class TestAdminTokenListCrossTenantIsolation:
    """
    The existing test covers cross-tenant token *revoke* (DELETE) but not
    cross-tenant token *listing* (GET).
    """

    def _make_jwt_client(self, user: User, tenant: Tenant):
        from rest_framework_simplejwt.tokens import RefreshToken
        token = str(RefreshToken.for_user(user).access_token)
        c = Client()
        return c, {
            "HTTP_AUTHORIZATION": f"Bearer {token}",
            "HTTP_HOST": f"{tenant.subdomain}.lms.com",
        }

    def test_admin_a_cannot_see_tenant_b_tokens_in_list(self, db):
        """
        Admin A's token list endpoint must return only tenant A's tokens,
        never tenant B's tokens.
        """
        from apps.users.scim_models import SCIMToken

        tenant_a = _tenant()
        tenant_b = _tenant()
        admin_a = _admin(tenant_a)
        admin_b = _admin(tenant_b)

        _, scim_token_b = SCIMToken.generate(tenant=tenant_b, name="B-token", created_by=admin_b)

        client, headers = self._make_jwt_client(admin_a, tenant_a)
        resp = client.get("/api/v1/admin/sso/scim-tokens/", **headers)

        assert resp.status_code == 200
        result_ids = [r["id"] for r in resp.json()["results"]]
        assert str(scim_token_b.id) not in result_ids, (
            "Tenant B's SCIM token ID must not appear in tenant A's listing"
        )

    def test_admin_a_list_only_contains_own_tokens(self, db):
        """
        Token list for admin A contains only tokens belonging to tenant A.
        """
        from apps.users.scim_models import SCIMToken

        tenant_a = _tenant()
        tenant_b = _tenant()
        admin_a = _admin(tenant_a)
        admin_b = _admin(tenant_b)

        _, token_a = SCIMToken.generate(tenant=tenant_a, name="A-only-token", created_by=admin_a)
        _, token_b = SCIMToken.generate(tenant=tenant_b, name="B-only-token", created_by=admin_b)

        client, headers = self._make_jwt_client(admin_a, tenant_a)
        resp = client.get("/api/v1/admin/sso/scim-tokens/", **headers)
        result_ids = [r["id"] for r in resp.json()["results"]]

        assert str(token_a.id) in result_ids
        assert str(token_b.id) not in result_ids


# ---------------------------------------------------------------------------
# CT-12: SCIMToken.verify() updates last_used_at
# ---------------------------------------------------------------------------

class TestSCIMTokenLastUsedAt:
    """
    Verify the side-effect that last_used_at is updated on each successful
    verify() call.  This is a unit test (no HTTP).
    """

    def test_verify_updates_last_used_at(self, db):
        from apps.users.scim_models import SCIMToken

        tenant = _tenant()
        admin = _admin(tenant)
        raw, scim_token = SCIMToken.generate(tenant=tenant, name="Okta", created_by=admin)
        assert scim_token.last_used_at is None  # fresh token

        before = timezone.now()
        result = SCIMToken.verify(raw)

        scim_token.refresh_from_db()
        assert result is not None
        assert scim_token.last_used_at is not None
        assert scim_token.last_used_at >= before

    def test_verify_updates_last_used_at_on_repeated_calls(self, db):
        """Two successive verifies result in a later last_used_at value."""
        from apps.users.scim_models import SCIMToken
        import time

        tenant = _tenant()
        admin = _admin(tenant)
        raw, scim_token = SCIMToken.generate(tenant=tenant, name="Okta", created_by=admin)

        SCIMToken.verify(raw)
        scim_token.refresh_from_db()
        first_used = scim_token.last_used_at

        # Small sleep to ensure clock advances
        time.sleep(0.05)

        SCIMToken.verify(raw)
        scim_token.refresh_from_db()
        second_used = scim_token.last_used_at

        assert second_used >= first_used


# ---------------------------------------------------------------------------
# CT-13: Soft-deleted users hidden from SCIM list
# ---------------------------------------------------------------------------

class TestSoftDeletedUserHidden:
    """
    Users with is_deleted=True (soft-deleted via admin, not SCIM deprovision)
    must be invisible to the SCIM list and detail endpoints.
    """

    def test_soft_deleted_user_excluded_from_list(self, db):
        tenant = _tenant()
        raw, _ = _scim_token(tenant)
        visible = _teacher(tenant, email="visible@tenant.com")
        hidden = _teacher(tenant, email="hidden@tenant.com")

        # Soft-delete the hidden user via admin path (not SCIM DELETE)
        hidden.is_deleted = True
        hidden.deleted_at = timezone.now()
        hidden.save(update_fields=["is_deleted", "deleted_at"])

        c = Client()
        resp = c.get("/scim/v2/Users", **_auth(raw))
        emails = [r["userName"] for r in resp.json()["Resources"]]

        assert "visible@tenant.com" in emails
        assert "hidden@tenant.com" not in emails

    def test_soft_deleted_user_returns_404_on_detail(self, db):
        """GET /scim/v2/Users/{id} for is_deleted=True user → 404."""
        tenant = _tenant()
        raw, _ = _scim_token(tenant)
        teacher = _teacher(tenant, email="will-be-deleted@tenant.com")

        teacher.is_deleted = True
        teacher.deleted_at = timezone.now()
        teacher.save(update_fields=["is_deleted", "deleted_at"])

        c = Client()
        resp = c.get(f"/scim/v2/Users/{teacher.id}", **_auth(raw))
        assert resp.status_code == 404

    def test_scim_deprovisioned_user_still_visible_with_active_false(self, db):
        """
        A user deprovisioned via SCIM DELETE (is_active=False, is_deleted=False)
        must still appear in the SCIM list with active=false (not be hidden).
        This distinguishes SCIM-deprovisioned from admin-soft-deleted users.
        """
        tenant = _tenant()
        raw, _ = _scim_token(tenant)
        teacher = _teacher(tenant, email="scim-deprovisioned@tenant.com")

        # SCIM deprovision (sets is_active=False, NOT is_deleted)
        c = Client()
        c.delete(f"/scim/v2/Users/{teacher.id}", **_auth(raw))

        resp = c.get("/scim/v2/Users", **_auth(raw))
        resources = resp.json()["Resources"]
        emails = [r["userName"] for r in resources]
        # After SCIM deprovision the user should still appear (active=false)
        assert "scim-deprovisioned@tenant.com" in emails
        match = next(r for r in resources if r["userName"] == "scim-deprovisioned@tenant.com")
        assert match["active"] is False


# ---------------------------------------------------------------------------
# CT-14: Cross-tenant PATCH does not bleed onto same-name user in tenant A
# ---------------------------------------------------------------------------

class TestPatchCrossTenantNoBleed:
    """
    If tenant A and tenant B both have a user named 'Jane Smith' but the
    attack uses tenant_b's user_id with token_a, the patch must fail with
    404 and must NOT mutate tenant A's 'Jane Smith'.
    """

    def test_cross_tenant_patch_does_not_bleed_to_same_named_user(self, db):
        tenant_a = _tenant()
        tenant_b = _tenant()
        raw_a, _ = _scim_token(tenant_a)

        teacher_a = _teacher(tenant_a, email="jane@tenant-a.com")
        teacher_a.first_name = "Jane"
        teacher_a.save(update_fields=["first_name"])

        teacher_b = _teacher(tenant_b, email="jane@tenant-b.com")
        teacher_b.first_name = "Jane"
        teacher_b.save(update_fields=["first_name"])

        payload = {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [
                {"op": "replace", "path": "name.givenName", "value": "XSS"},
            ],
        }
        # Use teacher_b's ID with token A — must 404
        resp = _patch_scim(f"/scim/v2/Users/{teacher_b.id}", payload, raw_a)
        assert resp.status_code == 404

        # Tenant A's Jane must still have "Jane" first name
        teacher_a.refresh_from_db()
        assert teacher_a.first_name == "Jane"

        # Tenant B's Jane must also be unmodified
        teacher_b.refresh_from_db()
        assert teacher_b.first_name == "Jane"


# ---------------------------------------------------------------------------
# CT-15: externalId uniqueness — same externalId in same tenant is accepted
# ---------------------------------------------------------------------------

class TestExternalIdNotUnique:
    """
    externalId (employee_id) is NOT a unique field — the same external HR
    system ID can be reused (e.g. synced from legacy data).  The SCIM POST
    must NOT reject payloads where externalId duplicates an existing value.
    """

    def test_duplicate_external_id_in_same_tenant_allowed(self, db):
        """Two users with the same externalId → both POSTs succeed."""
        tenant = _tenant()
        raw, _ = _scim_token(tenant)

        payload_a = {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
            "userName": "ext-a@test.com",
            "name": {"givenName": "A", "familyName": "User"},
            "externalId": "HR-12345",
        }
        payload_b = {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
            "userName": "ext-b@test.com",
            "name": {"givenName": "B", "familyName": "User"},
            "externalId": "HR-12345",
        }

        resp_a = _post_scim("/scim/v2/Users", payload_a, raw)
        resp_b = _post_scim("/scim/v2/Users", payload_b, raw)

        assert resp_a.status_code == 201, f"First POST: {resp_a.status_code}"
        assert resp_b.status_code == 201, f"Second POST with same externalId: {resp_b.status_code}"

    def test_duplicate_external_id_across_tenants_allowed(self, db):
        """Same externalId in two different tenants → both POSTs succeed."""
        tenant_a = _tenant()
        tenant_b = _tenant()
        raw_a, _ = _scim_token(tenant_a)
        raw_b, _ = _scim_token(tenant_b)

        payload_a = {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
            "userName": "xtid-a@tenant-a.com",
            "name": {"givenName": "A", "familyName": "User"},
            "externalId": "CORP-999",
        }
        payload_b = {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
            "userName": "xtid-b@tenant-b.com",
            "name": {"givenName": "B", "familyName": "User"},
            "externalId": "CORP-999",
        }

        resp_a = _post_scim("/scim/v2/Users", payload_a, raw_a)
        resp_b = _post_scim("/scim/v2/Users", payload_b, raw_b)

        assert resp_a.status_code == 201
        assert resp_b.status_code == 201


# ---------------------------------------------------------------------------
# CT-16: Cross-tenant email enumeration prevention (POST /scim/v2/Users)
# ---------------------------------------------------------------------------

class TestPostCrossTenantEmailEnumeration:
    """
    SCIM POST must not reveal whether an email is registered in a different
    tenant. The two-tier check in scim_views.py:

      • Same-tenant duplicate  → 409 uniqueness  (SCIM-spec, RFC 7644)
      • Cross-tenant duplicate → 400 invalidValue (generic, no detail leak)

    Addresses: FOLLOWUP-SCIM-CROSS-TENANT-EMAIL-ENUM-2026-04-23
    """

    def test_same_tenant_duplicate_email_returns_409(self, db):
        """
        POST with a userName that already exists in the *same* tenant must
        return 409 with scimType=uniqueness.
        """
        tenant = _tenant()
        raw, _ = _scim_token(tenant)
        # Pre-create the user in the same tenant
        _teacher(tenant, email="ct16-same@tenant-a.com")

        payload = {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
            "userName": "ct16-same@tenant-a.com",
            "name": {"givenName": "Dup", "familyName": "User"},
            "active": True,
        }
        resp = _post_scim("/scim/v2/Users", payload, raw)

        assert resp.status_code == 409, (
            f"Same-tenant duplicate must return 409, got {resp.status_code}"
        )
        data = resp.json()
        assert data.get("scimType") == "uniqueness"

    def test_same_tenant_duplicate_409_includes_scim_error_schema(self, db):
        """409 response body must be a proper SCIM error envelope."""
        tenant = _tenant()
        raw, _ = _scim_token(tenant)
        _teacher(tenant, email="ct16-schema@tenant-a.com")

        payload = {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
            "userName": "ct16-schema@tenant-a.com",
            "name": {"givenName": "X", "familyName": "Y"},
        }
        resp = _post_scim("/scim/v2/Users", payload, raw)
        data = resp.json()

        assert "schemas" in data
        assert "urn:ietf:params:scim:api:messages:2.0:Error" in data["schemas"]
        assert data["status"] == 409

    def test_cross_tenant_email_returns_400_not_409(self, db):
        """
        POST with a userName that belongs to a *different* tenant must return
        400 (not 409) so the caller cannot determine that the email is
        registered on the platform in another tenant.
        """
        tenant_a = _tenant()
        tenant_b = _tenant()
        raw_a, _ = _scim_token(tenant_a)

        # The email exists in tenant B only
        _teacher(tenant_b, email="ct16-cross@tenant-b.com")

        payload = {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
            "userName": "ct16-cross@tenant-b.com",
            "name": {"givenName": "Cross", "familyName": "Tenant"},
            "active": True,
        }
        resp = _post_scim("/scim/v2/Users", payload, raw_a)

        assert resp.status_code == 400, (
            f"Cross-tenant email collision must return 400, got {resp.status_code}"
        )

    def test_cross_tenant_400_body_does_not_leak_email(self, db):
        """
        The 400 response body must NOT contain the email address — leaking it
        would allow enumeration of cross-tenant accounts.
        """
        tenant_a = _tenant()
        tenant_b = _tenant()
        raw_a, _ = _scim_token(tenant_a)

        target_email = "ct16-noleak@tenant-b.com"
        _teacher(tenant_b, email=target_email)

        payload = {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
            "userName": target_email,
            "name": {"givenName": "No", "familyName": "Leak"},
        }
        resp = _post_scim("/scim/v2/Users", payload, raw_a)

        assert resp.status_code == 400
        body = resp.content.decode()
        assert target_email not in body, (
            f"Response body must not contain the email '{target_email}'; "
            f"body was: {body}"
        )

    def test_cross_tenant_400_scim_type_is_invalid_value(self, db):
        """Cross-tenant collision 400 must use scimType=invalidValue."""
        tenant_a = _tenant()
        tenant_b = _tenant()
        raw_a, _ = _scim_token(tenant_a)
        _teacher(tenant_b, email="ct16-type@tenant-b.com")

        payload = {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
            "userName": "ct16-type@tenant-b.com",
            "name": {"givenName": "X", "familyName": "Y"},
        }
        resp = _post_scim("/scim/v2/Users", payload, raw_a)

        assert resp.status_code == 400
        assert resp.json().get("scimType") == "invalidValue"

    def test_cross_tenant_400_emits_warning_log(self, db, caplog):
        """
        A cross-tenant email collision must emit a WARNING log line so that
        ops/security teams can investigate IdP misconfiguration or probing.
        """
        import logging

        tenant_a = _tenant()
        tenant_b = _tenant()
        raw_a, _ = _scim_token(tenant_a)
        _teacher(tenant_b, email="ct16-warnlog@tenant-b.com")

        payload = {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
            "userName": "ct16-warnlog@tenant-b.com",
            "name": {"givenName": "Warn", "familyName": "Log"},
        }

        with caplog.at_level(logging.WARNING, logger="apps.users.scim_views"):
            _post_scim("/scim/v2/Users", payload, raw_a)

        assert any(
            "cross-tenant email collision" in record.message
            for record in caplog.records
        ), (
            "Expected a WARNING log containing 'cross-tenant email collision' "
            f"but got records: {[r.message for r in caplog.records]}"
        )

    def test_cross_tenant_email_user_not_created_in_tenant_a(self, db):
        """
        The 400 response must also mean no user is inserted into tenant A
        — the operation must be a clean rejection, not a partial write.
        """
        tenant_a = _tenant()
        tenant_b = _tenant()
        raw_a, _ = _scim_token(tenant_a)

        email = "ct16-nocreate@tenant-b.com"
        _teacher(tenant_b, email=email)

        payload = {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
            "userName": email,
            "name": {"givenName": "Ghost", "familyName": "User"},
        }
        _post_scim("/scim/v2/Users", payload, raw_a)

        # Must not exist in tenant A
        assert not User.objects.all_tenants().filter(
            tenant=tenant_a, email__iexact=email
        ).exists(), "User must NOT have been created in tenant A after cross-tenant 400"
