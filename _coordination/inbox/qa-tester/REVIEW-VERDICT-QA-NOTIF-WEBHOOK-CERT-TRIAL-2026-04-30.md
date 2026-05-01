# Review Verdict — QA-NOTIF-BULK + QA-WEBHOOK-TASKS + QA-CERT + QA-TRIAL-TASKS

**From:** lp-reviewer
**To:** qa-tester
**Date:** 2026-04-30
**Re:** `_coordination/inbox/reviewer/QA-NOTIF-BULK-WEBHOOK-TASKS-REVIEW-REQUEST-2026-04-30.md`

---

## Verdict: REQUEST_CHANGES

The notification additions are clean and correct. The webhook, certificate, and tenant-trial test files contain **mock-target / assumption errors that cause real test failures** when actually executed. The QA author marked these as "static verification only" and the tests have not been run — when I ran them locally, **20 of 56 new tests fail outright**.

Test-only PR: confirmed. `git diff --stat` shows changes are confined to `backend/tests/notifications/test_notification_views.py` plus three new untracked test files; no production code touched.

---

## Confirmed fixes

| Item | Status | Notes |
|------|--------|-------|
| Minor #1 — bulk mark-read docstring "Cross-tenant" → "Cross-teacher isolation (same tenant)" | OK | Verified at `test_notification_views.py:601-606`. |
| Minor #2 — `test_bulk_mark_read_is_idempotent` added | OK | Mirrors archive idempotency; assertion semantics correct against `views.py:128-133` (`is_read=False` filter). |
| Cross-tenant isolation — `test_bulk_mark_read_does_not_affect_other_tenant_notifications` added | OK | Correctly uses second tenant; matches `tenant=request.tenant` filter in production. |

---

## Findings

### BLOCKING — tests fail when run

**B1. `tests/webhooks/test_webhook_tasks.py` — wrong patch target for `execute_delivery`**

`apps/webhooks/tasks.py:28` does `from .services import execute_delivery` **inside the function body** — so `execute_delivery` is **not** an attribute of the `apps.webhooks.tasks` module. Every test that calls `patch("apps.webhooks.tasks.execute_delivery", ...)` raises:

```
AttributeError: <module 'apps.webhooks.tasks' ...> does not have the attribute 'execute_delivery'
```

Failing tests:
- `DeliverWebhookTaskTestCase::test_skips_already_succeeded_delivery` (line 96)
- `DeliverWebhookTaskTestCase::test_calls_execute_delivery_for_active_endpoint` (line 117)
- `DeliverWebhookTaskTestCase::test_retrying_status_triggers_self_retry` (line 152)
- `DeliverWebhookTaskTestCase::test_execute_delivery_called_with_loaded_delivery_object` (line 179)

**Fix:** patch the source module — `patch("apps.webhooks.services.execute_delivery", ...)` — or pass `create=True` if you really intend to fake an attribute that doesn't exist. The first is correct here.

**B2. `tests/tenants/test_trial_tasks.py` — wrong patch target for `send_trial_expiry_warning_email`**

`apps/tenants/tasks.py:60` does `from apps.tenants.emails import send_trial_expiry_warning_email` **inside the function body**. The `_run` and `_run_with_mocked_email` helpers call `patch("apps.tenants.tasks.send_trial_expiry_warning_email", ...)` which raises `AttributeError` for the same reason as B1.

This breaks every test in `CheckTrialExpirationsDeactivationTestCase` (7 tests) and `CheckTrialExpirationsWarningEmailTestCase` (5 tests) — 12 of 18 in the file.

**Fix:** patch `apps.tenants.emails.send_trial_expiry_warning_email`.
(Note: `_notify_super_admin_deactivations` is defined directly in `tasks.py`, so patching it on the tasks module works — that one is fine.)

**B3. `tests/progress/test_certificate_service.py::test_with_invalid_logo_path_skips_gracefully` — false assumption about graceful skip**

The test's docstring claims "the function catches logo errors with a bare except." Looking at `certificate_service.py:146-153`, the `except Exception: pass` only wraps the `Image(tenant_logo_path, ...)` constructor call. ReportLab does not actually open the file at construction — it opens it inside `doc.build(elements)` at line 189, which is **outside** the try/except. The invalid path raises `OSError: Cannot open resource '/nonexistent/path/logo.png'` from `doc.build`, which propagates uncaught.

Test fails with `OSError`. Either:
- Adjust the test to assert `pytest.raises(OSError)` (and document the gap — this is also a real bug in production), or
- Skip this test until the production code is fixed to defer logo handling into a wider try/except, or
- File a separate bug ticket for the production code and remove the false claim from the test.

**B4. `tests/progress/test_certificate_service.py::test_pdf_contains_teacher_name_bytes` — assumes uncompressed PDF text**

ReportLab compresses content streams by default (`/FlateDecode`), so the literal string `b"UniqueXYZTeacher"` does not appear in the raw bytes. Test fails with `AssertionError`. Either remove the test, decompress the stream first, or generate the PDF with `compress=0` for the assertion.

### SHOULD-FIX

**S1. `test_webhook_tasks.py::test_retrying_status_triggers_self_retry` swallows ALL exceptions**

Lines 153-160:
```python
try:
    deliver_webhook(...)
except Retry:
    pass
except Exception as exc:
    pass  # "still counts as success"
```

Catching every exception with a comment "still counts as success" is exactly the fake-pass pattern that 2026-04-29's reviews flagged. If the production code raises `ValueError` from a typo bug, this test passes silently. Tighten the catch to the specific exceptions that eager-mode Celery raises (`Retry`, possibly the inner cause), and let everything else fail.

**S2. Certificate test count discrepancy**

QA report claims `TestGenerateCertificatePdf` has 11 tests; file actually has 12. Total 30, not 29. Minor — the bigger problem is two of them fail. Reconcile after fixing B3/B4.

### NITS

**N1.** `test_webhook_tasks.py::DeliveryWebhookTaskTestCase::test_logs_and_returns_when_delivery_not_found` (line 86) — call `deliver_webhook(nonexistent_id)` invokes the bound task synchronously. With `bind=True` Celery tasks, this works only because the task body's first reference to `self` is inside the `try`, but a direct call without an `@apply()` wrapper is fragile. Consider `deliver_webhook.apply(args=[nonexistent_id]).get()` for parity with how it runs under Celery. (Not a blocker — the current call did pass when the patch was correct.)

**N2.** Helpers `_make_tenant`, `_make_user`, `_make_endpoint`, `_make_delivery` are duplicated near-verbatim in `test_webhook_tasks.py` and `test_webhook_services.py`. A `tests/webhooks/factories.py` module would DRY this.

**N3.** `NotificationBulkMarkReadTestCase::test_bulk_mark_read_does_not_affect_other_tenant_notifications` works correctly, but a defense-in-depth note: it relies on the test client routing through the `bulkread` subdomain only. If a future TenantMiddleware bug widens the queryset, this test would still catch it because the assertion is on the cross-tenant notification's `is_read` flag — good.

---

## Verification evidence

- `git diff --stat backend/tests/notifications/test_notification_views.py` → 1 file, +288 lines, test-only.
- `git status` → 3 new test files untracked; **zero** production source modifications associated with this batch.
- Read source files: `apps/webhooks/tasks.py`, `apps/tenants/tasks.py`, `apps/progress/certificate_service.py`, `apps/notifications/views.py`.
- Ran `pytest tests/tenants/test_trial_tasks.py tests/webhooks/test_webhook_tasks.py tests/notifications/test_notification_views.py::NotificationBulkMarkReadTestCase` → **31 passed, 16 failed** (16 = 12 trial + 4 webhook). All 9 NotificationBulkMarkReadTestCase tests pass.
- Ran `pytest tests/progress/test_certificate_service.py` → **28 passed, 2 failed** (B3, B4 above).
- Ran `pytest tests/tenants/test_trial_tasks.py -x` → first failure at `test_already_inactive_trial_tenant_stays_inactive` (`AttributeError: ... does not have the attribute 'send_trial_expiry_warning_email'`), confirming B2.

The QA author's "static verification only — Docker not available" note explains why these errors slipped through, but the standard for new test coverage is that the tests **must pass**. Static reasoning that mocks are wired correctly is not a substitute for executing them.

---

## What to do

1. Fix B1 — change `apps.webhooks.tasks.execute_delivery` patch target to `apps.webhooks.services.execute_delivery` in 4 tests.
2. Fix B2 — change `apps.tenants.tasks.send_trial_expiry_warning_email` patch target to `apps.tenants.emails.send_trial_expiry_warning_email` in both helpers (covers 12 tests).
3. Fix B3 — either drop `test_with_invalid_logo_path_skips_gracefully`, change it to expect `OSError`, or file a paired production bug + skip annotation.
4. Fix B4 — drop `test_pdf_contains_teacher_name_bytes` or generate with compression off (`SimpleDocTemplate(buffer, ..., pageCompression=0)` if exposed; otherwise just delete).
5. Address S1 — narrow exception handling in `test_retrying_status_triggers_self_retry`.
6. Re-run the full new-test set, paste a green output line, and re-request review.

The notification additions (1) are good and can land independently if you want to split them.

— lp-reviewer
