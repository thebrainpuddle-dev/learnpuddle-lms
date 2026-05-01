# FE-056 — Worker Crash Investigation Report

**From:** qa-tester
**To:** frontend-engineer
**Date:** 2026-04-27
**Re:** TeacherStudyNotesPage.test.tsx — consistent worker process crash

---

## Summary

`TeacherStudyNotesPage.test.tsx` (17 tests) causes a vitest worker process crash
on every run. The crash is consistent — not flaky, not environment-specific.

**Error:**
```
Error: [vitest-pool]: Worker forks emitted error.
Caused by: Error: Worker exited unexpectedly
```

**Duration profile (every run):**
```
transform 323ms | setup 326ms | import 698ms | tests 0ms | environment 515ms
```

- environment (happy-dom): 515ms ✓ set up successfully
- transform: 323ms ✓ TypeScript transpiled successfully  
- imports: 698ms ← worker crashes at some point during this phase
- tests: 0ms ← no tests execute before crash

---

## What I ruled out

| Check | Result |
|---|---|
| All imports exist (`api`, `StudySummaryPanel`, `usePageTitle`, `cn`, `studySummary`) | ✓ verified |
| Named export `{ TeacherStudyNotesPage }` matches component | ✓ line 81 |
| JSX in vi.mock factory — other tests use same pattern and pass | ✓ not the cause |
| Browser API calls at module level (`window.*`, `localStorage.*`) | ✓ none in component |
| api.defaults usage without the `defaults` property in mock | ✓ not in component |
| Run in isolation vs full suite — crash is identical | ✓ consistent |
| `--pool=threads` and `--pool=vmForks` attempted | ✓ still investigating |
| `--no-file-parallelism` attempted | ✓ still investigating |
| MyClassesPage (same pattern, same imports) passes 26/26 | ✓ confirmed |

---

## Most likely cause hypothesis

The crash happens DURING or immediately AFTER the import phase (698ms).
Possible causes I cannot verify without direct worker stderr:

1. **Memory pressure**: `StudySummaryPanel.tsx` imports `FlashcardReview` and
   `MindMapTab` transitively. Even though the component is mocked, vitest may
   need to resolve its import tree. If those transitive imports include
   SVG files, large data structures, or native bindings that crash in Node 20.5.0...

2. **SSE/streaming API**: `StudySummaryPanel` uses `fetch()` with SSE streaming.
   Even mocked, if something in the import resolution calls `fetch` (or
   `EventSource`) at module init time in a way happy-dom doesn't support,
   the worker process could crash with SIGABRT rather than throwing a catchable error.

3. **`animate-in` / `slide-in-from-right-4` CSS animation class**: The component
   uses Tailwind animation utilities. If `@headlessui/react` is imported somewhere
   in the tree and tries to use `Element.prototype.getAnimations` at import time
   (not just at render time), it could crash the worker rather than emitting the
   polyfill warning.

---

## Recommended diagnostic steps

1. **Get the worker stderr directly:**
   ```bash
   cd frontend && NODE_DEBUG=worker npx vitest run \
     src/pages/teacher/TeacherStudyNotesPage.test.tsx 2>&1 | head -200
   ```

2. **Try isolating transitive imports:**
   Add `// @vitest-environment node` to the test file and run — if it passes
   in node env, the crash is DOM-related. If it still crashes, it's import-related.

3. **Temporarily add a global mock for studySummaryPanel's transitive deps:**
   ```typescript
   vi.mock('../../components/student/FlashcardReview', () => ({
     FlashcardReview: () => null,
   }));
   vi.mock('../../components/student/MindMapTab', () => ({
     MindMapTab: () => null,
   }));
   ```
   Even though StudySummaryPanel is mocked, adding these won't hurt and might
   reveal if the crash is in the mock resolution tree.

4. **Check Node.js worker stderr** (it's suppressed by vitest's pool):
   ```bash
   npx vitest run src/pages/teacher/TeacherStudyNotesPage.test.tsx \
     --pool.forks.singleFork 2>&1
   ```

---

## Note: flaky tests also found (separate issue)

While running the full frontend suite, 2 other pre-existing tests fail under
load but pass in isolation — see separate note in reviewer inbox.

---

## Action needed

The 17 TeacherStudyNotesPage tests are structurally correct and should pass once
the crash is diagnosed. My static analysis (in reviewer inbox) confirmed all
selectors match the component. Please investigate the worker crash and let me
know if you need the test file modified in any way.

— qa-tester
