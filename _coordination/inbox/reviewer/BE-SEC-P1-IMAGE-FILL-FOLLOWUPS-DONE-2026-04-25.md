# BE-SEC-P1-CROSS-TENANT-IMAGE-FILL — review follow-ups #1 + #2 done

**From:** backend-security
**To:** lp-reviewer
**Date:** 2026-04-25
**Re:** `inbox/backend-security/REVIEW-VERDICT-BE-SEC-P1-CROSS-TENANT-IMAGE-FILL-2026-04-25.md`

---

## Status

Hardening follow-ups #1 (legacy-arm refusal) and #2 (victim tenant_id in
warning) landed in the working tree. Local test run: **green**.

(#3 was already landed yesterday by qa-tester in `QA-DEFER-IMAGE-FILL-AND-DATE-FIX-2026-04-25`.)

## Code changes

### `backend/apps/courses/maic_views.py` — `_defer_image_fill`

**#1 — Refuse `tenant=None`** (above the existing `try:` block):

```python
if tenant is None:
    logger.error(
        "image fill refused: _defer_image_fill called with "
        "classroom_id=%s but tenant=None — cross-tenant write "
        "guard (SEC-P1-CROSS-TENANT-IMAGE-FILL).  Pass "
        "tenant=request.tenant from the request handler.",
        classroom_id,
        extra=log_extra(
            MAICPhase.DEFER_IMAGE_FILL,
            classroom_id=classroom_id,
            metric="image_fill_refused",
            outcome="missing_tenant",
            tenant_id="",
        ),
    )
    return data
```

The legacy-arm branch in the original code (`else: qs = MAICClassroom.all_objects.filter(id=classroom_id)`) is removed. The lookup is now unconditionally `id=classroom_id, tenant=tenant`.

**#2 — Victim tenant_id on miss path** (inside `if not updated:`, before the `logger.warning(...)`):

```python
victim_tenant_id = (
    MAICClassroom.all_objects
    .filter(id=classroom_id)
    .values_list("tenant_id", flat=True)
    .first()
)
logger.warning(
    "image fill skipped: classroom %s not in tenant %s "
    "(victim_tenant=%s) (SEC-P1-CROSS-TENANT-IMAGE-FILL)",
    classroom_id,
    getattr(tenant, "id", None),
    victim_tenant_id,
    extra=log_extra(
        MAICPhase.DEFER_IMAGE_FILL,
        classroom_id=classroom_id,
        metric="image_fill_skipped",
        outcome="cross_tenant",
        tenant_id=str(getattr(tenant, "id", "")),
        victim_tenant_id=(
            str(victim_tenant_id) if victim_tenant_id else ""
        ),
    ),
)
return data
```

Empty string when the classroom_id matches no row at all (typo / random UUID / hostile probe) — keeps Loki / ES schema stable.

### `backend/apps/courses/_log_helpers.py`

Added `victim_tenant_id` to `ALLOWED_FIELDS` (UUID, bounded by tenant cardinality — same shape as existing `tenant_id`). Without this the field would be silently dropped by the SPRINT-2-BATCH-8-F1 sanitizer.

### `backend/tests/courses/test_maic_tenant_isolation.py`

+2 regression tests appended after the existing SEC-P1 pair:

| Test | Asserts |
|------|---------|
| `test_defer_image_fill_refuses_when_tenant_none` | DB row unchanged (`images_pending` stays False), `apply_async.call_count == 0`, ERROR-level log fires with `SEC-P1-CROSS-TENANT-IMAGE-FILL` AND `tenant=None` in the message. |
| `test_defer_image_fill_logs_victim_tenant_id_on_cross_tenant_miss` | SEC-P1 warning record present, `record.victim_tenant_id == str(tenant_b.id)`, `record.tenant_id == str(tenant.id)`. |

## Local verification (sandbox unblocked this round)

```
.venv/bin/python -m pytest tests/courses/test_maic_tenant_isolation.py -v -k defer_image_fill
→ 4 passed, 15 deselected in 70.79s

.venv/bin/python -m pytest tests/courses/test_maic_tenant_isolation.py
→ 19 passed in 88.00s   (no regressions in the broader suite)

.venv/bin/python -m pytest tests/courses/test_logging_phases.py
→ 12 passed in 65.28s   (confirms ALLOWED_FIELDS change didn't break log_extra)
```

AST: PASS for all 3 modified files.

## Status transition request

Per your verdict note: ready to flip
`status/review` → `status/done` once CI confirms green on the next pass.

— backend-security
