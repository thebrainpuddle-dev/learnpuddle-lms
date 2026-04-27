# apps/users/token_policy.py
"""
Refresh-token freshness enforcement.

A refresh token is rejected when its ``iat`` (issued-at) claim predates
either:

* the owning tenant's ``TenantPasswordPolicy.policy_rotated_at``, i.e.
  an admin tightened the policy and the task spec mandates re-auth, or
* the owning user's ``password_changed_at``, i.e. the user themselves
  rotated their password (self-initiated or via reset), which implicitly
  revokes all outstanding refresh tokens.

``enforce_token_freshness`` is called from the refresh-token view.  It
raises :class:`ValueError` if the token must be rejected; the caller
turns that into a ``401``.
"""

from __future__ import annotations

from typing import Optional


def _issued_at(token) -> Optional[int]:
    """Return the `iat` claim as a unix timestamp, or ``None``."""
    try:
        iat = token.get("iat")
    except Exception:
        iat = None
    if iat is None:
        # SimpleJWT stores claims as a dict under `.payload`.
        iat = getattr(token, "payload", {}).get("iat")
    if iat is None:
        return None
    try:
        return int(iat)
    except (TypeError, ValueError):
        return None


def enforce_token_freshness(refresh_token) -> None:
    """Raise ``ValueError`` if the refresh token was issued before a
    policy rotation or the user's last password change.

    The function is a no-op when the token cannot be tied to a user (no
    ``user_id`` claim) or when neither timestamp has ever been set.
    """
    from apps.tenants.password_policy_models import TenantPasswordPolicy
    from apps.users.models import User

    iat = _issued_at(refresh_token)
    if iat is None:
        return  # Tokens without iat claim fail-closed via SimpleJWT itself.

    try:
        user_id = refresh_token["user_id"]
    except KeyError:
        return

    try:
        user = User.all_objects.get(pk=user_id)
    except User.DoesNotExist:
        raise ValueError("User no longer exists")

    # Per-user password rotation invalidates any earlier refresh tokens.
    pw_changed = getattr(user, "password_changed_at", None)
    if pw_changed is not None and iat < int(pw_changed.timestamp()):
        raise ValueError("Refresh token predates your last password change; please sign in again.")

    # Tenant-level policy rotation invalidates any earlier refresh tokens
    # for every user in the tenant.
    tenant_id = getattr(user, "tenant_id", None)
    if tenant_id:
        try:
            policy = TenantPasswordPolicy.objects.get(tenant_id=tenant_id)
        except TenantPasswordPolicy.DoesNotExist:
            policy = None
        if policy is not None and policy.policy_rotated_at is not None:
            if iat < int(policy.policy_rotated_at.timestamp()):
                raise ValueError(
                    "Refresh token predates a password policy change; please sign in again."
                )
