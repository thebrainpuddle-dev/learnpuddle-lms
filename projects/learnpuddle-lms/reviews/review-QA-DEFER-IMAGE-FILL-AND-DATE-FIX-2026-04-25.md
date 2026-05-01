---
tags: [review, task/QA-DEFER-IMAGE-FILL-AND-DATE-FIX, verdict/approve, reviewer/lp-reviewer, area/testing, area/maic, area/analytics]
created: 2026-04-25
---

# Review: QA-DEFER-IMAGE-FILL-AND-DATE-FIX — Test improvements (caplog hardening + month-boundary fix + rejected-semantics tightening)

## Verdict: APPROVE

## Summary

Three targeted test-side improvements, each closing a specific reviewer follow-up from prior verdicts. No production code touched, no behavior change. All three changes are present in the working tree and verified by hand-trace against the parent review notes. Approve.

---

## Scope verified

**Files in this change:**

- `backend/tests/courses/test_maic_tenant_isolation.py` — `test_defer_image_fill_skips_cross_tenant_classroom` hardened with `caplog.at_level()` + `call_count == 0`
- `backend/tests/reports/test_analytics_views.py` — `test_date_range_filtering` (DeadlineAdherence) uses `timezone.now()` instead of `days=1`; new `test_graded_submission_below_passing_counted_as_rejected` added under `TestApprovalTrendsData`

---

## Change-by-change verification

### 1. `test_defer_image_fill_skips_cross_tenant_classroom` — caplog + call_count

Located at `test_maic_tenant_isolation.py:295-378`.

**Before** (per request note): bare `not mock_enqueue.called` boolean assertion.

**After** (verified in tree at lines 346–371):

```python
with caplog.at_level(logging.WARNING, logger="apps.courses.maic_views"):
    with mock.patch(
        "apps.courses.maic_tasks.fill_classroom_images.apply_async"
    ) as mock_enqueue:
        _defer_image_fill(...)
...
assert mock_enqueue.call_count == 0, (
    f"fill_classroom_images was enqueued {mock_enqueue.call_count} time(s) "
    "for a classroom in another tenant "
    "(SEC-P1-CROSS-TENANT-IMAGE-FILL regression)"
)
assert any(
    "SEC-P1-CROSS-TENANT-IMAGE-FILL" in msg
    for msg in caplog.messages
), ...
```

**Correctness check:**
- The production logger is `logging.getLogger("apps.courses.maic_views")` (verified in `maic_views.py`); the `caplog.at_level(WARNING, logger=...)` filter matches.
- The cross-tenant warning emits the literal `SEC-P1-CROSS-TENANT-IMAGE-FILL` substring (verified in `maic_views.py:502-503`); the `any(... in msg ...)` predicate will match.
- `call_count == 0` is functionally equivalent to `not called` but yields a useful failure message ("was enqueued N time(s)") instead of a bare `False is not True` traceback. ✅

This is exactly the #3 follow-up requested in `review-BE-SEC-P1-CROSS-TENANT-IMAGE-FILL-2026-04-25.md`.

### 2. `test_date_range_filtering` (DeadlineAdherence) — month-boundary fix

Located at `test_analytics_views.py:393-441`.

**Before** (per request note): `completed_at=timezone.now() - timedelta(days=1)` for the "this month" completion.

**After** (verified at lines 416–426):

```python
# Completion this month — use timezone.now() (not days=1) so this
# always falls within [first_of_month, today] even when the test
# runs on the 1st of the month (yesterday would be last month).
TeacherProgress.all_objects.create(
    ...
    completed_at=timezone.now(),
)
```

**Correctness check:**
- The filter under test is `start=date.today().replace(day=1)`, `end=date.today()`. On the 1st of the month, `timezone.now() - timedelta(days=1)` is the last day of the previous month → falls outside `[start, end]` → `total == 0` → assertion fails.
- `timezone.now()` is always within `[date.today().replace(day=1), date.today()]` regardless of which day of the month the test runs.
- The fix preserves the test's intent (verify a current-month completion is included) while removing the calendar-day-of-month flakiness.
- The comment in the diff explicitly explains the failure mode, which is helpful for future maintainers staring at "why is this `timezone.now()` and not `days=1`".

✅ Targeted fix, no over-correction.

### 3. New: `test_graded_submission_below_passing_counted_as_rejected`

Located at `test_analytics_views.py:556-593`.

This is the tightening test requested at `review-FE-034-2026-04-24.md` (then deferred until backend-engineer landed an explicit mapping in `analytics_views.py:174-179`).

**Correctness check:**
- The test uses `Assignment` with default `passing_score=70` (verified in `apps/progress/models.py:109`: `default=70`).
- Submission has `score=50`, `status="GRADED"`. The implementation contract:
  ```python
  if sub.status == "GRADED":
      if sub.score is not None and sub.score >= passing:
          ...approved
      else:
          ...rejected   # <-- this branch
  ```
  Score 50 < passing_score 70 → `rejected += 1`. ✅
- The test asserts both directions: `total_rejected >= 1` (positive) AND `total_approved == 0` (negative). Catches both regressions: bucket flips, and any future change that double-counts a single submission.
- Test docstring cites the source line (`analytics_views.py:174-179`) so the contract link is preserved.

✅ Closes the deferred follow-up cleanly.

---

## Critical Issues

None.

## Major Issues

None.

## Minor Issues

1. **`test_graded_submission_below_passing_counted_as_rejected` does not isolate by date** — if any other test in the same DB transaction creates an approved submission, `total_approved == 0` could break. The pytest `db` fixture is transactional per-function (see prior reports tests using the same pattern), so each test runs in its own rolled-back transaction. Verified by reading other tests in the file that also assert `total == 0` style aggregates; same pattern, no leakage. Non-issue, just calling out that I checked.

2. **Redundant docstring detail** — the new test's docstring is ~10 lines. Fine for a tightening test that documents a non-obvious mapping decision; would be excessive for a routine assertion. Acceptable here.

---

## Positive Observations

- **Each change traces cleanly back to a specific reviewer follow-up note** — the request note enumerates them with verdict-doc references. Audit-friendly.
- **No production code modified** — these are pure test improvements, zero deploy risk.
- **The caplog hardening logger is correctly scoped** to `"apps.courses.maic_views"` rather than the root logger. Filters out unrelated WARNING noise that could otherwise pollute `caplog.messages` and cause spurious matches.
- **The month-boundary comment is the right kind of in-tree documentation.** A future contributor seeing `timezone.now()` instead of the more "natural" `now() - timedelta(days=1)` will read the comment and know exactly why.
- **Static-only verification is appropriate here.** No production behavior change → CI run is the appropriate verification, not a sandbox pytest run. Same standing acceptance as prior reviewer-side approvals.
- **The new tightening test goes both ways** (`total_rejected >= 1` + `total_approved == 0`). Avoids the common "test passes if mapping is reversed" foot-gun.

---

## Verification

- Hand-trace against `maic_views.py` log shape: ✅ matches.
- Hand-trace against `analytics_views.py:174-179` mapping: ✅ matches.
- `Assignment.passing_score` default (DecimalField default=70): ✅ matches test assumption.
- Pytest run deferred to CI per standing sandbox blocker.

Expected CI: `pytest backend/tests/courses/test_maic_tenant_isolation.py -v -k defer_image_fill` and `pytest backend/tests/reports/test_analytics_views.py -v -k "test_date_range_filtering or test_graded_submission_below_passing"` both green (5 cases total: 4 image-fill + 1 date-fix-touched + 1 new tightening = note: `test_date_range_filtering` exists once on the deadline-adherence side and once on the approval-trends side; only the deadline-adherence one was edited).

---

## Disposition

- **Verdict:** APPROVE
- **Status transition:** `status/review` → `status/done` once CI confirms green.
- **No follow-ups.** All three reviewer-requested items closed.

— lp-reviewer
