---
tags: [review, area/devops, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-21
---

# Review: nginx/Dockerfile — COPY includes/ and proxy_params

## Verdict: APPROVE

## Summary

Two-line hardening so the nginx image is self-contained. Matches the
`include` directives in both `nginx.conf` (line 74, 97) and
`production.conf`. Production behaviour is unchanged because runtime
volume mounts still take precedence.

## Verification

| Check | Result |
|-------|--------|
| `nginx.conf` references `include /etc/nginx/includes/shared_locations.conf` | ✅ lines 74, 97 |
| `nginx/includes/shared_locations.conf` exists in repo | ✅ |
| `COPY nginx/includes/ /etc/nginx/includes/` resolves path correctly | ✅ |
| `nginx/proxy_params` exists in repo | ✅ |
| `COPY nginx/proxy_params /etc/nginx/proxy_params` exact match | ✅ |
| Ownership / USER nginx unchanged | ✅ (lines 36–42) |
| Runtime volume mounts in `docker-compose.prod.yml` still override | ✅ (mounts land at the same paths) |

## Critical / Major Issues
None.

## Minor Issues

1. **(non-blocking) Smoke test pending.** Author correctly called out
   that they couldn't `docker build && docker run … nginx -t` in the
   sandbox. Before the next nginx-image push, run:
   ```
   docker build -f nginx/Dockerfile -t lms-nginx-test .
   docker run --rm lms-nginx-test nginx -t
   ```
   and paste the `configuration file … test is successful` line into
   the shared-log. Not gating merge because the failure mode (missing
   `include` target) is deterministic and trivially verifiable from
   the Dockerfile + repo layout.

## Positive Observations

- Fix is tightly scoped (2 new COPY lines, 1 explanatory comment).
- Comment explains *why* the COPY exists (smoke tests / k8s without
  configmaps) — future maintainers won't wonder if it's dead weight.
- No change to `chown`, USER, or port exposure; existing security
  posture (non-root `nginx` user + NET_BIND_SERVICE capability) intact.

— reviewer (lp-reviewer)
