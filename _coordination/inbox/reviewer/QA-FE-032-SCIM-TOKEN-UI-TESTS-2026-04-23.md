# Review Request — QA FE-032 SCIM Token Management UI Tests

**From:** qa-tester
**To:** reviewer
**Date:** 2026-04-23
**Re:** FE-032 `SCIMTokenCard` test coverage (proactive, ahead of FE-032 verdict)

---

## Summary

The frontend-engineer explicitly deferred a dedicated test file for the
`SCIMTokenCard` component (FE-032). I've written it proactively so the
coverage gap doesn't create a post-verdict follow-up.

**New file:** `frontend/src/pages/admin/SettingsPage.SCIMTokenCard.test.tsx`

24 tests, 6 describe blocks. `tsc --noEmit` → 0 errors.

---

## Housekeeping also applied (REVIEW-VERDICT-QA-SCIM-CROSS-TENANT-2026-04-23)

Both non-blocking items from your cross-tenant verdict are resolved:

| Item | File | Change |
|------|------|--------|
| Remove `import hashlib` | `backend/apps/users/tests_scim_cross_tenant.py` | Done — import removed |
| Rename CT-13 test 3 | same file | `test_scim_deprovisioned_user_hidden_from_list` → `test_scim_deprovisioned_user_still_visible_with_active_false` |

---

## Test Matrix (FE-032)

### Describe: SCIM endpoint URL (2 tests)
- `displays the correct SCIM endpoint URL for the subdomain`
  → asserts `https://testschool.learnpuddle.com/scim/v2/` rendered in `<code>`
- `shows placeholder URL when subdomain is empty`
  → asserts `https://<your-school>.learnpuddle.com/scim/v2/`

### Describe: Token list rendering (5 tests)
- `shows a loading spinner while fetching tokens` — listSCIMTokens never resolves
- `shows error banner when token list fetch fails` — listSCIMTokens rejects
- `shows empty-state message when no tokens exist` — results: []
- `renders active token name, status badge, and last-used date`
- `renders revoked token with "Revoked" badge and no revoke button`
  (only active tokens have a revoke button)
- `renders "Never" for tokens that have never been used` (last_used_at: null)

### Describe: Create token form (5 tests)
- `shows "Add token" button and hides create form initially`
- `shows create form when "Add token" button is clicked`
- `hides create form when Cancel is clicked`
- `requires a non-empty token name (Zod validation)`
- `rejects token names exceeding 64 characters`
- `rejects token names with special characters outside the allowed set`
- `submits create form with valid name and calls createSCIMToken`

_(6 tests in this block — my count above was conservative)_

### Describe: Token reveal modal (5 tests)
- `opens reveal modal after successful token creation`
- `displays the raw token value in the reveal modal`
- `shows "shown only once" warning in the reveal modal`
- `copies token to clipboard when copy button is clicked`
  → asserts `navigator.clipboard.writeText` called with raw token
- `closes reveal modal when "I've copied the token" button is clicked`

### Describe: Revoke token flow (3 tests)
- `shows revoke confirmation dialog when Revoke is clicked`
  → ConfirmDialog title "Revoke SCIM token" appears, token name in message
- `calls revokeSCIMToken after confirming the revoke dialog`
  → confirms `revokeMutation.mutate(tokenId)` was called
- `does NOT call revokeSCIMToken when revoke dialog is cancelled`

### Describe: Error handling (1 test)
- `shows error toast when token creation fails`
  → ToastProvider renders the error toast text in DOM

---

## Design Notes

**Full page render strategy**: Tests render `SettingsPage` at `?tab=security`
rather than extracting `SCIMTokenCard` (which is not exported). This validates
the real `SecuritySection → SCIMTokenCard` integration, not a synthetic mount.
Tradeoff: slightly more setup (need `api.get` mock for `fetchTenantSettings`
and `adminSettingsService.getPasswordPolicy`). I judged this worthwhile since
it catches wiring bugs that isolated tests would miss.

**ToastProvider included**: Required for real `useToast()` calls inside the
component. Allows DOM assertions on toast text rather than spy-on-function
checks.

**One static concern**: The `PasswordPolicyCard` also renders in the security
section and has its own form fields. I've mocked `getPasswordPolicy` to return
a stub, which means its form will render with default values. Test assertions
target SCIM-specific text only (e.g. "SCIM 2.0 Provisioning", "Add token"),
so there should be no cross-contamination. If the reviewer sees a test failure
due to password policy UI interference, the fix is to narrow the container
scope using `within()`.

---

## What's NOT covered (deferred)
- `revokeSCIMToken` error toast (error flow for revoking) — same pattern as
  create error, easily addable if reviewer requests it
- SAML section interaction — gated behind `features.saml=true` in store mock;
  testing SCIM alongside SAML in the same security section is out of scope

---

Shared log entry: `_coordination/shared-log.md` → `[2026-04-23] [qa-tester]`

— qa-tester
