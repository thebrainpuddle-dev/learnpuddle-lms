---
tags: [review, task/TASK-008, task/TASK-012, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-30
---

# Review: BE-TASK008 Resubmit — Transition Cleanup (dual-key restored + Deprecation header)

## Verdict: APPROVE

## Summary

All five concerns from the previous REQUEST_CHANGES review are addressed. The PR
now correctly preserves the dual-key emission (`error` + `detail`) during the
transition, adds a `Deprecation: detail-key` response header on every error path
for telemetry, and the FE migration follow-up has been filed. The premise is now
honest about state ("transition") rather than declaring the cleanup complete.

## Verification Performed

I diffed the resubmit against my original review and re-read both files end-to-end:

### `backend/utils/exception_handler.py`
- All 5 cases (1, 1b, 2, 3, 4) emit `"detail": <error_str>` alongside `"error"`. ✅
- All 5 cases set `response["Deprecation"] = "detail-key"`. ✅
- Module docstring (lines 16–27) correctly describes the transitional dual-key
  state and explicitly references "TASK-012" + "~68 `data.detail` sites" — the
  conflation noted in M2 of the prior review is gone. ✅
- The Deprecation header note in the docstring (lines 25–26) makes the telemetry
  intent discoverable without reading code. ✅
- Zero behavior drift outside the dual-key restoration; no other branches touched. ✅

### `backend/tests/test_exception_handler.py`
- 6 inverted tests reverted to legacy-key assertions
  (`test_*_legacy_detail_key`, `test_detail_value_is_plain_string_not_object`)
  asserting `"detail" in data` and `data["detail"] == data["error"]`. ✅
- 3 new tests added:
  - `test_not_authenticated_deprecation_header` (lines 82–86) — system-error path
  - `test_field_validation_deprecation_header` (lines 189–193) — validation path
  - `test_error_and_detail_are_equal` (lines 155–159) — equality contract
- Test count: 28 → 31 (lines up with the resubmit summary). Coverage of the
  Deprecation header spans both system-error and validation branches, which is
  the right minimum to lock the contract. ✅
- Module docstring (lines 13–22) explicitly documents the transition state and
  the Deprecation header. ✅

### FE migration follow-up
- `_coordination/inbox/frontend-engineer/BE-TASK008-DETAIL-KEY-MIGRATION-2026-04-30.md`
  exists, identifies the 68 occurrences across 33 files (matches my prior count),
  and prescribes the backward-compatible `data?.error ?? data?.detail ?? '...'`
  pattern. Acceptance criteria are concrete and verifiable. ✅

## Critical Issues
None.

## Major Issues
None.

## Minor Issues

### m1 (non-blocking) — Deprecation header value is non-standard

`Deprecation: detail-key` is a freeform sentinel rather than a
[RFC 8594 Deprecation](https://datatracker.ietf.org/doc/html/rfc8594) value
(which is HTTP-date or `true`). It works as an internal telemetry signal — any
log query for `Deprecation: detail-key` will catch it — but if you ever expose
this header to third-party API consumers, the canonical pattern is:

```
Deprecation: true
Sunset: Wed, 31 Dec 2026 23:59:59 GMT
Link: <https://docs.learnpuddle.com/api/errors#detail-key>; rel="deprecation"
```

Not worth fixing for an internal telemetry use-case. Flagging only so the next
person doesn't repeat the pattern for an external-facing deprecation.

### m2 (non-blocking) — Optional: parametrise the Deprecation header tests

`test_not_authenticated_deprecation_header` and
`test_field_validation_deprecation_header` are structurally identical and assert
the same invariant against different inputs. A parametrised test (or a single
fixture iterating over the four exception classes whose paths set the header)
would tighten coverage to all branches. Not required — the existing two tests
already prove the header reaches both major code paths.

## Positive Observations

- **Picked the recommended Option B from the prior review** (keep emitting + add
  Deprecation header) rather than rushing into Option A. This is the safer
  staging — FE migration can land independently, telemetry confirms readiness,
  then the cleanup PR has zero risk.
- **Filing the FE follow-up is the right move.** The migration request is
  written so it can be picked up by a different agent without re-deriving
  context: it cites the 33 affected files, gives the exact replacement pattern,
  and explains why the change is backward-compatible. That unblocks the final
  cleanup without coupling the two PRs in time.
- **Deprecation header is set on every error path**, including the rare Case 1b
  and Case 4 fallbacks. No silent gaps in telemetry coverage.
- **TDD discipline is preserved across the revert.** The new
  `test_error_and_detail_are_equal` makes the equality contract explicit (rather
  than implicit in each per-case assertion), which is exactly the right place to
  state an invariant.
- **Module docstrings updated to match new state.** Future readers will see the
  transitional intent and the FE migration count, not stale "cleanup done" wording.

## Next Steps (informational)

1. Frontend-engineer picks up `BE-TASK008-DETAIL-KEY-MIGRATION-2026-04-30.md`,
   migrates the 68 `data.detail` reads to `data?.error ?? data?.detail`.
2. After FE migration ships, monitor the `Deprecation: detail-key` header
   incidence in production logs for ~1 week.
3. When telemetry is quiet, reland the original cleanup PR — at that point the
   inverted assertions ("`detail` not in data") are correct and TASK-008 AC6
   ("No regression in error display on any page") can finally be checked.

— lp-reviewer
