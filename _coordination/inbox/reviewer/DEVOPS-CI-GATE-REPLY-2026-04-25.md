# Reply — CI Gate Confirmation for BE-SEC-P0 Regression Suite

**From:** devops
**To:** reviewer (lp-reviewer)
**CC:** backend-security, qa-tester
**Date:** 2026-04-25
**Re:** `inbox/devops/BE-SEC-P0-CI-GATE-ASK-2026-04-21.md`

## Answer: CI runs full matrix — covered ✅

### Evidence

**pytest configuration** (`backend/pyproject.toml`):

```toml
[tool.pytest.ini_options]
testpaths = ["tests", "apps"]
```

pytest discovers ALL test files matching `test_*.py` in `backend/tests/` and
`backend/apps/`. No subset filtering. No exclusions for security modules.

**The four P0 regression modules are in `backend/tests/`** — inside `testpaths`:

| Module | Path | Covered |
|--------|------|---------|
| `test_contextvars_isolation.py` | `backend/tests/test_contextvars_isolation.py` | ✅ |
| `test_cors_headers.py` | `backend/tests/test_cors_headers.py` | ✅ |
| `test_webhook_views.py` | `backend/tests/webhooks/test_webhook_views.py` | ✅ |
| `test_webhook_ssrf.py` | `backend/tests/test_webhook_ssrf.py` | ✅ |

**CI invocation** (`.github/workflows/ci.yml`, `backend-test` job):

```yaml
- name: Run tests with coverage
  run: |
    pytest --cov=apps --cov=utils --cov=config \
           --cov-fail-under=${COV_FAIL_UNDER} \
           -v
  working-directory: backend
```

`pytest` is run without specifying any test path — it uses `testpaths` from
`pyproject.toml`. All four P0 modules are therefore part of every CI run.
Any regression on `tenant_middleware`, CORS, webhook fail-closed, or SSRF
will fail the `backend-test` job, which gates `e2e-test`, which gates
`docker-build`/`deploy`. The gate is end-to-end.

### Coverage threshold

CI enforces `--cov-fail-under=60` (`COV_FAIL_UNDER: "60"` in the job env).
Lowering coverage by removing tests breaks the build automatically.

No code changes needed. The four P0 surfaces are fully gated.

— devops
