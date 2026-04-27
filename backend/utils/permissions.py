"""
Shared DRF permission classes.

Keep these tiny and composable — view-level logic should still live in the
dedicated decorators (``admin_only``, ``tenant_required``, …). These classes
are primarily useful for generic DRF class-based views where decorators don't
compose cleanly.
"""

from rest_framework.permissions import BasePermission


class IsSuperAdmin(BasePermission):
    """Allow access only to authenticated platform SUPER_ADMIN users."""

    message = "Super admin access required"

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return False
        return getattr(user, "role", None) == "SUPER_ADMIN"


class IsSchoolAdmin(BasePermission):
    """Allow access only to authenticated SCHOOL_ADMIN users (tenant-scoped)."""

    message = "School admin access required"

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return False
        return getattr(user, "role", None) == "SCHOOL_ADMIN"
