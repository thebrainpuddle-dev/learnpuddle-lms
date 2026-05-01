# Review Request — SCIM M6: tenant.is_active guard in SCIMToken.verify

**From:** backend-engineer
**To:** reviewer
**Date:** 2026-04-27
**Tag:** TASK-023-followup-M6

---

## Summary

Implements TASK-023 follow-up item M6: `SCIMToken.verify()` now rejects
tokens when `tenant.is_active=False`, preventing suspended tenants from
receiving SCIM provisioning calls.

## Files changed

| File | Change |
|------|--------|
| `backend/apps/users/scim_models.py` | Added `tenant.is_active` guard in `SCIMToken.verify()` (after expiry check, before `last_used_at` update) |
| `backend/apps/users/tests_scim.py` | +2 tests: `test_verify_rejected_when_tenant_is_inactive` (unit) and `test_inactive_tenant_token_returns_401` (integration) |

## What changed in scim_models.py

**New guard** added after the expiry check at line ~175 of `SCIMToken.verify()`:

```python
# M6 fix (TASK-023-followup) — tenant.is_active guard.
# A valid token on a deactivated/suspended tenant must not grant SCIM
# access. This ensures an IdP cannot create or modify users on an
# account that has been administratively suspended (e.g., payment
# failure, plan expiry). The token itself stays in the DB unchanged —
# re-activating the tenant immediately restores provisioning capability
# without requiring token rotation.
if not scim_token.tenant.is_active:
    logger.warning(
        "SCIMToken.verify: tenant is inactive — refusing SCIM access "
        "(token_id=%s tenant_id=%s)",
        scim_token.pk,
        scim_token.tenant_id,
    )
    return None
```

**No extra DB query** — the existing `select_related("tenant")` at line 134
means `scim_token.tenant` is already loaded when this check runs.

## New tests

### Unit (in `TestSCIMTokenModel`)

`test_verify_rejected_when_tenant_is_inactive`
- Creates a token, deactivates the tenant (`is_active=False`)
- Asserts `SCIMToken.verify(raw_token) is None`
- Regression pin: any future change that removes the guard will fail this test

### Integration (in `TestSCIMAuthentication`)

`test_inactive_tenant_token_returns_401`
- Creates a token, deactivates the tenant
- GET /scim/v2/Users with the valid token
- Asserts HTTP 401 (not 200)
- Confirms the guard flows through to the HTTP layer

## Design decisions

- **Token not revoked** — the token row is unchanged (still `is_active=True`
  on the `SCIMToken`). Re-activating the tenant immediately restores access.
  This is intentional: deactivation/reactivation is a tenant lifecycle event,
  not a token security event.
- **Guard position** — placed after the expiry check and before `last_used_at`
  update, so suspended tenants also don't refresh the `last_used_at` timestamp.
  This keeps `last_used_at` meaningful as an "active usage" signal.
- **Warning log** — consistent with the expiry check above it; gives ops
  visibility without flooding (one log per call, no sensitive data).

## Test count

`tests_scim.py`: **72 test methods** (was 70; +2 M6 tests).

## Verification

AST syntax check: PASS on both files.
Docker test run: routed to qa-tester (same sandbox blocker as prior SCIM reviews).

— backend-engineer
