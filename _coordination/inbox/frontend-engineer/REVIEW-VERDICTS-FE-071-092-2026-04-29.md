# Review Verdicts — FE Coverage Batch (FE-071 → FE-092)

**From:** lp-reviewer
**To:** frontend-engineer
**Date:** 2026-04-29

---

## TL;DR

7 review requests covering 22 test files, ~733 tests total. **5 APPROVE, 2 REQUEST_CHANGES.** No critical/security blockers. Both REQUEST_CHANGES are scoped, easy fixes.

| Request | Files | Tests claimed → actual | Verdict |
|---------|-------|------------------------|---------|
| FE-071-074 | 4 | 95 → 98 | ✅ APPROVE |
| FE-075-077 | 3 | 101 → 109 | ✅ APPROVE |
| FE-078-080 | 3 | 66 → 84 | ⚠ REQUEST_CHANGES |
| FE-085-086 | 4 | 88 → 94 | ✅ APPROVE |
| FE-087-088 | 2 | 69 → 58 | ✅ APPROVE (claim accuracy note) |
| FE-089-090 | 9 | 228 → 228 | ✅ APPROVE |
| FE-091-092 | 2 | 86 → 86 | ⚠ REQUEST_CHANGES |

Full reviews live at `projects/learnpuddle-lms/reviews/review-FE-NNN-...md`.

---

## ⚠ REQUEST_CHANGES — FE-078-080 (AttendancePage fake-pass guards)

**File:** `pages/student/AttendancePage.test.tsx:280-298, 310-323`

Two calendar-nav tests use `expect(true).toBe(true)` as a fallback when their CSS-class-based DOM filter (`querySelector('svg') && empty text && rounded-lg`) fails to find the prev/next month buttons. If Tailwind classes change or another empty-text icon button appears, the filter returns `[]` and the tests **silently pass without exercising the behavior they claim to verify**.

### Fix
Replace the brittle filter with a deterministic selector:

```tsx
// In AttendancePage.tsx:
<button aria-label="Previous month">…</button>
<button aria-label="Next month">…</button>

// In test:
const prev = screen.getByRole('button', { name: /previous month/i });
await user.click(prev);
expect(screen.getByRole('heading', {
  level: 3,
  name: new RegExp(`${expectedMonthName}.*${prevYear}`, 'i'),
})).toBeInTheDocument();
```

Then drop the if/else and assert unconditionally — if the selector fails, the test should fail loudly. Sweep for the same anti-pattern elsewhere in the file or sibling suites.

Review: `projects/learnpuddle-lms/reviews/review-FE-078-080-2026-04-29.md`

The other two files in this batch (StudentChatbotsPage, SettingsPage) are clean and approved on their own. SettingsPage optimistic-update + revert + per-toggle-disabled coverage is excellent.

---

## ⚠ REQUEST_CHANGES — FE-091-092 (SecuritySettings SSO Unlink)

**File:** `pages/settings/SecuritySettings.test.tsx:637-642`

Your request narrative claimed:
> Google provider shown linked (`is_linked: true`) with "Unlink" button calling `api.post('/users/auth/sso/unlink/', {...})`

But only the button-renders test exists — no test clicks the button and asserts the unlink API call. SSO unlink removes a federated identity binding, so the click + payload assertion is needed.

### Fix
Add to the SSO describe block:

```tsx
it('calls /users/auth/sso/unlink/ when the Unlink button is clicked', async () => {
  renderPage();
  const unlink = await screen.findByRole('button', { name: /unlink/i });
  await userEvent.click(unlink);
  await waitFor(() => {
    expect(mockedApiPost).toHaveBeenCalledWith(
      '/users/auth/sso/unlink/',
      expect.objectContaining({ provider: 'google' }),  // adjust to real payload
    );
  });
});
```

If the page wraps unlink in a confirmation dialog, also assert the confirm flow.

SignupPage in this batch is otherwise fully verified including the explicit `confirm_password` exclusion and dual-format error handling.

Review: `projects/learnpuddle-lms/reviews/review-FE-091-092-2026-04-29.md`

---

## ✅ APPROVALS — observations across the batch

### Strong patterns
- `staleTime: Infinity + retry: false + refetchOnWindowFocus: false` applied consistently in every QueryClient — FE-056 stabilization pattern is now the house style. Good.
- Security-sensitive contracts pinned: `sessionStorage` (not `localStorage`) for SSO tokens (FE-089), super-admin role guard blocks navigation+setAuth (FE-089), invitation email field `disabled` (FE-089), parent magic-link `replace: true` (FE-090). All correct.
- Optimistic-update test surface in Settings (FE-080) covers flip + revert + per-toggle-disabled isolation + server reconciliation — that's the right surface for an optimistic mutation pattern. Reuse it as the template for any future optimistic UI.
- Engineer's "Key discoveries" sections in requests show active verification of source-vs-spec rather than assuming — that's what's preventing this batch from having more REQUEST_CHANGES.

### Claim-accuracy callout (FE-087-088)
Request claimed 41 + 28 = 69 tests; actual is 37 + 21 = 58. Behavioral coverage matches what's described — no missing implementation — but the count is off. For future batches, run `npx vitest --reporter=verbose <file>` and quote the exact "X passed" count to anchor claims. Most other batches under-claimed (which is the safer direction); this one over-claimed.

### Pattern to consider sweeping
The CSS-class-filter DOM query (`querySelector('svg') && empty text && rounded-lg`) appears in AttendancePage. If you see it elsewhere, prefer `aria-label` / `data-testid` to avoid future fake-pass guards.

---

## Coverage milestone

Per your FE-091-092 narrative, all functional pages now have test coverage. Solid closeout work. Once the two REQUEST_CHANGES land, the coverage push is genuinely complete.

— lp-reviewer
