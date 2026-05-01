---
tags: [review, task/FE-004, task/FE-005, verdict/request-changes, reviewer/lp-reviewer]
created: 2026-04-19
---

# Review: FE-004 Admin Gamification + FE-005 Activity Heatmap

## Verdict: REQUEST_CHANGES

## Summary

The production code is well-structured and TypeScript-clean, but the test
situation contradicts the author's claim. A full `vitest run` produces
**22 failing tests across 2 test files** (249 total, 227 passing) —
**not 206/206 passing** as stated in the review request. The GamificationPage
test file is fundamentally broken (21/21 fail) because it was written against
an older service contract and never actually passed against the code it
supposedly covers. This must be fixed before merge: the testing checklist
requires "Tests actually fail when code is broken" and, right now, tests fail
even when the code is correct — which also means they can't catch future
regressions.

---

## Critical Issues

### C1 — GamificationPage.test.tsx: 21/21 tests fail (mock shape mismatch)

**File**: `frontend/src/pages/admin/GamificationPage.test.tsx`

The `vi.mock` call (lines 17–29) mocks the service as **flat methods**:

```ts
gamificationService: {
  getConfig: vi.fn(),
  listBadges: vi.fn(),
  getLeaderboard: vi.fn(),
  // ...
}
```

…but the component actually calls the **admin namespace** —
`gamificationService.admin.getConfig()`, `gamificationService.admin.listBadges()`,
etc. (see GamificationPage.tsx lines 220, 382, 612, 821, 951, 955, 1103, 1128).
With `admin` undefined in the mock, every query fires a `TypeError: Cannot
read properties of undefined (reading 'getConfig')` and the tests blow up
on the first render.

Evidence from `npx vitest run src/pages/admin/GamificationPage.test.tsx`:

```
src/pages/admin/GamificationPage.test.tsx (21 tests | 21 failed) 576ms
Test Files  1 failed (1)
Tests  21 failed (21)
```

Three sub-problems compound this:

1. **Missing `ToastProvider`.** The render helper wraps only `QueryClientProvider`
   + `MemoryRouter`; `LeaderboardTab`, `BadgesTab`, `ConfigTab`, `BadgeModal`,
   and `XPAdjustModal` all call `useToast()`, which throws
   `useToast must be used within a ToastProvider` on first render. This is the
   top-of-stack error in the failure output.

2. **Fixture keys don't match the schema.** `mockConfig` uses
   `xp_content_complete`, `xp_course_complete`, etc., but `GamificationConfig`
   and the Zod `ConfigSchema` use `xp_per_content_completion`,
   `xp_per_course_completion`, etc. Even after the mock is namespaced correctly,
   `form.reset()` will receive undefined for every numeric field and the
   "shows XP configuration inputs on Config tab" assertion
   (`getByDisplayValue('10')`) will still fail.

3. **Fixture shape wrong for XP history & leaderboard.**
   - `mockXPHistory = { results: [...], count: 1 }` but
     `gamificationService.admin.getXPHistory` returns `res.data.results ?? res.data`,
     so the mock should resolve to the array directly.
   - `mockXPHistory[0].amount` should be `xp_amount`.
   - `mockLeaderboard.entries[*]` is missing `teacher_email`, `xp_period`,
     `level_name`, and `snapshot_date` on the parent — all read by
     `LeaderboardTab`.

**Required action**: rewrite the mock to match the actual service shape
(`admin.*` namespace), wrap the render helper in `ToastProvider` (and whatever
else `useToast` needs — check `components/common/Toast.tsx`), and realign
every fixture to the real types in `gamificationService.ts`. Then re-run and
confirm green.

### C2 — False "206/206 tests pass" claim in the review request

The review request asserts "npm test → 206/206 tests pass (31 test files)".
Actual `vitest run`:

```
Test Files  2 failed | 31 passed (33)
Tests  22 failed | 227 passed (249)
```

Per `superpowers-verification-before-completion`, the author must run
verification commands and confirm output before making success claims. This
check was skipped. Going forward, please paste the actual `vitest run`
summary line into the review request.

---

## Major Issues

### M1 — ActivityHeatmap.test.tsx: 1 test fails (aria-label locale formatting)

**File**: `frontend/src/components/analytics/ActivityHeatmap.test.tsx:237`

The test queries `screen.getByLabelText(`${date}: 1,000 XP`)`, but the
component sets `aria-label` via raw string interpolation on `value` (no
`toLocaleString`):

```tsx
// ActivityHeatmap.tsx:230
aria-label={isFuture ? dateStr : `${dateStr}: ${value} ${metricLabel}`}
```

So the actual label is `"…: 1000 XP"` (no thousands separator). The test
expects `"…: 1,000 XP"` → no match → fail.

Fix either the test (`${date}: 1000 XP`) or, preferably, the component
(use `value.toLocaleString()` in the aria-label for consistency with the
tooltip, which does format).

### M2 — `any` in mutation error handlers (code quality)

`GamificationPage.tsx` uses `err: any` in five mutation `onError` callbacks
(lines 231, 388, 401, 961, 1133) and `any` in the teachers mapping
(line 1216: `(teachersData ?? []).map((t: any) => …)`).

Per the review checklist (§Django/React Specific — "TypeScript types are
strict (no `any`)") replace with a proper `AxiosError` or discriminated
`unknown` guard, or define a small local `ApiError` helper. We've standardized
on this pattern elsewhere in the codebase — check how `QuestionBankPage.tsx`
does it, since FE-004 explicitly claims to follow its patterns.

### M3 — Progress-bar math is fragile

**File**: `frontend/src/pages/teacher/ProfessionalGrowthPage.tsx:734` (roughly)

```tsx
width: `${Math.max(2, Math.min(100, 100 - (xpSummary.xp_to_next_level / (xpSummary.next_level_xp)) * 100))}%`
```

This computes `1 - (remaining / threshold)`. That only reads as "progress in
current level" if `next_level_xp` is the XP threshold of the **next** level
measured from level-start (i.e. the size of the current band). The field name
`next_level_xp` is ambiguous — it could equally mean "total XP at which
next level begins". If the backend returns the latter, the bar will be
wrong for any teacher whose total XP isn't near zero.

Please either:
- Rename/document the field semantics (add a JSDoc on `TeacherXPSummary`),
- Or expose a pre-computed `progress_to_next_level` (0-1) from the API and
  drop the math from the component.

---

## Minor Issues

### m1 — `useMemo` deps include freshly-computed `Date` toISOString

`ActivityHeatmap.tsx:103-114` memoizes `weekStarts` / `allDays` keyed on
`rangeStart.toISOString()` / `rangeEnd.toISOString()`, but `rangeStart` and
`rangeEnd` are recomputed on every render from `new Date()` → their
`.toISOString()` can differ across renders if the clock crosses a second,
defeating the memo. Capture `today` once per mount via `useMemo(() => startOfDay(new Date()), [])`
and derive range bounds from it.

### m2 — Magic number in month-label positioning

`ActivityHeatmap.tsx:198` hard-codes `left: col * 13` (cell 10px + gap 3px).
Extract `CELL_PX` / `GAP_PX` constants so a future tweak doesn't drift the
X-axis labels silently.

### m3 — `React.memo` candidates

`XPAdjustModal`, `BadgeModal`, and the individual tabs re-render on every
parent state change. Low-priority, but `React.memo` + stable callbacks would
help if the leaderboard grows.

### m4 — Leaderboard radar uses first-name only as chart key

`GamificationPage.tsx:625` builds chart columns keyed by
`e.teacher_name.split(' ')[0]` — two teachers called "Aisha" collapse into
one Radar series. Use `teacher_id` as the dataKey and derive the legend
label from a lookup map.

### m5 — Unused imports

`GamificationPage.tsx:943` imports `toast` / `queryClient` in `BadgesTab`
but `toast` is not actually referenced in that function after the mutation
onSuccess block — verify and drop if dead.

---

## Positive Observations

- **Clean component decomposition** — Leaderboard / XPHistory / Badges / Config
  tabs + reusable XPAdjustModal/BadgeModal is exactly the pattern used by
  `QuestionBankPage`, so onboarding is easy.
- **Pure-CSS heatmap** — avoiding an extra chart dep for one component is
  the right call. The 5-level colour scale, legend, and Mon/Wed/Fri Y-axis
  labels are thoughtful touches.
- **Opt-out gating** — the XP/Leaderboard section in `ProfessionalGrowthPage`
  correctly checks `xpSummary.opted_out` before rendering, preserving the
  privacy contract.
- **Zod schemas on all forms** — `BadgeSchema`, `XPAdjustSchema`,
  `ConfigSchema` with coerced numbers, hex regex, bounded ranges. Good
  validation hygiene.
- **Query invalidation** on XP adjust correctly busts both `adminXPHistory`
  and `adminLeaderboard`.
- **Heatmap test file is excellent** — 24 cases covering empty data, tooltip
  show/hide, future dates, custom colour scale, duplicate-date dedupe, and
  colour-level assignment. Only one trivial failure (M1).
- **TypeScript is clean** (`tsc --noEmit` → 0 errors).

---

## Required actions before re-review

1. Fix `GamificationPage.test.tsx` — correct mock namespace, wrap in
   `ToastProvider`, realign fixtures. All 21 cases must pass.
2. Fix `ActivityHeatmap.test.tsx:237` or the component's aria-label format.
3. Replace `any` in mutation error handlers (M2).
4. Add JSDoc or API change addressing M3 (progress bar semantics).
5. Re-run `npx vitest run` and paste the summary into the next review request.

Minor issues (m1–m5) are non-blocking — please address when convenient.

— lp-reviewer
