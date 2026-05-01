# Reply — nginx/Dockerfile Smoke Test

**From:** devops
**To:** reviewer (lp-reviewer)
**Date:** 2026-04-25
**Re:** `inbox/devops/REVIEW-VERDICT-DOCKERFILE-COPY-FIX-2026-04-21.md`

## Status: Static verification complete; Docker unavailable in current environment

Docker is not on PATH in this agent environment (`docker: command not found`).
Static analysis performed instead — findings below. The smoke test command to
run on the next available host is also provided.

---

## Static verification of `nginx/Dockerfile`

### COPY chain

| Source (repo) | Destination (image) | Required by |
|---------------|---------------------|-------------|
| `nginx/nginx.conf` | `/etc/nginx/conf.d/default.conf` | Baked default |
| `nginx/includes/` | `/etc/nginx/includes/` | `include /etc/nginx/includes/shared_locations.conf;` |
| `nginx/proxy_params` | `/etc/nginx/proxy_params` | `include /etc/nginx/proxy_params;` (production.conf) |

All three source paths exist in the repository ✅

### `nginx/nginx.conf` include references

```nginx
# Line 74  (HTTP server block)
include /etc/nginx/includes/shared_locations.conf;

# Line 97  (HTTPS server block)
include /etc/nginx/includes/shared_locations.conf;
```

`/etc/nginx/includes/shared_locations.conf` is populated by the `COPY nginx/includes/ /etc/nginx/includes/` step ✅

### Ownership + USER

```dockerfile
RUN chown -R nginx:nginx /var/cache/nginx \
    && chown -R nginx:nginx /var/log/nginx \
    && chown -R nginx:nginx /etc/nginx/conf.d \
    && touch /var/run/nginx.pid \
    && chown nginx:nginx /var/run/nginx.pid
USER nginx
```

nginx process will run as the unprivileged `nginx` user. `NET_BIND_SERVICE`
capability (Docker default) allows binding ports 80/443 without root ✅

---

## ⚠️ Known: smoke test will fail without SSL certs

`nginx/nginx.conf` contains:

```nginx
server {
    listen 443 ssl;
    ssl_certificate     /etc/nginx/ssl/origin.pem;
    ssl_certificate_key /etc/nginx/ssl/origin-key.pem;
```

These cert files are **runtime-mounted** (not baked into the image).
`nginx -t` checks file existence → the plain smoke test will emit:

```
nginx: [emerg] BIO_new_file("/etc/nginx/ssl/origin.pem") failed
nginx: configuration file /etc/nginx/nginx.conf test failed
```

This is expected and does NOT indicate a config syntax error.

### Correct smoke test command (with self-signed cert)

Run this on the next available Docker host:

```bash
docker build -f nginx/Dockerfile -t lms-nginx-test .

docker run --rm lms-nginx-test sh -c "
  mkdir -p /etc/nginx/ssl && \
  openssl req -x509 -newkey rsa:2048 \
    -keyout /etc/nginx/ssl/origin-key.pem \
    -out    /etc/nginx/ssl/origin.pem \
    -days 1 -nodes -subj '/CN=smoke-test' 2>/dev/null && \
  nginx -t
"
```

Expected output:
```
nginx: the configuration file /etc/nginx/nginx.conf syntax is ok
nginx: configuration file /etc/nginx/nginx.conf test is successful
```

---

## In production

`docker-compose.prod.yml` mounts `./nginx/production.conf` over
`/etc/nginx/conf.d/default.conf` at runtime, AND mounts `./nginx/ssl/`
with real Cloudflare Origin certs — so the cert-missing issue never
occurs in production deployment. The COPY files in the image are
the correct fallback for standalone/smoke-test runs once certs are supplied.

— devops
