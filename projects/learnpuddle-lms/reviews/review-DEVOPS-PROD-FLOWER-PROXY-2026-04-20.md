---
tags: [review, task/DEVOPS-PROD-FLOWER-PROXY, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-20
---

# Review: DEVOPS — production.conf `/flower/` proxy + pre-deploy-check hardening

## Verdict: APPROVE

## Summary

Small, correct, defense-in-depth change. Closes a real gap (flower UI was
unreachable via nginx in prod despite the upstream service being up and
authenticated) and tightens the pre-deploy check to detect missing
production-only nginx files. Pattern matches the existing `nginx.staging.conf`
implementation and complies with how `flower` is launched in
`docker-compose.prod.yml`.

## Scope Verified

| Concern | Result |
|---------|--------|
| Resolver is reachable by the new `location /flower/` block | OK — `resolver 127.0.0.11 valid=10s ipv6=off;` at file top (line 3), http-context when mounted into `conf.d/` |
| Variable-form `proxy_pass` requires resolver + fails gracefully when flower is down | OK — `set $flower_upstream flower:5555;` + variable in `proxy_pass` (lines 104–110) |
| URL prefix matches flower's launch flags | OK — `docker-compose.prod.yml` launches flower with `--url_prefix=flower` (line 182); nginx preserves the `/flower/` prefix (no trailing slash on `proxy_pass`), so flower receives URIs it expects |
| IP ACL blocks the public internet | OK — allow 10/8, 172.16/12, 192.168/16, 127.0.0.1 + `deny all` (matches `/metrics` at L88–97 and `nginx.staging.conf` L189–205) |
| Second layer of auth in addition to ACL | OK — `FLOWER_BASIC_AUTH` env var is required in compose (line 191 uses `:?Set FLOWER_PASSWORD in .env`), so even internal attackers must authenticate |
| WebSocket headers present for flower's live task stream | OK — `Upgrade` / `Connection: upgrade` set (lines 113–114) |
| `include /etc/nginx/proxy_params;` does not conflict with WS headers | OK — proxy_params sets Host/X-Real-IP/X-Forwarded-*/X-Request-ID/timeouts, no Upgrade or Connection overrides |
| `pre-deploy-check.sh` catches missing production.conf | OK — L246 now iterates `backend/Dockerfile nginx/nginx.conf nginx/production.conf nginx/proxy_params` and `fail`s when any is missing |

## Critical Issues

None.

## Major Issues

None.

## Minor Issues

**m1. 60s read/send timeout may clip long-lived flower panels.**
`proxy_params` sets `proxy_read_timeout 60s` and `proxy_send_timeout 60s`, which
apply here because the new block does not override them. Flower's live-task SSE
stream will disconnect every 60s and reconnect. The UI handles reconnects, so
this is cosmetic, not broken — but if operators report flicker we should override
to, e.g., `proxy_read_timeout 300s;` (matches the MAIC SSE block).

**m2. No HSTS/CSP consideration.**
The server-level CSP (L48) is permissive enough that flower's inline scripts
load, and the IP ACL ensures this URL isn't reachable from public browsers
anyway. Non-blocking. Worth a follow-up note if we ever widen the ACL.

**m3. `nginx.conf` (dev) still lacks `/flower/`.**
The local-dev nginx.conf search returned no hits for `/flower/`. Dev operators
use `localhost:5555` directly so this is working-as-intended, but an eventual
parity pass would be nice. Out of scope for this change.

## Positive Observations

- **Variable-form `proxy_pass` pattern is correct.** Using
  `set $flower_upstream flower:5555;` + `proxy_pass http://$flower_upstream;`
  means nginx defers DNS resolution to the resolver at request time. Without the
  variable, nginx would fail fast at startup if the flower container isn't up,
  preventing rolling restarts — exactly the subtle issue the devops note calls
  out.
- **Matches an existing, proven pattern.** The staging config has the same
  block at L189–205; keeping parity simplifies ops playbooks and review.
- **Pre-deploy-check scope fix is good hygiene.** Previously the script checked
  `nginx/nginx.conf` (baked into the image), but production mounts
  `nginx/production.conf` over it via volume. A missing production.conf would
  have led to a silent fallback to the baked-in dev config — exactly the class
  of failure that belongs on the pre-deploy checklist. Adding
  `nginx/proxy_params` too is correct because production.conf `include`s it.
- **No attempt to skip hooks, no git ops performed by devops author.**

## Recommended Verification (for operator running this)

`docker not available in sandbox`, so static analysis only. Before merging,
please run:

```bash
docker compose -f docker-compose.prod.yml config --quiet && echo OK
# And after the rebuild, on a prod-like host:
curl -I http://<internal-ip>/flower/        # 401 expected (basic auth)
curl -I -u admin:$FLOWER_PASSWORD http://<internal-ip>/flower/   # 200 expected
```

— lp-reviewer
