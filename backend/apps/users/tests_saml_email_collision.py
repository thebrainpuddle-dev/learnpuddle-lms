"""
SAML email-collision neutralisation tests — AUDIT-2026-04-26-PHASE3-11.

Tests written RED-first before implementation.

Asserts that:
  - provision_saml_user raises PermissionError with the generic message
    "Email unavailable." (not the old hint "This email is registered with
    another account; contact support.") when a cross-tenant collision
    is detected.
  - A logger.warning is emitted containing the existing user's tenant id
    and the attempted tenant id (SOC diagnostic data — server-side only).
"""

from __future__ import annotations

import logging
import uuid

import pytest

from apps.tenants.models import Tenant
from apps.users.models import User


pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Minimal stub objects so we can call provision_saml_user without full SAML
# ---------------------------------------------------------------------------

class _StubAssertion:
    """Minimal SAMLAssertion-like object accepted by provision_saml_user."""
    def __init__(self, email: str, first_name: str = "Test", last_name: str = "User"):
        self.email = email
        self.first_name = first_name
        self.last_name = last_name


class _StubConfig:
    """Minimal TenantSAMLConfig-like object."""
    auto_provision = True
    default_role = "TEACHER"

    def domain_allowed(self, email: str) -> bool:  # noqa: ARG002
        return True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tenant(sub: str = None) -> Tenant:
    sub = sub or uuid.uuid4().hex[:8]
    return Tenant.objects.create(
        name=f"School {sub}",
        slug=sub,
        subdomain=sub,
        email=f"admin@{sub}.test",
    )


def _make_teacher(tenant: Tenant, email: str) -> User:
    return User.objects.create_user(
        email=email,
        password="x",
        first_name="Alice",
        last_name="Smith",
        tenant=tenant,
        role="TEACHER",
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_provision_saml_user_email_collision_returns_neutral_message(caplog):
    """AUDIT-2026-04-26-PHASE3-11: cross-tenant collision must use generic message.

    The error text must be "Email unavailable." — matching the SCIM path —
    so that the IdP-visible message does not confirm email existence in
    another tenant.

    The cross-tenant diagnostic detail (existing_user.tenant_id vs
    attempted tenant.id) must appear in WARNING-level log records so
    SOC retains forensic data without surfacing it externally.
    """
    from apps.users.sso_pipeline import provision_saml_user

    tenant_a = _make_tenant("saml-a")
    tenant_b = _make_tenant("saml-b")

    # User lives in tenant A
    _make_teacher(tenant_a, "alice@cross.test")

    assertion = _StubAssertion(email="alice@cross.test")
    config = _StubConfig()

    with caplog.at_level(logging.WARNING, logger="apps.users.sso_pipeline"):
        with pytest.raises(PermissionError) as exc_info:
            provision_saml_user(tenant=tenant_b, config=config, assertion=assertion)

    # 1. The exception message must be the neutral string — no hint
    assert str(exc_info.value) == "Email unavailable.", (
        f"Expected 'Email unavailable.', got {str(exc_info.value)!r}. "
        "The SAML path must match the SCIM path (AUDIT-PHASE3-11)."
    )

    # 2. The server-side warning must contain both tenant IDs for SOC forensics
    warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warning_records, "Expected at least one WARNING log record."
    combined = " ".join(r.getMessage() for r in warning_records)
    assert str(tenant_a.id) in combined, (
        "WARNING log must include the existing user's tenant id."
    )
    assert str(tenant_b.id) in combined, (
        "WARNING log must include the attempted tenant id."
    )


def test_provision_saml_user_same_tenant_collision_raises_disabled(db):
    """A soft-deleted user in the SAME tenant raises 'User account is disabled.'
    — not the cross-tenant path."""
    from apps.users.sso_pipeline import provision_saml_user

    tenant = _make_tenant("saml-same")
    teacher = _make_teacher(tenant, "bob@same.test")
    teacher.is_deleted = True
    teacher.save(update_fields=["is_deleted"])

    assertion = _StubAssertion(email="bob@same.test")
    config = _StubConfig()

    with pytest.raises(PermissionError) as exc_info:
        provision_saml_user(tenant=tenant, config=config, assertion=assertion)

    assert "disabled" in str(exc_info.value).lower(), (
        f"Expected 'disabled' message, got {str(exc_info.value)!r}"
    )
    # Crucially, NOT "Email unavailable." — that's only for cross-tenant
    assert str(exc_info.value) != "Email unavailable."


def test_provision_saml_user_happy_path_creates_user(db):
    """Sanity: provision_saml_user creates a new user when auto_provision=True."""
    from apps.users.sso_pipeline import provision_saml_user

    tenant = _make_tenant("saml-happy")
    assertion = _StubAssertion(email="newuser@happy.test")
    config = _StubConfig()

    user = provision_saml_user(tenant=tenant, config=config, assertion=assertion)
    assert user.email == "newuser@happy.test"
    assert user.tenant_id == tenant.id
