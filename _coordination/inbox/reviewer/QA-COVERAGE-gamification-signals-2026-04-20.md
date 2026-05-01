# QA Coverage — `apps.progress.gamification_signals`

**Date**: 2026-04-20
**Agent**: qa-tester
**Scope**: `backend/apps/progress/gamification_signals.py` (175 LoC, 3 signal receivers)

## Why this area

Before today, **zero** dedicated tests existed for the three `post_save` signal
handlers that wire learning activity to XP / streak / league bumps:

- `on_teacher_progress_save` — content completion + course completion
- `on_assignment_submission`
- `on_quiz_submission`

`grep -n "def test_" apps/progress/` found **191** tests across 10 files, but
none targeted `gamification_signals.py` directly. A handful of existing
quiz-attempt tests (`tests_quiz_attempts.py`) exercise
`on_quiz_submission` as a side-effect of the `/submit` HTTP path, but
`on_teacher_progress_save` and `on_assignment_submission` were not covered at
all. Since the streak-freeze-token work + league lazy-assign branch now run
inside `award_xp` (called from these signals), drift risk was high.

## Deliverable

**File**: `backend/apps/progress/tests_gamification_signals.py`
**Tests**: **24** (all `TestCase`-based; no API client — direct ORM triggers)

### Test classes

| Class | Tests | What it proves |
|-------|------:|----------------|
| `TeacherProgressContentCompletionSignalTest` | 8 | Content XP awarded once, streak bumped, summary updated; non-COMPLETED skipped; dedup on re-save; missing tenant / inactive config / opt-out short-circuits |
| `TeacherProgressCourseCompletionSignalTest` | 3 | Course XP fires only when every content row is COMPLETED; dedups on subsequent saves |
| `AssignmentSubmissionSignalTest` | 5 | SUBMITTED/GRADED award once; PENDING skipped; status-change re-save does NOT double-award (because `created=False`); streak bumped |
| `QuizSubmissionSignalTest` | 7 | Completed attempt awards; in-progress (`score=None`) skipped; abandoned timed attempt (`time_expired=True, score=0`) skipped; time-expired-with-partial-score DOES award; each attempt gets its own XP; admin re-grade does not double-award; streak bumped |
| `SignalCrossTenantIsolationTest` | 2 | XP rows carry the correct tenant FK; simultaneous activity in two tenants does not cross-attribute |

## Coverage delta (estimate)

- `gamification_signals.py` — prior line coverage ~30% (exercised incidentally
  via quiz tests). New tests hit every branch including the three
  short-circuit paths (missing tenant, `score is None`, `time_expired` +
  zero-score). Estimated post-change line coverage: **~95%**.
- Overall progress-app line coverage uplift: **+0.5–1.0 pp** (small file, but
  every branch exercised).
- Overall backend coverage delta: **~+0.2 pp** toward the 60 % target.

## Notable findings

1. **No bugs discovered.** Signal dedup logic (XPTransaction.filter-by-ref
   lookup for content + course, `instance.id` lookup for quizzes) holds up
   under re-save / admin re-grade / timed-abandonment scenarios.
2. **Worth flagging for backend engineer**: the `on_assignment_submission`
   handler uses `if not created: return`, which is intentional but means an
   admin grading a PENDING submission via `.save()` will never retroactively
   earn the teacher XP — only the CREATE of the row triggers the award. If
   product ever wants XP to fire on transition to GRADED, this is the spot.
3. **Streak side-effect**: every successful XP award also records activity
   for the day — tests confirm the streak counter moves from 0 → 1 on the
   first activity of the day across all three signals.

## What remains untested (future work)

- `apps/progress/signals.py` (separate file, not `gamification_signals.py`) —
  check whether it exists and what it wires; today's session focused on the
  gamification handlers only.
- `apps/notifications/signals.py` — websocket push on notification create.
  WebSocket layer is hard to assert without a channels testing harness;
  deferred.
- Challenge-progress fan-out from these same triggers (not yet landed —
  TASK-017 in flight per handoff).
- End-to-end badge-award assertions inside the signal path (i.e. a streak
  milestone auto-granting a `StreakFreezeToken`). Covered elsewhere in
  `tests_streak_freeze_tokens.py`; no duplication added.

## How to run

```
docker compose exec web pytest apps/progress/tests_gamification_signals.py -v
```

No production code was modified. No git operations performed.

— qa-tester
