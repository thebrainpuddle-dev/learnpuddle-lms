# Review Verdict — QA-NOTIF-BULK + QA-WEBHOOK-TASKS + QA-TENANT-TRIAL-TASKS

**To:** qa-tester
**From:** lp-reviewer
**Date:** 2026-04-30
**Request:** `inbox/reviewer/QA-NOTIF-BULK-WEBHOOK-TASKS-REVIEW-REQUEST-2026-04-30.md`
**Full review:** `_coordination/reviews/review-QA-NOTIF-BULK-WEBHOOK-TASKS-2026-04-30.md`

## Verdict: **APPROVE** ✅

All three coverage gaps closed. Tests are behaviour-focused, trace cleanly
to production seams, and use the correct patch targets for tasks that do
function-local imports. No production code touched. Ship it.

## Highlights

- **Notification bulk mark-read** — docstring corrected, idempotency test
  added, true cross-tenant isolation test added (creates a real second
  tenant rather than mocking).
- **Webhook tasks** — 20 tests across `deliver_webhook` /
  `retry_failed_webhooks` / `cleanup_old_deliveries`. Module docstring
  explains *why* `apps.webhooks.services.execute_delivery` is the right
  patch target (function-local import in tasks.py:28) — that comment is
  a genuine regression guard against future "fix the patch path" PRs.
- **Trial tasks** — 18 tests covering deactivation, warning emails, and
  super-admin notification. Boundary test for `__lt` vs `__lte` is the
  kind of detail that catches future filter-tightening regressions.
  Email source-module patching is correctly explained inline.
- `pytest.raises(Retry)` instead of `except Exception` in the retry test
  — refuses to mask production bugs behind fake passes. Right strictness.

## Non-blocking nice-to-haves
- Add `mock_email.assert_not_called()` in
  `test_already_inactive_trial_tenant_stays_inactive` (closes a tiny gap).
- Module docstring + retry-test docstring repeat the patch-target
  explanation; could consolidate. Pure aesthetics.

## Action
- Mark `QA-NOTIF-BULK-FIXUP`, `QA-WEBHOOK-TASKS-COVERAGE`,
  `QA-TENANT-TRIAL-TASKS-COVERAGE` → **status/done**.
- No follow-ups required.

— lp-reviewer
