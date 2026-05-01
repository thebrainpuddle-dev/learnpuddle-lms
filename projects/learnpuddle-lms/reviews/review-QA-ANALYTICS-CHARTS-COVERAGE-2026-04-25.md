---
tags: [review, task/QA-analytics-charts, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-25
---

# Review: QA — Analytics Chart Tests + SCIM Spinner Strengthening

## Verdict: APPROVE

## Summary
Lands 38 tests for the three new analytics charts (DeadlineAdherence,
ApprovalTrends, CourseEffectiveness) introduced in FE-034 — closing what was
zero coverage on those components. Also strengthens the SCIM token loading
spinner assertion with a positive DOM check, addressing FE-032 M1. Suite goes
from 660 → 701 passing.

## Critical Issues
None.

## Major Issues
None.

## Minor Issues

- **Each describe block re-mocks every `adminReportsService` method.** Acceptable
  in isolation; if a fourth chart lands on this service, factor a `mockSvc()`
  helper before the file gets bigger.
- **Recharts is stubbed**, so visual correctness (axis ticks, stacking,
  responsiveness) is *not* covered here — that's expected and matches the
  approach used in `SkillRadarPage.test.tsx`. End-to-end visual coverage lives
  in Playwright, not vitest. No action.
- **Backend live run not executed** — sandbox lacks Docker. QA notes this
  explicitly and CI will be the first live invocation. Acknowledged; the
  backend analytics suite (`tests/reports/test_analytics_views.py`, 35 tests)
  was approved on 2026-04-24 and is gated by `--cov-fail-under=60` per the
  devops CI-gate confirmation also landing today.

## Positive Observations

- **Coverage of the FE-035 isError fix is direct and correct.** The
  ApprovalTrends describe block asserts both:
    - subtitle shows `"overall approval rate"` (no parens) on loading/error
    - subtitle shows `"overall approval rate (N total requests)"` on success
  That's the regression test the FE-035 fix needed. Tests would have failed
  before that fix and pass after — exactly what we want.
- **`document.querySelector('.animate-spin').toBeTruthy()`** strengthening on
  `SettingsPage.SCIMTokenCard.test.tsx:255` is precisely what I asked for in
  the FE-032 review. Comment in the source links back to the originating
  review note — easy to audit later.
- **Per-state coverage is symmetrical** across the three charts: loading /
  error / empty / data. The empty-state path (chart container absent,
  empty-message present) is the kind of thing teams forget — it's all here.
- **Click coverage on `View Details`** uses `userEvent.click` with the
  callback mock, *and* asserts the button is *not* rendered when the prop is
  omitted. Good negative test.

## Verification (claimed)

```
npx vitest run analyticsCharts.test.tsx             → 38/38 ✓
npx vitest run SettingsPage.SCIMTokenCard.test.tsx  → 24/24 ✓
npx vitest run                                      → 701/701 ✓
```

Spot-checked describe / it count in `analyticsCharts.test.tsx`: 13 + 15 + 10 =
38. Matches the request. Cleared to merge.

— lp-reviewer
