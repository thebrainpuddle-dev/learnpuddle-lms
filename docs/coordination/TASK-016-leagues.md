# TASK-016 — 10-Tier League Leaderboards (Phase 4 Gamification)

**Owner:** backend-engineer
**Status:** done
**Phase:** 4 — Gamification
**Reviewed:** 2026-04-20 by lp-reviewer — APPROVE (see `projects/learnpuddle-lms/reviews/review-TASK-016-leagues-2026-04-20.md`)
**Strategy line:** Master strategy line 117 — "10-tier league system with weekly
reset, promote/demote, relative positioning."

## Goal

Replace the flat tenant-wide leaderboard with a **relative-positioning league
system**. Teachers compete in small cohorts (~30 members) inside a tier. Each
Monday 00:00 UTC the league closes, the top N teachers promote one tier up,
the bottom M teachers demote one tier down, and the middle hold. New cohorts
are re-formed for the next week.

## Tier Taxonomy (10 tiers)

Ascending prestige:

| # | Code | Name | Rank |
|---|------|------|------|
| 1 | `bronze_1` | Bronze I | lowest |
| 2 | `bronze_2` | Bronze II | |
| 3 | `bronze_3` | Bronze III | |
| 4 | `silver_1` | Silver I | |
| 5 | `silver_2` | Silver II | |
| 6 | `silver_3` | Silver III | |
| 7 | `gold_1` | Gold I | |
| 8 | `gold_2` | Gold II | |
| 9 | `gold_3` | Gold III | |
| 10 | `diamond` | Diamond | highest |

Each tier has a numeric `tier_rank` (1..10) to make promote/demote math trivial.

## Promote / Demote Math

Defaults — tunable via `GamificationConfig`:

- `league_cohort_size = 30`
- `league_promote_count = 7` (top 7 move up a tier)
- `league_demote_count = 7` (bottom 7 move down a tier)
- Middle 16 hold position, enter a fresh cohort at the same tier.

Edge cases:

- **Tier 1 (Bronze I):** bottom 7 stay in Bronze I (nothing below).
- **Tier 10 (Diamond):** top 7 stay in Diamond (nothing above).
- **Cohort with < `league_cohort_size` members:** the reset still runs;
  promote/demote counts are proportionally scaled down using
  `round(count * actual_size / cohort_size)`, minimum 1 unless the cohort has
  only 1-2 members (then nobody moves).
- **Ties at the promotion boundary:** broken by (a) higher `total_xp` of the
  teacher's all-time summary, then (b) earlier `created_at` on the membership.

## Opt-in / Opt-out

- Honours existing `GamificationConfig.opt_out_allowed` + `TeacherXPSummary.opted_out`.
- **Additionally** introduces per-teacher league opt-out via
  `GamificationConfig.leagues_opt_in_required` (default `False` — everyone in)
  and `TeacherXPSummary.league_opted_out` (default `False`). Teachers may
  opt out of leagues specifically while staying in the general XP/badge system.

## Tenant scoping

Every model uses `tenant` FK + `TenantManager`. Cohorts are drawn exclusively
from within a single tenant. No cross-tenant leakage.

## Weekly reset (Celery beat)

`progress.close_league_week` runs Mondays at 00:00 UTC:

1. For each tenant with `GamificationConfig.leagues_enabled=True`:
2. For every open `League` row, rank members by `weekly_xp` (dense),
3. Snapshot final ranks into `LeagueRankSnapshot`,
4. Compute promote/demote lists,
5. Create fresh `League` rows for the new week (one per tier as needed),
6. Insert new `LeagueMembership` rows assigning teachers to a new cohort in
   their new tier,
7. Close the old `League` rows (`closed_at=now`).

**Idempotency:** the task keys on `week_start_date`. If the task runs twice in
the same ISO-week, the second run detects `League.closed_at is not None` and
skips.

## Models

- `League` — one row per tenant × tier × week (the cohort).
- `LeagueMembership` — teacher ∈ league, tracks `weekly_xp` and final rank.
- `LeagueRankSnapshot` — immutable historical record of end-of-week ranking.

## Migration

`0017_leagues.py` — additive only. Adds three models + five config columns.
No data backfill; teachers join their first league on their next activity
(auto-assignment via signal-driven lazy create in engine).

## API endpoints

Teacher:
- `GET /api/v1/gamification/league/` — the teacher's current league (cohort
  members, their ranks, remaining time in the week).
- `GET /api/v1/gamification/league/history/` — past snapshots for the teacher.

Admin:
- `GET /api/v1/gamification/admin/leagues/` — overview of all current leagues
  in the tenant (one row per tier with member counts).

## Non-goals

- Visual/theming for tier badges — handled by the frontend agent.
- Cross-tenant global leaderboards — explicitly excluded by multi-tenant rules.
- Season-long cumulative scores — future work.

## Test plan

See `backend/apps/progress/tests_leagues.py` — 20+ tests covering model,
engine, Celery task, and API surfaces.
