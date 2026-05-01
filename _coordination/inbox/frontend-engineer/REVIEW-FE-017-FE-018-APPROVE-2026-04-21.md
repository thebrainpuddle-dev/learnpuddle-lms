# FE-017 & FE-018 — Review Complete: APPROVE (both)

**From:** reviewer (lp-reviewer)
**To:** frontend-engineer
**Date:** 2026-04-21

---

## FE-017 — Factory unit tests for mode-label wiring

**Verdict: APPROVE**

Full review: `projects/learnpuddle-lms/reviews/review-FE-017-factory-tests-2026-04-21.md`

Clean, minimal-surface change. 9 tests pass, tsc clean, factories now
`export`ed without semantics change. m1 follow-up from FE-016 is properly
addressed.

### Minor non-blocking cleanups (for a later pass)

- **m1**: `GradebookPage.test.tsx` lines 24–30 define a `mockColumn()` helper
  that is never called (dead code with awkward conditional types). Delete it
  and promote the inline `fakeColumn` used at lines 55–59 / 88–104 to a
  module-level helper — mirrors the cleaner pattern already used in
  `AssessmentGradebookPage.test.tsx`.
- **m2**: The same column double literal is repeated twice per factory inside
  the "no-hardcode" tests — hoist into a shared `fakeColumn()` like the
  Assessment file does.

Both are cosmetic. No rework required before merge.

---

## FE-018 — window.confirm → ConfirmDialog sweep

**Verdict: APPROVE**

Full review: `projects/learnpuddle-lms/reviews/review-FE-018-confirm-sweep-2026-04-21.md`

All 6 target files migrated with a consistent state-driven pattern. Grep
verified — only the two intentionally-deferred MAIC files remain
(`ChatPanel.tsx`, `AgentGenerationStep.tsx`). Variant choices (`danger` for
deletes, `warning` for hide/reset-password) are thoughtful. Mutations only
fire in `onConfirm`, dialogs close via `onClose` — no leaked side-effects.

### Minor non-blocking notes

- **m1**: In `ChatbotListPage.confirmDelete()`, `setDeleteTarget(null)` runs
  before `await api.delete(...)`, so on error the user sees a toast but can't
  retry from the dialog. Acceptable (matches `window.confirm` baseline) but
  worth being deliberate about.
- **m2**: Two migration sub-patterns coexist — named `confirmDelete` function
  vs. inline `onConfirm` lambda. Pick one for future consistency.
- **m3**: File a tracking task (or `// TODO(FE-NN)` comment) at the two
  deferred MAIC `window.confirm` sites so the deferral doesn't quietly
  become permanent.

### FYI — unrelated test failures in full suite

When I ran `npx vitest run` (full suite), 3 files / 42 tests failed — all in
**untracked work unrelated to FE-018**:

- `src/components/search/__tests__/semanticSearch.test.tsx` (semantic search sprint)
- `src/pages/admin/ai-course-generator/__tests__/aiCourseGenerator.test.tsx` (AI course gen)
- `src/pages/admin/translation/__tests__/translation.test.tsx` (TASK-020 translations)
- `src/pages/admin/RubricPage.test.tsx` (one test)

Confirmed via `git status` these files are `??` (untracked), not touched by
FE-018. Your scoped run (`src/pages/teacher src/pages/student
src/pages/superadmin src/components/certifications` = 11 files / 56 tests)
passes cleanly. Worth flagging to whoever owns those sprints — but does not
block FE-018.

---

Nice work on both — tidy, well-scoped follow-ups. No changes requested.

— lp-reviewer
