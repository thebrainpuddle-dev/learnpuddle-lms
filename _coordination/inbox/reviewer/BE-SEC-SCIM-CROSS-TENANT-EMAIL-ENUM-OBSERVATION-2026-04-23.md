# Observation — SCIM POST leaks cross-tenant email existence via 409

**From:** backend-security
**To:** reviewer (lp-reviewer)
**Date:** 2026-04-23
**Severity:** Minor — cross-tenant information disclosure, low real-world impact
**Status:** Observation (not filing a task; deferring routing to reviewer)

---

## Summary

`scim_users_view` (POST) in `backend/apps/users/scim_views.py:166–183` returns
`409 scimType=uniqueness` when the requested `userName` already exists in **any**
tenant, not just the tenant bound to the calling SCIM token.

```python
# scim_views.py:178–183
if User.objects.all_tenants().filter(email__iexact=user_name).exists():
    return _scim_error(
        409,
        f"User with userName '{user_name}' already exists.",
        "uniqueness",
    )
```

Because `User.email` is globally unique, this check is semantically correct
for ensuring the insert will succeed. However, the 409 response reveals the
existence of an email address in a different tenant to the caller.

## Threat model

- Requires a valid SCIM token (issued to trusted IdPs like Okta / Azure AD).
- An attacker with a leaked SCIM token for Tenant A can probe arbitrary
  email addresses and discover whether they are registered *somewhere on
  the platform* (though not which tenant).
- Already bounded by the SCIM token rate at the IdP side, but the SCIM
  endpoints have no app-level rate limit.

## Suggested fix (if accepted)

Two-tier uniqueness check:

```python
# 1. Uniqueness inside the token's tenant — legitimate 409
if User.objects.all_tenants().filter(tenant=tenant, email__iexact=user_name).exists():
    return _scim_error(409, f"User with userName '{user_name}' already exists.", "uniqueness")

# 2. Clash with a different tenant — generic 400, no enumeration leak
if User.objects.all_tenants().filter(email__iexact=user_name).exists():
    logger.warning(
        "scim_post: cross-tenant email collision token_tenant=%s email=%s",
        tenant.id, user_name,
    )
    return _scim_error(400, "Email unavailable.", "invalidValue")
```

Add the corresponding regression test to
`backend/apps/users/tests_scim_cross_tenant.py` (qa-tester owns that suite;
CT-16 would be the natural slot).

## Why I am not filing a task

1. All five P0 and three in-scope P1 items are verified in place today
   (see shared-log entry 2026-04-23 for evidence table).
2. SCIM is a trusted-IdP-only surface; exposure is not reachable by
   unauthenticated traffic.
3. Fix requires a small behavioral spec decision (generic 400 vs scimType
   mismatch) that belongs with the reviewer or backend-engineer owning
   TASK-023.

Routing to reviewer for disposition: take, drop, or forward to
backend-engineer.

— backend-security
