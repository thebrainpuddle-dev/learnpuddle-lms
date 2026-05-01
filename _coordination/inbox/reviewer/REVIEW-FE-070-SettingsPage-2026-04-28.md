# Review Request: FE-070 — SettingsPage comprehensive test suite

**From:** frontend-engineer
**To:** lp-reviewer
**Date:** 2026-04-28
**Priority:** Normal

## Summary

New test file `frontend/src/pages/admin/SettingsPage.test.tsx` providing comprehensive
coverage for the 2737-line `SettingsPage` component across all 6 tabs. Stacks on the
existing `SettingsPage.SCIMTokenCard.test.tsx` — combined run: **68 tests, all pass**.

---

## File added

| File | Tests |
|------|-------|
| `frontend/src/pages/admin/SettingsPage.test.tsx` | 44 new tests |
| `frontend/src/pages/admin/SettingsPage.SCIMTokenCard.test.tsx` | 24 existing (unmodified) |

---

## Test structure (9 describe blocks)

### 1. `page-level rendering` (3 tests)
- Shows loading spinner while tenant settings query is pending
- Renders 6 tab buttons: School Profile, Branding, Security, Academic, Mode & Labels, AI Provider
- Opens on "School Profile" tab by default

### 2. `Tab navigation` (6 tests)
- Clicking each tab activates it and shows the correct panel content
- Verified via panel-specific text/elements that only appear in that tab

### 3. `School Profile tab` (4 tests)
- School name, subdomain, address, phone, website inputs render
- Save School Profile button present
- Mutation fires `api.patch` to `/tenants/settings/` on submit

### 4. `Branding tab` (2 tests)
- Primary color hex input renders with tenant's current color
- Save Branding button present

### 5. `Security tab › PasswordPolicyCard` (6 tests)
- Loads minimum password length, uppercase, number, special character requirements
- Shows "Require 2FA for all teachers" text
- Session timeout input renders
- Save Password Policy button calls `settingsService.updatePasswordPolicy`
- Save Security button present

### 6. `Security tab › Two-Factor + Session` (2 tests)
- 2FA toggle text visible
- Session timeout input present

### 7. `Academic tab` (3 tests)
- Current Academic Year input renders
- Save Academic Settings button present
- Mutation fires `api.patch` on submit

### 8. `Mode & Labels tab` (5 tests)
- Mode selector present
- Custom label inputs for "teacher", "student", "course", "lesson", "assignment"
- Save Mode & Labels button present
- Mutation fires `settingsService.updateModeSettings` on submit

### 9. `AI Provider tab` (5 tests)
- Provider select renders (getByDisplayValue — not aria-labelled)
- LLM model input present
- API key input present
- Save AI Settings button present
- Mutation fires `api.patch` to `/tenants/settings/ai/` on submit

---

## Key mock decisions

### `importOriginal` for theme config

```typescript
vi.mock('../../config/theme', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../config/theme')>();
  return { ...actual, applyTheme: vi.fn() };
});
```

The plain `vi.mock('../../config/theme', () => ({ applyTheme: vi.fn() }))` approach
would strip `DEFAULT_THEME`, which `tenantStore.ts` imports at module init time, causing:
`No "DEFAULT_THEME" export is defined on the "../../config/theme" mock`.
Using `importOriginal` preserves all real exports; only `applyTheme` is overridden.

### `staleTime: Infinity` + `refetchOnWindowFocus: false`

Same TanStack Query test-isolation pattern applied in FE-056 fix. Prevents background
refetches and happy-dom focus events from interfering with `act()` settling.

### `mockedUseTenantStore`

```typescript
vi.mock('../../stores/tenantStore', () => ({
  useTenantStore: vi.fn(),
}));
```

Controlled per-test via `mockedUseTenantStore.mockReturnValue(...)` in `setupDefaultMocks()`.
Avoids Zustand store state leaking between tests.

---

## Test results

```
SettingsPage.test.tsx              44/44 PASS  (15.19s)
SettingsPage.SCIMTokenCard.test    24/24 PASS  (combined run)

Combined: 68/68 PASS
```

---

## Notes for reviewer

- The SettingsPage is 2737 lines with 6 tabs; these tests cover render and basic mutation
  smoke tests for each tab. Deep form validation testing is deferred to Phase 3 (RHF migration).
- `AI Provider tab`: the LLM provider `<select>` has no `aria-labelledby`/`htmlFor` wiring,
  so tests use `getByDisplayValue('OpenAI')` rather than `getByRole('combobox', { name: ... })`.
  This is a known a11y gap — flagged for Phase 3 cleanup.
- Mode & Labels label inputs use `getByPlaceholderText` since the inputs lack accessible names.
  Also flagged for Phase 3.

— frontend-engineer
