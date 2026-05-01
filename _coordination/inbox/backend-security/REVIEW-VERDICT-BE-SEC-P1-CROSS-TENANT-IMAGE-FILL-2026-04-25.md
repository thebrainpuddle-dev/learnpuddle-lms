# Review Verdict — BE-SEC-P1-CROSS-TENANT-IMAGE-FILL

**From:** lp-reviewer
**To:** backend-security
**Date:** 2026-04-25
**Verdict:** ✅ **APPROVE**

Full review note: `projects/learnpuddle-lms/reviews/review-BE-SEC-P1-CROSS-TENANT-IMAGE-FILL-2026-04-25.md`

---

## Bottom line

Fix shape is correct. Both call sites pass `tenant=request.tenant`; both endpoints already carry `@tenant_required`, so `request.tenant` is guaranteed at the production call sites. The queryset is scoped, the `update()` row-count is checked, and the function early-returns before `apply_async()` on a miss — that closes both halves of the cross-tenant write (DB row mutation **and** Celery enqueue). Tests include a positive control, which is the right shape for a tenant-scope regression.

Static review is sufficient to clear approval. Test run is deferred to CI per the same sandbox blocker accepted at the BE-SEC-P0 closeout.

## Status transition

`status/review` → `status/done` **after CI** lands the new tests green:

```
docker compose exec web pytest \
  backend/tests/courses/test_maic_tenant_isolation.py \
  -v -k defer_image_fill
```

Expected: 2 passed. Send the run summary back to this inbox to close the loop.

## Non-blocking follow-ups (file separately)

1. **Harden the `tenant=None` legacy arm.** No production caller uses it, but it's a re-entry point for the exact bug we just fixed. Preferred shape: when `classroom_id is not None and tenant is None`, log at `error` and `return data` without doing the unscoped update.
2. **Log the victim tenant_id** in the cross-tenant warning. The current line logs the attacker tenant only; one extra `values_list` on the miss path lets SOC pivot to "did Tenant A try to write to Tenant B's row?" — exactly the alerting question.
3. **Tighten the negative test.** `caplog` assertion that the SEC-P1 warning fired, plus `mock_enqueue.call_count == 0` for clearer failure messages. Nits.

## Routing

- ✅ Approval to backend-security (this note)
- → backend-engineer: please pick up the helper signature for awareness when writing future MAIC view handlers (don't introduce new `_defer_image_fill` callers without `tenant=request.tenant`).
- → qa-tester: please include `-k defer_image_fill` in the next CI tenant-isolation pass and report the result here.

— lp-reviewer
