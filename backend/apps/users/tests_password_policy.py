"""Tests for TenantPasswordValidator + PasswordHistory.

Run with: ``pytest apps/users/tests_password_policy.py``.
"""

from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError

from apps.tenants.models import Tenant
from apps.tenants.password_policy_models import TenantPasswordPolicy
from apps.users.models import PasswordHistory, User
from apps.users.password_validators import (
    TenantPasswordValidator,
    record_password_history,
)
from utils.tenant_middleware import clear_current_tenant, set_current_tenant


pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant(db):
    t = Tenant.objects.create(
        name="Policy Test School",
        slug="policy-test",
        subdomain="policy-test",
        email="admin@policy-test.edu",
    )
    yield t
    clear_current_tenant()


@pytest.fixture
def strict_policy(tenant):
    return TenantPasswordPolicy.objects.create(
        tenant=tenant,
        min_length=10,
        require_uppercase=True,
        require_lowercase=True,
        require_digit=True,
        require_special=True,
        prevent_common=True,
        prevent_reuse_last_n=3,
    )


def test_validator_enforces_min_length(tenant, strict_policy):
    set_current_tenant(tenant)
    with pytest.raises(ValidationError):
        TenantPasswordValidator().validate("Ab1!short")


def test_validator_requires_uppercase(tenant, strict_policy):
    set_current_tenant(tenant)
    with pytest.raises(ValidationError):
        TenantPasswordValidator().validate("abcdefg1!xx")


def test_validator_requires_special(tenant, strict_policy):
    set_current_tenant(tenant)
    with pytest.raises(ValidationError):
        TenantPasswordValidator().validate("Abcdefghi1")


def test_validator_accepts_strong_password(tenant, strict_policy):
    set_current_tenant(tenant)
    # should not raise
    TenantPasswordValidator().validate("StrongPass1!xx")


def test_validator_falls_back_to_strict_default_with_no_tenant(db):
    clear_current_tenant()
    with pytest.raises(ValidationError):
        # 8 chars — shorter than 12-char default fallback baseline.
        TenantPasswordValidator().validate("Abcd123!")
    TenantPasswordValidator().validate("StrongPass1!Absolutely")


def test_prevent_reuse_last_n_blocks_recent_password(tenant, strict_policy):
    set_current_tenant(tenant)
    user = User.objects.create_user(
        email="p@policy-test.edu",
        first_name="P",
        last_name="U",
        tenant=tenant,
        password="OldPassword1!",
    )
    record_password_history(user)

    # Attempting to reuse the exact same plaintext must be rejected.
    with pytest.raises(ValidationError):
        TenantPasswordValidator().validate("OldPassword1!", user=user)


def test_prevent_reuse_allows_new_password_after_rotations(tenant, strict_policy):
    set_current_tenant(tenant)
    user = User.objects.create_user(
        email="rot@policy-test.edu",
        first_name="R",
        last_name="U",
        tenant=tenant,
        password="Pass1234!abc",
    )
    record_password_history(user)

    # Advance through several rotations greater than prevent_reuse_last_n.
    for pw in ("Pass1234!def", "Pass1234!ghi", "Pass1234!jkl", "Pass1234!mno"):
        user.set_password(pw)
        user.save()
        record_password_history(user)

    # The very first password should no longer be in the last-3 window.
    TenantPasswordValidator().validate("Pass1234!abc", user=user)


def test_lockout_threshold_respects_policy(tenant, strict_policy, settings):
    """Verify login serializer consults tenant policy for threshold."""
    from apps.users.serializers import _lockout_policy

    strict_policy.lockout_threshold = 2
    strict_policy.lockout_duration_minutes = 7
    strict_policy.save()

    threshold, duration = _lockout_policy(tenant)
    assert threshold == 2
    assert duration == 7 * 60


def test_refresh_token_rejected_after_policy_rotation(tenant, strict_policy):
    """H1 regression: bumping policy_rotated_at invalidates older refresh tokens."""
    import time
    from datetime import datetime, timezone, timedelta
    from apps.users.tokens import get_tokens_for_user
    from apps.users.token_policy import enforce_token_freshness
    from rest_framework_simplejwt.tokens import RefreshToken

    set_current_tenant(tenant)
    user = User.objects.create_user(
        email="rt@policy-test.edu",
        first_name="R",
        last_name="T",
        tenant=tenant,
        password="StrongPass1!xx",
    )
    # Issue a token NOW, then rotate policy in the future.
    tokens = get_tokens_for_user(user)
    rt = RefreshToken(tokens["refresh"])

    # Freshness check should pass immediately after issue.
    enforce_token_freshness(rt)

    # Rotate the policy 10 seconds *after* the token was issued.
    strict_policy.policy_rotated_at = datetime.now(timezone.utc) + timedelta(seconds=10)
    strict_policy.save(update_fields=["policy_rotated_at"])

    with pytest.raises(ValueError):
        enforce_token_freshness(rt)


def test_refresh_token_rejected_after_user_password_change(tenant, strict_policy):
    """User rotating their own password must invalidate prior refresh tokens."""
    from datetime import datetime, timezone, timedelta
    from apps.users.tokens import get_tokens_for_user
    from apps.users.token_policy import enforce_token_freshness
    from rest_framework_simplejwt.tokens import RefreshToken

    set_current_tenant(tenant)
    user = User.objects.create_user(
        email="rt2@policy-test.edu",
        first_name="R",
        last_name="T",
        tenant=tenant,
        password="StrongPass1!xx",
    )
    tokens = get_tokens_for_user(user)
    rt = RefreshToken(tokens["refresh"])

    # Bump password_changed_at to a moment in the future so the older
    # token's iat predates it.
    user.password_changed_at = datetime.now(timezone.utc) + timedelta(seconds=10)
    user.save(update_fields=["password_changed_at"])

    with pytest.raises(ValueError):
        enforce_token_freshness(rt)


def test_record_password_history_trims_old_rows(tenant, strict_policy):
    set_current_tenant(tenant)
    user = User.objects.create_user(
        email="trim@policy-test.edu",
        first_name="T",
        last_name="U",
        tenant=tenant,
        password="Initial1!abcd",
    )
    # Push 20 rotations; the trimmer should cap total history at
    # max(policy.prevent_reuse_last_n, 10) = 10.
    for i in range(20):
        user.set_password(f"Rotated{i}!abcdZ")
        user.save()
        record_password_history(user)
    assert PasswordHistory.objects.filter(user=user).count() <= 10
