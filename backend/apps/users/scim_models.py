"""
SCIMToken model for SCIM 2.0 User Provisioning (TASK-023).

Each tenant can have one or more named SCIM tokens. The raw token value is
never stored — only its SHA-256 hex digest. Tokens authenticate SCIM requests
from external IdPs (Okta, Azure AD, OneLogin).

    Authorization: Bearer <raw_token>
"""

import hashlib
import secrets
import uuid

from django.db import models
from django.utils import timezone


class SCIMToken(models.Model):
    """
    Per-tenant SCIM Bearer token.

    Only the SHA-256 hash is persisted; the raw token is returned once on
    creation and cannot be recovered afterwards.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="scim_tokens",
    )
    name = models.CharField(
        max_length=100,
        help_text="Human-readable label, e.g. 'Okta production'",
    )
    token_hash = models.CharField(
        max_length=64,
        unique=True,
        help_text="SHA-256 hex digest of the raw token — never the plaintext.",
    )
    created_by = models.ForeignKey(
        "users.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_scim_tokens",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "scim_tokens"
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["tenant", "is_active"],
                name="scim_tokens_tenant_active_idx",
            ),
        ]

    def __str__(self):
        return f"SCIMToken({self.name!r}, tenant_id={self.tenant_id})"

    # ------------------------------------------------------------------
    # Class-level factory / verification helpers
    # ------------------------------------------------------------------

    @classmethod
    def generate(cls, *, tenant, name, created_by):
        """
        Create a new SCIM token for *tenant* and return ``(raw_token, instance)``.

        The raw token is a URL-safe random string (≥ 43 chars, base64url alphabet).
        Only the SHA-256 hash is stored; callers must save the raw value now —
        it cannot be recovered from the database afterwards.
        """
        raw_token = secrets.token_urlsafe(32)  # 32 bytes → 43-char URL-safe string
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        instance = cls.objects.create(
            tenant=tenant,
            name=name,
            created_by=created_by,
            token_hash=token_hash,
        )
        return raw_token, instance

    @classmethod
    def verify(cls, raw_token: str):
        """
        Verify *raw_token* and return the matching :class:`SCIMToken`, or ``None``.

        Side-effect: updates ``last_used_at`` on every successful hit without
        fetching the whole row again.
        """
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        try:
            scim_token = (
                cls.objects
                .select_related("tenant")
                .get(token_hash=token_hash, is_active=True)
            )
        except cls.DoesNotExist:
            return None
        # Async-safe non-fetching update of last_used_at.
        cls.objects.filter(pk=scim_token.pk).update(last_used_at=timezone.now())
        return scim_token
