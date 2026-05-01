---
tags: [review, task/TASK-007, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-20
---

# Review: TASK-007 — Extract Duplicated Backend Helpers

## Verdict: APPROVE

## Summary

Clean, mechanical refactor. Two duplicated helpers (`_rewrite_rich_text` and
`_teacher_assigned_to_course`) have been consolidated into canonical shared
utilities at `backend/utils/rich_text.py` and `backend/utils/course_access.py`.
All six call-site files now delegate to the shared implementations and no
surviving inline duplicates were found.

## Critical Issues

None.

## Major Issues

None.

## Minor Issues

### m1 — No direct unit tests for the new utilities

**Files**: `backend/utils/rich_text.py`, `backend/utils/course_access.py`

Neither new module has a dedicated unit-test file (no `backend/tests/utils/`
directory exists yet). The logic is indirectly exercised through serializer
and view tests, so behaviour is covered — but since we're formalising these
as shared utilities they deserve focused unit tests. Recommended follow-up
(non-blocking): add `backend/tests/utils/test_rich_text.py` covering
null/empty input, missing `context['request']`, unusual image URL forms; and
`backend/tests/utils/test_course_access.py` covering teacher assigned to
course, assigned via group, unassigned user, deleted course.

### m2 — Extraction opportunistically pulled in more call-sites than the request described

The review request listed 6 call-sites but the diff also updates
`apps/courses/student_serializers.py`, `apps/courses/student_views.py`,
`apps/courses/teacher_study_views.py`, `apps/courses/study_summary_views.py`,
and `apps/progress/student_views.py`. This is a **positive** — more
duplication removed than advertised — but it's worth calling out in the task
note so reviewers don't miss the broader blast radius.

## Positive Observations

- **Backward-compat aliasing**: call-sites import `is_teacher_assigned_to_course as _teacher_assigned_to_course` so internal invocation names are preserved. Keeps the diff minimal and reduces churn across surrounding code. Good judgment.
- **TYPE_CHECKING guard** in `course_access.py` avoids circular imports with `apps.users.models.User` / `apps.courses.models.Course` — the correct pattern.
- **Signature stability**: `rewrite_rich_text_for_serializer(raw_html, context)` and `is_teacher_assigned_to_course(user, course)` preserve argument order and defaults from the inline versions.
- **No commented-out code, no dead branches, no TODOs** left behind in either new module.
- Zero model / API / migration churn — this is a pure refactor and the author correctly flagged that.

## Verification Notes

- `grep` for surviving inline definitions of `_rewrite_rich_text`, `_teacher_assigned_to_course`, `_student_assigned_to_course` returns **zero hits** across `backend/` — confirmed all duplicates removed.
- Imports verified at: `courses/serializers.py:10`, `courses/teacher_serializers.py:7`, `courses/student_serializers.py:9`, `courses/teacher_views.py:10`, `progress/teacher_views.py:36`, `progress/student_views.py:50`.
- 26+ call-sites across 6 files delegate to the canonical implementations.

## Ready to Merge

Yes — once m1 (unit tests) is tracked as a follow-up ticket. Not a merge blocker.
