# Frontend Review Request — FE-029

**From:** frontend-engineer
**To:** reviewer (lp-reviewer)
**Date:** 2026-04-23
**Priority:** Test fix — pre-existing flaky test now deterministically passing

---

## Summary

The `RubricPage.test.tsx` flaky failure that was documented in the FE-028 review request
("556 passed, 1 failure... pre-existing and unrelated to FE-028") is now fixed.
One line changed: `vi.clearAllMocks()` → `vi.resetAllMocks()` in the `beforeEach`.

---

## Root Cause

`vi.clearAllMocks()` only resets invocation stats (`mock.calls`, `mock.results`, etc.) — it does
**not** clear `.mockResolvedValue()` implementations or `.mockResolvedValueOnce()` queues.

The test "clicking Next advances to page 2 and queries with page=2" (line 429) sets:
```ts
vi.mocked(adminRubricService.listRubrics).mockResolvedValue(
  makeListResponse(mockRubrics, { count: 25 }),
);
```

After that test ends, `vi.clearAllMocks()` runs but leaves the `count=25` implementation
active. `setupDefaultMocks()` then calls `mockResolvedValue(makeListResponse())` — which does
reset the default to `count=2` — but the NEXT test in source order is "disables Next button on
the last page" (line 446). Under Vitest's test isolation, residual async state (pending React
Query microtasks) from the "clicking Next" test can consume the `mockResolvedValueOnce(count=12)`
queue entry before the component's own initial-render API call fires. This causes the component
to load with `count=25`→`totalPages=3`, leaving the Next button enabled on page 2 when it should
be disabled.

---

## Fix

**File changed:** `frontend/src/pages/admin/RubricPage.test.tsx` (line 218 only)

```ts
// BEFORE:
beforeEach(() => {
  vi.clearAllMocks();
  setupDefaultMocks();
});

// AFTER:
beforeEach(() => {
  // resetAllMocks() (not clearAllMocks) wipes all implementations and queues
  // so setupDefaultMocks() starts from a genuinely clean slate.
  vi.resetAllMocks();
  setupDefaultMocks();
});
```

`vi.resetAllMocks()` calls `.mockReset()` on every mock, which clears:
- Call-history (same as `clearAllMocks`)
- `mockResolvedValue` / `mockReturnValue` implementations
- `mockResolvedValueOnce` / `mockReturnValueOnce` queues

`setupDefaultMocks()` immediately re-establishes all needed implementations, so no test loses
its mock coverage.

**Scope:** Test-only change. No production files modified.

---

## Verification

```
npx vitest run src/pages/admin/RubricPage.test.tsx
→ 32/32 passed (was: 32/32 in isolation, 31/32 in full suite run — flaky)

npx vitest run (full suite)
→ 557/557 passed, 0 failures
   (FE-028 left it at 556 passed, 1 flaky failure; FE-029 brings it to 557/557)

npx tsc --noEmit
→ 0 errors
```

---

## Relationship to Previous PRs

- FE-028 explicitly noted this failure as "PRE-EXISTING and unrelated to FE-028"
- FE-029 is the minimal follow-up that closes that gap
- No changes to any files touched by FE-025, FE-026, FE-027, or FE-028

— frontend-engineer
