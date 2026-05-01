# Review Request — FE-035: Follow-up fixes (FE-031/032/033/034 non-blocking items)

**From:** frontend-engineer
**To:** reviewer
**Date:** 2026-04-25

## Summary

Implements all non-blocking follow-up suggestions from the four most recent review
verdicts (FE-031 through FE-034). Six targeted changes across five files.

---

## Changes

### 1. DeadlineAdherenceChart.tsx — Show `—` on error (`isError`)

**File:** `frontend/src/components/analytics/DeadlineAdherenceChart.tsx`  
**Origin:** FE-034 M1

The headline stat was showing `0%` when `isError` was true. Fixed to show `—`
(matching the `isLoading` path):

```diff
- {isLoading ? '—' : `${latest?.adherencePercent ?? 0}%`}
+ {isLoading || isError ? '—' : `${latest?.adherencePercent ?? 0}%`}
```

---

### 2. ApprovalTrendsChart.tsx — Show `—` on error in both stat and subtitle

**File:** `frontend/src/components/analytics/ApprovalTrendsChart.tsx`  
**Origin:** FE-034 M1

Same fix, plus the subtitle text also now guards on `isError` (was showing
"overall approval rate (0 total requests)" when error):

```diff
- {isLoading ? '—' : `${approvalRate}%`}
+ {isLoading || isError ? '—' : `${approvalRate}%`}

- {isLoading ? 'overall approval rate' : `overall approval rate (${totalAll} total requests)`}
+ {isLoading || isError ? 'overall approval rate' : `overall approval rate (${totalAll} total requests)`}
```

---

### 3. QuestionBankPage.tsx — Render Zod choices array-level error

**File:** `frontend/src/pages/admin/QuestionBankPage.tsx`  
**Origin:** FE-033 M2

Added `choices.root.message` rendering after the choices list. RHF v7 stores
FieldArray-level Zod errors (from `superRefine` with `path: ['choices']`) at
`errors.choices.root`, not `errors.choices.message`. Added `role="alert"` for
accessibility:

```tsx
{form.formState.errors.choices?.root?.message && (
  <p className="mt-1.5 text-xs text-red-500" role="alert">
    {form.formState.errors.choices.root.message}
  </p>
)}
```

---

### 4. QuestionBankPage.test.tsx — waitFor + alert assertion

**File:** `frontend/src/pages/admin/QuestionBankPage.test.tsx`  
**Origin:** FE-033 M1 + M2

- Replaced `await new Promise(r => setTimeout(r, 100))` with `await waitFor(...)`
  (no more magic-number sleep).
- Updated the test to also assert the Zod `choices` error message is visible in
  the dialog DOM before asserting service was not called:

```diff
- // Give RHF time to run validation.
- await new Promise((r) => setTimeout(r, 100));
- expect(svc.createQuestion).not.toHaveBeenCalled();
+ // Zod superRefine fires → choices error rendered in the dialog and service not called.
+ await waitFor(() => {
+   expect(
+     within(screen.getByRole('dialog')).getByRole('alert'),
+   ).toHaveTextContent(/mcq requires exactly 1 correct choice/i);
+ });
+ expect(svc.createQuestion).not.toHaveBeenCalled();
```

Test name updated from "does not call createQuestion" →
"shows choices validation error and does not call createQuestion".

---

### 5. SettingsPage.tsx — Clipboard error catch

**File:** `frontend/src/pages/admin/SettingsPage.tsx` (`TokenRevealModal.handleCopy`)  
**Origin:** FE-032 M2

Added `.catch` to `navigator.clipboard.writeText`:

```diff
  navigator.clipboard
    .writeText(tokenValue)
    .then(() => {
      setCopied(true);
      toast.success(...);
    })
+   .catch(() => {
+     toast.error('Copy failed', 'Clipboard access was denied — please select and copy the token manually.');
+   });
```

---

### 6. SettingsPage.tsx — Double-click guard in createMutation.onSuccess

**File:** `frontend/src/pages/admin/SettingsPage.tsx` (`SCIMTokenCard.createMutation`)  
**Origin:** FE-032 M1

Added `if (revealToken) return` to prevent rapid double-submit overwriting the
first token's plaintext before the admin copies it:

```diff
  onSuccess: (created) => {
+   if (revealToken) return;
    queryClient.invalidateQueries({ queryKey: ['scim-tokens'] });
    form.reset();
    setShowCreateForm(false);
    setRevealToken(created.token);
  },
```

---

---

### 7. ActivityHeatmap.test.tsx — Pin date to fix Saturday flake (bonus fix)

**File:** `frontend/src/components/analytics/ActivityHeatmap.test.tsx`

The "renders future dates with just the date string as aria-label" test was failing
on Saturdays. Root cause: `endOfWeek(today, { weekStartsOn: 0 }) === today` on
Saturdays, leaving zero future cells in the heatmap grid.

Fix: pin "today" to Wednesday 2026-04-22 with scoped fake timers so Thu/Fri/Sat
are always future dates, regardless of the real system clock:

```tsx
vi.useFakeTimers({ toFake: ['Date'] });
vi.setSystemTime(new Date('2026-04-22')); // Wednesday
try {
  // ... render and assertions ...
} finally {
  vi.useRealTimers(); // restore so CloneTemplateDialog tests (next in suite) aren't affected
}
```

The missing `useRealTimers()` was also responsible for making two
`CloneTemplateDialog` validation tests flaky in the full suite run (timer state leaked
into userEvent timing). Both now pass consistently.

---

## Verification

```
npx tsc --noEmit → 0 errors (exit 0)
npx vitest run   → 660/660 passed (all 3 pre-existing failures resolved)
                   QuestionBankPage.test.tsx:  29/29 ✓ (choices alert assertion)
                   ActivityHeatmap.test.tsx:   22/22 ✓ (date-pinned)
                   CloneTemplateDialog.test.tsx: 4/4 ✓ (timer leak fixed)
```

— frontend-engineer
