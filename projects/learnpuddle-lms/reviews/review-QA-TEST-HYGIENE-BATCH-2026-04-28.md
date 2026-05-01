---
tags: [review, task/QA-TEST-HYGIENE-BATCH, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-28
---

# Review: QA-TEST-HYGIENE-BATCH — Webhook stale-mock + Notification GENERAL fix + ReportBuilder no-op

## Verdict: APPROVE

## Summary
Two real test-hygiene fixes in one batch (both small, both correct), plus one item that was already done. Webhook services tests had 13 `@patch` decorators pointing at a symbol that does not exist as a module attribute; notifications service tests used an invalid choice value. Both are now fixed in a way that aligns with how the production code actually resolves these symbols.

## Files Verified
- `backend/tests/webhooks/test_webhook_services.py` — diff reviewed; grep confirms 13 `@patch("apps.webhooks.tasks.deliver_webhook")` occurrences in the right test classes
- `backend/apps/notifications/tests_services.py` — diff reviewed (single-line change)
- `backend/apps/webhooks/services.py:105` and `backend/apps/webhooks/tasks.py:21` — read to confirm import topology

## Critical Issues
None.

## Major Issues
None.

## Minor Issues

1. **Patch target rationale should be a code comment.** The fix moves all 13 patches from `apps.webhooks.services.deliver_webhook` to `apps.webhooks.tasks.deliver_webhook`. The reason — `services.py:105` does `from .tasks import deliver_webhook` *inside* `trigger_webhook()`, so the symbol is never bound at module level on `services.py` — is in the inbox message but not in the test file. A 2-line `# Patch target: deliver_webhook is locally imported inside trigger_webhook(),` `# so we patch tasks.deliver_webhook (the source module) — see services.py:105.` comment near the top of `TriggerWebhookTestCase` would prevent a future engineer from "fixing" it back. Non-blocking.

2. **No assertion change paired with the patch-target change.** The test bodies assert `mock_deliver.delay.assert_called_once()` (etc.) — these still pass because the inner `from .tasks import deliver_webhook` resolves `tasks.deliver_webhook` at call time, which now is the mocked symbol. Behavior is preserved, but worth a quick mental check that the prior "test passed for the wrong reason" hazard is gone — and it is, because under the old broken patch target the decorator raised `AttributeError` at collection time (so 13 tests were errored, not falsely passing). Not an issue, just calling out the verification.

3. **`tests_services.py` change is a one-liner from `"GENERAL"` → `"SYSTEM"`.** That's correct — `"SYSTEM"` is in `NOTIFICATION_TYPES` and absent from `ACTIONABLE_TYPES`, preserving the assertion semantics. Optionally, the test could now also import `NOTIFICATION_TYPES` and assert membership defensively, but that responsibility lives in the new `tests_notification_type_choices.py` registry instead — so duplicating it here would be redundant. Don't add anything.

## Positive Observations

1. **Patch target moved to where the symbol actually lives.** `apps.webhooks.tasks.deliver_webhook` is the canonical source: defined at `tasks.py:21`, imported via `from .tasks import deliver_webhook` everywhere else. Patching the source module is the correct mock.patch idiom — the alternative ("patch where it's used") would require `services.deliver_webhook` to be a module-level binding, which it explicitly is not. Fixing the test rather than introducing a module-level binding in production code is the right call.

2. **Scope discipline.** 13 `@patch` decorators changed mechanically; nothing else in those test methods touched. `ExecuteDeliveryTestCase` and `EmitEventHelpersTestCase` already used the correct target and were not touched — minimal blast radius.

3. **Verification matrix in the request matches reality.**
   - `deliver_webhook` defined in `tasks.py:21` ✅ (grep confirms)
   - `from .tasks import deliver_webhook` inside `services.py:105` ✅ (grep confirms)
   - 13 occurrences of new patch target in expected test classes ✅ (grep confirms 13 in TriggerWebhookTestCase + WebhookServiceCrossTenantTestCase, plus 2 in ExecuteDeliveryTestCase that were already correct)
   - `"SYSTEM"` in NOTIFICATION_TYPES + absent from ACTIONABLE_TYPES ✅ (verified against `models.py` and `services.py`)

4. **`tests_report_builder.py` correctly identified as no-op.** The author confirms the prior `BE-REPORT-BUILDER-DELIVERY-STATUS` work landed both the rename (`error` not `failed`) and the assertion update — so this batch correctly does nothing for that file rather than re-applying a stale fix. Good cross-PR awareness.

5. **Coordination with backend-engineer.** The `"GENERAL"` → `"SYSTEM"` fix originated from backend-engineer's `BE-NOTIF-INVALID-TYPE-GENERAL-TEST-FIX` request and was correctly routed to qa-tester for the test-only edit, while backend kept ownership of the model-side `DISCUSSION_REPLY` fix. Clean ownership split.

## Verification
- Read 4 files (webhooks tests diff, notifications tests diff, services.py:105, tasks.py:21)
- Grep confirmed exactly 13 patches at the new target in the expected test classes
- Confirmed `"SYSTEM"` membership in `NOTIFICATION_TYPES` post-`DISCUSSION_REPLY` fix
- Pytest re-run deferred (`pythonjsonlogger` sandbox blocker — same as other backend reviews this sprint)

## Recommendation
APPROVE — merge. Status updated to `done`. Both fixes are surgical, correctly targeted, and verifiable from the diffs alone.
