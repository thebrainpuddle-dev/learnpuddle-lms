# FE-010 Review Request — Admin Skill Radar Page

**Branch:** `maic-sprint-1-presence-rhythm` (uncommitted working tree)
**Author:** frontend-engineer
**Date:** 2026-04-20

## Scope

Phase 4 gamification/analytics UI gap: **Admin Skill Radar page** at
`/admin/analytics/skills`. The page surfaces team-wide competency data —
average current level vs. average target level per skill — as a Recharts
RadarChart, plus summary stats, a "Focus areas" list ranked by biggest
gap, and a detailed breakdown table.

Heatmap page was deferred because no backend engagement-heatmap endpoint
exists today. Skill Radar is fully backed by
`backend/apps/reports/manager_views.py::manager_skills_overview`.

## Endpoint used

`GET /api/reports/manager/skills-overview/?category=<optional>`

The endpoint is already wired under `teacher_or_admin` + `tenant_required`
and returns `{ results: [...], summary: { ... } }` aggregated by skill.
For `SCHOOL_ADMIN`, `_get_managed_teachers` returns the entire tenant
teacher set — no backend changes required.

## Files changed

New:
- `frontend/src/pages/admin/SkillRadarPage.tsx`
- `frontend/src/pages/admin/SkillRadarPage.test.tsx` (5 tests)

Modified:
- `frontend/src/services/skillsService.ts` — new typed
  `overview(params?)` method + `SkillOverviewItem`,
  `SkillsOverviewSummary`, `SkillsOverviewResponse`,
  `SkillOverviewTeacherDetail` interfaces. No `any` added.
- `frontend/src/App.tsx` — `React.lazy` import + new
  `/admin/analytics/skills` route nested under the existing admin shell.
- `frontend/src/components/layout/AdminSidebar.tsx` — new **Skill Radar**
  entry under **INSIGHTS**, uses `ChartPieIcon`, `tourId`
  `admin-nav-skill-radar`.
- `frontend/src/pages/admin/index.ts` — re-export `SkillRadarPage`.

## Visual description

- Header row: page title + one-line explainer, right-aligned category
  `<select>` that re-queries with `?category=`.
- Three stat cards: *Skills tracked*, *Teachers assessed*, *Total skill
  gaps*, each with a colored Heroicon badge.
- Main grid (2-column on `xl`): a 420px Recharts RadarChart (two overlaid
  polygons: blue **Avg current**, amber **Avg target**) and a
  right-hand *Focus areas* card listing the top-5 biggest-gap skills
  with `-Δ` warning badges.
- Below: responsive table with columns *Skill, Category, Avg current,
  Avg target, Coverage %, Below target*. Coverage percentage is color-
  coded (green ≥80%, amber ≥50%, red <50%).
- Graceful empty state in the radar panel and table when no skills are
  mapped yet.
- Error state shows `role="alert"` red panel with *Retry* button.

## Verification

- `npx tsc --noEmit` — 0 errors
- `npx vitest run` — **43 files / 352 tests all green**
  - 5 new tests for `SkillRadarPage` (summary stats + chart + table
    render, focus-area ordering, empty state, category filter refetch,
    error-state with retry)
  - 347 pre-existing tests unaffected

No commits were made per agent rules.
