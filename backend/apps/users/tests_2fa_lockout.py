"""
Per-account 2FA lockout tests (AUDIT-2026-04-26-PHASE3-8).

The existing ``twofa_verify`` endpoint relies on a per-IP
``ScopedRateThrottle`` only.  An attacker rotating IPs can iterate through
the 1M-entry TOTP space or the 8-character backup code space without
hitting the throttle.  These tests assert the new defences:

  - Per-`challenge_token` failure counter: after 5 wrong codes the
    challenge is destroyed and the endpoint returns 429.
  - Per-`(user_id, IP)` lockout: after 5 wrong codes from the same IP
    the user remains locked even if the attacker forces a password
    re-auth and obtains a fresh challenge_token.
  - The lockout response carries a stable error code
    (``code="too_many_2fa_attempts"``) so the FE can distinguish from a
    normal "wrong code" 400.
  - The lockout self-heals after the cache key TTL expires.
"""

from __future__ import annotations

import uuid

import pytest
from django.core.cache import cache
from django.test import Client, override_settings
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.tenants.models import Tenant
from apps.users.models import User

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tenant() -> Tenant:
    sub = uuid.uuid4().hex[:8]
    return Tenant.objects.create(
        name=f"School {sub}",
        slug=sub,
        subdomain=sub,
        email=f"admin@{sub}.test",
    )


def _make_user_with_2fa(tenant: Tenant):
    """Create a user with a confirmed TOTP device + a backup code."""
    user = User.objects.create_user(
        email=f"user-{uuid.uuid4().hex[:6]}@test.com",
        password="Password123!",
        first_name="Jane",
        last_name="Doe",
        tenant=tenant,
        role="TEACHER",
    )
    totp = TOTPDevice.objects.create(user=user, name="default", confirmed=True)
    static = StaticDevice.objects.create(user=user, name="backup", confirmed=True)
    StaticToken.objects.create(device=static, token="VALIDBACKUPCODE")
    return user, totp


def _issue_challenge(user) -> str:
    """Mimic the login view: store a challenge_token in cache."""
    import secrets
    token = secrets.token_urlsafe(32)
    cache.set(f"2fa_challenge:{token}", str(user.id), timeout=600)
    return token


@pytest.fixture(autouse=True)
def _flush_cache():
    cache.clear()
    yield
    cache.clear()


# ---------------------------------------------------------------------------
# 1. Per-challenge lockout: 5 wrong codes destroy the challenge
# ---------------------------------------------------------------------------

def test_twofa_verify_locks_out_after_5_wrong_codes_for_same_challenge():
    tenant = _make_tenant()
    user, _ = _make_user_with_2fa(tenant)
    token = _issue_challenge(user)

    c = Client()
    # 5 wrong attempts must each return 400 (invalid code).
    for i in range(5):
        resp = c.post(
            "/api/users/auth/2fa/verify/",
            data={"challenge_token": token, "code": "000000"},
            content_type="application/json",
        )
        assert resp.status_code == 400, f"attempt {i+1} returned {resp.status_code}"

    # 6th attempt must be 429 (lockout).
    resp = c.post(
        "/api/users/auth/2fa/verify/",
        data={"challenge_token": token, "code": "000000"},
        content_type="application/json",
    )
    assert resp.status_code == 429
    body = resp.json()
    assert body.get("code") == "too_many_2fa_attempts"

    # The challenge_token must be destroyed; even the *correct* code
    # cannot resurrect this challenge.
    assert cache.get(f"2fa_challenge:{token}") is None


# ---------------------------------------------------------------------------
# 2. Correct code does NOT count toward the lockout
# ---------------------------------------------------------------------------

@override_settings(OTP_STATIC_THROTTLE_FACTOR=0, OTP_TOTP_THROTTLE_FACTOR=0)
def test_twofa_verify_does_not_count_correct_against_lockout():
    """A few wrong attempts followed by the correct backup code returns
    200; a *fresh* challenge after that has a clean counter (the
    success path resets all attempt state).

    We disable django-otp's per-device throttling for this test so
    that the *correct* backup code on the 3rd attempt is not rejected
    by upstream's exponential back-off — that's a different concern
    (and would conflate two separate defences).
    """
    tenant = _make_tenant()
    user, _ = _make_user_with_2fa(tenant)
    token = _issue_challenge(user)

    c = Client()

    # 2 wrong codes — clearly under our 5-attempt threshold AND
    # under django-otp's throttle.
    for _ in range(2):
        resp = c.post(
            "/api/users/auth/2fa/verify/",
            data={"challenge_token": token, "code": "000000"},
            content_type="application/json",
        )
        assert resp.status_code == 400

    # Correct backup code → 200
    resp = c.post(
        "/api/users/auth/2fa/verify/",
        data={"challenge_token": token, "code": "VALIDBACKUPCODE"},
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.content

    # New challenge after a fresh password re-auth — must NOT be locked.
    # The per-user counter was cleared by the successful verify, so a
    # single wrong code should produce 400, not 429.
    new_token = _issue_challenge(user)
    resp = c.post(
        "/api/users/auth/2fa/verify/",
        data={"challenge_token": new_token, "code": "000000"},
        content_type="application/json",
    )
    assert resp.status_code == 400  # back to "invalid code", not 429


# ---------------------------------------------------------------------------
# 3. Per-account lockout holds across challenge tokens (defence against
#    attacker who burns one challenge then password-re-auths to get a new
#    one).
# ---------------------------------------------------------------------------

def test_twofa_verify_per_user_lockout_holds_across_challenge_tokens():
    tenant = _make_tenant()
    user, _ = _make_user_with_2fa(tenant)
    token1 = _issue_challenge(user)

    c = Client()
    # Burn the first challenge with 5 wrong attempts.
    for _ in range(5):
        c.post(
            "/api/users/auth/2fa/verify/",
            data={"challenge_token": token1, "code": "000000"},
            content_type="application/json",
        )

    # Attacker re-authenticates with the password and gets a brand-new
    # challenge token.
    token2 = _issue_challenge(user)

    # Even on the very first attempt with the new token, the user is
    # still locked because the per-(user, IP) counter persists.
    resp = c.post(
        "/api/users/auth/2fa/verify/",
        data={"challenge_token": token2, "code": "000000"},
        content_type="application/json",
    )
    assert resp.status_code == 429
    assert resp.json().get("code") == "too_many_2fa_attempts"


# ---------------------------------------------------------------------------
# 4. Lockout resets after TTL expires
# ---------------------------------------------------------------------------

def test_twofa_verify_lockout_resets_after_ttl():
    tenant = _make_tenant()
    user, _ = _make_user_with_2fa(tenant)
    token = _issue_challenge(user)

    c = Client()
    # Drive the per-user lockout.
    for _ in range(5):
        c.post(
            "/api/users/auth/2fa/verify/",
            data={"challenge_token": token, "code": "000000"},
            content_type="application/json",
        )

    # Confirm we're locked.
    new_token = _issue_challenge(user)
    resp = c.post(
        "/api/users/auth/2fa/verify/",
        data={"challenge_token": new_token, "code": "000000"},
        content_type="application/json",
    )
    assert resp.status_code == 429

    # Simulate TTL expiry by clearing cache (the per-user lockout key
    # would naturally drop after its 15-min TTL).
    cache.clear()

    # New challenge after lockout expires must accept attempts again.
    fresh = _issue_challenge(user)
    resp = c.post(
        "/api/users/auth/2fa/verify/",
        data={"challenge_token": fresh, "code": "000000"},
        content_type="application/json",
    )
    assert resp.status_code == 400, "Lockout should self-heal after TTL"


# ---------------------------------------------------------------------------
# 5. Lockout response carries a specific error code for FE handling.
# ---------------------------------------------------------------------------

def test_twofa_verify_returns_specific_error_code_for_lockout():
    tenant = _make_tenant()
    user, _ = _make_user_with_2fa(tenant)
    token = _issue_challenge(user)

    c = Client()
    for _ in range(5):
        c.post(
            "/api/users/auth/2fa/verify/",
            data={"challenge_token": token, "code": "000000"},
            content_type="application/json",
        )

    resp = c.post(
        "/api/users/auth/2fa/verify/",
        data={"challenge_token": token, "code": "000000"},
        content_type="application/json",
    )
    assert resp.status_code == 429
    body = resp.json()
    assert body.get("code") == "too_many_2fa_attempts"
    # And a human-readable detail.
    assert "2fa" in body.get("detail", "").lower() or \
           "attempts" in body.get("detail", "").lower()
