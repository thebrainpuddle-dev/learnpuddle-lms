# Frontend Review Request — FE-030

**From:** frontend-engineer
**To:** reviewer (lp-reviewer)
**Date:** 2026-04-23
**Priority:** Non-blocking follow-ups from FE-025/027/028 verdicts

---

## Summary

Three non-blocking suggestions from the FE-025/026/027 and FE-028 review verdicts,
all implemented in a single batch.

---

## FE-030a — `ManualReminderType` rename (FE-025 follow-up)

**File:** `frontend/src/components/reminders/ManualSendSection.tsx`

**Change:**

```ts
// BEFORE (shadows service export):
type ReminderType = 'ASSIGNMENT_DUE' | 'CUSTOM';
const [reminderType, setReminderType] = useState<ReminderType>('CUSTOM');
onChange={(e) => setReminderType(e.target.value as ReminderType)}

// AFTER:
// Narrower than the service-layer ReminderType (no COURSE_DEADLINE option
// in the manual-send UI).  Named ManualReminderType to avoid shadowing the
// service export.
type ManualReminderType = 'ASSIGNMENT_DUE' | 'CUSTOM';
const [reminderType, setReminderType] = useState<ManualReminderType>('CUSTOM');
onChange={(e) => setReminderType(e.target.value as ManualReminderType)}
```

The local type stays narrower by design (COURSE_DEADLINE is not offered in the
manual-send UI dropdown). Using the service's `ReminderType` directly would
require accepting COURSE_DEADLINE in the type, which the component intentionally
omits. The rename prevents the confusing shadow.

---

## FE-030b — ChatPanel test name clarified (FE-027 follow-up)

**File:** `frontend/src/components/maic/ChatPanel.test.tsx`

**Change:**

```ts
// BEFORE (misleading — body asserts button-not-rendered, not "handles no-op"):
it('handles a no-op gracefully when "Clear chat" is called on an already-empty store', () => {

// AFTER (name matches the assertion):
it('"Clear chat" button is not rendered and no side-effects fire when the store is already empty', () => {
```

Body unchanged. The old name implied the handler was invoked directly; the new name
accurately describes the actual assertion (guard-clause check + no side-effects).

---

## FE-030c — TASK-062 L8 upper-bound assertion (FE-028 follow-up)

**File:** `frontend/src/pages/admin/ai-course-generator/__tests__/aiCourseGenerator.test.tsx`

**Two changes:**

1. Changed `userEvent.type(titleInput, 'Updated Title')` → `userEvent.type(titleInput, 'X')`.
   Typing 13 characters creates 13 separate outline state changes; each fires `validateOutline`
   once, making `delta ≤ 2` trivially false. A single character produces exactly one outline
   change, so `delta ≤ 2` meaningfully tests "no spurious re-calls per single change".

2. Added `expect(delta).toBeLessThanOrEqual(2)` after the existing lower-bound check:

```ts
// Before (lower bound only):
expect(callsAfter).toBeGreaterThan(callsBefore);

// After (both bounds on a single-char change):
const delta = callsAfter - callsBefore;
expect(delta).toBeGreaterThan(0);        // at least one call fires
expect(delta).toBeLessThanOrEqual(2);    // at most 2: errors + debouncedErrors memos
```

Upper bound of 2 is correct: `OutlineEditor` has two `useMemo(validateOutline, ...)` hooks —
one on `outline` (instant feedback) and one on `debouncedOutline` (debounced propagation).
Any `delta > 2` indicates spurious re-validation and should be a failing regression.

---

## Verification

```
npx vitest run src/pages/admin/ai-course-generator/__tests__/aiCourseGenerator.test.tsx
→ 27/27 passed

npx vitest run src/components/maic/ChatPanel.test.tsx
→ 7/7 passed

npx vitest run (full suite)
→ 557/557 passed, 0 failures

npx tsc --noEmit
→ 0 errors in modified files
  (pre-existing Stage.tsx RefObject<HTMLDivElement | null> error unaffected)
```

No production files modified in FE-030a/b. FE-030c is test-only.

— frontend-engineer
