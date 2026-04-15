# LearnPuddle LMS - Digital Ocean Deployment Architecture

> Last updated: 2026-04-14
> Covers: Full production deployment on Digital Ocean for the LearnPuddle multi-tenant LMS.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Digital Ocean Services Mapping](#2-digital-ocean-services-mapping)
3. [Secrets Management](#3-secrets-management)
4. [Deployment Pipeline](#4-deployment-pipeline)
5. [DNS & Multi-Tenancy](#5-dns--multi-tenancy)
6. [Backup Strategy](#6-backup-strategy)
7. [Monitoring & Alerts](#7-monitoring--alerts)
8. [Scaling Path](#8-scaling-path)
9. [Cost Estimation](#9-cost-estimation)
10. [Migration Checklist](#10-migration-checklist)

---

## 1. Architecture Overview

### System Components

The LearnPuddle LMS consists of the following runtime services:

| Service | Technology | Role |
|---------|-----------|------|
| **Django API** | Gunicorn (WSGI) | REST API, auth, tenant resolution |
| **ASGI Server** | Daphne | WebSocket connections (real-time notifications) |
| **Celery Worker** | Celery | Video processing, emails, quiz generation, billing |
| **Celery Beat** | Celery Beat | Scheduled tasks (trial expiry, streaks, leaderboards, billing) |
| **Flower** | Flower | Celery monitoring dashboard |
| **OpenMAIC** | Next.js (Node 20) | AI classroom generation sidecar |
| **PostgreSQL** | pgvector/pg15 | Primary database (with vector extension) |
| **Redis** | Redis 7 | Cache (db 1), Celery broker (db 0), Channels layer (db 2) |
| **Nginx** | Nginx 1.25 | Reverse proxy, static/media serving, rate limiting |
| **React Frontend** | Vite/React 18 | SPA baked into Nginx image |

### Architecture Diagram

```
                         Internet
                            |
                     +------+------+
                     |  Cloudflare |  (DNS, SSL, DDoS, CDN cache)
                     |  *.learnpuddle.com
                     +------+------+
                            |
                            | (CF-Connecting-IP, X-Forwarded-Proto)
                            |
              +-------------+-------------+
              |     DO Droplet / App       |
              |         Platform           |
              |                            |
              |   +--------+  +---------+  |
              |   | Nginx  |  | Certbot |  |  (port 80/443)
              |   | + React|  | (if no  |  |
              |   |  SPA   |  |  CF SSL)|  |
              |   +---+----+  +---------+  |
              |       |                    |
              |   +---+--+----+---+        |
              |   |      |    |   |        |
              |  /api  /ws  /flower        |
              |   |      |    |            |
              | +-+--+ +-+-+ +-+----+      |
              | | Web| |ASGI| |Flower|     |
              | |8000| |8001| | 5555 |     |
              | +-+--+ +-+-+ +------+      |
              |   |      |                 |
              | +-+------+-+   +--------+  |
              | |  Redis   |   |OpenMAIC|  |
              | |  :6379   |   | :3000  |  |
              | +----------+   +--------+  |
              |                            |
              | +--------+ +------+        |
              | | Worker | | Beat |        |
              | |(Celery)| |(Celery)|      |
              | +--------+ +------+        |
              +------------+---------------+
                           |
                  +--------+--------+
                  |   DO Managed    |
                  |   PostgreSQL    |
                  |  (pgvector/15)  |
                  +-----------------+
                           |
                  +--------+--------+
                  |   DO Spaces     |
                  |  (S3-compat)    |
                  |  Media/Uploads  |
                  +-----------------+
```

### Data Flow Summary

1. **User request** arrives at Cloudflare, which terminates public SSL and proxies to the Droplet.
2. **Nginx** receives the request, resolves the Host header (e.g., `demo.learnpuddle.com`), and routes:
   - `/api/*` and `/media/*` to Django (Gunicorn on port 8000)
   - `/ws/*` to Daphne (ASGI on port 8001)
   - `/flower/*` to Flower (port 5555, IP-restricted)
   - Everything else to the React SPA (baked into the Nginx image)
3. **Django TenantMiddleware** extracts the subdomain, looks up the `Tenant` model, and sets `request.tenant`.
4. **Celery Worker** processes background tasks: video transcoding (ffmpeg), HLS segmentation, transcription (faster-whisper), quiz generation (OpenRouter/Ollama LLM), email sending, billing checks.
5. **Celery Beat** triggers scheduled tasks: trial expiry checks, streak processing, leaderboard computation, notification archival, ops probes.
6. **Redis** serves three roles: Celery broker (db 0), Django cache + rate limiting (db 1), Django Channels layer for WebSockets (db 2).
7. **PostgreSQL** (with pgvector) stores all application data, tenant-isolated via ForeignKey + TenantManager auto-filtering.
8. **DO Spaces** (S3-compatible) stores uploaded media files: videos, thumbnails, documents, certificates, tenant logos.

---

## 2. Digital Ocean Services Mapping

### Starter Tier (1-5 schools, <500 users)

| Component | DO Product | Spec | Monthly Cost |
|-----------|-----------|------|-------------|
| Django API + ASGI + Celery + Beat + Flower + Nginx + OpenMAIC | **Droplet** | Premium AMD, 4 vCPU / 8 GB RAM / 160 GB SSD | $48 |
| PostgreSQL | **Managed Database** | Basic plan, 1 vCPU / 1 GB / 10 GB disk (pg 15) | $15 |
| Redis | **Managed Database (Redis)** | 1 vCPU / 1 GB / no eviction | $15 |
| File Storage | **Spaces** | 250 GB included | $5 |
| Spaces CDN | **Spaces CDN** | Included with Spaces (first 1 TB free) | $0 |
| SSL | **Cloudflare** (free plan) | Wildcard SSL + DDoS protection | $0 |
| Domain DNS | **Cloudflare** (free plan) | Wildcard DNS for *.learnpuddle.com | $0 |
| Container Registry | **DO Container Registry** | Starter (500 MB, free) | $0 |
| **TOTAL** | | | **$83/mo** |

### Growth Tier (5-50 schools, <5000 users)

| Component | DO Product | Spec | Monthly Cost |
|-----------|-----------|------|-------------|
| Django API + ASGI + Nginx (x2) | **Droplet** (Primary) | Premium AMD, 4 vCPU / 8 GB / 160 GB | $48 |
| Celery Worker + Beat + Flower + OpenMAIC | **Droplet** (Worker) | Premium AMD, 4 vCPU / 8 GB / 160 GB | $48 |
| PostgreSQL | **Managed Database** | General Purpose, 2 vCPU / 4 GB / 60 GB + standby | $60 |
| Redis | **Managed Database (Redis)** | 2 vCPU / 2 GB | $30 |
| File Storage | **Spaces** | 250 GB + overage at $0.02/GB | $5 |
| Spaces CDN | **Spaces CDN** | 1 TB bandwidth included, $0.01/GB overage | $0 |
| SSL | **Cloudflare** (Pro plan for WAF) | Wildcard SSL + WAF + advanced DDoS | $20 |
| Domain DNS | **Cloudflare** (free) | Wildcard DNS | $0 |
| Container Registry | **DO Container Registry** | Basic (5 GB) | $5 |
| Load Balancer | **DO Load Balancer** | Small (if running 2 web Droplets) | $12 |
| Monitoring | **Sentry** | Team plan (50k events) | $26 |
| Email | **Resend** | Pro plan (50k emails/mo) | $20 |
| **TOTAL** | | | **$274/mo** |

### Why Droplet over App Platform

App Platform is simpler but has critical limitations for this stack:

1. **WebSockets**: App Platform does not natively support WebSocket connections (Daphne/ASGI). The LMS uses Django Channels for real-time notifications, which requires persistent WebSocket connections.
2. **ffmpeg**: The Celery video processing pipeline requires `ffmpeg` for HLS transcoding. App Platform's buildpacks do not include ffmpeg.
3. **Docker Compose**: The production stack runs 8+ containers with shared volumes and internal networking. A single Droplet with `docker compose` is the most straightforward path.
4. **Cost**: A single $48 Droplet replaces what would require multiple App Platform services at higher cost.

**Recommendation**: Use Droplets with `docker-compose.prod.yml` for both tiers. Graduate to Kubernetes (DO Kubernetes / DOKS) only when you need auto-scaling beyond 2-3 Droplets.

---

## 3. Secrets Management

### Secrets Inventory

The LMS requires the following secrets in production:

| Secret | Used By | Rotation Frequency |
|--------|---------|-------------------|
| `SECRET_KEY` | Django (sessions, CSRF, signing) | Yearly or on compromise |
| `JWT_SIGNING_KEY` | SimpleJWT (access/refresh tokens) | Yearly (must differ from SECRET_KEY) |
| `DB_PASSWORD` | PostgreSQL connection | Yearly or on compromise |
| `REDIS_PASSWORD` | Redis connection | Yearly or on compromise |
| `OPENROUTER_API_KEY` | LLM quiz generation | As needed |
| `ELEVENLABS_API_KEY` | Text-to-speech | As needed |
| `STRIPE_SECRET_KEY` | Payment processing | As needed |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook verification | As needed |
| `EMAIL_HOST_PASSWORD` | SMTP (Resend API key) | As needed |
| `FLOWER_PASSWORD` | Flower monitoring UI | Quarterly |
| `GOOGLE_OAUTH_CLIENT_SECRET` | Google SSO | As needed |
| `CAL_WEBHOOK_SECRET` | Cal.com webhook verification | As needed |
| `OPS_HARNESS_SHARED_SECRET` | Ops probe authentication | Quarterly |
| `SENTRY_DSN` | Error tracking | Rarely changes |

### WARNING: Current .env Contains Live Keys

The file `backend/.env` currently contains plaintext API keys for OpenRouter and ElevenLabs. These keys must be rotated before any production deployment, as they are committed or visible in the repository.

### Recommended Approach: DO Environment Variables + .env File on Droplet

For the Starter tier, the simplest secure approach:

1. **On the Droplet**, create `/opt/lms/.env` with all production secrets. This file is never committed to git.
2. **docker-compose.prod.yml** already reads from environment variables and `.env` file.
3. **File permissions**: `chmod 600 /opt/lms/.env` and `chown root:root /opt/lms/.env`.

```bash
# /opt/lms/.env (production secrets - never commit this file)
SECRET_KEY=<openssl rand -hex 50>
JWT_SIGNING_KEY=<openssl rand -hex 50>
DB_PASSWORD=<openssl rand -base64 32>
REDIS_PASSWORD=<openssl rand -base64 32>
FLOWER_PASSWORD=<openssl rand -base64 16>
PLATFORM_DOMAIN=learnpuddle.com
OPENROUTER_API_KEY=sk-or-v1-...
ELEVENLABS_API_KEY=sk_...
STRIPE_SECRET_KEY=sk_live_...
STRIPE_PUBLISHABLE_KEY=pk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
EMAIL_HOST=smtp.resend.com
EMAIL_HOST_USER=resend
EMAIL_HOST_PASSWORD=re_...
DEFAULT_FROM_EMAIL=noreply@learnpuddle.com
SENTRY_DSN=https://...@sentry.io/...
STORAGE_BACKEND=s3
STORAGE_ACCESS_KEY=DO00...
STORAGE_SECRET_KEY=...
STORAGE_BUCKET=learnpuddle-media
STORAGE_REGION=blr1
STORAGE_ENDPOINT=https://blr1.digitaloceanspaces.com
CDN_DOMAIN=learnpuddle-media.blr1.cdn.digitaloceanspaces.com
```

### Growth Tier: Doppler or DO Vault (if available)

For teams managing multiple environments (staging + production):

1. **Doppler** (recommended, free for small teams):
   - Install Doppler CLI on the Droplet.
   - Store all secrets in Doppler project with `staging` and `production` configs.
   - Run: `doppler run -- docker compose -f docker-compose.prod.yml up -d`
   - Doppler injects secrets as environment variables at runtime.
   - Provides audit logs, access control, and automatic rotation reminders.

2. **Alternative: 1Password CLI / HashiCorp Vault**:
   - Heavier setup, better for larger teams.
   - Overkill for <10 person operations.

### Key Generation Commands

```bash
# Django SECRET_KEY (100 hex chars)
openssl rand -hex 50

# JWT_SIGNING_KEY (must differ from SECRET_KEY)
openssl rand -hex 50

# Database and Redis passwords
openssl rand -base64 32

# Flower password
openssl rand -base64 16
```

---

## 4. Deployment Pipeline

### Strategy: GitHub Actions --> DO Container Registry --> SSH Deploy

The pipeline builds Docker images on GitHub Actions runners, pushes to DO Container Registry (DOCR), then SSHs to the Droplet to pull and restart.

### GitHub Actions Workflow

Create `.github/workflows/deploy-production.yml`:

```yaml
name: Deploy to Production

on:
  push:
    branches: [main]
  workflow_dispatch:

env:
  REGISTRY: registry.digitalocean.com
  REGISTRY_NAME: learnpuddle
  IMAGE_BACKEND: registry.digitalocean.com/learnpuddle/backend
  IMAGE_NGINX: registry.digitalocean.com/learnpuddle/nginx

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: pgvector/pgvector:pg15
        env:
          POSTGRES_DB: test_db
          POSTGRES_USER: test_user
          POSTGRES_PASSWORD: test_pass
        ports: ["5432:5432"]
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
      redis:
        image: redis:7-alpine
        ports: ["6379:6379"]
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: |
          cd backend
          pip install -r requirements.txt

      - name: Run tests
        env:
          SECRET_KEY: test-secret-key-not-for-production
          DB_NAME: test_db
          DB_USER: test_user
          DB_PASSWORD: test_pass
          DB_HOST: localhost
          DB_PORT: 5432
          REDIS_URL: redis://localhost:6379/1
          CELERY_BROKER_URL: redis://localhost:6379/0
          PLATFORM_DOMAIN: localhost
          DEBUG: "True"
        run: |
          cd backend
          python manage.py migrate --noinput
          pytest --tb=short -q

  build-and-push:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install doctl
        uses: digitalocean/action-doctl@v2
        with:
          token: ${{ secrets.DIGITALOCEAN_ACCESS_TOKEN }}

      - name: Log in to DO Container Registry
        run: doctl registry login --expiry-seconds 600

      - name: Build backend image
        run: |
          docker build \
            -t $IMAGE_BACKEND:${{ github.sha }} \
            -t $IMAGE_BACKEND:latest \
            -f backend/Dockerfile \
            backend/

      - name: Build nginx image (includes frontend)
        run: |
          docker build \
            -t $IMAGE_NGINX:${{ github.sha }} \
            -t $IMAGE_NGINX:latest \
            -f nginx/Dockerfile \
            --build-arg REACT_APP_API_URL=/api \
            --build-arg REACT_APP_PLATFORM_DOMAIN=${{ secrets.PLATFORM_DOMAIN }} \
            --build-arg REACT_APP_BOOK_DEMO_URL=${{ secrets.BOOK_DEMO_URL }} \
            .

      - name: Push images
        run: |
          docker push $IMAGE_BACKEND:${{ github.sha }}
          docker push $IMAGE_BACKEND:latest
          docker push $IMAGE_NGINX:${{ github.sha }}
          docker push $IMAGE_NGINX:latest

  deploy:
    needs: build-and-push
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Deploy to Droplet via SSH
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.DROPLET_IP }}
          username: deploy
          key: ${{ secrets.DEPLOY_SSH_KEY }}
          script: |
            set -e
            cd /opt/lms

            # Login to container registry
            doctl registry login --expiry-seconds 120

            # Pull latest images
            docker compose -f docker-compose.prod.yml pull web worker beat flower nginx

            # Run migrations before restarting
            docker compose -f docker-compose.prod.yml run --rm web \
              python manage.py migrate --noinput

            # Collect static files
            docker compose -f docker-compose.prod.yml run --rm -u root web \
              python manage.py collectstatic --noinput

            # Rolling restart (nginx last to minimize downtime)
            docker compose -f docker-compose.prod.yml up -d --no-deps beat
            docker compose -f docker-compose.prod.yml up -d --no-deps worker
            docker compose -f docker-compose.prod.yml up -d --no-deps flower
            docker compose -f docker-compose.prod.yml up -d --no-deps asgi
            docker compose -f docker-compose.prod.yml up -d --no-deps web
            sleep 10
            docker compose -f docker-compose.prod.yml up -d --no-deps nginx

            # Verify health
            sleep 15
            curl -sf http://localhost/health/live/ || exit 1
            echo "Deployment successful"

            # Cleanup old images
            docker image prune -f
```

### Staging Deployment

Create `.github/workflows/deploy-staging.yml` with the same structure but:
- Trigger on `develop` branch
- Use `docker-compose.staging.yml`
- Deploy to a separate staging Droplet
- Use staging secrets

### GitHub Secrets Required

| Secret | Description |
|--------|-------------|
| `DIGITALOCEAN_ACCESS_TOKEN` | DO API token (for doctl and container registry) |
| `DROPLET_IP` | Production Droplet IP address |
| `DEPLOY_SSH_KEY` | SSH private key for the `deploy` user on the Droplet |
| `PLATFORM_DOMAIN` | `learnpuddle.com` |
| `BOOK_DEMO_URL` | Cal.com booking URL (if applicable) |

### Droplet Setup for CI/CD

```bash
# On the Droplet, create a deploy user
sudo adduser deploy --disabled-password
sudo usermod -aG docker deploy

# Add the GitHub Actions public key
sudo mkdir -p /home/deploy/.ssh
sudo nano /home/deploy/.ssh/authorized_keys  # Paste public key
sudo chmod 700 /home/deploy/.ssh
sudo chmod 600 /home/deploy/.ssh/authorized_keys
sudo chown -R deploy:deploy /home/deploy/.ssh

# Install doctl on the Droplet
snap install doctl
doctl auth init  # Authenticate with DO API token

# Clone repo and set up
sudo mkdir -p /opt/lms
sudo chown deploy:deploy /opt/lms
su - deploy
cd /opt/lms
git clone https://github.com/thebrainpuddle-dev/learnpuddle-lms.git .
```

### Modifying docker-compose.prod.yml for DOCR Images

When using pre-built images from the container registry instead of building on the Droplet, override the `build` directives with `image` in a `docker-compose.override.yml` on the Droplet:

```yaml
# /opt/lms/docker-compose.override.yml
services:
  web:
    image: registry.digitalocean.com/learnpuddle/backend:latest
    build: !reset null
  asgi:
    image: registry.digitalocean.com/learnpuddle/backend:latest
    build: !reset null
  worker:
    image: registry.digitalocean.com/learnpuddle/backend:latest
    build: !reset null
  beat:
    image: registry.digitalocean.com/learnpuddle/backend:latest
    build: !reset null
  flower:
    image: registry.digitalocean.com/learnpuddle/backend:latest
    build: !reset null
  nginx:
    image: registry.digitalocean.com/learnpuddle/nginx:latest
    build: !reset null
```

---

## 5. DNS & Multi-Tenancy

### How Multi-Tenancy Works

Each school gets a subdomain: `schoolname.learnpuddle.com`. The Django `TenantMiddleware` extracts the subdomain from the `Host` header and resolves the corresponding `Tenant` record. All queries are then automatically filtered by tenant via `TenantManager`.

### Wildcard DNS Setup with Cloudflare

Cloudflare is the recommended DNS provider because it offers:
- Free wildcard SSL certificates (covers `*.learnpuddle.com`)
- Free DDoS protection and rate limiting
- CDN caching for static assets
- Origin certificates for server-side SSL

#### Step-by-step Cloudflare Configuration

1. **Add domain to Cloudflare** (free plan):
   - Sign up at cloudflare.com
   - Add `learnpuddle.com`
   - Update nameservers at your registrar to Cloudflare's nameservers

2. **Create DNS records**:

   | Type | Name | Content | Proxy | TTL |
   |------|------|---------|-------|-----|
   | A | `@` | `<DROPLET_IP>` | Proxied (orange cloud) | Auto |
   | A | `*` | `<DROPLET_IP>` | Proxied (orange cloud) | Auto |
   | CNAME | `www` | `learnpuddle.com` | Proxied | Auto |

   The wildcard `*` record catches all subdomains (e.g., `demo.learnpuddle.com`, `school1.learnpuddle.com`).

3. **SSL/TLS settings** (Cloudflare dashboard > SSL/TLS):
   - Mode: **Full (Strict)**
   - Edge Certificates: Universal SSL (auto, covers `*.learnpuddle.com`)
   - Minimum TLS Version: 1.2
   - Always Use HTTPS: On
   - Automatic HTTPS Rewrites: On

4. **Generate Cloudflare Origin Certificate** (Cloudflare dashboard > SSL/TLS > Origin Server):
   - Click "Create Certificate"
   - Private key type: RSA (2048)
   - Hostnames: `*.learnpuddle.com`, `learnpuddle.com`
   - Validity: 15 years
   - Download `origin.pem` (certificate) and `origin-key.pem` (private key)
   - Place on the Droplet:
     ```bash
     sudo mkdir -p /opt/lms/nginx/ssl
     sudo nano /opt/lms/nginx/ssl/origin.pem      # Paste certificate
     sudo nano /opt/lms/nginx/ssl/origin-key.pem   # Paste private key
     sudo chmod 600 /opt/lms/nginx/ssl/origin-key.pem
     ```

5. **Cloudflare Page Rules** (optional performance tuning):

   | URL Pattern | Setting |
   |------------|---------|
   | `*learnpuddle.com/static/*` | Cache Level: Cache Everything, Edge TTL: 1 month |
   | `*learnpuddle.com/api/*` | Cache Level: Bypass |
   | `*learnpuddle.com/ws/*` | Disable Security (WebSocket pass-through) |

6. **Cloudflare Firewall rules** (Growth tier):
   - Block requests not from expected countries (if applicable)
   - Rate limit `/api/users/auth/login/` to 5 per minute per IP

### Cloudflare vs DO Load Balancer

| Feature | Cloudflare (Free) | DO Load Balancer ($12/mo) |
|---------|-------------------|---------------------------|
| SSL Termination | Yes (edge, wildcard) | Yes (Let's Encrypt, no wildcard) |
| DDoS Protection | Yes (L3/L4/L7) | Basic (L4 only) |
| CDN / Cache | Yes (global edge) | No |
| WebSocket Support | Yes | Yes |
| Wildcard SSL | Yes (free) | No (need cert per subdomain) |
| Cost | $0 | $12/mo |

**Recommendation**: Use Cloudflare for DNS and SSL. Skip the DO Load Balancer for the Starter tier. For the Growth tier, add a DO Load Balancer only if running multiple web Droplets, and keep Cloudflare in front of it.

### How Nginx Handles Wildcard Subdomains

The nginx config uses `server_name _;` (catch-all), which accepts any hostname. Django's `TenantMiddleware` does the actual tenant resolution:

```
Request: https://demo.learnpuddle.com/api/courses/
  1. Cloudflare resolves *.learnpuddle.com to Droplet IP
  2. Cloudflare terminates SSL, proxies to Droplet port 80 (or 443 with origin cert)
  3. Nginx catches all hostnames, forwards to Django
  4. TenantMiddleware extracts "demo" from Host header
  5. Looks up Tenant(subdomain="demo") in database
  6. Sets request.tenant, filters all queries by this tenant
```

No nginx or Cloudflare configuration change is needed when a new school signs up. The tenant is created in the database, and the wildcard DNS + wildcard SSL handle it automatically.

---

## 6. Backup Strategy

### Database Backups

#### Managed Database (Automatic)

DO Managed Databases include automatic daily backups with 7-day retention (free, included in the plan).

- **Daily backups**: Automatic, taken at a consistent time
- **Point-in-time recovery**: Available for the last 7 days (General Purpose plans)
- **Restore**: Create a new database cluster from any backup point via DO dashboard
- **Failover**: General Purpose plans include automatic failover to a standby node

#### Additional Database Backups (Recommended)

For critical data, supplement with manual backups:

```bash
# Weekly full backup to Spaces (run via cron on Droplet)
#!/bin/bash
# /opt/lms/scripts/backup-db.sh
set -euo pipefail

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="/tmp/learnpuddle_backup_${TIMESTAMP}.sql.gz"
SPACES_BUCKET="learnpuddle-backups"
SPACES_PATH="db/${TIMESTAMP}.sql.gz"

# Dump from managed database (connection string from DO dashboard)
PGPASSWORD="${DB_PASSWORD}" pg_dump \
  -h "${DB_HOST}" \
  -p "${DB_PORT}" \
  -U "${DB_USER}" \
  -d "${DB_NAME}" \
  --no-owner \
  --no-acl \
  --format=custom \
  | gzip > "${BACKUP_FILE}"

# Upload to Spaces
s3cmd put "${BACKUP_FILE}" "s3://${SPACES_BUCKET}/${SPACES_PATH}" \
  --host=blr1.digitaloceanspaces.com \
  --host-bucket="%(bucket)s.blr1.digitaloceanspaces.com"

# Cleanup local file
rm -f "${BACKUP_FILE}"

# Delete backups older than 90 days from Spaces
s3cmd ls "s3://${SPACES_BUCKET}/db/" | \
  awk -v cutoff="$(date -d '90 days ago' +%Y-%m-%d)" '$1 < cutoff {print $4}' | \
  xargs -r s3cmd del

echo "[$(date)] Database backup completed: ${SPACES_PATH}"
```

Add to crontab:
```bash
# Weekly database backup - Sunday 03:00 UTC
0 3 * * 0 /opt/lms/scripts/backup-db.sh >> /var/log/lms-backup.log 2>&1
```

### Media File Backups (DO Spaces)

DO Spaces includes built-in redundancy (3x replication within the datacenter). For disaster recovery:

1. **Cross-region replication**: Create a second Spaces bucket in a different region and use `s3cmd sync` or `rclone` to mirror:
   ```bash
   # Weekly media mirror to secondary region
   rclone sync \
     spaces-blr1:learnpuddle-media \
     spaces-sfo3:learnpuddle-media-backup \
     --transfers 8
   ```

2. **Versioning**: Enable Spaces versioning to protect against accidental deletions:
   ```bash
   s3cmd setversioning --enable s3://learnpuddle-media
   ```

### Redis Backup

Redis is used as a cache and message broker. Data loss is acceptable (cache rebuilds automatically, and in-flight Celery tasks will retry). Managed Redis includes persistence if configured.

For the Growth tier with Managed Redis, DO includes automatic failover and persistence.

### Backup Verification

Monthly: restore a database backup to a temporary managed database and verify data integrity:

```bash
# Create temporary cluster from backup, verify, then destroy
doctl databases create test-restore \
  --engine pg \
  --version 15 \
  --size db-s-1vcpu-1gb \
  --restore-from <backup-id>

# Verify
PGPASSWORD=... psql -h <temp-host> -U doadmin -d learnpuddle_db \
  -c "SELECT count(*) FROM tenants_tenant;"

# Destroy
doctl databases delete <temp-cluster-id> --force
```

---

## 7. Monitoring & Alerts

### Layer 1: DO Built-in Monitoring (Free)

Digital Ocean provides agent-based monitoring for Droplets:

```bash
# Install DO monitoring agent on Droplet
curl -sSL https://repos.insights.digitalocean.com/install.sh | sudo bash
```

Configure alerts in DO dashboard (Settings > Monitoring > Alerts):

| Metric | Threshold | Action |
|--------|-----------|--------|
| CPU utilization | > 80% for 5 min | Email + Slack |
| Memory utilization | > 85% for 5 min | Email + Slack |
| Disk utilization | > 80% | Email + Slack |
| Disk I/O (read) | > 100 MB/s sustained | Email |
| Managed DB CPU | > 80% for 5 min | Email + Slack |
| Managed DB disk | > 80% | Email + Slack |
| Managed DB connections | > 80% of max | Email |

### Layer 2: Application Monitoring (Sentry)

The LMS already has Sentry integration built in. Enable it by setting `SENTRY_DSN`:

```bash
# In .env
SENTRY_DSN=https://<key>@o<org>.ingest.sentry.io/<project>
SENTRY_ENVIRONMENT=production
SENTRY_TRACES_RATE=0.1  # Sample 10% of requests for performance monitoring
```

Sentry captures:
- Unhandled exceptions in Django views and Celery tasks
- Slow database queries (via performance monitoring)
- Frontend JavaScript errors (add Sentry SDK to React app)

Configure Sentry alerts:
- **New issue**: Notify on Slack immediately
- **Issue frequency**: Alert if >10 events/hour for the same error
- **P75 response time**: Alert if >2 seconds for API endpoints

### Layer 3: Health Checks

The LMS exposes three health endpoints:

| Endpoint | Purpose | Checks |
|----------|---------|--------|
| `/health/live/` | Liveness probe | Process is running |
| `/health/ready/` | Readiness probe | DB + Redis connected |
| `/health/` | Full health | DB + Redis + disk space |

#### External Uptime Monitoring

Use a free uptime service (UptimeRobot, Better Uptime, or Cloudflare Health Checks):

| Check | URL | Interval | Alert |
|-------|-----|----------|-------|
| API Health | `https://learnpuddle.com/health/ready/` | 60s | Email + Slack |
| Frontend | `https://learnpuddle.com/` | 60s | Email + Slack |
| WebSocket | `wss://learnpuddle.com/ws/` (connect test) | 300s | Email |
| SSL Expiry | `https://learnpuddle.com` (cert check) | Daily | Email (30 days before expiry) |

### Layer 4: Prometheus Metrics (Growth Tier)

The LMS exposes Prometheus metrics at `/metrics` (IP-restricted in nginx). For the Growth tier:

1. Deploy a Prometheus + Grafana stack on the monitoring Droplet (or use DO Managed Monitoring if available).
2. Scrape `/metrics` from the web container.
3. Key metrics to dashboard:
   - `django_http_requests_total` (by method, status code)
   - `django_http_request_duration_seconds` (P50, P95, P99)
   - `django_db_query_duration_seconds`
   - `celery_worker_tasks_active`
   - `process_resident_memory_bytes`

### Layer 5: Log Aggregation (Growth Tier)

Docker logs are configured with `json-file` driver (10 MB max, 3 files rotation). For centralized logging:

1. **Option A**: Papertrail (free tier, 100 MB/month) -- add remote syslog to Docker logging driver.
2. **Option B**: DO Managed Logs (if available) or Loki + Grafana on a monitoring Droplet.
3. The LMS produces structured JSON logs in production (`LOG_JSON=True`), making them easy to parse and search.

### Alert Runbook Summary

| Alert | Severity | First Response |
|-------|----------|---------------|
| Health check failing | P1 | Check `docker compose ps`, restart unhealthy containers |
| CPU > 80% sustained | P2 | Check Celery queue depth, consider scaling worker |
| Disk > 80% | P2 | Clean Docker images (`docker system prune`), check log rotation |
| 5xx error spike | P1 | Check Sentry for root cause, check DB connections |
| DB connections > 80% | P2 | Check for connection leaks, increase `DB_CONN_MAX_AGE` |
| SSL cert expiry < 30d | P3 | Cloudflare origin certs are 15 years; check if using Let's Encrypt instead |
| Celery queue backing up | P2 | Check worker health, consider adding concurrency |

---

## 8. Scaling Path

### Phase 1: Vertical Scaling (Simplest)

When the Starter tier Droplet hits resource limits:

| Bottleneck | Action | New Spec | Cost Delta |
|-----------|--------|----------|------------|
| CPU/Memory | Resize Droplet | 8 vCPU / 16 GB | +$48/mo |
| Database | Resize Managed DB | 2 vCPU / 4 GB | +$45/mo |
| Redis | Resize Managed Redis | 2 vCPU / 2 GB | +$15/mo |

Droplet resizing takes ~1 minute of downtime. Database resizing is zero-downtime with Managed DB.

### Phase 2: Service Separation

Split services across multiple Droplets:

```
Droplet 1 (Web): Nginx + Django API + ASGI + React SPA
Droplet 2 (Workers): Celery Worker + Beat + Flower + OpenMAIC
```

Benefits:
- Video processing (CPU-heavy ffmpeg) no longer competes with API requests
- Worker Droplet can be a CPU-optimized instance
- Independent scaling of web and worker tiers

### Phase 3: Horizontal Scaling

Add multiple web Droplets behind a DO Load Balancer:

```
Cloudflare --> DO Load Balancer --> Droplet 1 (web)
                                --> Droplet 2 (web)
                                --> Droplet 3 (web)
```

Requirements for horizontal scaling:
- **Sticky sessions** for WebSocket connections (or use Redis adapter for Socket.IO)
- **Shared media volume** replaced by DO Spaces (already configured with `STORAGE_BACKEND=s3`)
- **Static files** served from Spaces CDN (already supported via `CDN_DOMAIN`)
- **Session storage** already in Redis (no filesystem dependency)
- **Celery** already uses Redis broker (workers can run on any node)

### Phase 4: CDN for Static Assets

Cloudflare caching (already in place) handles most CDN needs:

1. **React SPA assets** (`/static/js/`, `/static/css/`): Cached at Cloudflare edge with 1-year TTL (already set via nginx `Cache-Control: public, immutable`).
2. **Media files**: Served via DO Spaces CDN (`learnpuddle-media.blr1.cdn.digitaloceanspaces.com`). Set `CDN_DOMAIN` in env to enable.
3. **API responses**: Not cached (Cloudflare page rule: `/api/*` bypass cache).

### Phase 5: Database Read Replicas

When database becomes the bottleneck (Growth tier, >5000 users):

1. Add a read replica to the Managed PostgreSQL cluster ($30-60/mo).
2. Configure Django database router to send reads to the replica:

```python
# config/db_router.py
class ReadReplicaRouter:
    def db_for_read(self, model, **hints):
        return 'replica'
    def db_for_write(self, model, **hints):
        return 'default'
```

3. Update `DATABASES` in settings to include the replica:

```python
DATABASES = {
    'default': { ... },  # Primary (writes)
    'replica': { ... },  # Read replica
}
```

### Phase 6: Kubernetes (DOKS)

When you need auto-scaling, zero-downtime deployments, and multi-region:

- Migrate from docker-compose to Kubernetes manifests (Helm charts)
- Use DO Kubernetes (DOKS) with node auto-scaling
- Use Horizontal Pod Autoscaler for web and worker pods
- Estimated cost: $100-300/mo for the DOKS cluster + node pools

This is not needed until you are serving 50+ schools or 10,000+ concurrent users.

---

## 9. Cost Estimation

### Starter Tier: 1-5 Schools, <500 Users

| Service | Product | Spec | Monthly |
|---------|---------|------|---------|
| Compute | Droplet (Premium AMD) | 4 vCPU / 8 GB / 160 GB SSD | $48.00 |
| Database | Managed PostgreSQL | Basic, 1 vCPU / 1 GB / 10 GB | $15.00 |
| Cache/Broker | Managed Redis | 1 vCPU / 1 GB | $15.00 |
| Object Storage | Spaces | 250 GB storage, 1 TB bandwidth | $5.00 |
| CDN | Spaces CDN | Included with Spaces | $0.00 |
| DNS + SSL | Cloudflare (free) | Wildcard DNS + SSL + DDoS | $0.00 |
| Container Registry | DOCR Starter | 500 MB (free) | $0.00 |
| Email | Resend (free) | 3,000 emails/month | $0.00 |
| Monitoring | Sentry (free) | 5k events/month | $0.00 |
| Uptime | UptimeRobot (free) | 50 monitors | $0.00 |
| **TOTAL** | | | **$83.00/mo** |

### Growth Tier: 5-50 Schools, <5000 Users

| Service | Product | Spec | Monthly |
|---------|---------|------|---------|
| Web Compute | Droplet (Premium AMD) | 4 vCPU / 8 GB / 160 GB | $48.00 |
| Worker Compute | Droplet (Premium AMD) | 4 vCPU / 8 GB / 160 GB | $48.00 |
| Database | Managed PostgreSQL | GP, 2 vCPU / 4 GB / 60 GB + standby | $60.00 |
| Cache/Broker | Managed Redis | 2 vCPU / 2 GB | $30.00 |
| Object Storage | Spaces | 250 GB + overage | $5.00 |
| CDN | Spaces CDN | Included | $0.00 |
| DNS + SSL | Cloudflare Pro | WAF + advanced DDoS | $20.00 |
| Container Registry | DOCR Basic | 5 GB | $5.00 |
| Load Balancer | DO LB (Small) | 2 Droplets | $12.00 |
| Email | Resend Pro | 50k emails/month | $20.00 |
| Monitoring | Sentry Team | 50k events/month | $26.00 |
| Uptime | Better Uptime | Pro plan | $20.00 |
| **TOTAL** | | | **$294.00/mo** |

### Variable Costs

| Item | Unit Price | Notes |
|------|-----------|-------|
| Spaces overage (storage) | $0.02/GB/mo | Beyond 250 GB |
| Spaces overage (bandwidth) | $0.01/GB | Beyond 1 TB/mo |
| Managed DB backup storage | Free | 7-day retention included |
| Droplet bandwidth | Free | First 4 TB included per Droplet |
| OpenRouter API | Variable | Free tier models available; paid models ~$0.001-0.01/query |
| ElevenLabs TTS | $5-22/mo | Depends on character usage |
| Stripe processing | 2.9% + $0.30 | Per transaction |

### Cost Optimization Tips

1. **Reserved Droplets**: Commit to 1-year or 3-year reserved pricing for 20-35% savings.
2. **Free tier services**: Use Resend free (3k emails), Sentry free (5k events), UptimeRobot free (50 monitors).
3. **Cloudflare caching**: Reduces Droplet bandwidth and CPU load significantly.
4. **Right-size the database**: Start with Basic ($15), upgrade only when you see connection or query bottlenecks.
5. **Spaces CDN**: Already included; use it for all media delivery to reduce origin load.

---

## 10. Migration Checklist

### Prerequisites

- [ ] Digital Ocean account created and verified
- [ ] Cloudflare account created
- [ ] Domain `learnpuddle.com` registered
- [ ] GitHub repository access configured
- [ ] All production secrets generated (see Section 3)
- [ ] Current `.env` API keys rotated (OpenRouter and ElevenLabs keys are exposed)

### Step 1: Create DO Infrastructure

```bash
# Install doctl CLI
brew install doctl  # macOS
doctl auth init

# 1a. Create a VPC (private networking)
doctl vpcs create \
  --name learnpuddle-vpc \
  --region blr1 \
  --ip-range 10.10.10.0/24

# 1b. Create Managed PostgreSQL
doctl databases create learnpuddle-db \
  --engine pg \
  --version 15 \
  --size db-s-1vcpu-1gb \
  --region blr1 \
  --num-nodes 1 \
  --private-network-uuid <vpc-uuid>

# 1c. Create Managed Redis
doctl databases create learnpuddle-redis \
  --engine redis \
  --version 7 \
  --size db-s-1vcpu-1gb \
  --region blr1 \
  --num-nodes 1 \
  --private-network-uuid <vpc-uuid>

# 1d. Create Spaces bucket
doctl spaces create learnpuddle-media \
  --region blr1

# 1e. Create Spaces access keys (for Django S3 storage)
doctl spaces keys create --name learnpuddle-app

# 1f. Create Container Registry
doctl registry create learnpuddle --region blr1

# 1g. Create Droplet
doctl compute droplet create learnpuddle-prod \
  --image docker-20-04 \
  --size s-4vcpu-8gb-amd \
  --region blr1 \
  --vpc-uuid <vpc-uuid> \
  --ssh-keys <ssh-key-fingerprint> \
  --enable-monitoring \
  --tag-names production,learnpuddle
```

### Step 2: Configure the Droplet

```bash
# SSH into the Droplet
ssh root@<DROPLET_IP>

# 2a. System updates
apt update && apt upgrade -y

# 2b. Install Docker and Docker Compose (if not using Docker image)
# The docker-20-04 image comes with Docker pre-installed
docker --version
docker compose version

# 2c. Install doctl and s3cmd
snap install doctl
apt install -y s3cmd

# 2d. Configure firewall
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable

# 2e. Create deploy user
adduser deploy --disabled-password
usermod -aG docker deploy

# 2f. Set up SSH key for deploy user
mkdir -p /home/deploy/.ssh
# Paste your public key into authorized_keys
nano /home/deploy/.ssh/authorized_keys
chmod 700 /home/deploy/.ssh
chmod 600 /home/deploy/.ssh/authorized_keys
chown -R deploy:deploy /home/deploy/.ssh

# 2g. Create application directory
mkdir -p /opt/lms
chown deploy:deploy /opt/lms
```

### Step 3: Configure Managed Database

```bash
# 3a. Get connection details
doctl databases connection learnpuddle-db --format Host,Port,User,Password,Database

# 3b. Restrict access to VPC only (trusted sources)
doctl databases firewalls append learnpuddle-db \
  --rule droplet:<droplet-id>

# 3c. Create the application database
# Connect to the managed DB
PGPASSWORD=<admin-password> psql -h <db-host> -p <db-port> -U doadmin -d defaultdb

# In psql:
CREATE DATABASE learnpuddle_db;
CREATE USER learnpuddle WITH PASSWORD '<strong-password>';
GRANT ALL PRIVILEGES ON DATABASE learnpuddle_db TO learnpuddle;
ALTER DATABASE learnpuddle_db OWNER TO learnpuddle;
\q

# 3d. Enable pgvector extension
PGPASSWORD=<admin-password> psql -h <db-host> -p <db-port> -U doadmin -d learnpuddle_db
CREATE EXTENSION IF NOT EXISTS vector;
\q
```

### Step 4: Configure Managed Redis

```bash
# 4a. Get connection details
doctl databases connection learnpuddle-redis --format Host,Port,Password,URI

# 4b. Restrict access to VPC
doctl databases firewalls append learnpuddle-redis \
  --rule droplet:<droplet-id>

# Note the Redis URI format for .env:
# redis://<user>:<password>@<host>:<port>
```

### Step 5: Configure DO Spaces

```bash
# 5a. Enable CDN on the Spaces bucket
# Do this via DO Dashboard: Spaces > learnpuddle-media > Settings > Enable CDN

# 5b. Configure CORS for the Spaces bucket (via DO Dashboard or API)
# Allow GET from *.learnpuddle.com

# 5c. Note the endpoints for .env:
# STORAGE_ENDPOINT=https://blr1.digitaloceanspaces.com
# STORAGE_BUCKET=learnpuddle-media
# CDN_DOMAIN=learnpuddle-media.blr1.cdn.digitaloceanspaces.com
```

### Step 6: Deploy Application

```bash
# Switch to deploy user
su - deploy
cd /opt/lms

# 6a. Clone repository
git clone https://github.com/thebrainpuddle-dev/learnpuddle-lms.git .

# 6b. Create production .env file
cat > .env << 'ENVEOF'
# --- Core ---
SECRET_KEY=<generated-secret>
DEBUG=False
PLATFORM_DOMAIN=learnpuddle.com
PLATFORM_NAME=LearnPuddle

# --- Database (from Step 3) ---
DB_NAME=learnpuddle_db
DB_USER=learnpuddle
DB_PASSWORD=<from-step-3>
DB_HOST=<managed-db-private-host>
DB_PORT=25060

# --- Redis (from Step 4) ---
REDIS_PASSWORD=<from-step-4>
# Note: docker-compose.prod.yml constructs REDIS_URL and CELERY_BROKER_URL

# --- Storage (from Step 5) ---
STORAGE_BACKEND=s3
STORAGE_ACCESS_KEY=<spaces-key>
STORAGE_SECRET_KEY=<spaces-secret>
STORAGE_BUCKET=learnpuddle-media
STORAGE_REGION=blr1
STORAGE_ENDPOINT=https://blr1.digitaloceanspaces.com
CDN_DOMAIN=learnpuddle-media.blr1.cdn.digitaloceanspaces.com

# --- JWT ---
JWT_SIGNING_KEY=<generated-different-from-secret-key>

# --- Email ---
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.resend.com
EMAIL_PORT=465
EMAIL_USE_TLS=False
EMAIL_USE_SSL=True
EMAIL_HOST_USER=resend
EMAIL_HOST_PASSWORD=re_<your-resend-api-key>
DEFAULT_FROM_EMAIL=noreply@learnpuddle.com

# --- Stripe ---
STRIPE_SECRET_KEY=sk_live_...
STRIPE_PUBLISHABLE_KEY=pk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...

# --- LLM ---
OPENROUTER_API_KEY=sk-or-v1-<new-rotated-key>

# --- TTS ---
ELEVENLABS_API_KEY=sk_<new-rotated-key>

# --- Monitoring ---
SENTRY_DSN=https://...@sentry.io/...
SENTRY_ENVIRONMENT=production

# --- Flower ---
FLOWER_USER=admin
FLOWER_PASSWORD=<generated-password>
ENVEOF

chmod 600 .env

# 6c. Set up SSL certificates (Cloudflare Origin Certificate)
mkdir -p nginx/ssl
# Paste your Cloudflare origin certificate and key
nano nginx/ssl/origin.pem
nano nginx/ssl/origin-key.pem
chmod 600 nginx/ssl/origin-key.pem
```

### Step 7: Modify docker-compose.prod.yml for Managed Services

Since you are using Managed PostgreSQL and Managed Redis instead of self-hosted containers, you need to update the compose file. Create an override:

```bash
# 7a. The docker-compose.prod.yml references internal 'db' and 'redis' services.
# For managed services, remove those containers and point env vars to managed hosts.

cat > docker-compose.override.yml << 'OVERRIDE'
# Override for DO Managed Database and Redis
# Removes self-hosted db/redis, points to managed services
services:
  db:
    profiles: ["disabled"]  # Do not start self-hosted PostgreSQL
  redis:
    profiles: ["disabled"]  # Do not start self-hosted Redis

  web:
    depends_on: []  # Remove dependency on local db/redis
    environment:
      - DB_HOST=${DB_HOST}
      - DB_PORT=${DB_PORT:-25060}
      - REDIS_URL=rediss://:${REDIS_PASSWORD}@${REDIS_HOST}:${REDIS_PORT:-25061}/1
      - CELERY_BROKER_URL=rediss://:${REDIS_PASSWORD}@${REDIS_HOST}:${REDIS_PORT:-25061}/0

  asgi:
    depends_on:
      web:
        condition: service_healthy
    environment:
      - DB_HOST=${DB_HOST}
      - DB_PORT=${DB_PORT:-25060}
      - REDIS_URL=rediss://:${REDIS_PASSWORD}@${REDIS_HOST}:${REDIS_PORT:-25061}/1
      - CELERY_BROKER_URL=rediss://:${REDIS_PASSWORD}@${REDIS_HOST}:${REDIS_PORT:-25061}/0

  worker:
    depends_on:
      web:
        condition: service_healthy
    environment:
      - DB_HOST=${DB_HOST}
      - DB_PORT=${DB_PORT:-25060}
      - REDIS_URL=rediss://:${REDIS_PASSWORD}@${REDIS_HOST}:${REDIS_PORT:-25061}/1
      - CELERY_BROKER_URL=rediss://:${REDIS_PASSWORD}@${REDIS_HOST}:${REDIS_PORT:-25061}/0

  beat:
    depends_on:
      web:
        condition: service_healthy
    environment:
      - DB_HOST=${DB_HOST}
      - DB_PORT=${DB_PORT:-25060}
      - REDIS_URL=rediss://:${REDIS_PASSWORD}@${REDIS_HOST}:${REDIS_PORT:-25061}/1
      - CELERY_BROKER_URL=rediss://:${REDIS_PASSWORD}@${REDIS_HOST}:${REDIS_PORT:-25061}/0

  flower:
    depends_on:
      web:
        condition: service_healthy
    environment:
      - DB_HOST=${DB_HOST}
      - DB_PORT=${DB_PORT:-25060}
      - REDIS_URL=rediss://:${REDIS_PASSWORD}@${REDIS_HOST}:${REDIS_PORT:-25061}/1
      - CELERY_BROKER_URL=rediss://:${REDIS_PASSWORD}@${REDIS_HOST}:${REDIS_PORT:-25061}/0
OVERRIDE

# 7b. Add managed service connection details to .env
cat >> .env << 'MANAGED'

# --- Managed Service Hosts ---
DB_HOST=<private-hostname-from-do-dashboard>
DB_PORT=25060
REDIS_HOST=<private-hostname-from-do-dashboard>
REDIS_PORT=25061
MANAGED
```

**Important**: Managed Redis on DO uses TLS (`rediss://` with double-s). The port is typically 25061.

### Step 8: Build, Push, and Start

```bash
# 8a. Log in to container registry
doctl registry login

# 8b. Build images
docker compose -f docker-compose.prod.yml build web nginx openmaic

# 8c. Push to registry (optional, for CI/CD later)
docker tag lms-web registry.digitalocean.com/learnpuddle/backend:latest
docker tag lms-nginx registry.digitalocean.com/learnpuddle/nginx:latest
docker push registry.digitalocean.com/learnpuddle/backend:latest
docker push registry.digitalocean.com/learnpuddle/nginx:latest

# 8d. Start all services
docker compose -f docker-compose.prod.yml up -d

# 8e. Watch logs for startup issues
docker compose -f docker-compose.prod.yml logs -f --tail=100
```

### Step 9: Run Migrations and Create Admin

```bash
# 9a. Run database migrations
docker compose -f docker-compose.prod.yml exec web python manage.py migrate --noinput

# 9b. Collect static files
docker compose -f docker-compose.prod.yml exec -u root web python manage.py collectstatic --noinput

# 9c. Create superadmin user
docker compose -f docker-compose.prod.yml exec web python manage.py createsuperuser

# 9d. Create demo tenant (optional, for testing)
docker compose -f docker-compose.prod.yml exec web python manage.py create_demo_tenant
```

### Step 10: Configure DNS (Cloudflare)

```bash
# 10a. In Cloudflare dashboard:
# - Add domain learnpuddle.com
# - Update nameservers at registrar

# 10b. Add DNS records:
# A    @     <DROPLET_IP>    Proxied
# A    *     <DROPLET_IP>    Proxied
# CNAME www  learnpuddle.com Proxied

# 10c. SSL/TLS settings:
# - Mode: Full (Strict)
# - Generate Origin Certificate (see Section 5 for details)

# 10d. Page Rules:
# - *learnpuddle.com/static/* -> Cache Everything, Edge TTL 1 month
# - *learnpuddle.com/api/* -> Cache Level: Bypass
```

### Step 11: Verify Deployment

```bash
# 11a. Health checks
curl -s https://learnpuddle.com/health/live/
# Expected: {"status": "ok"}

curl -s https://learnpuddle.com/health/ready/
# Expected: {"status": "ok", "database": "ok", "redis": "ok"}

# 11b. Test tenant resolution
curl -s -H "Host: demo.learnpuddle.com" https://learnpuddle.com/api/tenants/theme/

# 11c. Test frontend
curl -s https://learnpuddle.com/ | head -20
# Should return React SPA HTML

# 11d. Check all containers are healthy
docker compose -f docker-compose.prod.yml ps

# 11e. Verify Celery workers
docker compose -f docker-compose.prod.yml exec web celery -A config inspect active_queues

# 11f. Test WebSocket (using wscat)
wscat -c wss://learnpuddle.com/ws/notifications/

# 11g. Verify Spaces connectivity
docker compose -f docker-compose.prod.yml exec web python manage.py shell -c "
from django.core.files.storage import default_storage
print('Storage backend:', type(default_storage).__name__)
print('Bucket:', getattr(default_storage, 'bucket_name', 'N/A'))
"

# 11h. Check Flower dashboard (from within private network or SSH tunnel)
ssh -L 5555:localhost:5555 deploy@<DROPLET_IP>
# Then open http://localhost:5555/flower/ in browser
```

### Step 12: Post-Deployment

- [ ] Set up GitHub Actions CI/CD (see Section 4)
- [ ] Configure Sentry project and alert rules
- [ ] Set up external uptime monitoring
- [ ] Configure database backup cron job (see Section 6)
- [ ] Enable Spaces versioning for media files
- [ ] Set up Cloudflare Page Rules for caching
- [ ] Configure Stripe webhook endpoint: `https://learnpuddle.com/api/webhooks/stripe/`
- [ ] Configure Cal.com webhook endpoint: `https://learnpuddle.com/api/webhooks/cal/`
- [ ] Test email delivery (send test email through admin panel)
- [ ] Run a full flow test: create tenant, add teacher, upload video, verify processing
- [ ] Document the Droplet IP, managed DB host, and Redis host for the team
- [ ] Set up SSH key rotation schedule
- [ ] Review and tighten Cloudflare WAF rules (Growth tier)

---

## Appendix A: Quick Reference Commands

```bash
# SSH to production
ssh deploy@<DROPLET_IP>
cd /opt/lms

# View all container status
docker compose -f docker-compose.prod.yml ps

# View logs (all services)
docker compose -f docker-compose.prod.yml logs -f --tail=50

# View logs (specific service)
docker compose -f docker-compose.prod.yml logs -f web
docker compose -f docker-compose.prod.yml logs -f worker

# Restart a single service
docker compose -f docker-compose.prod.yml restart web

# Run Django management command
docker compose -f docker-compose.prod.yml exec web python manage.py <command>

# Django shell
docker compose -f docker-compose.prod.yml exec web python manage.py shell_plus

# Database shell (managed DB)
docker compose -f docker-compose.prod.yml exec web python manage.py dbshell

# Pull latest code and redeploy
git pull origin main
docker compose -f docker-compose.prod.yml build --no-cache web nginx
docker compose -f docker-compose.prod.yml run --rm web python manage.py migrate --noinput
docker compose -f docker-compose.prod.yml run --rm -u root web python manage.py collectstatic --noinput
docker compose -f docker-compose.prod.yml up -d

# Emergency: force recreate all containers
docker compose -f docker-compose.prod.yml up -d --force-recreate

# Cleanup disk space
docker system prune -f
docker image prune -a -f  # Warning: removes all unused images
```

## Appendix B: Environment Variable Reference

Full list of all environment variables used by the LMS, organized by category:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SECRET_KEY` | Yes | - | Django secret key (50+ random hex chars) |
| `DEBUG` | No | `False` | Enable debug mode (never True in production) |
| `PLATFORM_DOMAIN` | Yes | `localhost` | Root domain (e.g., `learnpuddle.com`) |
| `PLATFORM_NAME` | No | `LearnPuddle` | Platform display name |
| `ALLOWED_HOSTS` | No | Auto-derived | Comma-separated allowed hosts |
| `DB_NAME` | Yes | - | PostgreSQL database name |
| `DB_USER` | Yes | - | PostgreSQL username |
| `DB_PASSWORD` | Yes | - | PostgreSQL password |
| `DB_HOST` | Yes | `localhost` | PostgreSQL host |
| `DB_PORT` | No | `5432` | PostgreSQL port (25060 for managed) |
| `DB_CONN_MAX_AGE` | No | `600` | Connection reuse time (seconds) |
| `REDIS_URL` | No | `redis://localhost:6379/1` | Redis URL for cache |
| `REDIS_PASSWORD` | Yes (prod) | - | Redis password |
| `CELERY_BROKER_URL` | No | `redis://localhost:6379/0` | Celery broker URL |
| `STORAGE_BACKEND` | No | `local` | `local` or `s3` |
| `STORAGE_ACCESS_KEY` | If s3 | - | S3/Spaces access key |
| `STORAGE_SECRET_KEY` | If s3 | - | S3/Spaces secret key |
| `STORAGE_BUCKET` | If s3 | - | Bucket name |
| `STORAGE_REGION` | If s3 | - | Region (e.g., `blr1`) |
| `STORAGE_ENDPOINT` | If s3 | - | S3 endpoint URL |
| `CDN_DOMAIN` | No | - | CDN hostname for media URLs |
| `JWT_SIGNING_KEY` | Yes (prod) | `SECRET_KEY` | JWT signing key (must differ from SECRET_KEY) |
| `JWT_ACCESS_TOKEN_LIFETIME` | No | `15` | Access token lifetime (minutes) |
| `JWT_REFRESH_TOKEN_LIFETIME` | No | `10080` | Refresh token lifetime (minutes, default 7 days) |
| `EMAIL_BACKEND` | No | `console` | Django email backend class |
| `EMAIL_HOST` | If SMTP | - | SMTP host |
| `EMAIL_PORT` | No | `587` | SMTP port |
| `EMAIL_HOST_USER` | If SMTP | - | SMTP username |
| `EMAIL_HOST_PASSWORD` | If SMTP | - | SMTP password / API key |
| `DEFAULT_FROM_EMAIL` | No | `noreply@{domain}` | Sender email address |
| `OPENROUTER_API_KEY` | No | - | OpenRouter API key for LLM quiz generation |
| `ELEVENLABS_API_KEY` | No | - | ElevenLabs API key for TTS |
| `STRIPE_SECRET_KEY` | No | - | Stripe secret key |
| `STRIPE_PUBLISHABLE_KEY` | No | - | Stripe publishable key |
| `STRIPE_WEBHOOK_SECRET` | No | - | Stripe webhook signing secret |
| `SENTRY_DSN` | No | - | Sentry error tracking DSN |
| `SENTRY_ENVIRONMENT` | No | `production` | Sentry environment tag |
| `SENTRY_TRACES_RATE` | No | `0.1` | Sentry performance sampling rate |
| `FLOWER_USER` | No | `admin` | Flower dashboard username |
| `FLOWER_PASSWORD` | Yes (prod) | - | Flower dashboard password |
| `GUNICORN_WORKERS` | No | `3` | Number of Gunicorn workers |
| `CELERY_CONCURRENCY` | No | `2` | Celery worker concurrency |
| `LOG_LEVEL` | No | `INFO` | Logging level |
| `LOG_JSON` | No | `True` (prod) | Use JSON structured logging |
| `GOOGLE_OAUTH_CLIENT_ID` | No | - | Google SSO client ID |
| `GOOGLE_OAUTH_CLIENT_SECRET` | No | - | Google SSO client secret |
| `CAL_WEBHOOK_SECRET` | No | - | Cal.com webhook verification secret |
| `MAX_VIDEO_UPLOAD_SIZE_MB` | No | `500` | Maximum video upload size |
