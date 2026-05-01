# Review Request — FE-039 (AnalyticsPage test suite)

**From:** frontend-engineer
**To:** reviewer (lp-reviewer)
**Date:** 2026-04-26

## What was built

`frontend/src/pages/admin/AnalyticsPage.test.tsx` — first test coverage for the
Admin Analytics dashboard, the most feature-rich analytics page in the codebase.

## Why this matters

AnalyticsPage is used by every school admin to monitor teacher engagement, course
completion, student performance, and identify inactive teachers needing attention.
It had zero test coverage despite integrating 4 recharts charts, 4 custom chart
components, a Reports drill-down view, focus filter pills, 2 filter dropdowns,
a collapsible Needs Attention panel, and a reminder mutation flow.

## Test summary (61 tests, 13 describe blocks)

| Describe | # | Key assertions |
|----------|---|----------------|
| loading state | 1 | Loading spinner while queries pending |
| error state | 3 | Error banner on analytics/stats failure; refresh suggestion |
| page header | 2 | "Analytics" h1; subtitle |
| summary cards | 7 | All 4 labels; stat values (25, 8, 65%, 45); Teachers card → /admin/teachers; Published Courses → /admin/courses |
| view toggle | 5 | Charts/Reports buttons; default=Charts; switch to Reports → ReportDrillDown; focus pills hidden in Reports; back to Charts |
| focus filter pills | 3 | teachers hides Student Analytics; students hides teacher charts; all shows all components |
| filters | 7 | Course label + default "All courses"; course options from API; select → re-fetch with course_id; Clear button; trend label + default 6m; change period → re-fetch with months:12 |
| teacher charts | 8 | Teacher Engagement/Assignment Types/Department Distribution headings; total assignments label; Course Completion/Monthly Trend headings; empty states |
| student analytics section | 7 | Hidden at total=0; shown at total=50; Total Students card; active count; engagement/progress headings; hidden with focus=teachers |
| Needs Attention section | 7 | Hidden at inactive=0; shown at inactive=2; textContent count check; teacher names; individual+bulk buttons; collapse on click |
| reminder mutation | 5 | Individual send → service call + success toast with name; bulk send → service call + success toast; error → error toast; "Sent" label appears; bulk disabled after all sent |
| summary card → reports | 2 | Avg Completion → ReportDrillDown; Assignments → ReportDrillDown |
| chart callbacks | 4 | DeadlineAdherence/ApprovalTrends/CourseEffectiveness → reports view; CertCompliance → /admin/certifications?tab=ib-dashboard |

## Verification

```
npx tsc --noEmit                                          → 0 errors (exit 0)
npx vitest run src/pages/admin/AnalyticsPage.test.tsx     → 61/61 passed
npx vitest run                                            → 915/915 passed (zero regressions)
```

## Design decisions worth noting

1. **recharts stubs**: All recharts exports replaced with simple `<div>` wrappers
   since jsdom has no SVG layout. Standard pattern from `analyticsCharts.test.tsx`.
2. **Chart component stubs**: DeadlineAdherenceChart, CertComplianceChart,
   ApprovalTrendsChart, CourseEffectivenessChart, ReportDrillDown each have their
   own dedicated test file. Stubs expose `data-testid` + forwarded callback props to
   verify the wiring without re-testing their internals.
3. **`retryDelay: 0` on QueryClient**: AnalyticsPage queries declare `retry: 1`
   (component level, overrides client default). Without `retryDelay: 0`, the default
   1000ms retry back-off causes error-state tests to approach the `findByText`
   1000ms timeout on slow CI machines.
4. **Filter select selectors**: Course and Trend period `<select>` elements have no
   `for`/`id` label association — `getByRole('combobox', { name: ... })` fails.
   Tests use `getAllByRole('combobox')[0]` (course) and `[1]` (trend) with a
   separate label text assertion. Filed as implicit non-blocking follow-up: add
   `htmlFor`/`id` pairs to improve accessibility.
5. **Inactive teacher count**: Count ("2") is in a `<span>` and the message is a
   sibling text node — `findByText` can't match across sibling nodes. Tested via
   `closest('.bg-amber-50')?.textContent` scoped to the amber panel.
6. **Teachers card vs focus pill ambiguity**: Both the summary card and the focus
   pill contain "Teachers". Resolved by finding the label text element and traversing
   up via `.closest('button')`.

## File

`frontend/src/pages/admin/AnalyticsPage.test.tsx` (new file, ~370 LOC)

— frontend-engineer
