---
tags: [review, task/FE-TEST-SUITE-FIX, verdict/approve, reviewer/lp-reviewer, area/frontend, area/tests]
created: 2026-04-21
---

# Review: FE-TEST-SUITE-FIX — 43 failing tests green + FE-017/018 follow-ups

## Verdict: APPROVE

## Summary
Correctly diagnoses and fixes five distinct root causes across three
previously-untracked test files (`semanticSearch`, `aiCourseGenerator`,
`translation`) flagged in the FE-018 review's "Note on the full-suite run".
Also closes FE-017 m1/m2 cosmetic cleanups and FE-018 m3 TODO-marker request
from their respective approval notes. Verified statically — every claimed
fix is present in the tree with explanatory comments at the fix sites.

## Critical Issues
None.

## Major Issues
None.

## Minor Issues
None worth gating on. Two observations filed below for future work.

## Positive Observations

### Diagnosis quality

Each of the five bugs is analysed to root cause (not patched around), and
the fix addresses the cause:

1. **Nested Router crash** — the two custom helpers (`renderWithProviders` /
   `renderWithRouter`) previously composed `<MemoryRouter>` + `<QueryClient>`
   *and* delegated to `test-utils.tsx` `render()` which does the same.
   Fix simplifies each helper to `render(ui, { useMemoryRouter: true, … })`,
   pushing routing/provider responsibility into the canonical test utility.
   Verified at `semanticSearch.test.tsx:80–81`, `aiCourseGenerator.test.tsx:130–131`,
   `translation.test.tsx:156–160`.
2. **`vi.useFakeTimers()` starving React scheduler** — correctly identified
   that `MessageChannel` (React concurrent scheduler) and `setInterval`
   (RTL `waitFor` poll) must stay real. `toFake: ['setTimeout', 'clearTimeout']`
   is the minimal correct scope. Applied consistently in every `beforeEach`
   across all three files (10+ call sites, all match).
3. **`userEvent.click` with fake `setTimeout`** — subtle but real; `userEvent`
   v14 sequences pointer events through a zero-timer microtask. With
   `setTimeout` faked and never advanced, click never dispatches. Swap to
   `fireEvent.click` at the two affected tests is the correct minimal
   surgery — and the in-code comments at `semanticSearch.test.tsx:296-298`
   and `:440-442` explain *why* so no future reviewer reverts them.
4. **Ambiguous `getByText('Course Alpha')`** — the `<h2>` group header and the
   `SearchResultItem` title span both contain the same text. `getByRole(
   'heading', { level: 2, name: 'Course Alpha' })` (line 175) correctly
   disambiguates by semantic role. Same applied to `Course Beta` (line 176).
5. **Stale regex in AI generator test** — `/draft course.*not be deleted/i`
   at line 599 matches the current copy while still asserting the
   meaningful substring. Inline comment at line 597 documents the intent.

### FE-017 follow-ups landed cleanly

- `GradebookPage.test.tsx`:
  - Dead `mockColumn` function removed (confirmed absent via grep).
  - `fakeColumn` promoted to a module-level `function fakeColumn()` (line 29),
    matching the convention in `AssessmentGradebookPage.test.tsx`.
  - `renderCourseHeader` helper extracted (line 77) and used in both
    subtests (lines 84, 88).

### FE-018 m3 TODO markers landed

- `ChatPanel.tsx:274–275` and `AgentGenerationStep.tsx:327–328` both carry
  `// TODO(FE-018): migrate to <ConfirmDialog> — deferred because …` with
  a one-line rationale. Exactly what the FE-018 review asked for. The
  deferral is now self-documenting at the call site, not hidden in a
  separate tracker.

### Review-friendly discipline

- No behavioural changes to any production component. The only two
  production-source edits (`ChatPanel.tsx`, `AgentGenerationStep.tsx`) are
  comment-only.
- All five test-file edits are either infrastructure (helpers/timers) or
  assertion-targeting (role vs text, regex). Nothing papers over a
  legitimate bug in the component under test.
- Comments at the fix sites ensure the reasoning survives future grep-driven
  edits.

## Observations for future work (non-blocking)

### O1. The two `renderWith…` helpers now have identical bodies

After this patch, each file's helper is essentially `render(ui,
{ useMemoryRouter: true, … })`. A single shared helper in `test-utils.tsx`
(e.g. `renderInRouter`) would let future test authors stop rolling their own
— and would prevent this exact nested-router class of bug from recurring.
Not owed by this patch; flag for whoever owns the test-utils convention.

### O2. Green-suite claim not independently re-runnable from the sandbox

The note states 514/514 tests pass. I verified every named fix statically,
but the sandbox cannot execute `npx vitest run`. The author's claim +
static verification is sufficient for approval here because the changes are
tightly scoped and visible; recommend a CI run on the branch gates the
final merge.

## Verification Performed

| Claim | Check | Result |
|------|-------|--------|
| Nested Router fix in all 3 files | `grep -n "useMemoryRouter: true"` in each | ✅ one per helper, 3 total |
| `toFake` scoped to setTimeout/clearTimeout in all fake-timer sites | `grep -n "useFakeTimers"` across 3 files | ✅ every hit is `{ toFake: ['setTimeout', 'clearTimeout'] }` (10 sites) |
| `fireEvent.click` only where needed | `grep -n "fireEvent.click"` in semanticSearch | ✅ 2 sites, both with explanatory comments |
| Heading disambiguation | `grep -n "getByRole.*heading.*Course Alpha"` | ✅ line 175 |
| Regex update in AI gen test | `grep -n "not be deleted"` | ✅ `/draft course.*not be deleted/i` at line 599 |
| GradebookPage cleanup | `grep -n "mockColumn\|fakeColumn\|renderCourseHeader"` | ✅ `mockColumn` absent, others present as described |
| FE-018 m3 TODO markers | `grep -n "TODO(FE-018)"` in `components/maic/` | ✅ ChatPanel.tsx:274, AgentGenerationStep.tsx:327 |

## Recommendation

Approved. CI should run `npx vitest run` on this branch as the final
pre-merge gate to confirm the 514/514 claim. No follow-up owed.

— reviewer (lp-reviewer)
