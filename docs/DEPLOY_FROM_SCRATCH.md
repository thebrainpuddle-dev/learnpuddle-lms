# LearnPuddle: Deploy from Scratch (Complete Guide)

Step-by-step instructions to deploy LearnPuddle to a fresh DigitalOcean Droplet with Cloudflare.

**All commands in Parts C–G run on the Droplet** — SSH in first: `ssh root@YOUR_DROPLET_IP`

---

## Quick Fixes

### "Permission denied: '/app/staticfiles/admin'"

If `collectstatic` fails with this error, run it as root:
```bash
docker compose -f docker-compose.prod.yml run --rm -u root web python manage.py collectstatic --noinput
```

### "Welcome to nginx!" or "405 Not Allowed" on learnpuddle.com

**Cause:** System nginx (installed on the host) is binding to port 80 instead of Docker. Traffic never reaches the app.

**Fix (on the Droplet):**
```bash
# Stop and disable system nginx
systemctl stop nginx
systemctl disable nginx

# Verify Docker nginx is using port 80
docker compose -f docker-compose.prod.yml ps
# nginx container should be "Up"

# If nginx wasn't running, restart all services
cd /opt/lms
docker compose -f docker-compose.prod.yml up -d

# Verify: port 80 should be used by Docker
ss -tlnp | grep :80
# Should show "docker-proxy" or "containerd", not "nginx"
```

**If you see a blank white screen** (main.xxx.js and main.xxx.css return 404), the nginx image may have stale frontend. Rebuild nginx (frontend is baked into the image):

```bash
cd /opt/lms
git pull

# Rebuild nginx (includes frontend build)
docker compose -f docker-compose.prod.yml build --no-cache nginx

# Restart nginx
docker compose -f docker-compose.prod.yml up -d nginx

# Verify React files are in the image
docker compose -f docker-compose.prod.yml run --rm -T nginx ls -la /usr/share/nginx/html/static/js/
# Should show main.*.js and chunk files
```

Then hard-refresh the page (Ctrl+Shift+R or Cmd+Shift+R) to clear cached index.html.

### ".env.production.example: No such file or directory"

If you see this after cloning, the template may be missing. On the Droplet:

```bash
cd /opt/lms
cp .env.example .env    # fallback if .env.production.example missing
nano .env              # edit and fill values
```

Then continue from **D.5 Fill .env** below.

---

## Part A: Cloudflare DNS (Do First)

### A.1 Fix Duplicate A Record

Your DNS shows **two A records** for `learnpuddle.com`:
- `64.227.185.164` ← **Keep this** (your Droplet)
- `162.255.119.94` ← **Remove this** (old/wrong IP)

**Action:** In Cloudflare → DNS → Records:
1. Find the A record for `learnpuddle.com` pointing to `162.255.119.94`
2. Click **Edit** → **Delete**
3. Keep only the record pointing to `64.227.185.164`

### A.2 Required DNS Records

| Type | Name | Content | Proxy | Notes |
|------|------|---------|-------|-------|
| A | `@` | `64.227.185.164` | Proxied (orange) | Root: learnpuddle.com |
| A | `*` | `64.227.185.164` | Proxied (orange) | Wildcard: school.learnpuddle.com |
| CNAME | `www` | `learnpuddle.com` | Proxied | Optional |

**Replace `64.227.185.164`** with your actual Droplet IP if different.

### A.3 Cloudflare SSL Mode

1. Cloudflare Dashboard → **SSL/TLS** → **Overview**
2. Set to **Flexible**
3. (Flexible = HTTPS to visitors, HTTP to your server)

### A.4 Domain Mapping: How It Works

| Layer | Where | What it does |
|-------|-------|---------------|
| **1. DNS (Cloudflare)** | Cloudflare → DNS → Records | `@` and `*` A records point `learnpuddle.com` and `*.learnpuddle.com` to your Droplet IP. All traffic for root + subdomains goes to the same server. |
| **2. Nginx** | `nginx/nginx.conf` | `server_name _` accepts any Host. Forwards requests to Django with `Host` header intact. No per-domain config. |
| **3. Django** | `.env` → `PLATFORM_DOMAIN` | `ALLOWED_HOSTS=.learnpuddle.com,learnpuddle.com` validates the Host. `tenant_utils.py` resolves tenant from subdomain. |
| **4. Tenant resolution** | `backend/utils/tenant_utils.py` | `learnpuddle.com` → platform root (no tenant). `school.learnpuddle.com` → Tenant(subdomain='school'). |

**Flow:** User visits `https://demo.learnpuddle.com` → Cloudflare resolves to Droplet IP → Nginx receives request → Django gets `Host: demo.learnpuddle.com` → tenant_utils extracts `demo` → loads Tenant(subdomain='demo').

**No per-school DNS.** The wildcard `*` covers all subdomains. When a school signs up with subdomain `silveroaks`, `silveroaks.learnpuddle.com` works immediately.

---

## Part B: DigitalOcean Droplet

### B.1 Create Droplet

1. Log in to [DigitalOcean](https://cloud.digitalocean.com)
2. **Create** → **Droplets**
3. **Image:** Ubuntu 22.04 LTS
4. **Plan:** Basic, $12/mo (2 GB RAM, 1 vCPU) or higher
5. **Region:** Choose closest to users (e.g. Bangalore, Singapore)
6. **Authentication:** SSH key (recommended) or password
7. **Hostname:** `learnpuddle-prod` (optional)
8. Click **Create Droplet**
9. **Note the IP address** (e.g. `64.227.185.164`)

### B.2 Update Cloudflare DNS (if new Droplet)

If you created a new Droplet with a different IP:
- Update both A records (`@` and `*`) in Cloudflare to the new IP

---

## Part C: Droplet Setup (SSH into server)

### C.1 Connect

```bash
ssh root@64.227.185.164
```

(Replace with your Droplet IP.)

### C.2 Update System & Install Docker

```bash
apt update && apt upgrade -y
curl -fsSL https://get.docker.com | sh
apt install -y docker-compose-plugin git
```

Verify:
```bash
docker --version
docker compose version
```

### C.3 Open Firewall Ports

```bash
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable
ufw status
```

---

## Part D: Clone & Configure App

### D.1 Clone Repository

```bash
mkdir -p /opt/lms
cd /opt/lms
git clone https://github.com/thebrainpuddle-dev/learnpuddle-lms.git .
```

The trailing `.` clones into the current directory (`/opt/lms`). If you cloned without the dot and got a `learnpuddle-lms` subfolder:
```bash
cd /opt/lms
mv learnpuddle-lms/* learnpuddle-lms/.[!.]* . 2>/dev/null || true
rmdir learnpuddle-lms 2>/dev/null || true
```

**If SSH fails (Permission denied):** Use HTTPS instead:
```bash
git clone https://github.com/thebrainpuddle-dev/learnpuddle-lms.git .
```

### D.2 Create .env File

```bash
cd /opt/lms

# Use production template if it exists, otherwise .env.example
if [ -f .env.production.example ]; then
  cp .env.production.example .env
elif [ -f .env.example ]; then
  cp .env.example .env
else
  echo "ERROR: No .env template found. Run: ls -la .env*"
  exit 1
fi

nano .env
```

**If you get "No such file or directory":** The repo may be missing the template. Use either:
```bash
cp .env.example .env    # if .env.example exists
# or create manually: nano .env
```

### D.3 Where to Run Commands

All deploy commands run **on the Droplet** via SSH. Two ways:

| Method | How |
|--------|-----|
| **SSH session** | `ssh root@YOUR_IP` then run commands in the terminal |
| **Remote one-liner** | From your Mac: `ssh root@YOUR_IP "cd /opt/lms && COMMAND"` |

There is **no DigitalOcean dashboard for .env** on a Droplet. Droplets are plain VPS—you manage files via SSH. (App Platform has env vars in the UI; we use a Droplet.)

### D.4 Generate Secrets (on your Mac or Droplet)

Run these and copy the output:

```bash
openssl rand -hex 50      # Use for SECRET_KEY and JWT_SIGNING_KEY
openssl rand -base64 24   # Use for DB_PASSWORD, REDIS_PASSWORD, FLOWER_PASSWORD
```

### D.5 Fill .env (Required Values)

Edit `nano .env` and set:

```
# Core
SECRET_KEY=<paste first openssl output>
DEBUG=False

# Platform
PLATFORM_DOMAIN=learnpuddle.com
PLATFORM_NAME=LearnPuddle

# Database
DB_NAME=learnpuddle_db
DB_USER=learnpuddle
DB_PASSWORD=<paste first base64 output>

# Redis
REDIS_PASSWORD=<paste second base64 output>

# JWT (use same hex as SECRET_KEY or generate another)
JWT_SIGNING_KEY=<paste second hex or same as SECRET_KEY>

# Flower
FLOWER_USER=admin
FLOWER_PASSWORD=<paste third base64 output>
```

### D.6 Update .env Later (After Deploy)

To change env vars:

1. **SSH:** `ssh root@YOUR_IP`
2. **Edit:** `cd /opt/lms && nano .env`
3. **Restart:** `docker compose -f docker-compose.prod.yml up -d`

**From your Mac (edit locally, then copy):**
```bash
# Create .env on your Mac, edit, then:
scp .env root@YOUR_IP:/opt/lms/.env
# Then SSH and restart: ssh root@YOUR_IP "cd /opt/lms && docker compose -f docker-compose.prod.yml up -d"
```

**DigitalOcean:** Droplets have no env UI. Use SSH + `nano` or `scp`. (App Platform has env vars in the dashboard; we use a Droplet.)

### D.7 Storage & Email (Choose One)

**Option A — Local storage + console email (simplest for first deploy):**

```
STORAGE_BACKEND=local
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
```

(Comment out or leave empty: STORAGE_ACCESS_KEY, STORAGE_SECRET_KEY, etc.)

**Option B — DigitalOcean Spaces + Resend (production):**

```
STORAGE_BACKEND=s3
STORAGE_ACCESS_KEY=<from DO Spaces>
STORAGE_SECRET_KEY=<from DO Spaces>
STORAGE_BUCKET=learnpuddle-media
STORAGE_REGION=sgp1
STORAGE_ENDPOINT=https://sgp1.digitaloceanspaces.com
CDN_DOMAIN=learnpuddle-media.sgp1.cdn.digitaloceanspaces.com

EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.resend.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=resend
EMAIL_HOST_PASSWORD=<Resend API key>
DEFAULT_FROM_EMAIL=noreply@learnpuddle.com
```

Save and exit: `Ctrl+O`, `Enter`, `Ctrl+X`.

---

## Part E: Build & Start Services

### E.1 Start Database and Redis

```bash
cd /opt/lms
docker compose -f docker-compose.prod.yml up -d db redis
```

Wait for DB to be ready:
```bash
sleep 20
```

### E.2 Run Migrations

```bash
docker compose -f docker-compose.prod.yml run --rm web python manage.py migrate --noinput
```

### E.3 Collect Static Files

```bash
docker compose -f docker-compose.prod.yml run --rm -u root web python manage.py collectstatic --noinput
```

### E.4 Create Superadmin User

```bash
docker compose -f docker-compose.prod.yml run --rm web python manage.py createsuperuser
```

Enter:
- **Email:** `admin@learnpuddle.com` (or your email)
- **Password:** (choose a strong password)

### E.5 Start All Services

```bash
docker compose -f docker-compose.prod.yml up -d
```

First run may take 3–5 minutes while the nginx image builds (includes frontend).

### E.6 Verify Services

```bash
docker compose -f docker-compose.prod.yml ps
```

These should show `Up`: db, redis, web, asgi, worker, beat, nginx, flower. The `certbot` container may show a different state—that’s fine. Check nginx:
```bash
curl -s http://localhost/health/
```

Expected: JSON with `"status": "ok"`.

---

## Part F: Verify from Outside

### F.1 Test Direct to Droplet (bypass Cloudflare)

From your Mac:
```bash
curl -v -H "Host: learnpuddle.com" http://64.227.185.164/health/
```

(Replace IP with your Droplet.) Should return `200 OK` with JSON.

### F.2 Test via Cloudflare

In browser:
- https://learnpuddle.com/health/
- https://learnpuddle.com/super-admin/login
- https://learnpuddle.com/signup

If you see "Host Error" or 5xx, see `docs/CLOUDFLARE_TROUBLESHOOTING.md`.

---

## Part G: Post-Deploy

### G.1 Create First School (Demo Tenant)

**Option 1 — Command Center:**
1. Go to https://learnpuddle.com/super-admin/login
2. Log in with superadmin email/password
3. **Schools** → **Add School**
4. Fill name, subdomain (e.g. `demo`), admin email, password
5. School URL: https://demo.learnpuddle.com/login

**Option 2 — Self-Service Signup:**
1. Go to https://learnpuddle.com/signup
2. Fill school name, admin email, password
3. Subdomain is auto-generated (e.g. `demo-school`)
4. Login URL: https://demo-school.learnpuddle.com/login

### G.2 Email (Resend)

To send real emails (password reset, verification):
1. Sign up at [Resend](https://resend.com)
2. Add domain `learnpuddle.com` and add DNS records in Cloudflare
3. Get API key and add to `.env` as `EMAIL_HOST_PASSWORD`
4. Restart: `docker compose -f docker-compose.prod.yml up -d web worker`

---

## Quick Reference: Commands on Droplet

**SSH in first:** `ssh root@YOUR_DROPLET_IP`

```bash
cd /opt/lms

# View logs
docker compose -f docker-compose.prod.yml logs -f

# Restart all
docker compose -f docker-compose.prod.yml restart

# Pull latest and redeploy
git pull
docker compose -f docker-compose.prod.yml build --no-cache web nginx
docker compose -f docker-compose.prod.yml run --rm web python manage.py migrate --noinput
docker compose -f docker-compose.prod.yml run --rm -u root web python manage.py collectstatic --noinput
docker compose -f docker-compose.prod.yml up -d --build
```

**Run full deploy from your Mac (one command):**
```bash
# If you have .env.deploy ready and SSH works:
./scripts/run-deploy-from-mac.sh 64.227.185.164
# (Replace IP with your Droplet)
```

**Run single commands from your Mac:**
```bash
ssh root@YOUR_IP "cd /opt/lms && docker compose -f docker-compose.prod.yml ps"
ssh root@YOUR_IP "cd /opt/lms && docker compose -f docker-compose.prod.yml logs -f web"
```

**Other CLIs:** `doctl` (DigitalOcean CLI) can manage Droplets but doesn't replace SSH for running app commands. SSH is the standard way.

---

## Checklist Summary

- [ ] Cloudflare: Remove duplicate A record (162.255.119.94)
- [ ] Cloudflare: A records for `@` and `*` → Droplet IP
- [ ] Cloudflare: SSL mode = **Flexible**
- [ ] Droplet: Docker + docker-compose installed
- [ ] Droplet: Ports 80, 443 open (ufw)
- [ ] Droplet: Repo cloned to `/opt/lms`
- [ ] Droplet: `.env` created and filled
- [ ] Droplet: Migrations run
- [ ] Droplet: Superadmin created
- [ ] Droplet: All services up
- [ ] Test: https://learnpuddle.com/health/ returns 200
- [ ] Test: https://learnpuddle.com/super-admin/login loads
