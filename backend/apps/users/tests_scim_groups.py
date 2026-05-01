"""
SCIM 2.0 Groups Provisioning — test suite (TASK-024).

TDD: these tests were written BEFORE any implementation code.
Every test should FAIL until the implementation is in place.

Covers:
  - GET  /scim/v2/Groups           — list groups (pagination + displayName filter)
  - POST /scim/v2/Groups           — provision a new group → TeacherGroup
  - GET  /scim/v2/Groups/{id}      — retrieve single group with members
  - PUT  /scim/v2/Groups/{id}      — full replace (rename + set members)
  - PATCH /scim/v2/Groups/{id}     — partial update via Operations (add/remove/replace members)
  - DELETE /scim/v2/Groups/{id}    — delete group
  - GET /scim/v2/ServiceProviderConfig → groups.supported = True
  - Tenant isolation across all group endpoints
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
# Shared constants / helpers  (mirrors tests_scim.py helpers)
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


def _make_group(tenant: Tenant, name: str = None) -> TeacherGroup:
    name = name or f"Group-{uuid.uuid4().hex[:6]}"
    return TeacherGroup.objects.create(
        tenant=tenant,
        name=name,
        description="A test group",
    )


def _scim_token_for(tenant: Tenant, admin: User):
    """Return (raw_token, SCIMToken) for tenant."""
    from apps.users.scim_models import SCIMToken
    return SCIMToken.generate(tenant=tenant, name="Test IdP", created_by=admin)


def _scim_headers(token: str) -> dict:
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# 1. Authentication — Groups endpoints require valid SCIM Bearer token
# ---------------------------------------------------------------------------

class TestSCIMGroupAuthentication:
    """All /scim/v2/Groups endpoints require a valid Bearer token."""

    def test_list_groups_without_auth_returns_401(self):
        c = Client()
        resp = c.get("/scim/v2/Groups")
        assert resp.status_code == 401

    def test_list_groups_with_invalid_token_returns_401(self):
        c = Client()
        resp = c.get("/scim/v2/Groups", HTTP_AUTHORIZATION="Bearer garbage")
        assert resp.status_code == 401

    def test_list_groups_with_valid_token_returns_200(self):
        tenant = _make_tenant()
        admin = _make_admin(tenant)
        raw_token, _ = _scim_token_for(tenant, admin)

        c = Client()
        resp = c.get("/scim/v2/Groups", **_scim_headers(raw_token))
        assert resp.status_code == 200

    def test_create_group_without_auth_returns_401(self):
        c = Client()
        resp = c.post(
            "/scim/v2/Groups",
            data=json.dumps({"displayName": "Science"}),
            content_type="application/scim+json",
        )
        assert resp.status_code == 401

    def test_get_group_without_auth_returns_401(self):
        tenant = _make_tenant()
        group = _make_group(tenant)
        c = Client()
        resp = c.get(f"/scim/v2/Groups/{group.id}")
        assert resp.status_code == 401

    def test_inactive_tenant_token_returns_401_on_groups(self):
        """Valid token for a deactivated tenant → 401 on Groups endpoint.

        Confirms that the M6 tenant.is_active guard in SCIMToken.verify()
        protects Groups endpoints too (not just Users).
        """
        tenant = _make_tenant()
        admin = _make_admin(tenant)
        raw_token, _ = _scim_token_for(tenant, admin)

        # Suspend the tenant
        tenant.is_active = False
        tenant.save(update_fields=["is_active"])

        c = Client()
        resp = c.get("/scim/v2/Groups", **_scim_headers(raw_token))
        assert resp.status_code == 401, (
            f"Expected 401 for inactive tenant on Groups, got {resp.status_code}. "
            "M6: suspended tenants must not accept SCIM provisioning on any endpoint."
        )


# ---------------------------------------------------------------------------
# 2. GET /scim/v2/Groups — list
# ---------------------------------------------------------------------------

class TestSCIMListGroups:
    """Tests for SCIM group list endpoint."""

    def _setup(self):
        tenant = _make_tenant()
        admin = _make_admin(tenant)
        raw_token, _ = _scim_token_for(tenant, admin)
        return tenant, raw_token

    def test_list_groups_returns_scim_list_response_envelope(self):
        """Response contains the SCIM ListResponse envelope."""
        tenant, raw_token = self._setup()
        _make_group(tenant)

        c = Client()
        resp = c.get("/scim/v2/Groups", **_scim_headers(raw_token))
        data = resp.json()

        assert resp.status_code == 200
        assert "urn:ietf:params:scim:api:messages:2.0:ListResponse" in data["schemas"]
        assert "totalResults" in data
        assert "Resources" in data
        assert "startIndex" in data
        assert "itemsPerPage" in data

    def test_list_groups_only_shows_own_tenant_groups(self):
        """SCIM group list must not leak groups from other tenants."""
        from apps.users.scim_models import SCIMToken

        tenant_a = _make_tenant()
        tenant_b = _make_tenant()
        admin_a = _make_admin(tenant_a)
        raw_token_a, _ = SCIMToken.generate(tenant=tenant_a, name="Okta", created_by=admin_a)

        _make_group(tenant_a, name="Math Teachers")
        _make_group(tenant_b, name="Science Teachers")

        c = Client()
        resp = c.get("/scim/v2/Groups", **_scim_headers(raw_token_a))
        data = resp.json()

        names = [r["displayName"] for r in data["Resources"]]
        assert "Math Teachers" in names
        assert "Science Teachers" not in names

    def test_list_groups_filter_by_display_name(self):
        """?filter=displayName eq '...' returns matching group only."""
        tenant, raw_token = self._setup()
        _make_group(tenant, name="Alpha Group")
        _make_group(tenant, name="Beta Group")

        c = Client()
        resp = c.get(
            '/scim/v2/Groups?filter=displayName eq "Alpha Group"',
            **_scim_headers(raw_token),
        )
        data = resp.json()

        assert resp.status_code == 200
        assert data["totalResults"] == 1
        assert data["Resources"][0]["displayName"] == "Alpha Group"

    def test_list_groups_pagination_count(self):
        """count=1 returns at most 1 result."""
        tenant, raw_token = self._setup()
        _make_group(tenant, name="Group A")
        _make_group(tenant, name="Group B")

        c = Client()
        resp = c.get("/scim/v2/Groups?count=1", **_scim_headers(raw_token))
        data = resp.json()

        assert resp.status_code == 200
        assert data["itemsPerPage"] == 1
        assert len(data["Resources"]) <= 1

    def test_list_groups_resource_schema_shape(self):
        """Each Group resource must contain required SCIM fields."""
        tenant, raw_token = self._setup()
        _make_group(tenant, name="Test Group")

        c = Client()
        resp = c.get("/scim/v2/Groups", **_scim_headers(raw_token))
        data = resp.json()

        group = data["Resources"][0]
        assert "urn:ietf:params:scim:schemas:core:2.0:Group" in group["schemas"]
        assert "id" in group
        assert "displayName" in group
        assert "members" in group
        assert "meta" in group
        assert group["meta"]["resourceType"] == "Group"

    def test_list_groups_empty_tenant_returns_zero_results(self):
        """No groups for this tenant → totalResults = 0."""
        tenant, raw_token = self._setup()

        c = Client()
        resp = c.get("/scim/v2/Groups", **_scim_headers(raw_token))
        data = resp.json()

        assert data["totalResults"] == 0
        assert data["Resources"] == []


# ---------------------------------------------------------------------------
# 3. POST /scim/v2/Groups — provision a new group
# ---------------------------------------------------------------------------

class TestSCIMCreateGroup:
    """Tests for SCIM group provisioning (POST)."""

    def _setup(self):
        tenant = _make_tenant()
        admin = _make_admin(tenant)
        raw_token, _ = _scim_token_for(tenant, admin)
        return tenant, raw_token

    def test_create_group_returns_201_with_scim_group_body(self):
        """POST /scim/v2/Groups → 201 with SCIM Group body."""
        tenant, raw_token = self._setup()
        payload = {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:Group"],
            "displayName": "Mathematics Department",
        }

        c = Client()
        resp = c.post(
            "/scim/v2/Groups",
            data=json.dumps(payload),
            content_type="application/scim+json",
            **_scim_headers(raw_token),
        )

        assert resp.status_code == 201
        data = resp.json()
        assert "urn:ietf:params:scim:schemas:core:2.0:Group" in data["schemas"]
        assert data["displayName"] == "Mathematics Department"
        assert "id" in data

    def test_create_group_creates_teacher_group_db_record(self):
        """Provisioning a SCIM Group creates a TeacherGroup in the database."""
        tenant, raw_token = self._setup()
        payload = {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:Group"],
            "displayName": "Science Teachers",
        }

        c = Client()
        c.post(
            "/scim/v2/Groups",
            data=json.dumps(payload),
            content_type="application/scim+json",
            **_scim_headers(raw_token),
        )

        assert TeacherGroup.all_objects.filter(
            name="Science Teachers", tenant=tenant
        ).exists()

    def test_create_group_with_members_adds_users(self):
        """POST with members array adds users to the group."""
        tenant, raw_token = self._setup()
        teacher = _make_teacher(tenant)

        payload = {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:Group"],
            "displayName": "New Group",
            "members": [{"value": str(teacher.id)}],
        }

        c = Client()
        resp = c.post(
            "/scim/v2/Groups",
            data=json.dumps(payload),
            content_type="application/scim+json",
            **_scim_headers(raw_token),
        )

        assert resp.status_code == 201
        group = TeacherGroup.all_objects.get(name="New Group", tenant=tenant)
        assert teacher in group.members.all()

    def test_create_group_missing_display_name_returns_400(self):
        """POST without displayName → 400 Bad Request."""
        tenant, raw_token = self._setup()
        payload = {"schemas": ["urn:ietf:params:scim:schemas:core:2.0:Group"]}

        c = Client()
        resp = c.post(
            "/scim/v2/Groups",
            data=json.dumps(payload),
            content_type="application/scim+json",
            **_scim_headers(raw_token),
        )
        assert resp.status_code == 400

    def test_create_group_duplicate_name_returns_409(self):
        """POST with an already-existing group name → 409 Conflict."""
        tenant, raw_token = self._setup()
        _make_group(tenant, name="Existing Group")

        payload = {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:Group"],
            "displayName": "Existing Group",
        }

        c = Client()
        resp = c.post(
            "/scim/v2/Groups",
            data=json.dumps(payload),
            content_type="application/scim+json",
            **_scim_headers(raw_token),
        )
        assert resp.status_code == 409

    def test_create_group_members_from_other_tenant_are_ignored(self):
        """Members that belong to another tenant are silently skipped."""
        tenant_a = _make_tenant()
        tenant_b = _make_tenant()
        admin_a = _make_admin(tenant_a)
        raw_token_a, _ = _scim_token_for(tenant_a, admin_a)

        teacher_b = _make_teacher(tenant_b)

        payload = {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:Group"],
            "displayName": "Cross Tenant Group",
            "members": [{"value": str(teacher_b.id)}],
        }

        c = Client()
        resp = c.post(
            "/scim/v2/Groups",
            data=json.dumps(payload),
            content_type="application/scim+json",
            **_scim_headers(raw_token_a),
        )

        assert resp.status_code == 201
        group = TeacherGroup.all_objects.get(name="Cross Tenant Group", tenant=tenant_a)
        # teacher_b not added — belongs to a different tenant
        assert teacher_b not in group.members.all()


# ---------------------------------------------------------------------------
# 4. GET /scim/v2/Groups/{id} — retrieve single group
# ---------------------------------------------------------------------------

class TestSCIMGetGroup:
    """Tests for GET single SCIM Group."""

    def _setup(self):
        tenant = _make_tenant()
        admin = _make_admin(tenant)
        raw_token, _ = _scim_token_for(tenant, admin)
        group = _make_group(tenant, name="Staff Group")
        return tenant, raw_token, group

    def test_get_group_returns_scim_group(self):
        """GET /scim/v2/Groups/{id} → 200 with SCIM Group body."""
        _, raw_token, group = self._setup()

        c = Client()
        resp = c.get(f"/scim/v2/Groups/{group.id}", **_scim_headers(raw_token))

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == str(group.id)
        assert data["displayName"] == "Staff Group"
        assert "members" in data

    def test_get_group_includes_member_list(self):
        """Members in the group are reflected in the SCIM response."""
        tenant, raw_token, group = self._setup()
        teacher = _make_teacher(tenant)
        group.members.add(teacher)

        c = Client()
        resp = c.get(f"/scim/v2/Groups/{group.id}", **_scim_headers(raw_token))
        data = resp.json()

        member_ids = [m["value"] for m in data["members"]]
        assert str(teacher.id) in member_ids

    def test_get_group_cross_tenant_returns_404(self):
        """Cannot read another tenant's group — returns 404."""
        from apps.users.scim_models import SCIMToken

        tenant_a = _make_tenant()
        tenant_b = _make_tenant()
        admin_a = _make_admin(tenant_a)
        raw_token_a, _ = SCIMToken.generate(tenant=tenant_a, name="Okta", created_by=admin_a)
        group_b = _make_group(tenant_b)

        c = Client()
        resp = c.get(f"/scim/v2/Groups/{group_b.id}", **_scim_headers(raw_token_a))
        assert resp.status_code == 404

    def test_get_group_nonexistent_returns_404(self):
        """GET for a non-existent UUID → 404."""
        _, raw_token, _ = self._setup()

        c = Client()
        resp = c.get(f"/scim/v2/Groups/{uuid.uuid4()}", **_scim_headers(raw_token))
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 5. PUT /scim/v2/Groups/{id} — full replace
# ---------------------------------------------------------------------------

class TestSCIMPutGroup:
    """Tests for SCIM PUT (full replace) on Groups."""

    def _setup(self):
        tenant = _make_tenant()
        admin = _make_admin(tenant)
        raw_token, _ = _scim_token_for(tenant, admin)
        group = _make_group(tenant, name="Old Name")
        return tenant, raw_token, group

    def test_put_group_renames_the_group(self):
        """PUT updates displayName (group name)."""
        _, raw_token, group = self._setup()

        payload = {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:Group"],
            "displayName": "New Name",
            "members": [],
        }

        c = Client()
        resp = c.put(
            f"/scim/v2/Groups/{group.id}",
            data=json.dumps(payload),
            content_type="application/scim+json",
            **_scim_headers(raw_token),
        )
        assert resp.status_code == 200
        group.refresh_from_db()
        assert group.name == "New Name"

    def test_put_group_replaces_members(self):
        """PUT replaces the full member list — previous members removed if not in payload."""
        tenant, raw_token, group = self._setup()
        old_teacher = _make_teacher(tenant)
        new_teacher = _make_teacher(tenant)
        group.members.add(old_teacher)

        payload = {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:Group"],
            "displayName": "Old Name",
            "members": [{"value": str(new_teacher.id)}],
        }

        c = Client()
        resp = c.put(
            f"/scim/v2/Groups/{group.id}",
            data=json.dumps(payload),
            content_type="application/scim+json",
            **_scim_headers(raw_token),
        )
        assert resp.status_code == 200
        group.refresh_from_db()
        assert new_teacher in group.members.all()
        assert old_teacher not in group.members.all()

    def test_put_group_empty_members_clears_membership(self):
        """PUT with members=[] removes all members."""
        tenant, raw_token, group = self._setup()
        teacher = _make_teacher(tenant)
        group.members.add(teacher)

        payload = {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:Group"],
            "displayName": "Old Name",
            "members": [],
        }

        c = Client()
        resp = c.put(
            f"/scim/v2/Groups/{group.id}",
            data=json.dumps(payload),
            content_type="application/scim+json",
            **_scim_headers(raw_token),
        )
        assert resp.status_code == 200
        group.refresh_from_db()
        assert group.members.count() == 0

    def test_put_group_cross_tenant_returns_404(self):
        """PUT on another tenant's group → 404."""
        from apps.users.scim_models import SCIMToken

        tenant_a = _make_tenant()
        tenant_b = _make_tenant()
        admin_a = _make_admin(tenant_a)
        raw_token_a, _ = SCIMToken.generate(tenant=tenant_a, name="Okta", created_by=admin_a)
        group_b = _make_group(tenant_b)

        payload = {
            "schemas": ["urn:ietf:params:scim:schemas:core:2.0:Group"],
            "displayName": "Hacked",
            "members": [],
        }

        c = Client()
        resp = c.put(
            f"/scim/v2/Groups/{group_b.id}",
            data=json.dumps(payload),
            content_type="application/scim+json",
            **_scim_headers(raw_token_a),
        )
        assert resp.status_code == 404
        group_b.refresh_from_db()
        assert group_b.name != "Hacked"


# ---------------------------------------------------------------------------
# 6. PATCH /scim/v2/Groups/{id} — partial update via Operations
# ---------------------------------------------------------------------------

class TestSCIMPatchGroup:
    """Tests for SCIM PATCH on Groups — Operations array."""

    def _setup(self):
        tenant = _make_tenant()
        admin = _make_admin(tenant)
        raw_token, _ = _scim_token_for(tenant, admin)
        group = _make_group(tenant, name="Patch Target")
        return tenant, raw_token, group

    def test_patch_replace_display_name(self):
        """PATCH replace displayName updates the group name."""
        _, raw_token, group = self._setup()

        payload = {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [
                {"op": "replace", "path": "displayName", "value": "Renamed Group"}
            ],
        }

        c = Client()
        resp = c.patch(
            f"/scim/v2/Groups/{group.id}",
            data=json.dumps(payload),
            content_type="application/scim+json",
            **_scim_headers(raw_token),
        )
        assert resp.status_code == 200
        group.refresh_from_db()
        assert group.name == "Renamed Group"

    def test_patch_add_member(self):
        """PATCH add members[...] adds a user to the group."""
        tenant, raw_token, group = self._setup()
        teacher = _make_teacher(tenant)

        payload = {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [
                {
                    "op": "add",
                    "path": "members",
                    "value": [{"value": str(teacher.id)}],
                }
            ],
        }

        c = Client()
        resp = c.patch(
            f"/scim/v2/Groups/{group.id}",
            data=json.dumps(payload),
            content_type="application/scim+json",
            **_scim_headers(raw_token),
        )
        assert resp.status_code == 200
        assert teacher in group.members.all()

    def test_patch_remove_member(self):
        """PATCH remove members[value eq '...'] removes a specific user."""
        tenant, raw_token, group = self._setup()
        teacher = _make_teacher(tenant)
        group.members.add(teacher)

        payload = {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [
                {
                    "op": "remove",
                    "path": f'members[value eq "{teacher.id}"]',
                }
            ],
        }

        c = Client()
        resp = c.patch(
            f"/scim/v2/Groups/{group.id}",
            data=json.dumps(payload),
            content_type="application/scim+json",
            **_scim_headers(raw_token),
        )
        assert resp.status_code == 200
        assert teacher not in group.members.all()

    def test_patch_replace_members_sets_exact_member_list(self):
        """PATCH replace members sets the full member list."""
        tenant, raw_token, group = self._setup()
        old_teacher = _make_teacher(tenant)
        new_teacher = _make_teacher(tenant)
        group.members.add(old_teacher)

        payload = {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [
                {
                    "op": "replace",
                    "path": "members",
                    "value": [{"value": str(new_teacher.id)}],
                }
            ],
        }

        c = Client()
        resp = c.patch(
            f"/scim/v2/Groups/{group.id}",
            data=json.dumps(payload),
            content_type="application/scim+json",
            **_scim_headers(raw_token),
        )
        assert resp.status_code == 200
        assert new_teacher in group.members.all()
        assert old_teacher not in group.members.all()

    def test_patch_no_operations_returns_400(self):
        """PATCH without Operations array → 400."""
        _, raw_token, group = self._setup()

        payload = {"schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"]}

        c = Client()
        resp = c.patch(
            f"/scim/v2/Groups/{group.id}",
            data=json.dumps(payload),
            content_type="application/scim+json",
            **_scim_headers(raw_token),
        )
        assert resp.status_code == 400

    def test_patch_add_member_from_other_tenant_is_ignored(self):
        """PATCH add with a user from another tenant is silently ignored."""
        tenant_a = _make_tenant()
        tenant_b = _make_tenant()
        admin_a = _make_admin(tenant_a)
        raw_token_a, _ = _scim_token_for(tenant_a, admin_a)
        group = _make_group(tenant_a, name="My Group")
        teacher_b = _make_teacher(tenant_b)

        payload = {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [
                {
                    "op": "add",
                    "path": "members",
                    "value": [{"value": str(teacher_b.id)}],
                }
            ],
        }

        c = Client()
        resp = c.patch(
            f"/scim/v2/Groups/{group.id}",
            data=json.dumps(payload),
            content_type="application/scim+json",
            **_scim_headers(raw_token_a),
        )
        assert resp.status_code == 200
        assert teacher_b not in group.members.all()


# ---------------------------------------------------------------------------
# 7. DELETE /scim/v2/Groups/{id}
# ---------------------------------------------------------------------------

class TestSCIMDeleteGroup:
    """Tests for SCIM DELETE on Groups."""

    def _setup(self):
        tenant = _make_tenant()
        admin = _make_admin(tenant)
        raw_token, _ = _scim_token_for(tenant, admin)
        group = _make_group(tenant, name="To Delete")
        return tenant, raw_token, group

    def test_delete_group_returns_204(self):
        """DELETE → 204 No Content."""
        _, raw_token, group = self._setup()

        c = Client()
        resp = c.delete(f"/scim/v2/Groups/{group.id}", **_scim_headers(raw_token))
        assert resp.status_code == 204

    def test_delete_group_removes_from_db(self):
        """Deleted group no longer exists in the database."""
        _, raw_token, group = self._setup()
        group_id = group.id

        c = Client()
        c.delete(f"/scim/v2/Groups/{group.id}", **_scim_headers(raw_token))

        assert not TeacherGroup.all_objects.filter(pk=group_id).exists()

    def test_delete_group_nonexistent_returns_404(self):
        """DELETE on a non-existent UUID → 404."""
        _, raw_token, _ = self._setup()

        c = Client()
        resp = c.delete(f"/scim/v2/Groups/{uuid.uuid4()}", **_scim_headers(raw_token))
        assert resp.status_code == 404

    def test_delete_group_cross_tenant_returns_404(self):
        """Cannot delete another tenant's group."""
        from apps.users.scim_models import SCIMToken

        tenant_a = _make_tenant()
        tenant_b = _make_tenant()
        admin_a = _make_admin(tenant_a)
        raw_token_a, _ = SCIMToken.generate(tenant=tenant_a, name="Okta", created_by=admin_a)
        group_b = _make_group(tenant_b)

        c = Client()
        resp = c.delete(f"/scim/v2/Groups/{group_b.id}", **_scim_headers(raw_token_a))
        assert resp.status_code == 404
        # group_b should still exist
        assert TeacherGroup.all_objects.filter(pk=group_b.id).exists()


# ---------------------------------------------------------------------------
# 8. ServiceProviderConfig — Groups capability advertisement
# ---------------------------------------------------------------------------

class TestSCIMServiceProviderConfigGroups:
    """The ServiceProviderConfig must advertise Groups support."""

    def test_service_provider_config_advertises_groups_supported(self):
        """GET /scim/v2/ServiceProviderConfig must include groups.supported=True."""
        c = Client()
        resp = c.get("/scim/v2/ServiceProviderConfig")
        data = resp.json()

        assert resp.status_code == 200
        assert "groups" in data
        assert data["groups"]["supported"] is True

    def test_service_provider_config_advertises_supported_schemas(self):
        """Supported schemas list must include the Group schema URN."""
        c = Client()
        resp = c.get("/scim/v2/ServiceProviderConfig")
        data = resp.json()

        # Groups schema must appear in the supportedSchemas array
        assert "supportedSchemas" in data
        schema_urns = [s["id"] for s in data["supportedSchemas"]]
        assert "urn:ietf:params:scim:schemas:core:2.0:Group" in schema_urns
        assert "urn:ietf:params:scim:schemas:core:2.0:User" in schema_urns


# ---------------------------------------------------------------------------
# 9. TASK-024 follow-up tests — empty displayName guard + audit detail
# ---------------------------------------------------------------------------

class TestSCIMPatchGroupFollowups:
    """
    Supplemental PATCH tests for TASK-024 non-blocking follow-up items
    (added by qa-tester after reviewer sign-off on 2026-04-24):

    1. PATCH replace displayName with empty/whitespace string → 400 invalidValue
       (empty displayName guard was added after the initial TDD tests shipped)
    2. PATCH audit log includes per-op detail in `changes.ops`
       (op/path audit detail added by backend-engineer per TASK-024 follow-up)
    3. PATCH member remove via path `members[value eq "..."]` works when path
       has surrounding whitespace (re.search vs re.match fix)
    """

    def _setup(self):
        tenant = _make_tenant()
        admin = _make_admin(tenant)
        raw_token, _ = _scim_token_for(tenant, admin)
        group = _make_group(tenant, name="Followup Group")
        return tenant, raw_token, group

    # ------------------------------------------------------------------
    # Empty displayName guard
    # ------------------------------------------------------------------

    def test_patch_replace_displayname_empty_string_returns_400(self):
        """PATCH replace displayName with '' → 400 invalidValue."""
        _, raw_token, group = self._setup()

        payload = {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [
                {"op": "replace", "path": "displayName", "value": ""}
            ],
        }

        c = Client()
        resp = c.patch(
            f"/scim/v2/Groups/{group.id}",
            data=json.dumps(payload),
            content_type="application/scim+json",
            **_scim_headers(raw_token),
        )
        assert resp.status_code == 400, (
            f"Empty displayName should return 400, got {resp.status_code}"
        )
        data = resp.json()
        assert data.get("scimType") == "invalidValue", (
            f"Expected scimType='invalidValue', got {data.get('scimType')!r}"
        )

    def test_patch_replace_displayname_whitespace_only_returns_400(self):
        """PATCH replace displayName with '   ' (whitespace-only) → 400 invalidValue."""
        _, raw_token, group = self._setup()

        payload = {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [
                {"op": "replace", "path": "displayName", "value": "   "}
            ],
        }

        c = Client()
        resp = c.patch(
            f"/scim/v2/Groups/{group.id}",
            data=json.dumps(payload),
            content_type="application/scim+json",
            **_scim_headers(raw_token),
        )
        assert resp.status_code == 400, (
            "Whitespace-only displayName must be rejected"
        )
        data = resp.json()
        assert data.get("scimType") == "invalidValue"

    def test_patch_replace_displayname_preserves_group_name_on_empty(self):
        """Group name must NOT change when PATCH replace displayName fails with 400."""
        _, raw_token, group = self._setup()
        original_name = group.name

        payload = {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [
                {"op": "replace", "path": "displayName", "value": ""}
            ],
        }

        c = Client()
        c.patch(
            f"/scim/v2/Groups/{group.id}",
            data=json.dumps(payload),
            content_type="application/scim+json",
            **_scim_headers(raw_token),
        )

        group.refresh_from_db()
        assert group.name == original_name, (
            "Group name must not change when PATCH rejects the empty displayName"
        )

    # ------------------------------------------------------------------
    # Audit log — per-op detail
    # ------------------------------------------------------------------

    def test_patch_audit_log_records_scim_group_patch_action(self):
        """A successful PATCH writes an AuditLog row with action='SCIM_GROUP_PATCH'."""
        from apps.tenants.models import AuditLog

        _, raw_token, group = self._setup()

        payload = {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [
                {"op": "replace", "path": "displayName", "value": "Audited Group"}
            ],
        }

        c = Client()
        resp = c.patch(
            f"/scim/v2/Groups/{group.id}",
            data=json.dumps(payload),
            content_type="application/scim+json",
            **_scim_headers(raw_token),
        )
        assert resp.status_code == 200

        log = AuditLog.objects.filter(
            action="SCIM_GROUP_PATCH",
            target_id=str(group.id),
        ).last()
        assert log is not None, "Expected SCIM_GROUP_PATCH audit entry after PATCH"

    def test_patch_audit_log_includes_ops_detail(self):
        """PATCH audit log changes.ops contains per-op entry with op and path keys."""
        from apps.tenants.models import AuditLog

        _, raw_token, group = self._setup()

        payload = {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [
                {"op": "replace", "path": "displayName", "value": "DetailAudit Group"}
            ],
        }

        c = Client()
        resp = c.patch(
            f"/scim/v2/Groups/{group.id}",
            data=json.dumps(payload),
            content_type="application/scim+json",
            **_scim_headers(raw_token),
        )
        assert resp.status_code == 200

        log = AuditLog.objects.filter(
            action="SCIM_GROUP_PATCH",
            target_id=str(group.id),
        ).last()
        assert log is not None
        ops = log.changes.get("ops", [])
        assert isinstance(ops, list), f"Expected changes.ops to be a list, got {type(ops)}"
        assert len(ops) >= 1, "Expected at least one op entry in audit log ops"

        op_entry = ops[0]
        assert "op" in op_entry, "Each audit ops entry must have an 'op' key"
        assert "path" in op_entry, "Each audit ops entry must have a 'path' key"

    def test_patch_audit_log_op_count_matches_operations(self):
        """PATCH audit log changes.op_count matches the number of Operations in payload."""
        from apps.tenants.models import AuditLog

        tenant, raw_token, group = self._setup()
        teacher = _make_teacher(tenant)

        payload = {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [
                {"op": "replace", "path": "displayName", "value": "Op Count Group"},
                {"op": "add", "path": "members", "value": [{"value": str(teacher.id)}]},
            ],
        }

        c = Client()
        resp = c.patch(
            f"/scim/v2/Groups/{group.id}",
            data=json.dumps(payload),
            content_type="application/scim+json",
            **_scim_headers(raw_token),
        )
        assert resp.status_code == 200

        log = AuditLog.objects.filter(
            action="SCIM_GROUP_PATCH",
            target_id=str(group.id),
        ).last()
        assert log is not None
        assert log.changes.get("op_count") == 2, (
            f"Expected op_count=2, got {log.changes.get('op_count')!r}"
        )

    # ------------------------------------------------------------------
    # re.search fix — lenient path matching for member remove
    # ------------------------------------------------------------------

    def test_patch_remove_member_with_padded_path_still_removes(self):
        """
        PATCH remove with path `  members[value eq "<uuid>"]  ` (leading/trailing
        spaces) must still remove the member (re.search vs re.match fix from
        TASK-024 follow-up).
        """
        tenant, raw_token, group = self._setup()
        teacher = _make_teacher(tenant)
        group.members.add(teacher)

        # Simulate a client that sends path with surrounding whitespace
        padded_path = f'  members[value eq "{teacher.id}"]  '

        payload = {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [{"op": "remove", "path": padded_path}],
        }

        c = Client()
        resp = c.patch(
            f"/scim/v2/Groups/{group.id}",
            data=json.dumps(payload),
            content_type="application/scim+json",
            **_scim_headers(raw_token),
        )
        assert resp.status_code == 200, (
            f"Padded path should still work with re.search, got {resp.status_code}"
        )
        group.refresh_from_db()
        assert teacher not in group.members.all(), (
            "Teacher should have been removed even with padded path"
        )
