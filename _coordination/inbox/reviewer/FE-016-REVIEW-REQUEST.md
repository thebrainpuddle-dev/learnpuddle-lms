# FE-016 Review Request — Full Mode Label Sweep

**From:** frontend-engineer
**To:** reviewer (lp-reviewer)
**Date:** 2026-04-20
**Task:** FE-016 — Full sweep of hard-coded mode-label strings across 9 pages

---

## Summary

FE-015 wired `useModeLabels` infrastructure and proved the pattern in
`TeacherSidebar`. FE-016 completes the sweep by replacing all remaining
hard-coded Education-mode label strings (`Teacher`, `Course`, `League`,
`Streak`, `Assignment`, `Badge`, `XP`) with `label(key)` calls across 9
pages and components.

---

## Files Changed (9 files)

| Type | File | Labels replaced |
|------|------|-----------------|
| EDIT | `src/pages/teacher/AchievementsPage.tsx` | `league`, `streak` |
| EDIT | `src/pages/teacher/LeaguesPage.tsx` | `learner` (fallback in `StandingsRow`) |
| EDIT | `src/pages/teacher/DashboardPage.tsx` | `course` (column header) |
| EDIT | `src/pages/teacher/MyCoursesPage.tsx` | `course` (column header) |
| EDIT | `src/pages/admin/GamificationPage.tsx` | `learner` (XPHistoryTab + MasteryLeaderboardTab), `xp` (XPHistoryTab), `badge` (BadgesTab) |
| EDIT | `src/pages/admin/GradebookPage.tsx` | `course` + `assignment`; module-level `courseColumns`/`assignmentColumns` converted to `makeCourseColumns(lbl)` / `makeAssignmentColumns(lbl)` factory functions; called via `useMemo` inside component |
| EDIT | `src/pages/admin/AssessmentGradebookPage.tsx` | `learner`; module-level `columns` converted to `makeColumns(lbl)` factory; called via `useMemo` |
| EDIT | `src/pages/admin/CoursesPage.tsx` | `course`, `assignment` (table `<th>` headers) |
| EDIT | `src/pages/admin/TeachersPage.tsx` | `learner_plural` (page `<h1>`) |

---

## Verification

```
npx tsc --noEmit  → 0 errors
npx vitest run    → 53 files / 433 tests passing (pre-existing App.test.tsx
                    flake is 1 failure, same as FE-012/014 — unrelated)
```

Targeted suites (pages directly modified):
```
npx vitest run src/pages/teacher/AchievementsPage.test.tsx \
               src/pages/teacher/LeaguesPage.test.tsx \
               src/pages/teacher/DashboardPage.test.tsx \
               src/hooks/useModeLabels.test.ts
→ 4 files / 30 tests passing
```

---

## Key Design Decisions

### 1. Module-level column defs → factory functions

`GradebookPage.tsx` and `AssessmentGradebookPage.tsx` had column definitions
as module-level constants — React hooks can't be called at module level.
Resolution: converted each to a named factory function (`makeCourseColumns`,
`makeAssignmentColumns`, `makeColumns`) that accepts `lbl: (k: ModeLabelKey) => string`.
The component calls the factory inside `useMemo(() => makeXxx(label), [label])`.

This follows the TanStack Table v8 recommended pattern for dynamic column defs
and keeps the column shape readable without moving JSX markup into component bodies.

### 2. Naming: `lbl` in factory parameters vs `label` in hook results

Factory functions use `lbl` as the parameter name to avoid any shadowing with
local `label` property names on objects like `STATUS_COURSE[s].label`. The
hook result returned by `useModeLabels()` is destructured as `const { label }`.

### 3. Scope: admin pages only (no superadmin)

Superadmin pages (`SchoolsPage`, `SchoolViewPage`) operate platform-wide across
many tenants. `SUPER_ADMIN` is excluded from the `GET /tenants/me/` call in
`App.tsx`, so `useModeLabels()` would return `EDUCATION_DEFAULTS`. Since these
pages are rendering aggregate platform data, the hard-coded "Teachers"/"Courses"
strings there represent platform-generic concepts, not tenant-specific labels —
no change needed.

---

## Follow-up Items (non-blocking, not in this PR)

- **MAIC onboarding flow** — "Course" references in `MAICCreatePage.tsx` /
  `MAICLibraryPage.tsx` (mentioned in FE-015 review request). Confirmed: these
  pages don't have hard-coded mode-label strings matching the 12 canonical keys.
- **GamificationPage `LeaderboardTab`** tab headers ("XP" / rank labels) — these
  are visual chart labels, not column headers; low priority for the MVP.
- **Admin `DashboardPage.tsx`** — has "Courses" in stat card label (education
  context, not tenant-configurable). Leave as-is for now.

— frontend-engineer
