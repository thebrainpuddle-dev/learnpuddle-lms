---
tags: [review, qa-coverage, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-20
---

# Review: QA Coverage — `apps/progress/assessment_views.py`

## Verdict: APPROVE

## Summary

A well-scoped gap-fill of 30 tests across 7 classes that fills the
view-layer branches `tests_assessment.py` did not exercise (bank /
question CRUD, quiz-config GET, start-edge cases, submit edge cases,
list isolation, gradebook cross-tenant). Style mirrors the existing
`tests_assessment.py` / `tests_quiz_api.py` pattern (`TestCase` +
`APIClient` + JWT login / `force_authenticate`, `setUpTestData`
fixtures on a shared base class). Shape-level assertions (no
`is_correct` / `explanation` leakage, 0 for partial MULTI, 0/0 safe
for `max_score=0`) go beyond "2xx" smoke tests and actually defend
the behaviour. Merge-ready.

## Critical Issues

None.

## Major Issues

None.

## Minor Issues

- `test_list_works_for_admin_too` asserts the admin sees `0` rows.
  This is a shape test of the *current* `@teacher_or_admin` + `filter(teacher=request.user)`
  combo. If a future refactor limits `/api/v1/teacher/quiz-attempts/`
  to `TEACHER`-only, this test will need re-scoping. Not a problem
  today; QA flagged it themselves.
- `test_get_config_creates_default_when_missing` locks in the
  read-mutates-DB smell on `quiz_config_for_content`. Fine as a
  characterization test; if the team later tightens the endpoint to
  `GET` read-only, this assertion flips. QA flagged the design note.
- `test_submit_respects_client_time_spent_when_less_than_elapsed`
  asserts `time_spent_seconds < 10`. That's a loose bound —
  appropriate for CI variability. Consider tightening to `<= 1` in a
  follow-up if the assertion proves stable.

## Positive Observations

- **Base class reuse.** `_AssessmentViewsBase` with `setUpTestData`
  (class-level) keeps each test class small and eliminates per-test
  tenant/user setup cost. Matches the existing pattern in
  `tests_assessment.py`.
- **Cross-tenant isolation.** `cls.tenant` (`cov`) + `cls.other_tenant`
  (`rival`) with distinct subdomains — correct realistic two-tenant
  setup. Cross-tenant 404 tests exist for question banks, questions,
  quiz config, quiz attempt start, and course gradebook. Each uses
  the caller's own tenant host (`cov.lms.com`) and targets the other
  tenant's object ID → asserts 404 (not 403). Matches the
  `get_object_or_404(tenant=request.tenant)` pattern used by the
  views.
- **Shape assertions not just status codes.**
  - `test_start_response_never_leaks_is_correct_or_explanation`
    iterates questions/choices and asserts neither key appears. Real
    defense against serializer leakage.
  - `test_submit_strips_is_correct_when_config_disables_reveal`
    mirrors the above for the submit response under
    `show_correct_answers_after=False`.
  - `test_multi_default_is_all_or_nothing` builds a 2-correct MULTI,
    submits one of the two, asserts `score == 0.0` — correctly
    complements the M1 partial-credit test in `tests_assessment.py`.
  - `test_submit_with_max_score_zero_does_not_crash` verifies
    `max_score=0 → score=0, max_score=0, passed=False` (no
    ZeroDivision).
- **Auth coverage.** `test_teacher_cannot_create_bank_or_question`,
  `test_teacher_cannot_access_gradebook`, `test_cross_tenant_bank_returns_404`,
  `test_cross_tenant_question_returns_404` — the RBAC matrix is
  exercised at the endpoint edge, not just via decorator unit tests.
- **Random selection math.** `test_start_random_count_uses_exact_number`
  (`random_selection_count=2` → 2 questions) and
  `test_start_random_count_larger_than_bank_uses_all_questions`
  (`=50` → clamped to 1 available) cover both branches of the `min()`.
- **Gradebook scoping.** `test_gradebook_ignores_attempts_on_other_courses`
  creates a second same-tenant course, runs a passing attempt there,
  and asserts the original course's aggregates still read 0. This is
  the single most valuable test in the new file because that scoping
  bug (content → module → course) is easy to regress.
- **Config GET implicit create** — `test_get_config_creates_default_when_missing`
  is a characterization test for known current behaviour and will
  fail loudly the day someone makes GET read-only, which is the
  correct signal.
- **Header / middleware compatibility.** `HTTP_HOST = "cov.lms.com"`
  matches the `TenantMiddleware` subdomain extraction in
  `utils/tenant_middleware.py` — same pattern as the existing test
  suite. `ALLOWED_HOSTS=["*"]` via `override_settings` on the base.

## Requirements cross-check

| Requirement | Status |
|------------|--------|
| Style mirrors existing (`APIClient`, JWT login, `setUpTestData`) | ✅ |
| Cross-tenant tests create two tenants with distinct subdomains | ✅ |
| Response-shape assertions (no `is_correct` leak on start) | ✅ |
| `show_answers=False` truly asserts key redaction | ✅ |
| MULTI all-or-nothing: 0 on partial, full on complete | ✅ (partial only; full-match coverage already in `tests_assessment.py` via M1) |
| Two qa design notes triaged (GET mutates, teacher-list admin-open) | ✅ treated as follow-ups, not blockers |

## Triage of author-flagged design notes

1. **`quiz_config_for_content` GET creates a default row** — minor
   REST smell. Agree with QA; not a bug, triaged as a follow-up if
   the team ever prefers a strict read-only GET. Current
   characterization test holds the behaviour in place.
2. **`my_quiz_attempts` open to admins** — intentional side-effect
   of `@teacher_or_admin` + `filter(teacher=request.user)`. Admins
   see an empty list. Not a leak, not a bug; coverage in
   `test_list_works_for_admin_too` documents it.

Neither note is a blocker.

## Files reviewed

- `backend/apps/progress/tests_assessment_views.py` (835 lines, 30
  tests, 7 test classes)
- Cross-referenced `backend/apps/progress/assessment_views.py`,
  `backend/apps/progress/tests_assessment.py`, and
  `backend/apps/progress/tests_quiz_attempts.py` for style/coverage
  parity.

## Not-run caveat

Per QA: pytest blocked in their sandbox. Reviewer did not run tests
either (no exec). Please run
`pytest apps/progress/tests_assessment_views.py -v` in CI and report
back if anything fails. Most likely failure mode would be HTTP_HOST
(`cov.lms.com`) not resolving against the local tenant middleware
config in the CI container — trivially fixable by adjusting the
`_host` helper default.
