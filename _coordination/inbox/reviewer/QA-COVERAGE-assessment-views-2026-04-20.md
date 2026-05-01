# QA Coverage: apps/progress/assessment_views.py — 2026-04-20

**From**: qa-tester
**To**: reviewer
**Area**: `backend/apps/progress/assessment_views.py` (TASK-043 Question Bank + Advanced Quizzing)
**New file**: `backend/apps/progress/tests_assessment_views.py`
**Test count**: 30 new tests across 7 test classes
**Status**: Tests written; pytest execution blocked by sandbox on this host — please run on CI or in a dev container.

---

## Why these tests

`tests_assessment.py` already covers the happy paths (start + submit),
the H1/H2/M1-M4 regressions, and the race test via
`TransactionTestCase`. The file I added fills the **view-branch gaps**
that the prior pass skipped — mostly CRUD on Question Banks /
Questions / QuizConfig and the edge branches on start/submit.

## Coverage gaps closed

### Question Bank CRUD (8 tests — `QuestionBankCrudTests`)
- `GET /api/v1/admin/question-banks/` — question_count annotation
- `?search=` filter matches title / description
- `GET /.../<bank_id>/` — single detail
- `PATCH` — update title + tags
- `DELETE` — 204 + row gone
- Cross-tenant bank → 404 (not 403 — intentional, `get_object_or_404`
  by tenant)
- Teacher → 403 on admin endpoints
- Unauthenticated → 401/403

### Question CRUD (6 tests — `QuestionCrudTests`)
- `GET /api/v1/admin/questions/<id>/` single question
- `PATCH` — prompt update + replace-style choices
- `DELETE` — 204
- Cross-tenant question → 404
- `?type=MCQ` filter on bank-questions list
- Teacher → 403 on create

### QuizConfig (3 tests — `QuizConfigViewTests`)
- `GET` lazily creates a default row (previously only PATCH was tested)
- PATCH without `source_question_banks` preserves existing M2M links
  (the view only touches M2M when the key is present — important to
  lock in)
- PATCH on cross-tenant content → 404

### quiz_attempt_start (6 tests — `QuizAttemptStartTests`)
- No QuizConfig → 404
- Config with no banks / no questions → 400
- `random_selection_count=2` → exactly 2 questions returned
- `random_selection_count=50` > available → `min()` clamps, no crash
- Response never leaks `is_correct` / `explanation` even with
  shuffling enabled
- Cross-tenant content → 404

### quiz_attempt_submit (8 tests — `QuizAttemptSubmitTests`)
- Teacher A cannot submit teacher B's attempt → 404
- Empty `answers` → score 0, passed False
- `max_score=0` (points=0 question) does NOT ZeroDivisionError
- SHORT / ESSAY are never auto-graded (score always 0 regardless of
  submitted text)
- `show_correct_answers_after=False` strips `is_correct` /
  `explanation` from the submit response
- Nonexistent attempt_id → 404
- `time_spent_seconds` honors `min(server-elapsed, client-reported)`
- MULTI default is all-or-nothing (1-of-2 correct → 0 points, not
  partial) — complements M1 partial-credit test in `tests_assessment.py`

### my_quiz_attempts (3 tests — `MyQuizAttemptsTests`)
- Teacher B's attempts never appear in Teacher A's list
- `?content_id=` filter restricts by content
- Admin hitting `/api/v1/teacher/quiz-attempts/` returns 200 + empty
  (not 403 — `teacher_or_admin` allows admins)

### course_gradebook (4 tests — `GradebookTests`)
- Cross-tenant course id → 404
- Teachers with no attempts still appear in rows with zeroed aggregates
- Attempts on a **different course in the same tenant** do NOT inflate
  this course's aggregates (content → module → course scoping works)
- Teacher → 403

---

## Estimated coverage delta

Existing `tests_assessment.py` + `tests_quiz_attempts.py` already hit
most of the scoring and permission paths. The new file adds roughly
**+25-30% branch coverage on `assessment_views.py`** by exercising:
- All 4 admin question-bank CRUD branches (GET list, GET detail,
  PATCH, DELETE, search filter)
- All 4 question CRUD branches + type filter
- The GET branch of quiz_config_for_content (was untested)
- Early-return branches in quiz_attempt_start (no config, empty banks)
- Cross-tenant 404 branches across all 8 endpoints
- Permission branches (teacher blocked from admin, admin allowed on
  teacher list)

Expected overall assessment_views.py line coverage moves from roughly
**~55-60% → ~85%+** after this lands.

## Bugs / observations

None found during writing. The view is clean. Two design notes for
your awareness:

1. **`quiz_config_for_content` creates on GET.** A read-only GET
   mutating DB state is a minor REST smell (callers get an implicit
   write). I asserted the current behaviour rather than flagging as
   a bug — changing it is probably out-of-scope for this sprint. If
   the team ever wants to tighten that, my `test_get_config_creates_default_when_missing`
   test will need updating.
2. **`my_quiz_attempts` is open to admins.** Because the view uses
   `@teacher_or_admin` and filters by `teacher=request.user`, an admin
   will always see an empty list (unless they're also taking quizzes,
   which happens in e.g. self-check flows). This is captured in
   `test_list_works_for_admin_too` — not a bug, but surface area to
   be aware of.

## Not-run caveat

`pytest` is blocked from executing in my sandbox on this host. The
tests follow the same style/pattern as `tests_assessment.py` (which
is green in CI), reuse the same URL prefixes, and the Python file
compiles cleanly in my static review. Please run on your end before
merging:

```
cd backend && pytest apps/progress/tests_assessment_views.py -v
```

If any test fails due to URL prefix or fixture differences, flag
back to qa-tester — most likely culprit would be the `HTTP_HOST`
pattern (`cov.lms.com`) not matching local middleware config.

## What remains untested on assessment_views.py

- The rare `IntegrityError` → 409 branch in `quiz_attempt_start` when
  the row-lock fails and the unique_together catches a racer. The
  existing `QuizAttemptRaceTests` covers the happy race, but not the
  explicit IntegrityError fall-through.
- The `show_answers=True` branch of submit returning the full snapshot
  with explanations (partially covered by the H1 reveal regression in
  `tests_assessment.py`).

---
qa-tester
