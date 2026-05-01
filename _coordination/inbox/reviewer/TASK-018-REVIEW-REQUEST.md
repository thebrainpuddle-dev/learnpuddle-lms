# TASK-018 — Mastery Points — Review Request

**From:** backend-engineer
**To:** reviewer
**Date:** 2026-04-20
**Status:** ready for review
**Task doc:** `docs/coordination/TASK-018-mastery-points.md`

## Summary

Adds a second gamification currency — **Mastery Points (MP)** —
complementary to XP. XP continues to reward effort (activity-based,
cheap); MP rewards demonstrated competence (high-score quizzes, graded
assignments, course-level mastery). Separate ledger
(`MasteryPointTransaction`) + separate summary (`TeacherMasterySummary`)
keep the two currencies independent. Opt-out is shared with XP.

## Files

### New

- `backend/apps/progress/mastery_engine.py` — `award_mastery_points`,
  `award_quiz_mastery`, `award_assignment_mastery`,
  `award_course_mastery_bonus`, `get_mastery_summary`.
- `backend/apps/progress/mastery_views.py` — teacher summary,
  teacher history, admin leaderboard endpoints.
- `backend/apps/progress/migrations/0019_mastery_points.py` —
  additive-only (5 config fields + 2 new tables + partial unique
  constraint).
- `backend/apps/progress/tests_mastery_points.py` — 20 tests.
- `docs/coordination/TASK-018-mastery-points.md` — task doc.

### Modified

- `backend/apps/progress/gamification_models.py` — adds
  `MASTERY_POINT_REASON_CHOICES`, 5 `GamificationConfig` tunables,
  `MasteryPointTransaction`, `TeacherMasterySummary`.
- `backend/apps/progress/gamification_serializers.py` —
  `MasteryPointTransactionSerializer`,
  `TeacherMasterySummarySerializer`,
  `MasteryLeaderboardEntrySerializer`.
- `backend/apps/progress/gamification_urls.py` — 3 new routes
  (`/mastery/`, `/mastery/history/`,
  `/admin/mastery/leaderboard/`).
- `backend/apps/progress/gamification_signals.py` — extends quiz
  submission handler with MP; adds assignment-graded MP handler;
  calls course mastery bonus from inside the existing
  course_completion XP block.
- `backend/apps/progress/models.py` — re-export the two new models
  for Django registration.

## Formulas / thresholds

| Source | Threshold | Amount |
|--------|-----------|--------|
| Quiz | `score_percent >= mp_quiz_threshold_percent` (default 80) | `round(score_percent * mp_quiz_weight)` (default weight 1.0) |
| Assignment | `score_percent >= mp_assignment_threshold_percent` (default 80) | `round(raw_score * mp_assignment_weight)` |
| Course completion | avg quiz `score_percent >= mp_quiz_threshold_percent` | flat `mp_course_bonus` (default 50) |

## Idempotency

Partial unique constraint on
`(teacher, reason, reference_type, reference_id)` where
`reference_id IS NOT NULL`. The engine wraps `create()` in
`transaction.atomic()` and catches `IntegrityError` — duplicate awards
silently no-op. This covers:

- Admin re-grades of quiz or assignment submissions.
- Repeated course completion hook fires.
- Accidental double-saves from signal handlers.

Admin adjustments (`reason='admin_adjust'`, `reference_id=NULL`) are
explicitly allowed to repeat.

## Cross-tenant isolation

- Both new models use `TenantManager` + `all_objects`.
- `award_mastery_points` derives `tenant = teacher.tenant` —
  teachers can only write to their own ledger.
- Admin leaderboard + teacher history both filter with
  `all_objects.filter(tenant=request.tenant)` + (for teacher routes)
  `teacher=request.user`.

## API surface

Teacher (TEACHER / HOD / IB_COORDINATOR / SCHOOL_ADMIN via
`@teacher_or_admin`):
- `GET /api/v1/gamification/mastery/`
- `GET /api/v1/gamification/mastery/history/`

Admin (SCHOOL_ADMIN / SUPER_ADMIN):
- `GET /api/v1/gamification/admin/mastery/leaderboard/?limit=...`

## Test status

**20 tests total**: 5 model · 9 engine · 5 signal wiring · 5 API.

Sandbox lacks docker / pytest — please run
`pytest apps/progress/tests_mastery_points.py -v` in CI and report
failures for follow-up.

## Risks & known limitations

- Course mastery bonus uses `QuizSubmission` (legacy) only. If the
  tenant has migrated fully to `QuizAttempt` in `assessment_models`,
  the course bonus formula won't account for those attempts. Flagged
  in the task doc as a follow-up.
- No admin UI to manually adjust MP (parallel to `xp_adjust`) — happy
  to add in a follow-up if desired.
- No frontend surface yet — frontend-engineer follow-up.
- Zero backfill: MP accumulates going forward. Historical submissions
  do **not** retroactively award MP. Intentional — simpler rollout.

## Coordination

Appended progress entry to `_coordination/shared-log.md` under
`## 2026-04-20`. Task status is `review`. No git commits made.
