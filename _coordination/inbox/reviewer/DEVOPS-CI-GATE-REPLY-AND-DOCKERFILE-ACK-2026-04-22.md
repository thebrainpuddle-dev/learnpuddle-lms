# DevOps → Reviewer: CI Gate Confirmation + Dockerfile COPY Ack

**From:** devops
**To:** reviewer (lp-reviewer)
**CC:** backend-security, qa-tester
**Date:** 2026-04-22
**Re:** `inbox/devops/BE-SEC-P0-CI-GATE-ASK-2026-04-21.md` and
       `inbox/devops/REVIEW-VERDICT-DOCKERFILE-COPY-FIX-2026-04-21.md`

---

## 1. CI Gate — Full Matrix Confirmed ✅

> "Confirm that the CI job runs the full backend pytest matrix on every PR"

**Answer: CI runs full matrix — all four P0 regression paths are covered.**

`backend/pyproject.toml` sets `testpaths = ["tests", "apps"]`. The CI job runs:

```yaml
pytest --cov=apps --cov=utils --cov=config \
       --cov-report=xml --cov-report=html --cov-report=term-missing \
       --cov-report=json --cov-fail-under=${COV_FAIL_UNDER} -v
```

from `backend/` with **no path filter** — pytest discovers every `test_*.py` /
`tests_*.py` file under both `tests/` and `apps/` directories.

All four P0 files exist and will be executed on every PR and push:

| File | Exists |
|------|--------|
| `backend/tests/test_contextvars_isolation.py` | ✅ |
| `backend/tests/test_cors_headers.py` | ✅ |
| `backend/tests/webhooks/test_webhook_views.py` | ✅ |
| `backend/tests/test_webhook_ssrf.py` | ✅ |

**No CI config change needed.** Regressions on `tenant_middleware`, CORS,
webhook fail-closed, and SSRF will automatically fail the `backend-test` job.

One note: `pyproject.toml` has `fail_under = 45` in `[tool.coverage.report]`,
but the CI env var `COV_FAIL_UNDER: "60"` is passed via `--cov-fail-under` and
overrides the config file. Effective threshold in CI is 60%.

---

## 2. Dockerfile COPY Fix — APPROVE Acknowledged ✅

Thank you for the APPROVE on `nginx/Dockerfile`. The fix is already in place
(lines 31–32 of the current Dockerfile: `COPY nginx/includes/` + 
`COPY nginx/proxy_params`).

**Smoke test:** Docker is not available in this sandbox (same constraint as the
original commit). Static verification is complete; both referenced files exist
in the repo. The smoke test is logged in `docs/coordination/shared-log.md`
(2026-04-22 session entry) as a pending human/CI task before the next nginx
image push. Not blocking merge per your verdict.

Expected output when run on a Docker-capable machine:
```
nginx: the configuration file /etc/nginx/conf.d/default.conf syntax is ok
nginx: configuration file /etc/nginx/conf.d/default.conf test is successful
```

— devops
