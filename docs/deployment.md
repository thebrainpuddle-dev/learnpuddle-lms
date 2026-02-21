# LearnPuddle Deployment Guide

**New to deployment?** See **[DEPLOY_FROM_SCRATCH.md](DEPLOY_FROM_SCRATCH.md)** for a full step-by-step guide (Cloudflare DNS, Droplet setup, clone, .env, deploy).

---

## Step 1: Migrate Repo to New GitHub Account

Run these commands **on your Mac** (from the project root):

```bash
# 1. Create a new empty repo on GitHub (other account):
#    - Go to github.com → New repository
#    - Name: LMS (or learnpuddle-lms)
#    - Do NOT initialize with README
#    - Copy the clone URL, e.g. https://github.com/YOUR_NEW_ORG/LMS.git

# 2. Add the new repo as remote and push
cd /path/to/your/LMS
git remote add new-origin https://github.com/YOUR_NEW_ORG/LMS.git
git push -u new-origin main

# 3. (Optional) Make new-origin the default and remove old remote
git remote remove origin
git remote rename new-origin origin
```

**If using SSH:**
```bash
git remote add new-origin git@github.com:YOUR_NEW_ORG/LMS.git
git push -u new-origin main
```

---

## Step 2: Deploy on DigitalOcean Droplet

### 2.1 Server Setup (first time only)

SSH into your Droplet:

```bash
ssh root@YOUR_DROPLET_IP
```

On the server:

```bash
# Update system
apt update && apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sh

# Install Docker Compose plugin
apt install -y docker-compose-plugin

# Optional: create deploy user
adduser deploy
usermod -aG sudo deploy
usermod -aG docker deploy
# Copy your SSH key: ssh-copy-id deploy@YOUR_DROPLET_IP
```

### 2.2 Clone the App

```bash
mkdir -p /opt/lms
cd /opt/lms
git clone https://github.com/YOUR_NEW_ORG/LMS.git .
# Or: git clone git@github.com:YOUR_NEW_ORG/LMS.git .
```

### 2.3 Create Production .env

```bash
cd /opt/lms
cp .env.production.example .env
nano .env
```

Fill in all values. Generate secrets:

```bash
openssl rand -hex 50   # for SECRET_KEY and JWT_SIGNING_KEY
openssl rand -base64 24   # for DB_PASSWORD, REDIS_PASSWORD, FLOWER_PASSWORD
```

### 2.4 Start the Stack

```bash
cd /opt/lms

# Build and start DB + Redis first
docker compose -f docker-compose.prod.yml up -d db redis

# Wait for DB to be ready
sleep 15

# Run migrations
docker compose -f docker-compose.prod.yml run --rm web python manage.py migrate --noinput
docker compose -f docker-compose.prod.yml run --rm -u root web python manage.py collectstatic --noinput

# Create superadmin (interactive)
docker compose -f docker-compose.prod.yml run --rm web python manage.py createsuperuser

# Start everything
docker compose -f docker-compose.prod.yml up -d
```

### 2.5 Verify

```bash
# On server
curl -s http://localhost/health/

# In browser
# https://learnpuddle.com
# https://learnpuddle.com/health/
```

### 2.6 Cloudflare Setup

1. **SSL mode**: Set to **Full (Strict)** (HTTPS end-to-end).
2. **DNS**: Add A records for `@` and `*` pointing to your Droplet IP (both proxied).
3. **Post-deploy origin check**:
   ```bash
   ./scripts/check-origin-health.sh docker-compose.prod.yml learnpuddle.com
   ```

### 2.7 Post-Deploy: First School

1. **Resend**: Add and verify domain `learnpuddle.com` in Resend dashboard, add DNS records in Cloudflare.
2. **Create tenant**: Use Command Center at `https://learnpuddle.com/super-admin/schools` or signup at `https://learnpuddle.com/signup`.

---

## One-Line Deploy (after initial setup)

For future deployments (pull latest and restart):

```bash
cd /opt/lms && git pull && docker compose -f docker-compose.prod.yml build --no-cache web nginx && docker compose -f docker-compose.prod.yml run --rm web python manage.py migrate --noinput && docker compose -f docker-compose.prod.yml run --rm -u root web python manage.py collectstatic --noinput && docker compose -f docker-compose.prod.yml up -d --build && ./scripts/check-origin-health.sh docker-compose.prod.yml learnpuddle.com
```
