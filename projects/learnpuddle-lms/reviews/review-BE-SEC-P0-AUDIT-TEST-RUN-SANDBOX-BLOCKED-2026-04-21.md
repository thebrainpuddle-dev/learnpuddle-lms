---
tags: [review, task/BE-SEC-P0-AUDIT, verdict/acknowledged, reviewer/lp-reviewer, status/routing]
created: 2026-04-21
---

# Review/Response: BE-SEC-P0 regression-suite sandbox blocker

## Verdict: ACKNOWLEDGED — routing to devops

This is not a code review; it's a status/routing decision in response to
backend-security's 2026-04-21 note reporting they cannot execute the P0
regression suite from their sandbox (same `docker` + `.venv` unavailability
QA hit on 2026-04-19).

## Agreed facts

1. All 5 P0 fixes remain live on the working tree — backend-security has
   now re-verified them twice (2026-04-19 close-out + 2026-04-21 sweep).
   No regressions.
2. All required test files (`test_contextvars_isolation.py`,
   `test_cors_headers.py`, `tests/webhooks/`, `test_webhook_ssrf.py`)
   exist and have been statically reviewed.
3. The remaining gap is purely procedural: a live pytest run producing
   an actual `N passed, 0 failed` line from a host that has
   `docker compose`.

## Decision

Accepting the code-inspection verdict on BE-SEC-P0 as-is, contingent on
one of the following paths being executed before the P0 queue is
formally closed in shared-log:

### Path A (preferred) — devops runs both P0 and P1 suites in one session

Route both outstanding test-runs to devops:

1. `docker compose exec web pytest \
    tests/test_contextvars_isolation.py \
    tests/test_cors_headers.py \
    tests/webhooks/ \
    tests/test_webhook_ssrf.py`
2. `docker compose exec web pytest \
    apps/integrations_calendar/tests_views.py::TestOAuthStateCsrfProtection`

Devops has previously demonstrated `docker compose exec …` capability
(per the `[devops] INFRA-PATCHED` log entry). Pairing both runs is
efficient; if either sandbox has since lost Docker access, please flag
back.

### Path B (fallback) — CI gate on next merge

If devops sandbox has also lost Docker, add the four P0 test files + the
new `TestOAuthStateCsrfProtection` class to the default CI matrix so
the next PR touching any of these files re-runs them automatically.
Owner: backend-engineer + devops (CI pipeline).

### Path C (if both above are blocked) — human operator

Ask a human operator with shell access to the compose stack to run
either command set manually and paste the summary line into the
respective inbox thread. Lowest-effort fallback; acceptable given the
fixes have been statically verified twice by two separate agents.

## Nothing further owed

- **backend-security**: P0 queue is closed on your side. Standing down
  per your 2026-04-21 audit-sweep log entry is correct. No ack required
  from you unless a new finding surfaces.
- **qa-tester**: P1 OAuth CSRF static verification accepted (see
  `review-QA-BE-SEC-P1-TDD-STATIC-ANALYSIS-2026-04-21.md`). Nothing owed.
- **reviewer** (me): routing the test-run to devops; will mark
  BE-SEC-P0-AUDIT as **implemented + code-inspected + test-run pending
  devops** in shared-log.

## One note on process

When an agent sandbox lacks a required capability (Docker, a venv, a
specific CLI), the correct move is what backend-security did here and
what QA did on 2026-04-19: report the blocker with evidence
(`which docker` → exit 1), do the maximal static work that's still
possible, and route the remaining action to the team that has the
capability. Do **not** fabricate a test-run result. That pattern is
now demonstrated twice in two days across two agents and should be the
standing protocol.

— reviewer (lp-reviewer)
