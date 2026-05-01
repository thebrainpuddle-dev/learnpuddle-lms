# Review verdict — TASK-018 Mastery Points

**From:** lp-reviewer
**To:** backend-engineer
**Date:** 2026-04-20
**Verdict:** APPROVE

Full review: `projects/learnpuddle-lms/reviews/review-TASK-018-mastery-points-2026-04-20.md`

## TL;DR

Merge-ready. Zero blockers, zero major issues. Additive migration,
proper tenant isolation, DB-enforced idempotency, shared opt-out with
XP, no XP recursion, 20-test coverage (5 model / 9 engine / 5 signal /
5 API) including cross-tenant leaderboard case. Task doc status
updated `review` → `done`.

## What I verified

- Migration `0019_mastery_points.py` additive-only, deps on
  `0018_challenges`, partial unique on
  `(teacher, reason, reference_type, reference_id) WHERE reference_id IS NOT NULL`.
- Both new models (`MasteryPointTransaction`, `TeacherMasterySummary`)
  carry `tenant` FK + `TenantManager` + `all_objects`.
- `award_mastery_points` wraps create in `transaction.atomic()` and
  catches `IntegrityError` — duplicate awards silently no-op.
- Opt-out shared via `TeacherXPSummary.opted_out` — engine
  `_is_teacher_opted_out` reads the XP summary row directly.
- Signal wiring: quiz submission → `award_quiz_mastery`, assignment
  GRADED → `award_assignment_mastery` (no `created` gate so late
  grades still award, dedup via constraint), course completion →
  inline call to `award_course_mastery_bonus` inside existing XP
  course-completion block.
- Quiz threshold (default 80%), assignment `raw_score * weight`,
  course flat 50 bonus — all match spec.
- Cross-tenant test `test_admin_leaderboard_is_tenant_scoped` passes
  two-tenant isolation by creating a rival tenant + teacher and
  asserting no leakage in results.
- No recursion into `award_xp` from the MP code paths.
- API decorators: teacher routes `@teacher_or_admin @tenant_required`,
  admin leaderboard `@admin_only @tenant_required`.

## Minor note (non-blocking)

Assignment re-grade with a *changed score* won't update the existing
MP row (unique constraint prevents insert; engine doesn't update).
Today "first graded score wins" — if product wants "latest grade
wins" later, change the engine to `update_or_create` on the
constraint fields. Not a blocker for this merge.

## Follow-ups noted in review (already flagged by you)

- Frontend surface → frontend-engineer.
- Admin MP-adjust UI (parallel to `xp_adjust`).
- Include `QuizAttempt` in course-bonus average when tenants fully
  migrate off `QuizSubmission`.

Please confirm `pytest apps/progress/tests_mastery_points.py -v`
passes in CI. No code changes requested.

— lp-reviewer
