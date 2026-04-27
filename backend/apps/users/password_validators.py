# apps/users/password_validators.py
"""
Tenant-aware Django password validator.

Registered in ``AUTH_PASSWORD_VALIDATORS`` in settings.  At validation
time it looks up the current tenant via ``utils.tenant_middleware`` and
consults :class:`apps.tenants.TenantPasswordPolicy` for composition
rules.  When no tenant is resolvable (management commands, super-admin
flows) it falls back to :meth:`TenantPasswordPolicy.default_values`
which is deliberately strict — we never weaken the platform baseline
silently.
"""

from __future__ import annotations

import re
from typing import Optional

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _


_SPECIAL_RE = re.compile(r"[^A-Za-z0-9]")
_UPPER_RE = re.compile(r"[A-Z]")
_LOWER_RE = re.compile(r"[a-z]")
_DIGIT_RE = re.compile(r"\d")


def _resolve_policy():
    """Return a dict of policy values — tenant-aware with strict fallback."""
    from apps.tenants.password_policy_models import TenantPasswordPolicy
    from utils.tenant_middleware import get_current_tenant

    tenant = get_current_tenant()
    if tenant is not None:
        try:
            return TenantPasswordPolicy.objects.get(tenant=tenant).as_dict()
        except TenantPasswordPolicy.DoesNotExist:
            pass
    return TenantPasswordPolicy.default_values()


class TenantPasswordValidator:
    """Validates composition rules + (optional) history against tenant policy."""

    def __init__(self, default_min_length: int = 8) -> None:
        self.default_min_length = default_min_length

    # Django will call this both directly and via validate_password().
    def validate(self, password: str, user=None) -> None:
        policy = _resolve_policy()
        errors = []

        if len(password) < policy["min_length"]:
            errors.append(
                _("Password must be at least %(n)d characters.") % {"n": policy["min_length"]}
            )
        if policy["require_uppercase"] and not _UPPER_RE.search(password):
            errors.append(_("Password must contain at least one uppercase letter."))
        if policy["require_lowercase"] and not _LOWER_RE.search(password):
            errors.append(_("Password must contain at least one lowercase letter."))
        if policy["require_digit"] and not _DIGIT_RE.search(password):
            errors.append(_("Password must contain at least one digit."))
        if policy["require_special"] and not _SPECIAL_RE.search(password):
            errors.append(_("Password must contain at least one special character."))

        if policy["prevent_common"]:
            # Lazy import to reuse Django's vetted list without re-distributing it.
            from django.contrib.auth.password_validation import CommonPasswordValidator

            try:
                CommonPasswordValidator().validate(password)
            except ValidationError:
                errors.append(_("This password is too common."))

        # History check: only meaningful if we have a persistent user.
        n = policy["prevent_reuse_last_n"]
        if n and user is not None and getattr(user, "pk", None):
            from django.contrib.auth.hashers import check_password

            from apps.users.models import PasswordHistory

            previous = PasswordHistory.objects.filter(user=user).order_by("-created_at")[:n]
            # Also compare with the currently-set password to catch same-password reuse.
            current_hash = getattr(user, "password", "") or ""
            candidates = [ph.hashed_password for ph in previous]
            if current_hash:
                candidates.append(current_hash)
            for hashed in candidates:
                try:
                    if check_password(password, hashed):
                        errors.append(
                            _("Password matches one of your last %(n)d passwords; choose a new one.")
                            % {"n": n}
                        )
                        break
                except Exception:
                    continue

        if errors:
            raise ValidationError(errors)

    def get_help_text(self) -> str:
        policy = _resolve_policy()
        parts = [f"at least {policy['min_length']} characters"]
        if policy["require_uppercase"]:
            parts.append("one uppercase letter")
        if policy["require_lowercase"]:
            parts.append("one lowercase letter")
        if policy["require_digit"]:
            parts.append("one digit")
        if policy["require_special"]:
            parts.append("one special character")
        if policy["prevent_reuse_last_n"]:
            parts.append(f"not one of your last {policy['prevent_reuse_last_n']} passwords")
        return "Passwords must contain " + ", ".join(parts) + "."


def record_password_history(user, raw_password: Optional[str] = None) -> None:
    """Persist the *currently hashed* password for history-based reuse checks.

    Callers should invoke this immediately after ``user.set_password(...)``
    + ``user.save()`` so that the stored hash corresponds to the password
    the user just chose.  We deliberately do not accept the plaintext.
    """
    from apps.users.models import PasswordHistory

    hashed = getattr(user, "password", "") or ""
    if not hashed:
        return
    PasswordHistory.objects.create(user=user, hashed_password=hashed)

    # Trim history beyond whatever the current policy asks for (+ a
    # small buffer) so we don't grow unbounded.
    try:
        from apps.tenants.password_policy_models import TenantPasswordPolicy

        policy = None
        if getattr(user, "tenant_id", None):
            policy = TenantPasswordPolicy.objects.filter(tenant_id=user.tenant_id).first()
        keep = max((policy.prevent_reuse_last_n if policy else 0), 10)
        ids_to_keep = list(
            PasswordHistory.objects.filter(user=user)
            .order_by("-created_at")
            .values_list("id", flat=True)[:keep]
        )
        PasswordHistory.objects.filter(user=user).exclude(id__in=ids_to_keep).delete()
    except Exception:
        # History trimming is best-effort — never block a password change.
        pass


def is_password_expired(user) -> bool:
    """Return True if the user must rotate per their tenant's max_age_days."""
    import datetime as _dt

    from apps.tenants.password_policy_models import TenantPasswordPolicy

    if not getattr(user, "tenant_id", None):
        return False
    try:
        policy = TenantPasswordPolicy.objects.get(tenant_id=user.tenant_id)
    except TenantPasswordPolicy.DoesNotExist:
        return False
    if not policy.max_age_days:
        return False
    # Look at the latest password history row if we have one; otherwise use user.updated_at.
    from apps.users.models import PasswordHistory

    latest = (
        PasswordHistory.objects.filter(user=user).order_by("-created_at").first()
    )
    reference = latest.created_at if latest else getattr(user, "updated_at", None)
    if reference is None:
        return False
    return reference < _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=policy.max_age_days)
