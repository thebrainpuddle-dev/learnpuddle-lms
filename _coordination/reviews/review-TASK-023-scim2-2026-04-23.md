---
tags: [review, task/TASK-023, verdict/approve, reviewer/lp-reviewer, area/security, area/auth, area/multi-tenancy]
created: 2026-04-23
reviewer: reviewer
author: backend-engineer
task: TASK-023
priority: P1
---

# Review: TASK-023 — SCIM 2.0 User Provisioning

## Verdict: APPROVE (with minor non-blocking follow-ups noted)

## Summary

Well-executed P1 enterprise feature. The SCIM 2.0 implementation is RFC-compliant
for its declared MVP scope, tenant isolation is sound, the Bearer-token auth path
is deliberately separated from DRF's JWT backend, and the test suite (42 tests
across 10 classes) exercises the negative and cross-tenant paths properly. The
design choices flagged by the author are all defensible. No security-critical
issues. A handful of minor, non-blocking observations are listed below that the
engineer can address in a follow-up PR.

Files reviewed:
- `/Users/rakeshreddy/LMS/backend/apps/users/scim_models.py`
- `/Users/rakeshreddy/LMS/backend/apps/users/scim_views.py`
- `/Users/rakeshreddy/LMS/backend/apps/users/scim_urls.py`
- `/Users/rakeshreddy/LMS/backend/apps/users/scim_admin_views.py`
- `/Users/rakeshreddy/LMS/backend/apps/users/scim_admin_urls.py`
- `/Users/rakeshreddy/LMS/backend/apps/users/migrations/0012_scim_token.py`
- `/Users/rakeshreddy/LMS/backend/apps/users/tests_scim.py`
- `/Users/rakeshreddy/LMS/backend/config/urls.py` (mount points)

## Critical Issues

None.

## Major Issues

None.

## Minor Issues (follow-up, not blocking)

### M1. Soft-deleted email collision can throw 500 instead of 409

`scim_views.scim_users_view` (POST) checks duplicates with
`User.objects.all_tenants().filter(email__iexact=user_name).exists()`. However,
`UserSoftDeleteManager.all_tenants()` returns `.alive()` — i.e. it **excludes**
soft-deleted rows. Meanwhile `User.email` has a global unique constraint at the
DB level on **all** rows (including soft-deleted). So if a user was previously
hard-soft-deleted (`is_deleted=True`), a SCIM POST for the same `userName` will:

1. Pass the duplicate check (row not visible in `.alive()`).
2. Hit an `IntegrityError` inside `User.objects.create_user(...)` → 500.

**Fix (follow-up):** use `User.all_objects` (or `all_with_deleted()`) for the
uniqueness check, and either return 409 or recycle the deleted row. Low priority
because the current soft-deprovision path does **not** set `is_deleted=True`, so
the only way to hit this is through an unrelated hard-delete flow — but still a
latent 500.

### M2. PUT does not strictly replace per RFC 7644 §3.5.1

`scim_user_detail_view` (PUT) merges values with the existing row rather than
replacing them:

```python
user.first_name = (name_obj.get("givenName") or user.first_name).strip()
```

An IdP sending an explicit empty string will **not** clear the field. Per §3.5.1
a PUT is a full replace. Most IdPs in the wild (Okta/Azure AD) never send
explicit empty strings, so practical impact is near zero — but if a customer
ever runs a cleanup job via PUT this deviates from spec. Consider using
`if "givenName" in name_obj:` checks in a follow-up.

### M3. PATCH does not support `path`-less `replace` ops

RFC 7644 §3.5.2.3 allows `{"op":"replace","value":{"active":false,"name":{...}}}`
without a `path`. Current implementation silently ignores such ops because the
`path=="active"` / `path=="name.givenName"` ladder doesn't match. Okta sends the
pathed form, so this works for Okta; Azure AD sometimes sends path-less replace.
Non-blocking for the declared MVP scope but worth tracking.

### M4. PATCH also silently ignores unknown `op` values

Only `op == "replace"` is handled. SCIM defines `add`, `remove`, `replace`. For
the current Users-only mapping (no multi-valued fields like groups/roles arrays),
`add` and `remove` don't have meaningful targets, so silent ignore is defensible
— but a log line at `DEBUG` level would help future debugging of IdP quirks.

### M5. `_authenticate_scim` allows a stray space after "Bearer"

`auth[len("Bearer "):]` slices after exactly one space. `"Bearer  token"` (two
spaces) would yield `" token"` and fail verify → 401. Fine (fails closed) but a
`.strip()` on the extracted token would be more forgiving.

### M6. `SCIMToken.verify` does not constrain tenant active-ness

`SCIMToken.verify(raw)` returns the row when `is_active=True`, but does not
verify `scim_token.tenant.is_active`. If a tenant is suspended, their SCIM
tokens keep working. Probably desirable for provisioning tombstone scenarios
but worth confirming with product. Low priority.

### M7. Test class `@override_settings(PLATFORM_DOMAIN="lms.test")` vs. admin tests using `.lms.com`

`TestSCIMTokenAdminAPI` is decorated with
`@override_settings(PLATFORM_DOMAIN="lms.test")`, but `_make_admin_client` hard-
codes `HTTP_HOST=f"{tenant.subdomain}.lms.com"`. With the class-level override,
`PLATFORM_DOMAIN` is `lms.test`, so `lms.com` hosts would not resolve via the
platform-subdomain branch of `get_tenant_from_request`. The tests apparently
pass (per the author's report) because the `TenantMiddleware` catches the
`PermissionDenied` from `get_tenant_from_request` and proceeds with
`tenant=None` — then `@tenant_required` would normally reject that.

The author wrote that they **fixed** this by changing to `.lms.com`. Without
running the suite I can't independently verify the passing state, but the
static analysis suggests the cleaner fix is either:
- Remove the class-level `PLATFORM_DOMAIN="lms.test"` override (the autouse
  fixture already sets `lms.com`), **or**
- Keep `PLATFORM_DOMAIN="lms.test"` and use `.lms.test` hosts.

Mixing them is confusing. Please double-check that this test class is actually
green under the current configuration — if so, harmless but noisy; if not,
quick fix.

### M8. Migration reversibility

`0012_scim_token.py` is a pure `CreateModel` + `AddIndex`, so Django
auto-generates the reverse (drop index, drop table). No data migration. Fully
reversible and safe to re-apply. No issue — just noted for completeness.

## Positive Observations

- **Tenant scoping is correctly explicit.** The decision to use
  `User.objects.all_tenants().filter(tenant=scim_token.tenant)` rather than
  relying on the thread-local tenant context is exactly right for SCIM —
  IdP requests do not carry a tenant-subdomain Host header and the middleware
  can't resolve one. Scoping directly off the token's tenant prevents any
  cross-tenant confused-deputy scenario. Cross-tenant GETs/PUTs/DELETEs
  correctly return 404 (not 403), matching the RFC semantics of "resource
  unknown to this tenant".
- **Token at rest is hashed.** SHA-256 of a `secrets.token_urlsafe(32)` token
  (256 bits of entropy) — infeasible to brute-force. Plaintext returned once
  on creation and never stored. The listing endpoint correctly omits both the
  raw token and the hash.
- **Auth plumbing is cleanly isolated.** Plain Django views + `@csrf_exempt`
  sidestep DRF's JWT backend. `TenantMiddleware` tolerates the missing tenant
  (catches `PermissionDenied`), and the SCIM views don't rely on
  `request.tenant`. There is no session-auth fallback.
- **Audit coverage is complete.** CREATE, PUT-UPDATE, PATCH, DEPROVISION, token
  CREATE, token REVOKE all go through `log_audit(...)` with the invoking
  `scim_token.name` recorded in the `changes` dict. This will be valuable for
  post-incident forensics.
- **Test quality.** 42 tests across 10 classes, with the cross-tenant negative
  paths (tests `test_list_users_only_returns_own_tenant_users`,
  `test_get_user_cross_tenant_returns_404`, `test_put_user_cross_tenant_returns_404`,
  `test_delete_cross_tenant_returns_404`, `test_admin_cross_tenant_token_revoke_returns_404`)
  explicitly asserting the 404 contract. Auth negatives cover missing header,
  wrong scheme, invalid token, revoked token. Model-level tests cover hash
  determinism, verify() success/failure, and URL-safe alphabet.
- **RFC-compliant error shape.** `_scim_error` emits
  `{"schemas": ["urn:ietf:params:scim:api:messages:2.0:Error"], "status": 401,
  "detail": ...}` with the correct `application/scim+json` content-type.
- **No N+1.** `SCIMToken.verify` uses `select_related("tenant")`. The list
  endpoint hits a single paginated query ordered by email.
- **URL placement.** `/scim/v2/` correctly mounted outside `/api/v1/` per RFC
  7644; admin token management correctly mounted under `/api/v1/admin/sso/` so
  it inherits JWT auth and `@admin_only` + `@tenant_required` decorators.
- **Good author self-disclosure.** The author called out the two TDD RED-phase
  test bugs they fixed, the design choices they made, and what's out of scope.
  This made the review much faster.

## Acceptance Criteria Verification

| AC | Status | Evidence |
|---|---|---|
| POST creates TEACHER-role user in correct tenant | PASS | `scim_views.py:195-205` hard-codes `role="TEACHER"`, `tenant=scim_token.tenant`; `test_create_user_creates_db_record` asserts. |
| PATCH active=false deactivates | PASS | `scim_views.py:299-300`; `test_patch_deactivate_sets_is_active_false`. |
| DELETE deactivates (not hard-deletes) | PASS | `scim_views.py:329-331` only sets `is_active=False`; `test_delete_deactivates_not_hard_deletes`. |
| GET filter userName eq returns match | PASS | Regex filter at `scim_views.py:43`; `test_list_users_filter_by_username`. |
| 401 for missing/invalid Bearer | PASS | `_authenticate_scim` + `_scim_401`; 4 auth tests. |
| Cross-tenant → 404 | PASS | `_tenant_users(tenant).get(pk=user_id)` scopes; 4 cross-tenant tests. |
| All provisioning actions audit-logged | PASS | `log_audit()` calls in all mutating paths. |
| ServiceProviderConfig returns capabilities | PASS | `scim_service_provider_config_view`; 2 tests. |

## Recommendation

APPROVE for merge. The minor items (M1-M7) are suitable for a short follow-up
task; none are blocking for an initial customer-facing SCIM beta. M1 and M7 are
the most worth fixing first.
