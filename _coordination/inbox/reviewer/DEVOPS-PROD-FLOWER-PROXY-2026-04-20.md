# DevOps: production.conf /flower/ proxy + pre-deploy-check hardening

**From:** devops  
**Date:** 2026-04-20  
**Priority:** Low (security hygiene, no functional regression)

## Summary

Full infrastructure audit completed. All listed DevOps Phase 1–3 tasks were already
done on the branch. Found and fixed one genuine gap.

## Change

**`nginx/production.conf`** — Added missing `/flower/` proxy location.

The config already had `set $flower_upstream flower:5555` declared (matching the
`nginx.conf` pattern) but no location block that used it. Flower's monitoring UI
was therefore unreachable via nginx in production — operators had to SSH-tunnel
directly to port 5555.

The new block:
```nginx
location /flower/ {
    set $flower_upstream flower:5555;
    allow 10.0.0.0/8;
    allow 172.16.0.0/12;
    allow 192.168.0.0/16;
    allow 127.0.0.1;
    deny all;
    proxy_pass http://$flower_upstream;
    include /etc/nginx/proxy_params;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
}
```

Key decisions:
- **Variable-based `proxy_pass`**: Uses `set $flower_upstream` + `resolver 127.0.0.11`
  (already present at top of file) so nginx starts cleanly even if the flower
  container is momentarily down during rolling restarts.
- **IP restrictions**: Same ACL as `/metrics` — Docker-internal ranges only.
  External traffic (from Cloudflare or public internet) is denied.
- **WebSocket headers**: Required for Flower's real-time task status updates.

**`scripts/pre-deploy-check.sh`** — Added `nginx/production.conf` and
`nginx/proxy_params` to the required-files check. Previously it only checked
`nginx/nginx.conf` (the baked-in image default that gets overridden by the
volume mount), which meant missing production.conf would not be caught before deploy.

## Verification

Docker not available in sandbox — manual review confirms:
- `resolver 127.0.0.11` is at http-context level (top of production.conf) ✅
- `set $flower_upstream` is inside `location /flower/` (valid rewrite directive) ✅
- `proxy_pass` uses variable form (requires resolver — present) ✅
- IP `allow/deny` pattern matches `/metrics` and `nginx.staging.conf` /flower/ ✅
- WebSocket upgrade headers match `/ws/` block pattern ✅
- File closes properly with `}` at line 199 ✅

Please run `docker compose -f docker-compose.prod.yml config` to confirm syntax
before merging.

— devops
