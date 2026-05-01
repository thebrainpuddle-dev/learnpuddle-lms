---
reviewer: lp-reviewer
date: 2026-04-22
subject: Review — Test Suite Stabilization (3 bug fixes)
verdict: APPROVED
scope: test-only
---

# Review Note

## Verification (static; vitest sandbox-blocked)

### Fix 1 — `frontend/src/components/common/Toast.test.tsx`
- Line 144: `vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })` — present.
- Lines 31–33: top-level `afterEach(() => { vi.useRealTimers(); })` safety-net cleanup — present.
- Per-test `vi.useRealTimers()` also still at line 162.
- Explanatory comment (lines 140–143) documents the MessageChannel/Date rationale. Good.

### Fix 2 — `frontend/src/components/chatbot/ChatbotWidget.test.tsx`
- Line 602: `screen.getAllByTestId('citation-chip-unknown-0')` — correct plural form.
- Lines 603–610: asserts `chips.length >= 1`, iterates each chip, asserts `tagName === 'SPAN'` and not `BUTTON`/`A`. Dual-render (inline + Sources) is correctly accommodated.
- Line 613: still asserts no `role="link"` exists. Sound.

### Fix 3 — `frontend/src/pages/admin/ai-course-generator/__tests__/aiCourseGenerator.test.tsx`
- Line 76 import: `{ aiCourseGeneratorService, MAX_FILE_BYTES, TERMINAL_STATES, validateOutline }` — `validateOutline` present.
- Usages at lines 168, 176 now bind correctly.

## Scope check
- `git diff --stat` for the three paths shows only `Toast.test.tsx` modified in working tree (12 ins / 1 del). Fixes 2 and 3 are already aligned in-tree (no diff vs HEAD), so no further changes needed.
- No non-`.test.` production source files were touched as part of this task. (Unrelated ambient changes on `maic-sprint-1-presence-rhythm` branch are out of scope for this review.)
- `ChatbotMessage` component dual-render behavior preserved — test now validates rather than masks it. Correct approach.

## Risk
- Low. All three are test-file-only.
- CI will be the first live run since local vitest is sandbox-blocked.

## Recommendations
- None blocking. Consider a follow-up lint rule or shared helper to forbid bare `vi.useFakeTimers()` at module scope to prevent regression of Fix 1.

## Verdict: APPROVED
