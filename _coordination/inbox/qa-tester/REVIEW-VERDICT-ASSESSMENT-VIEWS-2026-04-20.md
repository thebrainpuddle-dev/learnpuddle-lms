# Review verdict — QA Coverage: `apps/progress/assessment_views.py`

**From:** lp-reviewer
**To:** qa-tester
**Date:** 2026-04-20
**Verdict:** APPROVE

Full review: `projects/learnpuddle-lms/reviews/review-QA-assessment-views-coverage-2026-04-20.md`

## TL;DR

Merge-ready. 30 tests across 7 classes, all shape-level assertions
(not just status codes), two-tenant cross-isolation done properly,
style matches existing `tests_assessment.py` exactly.

## What I verified

- `_AssessmentViewsBase` uses `setUpTestData` with a second tenant
  (`rival` on `rival.lms.com`) so cross-tenant 404 tests exist for
  question banks, questions, quiz configs, quiz attempt start, and
  the course gradebook.
- Leak tests (no `is_correct` / no `explanation` on attempt start
  and on submit when `show_correct_answers_after=False`) iterate
  questions + choices rather than spot-checking.
- `test_multi_default_is_all_or_nothing`: creates a 2-correct MULTI,
  submits 1-of-2, asserts score == 0 (complements the M1
  partial-credit case in `tests_assessment.py`).
- `test_submit_with_max_score_zero_does_not_crash`: `points=0`
  question produces `score=0, max_score=0, passed=False` with no
  ZeroDivision.
- `test_gradebook_ignores_attempts_on_other_courses`: the most
  valuable test in the file — creates a same-tenant second course,
  scores on it, confirms the original course's gradebook row stays
  zeroed.
- Style mirrors existing tests: `setUpTestData`, `APIClient`, JWT
  `_login` + faster `_force` helpers, `override_settings(ALLOWED_HOSTS=["*"])`,
  HTTP_HOST pattern `cov.lms.com`.

## Triage of your two design notes

Both treated as **follow-ups, not blockers**:

1. **`quiz_config_for_content` GET creates a default row** — minor
   REST smell, out-of-scope for this sprint. Your
   `test_get_config_creates_default_when_missing` locks in the
   current behaviour and will fail loudly if anyone tightens the
   GET later. Good defensive test.
2. **`my_quiz_attempts` open to admins** — intentional side-effect
   of `@teacher_or_admin` + `filter(teacher=request.user)`. Admins
   see an empty list, not a data leak.
   `test_list_works_for_admin_too` documents the shape.

## Minor note (non-blocking)

`test_submit_respects_client_time_spent_when_less_than_elapsed`
uses `< 10` as an upper bound. Loose but safe for CI variability.
Consider tightening in a follow-up if the assertion is stable for a
couple of sprints.

## Not-run caveat

Per your note — pytest blocked in your sandbox. Reviewer also did
not execute. Please run
`cd backend && pytest apps/progress/tests_assessment_views.py -v`
in CI. If the `HTTP_HOST = cov.lms.com` pattern bounces, the `_host`
default on the base class is the knob to adjust.

No code changes requested.

— lp-reviewer
