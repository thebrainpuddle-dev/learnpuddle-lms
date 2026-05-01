---
tags: [review, task/FE-018, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-21
---

# Review: FE-018 — window.confirm Sweep (TASK-012 Follow-up)

## Verdict: APPROVE

## Summary

The six remaining `window.confirm` sites called out as non-blocking follow-ups
in TASK-012 have been migrated to `ConfirmDialog` with a consistent pattern.
Verified grep shows only the two intentionally-deferred MAIC sites remain
(`ChatPanel.tsx`, `AgentGenerationStep.tsx`), matching the documented scope.
Tests in the affected paths all pass.

## Critical Issues

None.

## Major Issues

None.

## Minor Issues

### m1 — Post-delete state nulling before error handling (non-blocking)

In `ChatbotListPage.tsx` (lines 93–103) and a couple of other handlers, the
pattern is:

```tsx
async function confirmDelete() {
  if (!deleteTarget) return;
  const id = deleteTarget;
  setDeleteTarget(null);        // clears state BEFORE the network call
  try {
    await chatbotApi.delete(id);
    removeChatbot(id);
  } catch (err) {
    toast.error('Delete failed', ...);
  }
}
```

Clearing `deleteTarget` before the await means the dialog closes immediately
on confirm, so on error the user sees only a toast — they can't retry from
within the dialog. That's an acceptable UX choice (matches `window.confirm`
baseline which also dismissed on confirm), but worth being deliberate about.
Not blocking — current behaviour is a strict improvement over `window.confirm`.

### m2 — Two patterns coexist across the migrated files (non-blocking)

Some files use a named `confirmDelete` async function (e.g. `ChatbotListPage`)
while others inline the confirm action in the dialog's `onConfirm` prop
(e.g. `SchoolAccreditationsTab`, `teacher/DiscussionThreadPage`). Both are
correct, but picking one convention would make future sweeps mechanical.
Non-blocking.

### m3 — `ChatPanel.tsx` / `AgentGenerationStep.tsx` deferral is documented
but should get a tracking task

The review request notes these two are intentionally deferred to a
MAIC-focused sprint. Fine — but the engineering-log should carry a ticket
(or at minimum, a `// TODO(FE-NN)` comment at each remaining `window.confirm`
site) so the deferral doesn't quietly become permanent. Non-blocking for this
PR; call out for planning.

## Positive Observations

- **Consistent migration pattern.** Each file uses the same state-driven
  approach (`deleteTarget: string | null` or a boolean flag for single-target
  actions like `SchoolDetailPage`'s password reset). Easy to scan.
- **Variant choice is thoughtful** — `danger` for deletes, `warning` for hide
  reply / reset password. Matches the actual consequence severity.
- **Verbatim grep guard matches the claim.** `grep -rn "window.confirm" src/`
  yields exactly the two intentionally-deferred MAIC files — no sneaky
  regressions reintroduced.
- **No side-effects leaked.** Confirmed by reading handlers that nothing
  runs until the user confirms (e.g. `deleteMilestoneMutation.mutate(id)` is
  only invoked inside `onConfirm`, not on dialog open).

## Verification Performed

- `grep -rn "window.confirm" frontend/src/ | grep -v test | grep -v .md` → only
  2 remaining hits in MAIC, matching the deferral list ✅
- `grep -n "ConfirmDialog"` across all 6 target files → import + mount present
  in every file ✅
- Read + spot-check of migrations in `ChatbotListPage.tsx`,
  `teacher/DiscussionThreadPage.tsx`, `SchoolAccreditationsTab.tsx`,
  `SchoolDetailPage.tsx` — pattern is correct; mutations only fire in
  `onConfirm`; dialog close wired on `onClose` ✅
- `npx vitest run src/pages/teacher src/pages/student src/pages/superadmin src/components/certifications`
  → 11 files / 56 tests passing ✅

### Note on the full-suite run

`npx vitest run` (full suite) shows 3 test files / 42 tests failing, but all
failures are in **unrelated untracked work** — `translation/__tests__/`,
`ai-course-generator/__tests__/`, `components/search/__tests__/`,
`RubricPage.test.tsx`. These are new test files from TASK-020 / AI course gen
/ semantic search sprints that are not on this branch's FE-018 change set. I
verified `git status` shows these as `??` (untracked, from other work), not
modified by FE-018. FE-018's changes do not introduce any regressions; the
failures are pre-existing issues in adjacent sprints and should be addressed
separately (worth flagging to the author team responsible for those files).

— lp-reviewer
