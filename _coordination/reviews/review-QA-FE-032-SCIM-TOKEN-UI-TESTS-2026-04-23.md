---
tags: [review, task/FE-032-tests, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-23
---

# Review: QA FE-032 — `SCIMTokenCard` UI Tests + cross-tenant housekeeping

## Verdict: APPROVE

## Summary
Comprehensive 6-describe/~24-test suite for the `SCIMTokenCard` feature
delivered proactively ahead of the FE-032 verdict. Tests render the full
`SettingsPage` at `?tab=security` to exercise real `SecuritySection →
SCIMTokenCard` wiring rather than a synthetic isolated mount — the right
trade-off. Uses `vi.resetAllMocks()` throughout, conforming to the FE-031
lint rule. The two cross-tenant housekeeping items (removing `import hashlib`,
renaming CT-13 test) are both applied correctly.

## Critical Issues
None.

## Major Issues
None.

## Minor Issues

- **Loading-spinner test is weak** (`SettingsPage.SCIMTokenCard.test.tsx:242–
  256`). The assertion body only verifies that
  `'Okta SCIM Provisioner'` is **absent** while the promise never resolves.
  That's a correct negative, but the test name is *"shows a loading spinner
  while fetching tokens"* — readers expect a positive assertion that `<Loading />`
  (or its role) is in the DOM. Tighten to:
  ```tsx
  expect(screen.getByRole('status')).toBeInTheDocument();
  // or: expect(container.querySelector('[data-testid="loading"]')).toBeTruthy();
  ```
  Not blocking — the current test would still fail if the table rendered
  prematurely, so coverage is real, just understated.

- **`rejects token names with special characters outside the allowed set`**
  (line 419). Uses `'Token <script>'` as input and matches
  `/only letters, numbers, spaces, hyphens/i`. The implementation message was
  changed during FE-032 to mention *parentheses* (and `\w` also allows
  underscores). The regex `/only letters, numbers, spaces, hyphens/i`
  still matches the current message prefix, so the test passes today — but
  if the wording gets tightened (see FE-032 minor issue), this could become
  brittle. Consider pinning to a narrower anchor like
  `/only letters.*hyphens/i` or assert on the Zod error-message constant.

- **Revoke test disambiguation** (line 594 vs 621): clicking
  `button, { name: /revoke/i }` targets the table-row button; after the
  dialog opens, the confirm button labeled *"Revoke token"* appears. Because
  the first click happens before the dialog mounts, there's no ambiguity —
  but if any UI change surfaces a second element matching `/revoke/i` in the
  same DOM (e.g. a "Revoke" column header), the first `getByRole` would
  throw. Prefer `name: /^revoke$/i` on the table-row click to be explicit.

- **Mock-queue pattern in reveal tests** (line 468–473): uses
  `mockResolvedValueOnce(...).mockResolvedValue(...)` to simulate the
  refresh after creation. That's fine, but the second resolved value
  duplicates `TOKEN_ACTIVE` with a different id/name (`{...TOKEN_ACTIVE,
  id: CREATED_TOKEN.id, name: CREATED_TOKEN.name}`) — cleaner to construct
  a dedicated fixture or spread `CREATED_TOKEN` (which is shape-compatible
  apart from missing `last_used_at`). Cosmetic.

## Positive Observations

- **Full-page render strategy is the right call.** Catches wiring regressions
  in `SecuritySection` (e.g. someone gates `SCIMTokenCard` behind a feature
  flag by accident) that an extracted mount would miss. The note about
  `PasswordPolicyCard` co-rendering and the `within()` escape hatch shows
  real forethought about cross-contamination.
- **Clipboard stub pattern is correct** (line 66–69) — `Object.defineProperty`
  with `configurable: true` avoids the jsdom "Not implemented" warning and
  allows per-test override if needed.
- **All new mocks use `resetAllMocks()`**, conforming to the FE-031 ESLint
  rule. No new `clearAllMocks` introduced.
- **Fixtures model the contract precisely**: `TOKEN_ACTIVE` with a
  `last_used_at`, `TOKEN_REVOKED` with `is_active: false` and
  `last_used_at: null`, `CREATED_TOKEN` with the raw `token` field. Each
  fixture's shape comes from the exported TypeScript interfaces in
  `adminSettingsService.ts`, so any contract drift would break compile.
- **`useTenantStore` mock** returns a realistic shape including
  `features: { saml: false }` — correctly suppresses the `SAMLSSOCard`
  render and isolates the test surface to SCIM.
- **Revoke-cancel test** (line 628–644) asserts the *negative* — that
  `revokeSCIMToken` is NOT called when "Keep active" is clicked. Critical
  for a destructive action; easy to forget.
- **Error-toast test** (line 653–676) validates the real `ToastProvider`
  DOM rendering rather than spying on `toast.error`. This is more valuable
  — it catches cases where the toast function is called but never reaches
  the DOM (e.g. provider misconfiguration).
- **Housekeeping from CT-13 verdict is complete**:
  - `backend/apps/users/tests_scim_cross_tenant.py` — `import hashlib`
    removed (grep: no match).
  - Test renamed to
    `test_scim_deprovisioned_user_still_visible_with_active_false` (line 781).
    The new name accurately reflects the behavior being tested.

## Evidence

- `frontend/src/pages/admin/SettingsPage.SCIMTokenCard.test.tsx:1–678` —
  reviewed in full.
- `backend/apps/users/tests_scim_cross_tenant.py:781` — CT-13 rename
  confirmed. `grep "import hashlib"` → 0 hits (removal confirmed).
- No new `vi.clearAllMocks` introduced — compatible with the FE-031 lint
  rule.
- Author-reported: `tsc --noEmit` 0 errors.

---

Marking QA FE-032 tests as done. The minor issues above are fine to roll
into a future tidy-up pass; they do not block the current landing.

— reviewer
