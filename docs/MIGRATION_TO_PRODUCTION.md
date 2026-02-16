# LearnPuddle: Migration to Production Plan

This document outlines the steps to migrate LearnPuddle to production with:
1. **Command Center** at `learnpuddle.com/admin` (or `/super-admin` for the platform admin UI)
2. **Subdomain-based school isolation** — each school gets `schoolname.learnpuddle.com` automatically when they register

---

## Architecture Overview

| URL | Purpose |
|-----|---------|
| `https://learnpuddle.com` | Platform root — Command Center, signup, marketing |
| `https://learnpuddle.com/super-admin/login` | Super admin (platform) login |
| `https://learnpuddle.com/super-admin/*` | Command Center dashboard, schools management |
| `https://learnpuddle.com/signup` | New school self-service registration |
| `https://learnpuddle.com/admin/` | Django admin (optional, for DB-level ops) |
| `https://schoolname.learnpuddle.com` | School tenant — admin + teachers |
| `https://schoolname.learnpuddle.com/login` | School admin / teacher login |
| `https://schoolname.learnpuddle.com/admin/*` | School admin dashboard |
| `https://schoolname.learnpuddle.com/teacher/*` | Teacher dashboard |

---

## Phase 1: Backend — Root Domain Handling

**Problem:** Visiting `learnpuddle.com` currently triggers tenant resolution. The code treats `learnpuddle` as a subdomain and looks for `Tenant(subdomain='learnpuddle')`, which fails → 403.

**Fix:** Treat the root domain (`learnpuddle.com`) as platform-level (no tenant). Only subdomains like `school.learnpuddle.com` resolve to tenants.

### 1.1 Update `backend/utils/tenant_utils.py`

Add root-domain check before subdomain lookup:

```python
from django.conf import settings

def get_tenant_from_request(request):
    host = request.get_host().split(':')[0].lower()

    # Platform root — no tenant (command center, signup, marketing)
    platform_domain = getattr(settings, 'PLATFORM_DOMAIN', '').lower()
    if platform_domain and host == platform_domain:
        return None

    # Development mode — use demo tenant
    if host in ['localhost', '127.0.0.1']:
        subdomain = 'demo'
    else:
        # Custom domain lookup...
        # Subdomain lookup: school.learnpuddle.com → subdomain='school'
        ...
```

### 1.2 Update `backend/utils/tenant_middleware.py`

Ensure `request.tenant = None` is handled for views that expect it (super-admin, onboarding). The middleware already sets `tenant = None` when `get_tenant_from_request` raises; after the fix it will return `None` directly.

### 1.3 Add onboarding to public paths (if missing)

Ensure `/api/onboarding/` and `/api/tenants/` signup endpoints are in `public_paths` so unauthenticated signup works on the root domain.

---

## Phase 2: DNS & SSL (Cloudflare)

### 2.1 Domain setup

1. Point `learnpuddle.com` to your Droplet IP (A record).
2. Add **wildcard** record: `*.learnpuddle.com` → same Droplet IP (A or CNAME).
3. Enable Cloudflare proxy (orange cloud) for both.
4. SSL: Cloudflare provides free SSL. Set SSL mode to **Full** (or **Full (Strict)** if using Origin Certificate).

### 2.2 No per-school DNS

Subdomains are **not** created manually. When a school signs up with subdomain `silveroaks`, `silveroaks.learnpuddle.com` works immediately because of the wildcard `*.learnpuddle.com`.

---

## Phase 3: Frontend — Root vs Subdomain UX

### 3.1 Command Center at root

- **Super-admin login:** `https://learnpuddle.com/super-admin/login`
- **Command Center:** `https://learnpuddle.com/super-admin/dashboard`, `/super-admin/schools`, etc.
- These routes are already defined in `App.tsx`; they work once the backend returns 200 for root-domain requests.

### 3.2 School login flow

- School admins and teachers use their school subdomain: `https://schoolname.learnpuddle.com/login`.
- Optional: Add a "Find your school" page at `learnpuddle.com` that lets users enter their school name and redirects to `schoolname.learnpuddle.com/login`.

### 3.3 Signup flow

- New schools sign up at `https://learnpuddle.com/signup`.
- On success, they receive:
  - Subdomain (e.g. `demo-school`)
  - Login URL: `https://demo-school.learnpuddle.com/login`
- Email templates in `onboarding_views.py` already use `{subdomain}.{PLATFORM_DOMAIN}`.

---

## Phase 4: Subdomain Auto-Provisioning (School Registration)

### 4.1 Self-service signup (`/signup`)

1. School fills: name, admin email, password, plan.
2. Backend generates unique subdomain via `generate_unique_subdomain(school_name)`.
3. Creates `Tenant` and `User` (SCHOOL_ADMIN).
4. Sends verification email with login URL: `https://{subdomain}.learnpuddle.com/login`.
5. No manual DNS or config — wildcard handles it.

### 4.2 Subdomain availability check

- `GET /api/onboarding/check-subdomain/?subdomain=schoolname` — used by signup form to validate availability before submit.

### 4.3 Command Center — create school manually

- Super admin can create schools via Command Center at `learnpuddle.com/super-admin/schools`.
- Same flow: subdomain is set, tenant created, admin user created.
- Subdomain is immediately usable.

---

## Phase 5: Deployment Checklist

### 5.1 Pre-deploy

- [ ] Repo pushed to `thebrainpuddle-dev/learnpuddle-lms` (main branch).
- [ ] DigitalOcean Droplet created (e.g. 2GB RAM, 1 vCPU).
- [ ] Domain `learnpuddle.com` and `*.learnpuddle.com` point to Droplet via Cloudflare.

### 5.2 Server setup

```bash
# SSH into Droplet
ssh root@YOUR_DROPLET_IP

# Run deploy script
cd /opt/lms  # or clone first
git clone https://github.com/thebrainpuddle-dev/learnpuddle-lms.git .
./scripts/deploy-droplet.sh
```

### 5.3 Environment

- [ ] Copy `.env.production.example` → `.env`.
- [ ] Set `PLATFORM_DOMAIN=learnpuddle.com`.
- [ ] Generate secrets: `openssl rand -hex 50`, `openssl rand -base64 24`.
- [ ] Configure Resend (email), DigitalOcean Spaces (storage), Redis password.

### 5.4 Post-deploy

1. **Create superadmin:** `docker compose -f docker-compose.prod.yml run --rm web python manage.py createsuperuser` (e.g. `admin@learnpuddle.com`).
2. **Verify root domain:** `https://learnpuddle.com/super-admin/login` (after Phase 1 fix).
3. **Create first school:** Via Command Center or `https://learnpuddle.com/signup`.
4. **Verify subdomain:** `https://demo.learnpuddle.com/login` (if demo tenant exists).

---

## Phase 6: Optional Enhancements

### 6.1 Custom domains (per school)

- Schools can use `lms.school.edu` instead of `school.learnpuddle.com`.
- Requires: CNAME `lms.school.edu` → `school.learnpuddle.com` (or platform).
- Backend: `Tenant.custom_domain`, `custom_domain_verified`; `tenant_utils` already supports custom domain lookup.
- Add domain verification flow (TXT record) before enabling.

### 6.2 Landing page at root

- Add a marketing/landing page at `https://learnpuddle.com` with:
  - "Get started" → `/signup`
  - "Command Center" → `/super-admin/login` (for platform admins)
  - "Find your school" → form that redirects to `{subdomain}.learnpuddle.com`

### 6.3 Django admin at `/admin`

- Django admin is at `/admin/` (Django’s built-in).
- Command Center (React) is at `/super-admin/`.
- To avoid confusion, you can:
  - Keep both (Django admin for DB ops, Command Center for product use), or
  - Restrict Django admin to staff-only and use Command Center as the main admin UI.

---

## Config Audit Summary

| Config | Expected Value | Purpose |
|--------|----------------|---------|
| `PLATFORM_DOMAIN` | `learnpuddle.com` | Root domain, cookie domain, CORS |
| `ALLOWED_HOSTS` | `.learnpuddle.com,learnpuddle.com,localhost` | Django host validation |
| `CSRF_TRUSTED_ORIGINS` | `https://*.learnpuddle.com,https://learnpuddle.com` | CSRF for root + subdomains |
| `CORS_ALLOWED_ORIGIN_REGEX` | `^https://([a-z0-9-]+\.)*learnpuddle\.com$` | CORS for root + subdomains |
| `SESSION_COOKIE_DOMAIN` | `.learnpuddle.com` | Cookies across subdomains |
| `CSRF_COOKIE_DOMAIN` | `.learnpuddle.com` | Same |
| Cloudflare SSL | **Flexible** | HTTP to origin (port 80) |
| Nginx `server_name` | `_` (catch-all) | Accept any Host |

See `docs/CLOUDFLARE_TROUBLESHOOTING.md` if Cloudflare shows "Host Error".

---

## Summary: Critical Code Change

The **only required code change** for root-domain support is in `tenant_utils.py`:

```python
# At the start of get_tenant_from_request(), after extracting host:
platform_domain = getattr(settings, 'PLATFORM_DOMAIN', '').lower()
if platform_domain and host == platform_domain:
    return None  # Platform root — command center, signup
```

Everything else (DNS wildcard, onboarding, subdomain generation) is already in place. After this change, `learnpuddle.com` will serve the Command Center and signup without requiring a tenant.
