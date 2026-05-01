"""
SCIM Token security regression tests — Phase 3 P1 audit follow-up.

Covers:
  - AUDIT-2026-04-26-PHASE3-4 (P1):  SCIMToken.verify must use a constant-time
                                      compare (`hmac.compare_digest`) as defence
                                      in depth on top of the DB lookup.
  - AUDIT-2026-04-26-PHASE3-13 (P2): SCIMToken must support an optional
                                      `expires_at` field; a token whose
                                      `expires_at` is in the past must be
                                      rejected by `verify()` (return None +
                                      WARNING log).  NULL expires_at preserves
                                      the existing "no expiry" behaviour.

These tests were written BEFORE the implementation per the TDD requirement
in the audit dispatch.  Run them red, then implement, then run them green.
"""

from __future__ import annotations

import hmac
import logging
import uuid
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from apps.tenants.models import Tenant
from apps.users.models import User

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Local helpers — duplicated minimally rather than depending on tests_scim
# helpers (which import-cycle through pytestmark fixtures).
# ---------------------------------------------------------------------------

def _tenant(subdomain: str | None = None) -> Tenant:
    sub = subdomain or ("ts-" + uuid.uuid4().hex[:8])
    return Tenant.objects.create(
        name=f"School {sub}",
        slug=sub,
        subdomain=sub,
        email=f"admin@{sub}.test",
    )


def _admin(tenant: Tenant) -> User:
    return User.objects.create_user(
        email=f"admin-{uuid.uuid4().hex[:6]}@ts.test",
        password="Password123!",
        first_name="Admin",
        last_name="User",
        tenant=tenant,
        role="SCHOOL_ADMIN",
    )


# ---------------------------------------------------------------------------
# AUDIT-2026-04-26-PHASE3-4 — constant-time compare (defence in depth)
# ---------------------------------------------------------------------------


class TestSCIMTokenConstantTimeCompare:
    """
    Verify that `SCIMToken.verify` uses `hmac.compare_digest` to compare the
    stored hash against the recomputed hash.  The DB lookup already gates
    access (PostgreSQL B-tree equality), but a constant-time secondary check
    protects against any future schema-shape change that might widen the
    matched-row set or relax the index.
    """

    def test_verify_uses_constant_time_compare(self, db):
        from apps.users import scim_models
        from apps.users.scim_models import SCIMToken

        tenant = _tenant()
        admin = _admin(tenant)
        raw_token, _instance = SCIMToken.generate(
            tenant=tenant, name="Okta", created_by=admin
        )

        # Wrap hmac.compare_digest with a MagicMock that delegates to the real
        # implementation so verify() still returns the expected result.
        side_effect_real = hmac.compare_digest
        with patch.object(
            scim_models.hmac,
            "compare_digest",
            MagicMock(side_effect=side_effect_real),
        ) as mock_cmp:
            result = SCIMToken.verify(raw_token)

        assert result is not None, "valid token must verify"
        assert mock_cmp.called, (
            "SCIMToken.verify must call hmac.compare_digest as a defence-in-depth "
            "constant-time compare against the matched-row hash"
        )

        # Sanity: at least one of the calls must compare the matched-row hash
        # (str or bytes) against the recomputed hash of the raw token.
        # The implementation is allowed to encode either side to bytes.
        called_args = []
        for call in mock_cmp.call_args_list:
            args = call.args
            # Normalise to str for comparison
            normalised = tuple(
                a.decode() if isinstance(a, (bytes, bytearray)) else a
                for a in args
            )
            called_args.append(normalised)

        # The expected DB-stored hash is the SHA-256 of raw_token
        import hashlib
        expected_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        assert any(
            expected_hash in pair for pair in called_args
        ), (
            f"compare_digest never received the stored hash {expected_hash!r}; "
            f"calls were: {called_args!r}"
        )

    def test_verify_returns_none_when_compare_digest_returns_false(self, db, caplog):
        """
        Defence-in-depth: even if a (future) DB lookup somehow returned a row,
        a False from compare_digest must fall back to None and log a warning.
        """
        from apps.users import scim_models
        from apps.users.scim_models import SCIMToken

        tenant = _tenant()
        admin = _admin(tenant)
        raw_token, _ = SCIMToken.generate(
            tenant=tenant, name="Okta", created_by=admin
        )

        with patch.object(
            scim_models.hmac,
            "compare_digest",
            MagicMock(return_value=False),
        ):
            with caplog.at_level(
                logging.WARNING, logger="apps.users.scim_models"
            ):
                result = SCIMToken.verify(raw_token)

        assert result is None, (
            "verify() must return None when compare_digest indicates mismatch, "
            "even if the DB lookup returned a row"
        )
        # WARNING log must be emitted to flag the unexpected condition
        assert any(
            "compare_digest" in record.message.lower()
            or "mismatch" in record.message.lower()
            for record in caplog.records
        ), (
            "Expected a WARNING log mentioning compare_digest/mismatch when "
            "the constant-time compare fails post-lookup; got: "
            f"{[r.message for r in caplog.records]}"
        )


# ---------------------------------------------------------------------------
# AUDIT-2026-04-26-PHASE3-13 — expires_at field
# ---------------------------------------------------------------------------


class TestSCIMTokenExpiresAt:
    """
    Verify the `expires_at` field on SCIMToken:

      - NULL  → token never expires (back-compat default).
      - past  → verify() returns None + emits WARNING log.
      - future → verify() returns the row normally.
    """

    def test_verify_accepts_token_with_no_expiry(self, db):
        from apps.users.scim_models import SCIMToken

        tenant = _tenant()
        admin = _admin(tenant)
        raw_token, instance = SCIMToken.generate(
            tenant=tenant, name="Okta", created_by=admin
        )
        # New tokens default to expires_at=None
        assert instance.expires_at is None, (
            "newly generated SCIMToken should default to expires_at=None"
        )

        result = SCIMToken.verify(raw_token)
        assert result is not None
        assert result.pk == instance.pk

    def test_verify_accepts_token_before_expiry(self, db):
        from apps.users.scim_models import SCIMToken

        tenant = _tenant()
        admin = _admin(tenant)
        raw_token, instance = SCIMToken.generate(
            tenant=tenant, name="Okta", created_by=admin
        )
        instance.expires_at = timezone.now() + timedelta(days=1)
        instance.save(update_fields=["expires_at"])

        result = SCIMToken.verify(raw_token)
        assert result is not None
        assert result.pk == instance.pk

    def test_verify_returns_none_when_token_expired(self, db, caplog):
        from apps.users.scim_models import SCIMToken

        tenant = _tenant()
        admin = _admin(tenant)
        raw_token, instance = SCIMToken.generate(
            tenant=tenant, name="Okta", created_by=admin
        )
        instance.expires_at = timezone.now() - timedelta(seconds=1)
        instance.save(update_fields=["expires_at"])

        with caplog.at_level(logging.WARNING, logger="apps.users.scim_models"):
            result = SCIMToken.verify(raw_token)

        assert result is None, (
            "Expired tokens (expires_at in the past) must be rejected by "
            "verify() — return None"
        )
        # Audit/log signal must fire so ops can spot stale-token use
        assert any(
            "expired" in record.message.lower()
            for record in caplog.records
        ), (
            "Expected a WARNING log line mentioning 'expired' when an expired "
            f"token is verified; got: {[r.message for r in caplog.records]}"
        )

    def test_verify_returns_none_when_token_expired_at_exact_now(self, db):
        """
        Boundary: verify treats expires_at <= now() as expired.
        Use a tiny safety margin so we don't race the clock.
        """
        from apps.users.scim_models import SCIMToken

        tenant = _tenant()
        admin = _admin(tenant)
        raw_token, instance = SCIMToken.generate(
            tenant=tenant, name="Okta", created_by=admin
        )
        # Set expires_at to a clearly past moment
        instance.expires_at = timezone.now() - timedelta(microseconds=1)
        instance.save(update_fields=["expires_at"])

        assert SCIMToken.verify(raw_token) is None

    def test_expires_at_field_is_nullable_and_default_null(self, db):
        """The DB schema must make expires_at nullable (NULL = no expiry)."""
        from apps.users.scim_models import SCIMToken

        field = SCIMToken._meta.get_field("expires_at")
        assert field.null is True, "expires_at must allow NULL (no expiry)"
        assert field.blank is True, "expires_at must be blank=True for admin UI"
