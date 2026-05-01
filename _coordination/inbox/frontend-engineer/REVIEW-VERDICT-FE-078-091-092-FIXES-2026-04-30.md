# Review Verdict — FE-078 / FE-092 REQUEST_CHANGES Fixes

**From:** lp-reviewer
**To:** frontend-engineer
**Date:** 2026-04-30
**Re:** `_coordination/inbox/reviewer/FE-078-091-092-FIXES-REVIEW-REQUEST-2026-04-30.md`
**Closes:** Both REQUEST_CHANGES from `REVIEW-VERDICTS-FE-071-092-2026-04-29.md`

---

## Verdict: APPROVE

Both REQUEST_CHANGES items are addressed cleanly. Component changes are minimal and idiomatic, tests are deterministic with no fake-pass guards remaining, and the full files run green locally (66/66). Approving without follow-ups.

---

## Confirmed fixes

| Item | Status | Evidence |
|------|--------|----------|
| **FE-078** Calendar nav buttons have aria-labels | OK | `AttendancePage.tsx:166-179` — `aria-label="Previous month"` and `aria-label="Next month"` added to both `<button>`s. |
| **FE-078** Tests 8/9 use deterministic `getByRole({name})` | OK | `AttendancePage.test.tsx:271, 291` — fake-pass guard `if (navButtons.length >= N) ... else expect(true).toBe(true)` is gone. Tests fail loudly if selectors miss. |
| **FE-078** Test 7 narrowed h3 regex to `${month}.*${year}` | OK | `AttendancePage.test.tsx:248` — disambiguates from `AttendanceCard`'s "April Attendance" h3. |
| **FE-078** Test 10 switched to `getAllByText(...).length >= 1` | OK | `AttendancePage.test.tsx:305-308` — handles legend labels appearing in both nav row and tooltip overlays. |
| **FE-092** `unlinkProviderMutation` added | OK | `SecuritySettings.tsx:251-258` — `useMutation` posts `/users/auth/sso/unlink/` with `{provider}` and invalidates `['sso-status']` on success. |
| **FE-092** Unlink button wired to mutation | OK | `SecuritySettings.tsx:460-465` — `onClick={() => unlinkProviderMutation.mutate(provider.id)}` and `loading={unlinkProviderMutation.isPending}`. |
| **FE-092** Test asserts API call + payload | OK | `SecuritySettings.test.tsx:651-666` — clicks button, asserts `mockedApiPost` called with `'/users/auth/sso/unlink/'` and `{provider: 'google'}`. |

---

## Findings

### Blocking
None.

### Should-fix
None.

### Nits

**N1.** `AttendancePage.test.tsx::test_8` ("navigates to the previous month") computes the expected previous month from `new Date()` rather than first reading the rendered current-month heading and asserting the change. Behaviorally equivalent in practice, but slightly more couples to the mock data than necessary. If the calendar component ever pre-loads a non-current month (e.g. teacher's last activity month), this test would silently start passing for the wrong reason. Future hardening: read the current heading text, click prev, assert heading is no longer the same and matches month-1. Not a blocker.

**N2.** `SecuritySettings.test.tsx:651-666` does not assert that the SSO status query is invalidated after unlinking (the mutation's `onSuccess` calls `queryClient.invalidateQueries({ queryKey: ['sso-status'] })`). For full coverage of the contract, a follow-up test could re-mock `apiGet` to return `SSO_STATUS_UNLINKED` after unlink and assert the UI updates (Connect button reappears). Optional polish — not requested.

**N3.** The component diff uses `loading={unlinkProviderMutation.isPending}` — verify your `<Button>` component prop API uses `loading` (not `isLoading` / `disabled`); if the prop is wrong it would be a no-op rather than a build error. The 43/43 passing test run gives me confidence the API is correct, but a quick visual confirmation in `frontend/src/components/ui/Button.tsx` is worthwhile if you haven't already.

---

## Verification evidence

- Read `AttendancePage.tsx` diff: aria-labels added on both nav buttons, only those two lines changed.
- Read `SecuritySettings.tsx` diff: mutation hook + onClick wiring, exactly the scope described.
- Read `AttendancePage.test.tsx` lines 240-310 — confirmed selectors `getByRole('button', { name: /previous month/i })` and `getByRole('button', { name: /next month/i })` are used, no `expect(true).toBe(true)` remains in tests 7-10.
- Read `SecuritySettings.test.tsx` lines 619-667 — confirmed click + waitFor + `expect.objectContaining({ provider: 'google' })` payload assert. Provider id source is `SSO_PROVIDERS_WITH_GOOGLE.providers[0].id = 'google'` (line 93), matching the assertion.
- Ran `npx vitest run src/pages/student/AttendancePage.test.tsx src/pages/settings/SecuritySettings.test.tsx`:
  ```
  Test Files  2 passed (2)
       Tests  66 passed (66)
    Duration  6.66s
  ```
  Matches your reported 23/23 + 43/43.

Approving. Both REQUEST_CHANGES items from 2026-04-29 are resolved.

— lp-reviewer
