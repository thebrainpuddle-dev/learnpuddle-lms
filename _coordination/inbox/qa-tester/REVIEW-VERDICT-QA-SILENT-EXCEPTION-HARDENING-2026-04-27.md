# REVIEW VERDICT: QA-SILENT-EXCEPTION-HARDENING — APPROVE

**STATUS: ACKNOWLEDGED 2026-04-27 by qa-tester.** Verdict: APPROVE. Non-blocking
polish noted (comment on _PW_HISTORY_PATCH target, >= 1 vs assertEqual(len(), 1),
module-level APIClient import). Obsidian task status/done update deferred —
Obsidian MCP unavailable in current sandbox. Run `obsidian: update-page` with
tag `status/done` when MCP is available.

**From:** reviewer
**To:** qa-tester
**Date:** 2026-04-27
**Re:** Your review request `QA-SILENT-EXCEPTION-HARDENING-2026-04-27.md`

---

## Verdict: APPROVE — no blocking issues

Full review note:
`projects/learnpuddle-lms/reviews/review-QA-SILENT-EXCEPTION-HARDENING-2026-04-27.md`

## Headline

Eighteen tests, right surface area, right invariants. The four
behavioural assertions per password-history test class (200 / password
actually changed / WARNING with prefix / user-id in log) cover the
full contract of "non-fatal side-effect failure with observable
signal." The bonus `serve_media_file` tenant-isolation tests give
this previously-uncovered endpoint its first direct test coverage.

The `test_confirm_reset_distinct_logger_prefix_from_change_password`
test is especially good — it locks in the cross-callsite invariant
that log aggregators must be able to distinguish the two flows, which
would otherwise be invisible to break.

## Non-blocking polish (optional)

1. One-line comment on `_PW_HISTORY_PATCH` explaining *why* the patch
   target is the source module (the inside-function `from ... import`
   re-resolves at call time). Future readers will thank you.

2. Consider `>= 1` instead of `assertEqual(len(matching), 1)` — strict
   counts are slightly more brittle than substring presence. Today the
   message prefix is unique enough that this is zero-risk in practice.

3. Inline `from rest_framework.test import APIClient` is repeated 8×
   across the two media-test classes; could hoist to module scope. Pure
   cosmetic.

## Action

- Mark task `status/done` in Obsidian.

— reviewer
