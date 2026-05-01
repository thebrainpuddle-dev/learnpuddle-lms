---
tags: [review, task/FE-022, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-23
---

# Review: FE-022 — Migrate deferred MAIC `window.confirm` → ConfirmDialog

## Verdict: APPROVE

## Summary
Clean, focused resolution of the two TODO(FE-018) sites in the MAIC surface.
Both migrations follow the established state-driven `ConfirmDialog` pattern
from the FE-018 sweep, the side-effects are sequenced correctly, and the
replacement tests are behavior-oriented. Production has **zero** remaining
`window.confirm` call sites (verified independently — only occurrence is a
test title string).

## Critical Issues
None.

## Major Issues
None.

## Minor Issues
- `ChatPanel` still has no dedicated test file — the `handleClearChat` →
  dialog → wipe flow relies on the neighbour `ChatbotChat.test.tsx` for
  indirect coverage. The author correctly flags this as pre-existing debt
  outside FE-022's scope; agreed, but worth tracking as a follow-up since
  the dialog branch is now production-critical.

## Positive Observations
- **Correct separation of handlers** in `ChatPanel.tsx`: `handleClearChat`
  only opens the dialog, and `handleClearConfirmed` performs the destructive
  work (abort + wipe in-memory + wipe sessionStorage + wipe IndexedDB).
  `abortRef.current?.abort()` now fires **only** when the user confirms —
  previously the pre-PR code already had that bug avoided, and this PR
  preserves it cleanly rather than regressing it.
- **Dialog messaging is user-facing and specific**: the message includes the
  live `chatMessages.length` count, which matches the original `window.confirm`
  string and gives the user enough information to decide.
- **`variant="warning"` justification is sound** (amber vs. red/danger):
  both actions are recoverable in spirit (chat can be recreated; agents can
  be regenerated). Consistent with how FE-018 classified "hide / reset" flows.
- **Test replacement is strictly stronger** than what it replaces:
  - Old test: spied on `window.confirm` — verifies nothing about UX.
  - New tests (2): (a) dialog actually opens with correct title + buttons;
    (b) Cancel keeps state intact AND `generateAgentProfiles` remains at
    one call (the initial mount load). That second assertion is the right
    invariant — it catches a subtle regression where a dialog's cancel path
    still fires the destructive action.
- **`grid` + `within(grid)` scoping in the tests** correctly avoids the
  double-match trap now that `AgentRevealModal` also renders the agent names.
- TypeScript compiles clean (`tsc --noEmit`); file-scoped vitest run shows
  6/6.

## Files Touched (verified in working tree)
- `frontend/src/components/maic/ChatPanel.tsx` — dialog state + split
  handlers + `<ConfirmDialog>` at JSX tail. ✓
- `frontend/src/components/maic/AgentGenerationStep.tsx` — `confirmRegenOpen`
  state, `handleRegenerateAll` is now a pure dialog opener, `<ConfirmDialog>`
  placed before `editing && <AgentEditModal …>`. ✓
- `frontend/src/components/maic/__tests__/AgentGenerationStep.test.tsx` —
  stale spy test replaced with two behavior tests (lines 119-146, 148-174). ✓

## Next Steps
- Update `status/review` → `status/done` on the FE-022 task.
- Consider a follow-up task to add a focused `ChatPanel.test.tsx` covering
  the clear-chat confirm path end-to-end.

— lp-reviewer
