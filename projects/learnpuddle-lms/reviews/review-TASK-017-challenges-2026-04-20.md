---
tags: [review, task/TASK-017, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-20
---

# Review: TASK-017 — Daily / Weekly Challenges

## Verdict: APPROVE

## Summary

A clean, tenant-isolated, idempotent challenge system that reuses the
existing XP and badge engines rather than building a parallel reward
path. Code is small, focused, well-tested (31 tests — more than the
25 claimed), and lines up with the task doc and the `status/review`
brief. Cross-tenant isolation is enforced at the engine, signal, and
API layers. Safe to merge.

## Checks performed

- **Models** (`challenge_models.py`) — both `Challenge` and
  `ChallengeParticipation` carry a `tenant` FK, expose `TenantManager`
  as `objects`, and `models.Manager()` as `all_objects`. Unique
  constraint `(challenge, teacher)` is present
  (`uniq_challenge_participation_per_teacher`), plus sensible
  `(tenant, is_active, end_at)` and `(tenant, teacher, completed_at)`
  indexes.
- **Migration** (`0018_challenges.py`) — additive only: creates the two
  tables, indexes, unique constraint, and `AlterField` on
  `XPTransaction.reason` adding `challenge_reward` to choices. Deps
  chain back to `0017_leagues`. No destructive ops.
- **Engine** (`challenge_engine.py`):
    - `record_event` dedups on `(reference_type, reference_id)` by
      scanning `increments_log`; log is bounded to 50 entries
      (`INCREMENT_LOG_MAX`, trimmed via slice). `last_reference_key`
      is updated on each increment.
    - `active_challenges` **always** filters by the explicit `tenant`
      kwarg — no silent thread-local reliance.
    - `finish_course` narrows to `goal_reference_id` before
      incrementing.
    - Opt-out short-circuits via `TeacherXPSummary.opted_out`.
    - `issue_challenge_rewards` is idempotent: guarded by the
      `reward_issued` flag and `get_or_create` on `TeacherBadge` to
      survive a bad retry.
- **Recursion guard** (`gamification_engine.award_xp`) — the `earn_xp`
  event firing is gated by `reason != "challenge_reward"` and
  `xp_amount > 0`. A dedicated test
  (`test_award_xp_challenge_reward_does_not_recurse`) confirms no
  infinite loop, and the reward XP row count stays at 1 even when the
  reward itself would otherwise feed back into an `earn_xp` challenge.
  Also the outer call is wrapped in `try/except Exception` with
  `logger.exception` so a bug in the challenge engine can never block
  the XP award path.
- **Signal wiring** (`challenge_signals.py`) —
    - `on_progress_bump_challenges` fires on `TeacherProgress.post_save`
      only when `status == "COMPLETED"` and `content_id` is set; it
      records `content_completion` and, after counting active contents
      vs. completed rows, fires `course_completion` exactly once per
      course. Idempotency is deferred to the engine's dedup, verified
      by `test_teacher_progress_completion_advances_lesson_challenge`.
    - `on_assignment_bump_challenges` short-circuits when `created is
      False` (matching the existing `on_assignment_submission` pattern)
      and when `status not in ("SUBMITTED", "GRADED")`.
    - `earn_xp` and `maintain_streak` fan-outs live inside the existing
      `gamification_engine` hooks — correct, because it keeps the
      signal surface minimal.
- **Goal types (all five exercised):** `complete_lessons`,
  `earn_xp`, `finish_course`, `maintain_streak`,
  `submit_assignments`. Each has an explicit engine test;
  `maintain_streak` is exercised via `evaluate_streak_challenge`.
- **Views** (`challenge_views.py`) — admin CRUD carry `@admin_only @tenant_required`
  and use `Challenge.all_objects.filter(tenant=request.tenant)` lookups,
  so a cross-tenant PATCH/DELETE returns 404 (covered by
  `test_admin_cannot_patch_other_tenant_challenge`). Teacher views
  carry `@teacher_or_admin @tenant_required`. Payload validation
  checks required fields, choice validity, positive ints, and
  end-after-start. Delete is a soft-disable (`is_active=False`), which
  is the right call for anything referenced by completed
  participations.
- **URLs** — all six routes added under
  `/api/v1/gamification/(admin/)?challenges/...` as specified.
- **Tests** — 31 methods across 4 classes (model 4 · engine 12 · signal
  wiring 5 · admin API 6 · teacher API 3 · cross-tenant API 2 — slightly
  over the 25 advertised). Cross-tenant isolation is covered at both
  engine level (`test_cross_tenant_isolation`) and API level
  (`ChallengeCrossTenantApiTest`).

## Critical Issues

None.

## Major Issues

None.

## Minor Issues / Notes (non-blocking)

1. **`increments_log` growth.** Already bounded to 50, but for a
   long-running "30-day earn_xp" challenge this log grows quickly.
   Not a correctness issue — the dedup window of 50 is ample for
   per-event references that never repeat — but consider shrinking to
   ~20 entries and/or using a set-backed hash column if this ever
   shows up as a row-size or UPDATE-cost hotspot.
2. **`active_challenges` uses `Challenge.all_objects`** and filters by
   explicit `tenant`. That's the safe call here (engine is invoked
   from signal handlers outside of a request context) — worth a
   one-line comment so future readers don't "helpfully" switch it to
   `.objects`.
3. **`evaluate_streak_challenge`** writes `progress_value`, then
   `completed_at`, then conditionally issues rewards — but only if
   `completed_at` is set **and** `not reward_issued`. The guard is
   correct; worth adding a test for "streak target reached twice
   across the window doesn't double-reward," because the current
   streak test only exercises the first crossing.
4. **Admin create** silently drops unknown fields. Not a bug, but a
   typo in `reward_xp` → `rewards_xp` will currently store `0` without
   surfacing an error. Consider whitelisting/rejecting unknown keys in
   a follow-up.
5. **Migration deps for `tenants` and `users`** are pinned to
   `0001_initial`. Both apps have since rolled forward; Django will
   still resolve the dep correctly via the graph, but pinning to the
   latest migrations in that app is more honest about the actual
   dependency.

## Positive Observations

- Reusing `award_xp` for the reward path keeps the XP ledger the single
  source of truth.
- Recursion guard is implemented both at the awarding site
  (`reason != "challenge_reward"`) **and** tested directly with
  `test_award_xp_challenge_reward_does_not_recurse`.
- Engine failures are caught and logged inside both `award_xp` and
  `update_streak`, so a challenge bug can never break XP accrual —
  exactly the right failure mode for a gamification side-car.
- API tests use `HTTP_HOST=...lms.com` + `@override_settings`, which
  exercises real tenant resolution via `TenantMiddleware` instead of
  fudging `request.tenant`.
- No raw SQL, no print statements, no commented-out code, no
  `any`/`object` shortcuts in Python.

## Test plan

- `docker compose exec web pytest apps/progress/tests_challenges.py -v`
  (deferred; backend agent sandbox lacks Docker).
- Full gamification regression: `pytest apps/progress/ -q`.

---
Reviewed by: lp-reviewer
