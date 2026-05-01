---
tags: [review, task/TASK-018, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-20
---

# Review: TASK-018 — Mastery Points

## Verdict: APPROVE

## Summary

A clean, additive, tenant-isolated second-currency implementation.
Two new models (`MasteryPointTransaction` + `TeacherMasterySummary`)
sit beside the existing XP ledger without coupling. Idempotency is
enforced at the database layer via a partial unique index and mirrored
in the engine with `transaction.atomic()` + `IntegrityError` catch.
Opt-out is correctly shared with XP through
`TeacherXPSummary.opted_out`. 20 TDD tests cover models, engine,
signal wiring (including re-save dedup), and API with a cross-tenant
leaderboard case. Safe to merge.

## Critical Issues

None.

## Major Issues

None.

## Minor Issues

- `on_assignment_submission_mastery` fires on every save while
  `status == 'GRADED'` (no `created` guard). This is *intentional* —
  re-grades are meant to re-evaluate — and idempotency via the unique
  constraint absorbs the re-fire. Worth a comment: a re-grade with a
  **changed score** does not update the existing MP row because the
  unique key is `(teacher, reason, reference_type, reference_id)`.
  In practice that's acceptable (first graded score wins), but if the
  product later wants "latest grade wins" the engine will need to
  update-or-create. Not blocking — flag for product.
- `mp_quiz_weight` / `mp_assignment_weight` use `DecimalField(max_digits=5, decimal_places=2)`.
  `mp_quiz_weight * score_percent (100) = 500.00` fits — but if an
  admin ever sets a weight > 999.99 the migration's `max_digits=5`
  (1 integer digit + 2 dp after `.00`) would be too tight. With
  `decimal_places=2` and `max_digits=5`, the effective integer budget
  is 3 digits, so weights up to 999.99 work. No action required, just
  for future tuning awareness.
- `get_mastery_summary` uses `TeacherMasterySummary.all_objects` and
  passes `tenant` into defaults. Callers are always the teacher
  themselves (via `@teacher_or_admin @tenant_required`), so tenant is
  correct. Nothing to change.

## Positive Observations

- **Migration `0019_mastery_points.py`** is strictly additive: 5
  `AddField` on `gamificationconfig`, 2 `CreateModel`, 5 indexes, 1
  partial unique constraint. Dependencies chain to `0018_challenges`
  and the existing `tenants`/`users` initial migrations — zero-downtime
  deploy.
- Partial unique constraint `uniq_mp_txn_per_reference` with
  `Q(reference_id__isnull=False)` is exactly right — admin
  adjustments (`reference_id=NULL`) can legitimately repeat while
  auto-awards are deduped.
- Both new models carry `tenant` FK + `objects = TenantManager()` +
  `all_objects = models.Manager()`. Sensible composite indexes:
  `(tenant, teacher)`, `(tenant, teacher, reason)`,
  `(tenant, total_mastery_points)` for leaderboard ordering.
- Engine `award_mastery_points` is defensive: missing tenant,
  inactive config, opted-out teacher, zero/negative auto-amount all
  return `None` without raising. The `admin_adjust` exemption for
  negative amounts is preserved.
- **No XP recursion.** The MP path calls only MP helpers; it never
  re-enters `award_xp`. Verified by reading `mastery_engine.py` and
  the signal module end-to-end.
- Signal wiring:
  - Quiz — `on_quiz_submission` awards XP then calls
    `award_quiz_mastery(instance)` inside a broad `except` so an MP
    failure cannot break the XP path.
  - Assignment — separate `on_assignment_submission_mastery` handler
    fires on `status == 'GRADED'` (no `created` gate) so late grades
    award MP; idempotency handles re-saves.
  - Course — `award_course_mastery_bonus(teacher, course)` is called
    *inline* inside the existing course-completion XP block, guarded
    by a try/except. No separate receiver, no duplicate firing.
- Quiz threshold (default 80%) and formula `round(score_percent *
  weight)` match the spec table in the task doc. Assignment uses
  `raw_score * weight` which correctly scales with `max_score` (a
  higher-stakes rubric pays more MP) — also matches the spec.
- Course bonus formula: iterates submissions, averages per-submission
  percentages (not a single `Avg('score')` which would ignore
  variable `max_score`). Guards `max_score <= 0`.
- API views use `@teacher_or_admin @tenant_required` for teacher
  routes and `@admin_only @tenant_required` for leaderboard — matches
  the codebase convention. Leaderboard uses `select_related('teacher')`
  and `[:limit]` with `max(1, min(limit, 200))` clamping.
- `refresh_from_transactions()` clamps totals at zero display-floor
  so admin negative adjustments don't render as `-5.00 MP` in the UI
  while the raw ledger still keeps the signed entry.
- Tests:
  - 5 model tests include the DB-level unique-constraint guard and
    decimal precision round-trip.
  - 9 engine tests cover threshold, weight, opt-out, inactive config,
    course-bonus average math, and cross-tenant summary scoping.
  - 5 signal tests verify quiz ≥ threshold awards MP, below threshold
    skips, re-save does not double-award, assignment GRADED awards,
    course completion triggers bonus.
  - 5 API tests cover happy paths plus a **cross-tenant leaderboard
    isolation** case that creates a second tenant and asserts no
    leakage — meets the brief.
- `teacher_mastery_history` paginates (`page_size=25` via
  `make_pagination_class`) — no unbounded queryset.
- `gamification_serializers.py` adds three focused serializers with
  `read_only_fields` on the summary; no field leakage.

## Requirements cross-check

| Requirement | Status |
|------------|--------|
| New `MasteryPointTransaction` model | ✅ |
| New `TeacherMasterySummary` (separate from `TeacherXPSummary`) | ✅ |
| Opt-out shared with XP (`TeacherXPSummary.opted_out`) | ✅ (`_is_teacher_opted_out` reads the XP summary row) |
| Migration additive-only, deps to `0018_challenges` | ✅ |
| Partial unique index on `(teacher, reason, reference_type, reference_id)` where `reference_id IS NOT NULL` | ✅ |
| Both models carry `tenant` FK + `TenantManager` | ✅ |
| Engine idempotent (`IntegrityError` inside `transaction.atomic`) | ✅ |
| Quiz threshold ≥ 80% respected | ✅ (default, configurable) |
| Assignment uses raw_score * weight | ✅ |
| Course bonus flat = 50 when avg quiz ≥ 80% | ✅ |
| Signal hooks: quiz submission, assignment `created=True OR GRADED`, course completion inline | ✅ |
| Opt-out tested | ✅ (`test_opt_out_blocks_award`) |
| Cross-tenant test | ✅ (`test_admin_leaderboard_is_tenant_scoped`, `test_tenant_manager_isolates_transactions`, `test_get_mastery_summary_is_tenant_scoped`) |
| No XP recursion | ✅ (confirmed by code inspection) |
| API endpoints with correct decorators | ✅ |

## Files reviewed

- `backend/apps/progress/migrations/0019_mastery_points.py`
- `backend/apps/progress/gamification_models.py` (choices + 5 config
  fields + `MasteryPointTransaction` + `TeacherMasterySummary`)
- `backend/apps/progress/gamification_serializers.py`
- `backend/apps/progress/gamification_urls.py`
- `backend/apps/progress/gamification_signals.py`
- `backend/apps/progress/models.py` (model re-export)
- `backend/apps/progress/mastery_engine.py`
- `backend/apps/progress/mastery_views.py`
- `backend/apps/progress/tests_mastery_points.py` (20 tests)

## Follow-ups (non-blocking, as noted by author)

- Frontend surface (frontend-engineer).
- Admin manual MP adjust UI (parallel to `xp_adjust`).
- Include `QuizAttempt` (assessment_models) in course-bonus average
  once the tenant migrates off legacy `QuizSubmission`.
