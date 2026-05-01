# Review Request — fix_report_run_status management command

**From:** backend-engineer
**To:** reviewer
**Date:** 2026-04-28
**Related:** `REVIEW-VERDICT-BE-REPORT-BUILDER-DELIVERY-STATUS-2026-04-28.md` (Advisory #1)

---

## Summary

Implements the data-integrity repair management command you suggested in the
Report Builder delivery-status review (Advisory #1: "Stale data sweep — consider
a one-off data-migration / management command to update them to 'error'").

The 2026-04-28 patch fixed the code bug (`run.status = "failed"` →
`"error"`), but rows written before the patch still carry the invalid
`"failed"` value.  This command repairs them.

---

## Files changed

| File | Action |
|------|--------|
| `backend/apps/reports_builder/management/__init__.py` | New (empty — Django package) |
| `backend/apps/reports_builder/management/commands/__init__.py` | New (empty — Django package) |
| `backend/apps/reports_builder/management/commands/fix_report_run_status.py` | New (command) |
| `backend/apps/reports_builder/tests_fix_report_run_status.py` | New (9 TDD tests) |

---

## Command API

```bash
# Preview (no writes)
python manage.py fix_report_run_status --dry-run

# Apply (all tenants)
python manage.py fix_report_run_status

# Apply (single tenant — staged rollout)
python manage.py fix_report_run_status --tenant-id <uuid>
```

---

## Design decisions

1. **`all_objects` manager** — The command uses `ReportRun.all_objects`
   (plain `models.Manager()`) rather than `TenantManager`, so it is safe
   to run from a management shell or cron job without a request context
   (no thread-local current-tenant set).

2. **`transaction.atomic()` on the update** — All-or-nothing; a partial
   failure rolls back.

3. **`--dry-run` flag** — Operators can preview the affected row count
   before committing writes.

4. **`--tenant-id` filter** — Supports staged rollout: fix one tenant,
   verify, then proceed to the next.

5. **Idempotent** — The WHERE clause is `status="failed"`.  After a
   successful run, no rows match, so subsequent runs are clean no-ops.

---

## TDD tests (9 cases in `TestFixReportRunStatusCommand`)

| Test | Contract |
|------|----------|
| `test_updates_failed_rows_to_error` | Core: 'failed' → 'error' |
| `test_updates_all_failed_rows_across_tenants` | Cross-tenant sweep |
| `test_stdout_reports_count_updated` | Stdout mentions count |
| `test_no_op_when_table_clean` | Valid rows untouched |
| `test_no_op_stdout_message` | "nothing to do" message |
| `test_dry_run_does_not_write` | --dry-run skips DB write |
| `test_dry_run_stdout_mentions_count` | Dry-run previews count |
| `test_tenant_filter_limits_update` | --tenant-id scopes correctly |
| `test_invalid_tenant_id_raises_command_error` | Invalid UUID → CommandError |
| `test_idempotent_on_second_run` | Second run is safe no-op |

---

## Static verification

All imports, model field references, and test assertions verified by static
analysis (Explore agent).  Summary:

- `ReportRun.STATUS_CHOICES` confirmed: `("pending", "running", "success", "error")` ✅
- `ReportRun.all_objects = models.Manager()` (not TenantManager) ✅
- `ReportDefinition.all_objects = models.Manager()` ✅
- Management package `__init__.py` files present ✅
- Test `_tenant()` helper fields match `Tenant` model signature ✅

Docker run (when sandbox available):
```bash
docker compose exec web pytest \
  apps/reports_builder/tests_fix_report_run_status.py -v
# Expected: 9 passed
```

— backend-engineer
