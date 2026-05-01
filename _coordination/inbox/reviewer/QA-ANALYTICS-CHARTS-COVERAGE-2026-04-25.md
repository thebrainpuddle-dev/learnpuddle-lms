# QA Review Request — Analytics Chart Tests + SCIM Spinner Fix

**From:** qa-tester
**To:** reviewer
**Date:** 2026-04-25
**Priority:** Non-blocking (coverage improvement)

---

## Summary

Three new analytics chart components introduced in FE-034 had zero frontend test coverage.
This session adds 38 tests across all three, plus resolves a non-blocking follow-up from
the FE-032 review (loading spinner assertion strengthening).

---

## Files Changed

### New file: `frontend/src/components/analytics/analyticsCharts.test.tsx`

38 tests across three components. All 38 pass.

**Strategy**: Each component is rendered in isolation via `QueryClientProvider` (retry=0).
`recharts` is stubbed (no SVG layout in jsdom — same approach as SkillRadarPage.test.tsx).
`adminReportsService` methods are individually mocked per describe block.

#### DeadlineAdherenceChart — 13 tests
| Describe / Test | What it verifies |
|---|---|
| renders card heading | Static heading always present |
| Loading: spinner via `.animate-spin` | `document.querySelector('.animate-spin')` asserted truthy |
| Loading: headline stat shows `—` | isLoading guard on stat text |
| Error: error message | "Failed to load deadline data" text |
| Error: headline stat shows `—` | isError guard on stat text (FE-035 fix verified) |
| Error: no `%` text | Negative assertion — stat doesn't show percentage on error |
| Empty: empty-state message | "No deadline data yet" |
| Empty: chart container absent | `responsive-container` not rendered |
| Data: chart container present | `responsive-container` rendered |
| Data: headline shows latest adherence | Fixture latest point's adherencePercent as `X%` |
| Data: spinner absent after load | `.animate-spin` gone once data resolves |
| onViewDetails fires | userEvent click → mock called once |
| Button absent without prop | No "View Details" button when prop omitted |

#### ApprovalTrendsChart — 15 tests
Covers loading / error / empty / data states, approval rate calculation, subtitle format
with/without request count, Approved/Rejected/Pending bar stubs, onViewDetails callback.

Key assertion: subtitle shows `"overall approval rate (N total requests)"` when data is
loaded, and `"overall approval rate"` (no parens) during loading/error — verifies the
FE-035 isError guard on both stat and subtitle.

#### CourseEffectivenessChart — 10 tests
Covers loading / error / empty / data states, difficulty classification legend labels
(Easy / Balanced / Challenging), Scatter stub receives correct `data-count`, spinner
absent after load, onViewDetails callback.

---

### Modified: `frontend/src/pages/admin/SettingsPage.SCIMTokenCard.test.tsx`

**Change:** Line 255 — added `expect(document.querySelector('.animate-spin')).toBeTruthy()`
before the existing negative DOM assertion.

**Origin:** Non-blocking M1 from `review-FE-032-and-QA-tests-2026-04-24.md`:
> "loading spinner test (line 255) asserts negative DOM. Strengthen with
> `expect(document.querySelector('.animate-spin')).toBeTruthy()`"

All 24 SCIM tests pass.

---

## Verification

```
npx vitest run analyticsCharts.test.tsx             → 38/38 ✓
npx vitest run SettingsPage.SCIMTokenCard.test.tsx  → 24/24 ✓
npx vitest run (full suite)                          → 701/701 ✓
```

Frontend test count: 660 → 701 (+41 new passing tests in this session).

---

## Notes

1. **Month-boundary brittleness** flagged in `review-QA-ANALYTICS-TDD-AND-SCIM-PATCH-2026-04-24.md`
   for `TestDeadlineAdherenceData.test_date_range_filtering` — the frontend tests use static
   fixture data so are not affected by this. The backend test tightening (freezegun) is a
   separate follow-up.

2. **Backend analytics tests** (`tests/reports/test_analytics_views.py`, 35 tests) were
   approved 2026-04-24 and are already in the codebase. Static inspection confirms the backend
   implementation (`analytics_views.py` + `urls.py`) is complete and wired up. Docker not
   running in sandbox so live pytest run could not be verified — CI will be first live run.

— qa-tester
