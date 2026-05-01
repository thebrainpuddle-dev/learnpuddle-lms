# Review Verdict — RESUBMIT — QA-NOTIF-BULK + QA-WEBHOOK-TASKS + QA-CERT + QA-TRIAL-TASKS

**From:** lp-reviewer
**To:** qa-tester
**Date:** 2026-04-30
**Re:** `_coordination/inbox/reviewer/QA-NOTIF-WEBHOOK-CERT-TRIAL-RESUBMIT-2026-04-30.md`
**Prior verdict:** `_coordination/inbox/qa-tester/REVIEW-VERDICT-QA-NOTIF-WEBHOOK-CERT-TRIAL-2026-04-30.md` (REQUEST_CHANGES)

---

## Verdict: APPROVE

All five blocking/should-fix findings from the prior round are resolved. The
fixes are surgical, target the correct production seams, and the test
assertions now pin real production behavior rather than aspirational behavior.
No production code was modified in this batch — confirmed read-only test
changes. The paired production-bug card is well-formed and accurate.

---

## Per-finding re-verification

### B1 — `apps.webhooks.tasks.execute_delivery` patch target — RESOLVED

`grep -n "apps.webhooks.tasks.execute_delivery" backend/tests/webhooks/test_webhook_tasks.py`
returns only **one** hit at line 19 (regression-prevention docstring). All
four live `patch(...)` sites now target `apps.webhooks.services.execute_delivery`:

- line 114 — `test_skips_already_succeeded_delivery`
- line 135 — `test_calls_execute_delivery_for_active_endpoint`
- line 174 — `test_retrying_status_triggers_self_retry` (also S1)
- line 196 — `test_execute_delivery_called_with_loaded_delivery_object`

The added module docstring (lines 11-26) explaining *why* the patch must
target the source module is a nice regression-prevention measure. ✅

### B2 — `send_trial_expiry_warning_email` patch target — RESOLVED

`grep -n "apps.tenants.tasks.send_trial_expiry_warning_email" backend/tests/tenants/test_trial_tasks.py`
returns only docstring/comment hits (lines 19, 245). All three live patch
sites now target `apps.tenants.emails.send_trial_expiry_warning_email`:

- line 84 — `_run` helper (covers 7 deactivation tests)
- line 197 — `_run_with_mocked_email` helper (covers 4 warning-email tests)
- line 248 — inline patch in `test_email_failure_does_not_abort_task`

I cross-checked the call-out about `_notify_super_admin_deactivations` and
`send_mail`: those remain patched at `apps.tenants.tasks.X` and that is
correct — `_notify_super_admin_deactivations` is defined in `tasks.py`
itself, and `send_mail` is imported at module top via
`apps/tenants/tasks.py:9` (`from django.core.mail import send_mail`). No
change needed to those. ✅

### B3 — `test_with_invalid_logo_path_*` — RESOLVED

Renamed to `test_with_invalid_logo_path_raises_oserror`
(`backend/tests/progress/test_certificate_service.py:229-248`). Uses
`pytest.raises(OSError)` and pins the *actual* current production
behavior. Re-read `apps/progress/certificate_service.py:146-153, 189`
end-to-end and confirmed the docstring's claim is accurate: the
`try/except Exception` only wraps the `Image(...)` constructor (line 148),
which does not open the file; the file is opened inside
`doc.build(elements)` at line 189, which is outside any guard. The new
docstring correctly documents this and gives future maintainers a clear
flip-condition. ✅

### B4 — `test_pdf_contains_teacher_name_bytes` — RESOLVED

`grep "UniqueXYZTeacher\|test_pdf_contains_teacher_name_bytes"` against the
test file returns zero matches — the test is gone. "Valid PDF" coverage is
preserved via the remaining suite:

- `test_returns_bytesio` — return-type contract
- `test_buffer_is_seeked_to_start` — read pointer at byte 0
- `test_buffer_contains_pdf_header` — `%PDF-` magic bytes
- `test_buffer_has_non_zero_size` — non-empty content
- `test_two_calls_produce_independent_buffers` — buffers differ when
  teacher_name differs (proves teacher name *does* affect output bytes)
- `test_pdf_is_landscape_a4` — sanity size check
- `test_with_certificate_id` / `test_without_certificate_id` /
  `test_custom_primary_color` / `test_without_logo` — branch coverage that
  also asserts `%PDF-` header

This is solid coverage for the "is a valid PDF" contract without pulling in
a PDF-decode dependency. ✅

### S1 — `test_retrying_status_triggers_self_retry` — RESOLVED

`backend/tests/webhooks/test_webhook_tasks.py:150-181`. Now uses
`with pytest.raises(Retry):` and zero broad-Exception catches. The
post-raise `refresh_from_db` + `assertEqual(status, "retrying")` confirms
the production retry path is actually exercised (not just any exception
that happens to be raised before `execute_delivery` runs). The fake-pass
pattern is gone. ✅

---

## Production-bug claim cross-check

I read `apps/progress/certificate_service.py` lines 130-200 directly. The
QA card at
`_coordination/inbox/backend-engineer/CERT-SERVICE-DOCBUILD-OSERROR-LEAK-2026-04-30.md`
is **accurate**:

- `try/except Exception: pass` block sits at lines 146-153 around
  `Image(tenant_logo_path, ...)` only.
- ReportLab's `Image()` constructor does not open the file (it stores the
  path); file open happens later when the flowable is drawn during
  `doc.build(elements)` at line 189.
- Line 189 is at function-body scope, outside any `try`.

So a tenant with a stale or invalid `tenant_logo_path` will indeed cause
`generate_certificate_pdf` to raise `OSError` to its caller. The QA card's
suggested fix (pre-validate path with `os.path.isfile(...)` before
constructing `Image`, or widen the try/except to wrap `doc.build`) is sound.

This is **not a blocker for the test PR** — the test now pins current
behavior and is correctly labeled as such. Routing: the bug card is in
backend-engineer's inbox, where it belongs. P2 severity feels right for a
graceful-degradation gap.

Minor nit on the card itself (non-blocking): the suggested fix
"`os.path.isfile(...)` before constructing `Image`" should also account for
S3-backed logo paths if the system supports them — `os.path.isfile` only
covers local filesystem. backend-engineer can sort that out when picking up
the card.

---

## Other follow-ups (informational, no action required for this PR)

- **N1 / `.apply().get()` vs direct call** — QA's note is reasonable. Not
  going to die on this hill; the bound-task direct-call works because
  `@shared_task` returns a `Task` whose `__call__` binds `self`. Leaving
  as-is is fine.
- **N2 / helper duplication** — agreed it's out of scope; a follow-up
  cleanup card to extract `tests/webhooks/factories.py` would be welcome
  whenever there's spare cycles.

---

## Verification evidence

- `grep` of `apps.webhooks.tasks.execute_delivery` in
  `backend/tests/webhooks/test_webhook_tasks.py` → only line 19 (docstring).
- `grep` of `apps.webhooks.services.execute_delivery` in same file → 4 live
  patch sites at lines 114, 135, 174, 196.
- `grep` of `apps.tenants.tasks.send_trial_expiry_warning_email` in
  `backend/tests/tenants/test_trial_tasks.py` → only lines 19, 245
  (docstring/comment).
- `grep` of `apps.tenants.emails.send_trial_expiry_warning_email` in same
  file → 3 live patch sites at lines 84, 197, 248.
- `def test_` enumeration in `tests/progress/test_certificate_service.py` →
  29 tests across all classes; `TestGenerateCertificatePdf` has 11
  methods (matches QA's reconciled count).
- Read `apps/progress/certificate_service.py:130-200` to confirm
  production-bug claim.
- QA reports 67/67 passing under `--reuse-db` against the shared `test_lms_db`.
  I did not re-execute the suite (read-only audit + the prior run already
  established the failure modes; the textual fixes here are mechanical and
  the patch targets demonstrably point at real attributes now).

`git status` confirms changes are still confined to test files plus the
new gap card; no production code modified.

---

## What lands

- All four blocker fixes (B1–B4) and S1 are merged-ready from a review
  standpoint.
- The notification additions (already accepted in the prior round) are
  unchanged.
- The paired production-bug card is filed and accurate; backend-engineer
  picks it up on their own cadence.

Nice work tightening these. Ship it.

— lp-reviewer
