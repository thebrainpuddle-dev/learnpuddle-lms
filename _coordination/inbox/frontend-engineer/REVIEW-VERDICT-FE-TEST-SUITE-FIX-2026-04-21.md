# Review verdict — FE test-suite fix (43 tests) + FE-017/018 cleanups

**From:** reviewer (lp-reviewer)
**To:** frontend-engineer
**Date:** 2026-04-21
**Request:** `FE-TEST-SUITE-FIX-2026-04-21.md`

---

## Verdict: APPROVED

All 5 bug-class fixes verified in the three test files. FE-017 m1/m2 cleanups in `GradebookPage.test.tsx` are present. FE-018 m3 TODO comments are present in both `ChatPanel.tsx` and `AgentGenerationStep.tsx`. No hidden production-behavior changes attributable to this task.

---

## Verification

### Bug fixes confirmed in the 3 test files

**`semanticSearch.test.tsx`**:
- `renderWithProviders` simplified to `render(ui, { useMemoryRouter: true })` (line 80–82).
- `vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })` applied in every `beforeEach` (lines 90, 128, 207, 260, 310, 353, 391, 454).
- `fireEvent.click` substitutions for userEvent + fake-timer interactions (lines 298, 442) with inline comments explaining the userEvent v14 `setTimeout(fn, 0)` pitfall — good defensive comment.
- `getByRole('heading', { level: 2, name: 'Course Alpha' })` heading query (lines 175–176) replacing ambiguous `getByText`.

**`aiCourseGenerator.test.tsx`**:
- `render(ui, { useMemoryRouter: true, initialRoute: initialPath })` (line 131).
- `toFake: ['setTimeout', 'clearTimeout']` at line 301.
- Stale regex replaced with `/draft course.*not be deleted/i` (line 599) — matches the actual copy "The draft course this job created will NOT be deleted."

**`translation.test.tsx`**:
- Same `useMemoryRouter` simplification (line 160).
- Two `toFake` fixes at lines 274 and 532.

All 5 bug classes you described are visible in the diffs as claimed.

### FE-017 m1/m2 cleanups in `GradebookPage.test.tsx`

- `fakeColumn()` promoted to module-level function (line 29).
- Dead `mockColumn()` is absent from the file (grep returned 0 hits) — confirms the "ugly conditional type, never called" helper was deleted.
- `renderCourseHeader` helper extracted (lines 77–88) and used for both education and corporate label tests — mirrors the `AssessmentGradebookPage.test.tsx` pattern as you stated.

### FE-018 m3 TODO comments

- `ChatPanel.tsx:274` — `// TODO(FE-018): migrate to <ConfirmDialog> — deferred because ChatPanel has a complex streaming state that needs careful dialog-open coordination.`
- `AgentGenerationStep.tsx:327` — analogous TODO comment.

Both TODOs live at the deferred `window.confirm` sites, as promised.

---

## One observation on scope isolation (non-blocking)

`ChatPanel.tsx` and `AgentGenerationStep.tsx` each show ~82–85 lines of diff in `git diff` — far more than a 2-line TODO addition would produce. I verified this is pre-existing MAIC sprint work (stage-interrupt plumbing in ChatPanel, AgentRevealModal + motion import in AgentGenerationStep) on the shared `maic-sprint-1-presence-rhythm` branch, NOT behavior changes introduced by this task. Your TODO lines are the only fingerprint of this task in those files. Flagging only so the coordinator understands the working-tree overlap: your claim "No behaviour changes to any production component" is true *for the work attributable to this task*, even though the files themselves carry unrelated edits.

Recommend future handoffs explicitly scope diffs to `git diff --stat -- <file>` ranges so concurrent-branch churn is not conflated with task work.

---

## Nice touches

- Inline comments in `semanticSearch.test.tsx` explaining the userEvent v14 + fake setTimeout interaction are educational for future contributors who might be tempted to "simplify" back to `userEvent.click`.
- The diagnosis of MessageChannel + setInterval being globally faked by `vi.useFakeTimers()` is spot-on — this is a classic Vitest/RTL gotcha and the `toFake: ['setTimeout', 'clearTimeout']` narrowing is the correct fix.
- Extracting `renderCourseHeader` genuinely reduces duplication in `GradebookPage.test.tsx`.

Full suite green at 514 / 514. Ship it.

— lp-reviewer
