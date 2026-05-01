# QA Review Request — defer_image_fill Test Improvements + Analytics Fixes

**From:** qa-tester
**To:** reviewer
**Date:** 2026-04-25
**Priority:** Non-blocking (reviewer follow-up items from prior sessions)

---

## Summary

Three targeted test improvements addressing reviewer follow-up items:

1. **`test_defer_image_fill_skips_cross_tenant_classroom`** — hardened with
   `caplog` assertion + `call_count == 0` (reviewer suggestion #3 from
   `REVIEW-VERDICT-BE-SEC-P1-CROSS-TENANT-IMAGE-FILL-2026-04-25.md`).

2. **`test_date_range_filtering`** (analytics) — fixed month-boundary
   brittleness (non-blocking M1 from
   `REVIEW-VERDICT-ANALYTICS-TDD-AND-SCIM-PATCH-2026-04-24.md`).

3. **`test_graded_submission_below_passing_counted_as_rejected`** (new) — closes
   the "rejected semantics" open item from
   `REVIEW-VERDICT-ANALYTICS-TDD-AND-SCIM-PATCH-2026-04-24.md`: "add a
   tightening test once backend-engineer picks a mapping." Backend chose
   `GRADED && score < passing_score → rejected` (confirmed in
   `analytics_views.py:174-179`).

---

## File 1: `backend/tests/courses/test_maic_tenant_isolation.py`

### Change to `test_defer_image_fill_skips_cross_tenant_classroom`

**Before:**
```python
assert not mock_enqueue.called, (
    "fill_classroom_images was enqueued ..."
)
```

**After:**
```python
# caplog added to fixture list
with caplog.at_level(logging.WARNING, logger="apps.courses.maic_views"):
    with mock.patch(...) as mock_enqueue:
        _defer_image_fill(...)

assert mock_enqueue.call_count == 0, (
    f"fill_classroom_images was enqueued {mock_enqueue.call_count} time(s) ..."
)
assert any(
    "SEC-P1-CROSS-TENANT-IMAGE-FILL" in msg
    for msg in caplog.messages
), (...)
victim.refresh_from_db()
assert victim.images_pending is False, (...)
```

### Why this is correct

The production code (`maic_views.py:467-472`) logs exactly:
```
"image fill skipped: classroom %s not in tenant %s (SEC-P1-CROSS-TENANT-IMAGE-FILL)"
```
at `logging.WARNING` through `logger = logging.getLogger("apps.courses.maic_views")`.
The `caplog.at_level(WARNING, logger="apps.courses.maic_views")` captures this.

`call_count == 0` is more explicit than `not called` — it shows the exact
count in the failure message rather than a bare boolean.

---

## File 2: `backend/tests/reports/test_analytics_views.py`

### Change to `TestDeadlineAdherenceData.test_date_range_filtering`

**Before:**
```python
completed_at=timezone.now() - timedelta(days=1),
```

**After:**
```python
# Completion this month — use timezone.now() (not days=1) so this
# always falls within [first_of_month, today] even when the test
# runs on the 1st of the month (yesterday would be last month).
completed_at=timezone.now(),
```

**Root cause:** On the 1st of any month, `timezone.now() - timedelta(days=1)` is
the last day of the previous month. The test filters with `start=first_of_month`
which excludes that completion → `total == 0` → assertion fails.

Using `timezone.now()` (same-day) ensures the completion is always within
`[first_of_month, today]` regardless of which day of the month the test runs.

---

## Verification

Static analysis only (Docker sandbox blocked — same blocker accepted
`REVIEW-VERDICT-BE-SEC-P0-AUDIT-SANDBOX-BLOCKED-2026-04-21.md`).

**Run commands:**
```bash
# defer_image_fill tests
docker compose exec web pytest backend/tests/courses/test_maic_tenant_isolation.py \
  -v -k defer_image_fill

# Analytics date fix
docker compose exec web pytest backend/tests/reports/test_analytics_views.py \
  -v -k test_date_range_filtering
```

Expected: both pass.

---

## File 3: `backend/tests/reports/test_analytics_views.py` (new test)

### New: `TestApprovalTrendsData.test_graded_submission_below_passing_counted_as_rejected`

```python
def test_graded_submission_below_passing_counted_as_rejected(self, db):
    """GRADED (score < passing_score) AssignmentSubmission → rejected count.

    Tightening test: Backend chose GRADED && score < passing_score → rejected.
    Assignment default passing_score=70 (model default).
    """
    # ... creates assignment with default passing_score=70
    # ... creates GRADED submission with score=50
    # Asserts: total_rejected >= 1, total_approved == 0
```

**Logic verification**: `analytics_views.py:174-179` checks:
```python
if sub.status == "GRADED":
    passing = sub.assignment.passing_score
    if sub.score is not None and sub.score >= passing:
        by_period[period]["approved"] += 1
    else:
        by_period[period]["rejected"] += 1
```
Score 50 < passing_score 70 → goes to `else` → `rejected += 1` ✅

---

## Verification

**What was verified**: Visual read-back of all changes confirming correct syntax
and logic. Static analysis only (Docker sandbox blocked — accepted at
`REVIEW-VERDICT-BE-SEC-P0-AUDIT-SANDBOX-BLOCKED-2026-04-21.md`).

**Run commands:**
```bash
# defer_image_fill tests (2 expected)
docker compose exec web pytest backend/tests/courses/test_maic_tenant_isolation.py \
  -v -k defer_image_fill

# Analytics fixes (3 expected)
docker compose exec web pytest backend/tests/reports/test_analytics_views.py \
  -v -k "test_date_range_filtering or test_graded_submission_below_passing"
```

Expected: all 5 pass.

---

## Notes

- The `tenant=None` legacy arm hardening (reviewer follow-up item #1) and
  "log victim tenant_id" (item #2) are production code changes that belong
  to backend-engineer, not qa-tester. These are not addressed here.
- No production code modified — only test files.
- Net new tests this session: +1 (rejected semantics); +1 (if you count
  caplog hardening as a structural change, not a new test).

— qa-tester
