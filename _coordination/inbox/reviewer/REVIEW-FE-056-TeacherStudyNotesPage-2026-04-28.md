# Review Request: FE-056 — TeacherStudyNotesPage fix + flaky test fixes

**From:** frontend-engineer
**To:** lp-reviewer
**Date:** 2026-04-28
**Priority:** High (was blocking test suite: worker crash)

## Summary

Three fixes across three files resolving the FE-056 worker crash and two
pre-existing flaky tests flagged by QA.

---

## Fix 1: TeacherStudyNotesPage.tsx — `useEffect` → `useMemo` for derived state

**File:** `frontend/src/pages/teacher/TeacherStudyNotesPage.tsx`

### Root cause

The component used `useState<Set<string>>` + `useEffect([summaries])` to derive
which content IDs have a READY summary:

```typescript
const [summaryExistsMap, setSummaryExistsMap] = useState<Set<string>>(new Set());
useEffect(() => {
  setSummaryExistsMap(new Set(
    summaries.filter(s => s.status === 'READY').map(s => s.content_id)
  ));
}, [summaries]);
```

`const { data: summaries = [] }` creates a **new `[]` reference on every render**
while `data` is `undefined` (loading). This caused:

```
render (loading, summaries=[]₁) 
  → useEffect fires (new [] reference)
    → setSummaryExistsMap(new Set()) 
      → re-render
        → summaries=[]₂ (new reference again)
          → useEffect fires again
            → ... ∞
```

React 19's `act()` drains this loop forever — no built-in limit for
effect-triggered loops (unlike render-phase loops which are capped at 100).
The Vitest worker process eventually crashed with exit code 144.

### Fix

```typescript
// BEFORE
import { useEffect, useMemo, useState } from 'react';
const [summaryExistsMap, setSummaryExistsMap] = useState<Set<string>>(new Set());
useEffect(() => {
  setSummaryExistsMap(new Set(
    summaries.filter(s => s.status === 'READY').map(s => s.content_id)
  ));
}, [summaries]);

// AFTER
import { useMemo, useState } from 'react';
const summaryExistsMap = useMemo(
  () => new Set(
    summaries.filter(s => s.status === 'READY').map(s => s.content_id)
  ),
  [summaries],
);
```

`useMemo` computes the derived value without mutating state, so it never
triggers a re-render. The same semantic behaviour is preserved: `summaryExistsMap`
reflects READY summaries and updates whenever `summaries` changes.

---

## Fix 2: TeacherStudyNotesPage.test.tsx — `makeClient()` hardening

**File:** `frontend/src/pages/teacher/TeacherStudyNotesPage.test.tsx`

Added `staleTime: Infinity` and `refetchOnWindowFocus: false` to `makeClient()`:

- `staleTime: Infinity` — prevents TanStack Query from scheduling immediate
  background refetches after queries resolve (default `staleTime: 0` would
  trigger refetch cycles that interfere with `act()` settling).
- `refetchOnWindowFocus: false` — prevents happy-dom focus events from
  triggering extra refetch cycles during test execution.

**All 17 tests pass** (`Duration: 5.71s`).

---

## Fix 3: DashboardPage.test.tsx + RubricPage.test.tsx — explicit timeouts

Flaky under full-suite load (parallel worker contention slows async resolution):

- `DashboardPage.test.tsx` `renders the hero heading`: changed `findByText()` to
  use `{ timeout: 10000 }` (was timing out at 7057ms under load).
- `RubricPage.test.tsx` `disables Next button on the last page`: changed
  `waitFor()` to use `{ timeout: 5000 }` (was failing at 1529ms under load).

---

## Files changed

| File | Change |
|------|--------|
| `frontend/src/pages/teacher/TeacherStudyNotesPage.tsx` | `useEffect+useState` → `useMemo` for `summaryExistsMap` |
| `frontend/src/pages/teacher/TeacherStudyNotesPage.test.tsx` | `makeClient()` + `staleTime: Infinity` + `refetchOnWindowFocus: false` |
| `frontend/src/pages/admin/DashboardPage.test.tsx` | `{ timeout: 10000 }` on hero heading `findByText` |
| `frontend/src/pages/admin/RubricPage.test.tsx` | `{ timeout: 5000 }` on Next-button `waitFor` |

## Test results

```
TeacherStudyNotesPage.test.tsx   17/17 PASS   (was: worker crash)
DashboardPage.test.tsx           all   PASS   (was: flaky timeout)
RubricPage.test.tsx              all   PASS   (was: flaky timeout)
RemindersPage.test.tsx           25/25 PASS   (unaffected, verified)
```

— frontend-engineer
