# LearnPuddle LMS - Development Guide

## Project Overview

LearnPuddle is a multi-tenant Learning Management System (LMS) for teacher professional development. Schools (tenants) get their own subdomain (e.g., `schoolname.learnpuddle.com`) with isolated data, branding, and user management.

### Tech Stack

| Layer | Technology |
|-------|------------|
| **Backend** | Django 4.2 + Django REST Framework |
| **Frontend** | React 18 + TypeScript + Vite |
| **Database** | PostgreSQL 15 |
| **Cache/Queue** | Redis |
| **Background Tasks** | Celery + Celery Beat |
| **Real-time** | Django Channels (WebSockets) |
| **File Storage** | Local filesystem or S3-compatible (DO Spaces, AWS S3) |
| **Auth** | JWT (SimpleJWT) + Google SSO + TOTP 2FA |

### Services (Docker Compose)

| Service | Purpose | Port |
|---------|---------|------|
| `web` | Django API (Gunicorn) | 8000 |
| `asgi` | WebSockets (Daphne) | 8001 |
| `worker` | Celery background tasks | - |
| `beat` | Celery scheduler | - |
| `db` | PostgreSQL | 5432 |
| `redis` | Cache + message broker | 6379 |
| `nginx` | Reverse proxy | 80/443 |
| `flower` | Celery monitoring | 5555 |

---

## Directory Structure

```
LMS/
├── backend/                    # Django REST Framework API
│   ├── config/                 # Project settings
│   │   ├── settings.py         # Django settings (env-driven)
│   │   ├── urls.py             # Root URL routing
│   │   └── wsgi.py / asgi.py   # WSGI/ASGI entry points
│   ├── apps/                   # Django applications
│   │   ├── tenants/            # Multi-tenancy (Tenant model, plans, features)
│   │   ├── users/              # Authentication, User model, roles
│   │   ├── courses/            # Course → Module → Content hierarchy
│   │   ├── progress/           # TeacherProgress, Assignments, Quizzes
│   │   ├── uploads/            # File upload endpoints
│   │   ├── notifications/      # In-app notifications
│   │   ├── reminders/          # Reminder system
│   │   └── reports/            # Analytics and reporting
│   ├── utils/                  # Shared utilities
│   │   ├── decorators.py       # @admin_only, @tenant_required, etc.
│   │   ├── tenant_middleware.py# Tenant resolution from Host header
│   │   ├── tenant_manager.py   # TenantManager for auto-filtering queries
│   │   └── audit.py            # Audit logging
│   └── manage.py
├── frontend/                   # React + TypeScript application
│   ├── src/
│   │   ├── pages/              # Page components by role
│   │   │   ├── admin/          # School Admin pages
│   │   │   ├── teacher/        # Teacher pages
│   │   │   └── super-admin/    # Platform admin pages
│   │   ├── components/         # Reusable UI components
│   │   ├── services/           # API service clients
│   │   ├── stores/             # Zustand state stores
│   │   └── config/             # API configuration
│   └── package.json
├── nginx/                      # Nginx configuration
├── docker-compose.yml          # Local development
├── docker-compose.prod.yml     # Production
└── docs/                       # Documentation
```

---

## Authentication & Authorization

### Roles

| Role | Access | Description |
|------|--------|-------------|
| `SUPER_ADMIN` | Platform-wide | LearnPuddle team, manages all schools |
| `SCHOOL_ADMIN` | Tenant-scoped | School principal/coordinator |
| `TEACHER` | Tenant-scoped | Course consumer |
| `HOD` | Tenant-scoped | Head of Department |
| `IB_COORDINATOR` | Tenant-scoped | IB Coordinator |

### JWT Tokens

- **Access token**: 15 minutes (configurable via `JWT_ACCESS_TOKEN_LIFETIME`)
- **Refresh token**: 7 days (configurable via `JWT_REFRESH_TOKEN_LIFETIME`)
- Token rotation enabled
- Stored in `sessionStorage` (session) or `localStorage` (remember me)

### Key Decorators

```python
from utils.decorators import admin_only, tenant_required, teacher_or_admin, check_feature

@api_view(["GET"])
@permission_classes([IsAuthenticated])
@admin_only                    # SCHOOL_ADMIN or SUPER_ADMIN only
@tenant_required               # Ensures request.tenant is set
def my_admin_view(request):
    pass

@check_feature("certificates") # Requires tenant.features["certificates"] == True
def feature_gated_view(request):
    pass
```

### Middleware Stack (Order Matters)

1. `RequestIDMiddleware` - Assigns X-Request-ID
2. `SecurityMiddleware` - Security headers
3. `CorsMiddleware` - CORS
4. `AuthenticationMiddleware` - User auth
5. `TenantMiddleware` - Tenant resolution (after auth)
6. `LoggingContextMiddleware` - Adds tenant/user to logs

---

## Multi-Tenancy

### Tenant Resolution

```
Request: https://demo.learnpuddle.com/api/courses/
         ^^^^
         subdomain = "demo"

1. TenantMiddleware extracts subdomain from Host header
2. Looks up Tenant(subdomain="demo")
3. Sets request.tenant = tenant
4. Validates user belongs to tenant (except SUPER_ADMIN)
```

### TenantManager (Auto-filtering)

Models using `TenantManager` automatically filter by current tenant:

```python
class Course(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    objects = TenantManager()  # Auto-filters by thread-local tenant

# Usage - automatically filtered
courses = Course.objects.all()  # Only returns current tenant's courses

# Bypass filtering (use carefully)
courses = Course.objects.all_tenants().all()  # All tenants
```

### File Storage Paths

Files are isolated by tenant:
```
media/
└── tenant/
    └── {tenant_id}/
        ├── uploads/
        │   ├── course-thumbnail/
        │   ├── content-file/
        │   └── certificates/
        └── videos/
            └── {content_id}/
                ├── master.m3u8
                └── segments/
```

---

## Key APIs

### Admin Course Management

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/courses/` | GET | List courses |
| `/api/v1/courses/` | POST | Create course |
| `/api/v1/courses/{id}/` | GET | Get course detail |
| `/api/v1/courses/{id}/` | PATCH | Update course |
| `/api/v1/courses/{id}/` | DELETE | Delete course |
| `/api/v1/courses/{id}/modules/` | POST | Add module |
| `/api/v1/courses/{id}/modules/{mid}/contents/` | POST | Add content |
| `/api/v1/courses/{id}/modules/{mid}/contents/video-upload/` | POST | Upload video |

### Admin Teacher Management

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/teachers/` | GET | List teachers |
| `/api/users/auth/register-teacher/` | POST | Create teacher |
| `/api/teachers/{id}/` | PATCH | Update teacher |
| `/api/teachers/{id}/` | DELETE | Deactivate teacher |
| `/api/teachers/bulk-import/` | POST | CSV bulk import |
| `/api/teachers/bulk-action/` | POST | Bulk activate/delete |

### File Uploads

| Endpoint | Method | Max Size | Types |
|----------|--------|----------|-------|
| `/api/v1/uploads/course-thumbnail/` | POST | 5MB | JPEG, PNG, WebP, GIF |
| `/api/v1/uploads/content-file/` | POST | 50MB | PDF, DOC, DOCX, PPT, PPTX, XLS, XLSX |
| `/api/v1/uploads/tenant-logo/` | POST | 2MB | PNG, SVG |
| `/api/v1/uploads/certificate/` | POST | 10MB | JPEG, PNG, PDF |

### Teacher APIs

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/teacher/courses/` | GET | My assigned courses |
| `/api/teacher/courses/{id}/` | GET | Course detail with progress |
| `/api/teacher/progress/content/{id}/complete/` | POST | Mark content complete |
| `/api/teacher/assignments/` | GET | My assignments |
| `/api/teacher/quizzes/{id}/submit/` | POST | Submit quiz |

---

## Background Tasks (Celery)

### Video Processing Pipeline

When a video is uploaded:

```
1. validate_duration     → Check video ≤ 1 hour
2. transcode_to_hls      → Convert to HLS streaming format
3. generate_thumbnail    → Extract poster frame
4. transcribe_video      → Generate transcript (faster-whisper)
5. generate_assignments  → Auto-create quiz from transcript (LLM)
6. finalize_video_asset  → Mark as READY
```

### Key Tasks

```python
# apps/courses/tasks.py
process_video_upload.delay(video_asset_id)  # Full pipeline
transcribe_video.delay(video_asset_id)      # Transcription only
generate_assignments.delay(content_id)       # Quiz generation

# Check status in Flower: http://localhost:5555
```

### Quiz Generation

Uses LLM with fallback chain:
1. OpenRouter (cloud, free tier)
2. Ollama (local, self-hosted)
3. Deterministic generator (fallback)

---

## Common Patterns

### Soft Delete

Models with `SoftDeleteMixin`:

```python
class Course(SoftDeleteMixin, models.Model):
    # has: is_deleted, deleted_at, deleted_by
    pass

# Soft delete
course.soft_delete(user=request.user)

# Query excludes deleted by default
Course.objects.all()  # Only non-deleted

# Include deleted
Course.objects.with_deleted().all()
```

### Audit Logging

```python
from utils.audit import log_audit

log_audit(
    request=request,
    action="CREATE",
    model_name="Course",
    object_id=str(course.id),
    changes={"title": course.title},
)
```

### Error Responses

DRF returns structured errors:

```json
// Field validation error
{
  "email": ["A user with this email already exists."],
  "password": ["This password is too common."]
}

// General error
{
  "detail": "Authentication credentials were not provided."
}

// Custom error
{
  "error": "Tenant limit exceeded"
}
```

---

## Development Workflow

### Local Setup

```bash
# Clone and enter
git clone https://github.com/thebrainpuddle-dev/learnpuddle-lms.git
cd learnpuddle-lms

# Start services
docker compose up -d

# Run migrations
docker compose exec web python manage.py migrate

# Create superuser
docker compose exec web python manage.py createsuperuser

# Create demo tenant
docker compose exec web python manage.py create_demo_tenant

# Access:
# - Frontend: http://localhost:3000
# - API: http://localhost:8000/api/
# - Admin: http://localhost:8000/admin/
# - Flower: http://localhost:5555
```

### Running Tests

```bash
# Backend tests
docker compose exec web pytest

# Specific app
docker compose exec web pytest apps/courses/

# Frontend tests
cd frontend && npm test
```

### Code Style

```bash
# Backend (Python)
black backend/
isort backend/
flake8 backend/

# Frontend (TypeScript)
cd frontend && npm run lint
```

---

## Debugging Tips

### Backend Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f web
docker compose logs -f worker

# Django debug mode
DEBUG=True docker compose up web
```

### API Debugging

```bash
# Test endpoint
curl -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     http://localhost:8000/api/courses/

# Check tenant resolution
curl -H "Host: demo.localhost" http://localhost:8000/api/tenants/theme/
```

### Database Queries

```bash
# Django shell
docker compose exec web python manage.py shell_plus

# Check tenant isolation
>>> from apps.courses.models import Course
>>> Course.objects.all()  # Filtered by current tenant (none in shell)
>>> Course.objects.all_tenants().all()  # All tenants
```

### Celery Tasks

```bash
# Monitor in Flower
open http://localhost:5555

# Check task status
docker compose exec web python manage.py shell
>>> from celery.result import AsyncResult
>>> result = AsyncResult('task-id')
>>> result.status, result.result
```

---

## Common Issues & Solutions

### "Invalid pk - object does not exist" on Course Save

**Cause**: Serializer queryset doesn't match what frontend shows.

**Solution**: Ensure serializer querysets match list endpoints:
```python
# In CourseDetailSerializer.__init__()
self.fields['assigned_teachers'].queryset = User.objects.filter(
    tenant=request.tenant,
).exclude(role__in=['SUPER_ADMIN', 'SCHOOL_ADMIN'])
```

### Tenant Not Set (403 Forbidden)

**Cause**: `TenantMiddleware` couldn't resolve tenant from Host header.

**Solution**: 
- Check Host header matches a tenant subdomain
- For local dev, use `demo.localhost:8000`
- Add `X-Tenant-Subdomain: demo` header

### File Upload Fails

**Cause**: MIME type or size validation.

**Checklist**:
1. Check file size against endpoint limits
2. Verify MIME type matches extension
3. Check storage permissions (S3 or local)
4. Monitor `docker compose logs web` for errors

### Video Processing Stuck

**Cause**: Celery task failed or queue backed up.

**Solution**:
1. Check Flower for task status
2. Check worker logs: `docker compose logs worker`
3. Verify Redis is running: `docker compose ps redis`
4. Retry task manually if needed

### Token Refresh Loop

**Cause**: Refresh token expired or invalidated.

**Solution**: Clear browser storage and re-login:
```javascript
sessionStorage.clear();
localStorage.clear();
window.location.href = '/login';
```

---

## Environment Variables

### Required

```bash
SECRET_KEY=<random-50-chars>
DEBUG=False
PLATFORM_DOMAIN=learnpuddle.com
DB_NAME=learnpuddle_db
DB_USER=learnpuddle
DB_PASSWORD=<strong-password>
REDIS_PASSWORD=<strong-password>
```

### Optional

```bash
# Storage (default: local)
STORAGE_BACKEND=s3
STORAGE_ACCESS_KEY=
STORAGE_SECRET_KEY=
STORAGE_BUCKET=
STORAGE_ENDPOINT=

# Email (default: console)
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.resend.com
EMAIL_HOST_PASSWORD=<api-key>

# LLM for quiz generation
LLM_PROVIDER=auto
OPENROUTER_API_KEY=
OLLAMA_BASE_URL=http://localhost:11434

# Monitoring
SENTRY_DSN=
```

---

## Deployment

### Production Checklist

- [ ] `DEBUG=False`
- [ ] Strong `SECRET_KEY` (50+ random chars)
- [ ] HTTPS enforced (via Cloudflare or nginx)
- [ ] Database backups configured
- [ ] Redis persistence enabled
- [ ] Celery worker running
- [ ] Static files collected
- [ ] Email backend configured

### Deploy Commands

```bash
# On server
cd /opt/lms
git pull

# Rebuild and restart
docker compose -f docker-compose.prod.yml build --no-cache web frontend
docker compose -f docker-compose.prod.yml run --rm web python manage.py migrate
docker compose -f docker-compose.prod.yml run --rm -u root web python manage.py collectstatic --noinput
docker compose -f docker-compose.prod.yml up -d
```

See `docs/DEPLOY_FROM_SCRATCH.md` for full deployment guide.

---

## API Versioning

- Current version: `v1`
- Base URL: `/api/v1/`
- Backward compatibility: `/api/` mirrors `/api/v1/`
- API docs (dev only): `/api/docs/` (Swagger), `/api/redoc/`

---

## Feature Flags

Tenant features are stored in `Tenant.features` (JSONField):

```python
# Check in view
if request.tenant.features.get("certificates"):
    # Feature enabled

# Check in decorator
@check_feature("certificates")
def certificate_view(request):
    pass
```

Common features: `certificates`, `groups`, `reminders`, `sso`, `2fa`, `custom_domain`

---

## Contact & Support

- Repository: https://github.com/thebrainpuddle-dev/learnpuddle-lms
- Issues: Use GitHub Issues for bug reports
- Docs: See `/docs/` folder for additional documentation
