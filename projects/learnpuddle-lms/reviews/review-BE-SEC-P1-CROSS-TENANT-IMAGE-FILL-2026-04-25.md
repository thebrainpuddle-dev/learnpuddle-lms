---
tags: [review, task/BE-SEC-P1-CROSS-TENANT-IMAGE-FILL, verdict/approve, reviewer/lp-reviewer, severity/p1, area/maic, area/security, area/multi-tenant]
created: 2026-04-25
---

# Review: BE-SEC-P1-CROSS-TENANT-IMAGE-FILL — Tenant-scope `_defer_image_fill` lookup + Celery enqueue

## Verdict: APPROVE

## Summary

Tight, well-targeted fix for a real (newly-introduced, never-shipped) cross-tenant write surface in the MAIC scene-content image-fill deferral path. Fix shape is correct, blast radius is minimal, and the regression suite includes both the negative cross-tenant case and a positive same-tenant control. Approving on shape; the test run is rightly deferred to CI per the same sandbox blocker the reviewer accepted at the BE-SEC-P0 closeout.

---

## Scope verified

**Files in this change (per author note + git status):**

- `backend/apps/courses/maic_views.py` — `_defer_image_fill(...)` signature + body; both call sites
- `backend/tests/courses/test_maic_tenant_isolation.py` — +2 tests appended

**Call-site coverage check (independent grep):**

```
backend/apps/courses/maic_views.py:625  _defer_image_fill(... tenant=request.tenant)   # teacher
backend/apps/courses/maic_views.py:1897 _defer_image_fill(... tenant=request.tenant)   # student
```

Two production call sites; both pass `tenant=request.tenant`. ✅

**Endpoint guard check:**

- `teacher_maic_generate_scene_content` — `@tenant_required` (line 590). ✅
- `student_maic_generate_scene_content` — `@tenant_required` (line 1909). ✅

So `request.tenant` is guaranteed non-None at both call sites and the new tenant-scoped filter is always active in production. Good belt-and-suspenders against the legacy fallback being silently re-introduced.

---

## Critical Issues

None.

## Major Issues

None.

## Minor Issues

1. **Legacy `tenant=None` fallback is a future-bug magnet** (`maic_views.py` line ~415).

   The fix preserves a backward-compat path:

   ```python
   if tenant is not None:
       qs = MAICClassroom.all_objects.filter(id=classroom_id, tenant=tenant)
   else:
       qs = MAICClassroom.all_objects.filter(id=classroom_id)   # <-- vulnerable shape
   ```

   No production caller currently hits the `else` arm — both call sites pass tenant, and a repo-wide grep confirms only one disabled-provider unit test (`test_defer_image_fill_disabled_provider_stamps_meta`) calls `_defer_image_fill` without tenant, but it also passes `classroom_id=None` so the DB-write block is skipped entirely.

   So the `else` branch is dead code today, but it is also a *re-entry point for the exact bug we just fixed*. If someone wires up a third call site in the future and forgets `tenant=...`, the vuln is back, silently. Two non-blocking options:

   - Make the kwarg required (`tenant`, no default) — breaks the disabled-provider test signature trivially (it can pass `tenant=None` explicitly, or be updated to use a real fixture); or
   - Inside the function, when `classroom_id is not None and tenant is None`, log at `error` (not `warning`) and `return data` without doing the unscoped update. This kills the unscoped DB write outright while keeping the current signature.

   I'd take option (2) for minimal blast radius. Not a blocker — flag for a follow-up.

2. **Log message could include the caller-supplied tenant of the victim row** for triage.

   Current warning (line ~422):

   ```
   "image fill skipped: classroom %s not in tenant %s (SEC-P1-CROSS-TENANT-IMAGE-FILL)",
   classroom_id, getattr(tenant, "id", None),
   ```

   This logs the *attacker's* tenant. The victim tenant is unknown without an extra query, but a follow-up `MAICClassroom.all_objects.filter(id=classroom_id).values_list('tenant_id', flat=True).first()` (only on the miss path, which is an attack/exception path) would let SOC pivot from the log line straight to "did Tenant A try to write to Tenant B's row?" That's exactly the alerting question for this class of bug.

   Acceptable to defer, but worth a follow-up ticket.

3. **Test naming is fine; one assertion could be tighter.**

   `test_defer_image_fill_skips_cross_tenant_classroom` asserts `mock_enqueue.called is False` and `victim.images_pending is False`. Consider also asserting `mock_enqueue.call_count == 0` (functionally equivalent, but makes intent obvious in the failure message) and asserting that the warning log line was emitted (via `caplog`). Both are nits.

---

## Positive Observations

- **Fix shape is exactly right.** Scoping by `tenant` at the queryset level + checking the `update()` row-count + early-returning before `apply_async()` covers both halves of the cross-tenant write (the row mutation *and* the Celery enqueue). It's the same pattern used elsewhere in the codebase for tenant-scoped admin actions.
- **Both call sites updated atomically with the helper signature** — no half-fixed state where the teacher path is safe but the student path still leaks.
- **Tests include a positive control** (`test_defer_image_fill_runs_for_same_tenant_classroom`). This is the right way to write the regression — a one-sided "no-op on cross-tenant" test would silently pass even if the fix over-scoped and broke same-tenant fills.
- **Both tests mock `apps.courses.maic_tasks.fill_classroom_images.apply_async` at the source** rather than asserting on Celery internals — matches the existing isolation-suite convention.
- **Comments in the diff explicitly cite `SEC-P1-CROSS-TENANT-IMAGE-FILL`** at every edit point, so future grep-driven audits land on the right context immediately.
- **Threat model in the request note is accurate:** P1 (write-only, no read leak, no DoS amplification beyond the existing per-user throttle, Celery cost charged to the deployment not the victim). The downgrade from P0 is justified.
- **No public API change, no migration, no serializer change.** The `tenant=None` default keeps the helper signature backward-compatible, which is good for the hot-fix posture.
- **Compliments the BE-SEC-P0 audit pattern.** Adding the assertion alongside the existing tenant-isolation suite (rather than a new file) keeps the regression net cohesive and easy to run as a single `-k` filter.

---

## Verification

- AST parse confirmed (per author).
- pytest run **deferred to CI** — same sandbox blocker accepted at BE-SEC-P0 closeout (`review-BE-SEC-P0-AUDIT-TEST-RUN-SANDBOX-BLOCKED-2026-04-21.md`). Reviewer-side static review (call-site grep, decorator stack, queryset shape, mock target) is sufficient to clear approval; expectation is the next CI run lands a green `pytest backend/tests/courses/test_maic_tenant_isolation.py -v -k defer_image_fill` (2 passed).

If CI surfaces a failure on the new tests, treat as a `REQUEST_CHANGES` re-open against this same review note rather than a new review cycle.

---

## Disposition

- **Verdict:** APPROVE
- **Status transition:** `status/review` → `status/done` once CI confirms green on the two new tests (author to send the run summary back to this inbox).
- **Follow-ups (non-blocking, file as separate tickets):**
  - Minor #1 — harden the `tenant=None` legacy arm (option 2 preferred).
  - Minor #2 — include victim tenant_id in the cross-tenant warning log for SOC triage.
  - Minor #3 — `caplog` assertion + `call_count == 0` tightening on the negative test.

— lp-reviewer
