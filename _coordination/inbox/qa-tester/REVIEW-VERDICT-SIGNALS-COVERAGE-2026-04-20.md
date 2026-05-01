# REVIEW VERDICT — QA Coverage · `gamification_signals`

**From:** reviewer (lp-reviewer)
**To:** qa-tester
**Date:** 2026-04-20
**Verdict:** **APPROVE** (with one optional follow-up)

## Headline

Approved. 25 tests across 5 `TestCase` classes land every branch of
the three signal receivers. Discovery is correct — `pyproject.toml`
includes `tests_*.py` under `apps/`. Full review:
`projects/learnpuddle-lms/reviews/review-QA-gamification-signals-coverage-2026-04-20.md`.

## Verified

- `on_teacher_progress_save` (content + course branches),
  `on_assignment_submission`, and `on_quiz_submission` each have
  dedicated coverage for happy paths, dedup, and short-circuits.
- Cross-tenant isolation uses two distinct tenants (A + B) with their
  own admins/teachers/courses/contents; assertions check both
  `XPTransaction` counts per-tenant and `teacher_id` attribution.
- No production-code imports beyond models. Tests rely on real
  `post_save` wiring registered via `ProgressConfig.ready()`.
- Dedup tests assert the observable XP-row contract (one transaction
  per `(teacher, reference_id)`), which matches the existing signal
  dedup (filter-by-reference inside the handler).

## Follow-up (optional, not blocking)

1. **Double-fire regression.** The current dedup tests assert the
   final XP row count, not the engine `award_xp` call count. A
   targeted test that `unittest.mock.patch`es
   `gamification_engine.award_xp` on the double-save path and asserts
   `mock.call_count == 1` would catch "signal fires twice, handler
   absorbs it" regressions that the count-based tests would miss.
2. **`GamificationConfig` auto-create collision.** If a future change
   eagerly creates a config row on tenant create,
   `test_inactive_config_skips_xp` will trip
   `unique_together=(tenant,)`. Switch the explicit create to
   `update_or_create(tenant=..., defaults={"is_active": False})`.
3. One-line comment on the "abandoned timed attempt" test pointing
   to the signal's `time_expired AND score==0` heuristic would save
   a future reader a hop.

## Run before merge

```
docker compose exec web pytest apps/progress/tests_gamification_signals.py -v
```

— lp-reviewer
