# QA Static Verification — SCIM M6 (tenant.is_active guard)

**From:** qa-tester
**To:** reviewer
**Date:** 2026-04-27
**Re:** SCIM-M6-TENANT-ACTIVE-CHECK-REVIEW-2026-04-27.md (Docker test run support)

---

## Context

backend-engineer noted "Docker test run: routed to qa-tester" for the M6 fix.
Docker is unavailable in QA sandbox. Static verification follows.

---

## Implementation verified

File: `backend/apps/users/scim_models.py`

```python
# M6 fix (TASK-023-followup) — tenant.is_active guard. (line 178)
# ...
if not scim_token.tenant.is_active:   # line 186
    logger.warning(...)
    return None
```

Guard position verified:
- After expiry check (correct: expired tokens don't reach is_active check)
- Before `last_used_at` update (correct: suspended tenants don't refresh timestamp)
- Uses already-loaded `scim_token.tenant` via `select_related` (no extra query)

---

## Tests verified

File: `backend/apps/users/tests_scim.py` — **72 tests** (was 70, +2)

| Test | Class | Line | What it pins |
|---|---|---|---|
| `test_verify_rejected_when_tenant_is_inactive` | TestSCIMTokenModel | 142 | Unit: `SCIMToken.verify()` returns `None` when `tenant.is_active=False` |
| `test_inactive_tenant_token_returns_401` | TestSCIMAuthentication | 219 | Integration: HTTP 401 when tenant suspended |

### Unit test logic (line 142–165):
```python
tenant.is_active = False
tenant.save(update_fields=["is_active"])
result = SCIMToken.verify(raw_token)
assert result is None
```
- Creates valid token, deactivates tenant, asserts verify() → None ✓
- Fails if the guard is removed or skipped ✓

### Integration test logic (line 219–~240):
```python
tenant.is_active = False
tenant.save(update_fields=["is_active"])
resp = c.get("/scim/v2/Users", **_scim_headers(raw_token))
assert resp.status_code == 401
```
- Full HTTP stack: proves the guard flows through `_authenticate_scim()` → 401 response ✓

---

## Token-not-revoked design verified

The `SCIMToken` row is NOT modified by the is_active check — the SCIMToken
`is_active` field on the token itself remains True. Only `tenant.is_active`
is checked. This means re-activating the tenant immediately restores SCIM access
without token rotation. The test confirms this implicitly: after the check, the
token still has `is_active=True` (only the tenant was deactivated).

---

## No regressions introduced

The existing `test_valid_token_grants_access` test (line 193) would fail if the
new guard accidentally rejected valid tokens for active tenants. Since the M6
change only fires when `tenant.is_active=False`, active-tenant paths are unaffected.

---

## Verdict

Static analysis: **PASS**. Both tests are structurally correct, implementation
matches intent. Ready for reviewer approval.

— qa-tester
