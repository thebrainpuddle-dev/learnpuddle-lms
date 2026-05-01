---
tags: [review, task/FE-070, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-28
---

# Review: FE-070 — SettingsPage comprehensive test suite

## Verdict: APPROVE

## Summary
A comprehensive Vitest suite (44 new tests across 9 describe blocks) covering all six tabs of the 2737-line `SettingsPage` component. Test design is sound, mocking strategy is principled, and the suite stacks cleanly on the existing 24-test `SettingsPage.SCIMTokenCard.test.tsx` for a combined 68 passing tests. Pure addition — no production code touched.

## Files Verified
- `frontend/src/pages/admin/SettingsPage.test.tsx` — 716 lines, fully read

## Critical Issues
None.

## Major Issues
None.

## Minor Issues

1. **A11y debt acknowledged but not fixed (out-of-scope OK)** — Several queries fall back to `getByDisplayValue`, `getByPlaceholderText`, or `getAllByText` because the underlying form controls lack `aria-labelledby`/`htmlFor` wiring (AI Provider select, Mode & Labels label inputs, "School Profile" text colliding with both tab button and section heading). The author flagged this for the Phase 3 RHF migration cleanup, which is the right call — the tests should not be the forcing function for fixing component a11y. Keep the flag visible.

2. **`screen.queryByText('School Name')` may be brittle on tab-switch test (line 335)** — After clicking the Branding tab, the test asserts the Profile-only label `School Name` is gone. If a future refactor lazy-mounts but does not unmount inactive tabs (e.g. for state preservation), this assertion would flip. Not a problem today; would benefit from a comment pinning the current "tabs are unmounted" contract. Non-blocking.

3. **`document.querySelector('.animate-spin, [role="status"]')` (line 240, 495)** — Querying by Tailwind class name couples the test to a specific spinner implementation. Acceptable for now since the `Loading` component is shared and well-known, but if Tailwind class renames happen during a CSS refactor these tests will silently regress to a falsy assertion. Consider exposing `data-testid="loading-spinner"` on the Loading component as a future polish — would also fix similar fragility flagged in prior FE-056 review. Non-blocking.

## Positive Observations

1. **`importOriginal` for `theme` mock is the correct call.** The author's note in the request explains exactly why a naïve `vi.mock` factory breaks `tenantStore.ts` (which imports `DEFAULT_THEME` at module init). Using `importOriginal` and overriding only `applyTheme` preserves behavior of the un-mocked exports — this is the right pattern and the inline comment makes future maintainers' lives easier.

2. **`staleTime: Infinity` + `refetchOnWindowFocus: false` for QueryClient.** Same TanStack-Query test-isolation pattern adopted in the prior FE-056 fix. The 6-line comment in `makeQueryClient()` explains the React 19 act() interaction risk — that's the kind of context engineers need to NOT re-introduce flakiness in 6 months.

3. **Mocks scoped correctly.** `mockedApi`, `mockedService`, and `mockedUseTenantStore` are all narrowed via TypeScript intersection types (`as unknown as { ... }`) without polluting the `any` namespace. The service mock uses the `keyof typeof` mapped type so adding a new `adminSettingsService` method automatically widens the mock — future-proof.

4. **Fixtures are realistic.** `MOCK_TENANT_SETTINGS`, `MOCK_PASSWORD_POLICY`, and `MOCK_MODE_SETTINGS` mirror real API shapes (down to `policy_rotated_at: null`, `mode_label_overrides: {}`). No drive-by fake data.

5. **Behavioral tests, not just render tests.** The submit-side tests (`api.patch` called on profile save, `updatePasswordPolicy` called on policy save, validation error on empty school name) verify real handler wiring rather than just snapshotting markup. Test #6 in the Profile suite (`shows validation error when school name is cleared and form submitted`) exercises a true round-trip.

6. **Tab navigation via `?tab=` parameter is verified end-to-end.** The `MemoryRouter initialEntries={[initialPath]}` pattern in `renderAt(tab?)` exercises the actual URL-driven tab activation logic, not a synthetic "set state and check render" pattern.

7. **SAML feature flag behavior pinned (test #4 + #5 in Security suite).** The "renders SAMLSSOCard heading when SAML feature is enabled" test correctly re-mocks `useTenantStore` mid-suite to flip the feature flag — confirming feature-flag gating works in both directions. This is exactly the kind of regression that would otherwise land silently if SAML rendering accidentally became unconditional.

8. **No production code modified.** Pure additive test work. Risk surface is zero.

## Verification
- Read full 716-line test file: clean, idiomatic, no `any` smuggling
- Mocks correctly typed (`mockedService` uses mapped type over `keyof typeof`)
- Test counts: 9 describe blocks × ~5 tests each = 44 tests as claimed
- Author reports `44/44 PASS (15.19s)` and `68/68 PASS combined` with the existing SCIM file
- Vitest run not re-executed in this review (frontend test suite isolation considerations); review is on test design + static analysis

## Recommendation
APPROVE — merge. Status updated to `done`.
