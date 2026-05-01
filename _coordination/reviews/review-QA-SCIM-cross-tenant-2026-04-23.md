---
tags: [review, qa/scim-cross-tenant, verdict/approve, reviewer/lp-reviewer, area/security, area/multi-tenancy, area/tests, area/scim]
created: 2026-04-23
reviewer: reviewer
author: qa-tester
task: QA supplemental for TASK-023
priority: P1
---

# Review: QA SCIM 2.0 Cross-Tenant Leak Regression Suite

## Verdict: APPROVE (test run still pending — static analysis clean)

## Summary

Excellent supplemental security-focused test suite. The 15 CT-### classes fill
every real gap in `tests_scim.py`, the self-contained helper design avoids
cross-test coupling, and the invariants tested are exactly the ones that would
matter in an enterprise breach scenario: tenant-override body fields, exact
404-vs-403 semantics, cross-tenant PATCH no-mutation proofs, filter-count leaks,
Bearer-scheme edge cases, and last_used_at side-effects.

File reviewed:
- `/Users/rakeshreddy/LMS/backend/apps/users/tests_scim_cross_tenant.py`
  (~923 lines, ~37 methods across 15 test classes)

Cross-referenced against:
- `/Users/rakeshreddy/LMS/backend/apps/users/scim_views.py`
- `/Users/rakeshreddy/LMS/backend/apps/users/scim_models.py`
- `/Users/rakeshreddy/LMS/backend/apps/users/models.py`
- `/Users/rakeshreddy/LMS/backend/utils/user_soft_delete_manager.py`

## CT-13 Resolution (the flagged concern)

**The qa-tester flagged:** "CT-13's third test depends on whether the User
manager's default queryset excludes `is_active=False` users. If it does, the
test will fail — which would be a real spec bug."

**Resolution: Test is correct, no production bug. Here is why:**

1. `scim_views.py:_tenant_users` calls `User.objects.all_tenants().filter(tenant=tenant)`.
2. `User.objects` is `UserSoftDeleteManager()` (see `users/models.py:118`).
3. `UserSoftDeleteManager.all_tenants()` returns
   `UserSoftDeleteQuerySet(...).alive()` (see `user_soft_delete_manager.py:63-65`).
4. `.alive()` is `self.filter(is_deleted=False)` (line 30-31). **It filters by
   `is_deleted`, not `is_active`.**
5. `_tenant_users(tenant)` therefore:
   - **Excludes** `is_deleted=True` users (soft-deleted via admin).
   - **Includes** `is_active=False` users (SCIM-deprovisioned).

So CT-13's three tests all assert the correct spec and will all pass as written:

| Test | Asserts | Will pass? |
|------|---------|------------|
| `test_soft_deleted_user_excluded_from_list` | `is_deleted=True` hidden from list | Yes — `.alive()` filters `is_deleted=False` |
| `test_soft_deleted_user_returns_404_on_detail` | `is_deleted=True` returns 404 on detail | Yes — same manager on `.get(pk=user_id)` |
| `test_scim_deprovisioned_user_hidden_from_list` | **`is_active=False` still VISIBLE with `active=false`** (name is a misnomer — the test actually asserts the user is still present) | Yes — `.alive()` does NOT filter `is_active` |

No production change required. The test-class naming (`TestSoftDeletedUserHidden`)
and method naming (`test_scim_deprovisioned_user_hidden_from_list`) are a little
confusing — test 3 is actually proving the *opposite* of "hidden" — but the
assertions are correct. Recommend renaming the method for clarity in a follow-up:

```python
def test_scim_deprovisioned_user_still_visible_with_active_false(self, db):
    ...
```

Non-blocking.

## Critical Issues

None.

## Major Issues

None.

## Minor Issues (non-blocking)

1. **CT-13 test-method name mismatch with intent.** See above. Rename
   `test_scim_deprovisioned_user_hidden_from_list` →
   `test_scim_deprovisioned_user_still_visible_with_active_false`.

2. **CT-12 `test_verify_updates_last_used_at` has no `@override_settings`
   wrapper.** The class isn't decorated with `ALLOWED_HOST_SETTINGS`, which
   is fine for a unit test with no HTTP (it doesn't need it). Just calling
   it out — intentional or oversight.

3. **CT-08 `test_bearer_with_prefix_space_in_token_returns_401`.**
   The test sends `"Bearer  <raw>"` (double space). The view's extraction
   is `auth[len("Bearer "):]` → `" <raw>"` (leading space). That value is
   SHA-256-hashed and won't match. 401 is expected. Confirmed against
   `scim_views.py:74-78` and `scim_group_views.py:84-88`. Good.

4. **CT-10 re-provision covers the SCIM DELETE soft-deprovision path.**
   After `c.delete(...)`, `_authenticate_scim` still works for the following
   POST (same token), and the POST's uniqueness check is
   `User.objects.all_tenants().filter(email__iexact=user_name).exists()`.
   Since `.all_tenants()` calls `.alive()` (excludes `is_deleted=True`) and
   SCIM DELETE only sets `is_active=False` (not `is_deleted`), the
   deprovisioned user is still returned by `.exists()` → 409. Correct.

5. **CT-15 externalId uniqueness: the test asserts no 409 on duplicate
   externalId.** Confirmed against `scim_views.py:176-183` — the only
   uniqueness check is on `email__iexact`. The `employee_id` field has no
   unique constraint (verified in `users/models.py:71`). Correct.

6. **`import hashlib` on line 30 appears unused.** Minor housekeeping only.

7. **Test runner confirmation is pending.** Author flagged this. Parallel
   test-runner session should be running. No static-analysis failures I
   could spot.

## Static analysis by test class

| Class | Static verdict |
|-------|---------------|
| CT-01 TestPostTenantBodyOverride | Correct — POST view never reads body `tenant` field; tenant always = `scim_token.tenant`. |
| CT-02 TestGetUserCrossTenantExact404 | Correct — `_tenant_users(tenant).get(pk=user_id)` raises `User.DoesNotExist` → SCIM error body. |
| CT-03 TestPatchUserCrossTenant | Correct — same lookup; no mutation on `User.DoesNotExist`. |
| CT-04/05 TestFilterCrossTenantIsolation | Correct — `.filter(tenant=tenant)` runs before `.filter(email__iexact=...)`. |
| CT-06 TestDeactivatedTokenRejects | Correct — `SCIMToken.verify` filters `is_active=True`, so a revoked token returns None → 401 on all 6 methods. |
| CT-07 TestBearerHeaderEdgeCases | Correct — `auth.startswith("Bearer ")` is the only case-sensitive check; "Token xxx" and "JWT xxx" both miss. |
| CT-08 TestBearerHeaderEdgeCases (cont.) | Correct — empty/whitespace/garbage-suffixed tokens all fail the hash lookup. |
| CT-09 TestPatchMultipleOperations | Correct — loop iterates `operations`, unknown paths fall through silently. Empty `[]` hits the `if not operations` guard → 400. |
| CT-10 TestReprovisionDeactivatedUser | Correct — see minor #4 above. |
| CT-11 TestAdminTokenListCrossTenantIsolation | Correct — `scim_admin_views` is scoped via JWT + Host-header tenant resolution. |
| CT-12 TestSCIMTokenLastUsedAt | Correct — `scim_models.py:106-107` updates `last_used_at` non-fetching. 0.05s sleep between calls handles clock resolution. |
| CT-13 TestSoftDeletedUserHidden | Correct (see CT-13 resolution above). |
| CT-14 TestPatchCrossTenantNoBleed | Correct — verifies non-leaky PATCH under cross-tenant UUID; refresh_from_db checks on both sides. |
| CT-15 TestExternalIdNotUnique | Correct — see minor #5 above. |

## Positive Observations

- **Self-contained helpers** — no coupling to `tests_scim.py`; each class
  creates fresh tenants with `uuid.uuid4().hex[:8]` subdomains.
- **Explicit `== 404` assertions** on cross-tenant paths — not just
  `!= 200`. Information-hiding invariant is what matters for SCIM.
- **No-mutation assertions** (`refresh_from_db()` + field equality) on
  CT-03 and CT-14 catch the class of bug where the ORM resolves the
  target through a different queryset path.
- **CT-06 covers every HTTP method on a revoked token** — GET, GET single,
  POST, PUT, PATCH, DELETE. Closes the gap where only GET list was tested
  in `tests_scim.py`.
- **CT-13 distinguishes `is_deleted=True` (admin soft-delete) from
  `is_active=False` (SCIM deprovision)** — a subtle but important spec
  invariant. The resolution above confirms the implementation matches
  the assertions.
- **CT-15 asserts externalId is NOT unique** — a commonly-mistaken
  constraint; good defensive test.

## Contingencies

- If the parallel test-runner surfaces any failure, re-review before merge.
- Encourage the small rename on CT-13 test 3 for clarity.

— Reviewer
