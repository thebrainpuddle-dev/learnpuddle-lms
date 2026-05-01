# DevOps: nginx/Dockerfile — missing COPY for includes/ and proxy_params

**From:** devops
**Date:** 2026-04-21
**Priority:** Low (latent build-time gap; no production regression)

## Summary

Full Phase 1–3 re-audit confirmed all previously listed tasks are complete
(see shared-log for table). One new gap identified and fixed.

## Change

**`nginx/Dockerfile`** — Added two `COPY` directives in Stage 2.

### The gap

The Dockerfile bakes `nginx/nginx.conf` as the container's default config
(`/etc/nginx/conf.d/default.conf`), but `nginx.conf` references two files
that were NOT in the image:

1. `include /etc/nginx/includes/shared_locations.conf;` (both HTTP + HTTPS
   server blocks in `nginx.conf`)
2. `include /etc/nginx/proxy_params;` (every `location` block in
   `production.conf`)

In production these are satisfied by volume mounts
(`docker-compose.prod.yml` mounts both paths), so the gap was invisible at
runtime. But if the image is started without the volume mounts — e.g., a
`docker run <image>` smoke test, image scanning tool, Kubernetes deployment
without config maps, or CI healthcheck — nginx would fail with:

```
nginx: [emerg] open() "/etc/nginx/includes/shared_locations.conf" failed
  (2: No such file or directory)
```

### Fix

```diff
 FROM nginx:1.25-alpine
 COPY --from=frontend-build /app/build /usr/share/nginx/html
 COPY nginx/nginx.conf /etc/nginx/conf.d/default.conf
+# Bake in supporting config files so the image is self-contained.
+# Production/staging override default.conf at runtime via volume mount, but
+# having these files in the image means the container can also start cleanly
+# without any volume mounts (e.g. smoke tests, standalone runs).
+COPY nginx/includes/ /etc/nginx/includes/
+COPY nginx/proxy_params /etc/nginx/proxy_params
 # Fix ownership so nginx user can write to cache, logs, and pid file.
```

## Verification (manual — Docker not available in sandbox)

| Check | Result |
|-------|--------|
| `nginx/nginx.conf` references `include /etc/nginx/includes/shared_locations.conf` | ✅ lines 74, 97 |
| `nginx/includes/shared_locations.conf` exists in repo | ✅ |
| `COPY nginx/includes/ /etc/nginx/includes/` will produce `/etc/nginx/includes/shared_locations.conf` | ✅ |
| `nginx/production.conf` references `include /etc/nginx/proxy_params` | ✅ lines 99, 115, 125, 133, 144, 174, 180 |
| `nginx/proxy_params` exists in repo | ✅ |
| `COPY nginx/proxy_params /etc/nginx/proxy_params` exact path match | ✅ |
| chown block is unchanged; root-owned files world-readable by `nginx` user | ✅ |
| No impact on existing volume mounts (mounts still override baked-in files) | ✅ |

Please run `docker build -f nginx/Dockerfile -t lms-nginx-test . && docker run --rm lms-nginx-test nginx -t` to confirm `nginx -t` passes before merging.

— devops
