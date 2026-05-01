"""
SCIMToken model for SCIM 2.0 User Provisioning (TASK-023).

Each tenant can have one or more named SCIM tokens. The raw token value is
never stored — only its SHA-256 hex digest. Tokens authenticate SCIM requests
from external IdPs (Okta, Azure AD, OneLogin).

    Authorization: Bearer <raw_token>

Security notes
--------------
- ``verify`` performs the SHA-256 hash → DB lookup, then a constant-time
  ``hmac.compare_digest`` check on the matched-row hash as defence in depth.
  This protects against any future schema-shape change that might widen the
  matched-row set or relax the unique index (AUDIT-2026-04-26-PHASE3-4).
- ``expires_at`` (nullable) lets operators rotate tokens on a schedule;
  ``verify`` rejects tokens whose ``expires_at`` is in the past
  (AUDIT-2026-04-26-PHASE3-13).  NULL = never expires (back-compat default).
"""

import hashlib
import hmac
import logging
import secrets
import uuid

from django.db import models
from django.utils import timezone

logger = logging.getLogger(__name__)


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
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Optional expiry; NULL = never expires",
    )
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
    def generate(cls, *, tenant, name, created_by, expires_at=None):
        """
        Create a new SCIM token for *tenant* and return ``(raw_token, instance)``.

        The raw token is a URL-safe random string (≥ 43 chars, base64url alphabet).
        Only the SHA-256 hash is stored; callers must save the raw value now —
        it cannot be recovered from the database afterwards.

        ``expires_at`` is optional — pass an aware datetime to set a hard
        expiry, or leave None for a non-expiring token.
        """
        raw_token = secrets.token_urlsafe(32)  # 32 bytes → 43-char URL-safe string
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        instance = cls.objects.create(
            tenant=tenant,
            name=name,
            created_by=created_by,
            token_hash=token_hash,
            expires_at=expires_at,
        )
        return raw_token, instance

    @classmethod
    def verify(cls, raw_token: str):
        """
        Verify *raw_token* and return the matching :class:`SCIMToken`, or ``None``.

        Pipeline:
          1. SHA-256 hash the raw token.
          2. DB lookup by ``token_hash`` and ``is_active=True``.
          3. Defence-in-depth ``hmac.compare_digest`` on the matched-row hash.
          4. Reject if ``expires_at`` is set and in the past.

        Side-effect: updates ``last_used_at`` on every successful hit without
        re-fetching the row.
        """
        if not raw_token:
            return None

        computed_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        try:
            scim_token = (
                cls.objects
                .select_related("tenant")
                .get(token_hash=computed_hash, is_active=True)
            )
        except cls.DoesNotExist:
            return None

        # ------------------------------------------------------------------
        # AUDIT-2026-04-26-PHASE3-4 — defence-in-depth constant-time compare.
        # The DB lookup already gates access via the unique index, but this
        # belt-and-braces check ensures that any future schema-shape change
        # (e.g. relaxing the unique index, adding a tenant-scoped lookup) cannot
        # silently regress to a non-constant-time comparison.
        # ------------------------------------------------------------------
        stored_hash = scim_token.token_hash or ""
        if not hmac.compare_digest(
            stored_hash.encode("ascii"),
            computed_hash.encode("ascii"),
        ):
            # Should be unreachable given the DB lookup matched, but if it
            # ever fires it indicates either a hash collision (cryptographic
            # break) or a schema regression.  Refuse the token and log loudly.
            logger.warning(
                "SCIMToken.verify: compare_digest mismatch after DB hit "
                "(token_id=%s tenant_id=%s) — refusing token",
                scim_token.pk,
                scim_token.tenant_id,
            )
            return None

        # ------------------------------------------------------------------
        # AUDIT-2026-04-26-PHASE3-13 — expiry check.
        # NULL expires_at = never expires (back-compat).
        # ------------------------------------------------------------------
        if scim_token.expires_at is not None and timezone.now() > scim_token.expires_at:
            logger.warning(
                "SCIMToken.verify: token expired (token_id=%s tenant_id=%s "
                "expires_at=%s) — refusing token",
                scim_token.pk,
                scim_token.tenant_id,
                scim_token.expires_at.isoformat(),
            )
            return None

        # ------------------------------------------------------------------
        # M6 fix (TASK-023-followup) — tenant.is_active guard.
        # A valid token on a deactivated/suspended tenant must not grant SCIM
        # access. This ensures an IdP cannot create or modify users on an
        # account that has been administratively suspended (e.g., payment
        # failure, plan expiry). The token itself stays in the DB unchanged —
        # re-activating the tenant immediately restores provisioning capability
        # without requiring token rotation.
        # ------------------------------------------------------------------
        if not scim_token.tenant.is_active:
            logger.warning(
                "SCIMToken.verify: tenant is inactive — refusing SCIM access "
                "(token_id=%s tenant_id=%s)",
                scim_token.pk,
                scim_token.tenant_id,
            )
            return None

        # Async-safe non-fetching update of last_used_at.
        cls.objects.filter(pk=scim_token.pk).update(last_used_at=timezone.now())
        return scim_token
