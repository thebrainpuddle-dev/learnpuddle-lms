# Cloudflare → Host Error: Troubleshooting Guide

When Cloudflare shows "Host Error" or similar (521, 522, 523, 524), the connection between Cloudflare and your origin (Droplet) is failing. Use this checklist to fix it.

---

## 1. Cloudflare SSL/TLS Mode

**Required: Flexible** (when origin has no SSL certificate)

- Cloudflare Dashboard → SSL/TLS → Overview
- Set to **Flexible**
- Flexible = HTTPS (user ↔ Cloudflare) + HTTP (Cloudflare ↔ origin)
- Our nginx listens on port 80 (HTTP) only

| Mode | User → CF | CF → Origin | Our setup |
|------|-----------|-------------|-----------|
| Off | HTTP | HTTP | ✓ |
| Flexible | HTTPS | HTTP | ✓ **Use this** |
| Full | HTTPS | HTTPS | ✗ Origin has no cert |
| Full (Strict) | HTTPS | HTTPS (valid cert) | ✗ |

---

## 2. DNS Records (Cloudflare)

Ensure these exist and point to your **Droplet IP**:

| Type | Name | Content | Proxy |
|------|------|---------|-------|
| A | `@` | `YOUR_DROPLET_IP` | Proxied (orange) |
| A | `*` | `YOUR_DROPLET_IP` | Proxied (orange) |

- `@` = root domain (learnpuddle.com)
- `*` = wildcard (school.learnpuddle.com, etc.)

**Verify:** `dig learnpuddle.com` and `dig foo.learnpuddle.com` should return Cloudflare IPs when proxied.

---

## 3. Droplet Firewall

Ports 80 and 443 must be open:

```bash
# On Droplet
ufw status
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 22/tcp   # SSH
ufw enable
ufw status
```

---

## 4. Docker & Nginx Running

```bash
# On Droplet
cd /opt/lms  # or your app dir
docker compose -f docker-compose.prod.yml ps

# All services should be "Up"
# nginx should show ports 0.0.0.0:80->80/tcp
```

If nginx isn't running:

```bash
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml logs nginx
```

---

## 5. Direct Origin Test (Bypass Cloudflare)

Test if the origin responds when hit directly:

```bash
# From your Mac (replace with Droplet IP)
curl -v -H "Host: learnpuddle.com" http://YOUR_DROPLET_IP/health/
```

Expected: `200 OK` with JSON body. If this fails, the issue is on the Droplet (Docker/nginx), not Cloudflare.

---

## 6. Django ALLOWED_HOSTS

Ensure `.env` has:

```
PLATFORM_DOMAIN=learnpuddle.com
```

Docker-compose sets:
- `ALLOWED_HOSTS=.learnpuddle.com,learnpuddle.com,localhost`

If the Host header doesn't match, Django returns 400 Bad Request.

---

## 7. Cloudflare Error Codes

| Code | Meaning | Fix |
|------|---------|-----|
| 521 | Origin web server down | Check Docker, nginx, web service |
| 522 | Connection timed out | Firewall, wrong IP, port closed |
| 523 | Origin unreachable | DNS, network, wrong IP |
| 524 | Timeout (100s) | Slow origin; increase timeout or optimize |

---

## 8. Quick Checklist

- [ ] Cloudflare SSL mode = **Flexible**
- [ ] DNS: `@` and `*` A records → Droplet IP
- [ ] Droplet: ports 80, 443 open (ufw)
- [ ] Docker: `docker compose ps` shows all Up
- [ ] `curl -H "Host: learnpuddle.com" http://DROPLET_IP/health/` returns 200
- [ ] `.env` has `PLATFORM_DOMAIN=learnpuddle.com`

---

## 9. Optional: Cloudflare "Full" Mode (HTTPS to Origin)

To use Full or Full Strict:

1. Generate Cloudflare Origin Certificate (Dashboard → SSL/TLS → Origin Server)
2. Save cert and key to Droplet
3. Uncomment the SSL server block in `nginx/nginx.conf`
4. Set Cloudflare SSL to **Full** or **Full (Strict)**
