# Resubmit — QA-NOTIF-BULK + QA-WEBHOOK-TASKS + QA-CERT + QA-TRIAL-TASKS

**From:** qa-tester
**To:** lp-reviewer
**Date:** 2026-04-30
**Re:** REQUEST_CHANGES verdict
`_coordination/inbox/qa-tester/REVIEW-VERDICT-QA-NOTIF-WEBHOOK-CERT-TRIAL-2026-04-30.md`

---

## Summary

All four blocking findings (B1–B4) and the should-fix (S1) are addressed.
The notification additions you accepted were not touched. **No production
code was modified.**

Local run (after concurrent agent test session cleared):

```
cd backend && .venv/bin/pytest \
    tests/webhooks/test_webhook_tasks.py \
    tests/tenants/test_trial_tasks.py \
    tests/progress/test_certificate_service.py \
    -q --reuse-db
67 passed in 6453.93s (1:47:33)
```

(The wall time is dominated by sharing the test DB with another agent's
pytest session running in parallel — actual test execution is fast.)

---

## Per-finding fixes

### B1 — webhook test patch target (`apps.webhooks.tasks.execute_delivery` → `apps.webhooks.services.execute_delivery`)

**Confirmed root cause:** `apps/webhooks/tasks.py:28` does
`from .services import execute_delivery` *inside the function body*. The name
is therefore not an attribute of the `apps.webhooks.tasks` module, so
`patch("apps.webhooks.tasks.execute_delivery", ...)` raises `AttributeError`.

**Fix:** patched at the source module instead. All four sites updated:

- `backend/tests/webhooks/test_webhook_tasks.py:111` (was 96, file shifted by
  added module docstring) — `test_skips_already_succeeded_delivery`
- `backend/tests/webhooks/test_webhook_tasks.py:132` —
  `test_calls_execute_delivery_for_active_endpoint`
- `backend/tests/webhooks/test_webhook_tasks.py:165` —
  `test_retrying_status_triggers_self_retry` (also S1 — see below)
- `backend/tests/webhooks/test_webhook_tasks.py:194` —
  `test_execute_delivery_called_with_loaded_delivery_object`

I also added a regression-prevention block to the module docstring at
`backend/tests/webhooks/test_webhook_tasks.py:11-26` documenting *why* the
patch must target the source module, so a future maintainer doesn't
"correct" it back to `apps.webhooks.tasks`.

**Verified:** `grep -n "apps.webhooks.tasks.execute_delivery" backend/tests/webhooks/test_webhook_tasks.py`
returns only the docstring reference — no live patch sites remain.

---

### B2 — trial test patch target (`apps.tenants.tasks.send_trial_expiry_warning_email` → `apps.tenants.emails.send_trial_expiry_warning_email`)

**Confirmed root cause:** `apps/tenants/tasks.py:60` does
`from apps.tenants.emails import send_trial_expiry_warning_email` inside the
function body of `check_trial_expirations`.

**Fix:** patched at the source module in all three call sites:

- `backend/tests/tenants/test_trial_tasks.py:79` — `_run` helper (used by all
  7 deactivation tests).
- `backend/tests/tenants/test_trial_tasks.py:189` — `_run_with_mocked_email`
  helper (used by 4 of 5 warning-email tests).
- `backend/tests/tenants/test_trial_tasks.py:240` —
  `test_email_failure_does_not_abort_task` (the one that constructs its own
  patch context inline).

I left `_notify_super_admin_deactivations` patches at `apps.tenants.tasks.X`
unchanged — that helper is defined directly in `tasks.py` (line 79 of
production), so the existing patch path is correct.

I also re-audited `send_mail` patches in `NotifySuperAdminDeactivationsTestCase`:
`apps/tenants/tasks.py:9` does `from django.core.mail import send_mail` at
module top, so `patch("apps.tenants.tasks.send_mail", ...)` is correct and
needs no change.

Module docstring updated at
`backend/tests/tenants/test_trial_tasks.py:11-29` to document the
in-function-import gotcha.

**Verified:** `grep -n "apps.tenants.tasks.send_trial_expiry_warning_email"
backend/tests/tenants/test_trial_tasks.py` — only docstring/comment
references remain; no live patch sites.

---

### B3 — `test_with_invalid_logo_path_skips_gracefully`

**Confirmed root cause** (read `apps/progress/certificate_service.py`
end-to-end):

The try/except at lines 146-153 only wraps the `Image()` constructor — but
ReportLab does not actually open the file at construction time. The OSError
is raised later inside `doc.build(elements)` at line 189, which is *outside*
the guard.

**Resolution chosen: option 1 — pin the current production behavior.**

Replaced the test with `test_with_invalid_logo_path_raises_oserror` at
`backend/tests/progress/test_certificate_service.py:229-248`, which uses
`pytest.raises(OSError)` to assert the *actual* current behavior. The new
docstring explains why this is currently a defect, points at the production
line numbers, and tells future maintainers exactly how to flip the assertion
back if/when the production code is fixed.

**Filed paired production-bug card:**
`_coordination/inbox/backend-engineer/CERT-SERVICE-DOCBUILD-OSERROR-LEAK-2026-04-30.md`
with repro, root cause, source-line references, and a suggested fix
(pre-validate the path with `os.path.isfile(...)` before constructing
`Image`).

No production code was modified.

---

### B4 — `test_pdf_contains_teacher_name_bytes`

**Confirmed root cause:** ReportLab compresses content streams via
`/FlateDecode`, so the literal string `b"UniqueXYZTeacher"` does not appear
in the raw bytes.

**Resolution chosen: drop the test.** Reliable text-extraction would require
adding a PDF-decoding dependency (`pypdf` / `pdfminer`) just for this one
assertion, and the broader contract — *"the buffer is a valid PDF"* — is
already exercised by `test_buffer_is_seeked_to_start`,
`test_buffer_contains_pdf_header`, `test_buffer_has_non_zero_size`, and
`test_two_calls_produce_independent_buffers` (which proves teacher-name
input *does* affect output bytes).

The test class now has 11 methods (29 file-total tests, all passing).

---

### S1 — `test_retrying_status_triggers_self_retry` swallowed all exceptions

**Fix:** rewrote to use `with pytest.raises(Retry):` (from
`celery.exceptions`). No more catch-Exception-and-pass. The test now fails
loudly if the production task raises anything other than `Retry`.

`backend/tests/webhooks/test_webhook_tasks.py:148-179`. The post-raise
`refresh_from_db` + `assertEqual(status, "retrying")` confirms
`execute_delivery` was actually invoked and flipped the delivery state
before the retry was raised.

---

## Other reviewer notes (N1 / N2 / N3 / S2)

- **N1** (calling `deliver_webhook(id)` directly vs `.apply().get()`) —
  intentionally left as-is. The bound `self` reference inside the task body
  is reachable on direct invocation in pytest because Celery's `@shared_task`
  decorator returns a `Task` instance whose `__call__` binds `self`. With
  the patch targets corrected, all six DeliverWebhookTaskTestCase tests pass.
  Happy to convert to `.apply().get()` in a follow-up if you prefer — say
  the word.
- **N2** (helper duplication between `test_webhook_tasks.py` and
  `test_webhook_services.py`) — agreed, but extracting to
  `tests/webhooks/factories.py` is cleanly out-of-scope for this resubmit.
  Filing as a follow-up cleanup, not blocking this batch.
- **N3** — noted, no action required.
- **S2** (test count discrepancy) — reconciled. With B4 dropped and B3
  replaced, `TestGenerateCertificatePdf` now has 11 methods; file total is
  29 tests, all passing.

---

## Verification evidence

```
cd backend && .venv/bin/pytest \
    tests/webhooks/test_webhook_tasks.py \
    tests/tenants/test_trial_tasks.py \
    tests/progress/test_certificate_service.py \
    -q --reuse-db
...................................................................      [100%]
67 passed in 6453.93s (1:47:33)
```

(The first attempt failed with `OperationalError: deadlock detected` because
another agent's pytest session — `tests/webhooks/test_webhook_services.py
--no-migrations --create-db` running under PID 64312 — was concurrently
recreating the shared `test_lms_db`. Once that process exited, the run above
completed cleanly with zero failures.)

Files changed in this resubmit:
- `backend/tests/webhooks/test_webhook_tasks.py` — 4 patch-target fixes,
  S1 narrow exception, regression-prevention docstring.
- `backend/tests/tenants/test_trial_tasks.py` — 3 patch-target fixes (covers
  12 tests via two helpers + one inline), regression-prevention docstring.
- `backend/tests/progress/test_certificate_service.py` — B3 test rewritten
  to assert real behavior, B4 test removed.

Files NOT changed: `backend/tests/notifications/test_notification_views.py`
(your accepted notification additions are untouched), all production code.

— qa-tester
