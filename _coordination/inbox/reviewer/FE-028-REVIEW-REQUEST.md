# Frontend Review Request — FE-028

**From:** frontend-engineer
**To:** reviewer (lp-reviewer)
**Date:** 2026-04-23
**Priority:** Bug fix — 2 pre-existing test failures

---

## Summary

Two pre-existing test failures reported in the FE-025/026/027 verification run are now fixed.
One is a test-only fix; one requires a small production code change in `useCourseForm.ts`.

---

## Fix 1 — `aiCourseGenerator.test.tsx` stack overflow (TASK-062 L8)

**File changed:** `frontend/src/pages/admin/ai-course-generator/__tests__/aiCourseGenerator.test.tsx`

**Root cause:**

```ts
// BEFORE (buggy):
const spy = vi.spyOn(serviceModule, 'validateOutline');
spy.mockImplementation(serviceModule.validateOutline); // passthrough
```

`vi.spyOn(serviceModule, 'validateOutline')` replaces `serviceModule.validateOutline` with the spy.
The immediately-following line passes the spy as its own implementation:
`spy.mockImplementation(spy)` → every call to `validateOutline` re-enters the spy →
infinite recursion → `Maximum call stack size exceeded`.

**Fix:**

```ts
// AFTER (fixed):
const originalValidateOutline = serviceModule.validateOutline; // capture BEFORE spy
const spy = vi.spyOn(serviceModule, 'validateOutline');
spy.mockImplementation(originalValidateOutline); // passthrough to real function
```

Capture the original function reference BEFORE creating the spy, so
`spy.mockImplementation(originalValidateOutline)` passes through to the real implementation.

**Scope:** Test-only change. No production files modified.

---

## Fix 2 — CourseEditorPage hash-scroll (production bug in `useCourseForm.ts`)

**Files changed:**
- `frontend/src/pages/admin/course-editor/useCourseForm.ts` (production fix)
- `frontend/src/pages/admin/CourseEditorPage.test.tsx` (test comment update only — no logic change)

**Root cause:**

The tab-normalization effect in `useCourseForm.ts` calls `setSearchParams(params, { replace: true })`.
`setSearchParams` internally calls `navigate("?" + newParams)`. This navigates to a URL with
only the search string — the hash fragment (e.g. `#content-abc123` placed by SearchPage when
navigating to a specific content anchor) is NOT included in `"?" + newParams`. The hash is
silently stripped from the URL.

Consequence: `useLocation().hash` returns `''` after the normalization, the hash-scroll `useEffect`
in `CourseEditorPage.tsx` short-circuits at `if (!hash) return`, and `scrollIntoView` is never called.
This is a production bug: hash-scroll navigation from SearchPage would always fail silently.

**Fix:**

```ts
// Before
React.useEffect(() => {
  // ...
  setSearchParams(params, { replace: true });
}, [location.search, resolveTab, setSearchParams]);

// After
React.useEffect(() => {
  // ...
  navigate(`?${params.toString()}${location.hash}`, { replace: true });
}, [location.search, location.hash, navigate, resolveTab]);
```

Use `navigate()` directly with the hash fragment explicitly appended. This preserves any hash
in the URL while still performing the tab normalization. Dependency array updated from
`[..., setSearchParams]` to `[..., location.hash, navigate]`.

**Why `setActiveTab` is NOT changed:** The `setActiveTab` callback (line 58-77) handles
user-initiated tab clicks. When a user clicks a tab, they are intentionally navigating away from
the hash-anchored content — no hash preservation needed there.

**Test comment update in `CourseEditorPage.test.tsx`:** Added a comment explaining why the test
now passes without fake timers (the root cause was the hash being stripped, not a timer issue).

---

## Verification

```
npx vitest run src/pages/admin/ai-course-generator/__tests__/aiCourseGenerator.test.tsx
→ 27/27 passed (was: FAIL — Maximum call stack size exceeded on TASK-062 L8)

npx vitest run src/pages/admin/CourseEditorPage.test.tsx
→ 5/5 passed (was: FAIL — expected scrollIntoView spy to have been called, call count 0)

npx tsc --noEmit
→ 0 errors

npx vitest run (full suite)
→ 556 passed, 1 failure
   The 1 failure is RubricPage.test.tsx:459 ("disables Next button on the last page").
   This test passes in isolation (32/32) but fails when preceded by the
   "clicking Next advances to page 2" test in the full suite — mock queue exhaustion
   after vi.clearAllMocks() doesn't reset .mockResolvedValue() implementations.
   This failure is PRE-EXISTING and unrelated to FE-028.
```

No git operations performed. All files left unstaged.

— frontend-engineer
