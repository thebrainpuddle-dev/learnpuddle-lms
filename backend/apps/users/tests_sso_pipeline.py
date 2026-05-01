"""Tests for the SSO pipeline functions in :mod:`apps.users.sso_pipeline`.

These tests focus on Phase-3 audit finding AUDIT-2026-04-26-PHASE3-1:
``associate_by_email`` must NOT cross-link a Google identity to a user
in a different tenant than the one the OAuth callback came from.

If the request tenant cannot be resolved, the function must return
``None`` rather than fall through to an unscoped lookup that would
silently link a Google identity to whatever user happens to share the
email address.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from apps.tenants.models import Tenant
from apps.users.models import User
from apps.users.sso_pipeline import associate_by_email


pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_strategy(*, tenant_attr=None):
    """Build a fake social-auth strategy whose ``request`` exposes ``tenant``.

    The real social-auth callback runs through Django's request stack so by
    the time the pipeline runs, ``TenantMiddleware`` has already populated
    ``request.tenant``.  We mimic that.
    """
    request = SimpleNamespace(tenant=tenant_attr)
    strategy = MagicMock()
    strategy.request = request
    return strategy


def _build_backend():
    return MagicMock(name="GoogleOAuth2Backend")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_associate_by_email_returns_short_circuit_when_user_already_passed():
    """If an upstream pipeline step already resolved a user, pass through."""
    strategy = _build_strategy()
    backend = _build_backend()
    sentinel = object()
    result = associate_by_email(
        backend=backend,
        details={"email": "alice@common.com"},
        user=sentinel,
        strategy=strategy,
    )
    assert result == {"user": sentinel}


def test_associate_by_email_returns_none_when_email_missing():
    strategy = _build_strategy()
    backend = _build_backend()
    result = associate_by_email(
        backend=backend,
        details={},
        strategy=strategy,
    )
    assert result is None


def test_associate_by_email_returns_none_when_request_tenant_missing(db):
    """SECURITY: refuse to fall through to an unscoped user lookup.

    AUDIT-2026-04-26-PHASE3-1: if ``request.tenant`` is unresolved (root
    domain, callback that bypassed tenant middleware, etc.), we MUST NOT
    look up a User across tenants.  Return None and let the upstream
    pipeline produce a no-account error.
    """
    Tenant.objects.create(
        name="A School",
        slug="alpha",
        subdomain="alpha",
        email="ops@alpha.test",
        is_active=True,
    )
    User.objects.create_user(
        email="alice@common.com",
        password="x",
        first_name="Alice",
        last_name="Alpha",
        tenant=Tenant.objects.get(subdomain="alpha"),
        role="TEACHER",
    )

    strategy = _build_strategy(tenant_attr=None)
    backend = _build_backend()
    result = associate_by_email(
        backend=backend,
        details={"email": "alice@common.com"},
        strategy=strategy,
    )
    assert result is None


def test_associate_by_email_returns_none_when_strategy_request_missing(db):
    """A pipeline invocation with no ``strategy.request`` is treated as
    unresolved tenant context — return None (do not cross-link)."""
    Tenant.objects.create(
        name="A School",
        slug="alpha",
        subdomain="alpha",
        email="ops@alpha.test",
        is_active=True,
    )
    User.objects.create_user(
        email="alice@common.com",
        password="x",
        first_name="Alice",
        last_name="Alpha",
        tenant=Tenant.objects.get(subdomain="alpha"),
        role="TEACHER",
    )

    strategy = MagicMock()
    strategy.request = None
    backend = _build_backend()
    result = associate_by_email(
        backend=backend,
        details={"email": "alice@common.com"},
        strategy=strategy,
    )
    assert result is None


def test_associate_by_email_does_not_link_user_from_other_tenant(db):
    """SECURITY (AUDIT-PHASE3-1): a Google login arriving at tenant B's
    callback must NEVER be associated with a user living in tenant A,
    even when that user's email matches the Google email.

    Email is globally unique on the User model, so the canonical case is:
    Alice exists only in tenant A, but an attacker triggers Google OAuth
    at tenant B's subdomain.  ``associate_by_email`` must refuse to
    link Alice to that callback's identity.
    """
    tenant_a = Tenant.objects.create(
        name="Alpha School",
        slug="alpha",
        subdomain="alpha",
        email="ops@alpha.test",
        is_active=True,
    )
    tenant_b = Tenant.objects.create(
        name="Bravo School",
        slug="bravo",
        subdomain="bravo",
        email="ops@bravo.test",
        is_active=True,
    )
    User.objects.create_user(
        email="alice@common.com",
        password="x",
        first_name="Alice",
        last_name="Alpha",
        tenant=tenant_a,
        role="TEACHER",
    )

    # Callback comes in with tenant B context.
    strategy = _build_strategy(tenant_attr=tenant_b)
    backend = _build_backend()
    result = associate_by_email(
        backend=backend,
        details={"email": "alice@common.com"},
        strategy=strategy,
    )
    assert result is None  # MUST NOT cross-link


def test_associate_by_email_links_user_in_request_tenant(db):
    """Happy path: when the request tenant matches the user's tenant,
    ``associate_by_email`` returns that user.
    """
    tenant_a = Tenant.objects.create(
        name="Alpha School",
        slug="alpha",
        subdomain="alpha",
        email="ops@alpha.test",
        is_active=True,
    )
    user_a = User.objects.create_user(
        email="alice@common.com",
        password="x",
        first_name="Alice",
        last_name="Alpha",
        tenant=tenant_a,
        role="TEACHER",
    )

    strategy = _build_strategy(tenant_attr=tenant_a)
    backend = _build_backend()
    result = associate_by_email(
        backend=backend,
        details={"email": "alice@common.com"},
        strategy=strategy,
    )
    assert result == {"user": user_a, "is_new": False}


def test_associate_by_email_returns_none_when_no_user_in_request_tenant(db):
    """If the user simply doesn't exist (in any tenant), still return
    None — let ``create_user_if_allowed`` decide whether to provision."""
    tenant_a = Tenant.objects.create(
        name="Alpha School",
        slug="alpha",
        subdomain="alpha",
        email="ops@alpha.test",
        is_active=True,
    )
    strategy = _build_strategy(tenant_attr=tenant_a)
    backend = _build_backend()
    result = associate_by_email(
        backend=backend,
        details={"email": "nobody@common.com"},
        strategy=strategy,
    )
    assert result is None
