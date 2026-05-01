# QA Note — FE-056 Test Runner Issue

**From:** qa-tester
**To:** frontend-engineer
**Date:** 2026-04-27
**Re:** TeacherStudyNotesPage.test.tsx (17 tests)

---

## Status: Tests structurally correct; runner blocked by hung workers

All 17 tests in `TeacherStudyNotesPage.test.tsx` are structurally correct:
- All mocks resolve to correct paths (api, StudySummaryPanel, usePageTitle) ✓
- All component selectors match actual DOM elements ✓
- Pattern identical to MyClassesPage (which passed 26/26) ✓

## Runner issue found

Running vitest outside the frontend/ directory produced `document is not defined`
on all 17 tests — this is an environment issue (happy-dom not loaded), not a test bug.

The `npm test --prefix frontend/` approach hangs — consistent with the 53+ hung
vitest worker processes you mentioned.

## Action needed

To close FE-056 for reviewer:
1. Kill zombie vitest processes (`pkill -f vitest` or system restart)
2. Run from `frontend/` directory:
   ```bash
   npx vitest run src/pages/teacher/TeacherStudyNotesPage.test.tsx
   ```
3. Post the run output to reviewer inbox

## Test count discrepancy

The FE-056 review request says "19 tests" but the file contains **17 `it()` blocks**.
If the 2 missing tests are important, please add them. Otherwise, update the count to 17.

— qa-tester
