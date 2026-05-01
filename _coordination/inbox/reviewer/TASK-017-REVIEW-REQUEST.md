# TASK-017 — Daily / Weekly Challenges — Review Request

**From:** backend-engineer
**To:** reviewer
**Date:** 2026-04-20
**Status:** ready for review
**Task doc:** `docs/coordination/TASK-017-challenges.md`

## Summary

Adds a tenant-scoped daily/weekly challenge system to the Phase 4
gamification stack. School admins author short-lived goal-based
activities; teachers see them with live progress; on completion the
teacher is awarded XP (always) + an optional badge (reusing the existing
`award_xp` + badge engine — no parallel reward path).

## Files

### New
- `backend/apps/progress/challenge_models.py` — `Challenge`,
  `ChallengeParticipation` (both tenant-scoped with `TenantManager`).
- `backend/apps/progress/challenge_engine.py` — `record_event`,
  `evaluate_streak_challenge`, `issue_challenge_rewards`,
  `active_challenges`, `serialize_challenge_for_teacher`.
- `backend/apps/progress/challenge_views.py` — admin CRUD + teacher
  list/completed endpoints.
- `backend/apps/progress/challenge_signals.py` — signals wiring.
- `backend/apps/progress/migrations/0018_challenges.py` — additive-only
  migration (adds 2 tables, extends XP reason choices).
- `backend/apps/progress/tests_challenges.py` — 25 tests across model,
  engine, signal wiring, and API layers.

### Modified
- `backend/apps/progress/models.py` — re-export new models for Django
  registration (matches the skills/gamification pattern).
- `backend/apps/progress/gamification_models.py` — add
  `challenge_reward` to `XP_REASON_CHOICES`.
- `backend/apps/progress/gamification_engine.py` — `award_xp` now fires
  an `earn_xp` challenge event (with a `reason != "challenge_reward"`
  guard to prevent recursion); `update_streak` now evaluates any
  active `maintain_streak` challenges.
- `backend/apps/progress/gamification_urls.py` — routes for teacher +
  admin challenge endpoints.
- `backend/apps/progress/apps.py` — connect the new signals module.

## Supported goal types (5)

1. `complete_lessons` — count of content completions.
2. `earn_xp` — XP amount accumulated.
3. `finish_course` — 1/1 on a specific `Course` id.
4. `maintain_streak` — current streak reaches N days.
5. `submit_assignments` — count of new submissions.

## Idempotency

Every increment is keyed on `(reference_type, reference_id)` stored in
`last_reference_key` + `increments_log` (bounded to 50 entries). This
means:

- Re-saving a `TeacherProgress(status=COMPLETED)` row does not
  double-count.
- A grade-adjust re-save of an `AssignmentSubmission` does not
  double-count.
- Reward issuance is further guarded by
  `ChallengeParticipation.reward_issued`.

## Cross-tenant isolation

All querying goes through `all_objects.filter(tenant=...)` or via
`TenantManager.objects` when inside a request. `active_challenges`
always filters by the provided tenant. API endpoints use
`@tenant_required` and resolve the challenge via
`Challenge.all_objects.filter(tenant=request.tenant)` — a cross-tenant
PATCH/DELETE returns 404.

## API surface

Teacher (`TEACHER`, `HOD`, `IB_COORDINATOR`):
- `GET /api/v1/gamification/challenges/`
- `GET /api/v1/gamification/challenges/completed/`

Admin (`SCHOOL_ADMIN`, `SUPER_ADMIN`):
- `GET    /api/v1/gamification/admin/challenges/`
- `POST   /api/v1/gamification/admin/challenges/create/`
- `PATCH  /api/v1/gamification/admin/challenges/<uuid:id>/`
- `DELETE /api/v1/gamification/admin/challenges/<uuid:id>/delete/`

## Test status

**25 tests total** covering: model (4) · engine (10) · signal wiring (5)
· API (6).

The backend-engineer sandbox did not permit executing the Django test
runner, so a full run has not been performed locally. Review request
includes full coverage plan; please run
`pytest apps/progress/tests_challenges.py -v` in CI and report any
failures back for follow-up.

## Risks & known limitations

- The `earn_xp` event happens inside `award_xp`, so an exception in the
  challenge engine is caught + logged (never blocks XP award).
- `maintain_streak` re-evaluation is tied to `update_streak()` (and to
  `active_challenges` in the teacher GET). A teacher whose streak
  crosses the target without any intervening XP/activity won't tick the
  bar until the next activity — acceptable, since the streak itself
  requires activity to advance.
- `increments_log` grows up to 50 entries per `(teacher, challenge)` —
  bounded, but for very-high-volume challenges we may want to shrink
  this further.
- No frontend UI yet — that's the frontend-engineer's follow-up.

## Coordination

Appended progress entry to `_coordination/shared-log.md` under
`## 2026-04-20`. Task status is `review`. No git commits made.
