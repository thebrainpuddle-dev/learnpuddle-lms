---
tags: [review, task/BE-FIX-REPORT-RUN-STATUS, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-28
---

# Review: BE-FIX-REPORT-RUN-STATUS — `fix_report_run_status` management command

## Verdict: APPROVE

## Summary
A clean, idiomatic Django data-repair command implementing Advisory #1 from the
prior delivery-status review. Scope is tight (3 files + 1 test file, no
production-code coupling), behaviour is safe (atomic, idempotent, tenant-scoped
flag), and the TDD suite covers happy path, no-op, dry-run, tenant filter,
invalid input, and idempotency. No critical or major issues found.

## Static facts verified

| Claim | Evidence |
|-------|----------|
| `ReportRun.STATUS_CHOICES` = pending/running/success/error (no `"failed"`) | `models.py:151-156` ✅ |
| `ReportRun.all_objects = models.Manager()` (plain Manager, not TenantManager) | `models.py:191` ✅ |
| Bug fix landed: every `run.status =` in `tasks.py` is now `running`/`success`/`error` | `tasks.py:66,91,99,113,120,249,274,379` — no `"failed"` anywhere ✅ |
| `delivery_failed` belongs to `ReportSchedule.STATUS_CHOICES`, not `ReportRun` | `models.py:91-96` ✅ — root-cause analysis is correct |
| Management package files present | `management/__init__.py` + `management/commands/__init__.py` ✅ |

## Critical Issues
None.

## Major Issues
None.

## Minor Issues

1. **Stale test docstring** — `tests_fix_report_run_status.py:14` says
   `Expected: 7 PASS` but the file actually contains **10** test methods.
   The review request also says "9 TDD tests" in the headline while the table
   below lists 10. Update both to `Expected: 10 PASS` to keep CI/runbook
   guidance accurate. (Cosmetic — not blocking.)

2. **`tenant_note` not echoed in dry-run line** — In `handle()`, the success
   message names the tenant scope (`(all tenants)` / `(tenant <uuid>)`), but
   the dry-run output (lines 99-103) does not. For an operator running
   `--dry-run --tenant-id <uuid>`, having the same scope echo would aid
   confidence. Trivial polish.

3. **Race window between `count()` and `update()`** — `count = qs.count()`
   (line 81) runs before `qs.update(status="error")` (line 108). They are
   two queries; `transaction.atomic()` brackets only the update, so a row
   inserted between the two reads would be updated but not reflected in the
   "Found {count}" stdout banner. Functionally correct (the operator-facing
   number is `updated` from the `UPDATE` itself, line 108), but the banner
   could mislead by 1-2 rows on a busy table. Use `qs.update(...)` and
   report only the returned `updated` count if you want to eliminate the
   race entirely. Genuinely minor — repair commands run rarely, and the
   command is idempotent.

## Positive Observations

- **Correct manager choice.** `all_objects` (plain `models.Manager()`) is
  exactly right for a shell/cron-invoked command — TenantManager's
  thread-local lookup would silently filter to nothing without a request
  context. The inline comment at lines 67-69 calls this out explicitly.
- **CommandError on bad UUID.** `--tenant-id not-a-valid-uuid` raises
  `CommandError` with a clear message rather than a Django stack trace.
  Good operator UX, and the test pins it.
- **Idempotency is explicit and tested.** `WHERE status="failed"` selects
  zero rows after first run; `test_idempotent_on_second_run` pins it.
- **Dry-run is genuinely a preview.** `test_dry_run_does_not_write` asserts
  the row stays at `"failed"` after `--dry-run`, catching the classic
  "dry-run flag set but write still happens" bug.
- **Tenant isolation is verified directly.** `test_tenant_filter_limits_update`
  asserts tenant A's row updates AND tenant B's row stays `"failed"` —
  pinning both halves of the contract.
- **Docstring traces the audit trail.** Module docstring cites the prior
  review verdict, the bug location, and the patch date. Future archaeology
  is much easier.
- **No production code touched.** This command is purely additive — it
  cannot break existing flows. Risk profile is essentially zero.

## Recommendation

**APPROVE — merge as-is.** The three minor items are cosmetic / docstring
polish and can be folded into the next sweep without holding this up.

Suggested operator runbook entry (already implied by the docstring, but
worth surfacing):

```
# After deploying the tasks.py fix, run once per environment:
python manage.py fix_report_run_status --dry-run    # preview
python manage.py fix_report_run_status              # apply
# Verify:
python manage.py shell -c \
  "from apps.reports_builder.models import ReportRun; \
   print(ReportRun.all_objects.filter(status='failed').count())"
# Expected: 0
```

— lp-reviewer
