---
tags: [review, task/BE-TASK008, verdict/approve, reviewer/lp-reviewer, resubmit]
created: 2026-04-30
---

# Review: BE-TASK008-RESUBMIT — Exception handler dual-key transition cleanup (resubmit)

## Verdict: APPROVE

## Summary
Resubmit cleanly addresses every item from the prior REQUEST_CHANGES. The `detail` legacy key is restored across all 5 emission cases, a `Deprecation: detail-key` response header is now set on every error response so monitoring can track FE adoption, the docstring honestly documents the transitional state, and the tests assert the contract (legacy key present, equal to `error`, plus a `Deprecation` header on representative cases). FE migration ticket is filed separately so AC6 can be closed by frontend-engineer.

## Critical Issues
None.

## Major Issues
None.

## Minor Issues

1. **Per-case duplication of the `Deprecation` header.** `response["Deprecation"] = "detail-key"` is set in five places (lines 157, 170, 183, 194, 203). A small refactor — set the header once at the bottom of `custom_exception_handler` before each `return response` — would be DRY-er. Not blocking; current form is explicit and readable.

2. **`Deprecation` header value is `detail-key` (not RFC-9745).** RFC 9745 defines the `Deprecation` header as a date or `Deprecation: @<unix-timestamp>` token. `detail-key` is a non-standard label. Since this is internal telemetry (not a public API contract surfaced to third parties), the non-standard value is fine — but if the team later wants to advertise deprecation to webhook consumers, switch to RFC-9745 format. Non-blocking.

3. **5 separate "TASK-012 transition" comments.** Same line of comment repeated five times. A single docstring entry (already present at lines 16-26) would suffice; the per-line breadcrumbs are belt-and-suspenders. Easy cleanup once the FE migration lands and the `detail` lines come out wholesale.

## Positive Observations

- **All 5 cases handled symmetrically.** Case 1 (single-key DRF), Case 1b (DRF + extras), Case 2 (field-level), Case 3 (list-form), Case 4 (fallback) all emit both `error` and `detail` and set the deprecation header. No path missed.
- **Docstring narrates the transitional state.** Lines 16-27 in `exception_handler.py` state the policy: both keys emitted, `error` is canonical, `detail` is legacy, `Deprecation` header signals adoption tracking, will drop after TASK-012 ships. Future reader has full context.
- **Three new tests pin the contract:**
  - `test_not_authenticated_deprecation_header` — header present on system errors
  - `test_field_validation_deprecation_header` — header present on validation errors
  - `test_error_and_detail_are_equal` — equality contract documented
- **Six restored `_legacy_detail_key` tests** — naming makes their transitional purpose explicit; will be easy to grep-and-delete once FE migration completes.
- **Forward-looking FE handoff.** `_coordination/inbox/frontend-engineer/BE-TASK008-DETAIL-KEY-MIGRATION-2026-04-30.md` was filed with the backward-compatible idiom (`data?.error ?? data?.detail`), so FE can migrate at its own pace without coordination on a flag-day.
- **Honest about scope.** "What Was NOT Done" section explicitly leaves AC6 open for FE — exactly the right boundary.

## Notes for Author

- After FE migration completes (TASK-012 closes), please file the cleanup ticket: drop the 5 `"detail": error_str` lines, drop the 5 `response["Deprecation"]` lines, drop the 6 `_legacy_detail_key` tests, drop the 3 deprecation-header tests, update the docstring, and remove the `Deprecation: detail-key` header from monitoring dashboards. The `# TASK-012 transition` breadcrumbs make this a mechanical sweep.
- Consider adding a metric on the `Deprecation` header emission count so monitoring can confirm "FE no longer reads `detail`" empirically before the cleanup PR lands.

— lp-reviewer
