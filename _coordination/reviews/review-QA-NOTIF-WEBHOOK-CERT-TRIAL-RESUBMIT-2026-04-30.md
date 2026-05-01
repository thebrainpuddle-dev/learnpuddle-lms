---
tags: [review, task/QA-NOTIF-WEBHOOK-CERT-TRIAL, verdict/approve, reviewer/lp-reviewer, resubmit]
created: 2026-04-30
---

# Review: QA-NOTIF-WEBHOOK-CERT-TRIAL Resubmit — Test-only fixes (B1–B4 + S1)

## Verdict: APPROVE

## Summary
All four blockers and the should-fix from the 2026-04-29/30 verdict are addressed. Patch targets correctly point at the *source* modules (where the symbol is defined), not the consumer modules that re-import inside function bodies — the docstring blocks added at the top of both test files explain the in-function-import gotcha so future maintainers don't "correct" it back. S1's silent exception swallow is replaced with `with pytest.raises(Retry):`. B3 evolved further than originally proposed: the paired bug card filed to backend-engineer led to a real production fix (BE-CERT-SERVICE-LOGO-PREVAL, approved separately today), so the test now asserts the *fixed* behavior (`test_with_invalid_logo_path_skips_gracefully`) rather than pinning the bug — a strictly better outcome.

## Critical Issues
None.

## Major Issues
None.

## Minor Issues

1. **N1 left as-is (`deliver_webhook(id)` direct invocation).** Author notes that the bound-`self` reference works under pytest because `@shared_task` returns a `Task` instance whose `__call__` binds. Pragmatically fine; convention in the rest of the suite is `.apply().get()` for slightly more realistic dispatch semantics. If you do refactor the helper, add it as a non-blocking follow-up — not a re-review trigger.

2. **N2 helper duplication acknowledged, deferred.** Extracting shared fixtures into `tests/webhooks/factories.py` is the right move for the next sweep. Not blocking this verdict.

3. **B3 description in the resubmit is now stale.** The resubmit text says it "replaced the test with `test_with_invalid_logo_path_raises_oserror`" pinning the bug. The actual file (verified) has `test_with_invalid_logo_path_skips_gracefully` because the production fix landed. Worth a one-line note in the next coordination log so the timeline is unambiguous — not a code issue, just a documentation drift.

## Positive Observations

- **B1 fix correctly traces the in-function import.** `apps/webhooks/tasks.py:28` does `from .services import execute_delivery` *inside the function*, so the patchable symbol lives at `apps.webhooks.services.execute_delivery`. All 4 sites (`test_webhook_tasks.py:114, 135, 174, 196`) now point at the correct module — verified via grep.
- **B2 fix follows the same pattern correctly.** `apps/tenants/tasks.py:60` re-imports `send_trial_expiry_warning_email` inside `check_trial_expirations`, so patches must target `apps.tenants.emails.send_trial_expiry_warning_email`. All 3 patch sites (`test_trial_tasks.py:84, 197, 248`) updated. Verified via grep — no live patches at the wrong target remain.
- **Module docstrings document the gotcha.** Lines 11-26 of `test_webhook_tasks.py` and 11-29 of `test_trial_tasks.py` explicitly explain why patches target the source module. This is the right kind of "regression-prevention via comments" — it stops the next reviewer from "fixing" it back.
- **`_notify_super_admin_deactivations` patches correctly *not* changed.** The author audited and noted the helper is defined directly in `tasks.py`, so its patches stay at `apps.tenants.tasks.X`. Same for `send_mail` — module-top import, correct target. That precision matters.
- **S1 replaced fake-pass with real assertion.** `with pytest.raises(Retry):` (verified at `test_webhook_tasks.py:176`) — test now fails loudly if the production task raises anything other than `Retry`, *and* the post-raise `refresh_from_db` confirms `execute_delivery` actually ran and flipped state before the retry was triggered.
- **B4 removed responsibly.** `test_pdf_contains_teacher_name_bytes` was relying on an assumption (literal text in raw PDF bytes) that is wrong under `/FlateDecode`. Adding a PDF-parsing dependency just for one assertion is the wrong trade-off; the existing `test_two_calls_produce_independent_buffers` already proves teacher-name input affects output bytes. Right call.
- **No production code touched.** Author explicitly confirms zero production changes in this resubmit. Test-only scope held.
- **B3 outcome surpassed expectations.** Filing the paired bug card to backend-engineer was the right move — instead of pinning a bug, we got a fix *and* a test that asserts the fix. That's a feature of the QA→BE handoff, not a bug.

## Verification Performed

- Confirmed `apps.webhooks.services.execute_delivery` is the patch target at `test_webhook_tasks.py:114, 135, 174, 196`. No live `apps.webhooks.tasks.execute_delivery` patches remain.
- Confirmed `apps.tenants.emails.send_trial_expiry_warning_email` is the patch target at `test_trial_tasks.py:84, 197, 248`. No live `apps.tenants.tasks.send_trial_expiry_warning_email` patches remain.
- Confirmed `with pytest.raises(Retry):` at `test_webhook_tasks.py:176`.
- Confirmed `test_with_invalid_logo_path_skips_gracefully` exists at `test_certificate_service.py:229` — production behavior is fixed (BE-CERT-SERVICE-LOGO-PREVAL approved today), so this test now asserts the fix rather than pinning the bug.
- Author reports `67 passed in 6453.93s (1:47:33)` — the wall time is dominated by a concurrent test-DB session, not the tests themselves. Acceptable.

## Notes for Author

- The N1/N2 follow-ups are tracked. No need to revisit unless touching those files for unrelated reasons.
- For future resubmits where a separately-tracked production fix lands between submit and resubmit, add a one-line note ("Note: B3 outcome superseded by BE-CERT-SERVICE-LOGO-PREVAL — the test now asserts the fixed behavior, not the original bug") so reviewers can reconcile the two threads at a glance.

— lp-reviewer
