"""DRF permissions + helpers for MAIC v2 access gating.

Phase 8 / MAIC-800. The deploy-level kill-switch stays as the global
``MAIC_V2_ENABLED`` env var (read at ``config.asgi`` import time). Per-
tenant gating is the new ``Tenant.feature_maic_v2`` BooleanField; this
module exposes the helpers that views and consumers consult to enforce
it.

Layered gating:
1. Global env var (``settings.MAIC_V2_ENABLED``) — deploy-level. False
   means MAIC v2 is OFF for everyone, no exceptions.
2. Tenant flag (``tenant.feature_maic_v2``) — customer-level. False
   means this tenant cannot reach MAIC v2 routes even if the env var
   is True. Defaults to False on all existing rows; admin must opt-in.

Both layers must be True for a request to pass.
"""
from __future__ import annotations

from rest_framework.permissions import BasePermission

from apps.maic.exceptions import MaicTenantError


def tenant_has_v2_access(tenant) -> bool:
    """Return True iff this tenant is allowed to use MAIC v2.

    A tenant of None (anonymous request) returns False. Inactive tenants
    return False even if their flag is on — being inactive trumps any
    feature flag. The global env-var gate is checked separately by the
    caller; this helper is purely about the tenant-level decision.
    """
    if tenant is None:
        return False
    if not getattr(tenant, "is_active", True):
        return False
    return bool(getattr(tenant, "feature_maic_v2", False))


def require_tenant_v2(tenant) -> None:
    """Raise ``MaicTenantError`` if the tenant cannot access MAIC v2.

    Used at the entry point of HTTP views and WS consumers when we need
    to fail loud rather than silently 404. The error message is generic
    so callers don't leak whether the tenant exists vs is unflagged.
    """
    if not tenant_has_v2_access(tenant):
        raise MaicTenantError("MAIC v2 not enabled for this tenant")


class MaicV2TenantPermission(BasePermission):
    """DRF permission class — same check as ``require_tenant_v2`` but
    expressed in DRF's ``has_permission`` protocol.

    Returns False (which DRF maps to 403) when the tenant flag is off.
    Anonymous requests are deferred to ``IsAuthenticated`` upstream;
    this permission class does not handle authentication itself.
    """

    message = "MAIC v2 not enabled for this tenant"

    def has_permission(self, request, view) -> bool:
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            # Let IsAuthenticated handle the 401; we only adjudicate v2 access.
            return False
        tenant = getattr(user, "tenant", None)
        return tenant_has_v2_access(tenant)
