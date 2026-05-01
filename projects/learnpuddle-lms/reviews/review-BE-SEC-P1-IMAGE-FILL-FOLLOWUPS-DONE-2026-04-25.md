---
tags: [review, task/BE-SEC-P1-CROSS-TENANT-IMAGE-FILL, verdict/approve, reviewer/lp-reviewer, severity/p1, area/maic, area/security, area/multi-tenant, follow-up]
created: 2026-04-25
---

# Review: BE-SEC-P1-CROSS-TENANT-IMAGE-FILL — Follow-ups #1 + #2 (legacy-arm refusal + victim tenant log field)

## Verdict: APPROVE

## Summary

All three follow-ups from `review-BE-SEC-P1-CROSS-TENANT-IMAGE-FILL-2026-04-25.md` are now landed and verified end-to-end. Production-code follow-ups #1 and #2 (this batch, by backend-security) compose cleanly with the qa-tester #3 hardening of the negative regression test. Net effect: the `_defer_image_fill` legacy `tenant=None` arm is now an explicit refusal (no more silent re-entry point), and the cross-tenant warning record now carries the victim tenant_id for SOC pivoting. Local pytest run reported green across the affected modules. Approve to flip `status/review` → `status/done`.

---

## Scope verified

**Files inspected against the request note:**

- `backend/apps/courses/maic_views.py` — `_defer_image_fill(...)` body (lines ~366–549)
- `backend/apps/courses/_log_helpers.py` — `ALLOWED_FIELDS` membership
- `backend/tests/courses/test_maic_tenant_isolation.py` — original SEC-P1 pair + 2 new tests + the qa-tester-hardened negative test

**Independent grep confirms:**

- `_defer_image_fill` callers still pass `tenant=request.tenant`:
  - `maic_views.py:753` (teacher path)
  - `maic_views.py:2091` (student path)
- No production caller hits the `tenant=None` legacy path (which is now an explicit refusal anyway).
- `victim_tenant_id` is added to `ALLOWED_FIELDS` (line 148) — without it, the SPRINT-2-BATCH-8-F1 sanitizer would silently drop the new field and follow-up #2's test would fail with `<missing>`.

---

## Follow-up disposition

### #1 — Legacy `tenant=None` arm hardened ✅

**Implementation** (lines 444–468): when `has_empty_images and classroom_id and not disabled` AND `tenant is None`, the function logs at ERROR level with `metric=image_fill_refused`, `outcome=missing_tenant`, then `return data`. No DB update, no Celery enqueue. The unscoped `MAICClassroom.all_objects.filter(id=classroom_id)` lookup is gone — the only queryset shape that survives is `filter(id=classroom_id, tenant=tenant)`.

This is exactly review option (2) — minimum-blast-radius hardening that keeps the function signature stable but prevents the unscoped DB write outright. Future callers that forget to pass tenant will get loud failure (ERROR + tagged metric) rather than a silent re-entry of the bug.

**Test coverage**: `test_defer_image_fill_refuses_when_tenant_none` asserts (a) `images_pending` not flipped on a real classroom that *would* have matched an unscoped lookup, (b) `apply_async.call_count == 0`, (c) ERROR-level message contains both `SEC-P1-CROSS-TENANT-IMAGE-FILL` and `tenant=None`. The "real classroom that would have matched if unscoped" framing makes this a sharp regression test — if anyone ever drops the guard, the test fails immediately because the unscoped lookup *would* succeed.

### #2 — Victim tenant_id in cross-tenant warning ✅

**Implementation** (lines 487–518): on the cross-tenant miss path (after `qs.update(images_pending=True)` returns 0), one extra `MAICClassroom.all_objects.filter(id=classroom_id).values_list("tenant_id", flat=True).first()` resolves the victim tenant (or `None` for typo / hostile-probe UUIDs). The warning message gets a third format arg, and the structured `extra` payload gets a new `victim_tenant_id` field (empty string when no row matched, str(uuid) otherwise).

The "empty string vs None" choice for the no-row case is the right call for log shape stability — Loki / ES indices keep a single string type for the field, no schema-evolution surprises later.

The extra DB hit is on the (already-rare) attack/exception path, so no perf concern. `all_objects` is correct here — the lookup is intentionally tenant-unscoped *because* it's looking up the victim outside the caller's tenant; this is exactly the one place in the function where bypassing TenantManager is right.

**Test coverage**: `test_defer_image_fill_logs_victim_tenant_id_on_cross_tenant_miss` walks `caplog.records` (not just `messages`) to inspect the structured field. It asserts both `victim_tenant_id == str(tenant_b.id)` (the row's actual owner) and `tenant_id == str(tenant.id)` (the attacker). The dual assertion catches both directions of regression — dropping the new field, or accidentally swapping which tenant id goes where.

### #3 — Negative test hardening (qa-tester, already landed) ✅

`test_defer_image_fill_skips_cross_tenant_classroom` now uses `caplog.at_level(WARNING, logger="apps.courses.maic_views")`, asserts `mock_enqueue.call_count == 0` (instead of `not called`), and asserts the SEC-P1 tag appears in `caplog.messages`. The change is structurally identical to what the original review note recommended, and the failure messages are now self-describing (e.g. `"fill_classroom_images was enqueued 1 time(s) ..."` vs the prior bare `False` assertion).

---

## Critical Issues

None.

## Major Issues

None.

## Minor Issues

1. **`getattr(tenant, "id", None)` vs structured field empty-string convention** (line 505 vs 512):

   The human-readable warning message uses `getattr(tenant, "id", None)` (which renders as `"None"` if tenant is missing), while the structured `extra.tenant_id` uses `str(getattr(tenant, "id", ""))` (empty string). Since follow-up #1 already refuses `tenant=None` upstream, both branches are dead code on this path — at this point in the function `tenant` is guaranteed non-None. Cosmetic. No action needed.

2. **`victim_tenant_id` rendered as a UUID object in the human-readable message** (line 506):

   `logger.warning("... (victim_tenant=%s) ...", ..., victim_tenant_id)` will format a `UUID` object via `str()` for the message, but the structured `extra` payload coerces explicitly with `str(victim_tenant_id) if victim_tenant_id else ""`. The asymmetry is harmless (Python's `%s` calls `__str__`), but a future reader scanning Loki output may briefly wonder why the message-line UUID has hyphens but the extra-field UUID is a different shape. Pure nit.

3. **Test imports inside function bodies** (e.g. `import logging` at line 449, `from apps.courses.maic_models import MAICClassroom` at line 450):

   The two new tests follow the same pattern as the original SEC-P1 tests in this file — local imports rather than module-level. That's an existing convention here, so consistent. If someone wants to consolidate later, it's a sweep across the whole file, not this PR's concern.

---

## Positive Observations

- **Both follow-ups have first-class regression tests** — not just static-analysis confidence. The legacy-arm refusal test in particular is sharply written: it sets up a classroom that *would* match an unscoped lookup, so a regression that re-introduces the unscoped path will flip `images_pending` and the test will catch it.
- **`ALLOWED_FIELDS` update is the right kind of change** — declarative, in-line comment cites SEC-P1, and the comment explicitly notes the cardinality bound (UUID, same shape as `tenant_id`). Without this, the structured field would be silently dropped and only the test-side `getattr(rec, ...)` assertion would catch it. Catching it at static-allowlist update time is much safer.
- **Comments at every edit point cite `SEC-P1-CROSS-TENANT-IMAGE-FILL` and the date** — future grep-driven audits land on the right context immediately. The follow-up numbers (`#1`, `#2`) are also called out, which makes the link back to the review note one search away.
- **Log shapes are stable**: the new `victim_tenant_id` field is always a string (UUID-string or empty), never sometimes-None. Loki / ES happy.
- **Test for #2 inspects `caplog.records` not just `caplog.messages`**, which is the right granularity for verifying structured-log fields. It's also robust to the eventual `log_extra` shape changing — it asserts on the LogRecord attribute, not on a substring of the rendered message.
- **No surprise scope creep**: the diff only touches `_defer_image_fill`, the log-helper allowlist, and the test file. No drive-by refactors, no incidental signature changes.
- **Composes cleanly with QA's #3 hardening**: backend-security and qa-tester landed in the same module across overlapping sessions without merge conflicts on the test file. The original SEC-P1 tests, the QA-hardened negative test, and the two new follow-up tests now form a coherent four-test block with consistent fixture usage and assertion style.

---

## Verification

- **Author-reported pytest run**: `tests/courses/test_maic_tenant_isolation.py -v -k defer_image_fill` → 4 passed; full module → 19 passed; `test_logging_phases.py` → 12 passed (confirms `ALLOWED_FIELDS` change didn't break the sanitizer's allow-list parsing).
- **Reviewer-side static checks**:
  - Code at `maic_views.py:444–518` matches the request note line-for-line (modulo formatting).
  - `_log_helpers.py:148` adds `victim_tenant_id` to `ALLOWED_FIELDS` with the cardinality-bound comment.
  - Both new tests are present at `test_maic_tenant_isolation.py:441–585`.
  - `caplog` hardening is present at `test_maic_tenant_isolation.py:346–371`.
  - Two production callers (lines 753, 2091) still pass `tenant=request.tenant`.
- **CI dependency**: per the standing acceptance of the Docker sandbox blocker (`review-BE-SEC-P0-AUDIT-TEST-RUN-SANDBOX-BLOCKED-2026-04-21.md`), the reviewer-side green light is granted on static review + author's local pytest report. Next CI run is expected to publish a green test pass on these four `defer_image_fill_*` cases.

---

## Disposition

- **Verdict:** APPROVE
- **Status transition:** `status/review` → `status/done`. All three follow-ups from the parent review note are closed.
- **No further follow-ups required.** This closes the BE-SEC-P1-CROSS-TENANT-IMAGE-FILL ticket end-to-end (initial fix + three review follow-ups + regression tests).

— lp-reviewer
