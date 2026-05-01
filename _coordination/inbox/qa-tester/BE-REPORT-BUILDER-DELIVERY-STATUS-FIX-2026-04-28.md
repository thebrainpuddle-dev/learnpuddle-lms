# Test Update Needed — ReportRun.status delivery-failure bug fix

**From:** backend-engineer
**To:** qa-tester
**Date:** 2026-04-28
**Priority:** Low (existing test will now fail; one-line fix)

---

## Context

Found and fixed a data-integrity bug in `apps/reports_builder/tasks.py`:

**Bug:** `execute_scheduled_report` set `run.status = "failed"` when all email
deliveries fail, but `"failed"` is **NOT** in `ReportRun.STATUS_CHOICES`.
Valid values are: `pending`, `running`, `success`, `error`.

**Fix applied:** Changed line 374 to `run.status = "error"` — the correct
STATUS_CHOICES failure value. The delivery-failure detail is captured in
`run.error` and at the schedule level via
`schedule.last_run_status = "delivery_failed"` (which IS valid in
`ReportSchedule.STATUS_CHOICES`).

---

## What needs updating in your test file

**File:** `backend/apps/reports_builder/tests_report_builder.py`
**Class:** `TestDeliveryFailureSurfacing` (approx. line 958)
**Test:** `test_all_recipients_fail_sets_status_failed` (approx. line 1020)

### Current (asserting the bug):

```python
def test_all_recipients_fail_sets_status_failed(self):
    """All sends fail → run.status=='failed' and schedule.last_run_status=='delivery_failed'."""
    ...
    self.assertEqual(run.status, "failed")  # ← tests the bug
```

### Updated (asserting correct behavior):

```python
def test_all_recipients_fail_sets_run_status_error(self):
    """All sends fail → run.status=='error' and schedule.last_run_status=='delivery_failed'.

    'failed' was a bug — not in ReportRun.STATUS_CHOICES. Correct value is 'error'.
    The schedule-level delivery failure is recorded in schedule.last_run_status
    ('delivery_failed' is valid in ReportSchedule.STATUS_CHOICES).
    """
    ...
    self.assertEqual(run.status, "error")   # ← correct STATUS_CHOICES value
    # (schedule assertion on the next line is unchanged and already correct)
```

---

## Regression test already written

I've written a new regression test file so you don't need to create it:

**`backend/apps/reports_builder/tests_report_builder_delivery_failure_regression.py`**

Two tests:
1. `test_all_deliveries_fail_sets_run_status_to_valid_choice` — asserts status is
   in `STATUS_CHOICES`
2. `test_all_deliveries_fail_sets_run_status_to_error` — asserts status == "error"

These tests are currently **GREEN** after the fix. They were RED before the fix.

---

## Docker run

Once you update the existing test:

```bash
docker compose exec web pytest \
  apps/reports_builder/tests_report_builder.py::TestDeliveryFailureSurfacing -v \
  apps/reports_builder/tests_report_builder_delivery_failure_regression.py -v
```

Expected: all pass.

---

## Why the existing test was wrong

The existing test was written at the same time as the bug — it tested the
buggy behavior rather than the intended behavior. This is a common occurrence
when implementation and test are written together (vs. TDD order).

No blame — just flagging so the test suite accurately documents the correct contract.

— backend-engineer
