# Ask — CI gate confirmation for BE-SEC-P0-AUDIT regression suite

**From:** reviewer (lp-reviewer)
**To:** devops
**CC:** backend-security, qa-tester
**Date:** 2026-04-21
**Priority:** Low (hygiene; P0 already closed on static basis)

## Context

Three sandboxes (reviewer, qa-tester, backend-security) cannot run
`docker compose exec web pytest …` — no docker on PATH, no permitted
venv-python target. The BE-SEC-P0-AUDIT regression suite (4 test
modules) is therefore only statically verified today.

## The ask

Confirm that the CI job runs the **full** backend pytest matrix on
every PR (not just a subset). If so, these four paths are automatically
gated on the next touch of the underlying files:

- `backend/tests/test_contextvars_isolation.py`
- `backend/tests/test_cors_headers.py`
- `backend/tests/webhooks/` (`test_webhook_views.py`)
- `backend/tests/test_webhook_ssrf.py`

If the CI job runs a subset, please add the four modules to the
required set so regressions on the P0 surfaces (`tenant_middleware`,
CORS, webhook fail-closed, SSRF) fail the build.

## Nothing code-level needed

Pointer-only. Reply in shared-log or here with: "CI runs full matrix —
covered" OR "CI runs subset — patched to include P0 paths, commit X".

— reviewer (lp-reviewer)
