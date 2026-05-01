---
from: frontend-engineer
to: reviewer (lp-reviewer)
date: 2026-04-22
subject: Review Request — Test Suite Stabilization (3 bug fixes)
---

# Review Request: Test Suite Stabilization

## Summary

Three test bugs fixed that were causing a flaky full suite (0–9 random failures
per run, all passing individually). Two consecutive `npx vitest run` runs now
show **61/61 files, 547/547 tests** — green and stable.

## Files Changed

| File | Change |
|------|--------|
| `frontend/src/components/common/Toast.test.tsx` | Timer scope fix + cleanup hook |
| `frontend/src/components/chatbot/ChatbotWidget.test.tsx` | Dual data-testid fix |
| `frontend/src/pages/admin/ai-course-generator/__tests__/aiCourseGenerator.test.tsx` | Missing import fix |

## Fix 1 — Timer pollution (Toast.test.tsx)

**Root cause:** `vi.useFakeTimers()` without `{ toFake: [...] }` scope fakes
`MessageChannel` and `Date`, which React 18's concurrent scheduler relies on.
When this test file ran before timer-sensitive tests in the same Vitest worker,
`waitFor` in later tests would hang or time out.

**Change:**
```ts
// Before (line 133):
vi.useFakeTimers();

// After:
vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
```

Also added `afterEach(() => vi.useRealTimers())` at the describe-block level
as a safety net — matches the pattern in `semanticSearch.test.tsx`,
`aiCourseGenerator.test.tsx`, `translation.test.tsx`, `useAiStudioWebSocket.test.ts`.

**Verification:** Before fix, `Toast.test.tsx` caused cascade failures in
`RubricPage`, `GamificationPage`, `ActivityHeatmap`, `LoginPage`, `MAIC`
integration tests, etc. After fix, all 61 test files are stable.

## Fix 2 — Duplicate data-testid (ChatbotWidget.test.tsx)

**Root cause:** `ChatbotMessage` renders `CitationChip` twice per citation:
once inline in the answer text and once in the Sources section at the bottom.
Both rendered the same `data-testid="citation-chip-unknown-N"`. The test
`screen.getByTestId(...)` threw "Found multiple elements."

**Change:**
```ts
// Before:
const chip = screen.getByTestId('citation-chip-unknown-0');
expect(chip.tagName).toBe('SPAN');

// After:
const chips = screen.getAllByTestId('citation-chip-unknown-0');
expect(chips.length).toBeGreaterThanOrEqual(1);
chips.forEach(chip => {
  expect(chip.tagName).toBe('SPAN');
  expect(chip.tagName).not.toBe('BUTTON');
});
```

**Note:** The component behavior (rendering chips in both locations) is
intentional — inline for in-text navigation and in Sources for source browsing.
The test now correctly validates both locations must be non-navigable spans.

## Fix 3 — Missing import (aiCourseGenerator.test.tsx)

**Root cause:** Tests for "TASK-062 L2: validateOutline content title 200-char
cap" used `validateOutline()` at lines 167/175 but never imported it.

**Change:**
```ts
// Before:
import { aiCourseGeneratorService, MAX_FILE_BYTES, TERMINAL_STATES } from '...';

// After:
import { aiCourseGeneratorService, MAX_FILE_BYTES, TERMINAL_STATES, validateOutline } from '...';
```

The function is exported from `aiCourseGeneratorService.ts:113` and the
`vi.mock` factory spreads `...actual` so the real implementation flows through.

## Test Results

```
npx vitest run  (run 1): Test Files 61/61 | Tests 547/547 ✓
npx vitest run  (run 2): Test Files 61/61 | Tests 547/547 ✓
```

No regressions. TASK-061 chatbot widget: 20/20. TypeScript: clean (tsc --noEmit).

## Scope

These are test-only fixes. No production component behavior was changed.
The `ChatbotMessage` component dual-render of citation chips is preserved.
