---
tags: [review, qa-coverage, area/gamification-signals, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-20
---

# Review: QA Coverage — `apps.progress.gamification_signals`

## Verdict: APPROVE (with one follow-up suggestion)

## Summary

A solid, targeted coverage uplift for a previously-untested signal
module. All three `post_save` receivers are exercised end-to-end via
ORM writes, with happy-path, dedup, and short-circuit branches
covered. Cross-tenant isolation uses two genuinely separate tenants.
File is named `tests_gamification_signals.py` so pytest will pick it
up given `pyproject.toml` has `python_files = ["test_*.py",
"tests_*.py", "*_test.py", "tests.py"]` and `testpaths = ["tests",
"apps"]`.

## Checks performed

- **File:** `backend/apps/progress/tests_gamification_signals.py`
  (506 lines, 25 `def test_` methods across 5 `TestCase` classes —
  matches the report).
- **Test discovery:** `pyproject.toml` picks up `tests_*.py` under
  `apps/`, so no renames needed.
- **Receivers exercised:**
    - `on_teacher_progress_save` — content completion (8 tests:
      happy path, summary write, streak bump, non-COMPLETED skip,
      double-save dedup, missing-tenant short-circuit, inactive
      config, opt-out) + course completion (3 tests: full → fires,
      partial → skips, re-save dedup).
    - `on_assignment_submission` (5 tests: SUBMITTED awards, GRADED-on-create
      awards, PENDING skips, re-save dedup via `created=False`,
      streak bump).
    - `on_quiz_submission` (7 tests: completed awards, in-progress
      skips, abandoned timed skips, time-expired-with-nonzero-score
      awards, each attempt gets its own XP, admin re-grade dedups,
      streak bump).
- **Cross-tenant isolation:** 2 tests using `tenant_a` + `tenant_b`
  with their own admin, teacher, course, module, content — no shared
  rows, no shared users. Assertions are on `XPTransaction.all_objects.filter(tenant=...)`
  counts and on `teacher_id` attribution, which is exactly right.
- **Imports:** only production models (`TeacherProgress`,
  `AssignmentSubmission`, `QuizSubmission`, `XPTransaction`,
  `TeacherStreak`, `TeacherXPSummary`, `GamificationConfig`). No
  imports of signals modules or internal helpers — tests rely on the
  real signal wiring from `ProgressConfig.ready()`, which is the
  correct seam.
- **No fixtures leak.** Each class has its own `setUp` with fresh
  tenants; the `_TENANT_COUNTER` generator guarantees subdomain
  uniqueness across classes.

## Critical Issues

None.

## Major Issues

None.

## Minor Issues / Notes

1. **Dedup tests assert XP row count, not inner engine call count.**
   The review brief flagged this specifically: asserting on
   `XPTransaction.filter(...).count() == 1` catches a "final balance"
   regression but would NOT catch a "signal fired twice but dedup inside
   `award_xp` absorbed it" regression. Recommend following up with one
   targeted test that uses `unittest.mock.patch` on
   `gamification_engine.award_xp` (or `XPTransaction.all_objects.create`)
   and asserts `mock.call_count == 1` on the double-save path. For
   the current drop this is a **suggestion, not a blocker**: the
   existing XP-count assertions do protect the observable contract,
   which is what matters at the API level.
2. **`test_inactive_config_skips_xp` depends on the default-config
   auto-creation ordering.** If a future change eagerly creates a
   `GamificationConfig(is_active=True)` on tenant create, the explicit
   `GamificationConfig.objects.create(tenant=..., is_active=False)`
   inside the test will raise on the `unique_together=(tenant,)`
   constraint. Defensive fix: `GamificationConfig.all_objects.update_or_create(tenant=..., defaults={"is_active": False})`.
3. **Quiz "abandoned" assertion** depends on the signal's specific
   heuristic (`time_expired=True AND score == 0`). That's correct for
   today's behaviour — worth a one-line comment pointing to the
   implementation so a reader doesn't have to go digging.
4. **No explicit streak-dedup assertion** (streak incremented once
   per day regardless of XP source). Nice-to-have; not a correctness
   gap.

## Positive Observations

- 25 tests is the right dose — enough to pin each branch, not so many
  that maintenance cost balloons.
- Each class uses its own tenant factory instance; no shared state
  between classes.
- The "missing tenant" short-circuit test is especially valuable —
  easy to regress when someone adds a new `@tenant_required`-style
  check inside the signal handler.
- Cross-tenant test asserts both row count **and** `teacher_id`
  attribution — catches a different bug than a pure count check
  would.
- Claim `.save()` on a row to retrigger `post_save` (rather than
  calling the handler directly) is the correct way to test signal
  code — it verifies wiring + handler together.
- No production-code imports from sibling test modules.

## Test plan

- `docker compose exec web pytest apps/progress/tests_gamification_signals.py -v`
- Follow-up (optional): add one `mock.patch` test on `award_xp`
  call count for the double-save dedup path.

---
Reviewed by: lp-reviewer
