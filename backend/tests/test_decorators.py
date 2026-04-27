"""
Unit tests for ``utils/decorators.py``.

The decorators are the primary access-control layer for all API views.
They are tested indirectly by every API-level test, but direct unit tests:

  1. Pin the exact role/tenant logic in one place.
  2. Guard against accidental changes (e.g. an errant merge removing a
     role from an allowed-list).
  3. Run without HTTP overhead — each test calls the decorator directly.

Test strategy
-------------
Each decorator is applied to a trivial sentinel view function:

    @decorator
    def _view(request, *args, **kwargs):
        return "OK"

The test then constructs a minimal ``request``-like object with the
attributes the decorator reads (``user.is_authenticated``, ``user.role``,
``user.tenant_id``) and asserts whether ``_view(request)`` returns ``"OK"``
or raises ``PermissionDenied``.

For ``tenant_required``, the contextvars tenant is set/cleared via
``utils.tenant_middleware`` helpers.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from rest_framework.exceptions import PermissionDenied

from utils.decorators import (
    admin_only,
    check_feature,
    student_only,
    student_or_admin,
    super_admin_only,
    teacher_or_admin,
    tenant_required,
)
from utils.tenant_middleware import clear_current_tenant, set_current_tenant


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sentinel_view(request, *args, **kwargs):  # noqa: ARG001
    return "OK"


def _user(
    role: str = "TEACHER",
    is_authenticated: bool = True,
    tenant_id: int | None = 1,
) -> SimpleNamespace:
    return SimpleNamespace(
        role=role,
        is_authenticated=is_authenticated,
        tenant_id=tenant_id,
    )


def _request(user=None, tenant=None) -> SimpleNamespace:
    req = SimpleNamespace(
        user=user or _user(),
        tenant=tenant,
    )
    return req


# ---------------------------------------------------------------------------
# tenant_required
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestTenantRequired:
    """The ``@tenant_required`` decorator enforces tenant context and
    cross-tenant isolation."""

    def setup_method(self):
        clear_current_tenant()

    def teardown_method(self):
        clear_current_tenant()

    def test_raises_when_no_tenant_in_context(self):
        """Without a tenant in the contextvars store, view must raise 403."""
        view = tenant_required(_sentinel_view)
        req = _request(user=_user(role="TEACHER", tenant_id=None))
        with pytest.raises(PermissionDenied, match="Tenant context required"):
            view(req)

    def test_passes_when_tenant_set_and_user_owns_tenant(self, tenant, teacher_user):
        """When tenant context matches the user's tenant, access is granted."""
        set_current_tenant(tenant)
        view = tenant_required(_sentinel_view)
        user = SimpleNamespace(
            role="TEACHER",
            is_authenticated=True,
            tenant_id=tenant.id,
        )
        req = _request(user=user)
        assert view(req) == "OK"

    def test_raises_for_cross_tenant_user(self, tenant, tenant_b):
        """User from tenant A trying to access tenant B's context → 403."""
        set_current_tenant(tenant_b)
        view = tenant_required(_sentinel_view)
        user = SimpleNamespace(
            role="TEACHER",
            is_authenticated=True,
            tenant_id=tenant.id,  # user belongs to A, context is B
        )
        req = _request(user=user)
        with pytest.raises(PermissionDenied, match="does not belong"):
            view(req)

    def test_super_admin_bypasses_cross_tenant_check(self, tenant, tenant_b):
        """SUPER_ADMIN can access any tenant's context."""
        set_current_tenant(tenant_b)
        view = tenant_required(_sentinel_view)
        user = SimpleNamespace(
            role="SUPER_ADMIN",
            is_authenticated=True,
            tenant_id=tenant.id,  # belongs to A, context is B
        )
        req = _request(user=user)
        assert view(req) == "OK"

    def test_sets_request_tenant_attribute_when_missing(self, tenant):
        """Decorator populates ``request.tenant`` from contextvars if absent."""
        set_current_tenant(tenant)
        view = tenant_required(_sentinel_view)
        user = SimpleNamespace(
            role="TEACHER",
            is_authenticated=True,
            tenant_id=tenant.id,
        )
        req = SimpleNamespace(user=user)  # No 'tenant' attribute
        view(req)
        assert req.tenant is tenant

    def test_unauthenticated_user_with_tenant_in_context(self, tenant):
        """Unauthenticated users pass the cross-tenant check (no tenant_id)."""
        set_current_tenant(tenant)
        view = tenant_required(_sentinel_view)
        user = SimpleNamespace(role="ANONYMOUS", is_authenticated=False, tenant_id=None)
        req = _request(user=user)
        result = view(req)
        assert result == "OK"


# ---------------------------------------------------------------------------
# admin_only
# ---------------------------------------------------------------------------


class TestAdminOnly:
    """``@admin_only`` allows SCHOOL_ADMIN and SUPER_ADMIN; blocks everyone else."""

    def _call(self, role: str, is_authenticated: bool = True) -> str:
        view = admin_only(_sentinel_view)
        return view(_request(user=_user(role=role, is_authenticated=is_authenticated)))

    def test_school_admin_allowed(self):
        assert self._call("SCHOOL_ADMIN") == "OK"

    def test_super_admin_allowed(self):
        assert self._call("SUPER_ADMIN") == "OK"

    def test_teacher_denied(self):
        with pytest.raises(PermissionDenied, match="Admin access required"):
            self._call("TEACHER")

    def test_hod_denied(self):
        with pytest.raises(PermissionDenied, match="Admin access required"):
            self._call("HOD")

    def test_ib_coordinator_denied(self):
        with pytest.raises(PermissionDenied, match="Admin access required"):
            self._call("IB_COORDINATOR")

    def test_student_denied(self):
        with pytest.raises(PermissionDenied):
            self._call("STUDENT")

    def test_unauthenticated_denied(self):
        with pytest.raises(PermissionDenied, match="Authentication required"):
            self._call("TEACHER", is_authenticated=False)


# ---------------------------------------------------------------------------
# super_admin_only
# ---------------------------------------------------------------------------


class TestSuperAdminOnly:
    """``@super_admin_only`` allows only SUPER_ADMIN."""

    def _call(self, role: str, is_authenticated: bool = True) -> str:
        view = super_admin_only(_sentinel_view)
        return view(_request(user=_user(role=role, is_authenticated=is_authenticated)))

    def test_super_admin_allowed(self):
        assert self._call("SUPER_ADMIN") == "OK"

    def test_school_admin_denied(self):
        with pytest.raises(PermissionDenied, match="Super admin access required"):
            self._call("SCHOOL_ADMIN")

    def test_teacher_denied(self):
        with pytest.raises(PermissionDenied, match="Super admin access required"):
            self._call("TEACHER")

    def test_hod_denied(self):
        with pytest.raises(PermissionDenied):
            self._call("HOD")

    def test_unauthenticated_denied(self):
        with pytest.raises(PermissionDenied, match="Authentication required"):
            self._call("SUPER_ADMIN", is_authenticated=False)


# ---------------------------------------------------------------------------
# teacher_or_admin
# ---------------------------------------------------------------------------


class TestTeacherOrAdmin:
    """``@teacher_or_admin`` allows TEACHER, SCHOOL_ADMIN, SUPER_ADMIN, HOD, IB_COORDINATOR."""

    def _call(self, role: str, is_authenticated: bool = True) -> str:
        view = teacher_or_admin(_sentinel_view)
        return view(_request(user=_user(role=role, is_authenticated=is_authenticated)))

    def test_teacher_allowed(self):
        assert self._call("TEACHER") == "OK"

    def test_school_admin_allowed(self):
        assert self._call("SCHOOL_ADMIN") == "OK"

    def test_super_admin_allowed(self):
        assert self._call("SUPER_ADMIN") == "OK"

    def test_hod_allowed(self):
        assert self._call("HOD") == "OK"

    def test_ib_coordinator_allowed(self):
        assert self._call("IB_COORDINATOR") == "OK"

    def test_student_denied(self):
        with pytest.raises(PermissionDenied, match="Teacher or admin access required"):
            self._call("STUDENT")

    def test_unauthenticated_denied(self):
        with pytest.raises(PermissionDenied, match="Authentication required"):
            self._call("TEACHER", is_authenticated=False)


# ---------------------------------------------------------------------------
# student_only
# ---------------------------------------------------------------------------


class TestStudentOnly:
    """``@student_only`` allows only STUDENT."""

    def _call(self, role: str, is_authenticated: bool = True) -> str:
        view = student_only(_sentinel_view)
        return view(_request(user=_user(role=role, is_authenticated=is_authenticated)))

    def test_student_allowed(self):
        assert self._call("STUDENT") == "OK"

    def test_teacher_denied(self):
        with pytest.raises(PermissionDenied, match="Student access required"):
            self._call("TEACHER")

    def test_school_admin_denied(self):
        with pytest.raises(PermissionDenied):
            self._call("SCHOOL_ADMIN")

    def test_super_admin_denied(self):
        with pytest.raises(PermissionDenied):
            self._call("SUPER_ADMIN")

    def test_unauthenticated_denied(self):
        with pytest.raises(PermissionDenied, match="Authentication required"):
            self._call("STUDENT", is_authenticated=False)


# ---------------------------------------------------------------------------
# student_or_admin
# ---------------------------------------------------------------------------


class TestStudentOrAdmin:
    """``@student_or_admin`` allows STUDENT, SCHOOL_ADMIN, SUPER_ADMIN."""

    def _call(self, role: str, is_authenticated: bool = True) -> str:
        view = student_or_admin(_sentinel_view)
        return view(_request(user=_user(role=role, is_authenticated=is_authenticated)))

    def test_student_allowed(self):
        assert self._call("STUDENT") == "OK"

    def test_school_admin_allowed(self):
        assert self._call("SCHOOL_ADMIN") == "OK"

    def test_super_admin_allowed(self):
        assert self._call("SUPER_ADMIN") == "OK"

    def test_teacher_denied(self):
        with pytest.raises(PermissionDenied, match="Student or admin access required"):
            self._call("TEACHER")

    def test_hod_denied(self):
        with pytest.raises(PermissionDenied):
            self._call("HOD")

    def test_ib_coordinator_denied(self):
        with pytest.raises(PermissionDenied):
            self._call("IB_COORDINATOR")

    def test_unauthenticated_denied(self):
        with pytest.raises(PermissionDenied, match="Authentication required"):
            self._call("STUDENT", is_authenticated=False)


# ---------------------------------------------------------------------------
# check_feature
# ---------------------------------------------------------------------------


class TestCheckFeature:
    """``@check_feature(name)`` gates on tenant feature flags.

    Three name forms are supported:
      - BooleanField attribute:  ``'feature_certificates'``
      - Dict lookup:             ``'certificates'``
      - Explicit dict form:      ``'features.certificates'``
    """

    @staticmethod
    def _make_tenant_with_feature(feature_name: str, enabled: bool):
        """Return a request-like object whose tenant has a single feature."""
        short = (
            feature_name.split(".")[-1]
            if "." in feature_name
            else feature_name.replace("feature_", "")
        )
        tenant = SimpleNamespace(
            features={short: enabled},
            **{f"feature_{short}": enabled},
        )
        return SimpleNamespace(
            user=_user(),
            tenant=tenant,
        )

    def _call_with_tenant(self, feature_name: str, enabled: bool):
        view = check_feature(feature_name)(_sentinel_view)
        req = self._make_tenant_with_feature(feature_name, enabled)
        return view(req)

    # --- Feature enabled ---

    def test_feature_allowed_via_features_dict(self):
        result = self._call_with_tenant("certificates", True)
        assert result == "OK"

    def test_feature_allowed_via_boolean_attribute(self):
        result = self._call_with_tenant("feature_certificates", True)
        assert result == "OK"

    def test_feature_allowed_via_dotted_form(self):
        result = self._call_with_tenant("features.certificates", True)
        assert result == "OK"

    # --- Feature disabled ---

    def test_feature_blocked_when_disabled_via_dict(self):
        from rest_framework.response import Response

        view = check_feature("certificates")(_sentinel_view)
        req = self._make_tenant_with_feature("certificates", False)
        result = view(req)
        assert isinstance(result, Response)
        assert result.status_code == 403
        assert result.data.get("upgrade_required") is True
        assert "certificates" in result.data.get("feature", "")

    def test_feature_blocked_when_false_boolean_attribute(self):
        from rest_framework.response import Response

        view = check_feature("feature_certificates")(_sentinel_view)
        req = self._make_tenant_with_feature("feature_certificates", False)
        result = view(req)
        assert isinstance(result, Response)
        assert result.status_code == 403

    # --- No tenant (passes through — guard is only active when tenant set) ---

    def test_no_tenant_passes_through(self):
        """If no tenant is set (e.g. management command), the check is skipped."""
        view = check_feature("certificates")(_sentinel_view)
        req = SimpleNamespace(user=_user(), tenant=None)
        result = view(req)
        assert result == "OK"

    def test_feature_name_preserved_in_403_response(self):
        """The 403 payload must identify WHICH feature triggered the gate."""
        from rest_framework.response import Response

        view = check_feature("feature_maic")(_sentinel_view)
        req = self._make_tenant_with_feature("feature_maic", False)
        result = view(req)
        assert isinstance(result, Response)
        assert result.data.get("feature") == "feature_maic"
