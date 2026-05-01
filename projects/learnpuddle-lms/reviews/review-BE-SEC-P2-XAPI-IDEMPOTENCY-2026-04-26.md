---
tags: [review, task/BE-SEC-P2-XAPI-IDEMPOTENCY, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-26
---

# Review: BE-SEC-P2-XAPI-IDEMPOTENCY — Tenant-explicit idempotency lookup (defence-in-depth)

## Verdict: APPROVE

## Summary
Tightens the xAPI POST idempotency filter to explicitly scope on `tenant=request.tenant`,
eliminating a latent cross-tenant IDOR risk should `objects` ever be swapped for
`all_objects`. Targeted, low-risk hardening with a focused regression test that
verifies the *behavior* (Tenant B reusing Tenant A's `statement_id` gets a fresh
201, not Tenant A's stored timestamp).

## Critical Issues
None.

## Major Issues
None.

## Minor Issues
None blocking. Two micro-observations:

1. **Comment clarity** — the in-line note already documents intent well. No change requested.
2. **Test asserts `stored != A.stored`** — relies on `auto_now_add` producing distinct
   timestamps. In a fast sandbox this could in theory tie at microsecond resolution.
   The stronger assertion that *does* the heavy lifting is the count==2 + tenant
   mismatch check (lines 511–516) and `resp.json()["stored"] == b_row.stored` (line 526),
   so this is a non-issue. Calling it out for the record only.

## Positive Observations
- **Right-sized fix.** The diff is the minimum surface area needed: two added kwargs
  on a `.filter()` and a 9-line comment that future-proofs the call site against
  refactor regressions. No churn.
- **Explicit-over-implicit at security boundaries.** Even though `TenantManager` made
  the previous code safe today, encoding the security invariant at the call site
  matches the named DB constraint (`xapi_statement_unique_per_tenant`) and removes
  the "spooky action at a distance" between manager swap and idempotency leak.
- **Test design is correct.** Uses `XAPIStatement.all_objects` (not `objects`) to
  prove both rows coexist post-write — exactly the right tool for verifying tenant
  isolation, since `objects` would silently filter the assertion. Setup creates a
  pre-existing Tenant A row with sensitive payload (`score: 99`, `secret-activity`)
  to make the leak shape concrete.
- **Verdict-friendly verification:** 11 passed (10 pre-existing + 1 new), no
  regressions. AST-clean.
- **Audit sweep is on-task and bounded.** The proactive scan covered 11 recently-added
  apps with the right threat model (auth decorators, IDOR, manager bypass, SSRF on
  outbound HTTP, unsigned webhooks, mass assignment, upload validation) and reports
  *clean* with concrete reasons rather than just "looked fine." This is exactly the
  level of evidence needed to close the security queue.

## Routing
- ✅ Approved.
- backend-security queue is empty after this — concur.
- No QA action needed (test landed green).
- No backend-engineer awareness needed (self-contained).
