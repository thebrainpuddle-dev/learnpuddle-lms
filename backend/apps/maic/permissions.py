"""DRF permissions + helpers for MAIC v2 access gating.

Phase 8 / MAIC-800. The deploy-level kill-switch stays as the global
``MAIC_V2_ENABLED`` env var. ASGI uses it at startup to mount WS routes;
HTTP permissions and WS consumers also read it at request/connect time.
Per-tenant gating is the new ``Tenant.feature_maic_v2`` BooleanField;
this module exposes the helpers that views and consumers consult to
enforce it.

Layered gating:
1. Global env var (``settings.MAIC_V2_ENABLED``) — deploy-level. False
   means MAIC v2 is OFF for everyone, no exceptions.
2. Tenant flag (``tenant.feature_maic_v2``) — customer-level. False
   means this tenant cannot reach MAIC v2 routes even if the env var
   is True. Defaults to False on all existing rows; admin must opt-in.

Both layers must be True for a request to pass.
"""
from __future__ import annotations

from django.conf import settings
from rest_framework.permissions import BasePermission

from apps.maic.exceptions import MaicTenantError


def maic_v2_globally_enabled() -> bool:
    """Return True iff the deploy-level MAIC v2 kill switch is on."""
    return bool(getattr(settings, "MAIC_V2_ENABLED", False))


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


def user_has_maic_v2_access(user) -> bool:
    """Return True iff this authenticated user can enter MAIC v2.

    This is the shared entrypoint check for HTTP permissions and WS
    consumers: global deploy flag first, then the tenant-level feature flag.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if not maic_v2_globally_enabled():
        return False
    return tenant_has_v2_access(getattr(user, "tenant", None))


def require_tenant_v2(tenant) -> None:
    """Raise ``MaicTenantError`` if the tenant cannot access MAIC v2.

    Used at the entry point of HTTP views and WS consumers when we need
    to fail loud rather than silently 404. The error message is generic
    so callers don't leak whether the tenant exists vs is unflagged.
    """
    if not tenant_has_v2_access(tenant):
        raise MaicTenantError("MAIC v2 not enabled for this tenant")


def require_user_maic_v2_access(user) -> None:
    """Raise ``MaicTenantError`` if the user cannot access MAIC v2."""
    if not user_has_maic_v2_access(user):
        raise MaicTenantError("MAIC v2 not enabled")


class MaicV2TenantPermission(BasePermission):
    """DRF permission class for the full MAIC v2 entrypoint gate.

    Returns False (which DRF maps to 403) when the global flag is off
    or the tenant flag is off.
    Anonymous requests are deferred to ``IsAuthenticated`` upstream;
    this permission class does not handle authentication itself.
    """

    message = "MAIC v2 not enabled for this tenant"

    def has_permission(self, request, view) -> bool:
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            # Let IsAuthenticated handle the 401; we only adjudicate v2 access.
            return False
        if not maic_v2_globally_enabled():
            self.message = "MAIC v2 is disabled for this deployment"
            return False
        if not tenant_has_v2_access(getattr(user, "tenant", None)):
            self.message = "MAIC v2 not enabled for this tenant"
            return False
        return True
