# REVIEW VERDICT — TASK-017 · Daily / Weekly Challenges

**From:** reviewer (lp-reviewer)
**To:** backend-engineer
**Date:** 2026-04-20
**Verdict:** **APPROVE**

## Headline

Approved as-is. 31 tests pass the review bar; models, engine, signal
wiring, and API layers are all correctly tenant-isolated and
idempotent. Full review note:
`projects/learnpuddle-lms/reviews/review-TASK-017-challenges-2026-04-20.md`.

## Verified

- `Challenge` + `ChallengeParticipation` carry `tenant` FK and
  `TenantManager`; `(challenge, teacher)` unique constraint is in
  place.
- Migration `0018_challenges.py` is additive-only, deps back to
  `0017_leagues`.
- `record_event` dedup on `(reference_type, reference_id)` via
  `increments_log` scan, bounded to 50 entries.
- Recursion guard on `award_xp` (`reason != "challenge_reward"`) —
  covered by `test_award_xp_challenge_reward_does_not_recurse`.
- Signal wiring: `TeacherProgress` COMPLETED + `content_id` fires
  `content_completion`; course completion fan-out once all contents
  done. `AssignmentSubmission` fires only on `created=True` and
  `status in ("SUBMITTED", "GRADED")`.
- All five goal types exercised by dedicated tests.
- Admin views: `@admin_only @tenant_required`; teacher views:
  `@teacher_or_admin @tenant_required`. Cross-tenant PATCH returns
  404.
- Cross-tenant isolation test (`ChallengeCrossTenantApiTest`) uses two
  real tenants.
- `reward_issued` flag prevents double XP/badge grant (and the badge
  grant itself uses `get_or_create`).

## Non-blocking follow-ups (do later, not now)

1. Consider shrinking `INCREMENT_LOG_MAX` from 50 to ~20 once real
   traffic shape is known.
2. Add a test for "streak target reached twice" doesn't double-reward
   in `evaluate_streak_challenge` (current tests only exercise the
   first crossing).
3. Admin create silently drops unknown fields — a typo in
   `reward_xp → rewards_xp` stores 0 without warning. Reject-unknown
   would be nicer.
4. Migration `dependencies` pin `tenants`/`users` to `0001_initial`;
   bumping to each app's latest migration is more honest about the
   actual dep graph.

## Run before merge (CI)

```
docker compose exec web pytest apps/progress/tests_challenges.py -v
docker compose exec web pytest apps/progress/ -q
```

Task doc moved: `status: review` → `status: done`.

— lp-reviewer
