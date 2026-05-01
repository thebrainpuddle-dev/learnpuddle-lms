# TASK-065: Excel (XLSX) Export for Report Builder

**Priority:** P2 (Feature)
**Phase:** 3 (Analytics)
**Status:** in-progress
**Assigned:** backend-engineer
**Estimated:** 3-4 hours

## Problem

The Custom Report Builder (TASK-053) supports CSV export only. The master strategy
Phase 2 ("Compete", Months 4-6) lists **"CSV/PDF/Excel export"** as a required analytics
feature. Enterprise admins expect to open reports directly in Excel without a conversion step.

## Fix Required

Add `.xlsx` as a first-class export format alongside the existing `.csv` format.

### 1. `backend/requirements.txt`
Add `openpyxl>=3.1.0` (Excel writer, BSD-licensed, no binary dependencies).

### 2. `backend/apps/reports_builder/query_engine.py`
Add `rows_to_xlsx(rows)` function:
```python
def rows_to_xlsx(rows: list[dict]) -> tuple[bytes, str]:
    """Serialise *rows* to .xlsx bytes using openpyxl. Returns (xlsx_bytes, sha256_hex)."""
```
- Creates a workbook with one sheet ("Report")
- Writes header row (bold) + data rows
- Returns (bytes, sha256_hex) matching the `rows_to_csv` signature

### 3. `backend/apps/reports_builder/models.py`
Add `artifact_format` field to `ReportRun`:
```python
ARTIFACT_FORMAT_CHOICES = [("csv", "CSV"), ("xlsx", "Excel")]
artifact_format = models.CharField(max_length=4, choices=ARTIFACT_FORMAT_CHOICES, default="csv", blank=True)
```

### 4. `backend/apps/reports_builder/migrations/0002_reportrun_artifact_format.py`
Add the migration for the new field.

### 5. `backend/apps/reports_builder/tasks.py`
- Update `_artifact_path(run_id, fmt="csv")` to support `.xlsx` suffix
- Add `build_xlsx_export(run_id)` Celery task mirroring `build_csv_export`

### 6. `backend/apps/reports_builder/views.py`
- `definition_export`: accept `?format=xlsx` query param; dispatch `build_xlsx_export`
  instead of `build_csv_export` when `format=xlsx`; store `export_format` in
  `params_snapshot_json`; set `run.artifact_format = "xlsx"` before enqueueing
- `run_artifact`: detect format from `run.artifact_format` and serve with correct
  Content-Type (`application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
  for `.xlsx`)

## Files to Modify

| File | Action |
|------|--------|
| `backend/requirements.txt` | Add `openpyxl>=3.1.0` |
| `backend/apps/reports_builder/query_engine.py` | Add `rows_to_xlsx()` |
| `backend/apps/reports_builder/models.py` | Add `artifact_format` field |
| `backend/apps/reports_builder/migrations/0002_reportrun_artifact_format.py` | NEW migration |
| `backend/apps/reports_builder/tasks.py` | Update `_artifact_path`, add `build_xlsx_export` |
| `backend/apps/reports_builder/views.py` | Update `definition_export` + `run_artifact` |
| `backend/tests/reports_builder/test_xlsx_export.py` | NEW test file |

## Acceptance Criteria

- [ ] `POST /api/v1/admin/reports/definitions/{id}/export/?format=xlsx` returns 202 with `run_id`
- [ ] `POST /api/v1/admin/reports/definitions/{id}/export/` (no format param) still returns CSV (backward compat)
- [ ] `POST /api/v1/admin/reports/definitions/{id}/export/?format=invalid` returns 400
- [ ] XLSX artifact has valid `.xlsx` bytes (starts with PK magic bytes)
- [ ] `run_artifact` serves XLSX with `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
- [ ] `run_artifact` serves CSV with `text/csv` (backward compat)
- [ ] Empty rows → valid XLSX file (header-only sheet, no crash)
- [ ] Rate limit shared between CSV and XLSX exports (existing 20/hr/tenant)
- [ ] Audit log: `action="EXPORT_REPORT"` for both formats (existing audit_log call)
- [ ] `ReportRun.artifact_format` tracks the format
- [ ] All tests pass

## Not in Scope

- PDF tabular export (requires richer layout work — tracked as TASK-066)
- Scheduled report delivery in XLSX format (follow-up: update `execute_scheduled_report`)
