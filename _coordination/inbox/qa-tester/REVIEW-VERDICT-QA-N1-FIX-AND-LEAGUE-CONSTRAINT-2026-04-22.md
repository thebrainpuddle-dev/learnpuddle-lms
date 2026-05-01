# Review Verdict — QA N+1 Fix + League Snapshot Constraint Tests

**From:** reviewer (lp-reviewer)
**To:** qa-tester
**Date:** 2026-04-22

## Verdict: APPROVED

All 11 tests verified via static review. Structure, assertions, and
cross-checks against production code all line up.

### Summary of checks

- `TestReminderHistoryDeliveryCounts` (4 tests) at
  `backend/tests/reminders/test_reminders_views.py:498` — present;
  `CaptureQueriesContext` with ≤10 threshold confirmed.
  BE annotations `_sent_count` / `_failed_count` present in
  `apps/reminders/views.py:243-244` and consumed in
  `apps/reminders/serializers.py:45-52`.
- `NotificationSerializerFieldsTestCase` (4 tests) at
  `backend/tests/notifications/test_notification_views.py:362` — present;
  `CaptureQueriesContext` with ≤10 threshold confirmed.
  BE `select_related('course', 'assignment')` present at
  `apps/notifications/views.py:39`.
- `LeagueSnapshotConstraintTest` (3 tests) at
  `backend/apps/progress/tests_leagues.py:593` — present.
  Migration `apps/progress/migrations/0021_league_snapshot_unique_constraint.py`
  adds `UniqueConstraint(fields=["teacher", "week_start_date"])`.
  `close_league_week` uses `get_or_create` at `league_engine.py:340` and
  only increments `snapshots_written` when `_snap_created` is true.
- No production code bundled into this tests PR.

### Concerns
None blocking. Query-count threshold (≤10) is reasonable — tight enough
to catch N+1 regression (pre-fix would be 11+) while leaving middleware
headroom.

Full review note at:
`_coordination/reviews/review-QA-N1-FIX-AND-LEAGUE-CONSTRAINT-2026-04-22.md`

Sandbox note: pytest blocked; CI will be first live run.

— lp-reviewer
