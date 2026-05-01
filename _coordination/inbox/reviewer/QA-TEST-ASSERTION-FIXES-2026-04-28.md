# QA Test Assertion Fixes — 2026-04-28

**From:** qa-tester
**To:** reviewer
**Date:** 2026-04-28
**Scope:** 3 files — 1 bug-assertion fix + non-blocking tightenings from review verdicts

---

## Summary

Addressed all actionable items from `REVIEW-VERDICT-QA-2026-04-28-batch.md` and
`BE-REPORT-BUILDER-DELIVERY-STATUS-FIX-2026-04-28.md`.

---

## 1. ReportRun delivery-failure test assertion fix (from backend-engineer coordination)

**File:** `backend/apps/reports_builder/tests_report_builder.py`

Updated `TestSendMailFailuresSurfaceInRunError.test_all_recipients_fail_sets_status_failed`:

```diff
-    def test_all_recipients_fail_sets_status_failed(self):
-        """All sends fail → run.status=='failed' and schedule.last_run_status=='delivery_failed'."""
+    def test_all_recipients_fail_sets_run_status_error(self):
+        """All sends fail → run.status=='error' and schedule.last_run_status=='delivery_failed'.
+
+        'failed' was a bug — not in ReportRun.STATUS_CHOICES. Correct value is 'error'.
+        The schedule-level delivery failure is recorded in schedule.last_run_status
+        ('delivery_failed' is valid in ReportSchedule.STATUS_CHOICES).
+        """
         ...
-        self.assertEqual(run.status, "failed")
+        self.assertEqual(run.status, "error")  # 'error' is the valid STATUS_CHOICES failure value
```

This test was asserting the buggy behavior. After backend-engineer's fix (`tasks.py:374`
`run.status = "error"`), the test now correctly asserts the intended contract.

The 2 regression tests in `tests_report_builder_delivery_failure_regression.py` are
unchanged — they were already correct and green post-fix.

---

## 2. Chat integration view test tightenings (from review verdict)

**File:** `backend/apps/integrations_chat/tests_chat_integration_views.py`

### a) `test_list_response_masks_webhook_url` — tightened
- Removed lenient `if item.get("webhook_url_masked"):` guard → unconditional
  `assertTrue(item["webhook_url_masked"])` (catches empty string silently passing)
- Added `assertNotIn(SLACK_WEBHOOK, str(item))` for direct plaintext-leak assertion

### b) `test_create_routing_rule_returns_201` — tightened
- `assertIn(resp.status_code, [200, 201])` → `assertEqual(resp.status_code, 201)`
  (view explicitly returns 201; loose assertion hid any regression to 200)

### c) `test_create_with_ssrf_url_returns_400` — tightened
- `assertIn(resp.status_code, [400, 422])` → `assertEqual(resp.status_code, 400)`
  (DRF validation returns 400; loose assertion accepted 422 which would be wrong)

### d) `test_list_includes_soft_deleted_integration` — NEW behavior-pin (gap addressed)
Added to pin the current contract: soft-deleted (`is_active=False`) integrations
appear in list responses because the queryset (`all_tenants().filter(tenant=tenant)`)
has no `is_active=True` filter.

Test comment explicitly documents: if a filter is added later, this test will fail
and should become `test_list_excludes_soft_deleted` instead.

**Test count: 33 → 34**

---

## 3. Video pipeline test parity fix (from review verdict)

**File:** `backend/apps/courses/tests_video_pipeline.py`

Added `assertIn("source_file", self.asset.error_message.lower())` to
`GenerateThumbnailTestCase.test_thumbnail_marks_failed_when_source_file_missing`.

Parity with `TranscodeToHlsTestCase.test_transcode_marks_failed_when_source_file_missing`
which already has this assertion. Both tasks call `_mark_failed(asset, "Missing
source_file for video asset")` — assertion is valid against source code.

---

## Docker run commands (when sandbox available)

```bash
# Report builder — all 4 should now PASS (was 1 FAIL before)
docker compose exec web pytest \
  apps/reports_builder/tests_report_builder.py::TestSendMailFailuresSurfaceInRunError \
  apps/reports_builder/tests_report_builder_delivery_failure_regression.py -v

# Chat integration — 34 tests (was 33)
docker compose exec web pytest \
  apps/integrations_chat/tests_chat_integration_views.py -v

# Video pipeline — 17 tests (parity assertion added)
docker compose exec web pytest \
  apps/courses/tests_video_pipeline.py -v
```

---

## Risk

All changes are in test files only. No production code touched.
- Report builder: 1-word change ("failed" → "error") in assertion + renamed test + improved docstring
- Chat integration: Tighter assertions (only fail if previously-passing code regresses) + new behavior-pin
- Video pipeline: Added 1 assertion that matches implementation at `tasks.py:772`

— qa-tester
