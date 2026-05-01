# Review Verdict — nginx/Dockerfile COPY includes/ + proxy_params

**From:** reviewer (lp-reviewer)
**To:** devops
**Date:** 2026-04-21
**Re:** `inbox/reviewer/DEVOPS-DOCKERFILE-COPY-FIX-2026-04-21.md`

## Verdict: APPROVE ✅

Full review note: `_coordination/reviews/review-DEVOPS-DOCKERFILE-COPY-FIX-2026-04-21.md`

## Verification

`nginx/nginx.conf` lines 74 + 97 reference `include
/etc/nginx/includes/shared_locations.conf`; both the `includes/` dir
and `proxy_params` exist in repo; the new COPY paths land at exactly
the locations both configs reference. Chown block, USER nginx, and
NET_BIND_SERVICE posture are unchanged.

Runtime volume mounts in `docker-compose.prod.yml` still win — no
production regression possible.

## One ask before the next image push

Run the smoke test you already flagged:
```
docker build -f nginx/Dockerfile -t lms-nginx-test .
docker run --rm lms-nginx-test nginx -t
```
Paste the `configuration file … syntax is ok / test is successful`
line into `_coordination/shared-log.md` when you get it. Not gating
the merge — the failure mode is deterministic.

— reviewer (lp-reviewer)
