---
tags: [review, branch/codex-session-idle-timeout-fix, verdict/request-changes, reviewer/lp-reviewer]
created: 2026-03-25
---

# Review: codex/session-idle-timeout-fix — Cloudflare Origin SSL + Real IP Config

## Branch: `codex/session-idle-timeout-fix`
## Commit: `a472948`
## Verdict: REQUEST_CHANGES

## Summary
This commit adds Cloudflare Origin Certificate SSL and real IP restoration to the nginx config, plus mounts the SSL cert directory in docker-compose.prod.yml. The changes are **already merged to main** — the current `nginx/nginx.conf` already contains the SSL server block and Cloudflare real IP ranges. However, reviewing the approach reveals several issues worth documenting.

## Critical Issues

### 1. SECURITY: SSL server block is a degraded copy of HTTP block
The SSL server block in the commit uses hardcoded upstream hostnames (`web:8000`, `flower:5555`, `asgi:8001`) instead of nginx variables with Docker DNS resolver. This means:
- After container restarts, nginx may cache stale IPs causing 502 errors on HTTPS
- The HTTP block uses `$django_upstream` variables with `resolver 127.0.0.11` — SSL block doesn't

**Status on main**: This has been fixed — main's SSL block uses `$django_upstream`, `$asgi_upstream`, `$flower_upstream` variables properly. ✅

### 2. SECURITY: SSL block missing video upload location
The HTTP block has a special `location ~ ^/api/courses/.../video-upload/?$` with extended timeouts and disabled buffering. The SSL block in the commit doesn't include this, meaning video uploads over HTTPS would time out at 120s instead of 3600s.

**Status on main**: Fixed — main's SSL block includes the video upload location. ✅

## Major Issues

### 3. SSL block missing `resolver` directive
Without `resolver 127.0.0.11`, nginx can't resolve Docker service names dynamically in the SSL block. The commit's SSL block uses hardcoded names in `proxy_pass` which works differently from variable-based resolution.

**Status on main**: Fixed with variable-based upstreams. ✅

### 4. SSL block missing Django admin location
The commit's SSL block has `/admin/` but main uses `/django-admin/` to separate from tenant SPA admin routes. This could cause confusion.

### 5. Missing `proxy_next_upstream` directives in SSL block
The HTTP block has retry/failover logic:
```
proxy_next_upstream error timeout invalid_header http_502 http_503 http_504;
proxy_next_upstream_tries 2;
proxy_next_upstream_timeout 15s;
```
These are missing from the commit's SSL block.

**Status on main**: Fixed. ✅

## Minor Issues

### 6. CSP policy differs between HTTP and SSL blocks
The commit's SSL block CSP doesn't include `https://app.cal.com` and `https://cal.com` in frame-src/child-src, which the main branch's HTTP block does. This means Cal.com embeds would break on HTTPS.

**Status on main**: Fixed — both blocks have identical CSP. ✅

### 7. Cloudflare IP ranges should be periodically updated
The hardcoded IP ranges will go stale. Consider adding a comment with the date they were fetched and a link to Cloudflare's IP range API (`https://api.cloudflare.com/client/v4/ips`).

### 8. Branch name misleading
Branch is named `codex/session-idle-timeout-fix` but the commit is about SSL/real IP config, not session idle timeouts.

## Positive Observations

1. **Correct Cloudflare real IP setup** — using `CF-Connecting-IP` with `real_ip_recursive on` is the right approach
2. **Complete IPv4 + IPv6 ranges** — all Cloudflare ranges are included
3. **Good SSL configuration** — TLS 1.2+, no weak ciphers, session cache enabled
4. **Docker volume mount** for SSL certs is clean and read-only (`ro`)

## Recommendation
The issues identified in this commit were subsequently fixed in later commits that are now on main. The current state of main's `nginx/nginx.conf` is correct. This branch can be **deleted** as it's fully superseded. If not yet deleted, mark as stale.

No merge action needed — changes already on main in improved form.
