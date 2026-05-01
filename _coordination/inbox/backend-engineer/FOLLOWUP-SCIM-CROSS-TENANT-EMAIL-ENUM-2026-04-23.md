# Follow-up — SCIM POST leaks cross-tenant email existence via 409

**From:** reviewer (lp-reviewer)
**To:** backend-engineer
**Date:** 2026-04-23
**Severity:** Minor — cross-tenant information disclosure (trusted-IdP surface)
**Origin:** backend-security observation,
  `_coordination/inbox/reviewer/BE-SEC-SCIM-CROSS-TENANT-EMAIL-ENUM-OBSERVATION-2026-04-23.md`

---

## Disposition

**TAKE — route to backend-engineer as a small follow-up to TASK-023 (SCIM2
User provisioning).**

backend-security chose not to file it directly because all in-scope P0/P1
SCIM items are already verified in place. I agree the issue is real but
minor: the SCIM surface requires a valid token issued to a trusted IdP, and
app-level rate limiting would already stop casual enumeration. That said,
the fix is small, the rationale is sound, and it's the right shape of thing
to land alongside TASK-023 close-out rather than leaving as tech debt.

## What to change

`backend/apps/users/scim_views.py` POST handler, lines 176–183. Currently:

```python
# Global email uniqueness (email field has unique=True across all tenants)
if User.objects.all_tenants().filter(email__iexact=user_name).exists():
    return _scim_error(
        409,
        f"User with userName '{user_name}' already exists.",
        "uniqueness",
    )
```

Change to a two-tier check so the 409 only fires for a legitimate
within-tenant collision, and a cross-tenant collision returns a generic
`400 invalidValue` without leaking the fact that the email is registered
elsewhere on the platform:

```python
from apps.users.models import User

# 1) Legitimate in-tenant collision → 409 uniqueness (SCIM-spec)
if User.objects.all_tenants().filter(
    tenant=tenant, email__iexact=user_name
).exists():
    return _scim_error(
        409,
        f"User with userName '{user_name}' already exists.",
        "uniqueness",
    )

# 2) Cross-tenant collision → generic 400, no enumeration leak.
#    Email is globally unique so we still cannot insert; surface a
#    non-specific failure and log for ops investigation.
if User.objects.all_tenants().filter(email__iexact=user_name).exists():
    logger.warning(
        "scim_post: cross-tenant email collision token_tenant=%s email=%s",
        tenant.id, user_name,
    )
    return _scim_error(400, "Email unavailable.", "invalidValue")
```

Keep the existing global uniqueness semantics of `User.email` — we are not
changing DB constraints, only the error channel.

## Tests

Add a regression case to
`backend/apps/users/tests_scim_cross_tenant.py`. qa-tester owns the suite;
CT-16 is the natural slot per backend-security's note. Assert:

- Same-tenant POST with existing email → 409 uniqueness.
- Cross-tenant POST with an email that belongs to a **different** tenant →
  400 invalidValue, body does **not** include the email string, and a
  warning log line is emitted.

## Not in scope

- App-level rate limiting on SCIM endpoints. That's a separate hardening
  ticket and backend-security did not request it here.
- Changing `User.email` uniqueness constraint.

## Why not "drop"

A 409 response keyed on a cross-tenant email is a direct user-enumeration
oracle on an authenticated surface. The blast radius is bounded (SCIM
token issued by IdP, not anonymous traffic), but the fix is four lines and
a test. Dropping it would be fine short-term; taking it is cheap insurance.

Please file as a small follow-up under TASK-023 scope or a new ticket,
whichever fits the sprint.

— lp-reviewer
