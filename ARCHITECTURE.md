# Brain LMS -- Architecture & Operations Guide

## Table of Contents

- [System Overview](#system-overview)
- [Architecture Diagram](#architecture-diagram)
- [Technology Stack](#technology-stack)
- [Multi-Tenancy Model](#multi-tenancy-model)
- [Backend Structure](#backend-structure)
- [Frontend Structure](#frontend-structure)
- [Data Flow](#data-flow)
- [Video Processing Pipeline](#video-processing-pipeline)
- [API Reference](#api-reference)
- [Running Locally](#running-locally)
- [Production Deployment](#production-deployment)
- [Commands Reference](#commands-reference)
- [Pending / Roadmap](#pending--roadmap)

---

## System Overview

Brain LMS is a multi-tenant SaaS Learning Management System for schools. Each school (tenant) gets its own branded subdomain (`schoolname.lms.com`) with complete data isolation, while sharing a single codebase and database.

**Three user interfaces on one platform:**

| Portal | Who uses it | Route prefix | Purpose |
|--------|-------------|--------------|---------|
| Command Center | Platform operator (you) | `/super-admin/*` | Onboard schools, manage tenants, platform stats |
| School Admin | School principal / coordinator | `/admin/*` | Manage courses, teachers, groups, reports, branding |
| Teacher Portal | Teachers | `/teacher/*` | View courses, watch videos, take quizzes, submit assignments |

---

## Architecture Diagram

```
                    ┌──────────────────────────────────────────────┐
                    │              Internet / Browser              │
                    └──────────────────┬───────────────────────────┘
                                       │
                            *.lms.com (wildcard DNS)
                                       │
                    ┌──────────────────▼───────────────────────────┐
                    │           Nginx (reverse proxy)              │
                    │  • SSL termination (Let's Encrypt wildcard)  │
                    │  • /api/* → Gunicorn                         │
                    │  • /static/* → filesystem                    │
                    │  • /media/* → filesystem (or S3)             │
                    │  • /* → React SPA (index.html)               │
                    └───────┬──────────────┬───────────────────────┘
                            │              │
                 ┌──────────▼──────┐  ┌────▼──────────────────┐
                 │  React Frontend │  │  Django + Gunicorn     │
                 │  (static SPA)   │  │  (REST API)            │
                 │  Port 3000 dev  │  │  Port 8000             │
                 │  Tailwind CSS   │  │  DRF + SimpleJWT       │
                 │  React Query    │  │  TenantMiddleware       │
                 │  Zustand        │  │                         │
                 └─────────────────┘  └───┬──────────┬──────────┘
                                          │          │
                              ┌────────────▼──┐  ┌───▼──────────┐
                              │  PostgreSQL   │  │    Redis      │
                              │  (all data)   │  │  (Celery      │
                              │               │  │   broker)     │
                              └───────────────┘  └───┬──────────┘
                                                     │
                                          ┌──────────▼──────────┐
                                          │   Celery Workers    │
                                          │  • Video transcode  │
                                          │  • Transcription     │
                                          │  • Quiz generation  │
                                          │  • Email sending    │
                                          │  • Trial expiry     │
                                          └─────────────────────┘
```

---

## Technology Stack

### Backend

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Framework | Django 5.0 + Django REST Framework | API server |
| Database | PostgreSQL 15 | All application data |
| Auth | Simple JWT (access + refresh tokens) | Stateless authentication |
| Task Queue | Celery 5.3 + Redis 7 | Background jobs (video, email) |
| Video Processing | ffmpeg + ffprobe | HLS transcoding, thumbnails |
| Transcription | faster-whisper (OpenAI Whisper) | Speech-to-text for video captions |
| Storage | Local filesystem / S3 (MinIO dev) | Media files, video artifacts |
| WSGI Server | Gunicorn | Production HTTP server |
| Email | Django send_mail (SMTP configurable) | Welcome emails, password resets |

### Frontend

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Framework | React 19 + TypeScript | UI |
| Styling | Tailwind CSS 3 | Utility-first CSS |
| State | Zustand | Auth & tenant state |
| Data Fetching | TanStack Query (React Query) | Server state + caching |
| HTTP | Axios | API client with JWT interceptor |
| Video | hls.js | Adaptive HLS streaming |
| Charts | Chart.js + react-chartjs-2 | Analytics visualizations |
| Icons | Heroicons | UI icons |
| Routing | React Router DOM v6 | SPA navigation |

### Infrastructure

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Containers | Docker + Docker Compose | Packaging and orchestration |
| Reverse Proxy | Nginx 1.25 | SSL, static files, routing |
| SSL | Let's Encrypt (Certbot) | Free wildcard certificates |
| CI/CD | GitHub Actions | Test, build, deploy pipeline |
| Dev Storage | MinIO | S3-compatible local storage |

---

## Multi-Tenancy Model

Brain LMS uses **shared database, shared application** multi-tenancy. There is no per-school infrastructure. All schools share one PostgreSQL database with row-level tenant isolation.

### How Tenant Isolation Works

```
    Request: https://abcschool.lms.com/api/courses/
                        │
                        ▼
    ┌──────────────────────────────────────────┐
    │        TenantMiddleware                  │
    │  1. Extract subdomain "abcschool"        │
    │  2. Lookup Tenant(subdomain="abcschool") │
    │  3. Attach to request.tenant             │
    │  4. Set in thread-local storage          │
    │  5. Verify user.tenant == request.tenant │
    └──────────────────┬───────────────────────┘
                       ▼
    ┌──────────────────────────────────────────┐
    │            View / Serializer             │
    │  Course.objects.filter(tenant=req.tenant)│
    │  ──── or ────                            │
    │  TenantManager auto-filters by tenant    │
    └──────────────────────────────────────────┘
```

**Key files:**

| File | Responsibility |
|------|---------------|
| `backend/utils/tenant_middleware.py` | Extract tenant from subdomain, enforce membership |
| `backend/utils/tenant_utils.py` | Parse subdomain from HTTP Host header |
| `backend/utils/tenant_manager.py` | Custom QuerySet manager that auto-filters by tenant |
| `backend/apps/tenants/models.py` | Tenant model (name, subdomain, branding, trial status) |

**Tenant-aware models** use `TenantManager` or explicit `filter(tenant=request.tenant)`. Every app (courses, progress, notifications, reminders) is tenant-scoped.

---

## Backend Structure

```
backend/
├── config/                    # Django project config
│   ├── settings.py            # All settings (DB, JWT, Celery, Storage, Email)
│   ├── urls.py                # Root URL router
│   ├── celery.py              # Celery app + beat schedule
│   └── wsgi.py / asgi.py      # WSGI/ASGI entry points
│
├── apps/
│   ├── tenants/               # Multi-tenancy core
│   │   ├── models.py          # Tenant model (branding, trial, status)
│   │   ├── services.py        # TenantService.create_tenant_with_admin()
│   │   ├── views.py           # Public theme endpoint
│   │   ├── superadmin_views.py # Command center API (CRUD tenants)
│   │   ├── emails.py          # Welcome & trial expiry emails
│   │   └── tasks.py           # Daily trial expiration check
│   │
│   ├── users/                 # Authentication & user management
│   │   ├── models.py          # Custom User (email auth, roles, tenant FK)
│   │   ├── views.py           # Login, logout, refresh, password reset
│   │   ├── tokens.py          # JWT with custom claims (role, tenant_id)
│   │   └── admin_views.py     # Teacher management for school admins
│   │
│   ├── courses/               # Course content management
│   │   ├── models.py          # Course → Module → Content hierarchy
│   │   ├── video_models.py    # VideoAsset, VideoTranscript
│   │   ├── views.py           # Admin CRUD for courses/modules/contents
│   │   ├── video_views.py     # Video upload, status, regenerate
│   │   ├── tasks.py           # Celery pipeline (transcode, transcribe, quiz)
│   │   ├── teacher_views.py   # Teacher course viewing + transcript API
│   │   └── group_views.py     # Teacher group management
│   │
│   ├── progress/              # Learning progress & assignments
│   │   ├── models.py          # TeacherProgress, Assignment, Quiz, QuizQuestion
│   │   └── teacher_views.py   # Dashboard, progress tracking, quiz submit
│   │
│   ├── notifications/         # In-app notification bell
│   ├── reminders/             # Bulk email/in-app reminders
│   ├── reports/               # Course completion & assignment reports
│   └── uploads/               # File upload endpoints
│
└── utils/                     # Shared utilities
    ├── decorators.py          # @admin_only, @super_admin_only, @tenant_required
    ├── tenant_middleware.py    # Request-level tenant resolution
    └── tenant_manager.py      # Auto-filtering QuerySet
```

### User Roles

| Role | Access | Can belong to tenant? |
|------|--------|----------------------|
| `SUPER_ADMIN` | Command center, all tenants | No (tenant = null) |
| `SCHOOL_ADMIN` | Full school admin panel | Yes |
| `TEACHER` | Teacher portal only | Yes |
| `HOD` | Teacher portal + dept visibility | Yes |
| `IB_COORDINATOR` | Teacher portal + IB visibility | Yes |

---

## Frontend Structure

```
frontend/src/
├── App.tsx                    # Route definitions (3 protected groups)
├── config/
│   ├── api.ts                 # Axios instance + JWT interceptor
│   └── theme.ts               # Dynamic tenant branding (CSS variables)
│
├── stores/
│   ├── authStore.ts           # Zustand: user, tokens, isAuthenticated
│   └── tenantStore.ts         # Zustand: tenant theme
│
├── services/                  # API service layer (one per domain)
│   ├── authService.ts         # Login, logout, refresh, password reset
│   ├── teacherService.ts      # Courses, progress, assignments, quizzes
│   ├── superAdminService.ts   # Platform stats, tenant CRUD, onboarding
│   ├── adminService.ts        # Tenant stats
│   └── ...                    # Groups, reminders, reports, notifications
│
├── pages/
│   ├── superadmin/            # Command center UI
│   │   ├── DashboardPage.tsx  # Platform-wide stats
│   │   └── SchoolsPage.tsx    # School list + onboard modal
│   │
│   ├── admin/                 # School admin UI
│   │   ├── DashboardPage.tsx  # School stats + recent activity
│   │   ├── CourseEditorPage.tsx # Create/edit courses, modules, content
│   │   ├── CoursesPage.tsx    # Course list
│   │   ├── TeachersPage.tsx   # Teacher management
│   │   ├── GroupsPage.tsx     # Teacher groups
│   │   ├── ReportsPage.tsx    # Completion & assignment reports
│   │   ├── RemindersPage.tsx  # Bulk reminders
│   │   └── SettingsPage.tsx   # Branding (logo, colors, fonts)
│   │
│   ├── teacher/               # Teacher portal
│   │   ├── DashboardPage.tsx  # Personal stats + continue learning
│   │   ├── MyCoursesPage.tsx  # Assigned course grid
│   │   ├── CourseViewPage.tsx # Course player (sidebar + content)
│   │   ├── AssignmentsPage.tsx # Assignment list with status filters
│   │   ├── QuizPage.tsx       # Quiz-taking interface
│   │   └── ProfilePage.tsx    # User profile
│   │
│   └── auth/
│       └── LoginPage.tsx      # Tenant-branded login
│
└── components/
    ├── common/                # Button, Input, Toast, Loading, ProtectedRoute
    ├── layout/                # AdminLayout, TeacherLayout, SuperAdminLayout
    └── teacher/               # ContentPlayer (HLS + transcript), CourseCard
```

---

## Data Flow

### Login Flow

```
Browser                      Frontend                       Backend
  │                            │                              │
  │  Enter email/password      │                              │
  │ ─────────────────────────► │                              │
  │                            │  POST /api/users/auth/login/ │
  │                            │ ────────────────────────────►│
  │                            │                              │ authenticate()
  │                            │                              │ get_tokens_for_user()
  │                            │  { user, tokens }            │ (JWT with role, tenant_id)
  │                            │ ◄────────────────────────────│
  │                            │ Store in sessionStorage       │
  │                            │ setAuth(user, tokens)         │
  │  Redirect by role          │                              │
  │ ◄──────────────────────────│                              │
```

### School Onboarding Flow

```
Super Admin                  Frontend                       Backend
  │                            │                              │
  │  Fill onboard form         │                              │
  │ ─────────────────────────► │                              │
  │                            │  POST /api/super-admin/      │
  │                            │       tenants/               │
  │                            │ ────────────────────────────►│
  │                            │                              │ TenantService
  │                            │                              │   .create_tenant_with_admin()
  │                            │                              │   → Create Tenant row
  │                            │                              │   → Create SCHOOL_ADMIN user
  │                            │                              │   → Auto-generate subdomain
  │                            │                              │ send_onboard_welcome_email()
  │                            │  { tenant, admin_email,      │
  │                            │    subdomain }               │
  │                            │ ◄────────────────────────────│
  │  "School onboarded!"       │                              │
  │ ◄──────────────────────────│                              │
  │                            │                              │
  │  School admin receives     │                              │
  │  welcome email with        │                              │
  │  subdomain URL + login     │                              │
```

---

## Video Processing Pipeline

When an admin uploads a video, a Celery task chain runs in the background:

```
Upload                 Celery Worker Pipeline
  │
  ▼
 POST /api/courses/{id}/modules/{id}/contents/video-upload/
  │
  │  1. Save source file to storage (tenant-prefixed key)
  │  2. Create Content(VIDEO) + VideoAsset(UPLOADED)
  │  3. Enqueue Celery chain ──►─┐
  │  4. Return 201 immediately   │
  │                               ▼
  │                        ┌──────────────┐
  │                        │  validate    │  ffprobe: read duration
  │                        │  _duration   │  FAIL if > 3600s (1 hour)
  │                        └──────┬───────┘
  │                               ▼
  │                        ┌──────────────┐
  │                        │ transcode    │  ffmpeg → HLS (m3u8 + .ts segments)
  │                        │ _to_hls      │  Upload to storage
  │                        └──────┬───────┘
  │                               ▼
  │                        ┌──────────────┐
  │                        │  generate    │  ffmpeg → thumbnail at 1s
  │                        │  _thumbnail  │  Upload to storage
  │                        └──────┬───────┘
  │                               ▼
  │                        ┌──────────────┐
  │                        │ transcribe   │  faster-whisper → segments + VTT
  │                        │ _video       │  Upload captions.vtt to storage
  │                        └──────┬───────┘
  │                               ▼
  │                        ┌──────────────┐
  │                        │  generate    │  Create 2 assignments:
  │                        │ _assignments │  • Reflection (text submission)
  │                        │              │  • Quiz (MCQ + short answer)
  │                        │              │  Notify assigned teachers
  │                        └──────┬───────┘
  │                               ▼
  │                        ┌──────────────┐
  │                        │  finalize    │  Set VideoAsset.status = READY
  │                        │ _video_asset │
  │                        └──────────────┘
```

**Storage layout** (tenant-isolated):
```
tenant/{tenant_id}/videos/{content_id}/
├── source.mp4
├── hls/
│   ├── master.m3u8
│   └── seg_00001.ts, seg_00002.ts, ...
├── thumb.jpg
└── captions.vtt
```

---

## API Reference

### Authentication (public)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/users/auth/login/` | Login → returns JWT tokens |
| POST | `/api/users/auth/refresh/` | Refresh access token |
| POST | `/api/users/auth/logout/` | Blacklist refresh token |
| POST | `/api/users/auth/request-password-reset/` | Email reset link |
| POST | `/api/users/auth/confirm-password-reset/` | Reset with uid+token |
| GET | `/api/tenants/theme/` | Tenant branding (public, no auth) |

### Command Center (SUPER_ADMIN only)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/super-admin/stats/` | Platform-wide stats |
| GET | `/api/super-admin/tenants/` | List all schools (paginated, filterable) |
| POST | `/api/super-admin/tenants/` | Onboard a new school |
| GET | `/api/super-admin/tenants/{id}/` | School detail |
| PATCH | `/api/super-admin/tenants/{id}/` | Update school (activate/deactivate) |
| POST | `/api/super-admin/tenants/{id}/impersonate/` | Get admin JWT for support |

### School Admin (SCHOOL_ADMIN)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/tenants/stats/` | School stats |
| GET/PATCH | `/api/tenants/settings/` | Branding settings |
| GET/POST | `/api/courses/` | Course CRUD |
| GET/PATCH/DELETE | `/api/courses/{id}/` | Course detail |
| POST | `/api/courses/{id}/publish/` | Publish/unpublish |
| GET/POST | `/api/courses/{id}/modules/` | Module CRUD |
| GET/POST | `/api/courses/{id}/modules/{id}/contents/` | Content CRUD |
| POST | `/api/courses/{id}/modules/{id}/contents/video-upload/` | Video upload |
| GET | `/api/courses/{id}/modules/{id}/contents/{id}/video-status/` | Processing status |
| GET | `/api/teachers/` | Teacher list |
| POST | `/api/users/auth/register-teacher/` | Create teacher |
| GET/POST | `/api/teacher-groups/` | Group management |
| GET | `/api/reports/course-completion/` | Reports |
| POST | `/api/reminders/` | Send reminders |

### Teacher Portal (TEACHER / HOD / IB_COORDINATOR)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/teacher/dashboard/` | Dashboard stats |
| GET | `/api/teacher/courses/` | My courses |
| GET | `/api/teacher/courses/{id}/` | Course detail + progress |
| POST | `/api/teacher/progress/content/{id}/start/` | Start content |
| PATCH | `/api/teacher/progress/content/{id}/` | Update progress |
| POST | `/api/teacher/progress/content/{id}/complete/` | Mark complete |
| GET | `/api/teacher/videos/{id}/transcript/` | Video transcript |
| GET | `/api/teacher/assignments/` | My assignments |
| POST | `/api/teacher/assignments/{id}/submit/` | Submit assignment |
| GET | `/api/teacher/quizzes/{id}/` | Quiz questions |
| POST | `/api/teacher/quizzes/{id}/submit/` | Submit quiz |
| GET | `/api/notifications/` | Notification list |

---

## Running Locally

### Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL 14+ (or Docker)
- ffmpeg (for video processing)
- Redis (for Celery -- optional for basic dev)

### 1. Start the database

```bash
cd backend
docker-compose up -d db    # starts Postgres on port 5433
```

### 2. Backend setup

```bash
cd backend

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate        # macOS/Linux
# venv\Scripts\activate         # Windows

# Install dependencies
pip install -r requirements.txt

# Create .env from example
cp .env.example .env
# Edit .env with your DB credentials

# Run migrations
python manage.py migrate

# Create demo tenant + admin user
python manage.py create_demo_tenant

# Start Django dev server
python manage.py runserver 0.0.0.0:8000
```

### 3. Frontend setup

```bash
cd frontend

# Install dependencies
npm install

# Start dev server
npm start
# → opens http://localhost:3000
```

### 4. (Optional) Start Celery for video processing

```bash
# Terminal 1: start Redis
docker-compose up -d redis

# Terminal 2: start Celery worker
cd backend && source venv/bin/activate
celery -A config worker -l info

# Terminal 3: start Celery beat (scheduled tasks)
celery -A config beat -l info
```

### Demo credentials

| Role | Email | Password |
|------|-------|----------|
| Super Admin | admin@lms.com | (set manually via Django shell) |
| School Admin | admin@demo.com | demo123 |
| Teacher | teacher@demo.com | demo123 |

### Creating a super admin

```bash
cd backend && source venv/bin/activate
python manage.py shell -c "
from apps.users.models import User
User.objects.create_superuser(
    email='admin@lms.com',
    password='superadmin123',
    first_name='Platform',
    last_name='Admin'
)
print('Super admin created: admin@lms.com')
"
```

---

## Production Deployment

### Quick deploy (single VPS)

**1. Provision a VPS** (DigitalOcean 4GB+ / Hetzner / AWS Lightsail, ~$24/mo)

**2. Set up DNS:**
- `A` record: `lms.com` → server IP
- `A` record: `*.lms.com` → server IP (wildcard)

**3. Clone and configure:**
```bash
ssh root@your-server
mkdir -p /opt/lms && cd /opt/lms
git clone https://github.com/your-org/LMS.git .

# Create production .env
cat > .env << 'EOF'
SECRET_KEY=your-random-secret-key-here
DB_NAME=lms_db
DB_USER=postgres
DB_PASSWORD=strong-password-here
PLATFORM_DOMAIN=lms.com
PLATFORM_NAME=Brain LMS
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.mailgun.org
EMAIL_HOST_USER=postmaster@lms.com
EMAIL_HOST_PASSWORD=your-mailgun-key
DEFAULT_FROM_EMAIL=noreply@lms.com
EOF
```

**4. SSL certificate:**
```bash
# First, temporarily start nginx without SSL for certbot challenge
docker compose -f docker-compose.prod.yml up -d nginx
certbot certonly --webroot -w /var/www/certbot \
  -d "lms.com" -d "*.lms.com" \
  --preferred-challenges dns
```

**5. Launch:**
```bash
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml exec web python manage.py migrate
docker compose -f docker-compose.prod.yml exec web python manage.py collectstatic --noinput
docker compose -f docker-compose.prod.yml exec web python manage.py create_demo_tenant
```

**6. Update `nginx/nginx.conf`** to replace `lms.com` with your actual domain.

### CI/CD (GitHub Actions)

The `.github/workflows/ci.yml` pipeline:

1. **On every PR:** runs backend tests + frontend build check
2. **On push to main:** builds Docker images → pushes to GHCR → SSH deploys to VPS

Required GitHub Secrets:
- `DEPLOY_HOST` -- your server IP
- `DEPLOY_USER` -- SSH user (e.g., `deploy`)
- `DEPLOY_SSH_KEY` -- SSH private key

---

## Commands Reference

### Management commands

```bash
# Create demo tenant (dev)
python manage.py create_demo_tenant

# Run migrations
python manage.py migrate

# Collect static files (production)
python manage.py collectstatic --noinput

# Django shell
python manage.py shell

# Run tests
python manage.py test
```

### Celery commands

```bash
# Start worker (processes video, sends emails)
celery -A config worker -l info --concurrency=2

# Start beat (scheduled tasks: trial expiry)
celery -A config beat -l info

# Inspect active tasks
celery -A config inspect active
```

### Docker commands (production)

```bash
# Start all services
docker compose -f docker-compose.prod.yml up -d

# View logs
docker compose -f docker-compose.prod.yml logs -f web
docker compose -f docker-compose.prod.yml logs -f worker

# Run migrations
docker compose -f docker-compose.prod.yml exec web python manage.py migrate

# Access Django shell
docker compose -f docker-compose.prod.yml exec web python manage.py shell

# Restart after code update
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d --remove-orphans
```

---

## Pending / Roadmap

### Already built and working

- [x] Multi-tenancy (subdomain-based, shared DB)
- [x] School admin panel (courses, teachers, groups, reports, reminders, settings)
- [x] Teacher portal (courses, video player, assignments, quizzes, notifications)
- [x] Video pipeline (upload → HLS → thumbnail → transcript → auto-quiz)
- [x] HLS streaming with transcript panel and click-to-seek
- [x] Command center API (onboard schools, list/update/deactivate, impersonate)
- [x] Command center frontend (dashboard, schools list, onboard modal)
- [x] Welcome email on school onboard
- [x] Password reset flow (request + confirm with token)
- [x] Trial expiration automation (Celery beat daily check)
- [x] Production Dockerfiles (backend + frontend)
- [x] Docker Compose production config (all 6 services)
- [x] Nginx wildcard subdomain config with SSL
- [x] CI/CD pipeline (GitHub Actions: test → build → deploy)
- [x] Dynamic tenant branding (logo, colors, fonts)
- [x] JWT auth with custom claims (role, tenant_id)

### Pending for production hardening

| Item | Priority | Effort |
|------|----------|--------|
| Analytics page with charts (engagement, completion trends) | Medium | Medium |
| Custom domain support (TenantDomain model + nginx routing) | Medium | Medium |
| Audit logging for admin actions | High | Small |
| Database backup automation (pg_dump cron) | High | Small |
| CSV/PDF export for reports | Medium | Small |
| Email verification flow (verify teacher email) | Low | Small |
| Account lockout after failed login attempts | Medium | Small |
| Structured JSON logging for production | Low | Tiny |
| Sentry error tracking integration | High | Tiny |
| Frontend password reset page (currently backend-only) | High | Small |
| File size limits on video upload (client-side + server-side) | Medium | Tiny |

### Cost to run

| Service | Cost | Notes |
|---------|------|-------|
| VPS (4GB) | $24/mo | Handles 50+ schools |
| Domain | $12/year | .com domain |
| SSL | Free | Let's Encrypt wildcard |
| Email | Free | Mailgun/Resend free tier |
| Monitoring | Free | Sentry free tier |
| **Total** | **~$26/month** | |
