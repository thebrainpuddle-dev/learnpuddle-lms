"""
DRF permission classes for the LearnPuddle users app.

AUDIT-2026-04-26-PHASE3-12: MustNotRequirePasswordChange
---------------------------------------------------------
Enforces that users with ``must_change_password=True`` can only access a
small allowlist of endpoints (password change, login, logout, token-refresh,
health checks) until they reset their password.

Wire-up (settings.py):
    REST_FRAMEWORK = {
        "DEFAULT_PERMISSION_CLASSES": [
            "rest_framework.permissions.IsAuthenticated",
            "apps.users.permissions.MustNotRequirePasswordChange",
        ],
        ...
    }

The class is listed *after* IsAuthenticated so that unauthenticated requests
are rejected by IsAuthenticated first — this class never sees them.
Anonymous users are passed through unconditionally so that public / AllowAny
views continue to work without needing per-view overrides.
"""

from __future__ import annotations

from rest_framework.permissions import BasePermission
from rest_framework.response import Response


# Path prefixes that a must_change_password user is still allowed to reach.
# Keep this list minimal — only the flows required to complete the mandatory
# password change or to bootstrap a new session.
_ALLOWED_PATH_PREFIXES = (
    # Password-change flow — the whole point of the flag
    "/api/v1/users/auth/change-password/",
    "/api/users/auth/change-password/",
    # Login / logout — allow them to re-authenticate or log out cleanly
    "/api/v1/users/auth/login/",
    "/api/users/auth/login/",
    "/api/v1/users/auth/logout/",
    "/api/users/auth/logout/",
    # Token refresh — let the client obtain a fresh access token while
    # prompting the user to change their password
    "/api/v1/users/auth/refresh/",
    "/api/users/auth/refresh/",
    # Health checks — infra probes must always succeed
    "/health/",
    # SAML / SSO ACS — allow the SSO flow to complete even if this flag
    # is set (the password-change prompt is a post-login UI concern)
    "/api/v1/saml/",
    "/api/saml/",
    # Password reset (e.g. forgot-password flow — distinct from change-password)
    "/api/v1/users/auth/request-password-reset/",
    "/api/users/auth/request-password-reset/",
    "/api/v1/users/auth/confirm-password-reset/",
    "/api/users/auth/confirm-password-reset/",
)


class MustNotRequirePasswordChange(BasePermission):
    """
    Blocks any authenticated user whose ``must_change_password`` flag is True
    from accessing any route not in the allowlist above.

    Returns HTTP 403 with a structured SCIM-like body:
        {"detail": "Password change required.", "code": "must_change_password"}

    Anonymous users always pass (IsAuthenticated handles them separately).
    Normal authenticated users (flag=False) always pass.
    """

    message = {
        "detail": "Password change required.",
        "code": "must_change_password",
    }

    def has_permission(self, request, view) -> bool:
        user = request.user

        # Pass anonymous users through — IsAuthenticated in the chain handles them.
        if not user or not user.is_authenticated:
            return True

        # Users without the flag set are never blocked.
        if not getattr(user, "must_change_password", False):
            return True

        # Check if the requested path is in the allowlist.
        path = request.path
        for prefix in _ALLOWED_PATH_PREFIXES:
            if path.startswith(prefix):
                return True

        # Blocked — return False; DRF will respond with self.message and 403.
        return False
