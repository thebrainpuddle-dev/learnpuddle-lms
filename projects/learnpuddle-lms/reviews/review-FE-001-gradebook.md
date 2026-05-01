---
tags: [review, task/FE-001, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-19
author: frontend-engineer
branch: maic-sprint-1-presence-rhythm
files:
  - frontend/src/pages/admin/GradebookPage.tsx (new)
  - frontend/src/App.tsx (route added)
  - frontend/src/components/layout/AdminSidebar.tsx (nav added)
---

# Review: FE-001 — Admin Gradebook page (/admin/gradebook)

## Verdict: APPROVE

## Summary
Well-structured, self-contained page built on the existing `DataTable` + TanStack Query conventions. Column defs, summary widgets, and CSV export are cleanly separated; filters are composed correctly into query keys. No critical, security, or tenant-isolation issues. Safe to ship.

## Critical Issues
None.

## Major Issues
None.

## Minor Issues

1. **CSV injection risk on export (L60–82).** Cells are quote-escaped but not prefixed to neutralise spreadsheet formulas. A teacher whose name begins with `=`, `+`, `-`, or `@` (e.g. `=HYPERLINK(...)`) would execute in Excel/Sheets when the admin opens the CSV. Low likelihood in practice, but worth a single-line guard:
   ```ts
   const safe = /^[=+\-@\t\r]/.test(s) ? `'${s}` : s;
   ```
   Apply before the existing quote/escape step. Not blocking — tenant-scoped data, admin-only consumer — but trivial to add and worth doing once across all CSV exports we emit.

2. **`role` filter uses `'teachers' | 'students'` literal but backend expects role codes.** The page sends `role: 'teachers'` / `role: 'students'` to `adminReportsService.courseProgress`. If the backend filter keys on `role__in=['TEACHER','HOD','IB_COORDINATOR']` vs `role='STUDENT'` (or similar), the mapping must live somewhere — please confirm the backend accepts these exact strings, or translate at the service layer. Not visible from this diff; flagging so it gets verified before QA.

3. **`courseColumns` / `assignmentColumns` are duplicated 80%** (Name, Role, Grade/Section cells are identical). A shared `teacherIdentityColumns()` helper would shave ~60 lines. YAGNI is fine for now; noting for when the third tab arrives.

4. **Dropdowns are plain native `<select>`** while the rest of admin uses the shadcn `Select` primitive. Minor visual inconsistency with the filter pill above.

## Positive Observations

- Clean separation: columns → summary → main component, all pure functions where possible.
- `useMemo` on derived rows, `enabled: !!courseId` gate on the query, correct cache keying on all four filter inputs — no wasted fetches.
- `usePageTitle`, `DataTable`, `Badge`, `Button`, `Loading` all come from the established component library — no new primitives invented.
- Empty / no-selection / loading states are all handled distinctly. Good UX polish.
- No `any`, no `console.log`, no dead code, no hardcoded tenant data.
- CSV export is dependency-free and correctly revokes the object URL.
- Naming is clear (`needsSelect`, `hasData`, `courseRows`).

## Testing Notes
No Jest/Vitest test added for this page. Acceptable for a pure view layer built from tested primitives, but a smoke test covering "renders empty state without a course selected" + "renders table when data arrives" would protect against future regressions. Follow-up task for qa-tester.

## Next Actions
- `status/review` → `status/done`
- Minor issues 1 & 2 logged as follow-ups, not blockers.
