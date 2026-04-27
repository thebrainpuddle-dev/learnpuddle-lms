# tests/test_permissions.py
"""
Tests for utils/permissions.py — DRF permission classes.

Covers:
- IsSuperAdmin: allows only SUPER_ADMIN, blocks all others and unauthenticated
- IsSchoolAdmin: allows only SCHOOL_ADMIN, blocks all others and unauthenticated
- Edge cases: None user, missing role attribute, inactive users
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from django.test import TestCase


# ===========================================================================
# Helpers
# ===========================================================================

def _make_user(role: str, is_authenticated: bool = True):
    """Create a minimal mock user object for permission tests."""
    user = SimpleNamespace(
        role=role,
        is_authenticated=is_authenticated,
    )
    return user


def _make_request(user=None):
    """Create a minimal mock request object."""
    req = SimpleNamespace(user=user)
    return req


# ===========================================================================
# 1. IsSuperAdmin Tests
# ===========================================================================


class IsSuperAdminTestCase(TestCase):
    """IsSuperAdmin allows only authenticated SUPER_ADMIN users."""

    def setUp(self):
        from utils.permissions import IsSuperAdmin
        self.permission = IsSuperAdmin()
        self.view = MagicMock()

    def test_super_admin_is_allowed(self):
        """Authenticated SUPER_ADMIN must have permission."""
        request = _make_request(_make_user("SUPER_ADMIN"))
        self.assertTrue(
            self.permission.has_permission(request, self.view),
            "IsSuperAdmin must allow SUPER_ADMIN role",
        )

    def test_school_admin_is_denied(self):
        """SCHOOL_ADMIN must not pass IsSuperAdmin."""
        request = _make_request(_make_user("SCHOOL_ADMIN"))
        self.assertFalse(
            self.permission.has_permission(request, self.view),
            "IsSuperAdmin must deny SCHOOL_ADMIN role",
        )

    def test_teacher_is_denied(self):
        """TEACHER role must not pass IsSuperAdmin."""
        request = _make_request(_make_user("TEACHER"))
        self.assertFalse(
            self.permission.has_permission(request, self.view),
            "IsSuperAdmin must deny TEACHER role",
        )

    def test_hod_is_denied(self):
        """HOD role must not pass IsSuperAdmin."""
        request = _make_request(_make_user("HOD"))
        self.assertFalse(self.permission.has_permission(request, self.view))

    def test_ib_coordinator_is_denied(self):
        """IB_COORDINATOR role must not pass IsSuperAdmin."""
        request = _make_request(_make_user("IB_COORDINATOR"))
        self.assertFalse(self.permission.has_permission(request, self.view))

    def test_unauthenticated_user_is_denied(self):
        """Unauthenticated user (is_authenticated=False) must be denied."""
        request = _make_request(_make_user("SUPER_ADMIN", is_authenticated=False))
        self.assertFalse(
            self.permission.has_permission(request, self.view),
            "IsSuperAdmin must deny unauthenticated users even if role is correct",
        )

    def test_none_user_is_denied(self):
        """None user on request must be denied gracefully (no AttributeError)."""
        request = _make_request(user=None)
        self.assertFalse(
            self.permission.has_permission(request, self.view),
            "IsSuperAdmin must handle None user without raising",
        )

    def test_no_user_attribute_on_request_is_denied(self):
        """Request with no user attribute at all is denied gracefully."""
        request = SimpleNamespace()  # No 'user' attribute
        self.assertFalse(
            self.permission.has_permission(request, self.view),
            "IsSuperAdmin must handle missing user attribute gracefully",
        )

    def test_user_without_role_attribute_is_denied(self):
        """User without role attribute must not pass IsSuperAdmin."""
        user = SimpleNamespace(is_authenticated=True)  # No 'role' attribute
        request = _make_request(user)
        self.assertFalse(
            self.permission.has_permission(request, self.view),
            "IsSuperAdmin must deny user with missing role attribute",
        )

    def test_message_is_descriptive(self):
        """IsSuperAdmin must have a human-readable message for 403 responses."""
        from utils.permissions import IsSuperAdmin
        perm = IsSuperAdmin()
        self.assertTrue(
            len(perm.message) > 0,
            "IsSuperAdmin.message must be non-empty for DRF 403 responses",
        )


# ===========================================================================
# 2. IsSchoolAdmin Tests
# ===========================================================================


class IsSchoolAdminTestCase(TestCase):
    """IsSchoolAdmin allows only authenticated SCHOOL_ADMIN users."""

    def setUp(self):
        from utils.permissions import IsSchoolAdmin
        self.permission = IsSchoolAdmin()
        self.view = MagicMock()

    def test_school_admin_is_allowed(self):
        """Authenticated SCHOOL_ADMIN must have permission."""
        request = _make_request(_make_user("SCHOOL_ADMIN"))
        self.assertTrue(
            self.permission.has_permission(request, self.view),
            "IsSchoolAdmin must allow SCHOOL_ADMIN role",
        )

    def test_super_admin_is_denied(self):
        """
        SUPER_ADMIN must NOT pass IsSchoolAdmin.
        Super admins have separate permission class; this class is tenant-scoped.
        """
        request = _make_request(_make_user("SUPER_ADMIN"))
        self.assertFalse(
            self.permission.has_permission(request, self.view),
            "IsSchoolAdmin must deny SUPER_ADMIN — use IsSuperAdmin for that",
        )

    def test_teacher_is_denied(self):
        """TEACHER role must not pass IsSchoolAdmin."""
        request = _make_request(_make_user("TEACHER"))
        self.assertFalse(
            self.permission.has_permission(request, self.view),
            "IsSchoolAdmin must deny TEACHER role",
        )

    def test_hod_is_denied(self):
        """HOD role must not pass IsSchoolAdmin."""
        request = _make_request(_make_user("HOD"))
        self.assertFalse(self.permission.has_permission(request, self.view))

    def test_ib_coordinator_is_denied(self):
        """IB_COORDINATOR role must not pass IsSchoolAdmin."""
        request = _make_request(_make_user("IB_COORDINATOR"))
        self.assertFalse(self.permission.has_permission(request, self.view))

    def test_unauthenticated_user_is_denied(self):
        """Unauthenticated SCHOOL_ADMIN must be denied."""
        request = _make_request(_make_user("SCHOOL_ADMIN", is_authenticated=False))
        self.assertFalse(
            self.permission.has_permission(request, self.view),
            "IsSchoolAdmin must deny unauthenticated users even if role is correct",
        )

    def test_none_user_is_denied(self):
        """None user must be denied gracefully."""
        request = _make_request(user=None)
        self.assertFalse(
            self.permission.has_permission(request, self.view),
            "IsSchoolAdmin must handle None user without raising",
        )

    def test_no_user_attribute_on_request_is_denied(self):
        """Request with no user attribute at all is denied gracefully."""
        request = SimpleNamespace()  # No 'user' attribute
        self.assertFalse(
            self.permission.has_permission(request, self.view),
            "IsSchoolAdmin must handle missing user attribute gracefully",
        )

    def test_user_without_role_attribute_is_denied(self):
        """User without role attribute must not pass IsSchoolAdmin."""
        user = SimpleNamespace(is_authenticated=True)  # No 'role' attribute
        request = _make_request(user)
        self.assertFalse(
            self.permission.has_permission(request, self.view),
            "IsSchoolAdmin must deny user with missing role attribute",
        )

    def test_message_is_descriptive(self):
        """IsSchoolAdmin must have a human-readable message."""
        from utils.permissions import IsSchoolAdmin
        perm = IsSchoolAdmin()
        self.assertTrue(
            len(perm.message) > 0,
            "IsSchoolAdmin.message must be non-empty for DRF 403 responses",
        )


# ===========================================================================
# 3. Permission Class Composition Tests
# ===========================================================================


class PermissionCompositionTestCase(TestCase):
    """
    Verify that IsSuperAdmin and IsSchoolAdmin are mutually exclusive
    for the roles they are designed for.
    """

    def setUp(self):
        from utils.permissions import IsSuperAdmin, IsSchoolAdmin
        self.is_super = IsSuperAdmin()
        self.is_school = IsSchoolAdmin()
        self.view = MagicMock()

    def test_super_admin_passes_only_isSuperAdmin(self):
        """SUPER_ADMIN must pass IsSuperAdmin but NOT IsSchoolAdmin."""
        request = _make_request(_make_user("SUPER_ADMIN"))
        self.assertTrue(self.is_super.has_permission(request, self.view))
        self.assertFalse(self.is_school.has_permission(request, self.view))

    def test_school_admin_passes_only_isSchoolAdmin(self):
        """SCHOOL_ADMIN must pass IsSchoolAdmin but NOT IsSuperAdmin."""
        request = _make_request(_make_user("SCHOOL_ADMIN"))
        self.assertFalse(self.is_super.has_permission(request, self.view))
        self.assertTrue(self.is_school.has_permission(request, self.view))

    def test_teacher_fails_both(self):
        """TEACHER must fail both IsSuperAdmin and IsSchoolAdmin."""
        request = _make_request(_make_user("TEACHER"))
        self.assertFalse(self.is_super.has_permission(request, self.view))
        self.assertFalse(self.is_school.has_permission(request, self.view))
