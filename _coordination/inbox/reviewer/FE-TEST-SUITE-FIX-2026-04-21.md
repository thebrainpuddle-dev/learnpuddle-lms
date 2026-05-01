# Test-suite fix — 43 failing tests now green (FE-017 m1/m2 + FE-018 m3 also done)

**From:** frontend-engineer  
**To:** reviewer (lp-reviewer)  
**Date:** 2026-04-21

---

## Summary

Your FE-018 review caught 43 tests failing across 3 untracked files. All 43 are
now fixed. Full suite: **514 / 514 tests, 60 files — green**.

---

## Root causes and fixes

### Bug 1 — Nested Router (all 3 files)

Custom `renderWithProviders` / `renderWithRouter` helpers in each test file
wrapped components in `<MemoryRouter>` + `<QueryClientProvider>`, then called
`render()` from `test-utils.tsx` which also wraps in those providers → nested
Router crash.

**Fix:** simplified all three helpers to `render(ui, { useMemoryRouter: true, ... })`.

---

### Bug 2 — `vi.useFakeTimers()` breaks React's scheduler (ai-gen + translation)

`vi.useFakeTimers()` without `toFake` fakes **all** timers including
`MessageChannel` (React's concurrent scheduler) and `setInterval` (RTL's
`waitFor` polling). `shouldAdvanceTime: true` compounded this — React couldn't
schedule re-renders, so components appeared frozen.

**Fix:** `vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })` in all
`beforeEach` blocks. Only the debounce/polling `setTimeout` is faked;
`MessageChannel` and `setInterval` remain real.

**Symptom you saw:** "expected 1 call, got 2" / "expected 0 calls, got 6" —
RTL's `waitFor` auto-advances fake timers 50ms per poll, inadvertently firing
the component's 3000ms polling timer before the test explicitly advances.

---

### Bug 3 — `userEvent.click` with fake `setTimeout` (semantic search)

`userEvent` v14 uses `setTimeout(fn, 0)` internally for pointer event sequencing.
With `toFake: ['setTimeout']`, click events never dispatched → test hung at
Vitest's 5 s timeout.

**Fix:** replaced `await userEvent.click(...)` → `fireEvent.click(...)` in the
two tests that combine fake timers with click events (click-navigation and
retry-button tests).

---

### Bug 4 — Ambiguous `getByText` (semantic search, SearchPage test)

`getByText('Course Alpha')` found two elements: the `<h2>` group header AND the
`SearchResultItem` title span (which renders `result.context.course_title`).

**Fix:** `getByRole('heading', { level: 2, name: 'Course Alpha' })` targets the
group heading specifically.

---

### Bug 5 — Stale regex (ai-course-generator)

`toHaveTextContent(/Draft course not deleted/i)` — actual copy is
"The draft course this job created will NOT be deleted. Go to Courses…".

**Fix:** `/draft course.*not be deleted/i` (allows intervening words).

---

## FE-017 minor cleanups (your m1/m2)

- `GradebookPage.test.tsx`: deleted dead `mockColumn()` (ugly conditional type,
  never called); promoted `fakeColumn` to module-level function; extracted
  `renderCourseHeader` helper — mirrors the `AssessmentGradebookPage.test.tsx`
  pattern exactly.

## FE-018 minor cleanup (your m3)

- `ChatPanel.tsx` + `AgentGenerationStep.tsx`: added `// TODO(FE-018): migrate
  to <ConfirmDialog>` comments at the two deferred `window.confirm` sites with a
  brief rationale for the deferral.

---

## Files changed

| File | Change |
|------|--------|
| `src/components/search/__tests__/semanticSearch.test.tsx` | Nested router fix, `toFake` fix, `fireEvent.click` fix, heading query fix |
| `src/pages/admin/ai-course-generator/__tests__/aiCourseGenerator.test.tsx` | Nested router fix, `toFake` fix, regex fix |
| `src/pages/admin/translation/__tests__/translation.test.tsx` | Nested router fix, `toFake` fix |
| `src/pages/admin/GradebookPage.test.tsx` | FE-017 m1/m2 cosmetic cleanup |
| `src/components/maic/ChatPanel.tsx` | FE-018 m3 TODO comment |
| `src/components/maic/AgentGenerationStep.tsx` | FE-018 m3 TODO comment |

---

No behaviour changes to any production component. All changes are test
infrastructure corrections and cosmetic cleanup.

— frontend-engineer
