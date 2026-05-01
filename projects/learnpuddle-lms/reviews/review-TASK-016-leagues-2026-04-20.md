---
tags: [review, task/TASK-016, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-20
---

# Review: TASK-016 — 10-tier League Leaderboards

## Verdict: APPROVE

## Summary
Solid, well-isolated implementation of Phase 4 relative-positioning leagues.
Models, engine, Celery task, API and tests all hang together cleanly;
tenant scoping, idempotency, and promote/demote clamping are correct and
exercised by tests. Migration is strictly additive. Safe to ship.

## Requirements vs. acceptance criteria
- 10-tier taxonomy (Bronze I..Diamond) with rank 1..10 — confirmed in
  `league_models.LEAGUE_TIERS` + 5 constant tests.
- Weekly Monday 00:00 UTC close — `config/celery.py` beat entry
  `progress-close-league-week-weekly` uses
  `crontab(hour=0, minute=0, day_of_week="mon")` and the task path
  `progress.close_league_week` matches `@shared_task(name=...)` in
  `gamification_tasks.py`.
- Promote 7 / demote 7 / hold middle with small-cohort scaling and
  <3-member skip — implemented in `_scale_count` +
  `close_league_week`; test `test_small_cohort_scales_promote_count`
  verifies `round(3*4/10) = 1`.
- Clamping at Diamond / Bronze I — verified by
  `test_top_tier_promotion_is_clamped` and
  `test_bottom_tier_demotion_is_clamped`.
- Tenant isolation — every query in `league_engine.py` filters by
  `tenant=` explicitly; `test_close_week_is_tenant_scoped` creates a
  second tenant and asserts no snapshots/close mutations leak.
- Opt-in/opt-out — `TeacherXPSummary.league_opted_out` and
  `opted_out` both short-circuit `_is_teacher_eligible`; admin roles
  (`SUPER_ADMIN`, `SCHOOL_ADMIN`) also excluded.
- API auth — all three views carry
  `@permission_classes([IsAuthenticated])` +
  `@teacher_or_admin`/`@admin_only` + `@tenant_required`.
- `GamificationConfigSerializer` exposes the 5 new config fields.

## Critical issues
None.

## Major issues
None blocking. One behavioural nuance to flag for follow-up, not a
blocker:

- **Race swallow at cohort edge.** Concurrent first-XP awards for the
  same teacher in the same week can both reach
  `assign_teacher_to_league` before either row commits. The inner
  `@transaction.atomic` doesn't serialize across connections; the
  `UniqueConstraint` on `(teacher, league)` will raise `IntegrityError`
  on the losing caller, which bubbles out of
  `_bump_league_weekly_xp` and is caught by the broad `except` in
  `award_xp` (line 120). Net effect: that one XP award silently skips
  the league bump (the XP itself still lands). Acceptable in practice
  (the next award fixes it, and ordering of first-bump in a week is
  invisible to users) but worth a single retry on `IntegrityError` in
  a future polish pass. Logging already captures it.

## Minor issues
- `league_views.teacher_current_league` does a write
  (`assign_teacher_to_league`) on a `GET`. Idempotent, but a future
  rate-limited read-replica setup would trip on it. Consider moving
  lazy-assignment behind a write-tolerant path (not urgent).
- `_iso_week_start` uses `timezone.localdate()` which honours
  `TIME_ZONE`; the task comment says "UTC". With Django's default
  `USE_TZ=True` and `TIME_ZONE='UTC'` this is fine, but if a tenant
  ever overrides `TIME_ZONE` the Monday boundary could shift. Cheap
  hardening: `timezone.now().astimezone(timezone.utc).date()`.
- `gamification_serializers.py` exposes all 5 new config columns but
  doesn't expose `TeacherXPSummary.league_opted_out` on any
  teacher-facing serializer. The admin overview endpoint surface is
  fine; a subsequent FE task likely needs this on the teacher self
  serializer.
- `LeagueRankSnapshot` has no unique constraint on
  `(teacher, week_start_date)`. Idempotency of `close_league_week` is
  enforced by the `closed_at IS NOT NULL` early-exit rather than DB
  uniqueness. Acceptable since the early-exit is tested
  (`test_close_week_is_idempotent`), but a constraint would be
  defence-in-depth.

## Positive observations
- Clean separation of tier taxonomy (constants), engine (pure
  Python), models (persistence), views (HTTP) and task (scheduling).
- `_bump_league_weekly_xp` uses `F("weekly_xp") + delta` — no
  read-modify-write race on the XP column itself.
- Tie-break ordering (`-weekly_xp`, `-total_xp`, `created_at`) is
  deterministic and testable.
- `close_league_week` is wrapped in `@transaction.atomic`, snapshot
  + next-week memberships created in the same transaction that closes
  the league.
- Test suite genuinely covers behavior — small-cohort scaling,
  cross-tenant leak, clamping, idempotency, API cohort visibility.
- Migration `0017_leagues.py` is strictly additive; every new column
  has a default; dependency chain `progress.0016_streak_freeze_tokens`
  is correct.
- Celery task path `progress.close_league_week` matches the beat entry
  (no typo) and filters `GamificationConfig` by both
  `is_active=True` and `leagues_enabled=True` before iterating.
- Admin/super-admin exclusion in `_is_teacher_eligible` is explicit.

## Verification status
- Tests not executed by reviewer (sandbox constraint, as noted by
  author). Static trace against test expectations looks correct; CI
  should confirm green.
- `pytest apps/progress/tests_leagues.py -v` is the recommended gate
  before merge.
