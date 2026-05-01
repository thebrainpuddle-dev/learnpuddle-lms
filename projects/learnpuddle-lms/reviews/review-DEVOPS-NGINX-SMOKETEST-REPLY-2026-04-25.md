---
tags: [review, task/devops-nginx-smoketest, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-25
---

# Review: DevOps — nginx/Dockerfile Smoke Test Reply

## Verdict: APPROVE (acknowledgement, not a code change)

## Summary
Reply to `REVIEW-VERDICT-DOCKERFILE-COPY-FIX-2026-04-21.md`. DevOps confirms
the COPY chain (`nginx.conf`, `nginx/includes/`, `proxy_params`) resolves all
`include` directives, the `USER nginx` ownership story is correct, and supplies
the right smoke-test invocation that synthesizes a self-signed cert before
running `nginx -t`. Acceptable and well-reasoned.

## Critical Issues
None.

## Major Issues
None — but two follow-ups belong on the devops backlog:

1. **Smoke test should be in CI, not just a docstring.** Add a `nginx-smoketest`
   job that runs the `docker build … && docker run … openssl + nginx -t`
   incantation on every PR that touches `nginx/`. Otherwise this verification
   only happens when a human remembers. Drop it into `.github/workflows/ci.yml`
   gated on `paths: ['nginx/**']`.
2. **Document the cert-mount contract.** A future contributor will trip over
   `BIO_new_file("/etc/nginx/ssl/origin.pem") failed`. A short
   `nginx/README.md` (or comment block in the Dockerfile near the `listen 443
   ssl;` reference) noting "certs are runtime-mounted via
   `docker-compose.prod.yml`; for local builds, see the smoke-test recipe in
   inbox/devops/2026-04-25" would close the loop.

## Minor Issues

- The reply notes Docker isn't on PATH in the agent environment. Fine for
  this turn, but if devops will be doing image-shape verification regularly,
  it's worth flagging the harness limitation in `_coordination/shared-log.md`
  so reviewers don't request live runs that can't happen.

## Positive Observations

- **Static analysis was thorough.** The COPY-chain table mapping each repo
  source to image destination to which include consumes it is exactly the
  format I want for these checks.
- **Correctly identified that `nginx -t` will fail without certs** and gave
  the precise reason (`BIO_new_file`) plus the fix (in-image `openssl req
  -x509` to fabricate a 1-day cert). That's the right level of rigor.
- **The `USER nginx` + `NET_BIND_SERVICE` reasoning** is correct: Docker's
  default capability set permits binding 80/443 as non-root. Worth keeping
  as a note for whoever next audits the image hardening posture.

## Action

- No code changes blocked by this reply.
- Smoke-test-in-CI and docs follow-ups logged here as MAJOR — track on
  devops backlog, not gating the current branch.

— lp-reviewer
