---
tags: [review, task/BE-SEC-P0-AUDIT, verdict/acknowledge, reviewer/lp-reviewer]
created: 2026-04-21
---

# Review: BE-SEC-P0 test-run — sandbox blocker acknowledgment

## Verdict: ACKNOWLEDGE (not a code review — routing/triage)

## Summary

This note is not a code-review request; it is a status update that both
qa-tester and backend-security lack docker/pytest execution rights in
their sandboxes and therefore cannot run the four test modules the
reviewer asked to have executed as the final gate on the P0 queue. The
code-review verdict on the P0 queue itself already shipped in
`review-BE-SEC-P0-audit-signoff.md` — static analysis signed off on
all five fixes. The outstanding item is *execution evidence*, not
*review*.

## Findings

### Static re-verification (2026-04-21) checked by reviewer

backend-security's re-audit table is accurate. Spot-checked the two
load-bearing items:

| # | Fix | Verified at | Evidence |
|---|-----|-------------|----------|
| 1 | `contextvars` tenant storage | `backend/utils/tenant_middleware.py:5,17–34` | `import contextvars`, `_current_tenant: contextvars.ContextVar = …`; no `threading.local` |
| 3 | Stripe webhook fail-closed | `apps/billing/stripe_service.py` | Raises `ValueError` when `STRIPE_WEBHOOK_SECRET` absent |

The other three fixes (double-hash on register-teacher, no wildcard
CORS, Redis password enforcement) were already re-verified by the
BE-SEC-001/002 review chain and remain present on the working tree.

### Sandbox blocker is genuine

- `docker` not on PATH in agent sandboxes — confirmed by two
  independent agents (qa-tester 2026-04-19, backend-security 2026-04-21).
- Direct venv invocation requires an interactive approval gate that
  headless agents cannot satisfy.
- This is an infrastructure constraint, not an agent skill gap.

## Decision

Accept the code-inspection verdict for the P0 queue and route the
execution gate to a channel that actually has the runtime. Per
backend-security's proposed options:

**Preferred path:** Have devops run the four test modules from the
environment that already hosts the docker-compose stack. Devops has
demonstrated `docker compose exec` capability in a prior log entry
(`[devops] INFRA-PATCHED`). One paste of the
`N passed, M failed` summary into either inbox closes the gate.

**Fallback path:** Add these four modules to the CI test matrix so they
gate the next PR touching any of the referenced files
(`utils/tenant_middleware.py`, `apps/tenants/webhook_views.py`,
`apps/billing/stripe_service.py`, `config/settings.py`). Backend-engineer
+ devops co-own that matrix. This is strictly additive and low-risk.

**Not acceptable:** Quietly dropping the execution gate and calling
P0 closed. The static review is strong but the P0 queue was important
enough to warrant runtime verification in the original plan, and the
reasoning for that plan has not changed.

## Action Items (routed, not blocked)

1. **devops** (primary): run the four-module pytest command below from
   the compose-host shell and reply with the summary line.

   ```bash
   docker compose exec web pytest \
     tests/test_contextvars_isolation.py \
     tests/test_cors_headers.py \
     tests/webhooks/ \
     tests/test_webhook_ssrf.py -v
   ```

2. **backend-engineer + devops** (secondary): if #1 is not possible in
   the next 24h, add these four modules to the CI test gate on the
   next PR touching the covered files. Reference this note in the PR
   description.

3. **reviewer** (me): once execution evidence arrives, append a
   closeout line to `review-BE-SEC-P0-audit-signoff.md` and mark the
   P0 queue fully closed.

## Positive Observations

- backend-security did the right thing — attempted the run, documented
  the specific blocker (PATH + approval-gate), and escalated rather
  than silently dropping the task.
- Static re-audit table is evidence-dense (file + line numbers on
  every row). Easy to spot-check.
- Proposal to gate via CI on the next touching PR is the correct
  long-term fix; the manual one-shot run is a bridge, not a
  substitute.

— reviewer (lp-reviewer)
