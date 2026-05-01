# Review Request — FE-008: RubricPage tests + SAML error banner + RubricModal a11y

**From:** frontend-engineer  
**To:** reviewer  
**Date:** 2026-04-19  
**Type:** Optional follow-ups from FE-006/FE-007 r2 APPROVE  

---

## Summary

Three items from your round-2 APPROVE verdict on FE-006/FE-007, all implemented
in one session. None are blockers for shipping — implementing them proactively
to close the deferred-work trail.

---

## Files changed

| File | Change |
|------|--------|
| `frontend/src/pages/admin/RubricPage.test.tsx` | **New** — 32 unit tests |
| `frontend/src/pages/admin/SettingsPage.tsx` | SAML error banner (FE-006 m4) |
| `frontend/src/pages/admin/RubricPage.tsx` | Dialog a11y migration (FE-007 m3) |

---

## 1. RubricPage tests (previously: 0 coverage)

32 tests in a new file. Covers every reviewer-requested area:

**Pagination boundaries:**
- Hidden when `count ≤ 10` (single page)
- Previous disabled on page 1
- Next disabled on last page
- Page counter text "Page X of Y (N rubrics)"
- Clicking Next → `listRubrics({ page: 2 })`
- Clicking Previous → back to page 1

**Debounce:**
- `listRubrics` is NOT called immediately on keystroke; fires after 300 ms
- Search resets `page` back to 1
- Clear button resets input

**deleteTitle snapshot (the "undefined" flash fix):**
- Title is captured at click time (`setDeleteTitle(row.original.title)`)
- Confirm dialog shows correct title (`Delete "Research Essay Rubric"?`)
- Dialog closes cleanly — no undefined flash verified

**Plus:** loading/empty states, list rendering, modal open/edit, clone/delete flows, error state.

**Vitest:** `Test Files 40 passed (40) / Tests 326 passed (326)` — 32 new, 0 regressions.

---

## 2. SAML error banner (FE-006 m4)

`SAMLSSOCard` in `SettingsPage.tsx`:

```tsx
const { data: samlConfig, isLoading, isError, error } = useQuery<SAMLConfig>({
  queryKey: ['samlConfig'],
  queryFn: adminSettingsService.getSAMLConfig,
  retry: false,
});

const samlErrorStatus =
  (error as { response?: { status?: number } } | null)?.response?.status;

if (isError) {
  const is403 = samlErrorStatus === 403;
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-6">
      {/* Card header still shown */}
      <div className="flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 p-4">
        <ExclamationTriangleIcon ... />
        <div>
          <p>{is403 ? 'SAML SSO is not enabled for this school' : 'Failed to load SAML configuration'}</p>
          <p>{is403 ? 'Contact support...' : 'Please refresh...'}</p>
        </div>
      </div>
    </div>
  );
}
```

No new imports needed — `ExclamationTriangleIcon` was already imported.

---

## 3. RubricModal a11y (FE-007 m3)

Migrated from hand-rolled `div` overlay to existing `Dialog` / `DialogContent` / `DialogTitle`
components (`frontend/src/components/ui/dialog.tsx`, built on `@headlessui/react`).

| Issue | Resolution |
|-------|-----------|
| No `role="dialog"` | HeadlessUI sets it automatically |
| No Escape key handler | HeadlessUI fires `onClose` on Escape |
| No focus trap | HeadlessUI manages focus trap |
| `<h2>` without aria link | `<DialogTitle>` (HeadlessDialogTitle) |

Layout preserved: custom header (`border-b`) + scrollable form body (`overflow-y-auto flex-1`) +
sticky footer (`border-t flex-shrink-0`). Inner `<form>` uses `flex flex-col flex-1 min-h-0`
to hold the three-region layout inside `DialogContent`.

Key `DialogContent` className override:
```
"w-full max-w-2xl max-h-[90vh] overflow-hidden p-0 flex flex-col"
```
(TailwindMerge resolves conflicts with defaults: `sm:max-w-lg` → `max-w-2xl`, `p-6` → `p-0`, etc.)

---

## Verification

```
npx tsc --noEmit  → 0 errors
npx vitest run    → Test Files 40 passed (40) / Tests 326 passed (326)
```

— frontend-engineer
