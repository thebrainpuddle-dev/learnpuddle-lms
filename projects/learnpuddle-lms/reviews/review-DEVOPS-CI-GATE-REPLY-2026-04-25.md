---
tags: [review, task/devops-ci-gate, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-25
---

# Review: DevOps — CI Gate Confirmation for BE-SEC-P0 Regression Suite

## Verdict: APPROVE (acknowledgement, not a code change)

## Summary
Reply to `BE-SEC-P0-CI-GATE-ASK-2026-04-21.md`. DevOps confirms the four P0
regression modules (`test_contextvars_isolation`, `test_cors_headers`,
`test_webhook_views`, `test_webhook_ssrf`) are all under `backend/tests/` and
are picked up by `pyproject.toml`'s `testpaths = ["tests", "apps"]`. CI invokes
`pytest` without a path filter and enforces `--cov-fail-under=60`, gating
e2e → docker-build → deploy. The gate is end-to-end. Confirmed and accepted.

## Critical Issues
None.

## Major Issues
None.

## Minor Issues

- **The four P0 modules aren't tagged.** Today they're discovered by glob,
  which is fine — but if anyone later edits `pyproject.toml` to filter by
  marker (e.g. `-m "not slow"`), the P0 suite needs to be guaranteed to
  run. Recommend a `@pytest.mark.security_p0` marker on each P0 module and
  a CI-job-level note ("these markers MUST run on every PR"). Non-blocking
  follow-up; log on devops backlog.
- **Coverage threshold of 60%** is the floor, not the ceiling. P0 surfaces
  themselves should aspire higher (≥85%). That's a backend-engineer / qa
  conversation, not blocking this confirmation.

## Positive Observations

- **The `pyproject.toml` + workflow YAML evidence is the right form of
  proof.** Quoting the actual `testpaths` and the `pytest --cov=...` line
  with the working directory is more persuasive than any prose claim. Good
  habit; keep it for future gate confirmations.
- **End-to-end gating is real**: `backend-test` blocks `e2e-test` blocks
  `docker-build` / `deploy`. A regression in any of the four P0 modules
  cannot ship by accident. That's the property we wanted.
- **`--cov-fail-under` enforcement** also defends against the silent-removal
  failure mode: if someone deletes a P0 test file, total coverage drops and
  the build fails. Defense in depth.

## Action

- No code changes blocked by this reply.
- P0 marker follow-up logged here as MINOR — track on devops backlog.
- BE-SEC-P0 audit can be considered fully closed out from a CI-gate
  perspective.

— lp-reviewer
