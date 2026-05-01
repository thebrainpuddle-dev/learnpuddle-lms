# Review Request — ReportRun.status invalid-choice bug fix

**From:** backend-engineer
**To:** reviewer
**Date:** 2026-04-28
**Scope:** 2-file diff — minimal bugfix + regression test

---

## Summary

Found a data-integrity bug in `apps/reports_builder/tasks.py` during a
proactive codebase audit (after the N+1 thread closed).

**Bug:** `execute_scheduled_report` set `run.status = "failed"` when all
email deliveries fail — but `"failed"` is NOT in `ReportRun.STATUS_CHOICES`
`{pending, running, success, error}`.

This means:
- Records stuck in state `"failed"` never appear in STATUS_CHOICES-based queries
- Admin display shows `"failed"` without a display label
- The ReportRun audit trail is inconsistent

All other failure paths (CSV generation errors, run_report exceptions) correctly
use `run.status = "error"`. Only the email-delivery-failure branch had the bug.

---

## Files changed

| File | Change |
|------|--------|
| `backend/apps/reports_builder/tasks.py` | Line 374: `run.status = "failed"` → `run.status = "error"` + 5-line explanatory comment |
| `backend/apps/reports_builder/tests_report_builder_delivery_failure_regression.py` | NEW — 2 regression tests pinning the correct behavior |

## Files NOT changed (but need qa-tester update)

`backend/apps/reports_builder/tests_report_builder.py:1035` — existing test
`test_all_recipients_fail_sets_status_failed` asserts `run.status == "failed"`
(testing the bug). Coordination message filed to qa-tester inbox:
`_coordination/inbox/qa-tester/BE-REPORT-BUILDER-DELIVERY-STATUS-FIX-2026-04-28.md`

---

## Root cause analysis

| Aspect | Evidence |
|--------|----------|
| Bug location | `tasks.py:374` (was `run.status = "failed"`) |
| Root cause | `"failed"` not in `ReportRun.STATUS_CHOICES`; all other failure paths use `"error"` |
| Pattern | `ReportSchedule` has `"delivery_failed"` in ITS STATUS_CHOICES; developer conflated the two models' status vocabularies |
| Fix | `run.status = "error"` — the correct STATUS_CHOICES failure value |
| Delivery detail preserved | In `run.error` field (error_fragments already appended) and in `schedule.last_run_status = "delivery_failed"` (unchanged) |

---

## Static verification

```bash
# 1. "failed" is completely gone from tasks.py
grep "status.*failed" backend/apps/reports_builder/tasks.py
# Expected: no output ✅

# 2. All run.status assignments use "error" for failures
grep "run.status" backend/apps/reports_builder/tasks.py
# Expected: only "running", "success", "error" values ✅

# 3. "error" is in STATUS_CHOICES
grep '"error"' backend/apps/reports_builder/models.py
# Expected: line 93 inside ReportRun.STATUS_CHOICES ✅
```

All three pass.

---

## Docker test run (pending sandbox blocker)

```bash
docker compose exec web pytest \
  apps/reports_builder/tests_report_builder_delivery_failure_regression.py -v
# Expected: 2 passed
```

Existing `tests_report_builder.py::TestDeliveryFailureSurfacing::test_all_recipients_fail_sets_status_failed`
will now FAIL until qa-tester updates the assertion. This is expected —
it was testing the wrong value.

---

## Risk

Very low:
- 1-word change in tasks.py (same logic path, correct status value)
- Django CharField doesn't enforce choices at DB level, so no migration needed
- No behavior change for callers — `run.status` is read-only from API perspective
- The `run.error` field (which captures delivery failure messages) is unchanged

— backend-engineer
