# BE-SEC-P1-CROSS-TENANT-IMAGE-FILL — Fix ready for review

**From:** backend-security
**To:** reviewer (lp-reviewer)
**Date:** 2026-04-25
**Severity:** P1 — Cross-Tenant Write (multi-tenant isolation invariant violation)

---

## Summary

While doing a proactive audit of uncommitted MAIC scene-content changes
(`backend/apps/courses/maic_views.py`, ~551 LOC of additions), I found a
cross-tenant write surface in the image-fill deferral helper.

`_defer_image_fill` writes `images_pending=True` to a classroom row whose
PK is **body-supplied** (`request.body['classroomId']`), without scoping
the lookup by `request.tenant`. Both call sites use it:

- `teacher_maic_generate_scene_content` (POST `/api/v1/teacher/maic/generate/scene-content/`)
- `student_maic_generate_scene_content` (POST `/api/v1/student/maic/generate/scene-content/`)

A teacher in Tenant A can submit Tenant B's classroom UUID and:

1. Flip `images_pending=True` on Tenant B's classroom row, **and**
2. Enqueue a `fill_classroom_images` Celery task referencing Tenant B's
   classroom.

The task itself self-protects via `MAICClassroom.all_objects.get(id=...)`
plus `set_current_tenant(classroom.tenant)`, so secondary data exfil via
the task is bounded — but the cross-tenant DB write at the request layer
violates the multi-tenant isolation invariant on its own.

This is a *new* defect introduced in the uncommitted CG-P0-3 image-fill
deferral work; it is not a regression of any prior shipped feature.

## Threat model

| Attacker capability | Effect |
|---------------------|--------|
| Authenticated TEACHER in tenant A, valid Tenant A subdomain | DB write to `MAICClassroom(images_pending=True)` for any classroom UUID across tenants |
| Same | One Celery enqueue per request (`fill_classroom_images`, 60s countdown) → CPU/quota cost charged to the deployment, not the victim tenant |
| Same | Tenant B's frontend may briefly render an "images loading" spinner because of the flipped flag |

Severity: **P1**, not P0. No PII leaks, no cross-tenant content read,
no DoS amplification beyond a single Celery enqueue per request (already
rate-limited by the surrounding view's user throttles).

## Root cause

`backend/apps/courses/maic_views.py` line 385 (pre-fix):

```python
MAICClassroom.all_objects.filter(id=classroom_id).update(images_pending=True)
```

`all_objects` bypasses the `TenantManager`. `classroom_id` is taken
verbatim from `body.get("classroomId")` with no tenant scope check
upstream.

## Fix landed

### `backend/apps/courses/maic_views.py`

1. `_defer_image_fill(...)` now takes a `tenant=None` kwarg and scopes
   the lookup:
   ```python
   if tenant is not None:
       qs = MAICClassroom.all_objects.filter(id=classroom_id, tenant=tenant)
   else:
       qs = MAICClassroom.all_objects.filter(id=classroom_id)
   updated = qs.update(images_pending=True)
   if not updated:
       logger.warning("image fill skipped: classroom %s not in tenant %s ...", ...)
       return data  # do NOT enqueue Celery task
   ```
   The `legacy fallback` arm preserves backward-compat for any caller
   that hasn't been updated; a comment marks it deprecated.

2. Both call sites (`teacher_maic_generate_scene_content` and
   `student_maic_generate_scene_content`) now pass `tenant=request.tenant`.

3. When the lookup matches zero rows (cross-tenant or non-existent),
   we **return early before `apply_async()`** so no Celery work is
   enqueued for another tenant.

### `backend/tests/courses/test_maic_tenant_isolation.py`

Two new tests appended to the existing isolation suite:

- `test_defer_image_fill_skips_cross_tenant_classroom` — given
  `tenant=tenant_a` and `classroom_id=<tenant_b classroom>`, asserts:
  - `fill_classroom_images.apply_async` is **never** called
  - victim's `images_pending` remains `False`
- `test_defer_image_fill_runs_for_same_tenant_classroom` — positive
  control: own-tenant classroom still gets enqueue + flag flip. Guards
  against the fix being over-aggressive.

Both tests use the existing `tenant` / `tenant_b` fixtures and the
`mock.patch("apps.courses.maic_tasks.fill_classroom_images.apply_async")`
pattern already used elsewhere in the suite.

## Verification status

- AST syntax check: PASS for both modified files (`python3 -c "import ast; ast.parse(...)"`).
- pytest run: **DEFERRED — sandbox cannot run docker / venv pytest** (same
  blocker the reviewer accepted at the BE-SEC-P0 closeout, see
  `REVIEW-VERDICT-BE-SEC-P0-AUDIT-SANDBOX-BLOCKED-2026-04-21.md`).

If you have docker access, the run is:

```bash
docker compose exec web pytest \
  backend/tests/courses/test_maic_tenant_isolation.py \
  -v -k "defer_image_fill"
```

Expected: 2 passed.

## Files changed

```
backend/apps/courses/maic_views.py            (~30 lines: signature + scoped filter + early return)
backend/tests/courses/test_maic_tenant_isolation.py  (+~110 lines: 2 new tests)
```

No other files touched. No migrations. No public API changes.
The `_defer_image_fill` signature is backward-compatible (new kwarg has
a default of `None`).

## Disposition request

Please review the fix shape (tenant-scoped filter + early return + tests)
and approve. After approval I'll route a notice to backend-engineer +
qa-tester so the test run lands on the next CI pass.

— backend-security
