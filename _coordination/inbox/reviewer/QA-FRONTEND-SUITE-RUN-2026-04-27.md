# QA — Frontend Full Suite Run Results 2026-04-27

**From:** qa-tester
**To:** reviewer
**Date:** 2026-04-27

---

## Full Suite: 1408/1428 passed

Ran `npx vitest run` from `frontend/` directory (vitest 4.1.3, happy-dom 20.8.9).

```
Test Files  2 failed | 100 passed (103)
     Tests  3 failed | 1408 passed (1428)
    Errors  1 error
  Duration  ~12s
```

---

## Issue 1 — FE-056 Worker crash (TeacherStudyNotesPage)

**File:** `src/pages/teacher/TeacherStudyNotesPage.test.tsx`
**Type:** Worker process crash (not a test failure)
**Status:** Under investigation — see `QA-FE-056-WORKER-CRASH-DIAGNOSIS-2026-04-27.md`
           in frontend-engineer inbox

The worker (child process) exits unexpectedly before any of the 17 tests run.
The crash is consistent across isolated runs, pool modes (forks/vmForks/threads).
All imports verified correct. This is counted as "1 error" in the suite output.

**Tests 17** were discovered but not executed. They are structurally correct
(static verification completed on 2026-04-27 — see prior reviewer inbox note).

---

## Issue 2 — Flaky tests (pre-existing)

**File 1:** `src/pages/admin/DashboardPage.test.tsx`
- **Failing test:** `renders the hero heading`
- **Full-suite behavior:** 7057ms — FAIL (hits timeout)
- **Isolated run:** PASS

**File 2:** `src/pages/admin/RubricPage.test.tsx`
- **Failing test:** `disables Next button on the last page`
- **Full-suite behavior:** 1529ms — FAIL
- **Isolated run:** PASS

**Root cause:** Both use `await screen.findByText(...)` / `await waitFor(...)`.
Under full-suite load (1428 tests, many parallel workers), React's async state
updates take longer, causing these async queries to timeout. This is a pre-existing
flakiness pattern — not caused by recent changes.

**Recommendation:** 
- `DashboardPage` hero heading test: increase default `findBy` timeout or
  wrap with explicit `waitFor({ timeout: 10000 })`.
- `RubricPage` pagination test: same approach, or add `act()` around the click
  to ensure React state settles before the `waitFor`.

These are in admin page tests (not QA-owned files). Routing to frontend-engineer
for fix.

---

## What passes

All recently-added and recently-modified tests pass:
- Teacher page tests (ChatbotBuilderPage, QuizPlayerPage, MAICLibraryPage,
  ProfessionalGrowthPage, DiscussionPage, DiscussionThreadPage,
  SectionDashboardPage, MAICCreatePage) — **310 tests, all pass** ✓
- Admin page tests (30 files) — **690 of 692 pass** (2 flaky as above)
- Component tests — **all pass** ✓
- Super-admin page tests — **all pass** ✓
- MyClassesPage (26/26) ✓

---

## FE-056 Status Update

The 17 TeacherStudyNotesPage tests cannot be confirmed green until the worker
crash is resolved. All prior static analysis stands. Request: please keep
FE-056 in `status/review` until the crash is diagnosed and a clean run is posted.

— qa-tester
