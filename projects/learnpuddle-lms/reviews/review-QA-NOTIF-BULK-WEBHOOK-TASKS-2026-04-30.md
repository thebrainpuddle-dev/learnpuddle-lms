---
tags: [review, task/QA-NOTIF-BULK, task/QA-WEBHOOK-TASKS, task/QA-CERT-SERVICE, task/QA-TENANT-TRIAL, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-30
---

# Review: QA-NOTIF-BULK-FIXUP + QA-WEBHOOK-TASKS-COVERAGE + QA-CERTIFICATE-SERVICE-COVERAGE + QA-TENANT-TRIAL-TASKS-COVERAGE

## Verdict: APPROVE

## Summary

Four test-only deliverables in one batch — three new files (~983 LOC) plus an
extension to the notifications view tests. All four address the modules the
2026-04-29 review verdicts flagged as 0%-coverage. Test design is consistent
with the rest of the suite (TestCase + `_make_*` helpers + scoped patches),
contracts are verified against source, and the previously misleading
"cross-tenant" docstring in `NotificationBulkMarkReadTestCase` is corrected.

There are a few minor coverage and assertion-tightness issues below, but none
of them block. The tests as written would all catch real regressions in the
modules they cover.

The qa-tester correctly disclosed that they could not run the suite locally
(no Docker in the sandbox). Static review against source confirms the
invariants asserted are the right ones; CI will be the runtime gate.

## Critical Issues

None.

## Major Issues

None.

## Minor Issues

### m1 — `apps/tenants/tasks.py` 1-day and 0-day warnings are uncovered

The source iterates over `(7, 3, 1, 0)` warning windows
(`apps/tenants/tasks.py:62`):

```python
for days in (7, 3, 1, 0):  # Added day 1 and day 0 (expiry day) warnings
```

The new test class `CheckTrialExpirationsWarningEmailTestCase` covers only the
`7` and `3` windows. If someone removes `1` or `0` from the tuple (or breaks
the boundary check for them), no test fails. Two more tests of the same shape
as `test_sends_warning_email_7_days_before_expiry` would close this — please
add as a follow-up:

```python
def test_sends_warning_email_1_day_before_expiry(self): ...
def test_sends_warning_email_on_expiry_day(self): ...   # days=0
```

### m2 — `test_retrying_status_triggers_self_retry` swallows all exceptions

`tests/webhooks/test_webhook_tasks.py:147-160`:

```python
try:
    deliver_webhook(str(self.delivery.id))
except Retry:
    pass  # Expected — task re-queued itself
except Exception as exc:
    # In eager mode the retry itself may raise; still counts as success
    # as long as execute_delivery was called
    pass
```

The bare `except Exception:` defeats the test — a `TypeError` from a future
signature change, an `AttributeError` from a removed model field, or any
unrelated bug raising in this branch will all silently pass. Tighten to:

```python
try:
    deliver_webhook(str(self.delivery.id))
except Retry:
    pass  # The only acceptable exception
```

If the task **must** be allowed to raise something other than `Retry` in
eager mode, name that specific exception instead of catching `Exception`.
The post-call assertion (`self.delivery.status == 'retrying'`) is a good
behavioural check, but it pairs with — not replaces — the right exception
shape.

### m3 — Cleanup test does not exercise the boundary

`test_uses_default_30_day_window` uses a 31-day-old record. Add a sibling
test for the boundary itself (29 days old → preserved; exactly 30 days old →
behaviour follows source). Source uses `created_at__lt=cutoff`, so a record
created exactly at `now - 30 days` should be preserved, not deleted. Worth
asserting explicitly because off-by-one bugs here are silent (the only
visible symptom is "we deleted records earlier than we said we would").

### m4 — Cross-tenant test uses `_make_user` for tenant B without exercising the SCIM/role default

`test_bulk_mark_read_does_not_affect_other_tenant_notifications` makes both
teachers via the same `_make_user` helper. Looks correct, but if the helper
defaults to `role='SCHOOL_ADMIN'` and the view path requires `TEACHER` or
similar, a future change to the helper default could mask a legitimate
permission failure. Not a current bug — just worth threading `role='TEACHER'`
explicitly in the cross-tenant test for self-documentation.

### m5 — Idempotency test uses two POSTs in the same TestCase setUp state

The new `test_bulk_mark_read_is_idempotent` is correct, but worth adding one
more assertion: after the second call, `read_at` must not change (the source
filters on `is_read=False` so the `update(read_at=now)` should be a no-op).
Capture `notif1.read_at` after the first POST and assert equality after the
second — gives one more signal if someone "fixes" the filter to update `read_at`
on every call.

### m6 — Static verification only (acknowledged in the request)

The qa-tester explicitly notes Docker isn't available, so none of the new
tests have actually run. Patterns and contracts look right; the bound-Celery
direct-invocation pattern (`deliver_webhook(str(self.delivery.id))`) relies on
the `task_always_eager=True` set by the session fixture in `conftest.py:307-319`
— I read that fixture and it does run in autouse session scope, so the
direct-call pattern should work. But please run the suite once before this
batch lands so we don't discover a bound-task signature surprise after merge.

```bash
docker compose exec web pytest \
  tests/notifications/test_notification_views.py::NotificationBulkMarkReadTestCase \
  tests/webhooks/test_webhook_tasks.py \
  tests/progress/test_certificate_service.py \
  tests/tenants/test_trial_tasks.py -v
```

(That's the qa-tester's own suggested command — just confirming I'd want to
see the green output before stamping.)

## Positive Observations

- **Cross-tenant isolation test is the right shape.** The two-tenant test
  (`test_bulk_mark_read_does_not_affect_other_tenant_notifications`) creates
  a real second `Tenant`, a real second `User`, a real second `Notification`,
  and submits *both* IDs in the same POST body — exercising the actual filter
  in the view (`teacher=request.user, tenant=request.tenant`). This is how
  cross-tenant tests should be written, not via mocking.
- **Docstring fix is exactly right.** The previous "Cross-tenant safety"
  docstring on the cross-teacher test was misleading — the new
  "Cross-teacher isolation (same tenant)" wording matches what the test
  actually does, and the new test fills the cross-tenant gap. Good response
  to the previous review's Minor #1.
- **Idempotency mirrors the existing `test_bulk_archive_is_idempotent`.** The
  symmetry is helpful — if someone breaks the `is_read=False` filter, both
  the mark-read and the archive idempotency tests will fail in the same way,
  pointing at the same root cause.
- **Webhook task tests cover all five branches** of `deliver_webhook`
  (DoesNotExist / already success / inactive endpoint / active+pending /
  retrying), and assert the right behaviour for each branch (return shape,
  status field on the delivery, `execute_delivery` mock call count). The
  source-line annotations in the request make it cheap to verify each test
  is targeting the right line range.
- **`cleanup_old_deliveries` correctly preserves `retrying` and `pending`.**
  Easy bug to introduce — "let's also clean up old retrying records" — and
  the test catches it. Good defensive coverage.
- **Certificate-service tests correctly avoid Django DB** for the pure helper
  functions (`hex_to_rgb`, `get_certificate_filename`) and scope DB usage to
  the actual ReportLab buffer generation. Keeps the tests fast.
- **Trial-task tests use the right mocking pattern** — `mock_now.date.return_value`
  is the contract `tasks.py:32` uses (`timezone.now().date()`), not a global
  `freeze_time`. This means the test won't break if a future change uses
  `timezone.now()` without `.date()` — instead it'll fail loudly because
  the mock will return the MagicMock proxy and the comparison will surprise
  the developer. That's the right shape for a test of date-boundary code.
- **`_notify_super_admin_deactivations` tests probe `send_mail` positional args
  by index** which is fragile in general, but correct here because the source
  uses positional args. If the source migrates to keyword args, these tests
  fail loud — which is exactly what you want.

## Verification I performed

- Read `tests/notifications/test_notification_views.py` diff (≈290 lines added).
- Read `tests/webhooks/test_webhook_tasks.py` end-to-end (408 lines) and cross-
  referenced every test against `apps/webhooks/tasks.py` (the file is 98 lines).
- Read `tests/tenants/test_trial_tasks.py` (311 lines) and cross-referenced
  against `apps/tenants/tasks.py:1-116`. Confirmed:
  - `TRIAL_GRACE_PERIOD_DAYS = 3` is read from the module rather than
    hard-coded.
  - The deactivation filter is `trial_end_date__lt=deactivation_cutoff` —
    matches the boundary test (`grace_period_days_ago` stays active).
  - `_notify_super_admin_deactivations` calls `send_mail(subject, message,
    from_email, [admin_email], fail_silently=True)` — positional-arg test
    indices match.
  - The source loops over `(7, 3, 1, 0)` — see m1 above for the gap.
- Read `tests/progress/test_certificate_service.py` opening 120 lines —
  shape and assertion strategy match the rest of the suite.
- Confirmed `task_always_eager=True` session fixture in `conftest.py:307-319`
  applies before these tests run, so the direct-call pattern for bound
  tasks (`deliver_webhook(delivery_id)` without `.delay()`) is the right
  pattern in this codebase.
- Confirmed `apps/notifications/views.py:128-133` filter shape:
  `teacher=request.user, tenant=request.tenant, is_read=False` — both
  cross-teacher and cross-tenant tests target this exact filter.

— lp-reviewer
