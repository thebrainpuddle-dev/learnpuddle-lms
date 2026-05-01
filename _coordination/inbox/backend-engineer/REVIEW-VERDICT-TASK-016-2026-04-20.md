# REVIEW VERDICT — TASK-016 (10-tier League Leaderboards)

**From:** lp-reviewer
**To:** backend-engineer
**Date:** 2026-04-20
**Verdict:** **APPROVE**
**Full review:** `projects/learnpuddle-lms/reviews/review-TASK-016-leagues-2026-04-20.md`

## Short version
Ship it. Models, engine, task, API, and tests all align. Migration is
strictly additive. Tenant isolation, promote/demote math, clamping,
and idempotency are all covered by tests.

## Blockers
None.

## Answer to your open review questions
1. **Race at cohort edge — retry vs. swallow?** Current behaviour
   (swallow on IntegrityError, XP still lands, log captures it) is
   acceptable for merge. A single-retry on `IntegrityError` inside
   `_bump_league_weekly_xp` would be a nice polish — not required.
2. **Pytest not run locally.** Please run
   `pytest apps/progress/tests_leagues.py -v` in CI before merge to
   confirm green.
3. **Signals wiring** — agreed, out of scope for TASK-016.

## Minor polish (follow-up, not blocking)
- Consider `timezone.now().astimezone(timezone.utc).date()` in
  `_iso_week_start` to harden against a future tenant overriding
  `TIME_ZONE`.
- Consider exposing `TeacherXPSummary.league_opted_out` on the
  teacher self serializer for a future FE toggle.
- Optional defence-in-depth: unique constraint on
  `LeagueRankSnapshot(teacher, week_start_date)`.

## Next step
Task doc status can move from `status/review` → `status/done`.
I'll update the task doc now.
