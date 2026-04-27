# apps/tenants/password_policy_models.py
"""
Per-tenant password policy configuration.

A TenantPasswordPolicy row exists per tenant and is consulted by
`apps.users.password_validators.TenantPasswordValidator` during password
validation.  When no policy row exists, the validator falls back to a
strict default so that management commands and super-admin flows never
get a weaker policy than the platform minimum.
"""

from __future__ import annotations

import uuid

from django.db import models


class TenantPasswordPolicy(models.Model):
    """Configurable password policy for a single tenant."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.OneToOneField(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="password_policy",
    )

    # Composition rules
    min_length = models.PositiveIntegerField(default=8)
    require_uppercase = models.BooleanField(default=True)
    require_lowercase = models.BooleanField(default=True)
    require_digit = models.BooleanField(default=True)
    require_special = models.BooleanField(default=False)

    # Strength rules
    prevent_common = models.BooleanField(
        default=True,
        help_text="Reject passwords on Django's built-in common-password list.",
    )
    prevent_reuse_last_n = models.PositiveIntegerField(
        default=0,
        help_text="0 disables history checks; otherwise last N hashes are rejected.",
    )

    # Rotation + lockout
    max_age_days = models.PositiveIntegerField(
        default=0,
        help_text="0 = passwords never expire; else number of days before forced rotation.",
    )
    lockout_threshold = models.PositiveIntegerField(
        default=5,
        help_text="Consecutive failed attempts before lockout.",
    )
    lockout_duration_minutes = models.PositiveIntegerField(
        default=30,
        help_text="Minutes to keep account locked after threshold hit.",
    )

    # Invalidate refresh tokens issued before this moment when the policy
    # is tightened.  Callers bump this on PATCH so existing sessions
    # re-authenticate.
    policy_rotated_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tenant_password_policies"
        verbose_name = "Tenant password policy"
        verbose_name_plural = "Tenant password policies"

    def __str__(self) -> str:
        return f"PasswordPolicy({self.tenant_id})"

    # ---- Helpers -----------------------------------------------------

    @classmethod
    def default_values(cls) -> dict:
        """Safe baseline used when no policy row exists (super admins, mgmt cmds)."""
        return {
            "min_length": 12,
            "require_uppercase": True,
            "require_lowercase": True,
            "require_digit": True,
            "require_special": False,
            "prevent_common": True,
            "prevent_reuse_last_n": 0,
            "max_age_days": 0,
            "lockout_threshold": 5,
            "lockout_duration_minutes": 30,
        }

    def as_dict(self) -> dict:
        return {
            "min_length": self.min_length,
            "require_uppercase": self.require_uppercase,
            "require_lowercase": self.require_lowercase,
            "require_digit": self.require_digit,
            "require_special": self.require_special,
            "prevent_common": self.prevent_common,
            "prevent_reuse_last_n": self.prevent_reuse_last_n,
            "max_age_days": self.max_age_days,
            "lockout_threshold": self.lockout_threshold,
            "lockout_duration_minutes": self.lockout_duration_minutes,
        }
