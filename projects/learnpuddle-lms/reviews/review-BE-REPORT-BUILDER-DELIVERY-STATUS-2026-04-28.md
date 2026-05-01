---
tags: [review, task/BE-REPORT-BUILDER-DELIVERY-STATUS, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-28
---

# Review: BE-REPORT-BUILDER-DELIVERY-STATUS — ReportRun.status invalid-choice bugfix

## Verdict: APPROVE

## Summary
Surgical 1-line bugfix that restores STATUS_CHOICES integrity for `ReportRun`. Root cause analysis is correct, the fix matches every other failure path in the same file, and the regression tests pin both the general invariant (status must be a valid choice) and the specific value (`"error"`). Low risk, clearly documented.

## Critical Issues
None.

## Major Issues
None.

## Minor Issues

1. **Coordination with existing test** — The existing `tests_report_builder.py:1035::test_all_recipients_fail_sets_status_failed` will now fail until qa-tester flips the assertion from `"failed"` → `"error"`. The submitter has filed a coordination message to qa-tester (`_coordination/inbox/qa-tester/BE-REPORT-BUILDER-DELIVERY-STATUS-FIX-2026-04-28.md`), so this is tracked. **Recommendation:** before this lands on a CI-gated branch, ensure the qa-tester update is sequenced ahead or alongside, or the suite will go red. Not a blocker for the review verdict, but a coordination note.

2. **Test setup uses `User.tenant` post-create** — In `_make_user`, the test creates the user via `create_user(...)` and then assigns `user.tenant = tenant; user.save()`. This is consistent with other test files but slightly fragile if `User.create_user` evolves to require tenant at creation time. Non-blocking — matches existing project patterns.

## Positive Observations

- **Correctness of fix verified**: All eight `run.status = ...` assignments in `tasks.py` (lines 66, 91, 99, 113, 120, 249, 274, 379) now use values from `ReportRun.STATUS_CHOICES = {pending, running, success, error}`. Confirmed by `grep` across the file.
- **Distinction between vocabularies preserved**: The fix correctly preserves the *delivery* nuance via `schedule.last_run_status = "delivery_failed"` (which IS in `ReportSchedule.STATUS_CHOICES`). The two-status-vocabulary design is honored, and the delivery-failure detail is also captured in `run.error`. No information is lost.
- **Explanatory comment added at the fix site** (lines 374–378) documenting *why* `"error"` is correct and where the delivery-specific detail lives. This prevents the same conflation from being reintroduced.
- **Regression tests are well-designed**:
  - `test_all_deliveries_fail_sets_run_status_to_valid_choice` pins the general invariant against `STATUS_CHOICES` (would catch any future regression to *any* invalid value, not just `"failed"`).
  - `test_all_deliveries_fail_sets_run_status_to_error` pins the specific contract.
  - The second test additionally asserts `run.error` contains the `DELIVERY_FAILED` fragment AND `schedule.last_run_status == "delivery_failed"` — i.e. the test is a complete behavioral contract for the failure branch, not just a status check.
- **Mock strategy is appropriate**: `_patch_csv_stack` mocks `run_report`, `rows_to_csv`, `_artifact_path`, and `send_mail` — isolates the email-failure branch from CSV pipeline noise. Test runs are deterministic.
- **No migration needed**: Django CharField does not enforce choices at DB level, so existing rows with the bogus `"failed"` value (if any from production) won't break — though a follow-up data migration to clean those up may be worth tracking separately. (Filed as a non-blocking observation; bug is recent enough that prod impact is likely small or zero.)
- **TDD discipline visible**: The test docstring explicitly notes RED → GREEN, and the regression test file is purpose-built and named for the bug.

## Verification Performed

| Check | Result |
|-------|--------|
| `ReportRun.STATUS_CHOICES` contains `"error"` | ✅ models.py:155 |
| `ReportRun.STATUS_CHOICES` does NOT contain `"failed"` | ✅ verified |
| All `run.status = ...` assignments in tasks.py use valid choices | ✅ all 8 sites |
| No remaining `"failed"` literal applied to `run.status` in tasks.py | ✅ |
| `ReportSchedule.STATUS_CHOICES` retains `"delivery_failed"` | ✅ models.py:95 |
| Comment at fix site explains the two vocabularies | ✅ tasks.py:374–378 |
| Regression test imports + fixtures resolve | ✅ static check |

## Follow-up (non-blocking, advisory)

1. **One-off data fix** — If any production `ReportRun` rows already have `status = "failed"`, consider a one-off data migration or management command to update them to `"error"`. Currently they would be invisible to any queryset filtering on `STATUS_CHOICES` membership. Cheap and safe; track separately.
2. **Existing test update** — qa-tester must update `tests_report_builder.py:1035` assertion from `"failed"` → `"error"` before the merged change reaches a CI-gated branch.

— reviewer
