# Review Request — FE-034: Wire Analytics Charts to Real Backend APIs

**From:** frontend-engineer
**To:** reviewer
**Date:** 2026-04-24

---

## Summary

Three analytics chart components were shipping hardcoded `MOCK_DATA` arrays with
`// TODO: Replace with useQuery` comments. FE-034 removes all mock data and wires
each chart to a live API endpoint, adding appropriate loading, error, and empty states.

---

## Files changed

### 1. `frontend/src/services/adminReportsService.ts`

Added 4 new TypeScript interfaces and 3 new service methods at the bottom of the file:

**New interfaces:**
```typescript
DeadlineAdherencePoint  { period, adherencePercent, totalTeachers, onTime, late }
ApprovalTrendsPoint     { period, approved, rejected, pending }
CourseEffectivenessItem { courseId, courseName, completionRate, avgScore, enrolledCount }
AnalyticsPeriodParams   { start?, end? }  // shared query-params type
```

**New methods:**
```typescript
adminReportsService.deadlineAdherence(params?)  → GET /reports/analytics/deadline-adherence/
adminReportsService.approvalTrends(params?)     → GET /reports/analytics/approval-trends/
adminReportsService.courseEffectiveness()       → GET /reports/analytics/course-effectiveness/
```

`deadlineAdherence` and `approvalTrends` accept optional `start`/`end` ISO date strings
(passed as query params); `courseEffectiveness` takes no params. Keys default to no-param
call — date-range filtering can be wired later without a service change.

---

### 2. `frontend/src/components/analytics/DeadlineAdherenceChart.tsx`

- **Removed**: `MOCK_DATA` constant and local `DeadlineDataPoint` interface
- **Added**: `import { useQuery }` + `import { adminReportsService, type DeadlineAdherencePoint }`
- **Query**: `useQuery(['deadlineAdherence'], adminReportsService.deadlineAdherence, { staleTime: 5min })`
- **Loading state**: emerald spinner (matches chart's `#10b981` stroke colour)
- **Error state**: red "Failed to load deadline data" message
- **Empty state**: "No deadline data yet" (existing — now also reachable from real empty API response)
- **Stat**: shows `—` during loading (was always `0%` with mock data)

---

### 3. `frontend/src/components/analytics/ApprovalTrendsChart.tsx`

- **Removed**: `MOCK_DATA` constant and local `ApprovalDataPoint` interface
- **Added**: `import { useQuery }` + `import { adminReportsService, type ApprovalTrendsPoint }`
- **Query**: `useQuery(['approvalTrends'], adminReportsService.approvalTrends, { staleTime: 5min })`
- **Loading state**: amber spinner (matches `CheckBadgeIcon text-amber-600`)
- **Error state**: red "Failed to load skip request data" message
- **Summary stat**: shows `—` during loading; "overall approval rate" text drops `(N total requests)` while loading to avoid "0 total requests" flash

---

### 4. `frontend/src/components/analytics/CourseEffectivenessChart.tsx`

- **Removed**: `MOCK_DATA` constant and local `CourseEffectivenessItem` interface (now imported from service)
- **Added**: `import { useQuery }` + `import { adminReportsService, type CourseEffectivenessItem }`
- **Query**: `useQuery(['courseEffectiveness'], adminReportsService.courseEffectiveness, { staleTime: 5min })`
- **Loading state**: purple spinner (matches `AcademicCapIcon text-purple-600`)
- **Error state**: red "Failed to load course data" message
- **`CustomTooltip`**: updated to type `payload[0].payload` as `CourseEffectivenessItem & { x, y, z }` (was `any`)

---

## Design decisions

| Decision | Rationale |
|----------|-----------|
| `staleTime: 5 * 60 * 1000` | Matches `CertComplianceChart` precedent. Analytics charts don't need sub-minute freshness. |
| `rawData ?? []` fallback | `useQuery` returns `data: T \| undefined` until first fetch. `?? []` means `data` is always `DeadlineAdherencePoint[]` — no conditional guards needed downstream. |
| `isError` state | Previously the mock never failed. Now that data comes from real API, network/parse errors need a visible signal rather than a broken chart. |
| Spinner colour per chart | Emerald/amber/purple mirrors each chart's icon colour — emerald for Deadline (ClockIcon), amber for Skip Requests (CheckBadgeIcon), purple for Course Effectiveness (AcademicCapIcon). Matches the spinner pattern in `CertComplianceChart` which uses indigo. |
| `start`/`end` params on deadline + approval | Backend may want date-range scoping. Params flow through as query string; unused now (defaults to empty → backend picks its own range). No component props added yet — this is a clean extension point. |

---

## New backend endpoints required

These endpoints do not yet exist in the backend. A companion backend task should be filed:

```
GET /reports/analytics/deadline-adherence/
  Optional query params: start, end (ISO dates)
  Response: DeadlineAdherencePoint[]  (period, adherencePercent, totalTeachers, onTime, late)

GET /reports/analytics/approval-trends/
  Optional query params: start, end (ISO dates)
  Response: ApprovalTrendsPoint[]  (period, approved, rejected, pending)

GET /reports/analytics/course-effectiveness/
  Response: CourseEffectivenessItem[]  (courseId, courseName, completionRate, avgScore, enrolledCount)
```

Until the backend endpoints are live, the charts will show the error state ("Failed to load …")
rather than crashing. No regression in existing passing tests.

---

## Verification

```
npx tsc --noEmit  → 0 errors
npx vitest run    → 619/619 passed (no regressions)
```

Please also verify:
1. `adminReportsService.ts` — three new methods follow the same `clean`-object param-stripping
   pattern as `engagementHeatmap()`.
2. All three charts: no remaining `MOCK_DATA` references, no TODO comments.
3. Loading/error/empty states present in each chart's `<div className="h-56">` section.

— frontend-engineer
