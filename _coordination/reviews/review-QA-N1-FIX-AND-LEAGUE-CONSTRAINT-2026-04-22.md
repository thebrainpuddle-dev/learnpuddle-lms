---
tags: [review, task/qa-n1-league, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-22
---

# Review: QA N+1 Fix + League Snapshot Constraint Tests

## Verdict: APPROVE

## Summary
11 new tests across 3 files correctly validate the backend-engineer's
2026-04-22 N+1 fixes (reminder_history, notification_list) and the
LeagueRankSnapshot unique-constraint + idempotent `get_or_create` change.
Static review; pytest blocked in sandbox. All assertions align with the
production BE code they exercise.

## Checks Performed

### 1. `backend/tests/reminders/test_reminders_views.py`
- `TestReminderHistoryDeliveryCounts` class present at line 498 with all
  4 named tests (549, 590, 618, 647). Confirmed.
- `test_history_query_count_does_not_scale_with_campaign_count` uses
  `CaptureQueriesContext` (line 655) and asserts `<= 10` queries for 5
  campaigns — threshold matches request. Old N+1 would emit 1 + 5×2 = 11.
- Cross-check BE fix: `apps/reminders/views.py:243-244` applies
  `_sent_count` / `_failed_count` Count-with-filter annotations; serializer
  (`serializers.py:45-52`) reads `hasattr(obj, "_sent_count")` with live
  fallback. Annotation path verified.

### 2. `backend/tests/notifications/test_notification_views.py`
- `NotificationSerializerFieldsTestCase` class present at line 362 with
  all 4 tests (435, 456, 478, 501). Confirmed.
- N+1 test uses `CaptureQueriesContext` (line 511) with `<= 10` threshold
  for 5 notifications (pre-fix would be 11+).
- Cross-check: `apps/notifications/views.py:39` applies
  `.select_related('course', 'assignment')`. Match.

### 3. `backend/apps/progress/tests_leagues.py`
- `LeagueSnapshotConstraintTest` class present at line 593 with all 3 tests
  (623, 665, 732). Confirmed.
- Migration `0021_league_snapshot_unique_constraint.py` is a clean
  additive `AddConstraint` on `(teacher, week_start_date)` with name
  `unique_league_rank_snapshot_per_teacher_per_week`; depends on 0020.
- `league_engine.py:340` uses `LeagueRankSnapshot.all_objects.get_or_create(
  teacher=..., week_start_date=..., defaults={...})` and only increments
  `snapshots_written` when `_snap_created` is true. Exactly what
  `test_close_week_crash_retry_does_not_raise_integrity_error` asserts
  (`snapshots_written == 0` on retry).
- `league_models.py:227-233` declares the matching `UniqueConstraint` on
  the model — consistent with migration.

### 4. Production-code scope
- Test files are either appended to existing test modules or new files
  (e.g., `tests_leagues.py` is untracked). No production-code edits are
  bundled into this tests PR.

## Critical Issues
None.

## Major Issues
None.

## Minor Issues / Observations
- Query-count budget of ≤10 is generous but appropriate — it leaves
  headroom for auth/tenant middleware `SELECT`s without weakening the
  regression signal (old N+1 would be 11+).
- All tests use realistic fixtures and API calls (not direct serializer
  probing), which validates behavior end-to-end.

## Positive Observations
- N+1 tests correctly match BE's exact annotation keys (`_sent_count`,
  `_failed_count`) and `select_related` pair (`course`, `assignment`).
- Crash-retry test asserts both the no-raise behavior AND
  `snapshots_written == 0` — which uniquely pins the `get_or_create`
  semantics versus a plain try/except wrapper.
- Good docstrings linking each test to the specific BE fix number.
