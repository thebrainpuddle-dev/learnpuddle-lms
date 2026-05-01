# Review Verdict — QA-COMPLETION-RATE-TESTS-2026-04-22

**From:** reviewer (lp-reviewer)
**To:** qa-tester
**Date:** 2026-04-22
**Re:** `backend/apps/courses/tests_completion_rate.py` (6 tests)

---

## Verdict: APPROVED

## What was verified

1. All 6 named tests exist with the exact assertions listed in the request
   (50.0, 0.0 no-teachers, 100.0, 0.0 content-level-only, 0.0 assigned_to_all,
   33.3 rounding). Locations: lines 144–290.
2. Tests hit `GET /api/v1/courses/` (line 132) which routes through
   `course_list_create` in `backend/apps/courses/views.py:116`. The
   `_completed_teacher_count` annotation (views.py:145–152) is therefore exercised,
   and `CourseListSerializer.get_completion_rate` (serializers.py:197) takes the
   annotation branch rather than the DB-count fallback.
3. Tenant/middleware hygiene is correct:
   `@override_settings(ALLOWED_HOSTS=["*"], PLATFORM_DOMAIN="lms.com")` on the
   TestCase, unique subdomain per test via `uuid.uuid4().hex[:6]`, and
   `TeacherProgress.all_objects.create(...)` to bypass the TenantManager
   contextvar inside setUp.
4. No production code modified — only new test file added.

## Concerns

- **Sandbox limit:** pytest cannot run inside the agent sandbox (known
  project-wide Docker constraint). Static review only; CI will be first live run.
- Minor helper duplication with `apps/courses/tests/factories.py` — optional
  follow-up de-dup, not blocking.
- `_make_content` hard-codes `content_type="TEXT"` — fine today, parametrise
  if future tests need video/quiz rows.

Full review: `_coordination/reviews/review-QA-COMPLETION-RATE-TESTS-2026-04-22.md`.

Ship it.

— lp-reviewer
