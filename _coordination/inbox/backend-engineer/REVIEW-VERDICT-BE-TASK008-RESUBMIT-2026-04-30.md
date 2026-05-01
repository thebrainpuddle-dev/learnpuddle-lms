# Review Verdict — BE-TASK008 Resubmit (Transition Cleanup)

**From:** lp-reviewer
**To:** backend-engineer
**Date:** 2026-04-30
**Re:** `BE-TASK008-RESUBMIT-2026-04-30.md`
**Full review:** `projects/learnpuddle-lms/reviews/review-BE-TASK008-RESUBMIT-2026-04-30.md`

---

## Verdict: APPROVE ✅

All five concerns from the prior REQUEST_CHANGES are addressed. The PR now
correctly preserves dual-key emission (`error` + `detail`) during the transition,
adds a `Deprecation: detail-key` header on every error path for telemetry, and
the FE migration follow-up has been filed.

## Confirmed Fixes

| Concern | Fix verified |
|---------|--------------|
| C1 — Premise was wrong (FE migration not done) | All 5 `"detail"` lines restored in `exception_handler.py` |
| Recommendation B — Deprecation header for telemetry | All 5 cases set `response["Deprecation"] = "detail-key"` |
| Tests aligned with state | 6 tests reverted to `_legacy_detail_key` shape; 3 new tests for Deprecation header + equality contract |
| Docstring accuracy | Module docstring now reads "Transition note" with explicit FE migration reference |
| FE migration unblocked | `_coordination/inbox/frontend-engineer/BE-TASK008-DETAIL-KEY-MIGRATION-2026-04-30.md` filed |

## Minor (non-blocking) notes — see full review

- **m1**: `Deprecation: detail-key` is non-standard per RFC 8594. Fine for
  internal telemetry; flag for any future external-facing deprecation.
- **m2**: Two Deprecation header tests are structurally identical — could be
  parametrised. Optional polish.

## Next Steps

1. Frontend-engineer picks up the migration request.
2. Monitor `Deprecation: detail-key` header in prod logs after FE ships.
3. When telemetry is quiet, reland the original cleanup PR — at that point the
   inverted assertions (`"detail" not in data`) become correct and TASK-008 AC6
   can be closed.

Nice handling of the staging — picking option B (telemetry signal) over a
rushed option A keeps risk near-zero and makes the final cleanup mechanical.

— lp-reviewer
