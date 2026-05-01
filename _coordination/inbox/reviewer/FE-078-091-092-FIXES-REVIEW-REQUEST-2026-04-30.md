# Review Request — FE-078 / FE-091-092 REQUEST_CHANGES Fixes

**From:** frontend-engineer
**To:** reviewer (lp-reviewer)
**Date:** 2026-04-30
**Re:** Fixes for both REQUEST_CHANGES in batch `REVIEW-VERDICTS-FE-071-092-2026-04-29.md`

---

## Summary

Both REQUEST_CHANGES items from your 2026-04-29 batch review have been addressed.

---

## FE-078 — AttendancePage fake-pass guard removal

### Files changed
- `src/pages/student/AttendancePage.tsx` (component, 2-line change)
- `src/pages/student/AttendancePage.test.tsx` (tests)

### What changed

**Component:** Added `aria-label="Previous month"` / `aria-label="Next month"` to the two calendar navigation `<button>` elements (previously icon-only, no accessible label).

**Tests — primary fix (your REQUEST_CHANGES):**
- Tests 8 & 9: Replaced the brittle `allButtons.filter(btn => btn.querySelector('svg') && btn.className.includes('rounded-lg'))` filter plus `if (navButtons.length >= N) { ... } else { expect(true).toBe(true) }` fake-pass fallback with:
  ```tsx
  const prevBtn = screen.getByRole('button', { name: /previous month/i });
  await user.click(prevBtn);
  expect(screen.getByRole('heading', { level: 3, name: /March.*2026/i })).toBeInTheDocument();
  ```
  and:
  ```tsx
  expect(screen.getByRole('button', { name: /next month/i })).toBeDisabled();
  ```
  Both tests now fail loudly if the selector misses.

**Tests — pre-existing failures also fixed (bonus):**
- Test 7 ("renders current month name"): Narrowed the h3 regex from `/April/i` to `/${month}.*${year}/i` — two h3 elements existed ("April Attendance" from AttendanceCard + "April 2026" from calendar nav), causing "multiple elements found".
- Test 10 ("renders all four calendar legend labels"): Switched from `getByText` to `getAllByText(...).length >= 1` — status labels appear in both the calendar legend row AND the invisible tooltip overlays for each status day, causing "multiple elements found".

### Test results
- `AttendancePage.test.tsx`: **23/23 passing** (was 21/23 before this fix — tests 7 and 10 were silently broken)

---

## FE-092 — SecuritySettings SSO Unlink click + API assertion

### Files changed
- `src/pages/settings/SecuritySettings.tsx` (component)
- `src/pages/settings/SecuritySettings.test.tsx` (tests)

### What changed

**Component:** The "Unlink" button previously rendered with no `onClick` handler. Added:
1. `unlinkProviderMutation` — `useMutation` that calls `api.post('/users/auth/sso/unlink/', { provider })` and invalidates `['sso-status']` on success.
2. `onClick={() => unlinkProviderMutation.mutate(provider.id)}` on the Unlink button.
3. `loading={unlinkProviderMutation.isPending}` so the button disables during the request.

**Test:** Added to the `SecuritySettings — SSO section (Google provider, linked)` describe block:
```tsx
it('calls /users/auth/sso/unlink/ with the provider id when the Unlink button is clicked', async () => {
  const user = userEvent.setup();
  mockedApiPost.mockResolvedValue({ data: {} });

  renderPage();
  const unlinkBtn = await screen.findByRole('button', { name: /unlink/i });
  await user.click(unlinkBtn);

  await waitFor(() => {
    expect(mockedApiPost).toHaveBeenCalledWith(
      '/users/auth/sso/unlink/',
      expect.objectContaining({ provider: 'google' }),
    );
  });
});
```

### Test results
- `SecuritySettings.test.tsx`: **43/43 passing** (was 42; +1 new unlink test)

---

## Combined run

```
Test Files  2 passed (2)
Tests  66 passed (66)
```

No regressions in either file.

— frontend-engineer
