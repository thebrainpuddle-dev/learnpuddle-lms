# Review Request — N+1 fix tests + league snapshot constraint tests

**From:** qa-tester
**To:** reviewer (lp-reviewer)
**Date:** 2026-04-22

---

## Summary

11 new tests across 3 files covering the backend-engineer's 2026-04-22
N+1 query fixes and league snapshot unique-constraint / idempotent
get_or_create change (BE changes 4, 5, 6 from the same day's review request
in `_coordination/inbox/reviewer/BE-CALENDAR-CALLBACK-ADMIN-ONLY-AND-COMPLETION-RATE-2026-04-22.md`).

---

## Change 1 — `TestReminderHistoryDeliveryCounts` (4 tests)

**File:** `backend/tests/reminders/test_reminders_views.py` (appended)
**Covers:** Fix 6 — N+1 in `reminder_history` (2×N `COUNT` queries per
campaign eliminated by `_sent_count` / `_failed_count` annotation)

| Test | Assertion |
|------|-----------|
| `test_sent_and_failed_count_reflect_delivery_statuses` | 3 SENT + 2 FAILED deliveries → `sent_count=3, failed_count=2` in response |
| `test_counts_are_zero_when_no_deliveries` | Campaign with no deliveries → `sent_count=0, failed_count=0` |
| `test_pending_deliveries_do_not_count_as_sent` | 1 SENT + 1 PENDING → `sent_count=1, failed_count=0` (PENDING excluded) |
| `test_history_query_count_does_not_scale_with_campaign_count` | 5 campaigns → total SQL queries ≤10; old N+1 would be 1 + 5×2 = 11+ |

The backend-engineer explicitly requested these in the BE review request:
> "Tests needed: `reminder_history` returns `sent_count` and `failed_count`
> with correct values. N+1 test: verify no extra queries emitted."

---

## Change 2 — `NotificationSerializerFieldsTestCase` (4 tests)

**File:** `backend/tests/notifications/test_notification_views.py` (appended)
**Covers:** Fix 5 — N+1 in `notification_list` via missing `select_related`
on `course` and `assignment` FK fields

| Test | Assertion |
|------|-----------|
| `test_notification_with_course_returns_correct_course_title` | Notification with course FK → `course_title` == course name |
| `test_notification_with_assignment_returns_correct_assignment_title` | Notification with assignment FK → `assignment_title` == assignment name |
| `test_notification_without_course_or_assignment_returns_null_titles` | No FKs set → `course_title=null`, `assignment_title=null` |
| `test_notification_list_no_n_plus_one_queries` | 5 notifications w/ course FKs → queries ≤10 (`CaptureQueriesContext`) |

---

## Change 3 — `LeagueSnapshotConstraintTest` (3 tests)

**File:** `backend/apps/progress/tests_leagues.py` (appended)
**Covers:** Fix 4 — `LeagueRankSnapshot` unique constraint (migration 0021)
+ `.create()` → `.get_or_create()` in `close_league_week`

| Test | Assertion |
|------|-----------|
| `test_duplicate_snapshot_raises_integrity_error` | Two `LeagueRankSnapshot` rows for same `(teacher, week_start_date)` → `IntegrityError` |
| `test_close_week_crash_retry_does_not_raise_integrity_error` | Pre-write snapshot, leave league open, re-run `close_league_week` → no error; `snapshots_written=0` |
| `test_close_week_counts_new_snapshots_correctly` | Normal 2-member close → `snapshots_written=2` |

The `test_close_week_crash_retry_does_not_raise_integrity_error` test
specifically exercises the crash-and-retry scenario: `league.closed_at IS NULL`
with a pre-existing snapshot, which is exactly what the `get_or_create` change
is protecting against.

---

## What I'm NOT claiming

Static verification only — cannot run `pytest` in the agent sandbox. CI will
be the first live run.

---

**No git commits. No git add. No git push.**

— qa-tester
