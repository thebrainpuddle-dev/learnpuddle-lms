# TASK-016 Review Request — 10-Tier League Leaderboards

**From:** backend-engineer
**To:** reviewer
**Date:** 2026-04-20
**Status:** `status/review`
**Phase:** 4 — Gamification

## Summary

Implements relative-positioning league leaderboards per master strategy line
117: 10 tiers (Bronze I → Diamond), weekly Monday 00:00 UTC close, promote
top N / demote bottom N / hold middle, tenant-scoped cohorts of ~30 teachers,
per-teacher opt-in/opt-out.

## Files Changed

### New
- `backend/apps/progress/league_models.py` — `League`, `LeagueMembership`,
  `LeagueRankSnapshot` + 10-tier taxonomy constants.
- `backend/apps/progress/league_engine.py` — eligibility, lazy assignment,
  `close_league_week()` promote/demote engine.
- `backend/apps/progress/league_views.py` — 3 API endpoints.
- `backend/apps/progress/tests_leagues.py` — 22 TDD tests.
- `backend/apps/progress/migrations/0017_leagues.py` — additive migration.
- `docs/coordination/TASK-016-leagues.md` — task spec & math rationale.

### Modified
- `backend/apps/progress/gamification_models.py` — added 5 league config
  columns + `TeacherXPSummary.league_opted_out`.
- `backend/apps/progress/gamification_serializers.py` — exposed new config
  fields in admin surface.
- `backend/apps/progress/gamification_engine.py` — `award_xp` now also bumps
  `LeagueMembership.weekly_xp` for the teacher's current cohort (lazy
  assignment on first XP of the week). Wrapped in try/except so league
  errors never break XP award.
- `backend/apps/progress/gamification_tasks.py` — added Celery task
  `progress.close_league_week` (iterates tenants, calls engine).
- `backend/apps/progress/gamification_urls.py` — 3 new URL routes.
- `backend/config/celery.py` — beat schedule entry for Monday 00:00 UTC.

## Test Count

22 tests in `apps/progress/tests_leagues.py`:
- 5 tier-constant tests
- 4 model tests (create, uniqueness, cross-tenant isolation, snapshot shape)
- 6 engine assignment tests (new teacher, idempotency, opt-out, cohort fill,
  overflow)
- 6 promote/demote math tests (correct bucket counts, top clamp, bottom clamp,
  idempotency, tenant-scope, small-cohort scaling)
- 2 Celery task tests
- 4 API tests (teacher current, opted-out empty, cross-tenant isolation,
  admin overview, teacher history)

## Promote/Demote Math (Key Detail)

Defaults (tunable via `GamificationConfig.league_*` columns):
- `league_cohort_size = 30`
- `league_promote_count = 7`
- `league_demote_count = 7`
- Middle 16 hold position.

**Scaling for small cohorts:** If a cohort has fewer than `cohort_size`
members, promote/demote counts scale proportionally:
`scaled = max(1, round(configured * actual_size / cohort_size))`. Below 3
members, nobody moves. If `promote_n + demote_n > size`, demote is reduced
to eliminate overlap.

**Clamping:**
- Bronze I demotions stay in Bronze I (no lower tier).
- Diamond promotions stay in Diamond (no higher tier).

**Tie-breaking:** `weekly_xp` desc → `total_xp` desc (from `TeacherXPSummary`) →
`membership.created_at` asc.

## Idempotency

- `close_league_week(tenant, week_start)` skips already-closed leagues
  (`closed_at IS NOT NULL`). Safe to replay.
- `assign_teacher_to_league(teacher)` returns existing membership if one
  already exists for the target week.
- Celery beat running the task twice in the same ISO week is a no-op.

## Opt-In / Opt-Out

- Honours `GamificationConfig.opt_out_allowed` + `TeacherXPSummary.opted_out`
  (global gamification opt-out).
- Adds `TeacherXPSummary.league_opted_out` for league-specific opt-out.
- Adds `GamificationConfig.leagues_opt_in_required` flag (default False).
- Admin roles (`SUPER_ADMIN`, `SCHOOL_ADMIN`) never enrolled.

## Tenant Scoping

Every query in `league_engine.py` filters explicitly by `tenant=` (belt and
braces — not just relying on `TenantManager`). `close_league_week` takes a
`tenant` argument and only touches that tenant's leagues. Cross-tenant
leak test included in both model and API test suites.

## Risks & Open Questions

1. **Migration collision window:** `0017_leagues.py` is additive-only. New
   columns on `GamificationConfig` and `TeacherXPSummary` have defaults so
   existing rows receive them cleanly. Zero-downtime safe.

2. **Race at cohort edge:** Two concurrent `award_xp` calls could both try to
   lazy-assign a teacher to the same cohort. Protected by the `UniqueConstraint`
   on `(teacher, league)` and the `@transaction.atomic` wrapper on
   `assign_teacher_to_league`; an `IntegrityError` on the second would bubble
   up — the try/except in `_bump_league_weekly_xp` catches it and logs.
   **Review ask:** should we retry once rather than silently swallow?

3. **Pytest not run locally:** The sandbox in this session couldn't execute
   Python outside the working directory. All code paths were statically
   traced against the test expectations. Please run
   `pytest apps/progress/tests_leagues.py -v` to confirm green.

4. **No signal wiring from streak/badge events to `weekly_xp`:** Currently
   only direct `award_xp` calls bump the league. If future code awards XP
   without going through `award_xp`, leagues won't see it. Acceptable for
   this task — all existing XP sources route through `award_xp`.

5. **Frontend not touched** (per agent file ownership).

## How to Verify

```bash
cd backend
pytest apps/progress/tests_leagues.py -v
python manage.py migrate  # applies 0017_leagues
# Simulate weekly close manually:
python manage.py shell -c "
from apps.progress.gamification_tasks import close_league_week_task
print(close_league_week_task.apply().result)
"
```
