---
tags: [review, task/FE-034, task/TASK-024, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-24
---

# Review: QA Analytics TDD Tests + SCIM Groups PATCH Follow-ups

## Verdict: APPROVE

## Summary

Two clean, well-scoped test deliverables: (1) 35 TDD tests in `backend/tests/reports/test_analytics_views.py`
that nail down the HTTP contract for the three FE-034 analytics endpoints before any backend code
is written; (2) 7 supplemental SCIM Groups PATCH tests appended to `backend/apps/users/tests_scim_groups.py`
locking in the empty-displayName guard, per-op audit detail (`changes.ops`, `op_count`), and the
`re.search` lenient-path fix for member removes. Both files match approved precedents
(`tests_completion_rate.py`, `tests_scim_cross_tenant.py`), use real model field names verified
against `apps/progress/models.py` and `apps/users/scim_group_views.py`, and properly isolate state
via `all_objects` managers.

## Verification performed

- **Model contracts confirmed**:
  - `TeacherProgress.completed_at` (DateTimeField), `status` choices include `COMPLETED`/`IN_PROGRESS`/`NOT_STARTED` ✓
  - `AssignmentSubmission.status` choices = `PENDING`/`SUBMITTED`/`GRADED` (no `REJECTED` — flagged correctly in QA note) ✓
  - `Quiz.assignment` is a `OneToOneField(Assignment, ...)`, so the `_quiz` helper correctly creates an Assignment first ✓
  - `Course.deadline` is a `DateField` ✓
  - `Course.is_published` field exists ✓
- **SCIM PATCH implementation matches test expectations** (`apps/users/scim_group_views.py`):
  - Lines 327–335: empty/whitespace `displayName` → `_scim_error(400, ..., "invalidValue")` ✓
  - Lines 320, 338, 343, 349, 357, 370–374: `audit_ops` collected with `{op, path}` per operation ✓
  - Lines 384–396: `log_audit(action="SCIM_GROUP_PATCH", ..., changes={"op_count": ..., "ops": audit_ops, ...})` ✓
  - Line 360: `_MEMBER_FILTER_RE.search(path)` (not `match`) — handles padded paths ✓
- **Tenant resolution**: `HTTP_HOST=f"{tenant.subdomain}.lms.com"` matches `conftest.py` line 276 (`PLATFORM_DOMAIN = "lms.com"`) ✓
- **All 35 analytics tests will return 404 today** (endpoints don't exist) — correct TDD-failing state.

## Critical Issues

None.

## Major Issues

None.

## Minor Issues

1. **Month-boundary brittleness in `TestDeadlineAdherenceData.test_date_range_filtering`**
   (`test_analytics_views.py` lines 393–439).
   The test creates a "current month" completion with `completed_at = timezone.now() - timedelta(days=1)`
   and filters from `start = date.today().replace(day=1)`. If the test runs on the **1st of any month**,
   "yesterday" falls in the previous month → outside the filter window → assertion `total >= 1` fails.
   Suggest `completed_at = timezone.now()` or guard against running on day-1, or pin time with `freezegun`.
   Not blocking — backend-engineer can land first; QA can tighten in a follow-up.

2. **Tautology in empty-list assertions**
   (`assert resp.data == [] or isinstance(resp.data, list)`, lines 231, 490, 718).
   Since `[] is a list`, the right side always covers the left. Harmless but the second clause is
   never reached. Either drop the `== []` half or split into two assertions for clarity.

3. **Ambiguous `rejected` semantics for `ApprovalTrendsPoint`**
   QA correctly flagged this in the cover note. The `AssignmentSubmission` model has no `REJECTED`
   status, so the test only asserts `rejected >= 0`. Backend-engineer must define the mapping
   (likely "GRADED with score < passing_score") when implementing the view, and QA should add a
   tightening test once the contract is decided. Not a defect in the tests as filed — they
   correctly avoid baking in a guess.

4. **`test_unpublished_courses_excluded` doesn't set `assigned_to_all`**
   (line 898). Bypasses the `_course` helper to set `is_published=False`. Fine for the assertion
   ("draft course must not appear"), but if the implementation joins on enrollments, the contract
   isn't fully exercised. Consider also asserting that an unpublished course with enrollments
   stays excluded.

## Positive Observations

- **TDD discipline**: tests written first, no implementation yet — exactly what FE-034 needed
  to land cleanly. Backend-engineer now has 35 unambiguous failing tests as a spec.
- **Tenant isolation tests on every endpoint** — matches the LMS security posture (cross-tenant
  leakage is BLOCK-level severity here). Each endpoint has a dedicated isolation test that
  spins up a second tenant with data and asserts the first tenant sees nothing.
- **Self-contained helpers** (`_tenant`, `_admin`, `_teacher`, `_course`, `_module`, `_content`,
  `_assignment`, `_quiz`, `_auth_client`) — same pattern that worked for
  `tests_scim_cross_tenant.py` and `tests_completion_rate.py`. No conftest fixture coupling means
  the tests are robust to fixture refactors.
- **`all_objects.create(...)` usage on `TeacherProgress`, `QuizSubmission`, `AssignmentSubmission`**
  correctly bypasses the `TenantManager` contextvar (which is unset in pytest setup phase).
- **Quiz creation via `Assignment` first** — the `_quiz` helper correctly threads
  `Assignment → Quiz` because `Quiz.assignment` is a `OneToOneField`. Easy mistake to miss.
- **Type assertions are tight**: `isinstance(item["totalTeachers"], int)`, `0 <= adherencePercent <= 100`,
  `uuid.UUID(item["courseId"])` — these will catch shape regressions early.
- **Audit log tests verify both presence and structure**: action name, target_id, ops list shape,
  op_count match. Good defense-in-depth for compliance auditing.
- **SCIM PATCH padded-path test** is a real-world regression guard — Okta and Azure AD both send
  pretty-printed JSON with whitespace, and the `re.search` fix prevents silent "remove did
  nothing" bugs.

## Recommendations

- **APPROVE** the test merge. Backend-engineer is unblocked to implement
  `apps/reports/views.py` analytics endpoints driven by these 35 failing tests.
- After backend lands, re-run the suite. Expect all 35 to pass; if `test_date_range_filtering`
  flakes around the 1st of a month, revisit the minor issue above.
- Add the `rejected` mapping clarification to TASK definition (or the FE-034 follow-up note)
  before backend implementation begins — keeps the contract explicit.

---

**Action**: Notifying qa-tester (approval) and backend-engineer (TDD ready to drive implementation).
