# apps/users/password_history_models.py
"""Password history rows for reuse-prevention."""

from __future__ import annotations

import uuid

from django.db import models


class PasswordHistory(models.Model):
    """A single prior password hash for a user.

    We deliberately do NOT store plaintext — only the hashed value as
    produced by Django's configured password hasher.  Comparison is
    performed with :func:`django.contrib.auth.hashers.check_password`
    which tolerates legacy hashers.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="password_history",
    )
    hashed_password = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "password_history"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"PasswordHistory(user={self.user_id}, created_at={self.created_at})"


class SAMLAuthEvent(models.Model):
    """Audit row for every SAML ACS decision — both accepts and rejects.

    Tenant-scoped so deletion of a tenant removes its logs automatically.
    """

    DECISION_CHOICES = [
        ("ACCEPT", "Accepted"),
        ("REJECT_SIGNATURE", "Rejected: bad signature"),
        ("REJECT_EXPIRED", "Rejected: assertion expired"),
        ("REJECT_NOT_YET_VALID", "Rejected: assertion not yet valid"),
        ("REJECT_AUDIENCE", "Rejected: audience mismatch"),
        ("REJECT_NO_EMAIL", "Rejected: no email attribute"),
        ("REJECT_PROVISION_DISABLED", "Rejected: auto-provision disabled"),
        ("REJECT_DOMAIN_NOT_ALLOWED", "Rejected: email domain not allowed"),
        ("REJECT_DISABLED", "Rejected: SAML not enabled for tenant"),
        ("REJECT_MALFORMED", "Rejected: malformed response"),
        ("REJECT_REPLAY", "Rejected: replay detected"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="saml_auth_events",
        null=True, blank=True,
    )
    user = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="saml_auth_events",
    )
    email = models.EmailField(blank=True, default="")
    decision = models.CharField(max_length=40, choices=DECISION_CHOICES)
    detail = models.CharField(max_length=500, blank=True, default="")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    assertion_id = models.CharField(
        max_length=255, blank=True, default="", db_index=True,
        help_text="SAML Response ID — used for replay detection.",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "saml_auth_events"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["tenant", "-created_at"]),
            models.Index(fields=["decision", "-created_at"]),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"SAMLAuthEvent({self.decision}, email={self.email})"
