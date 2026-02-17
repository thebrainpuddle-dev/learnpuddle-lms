# LearnPuddle – Bug Check, Commit & Architecture Pipeline

Pipeline of commands and checks for development, debugging, and deployment.

---

## Phase 1: Pre-Commit Checks

### 1.1 Linting & Formatting

```bash
# Backend
cd backend
black .
isort .
flake8 .

# Frontend
cd frontend
npm run lint
npm run build   # Ensure build succeeds
```

### 1.2 Run Tests

```bash
# Backend unit/integration tests
docker compose exec web pytest -v

# Specific app
docker compose exec web pytest apps/courses/ -v
docker compose exec web pytest apps/users/ -v

# Frontend tests (if configured)
cd frontend && npm test
```

### 1.3 Migration Check

```bash
# Ensure no unapplied migrations
docker compose exec web python manage.py migrate --check

# Show migration status
docker compose exec web python manage.py showmigrations
```

---

## Phase 2: Bug Detection

### 2.1 Backend Logs

```bash
# Live backend logs
docker compose logs -f web

# Last 100 lines
docker compose logs --tail=100 web

# Search for errors
docker compose logs web 2>&1 | grep -i error
```

### 2.2 Frontend Console

- Open DevTools (F12) → Console
- Check for 4xx/5xx in Network tab
- Inspect failed requests (payload, response, headers)

### 2.3 API Debugging

```bash
# Health check
curl -s http://localhost:8000/health/

# Authenticated request (replace TOKEN)
curl -H "Authorization: Bearer TOKEN" \
     -H "Content-Type: application/json" \
     http://localhost:8000/api/v1/courses/

# Tenant resolution (local dev)
curl -H "Host: demo.localhost" http://localhost:8000/api/tenants/theme/
```

### 2.4 Database Verification

```bash
# Django shell
docker compose exec web python manage.py shell_plus

# In shell:
>>> from apps.courses.models import Course
>>> Course.objects.count()
>>> from apps.users.models import User
>>> User.objects.filter(tenant__subdomain='demo').count()
```

### 2.5 Celery / Background Tasks

```bash
# Flower (if running)
open http://localhost:5555

# Worker logs
docker compose logs -f worker
```

---

## Phase 3: Commit Hygiene

### 3.1 Before Committing

```bash
# Status
git status

# Diff
git diff
git diff --staged

# Ensure no secrets
git diff | grep -E "(SECRET|PASSWORD|API_KEY)" || true
```

### 3.2 Commit Message Format

```
<type>: <scope> Brief description

Examples:
fix: courses - resolve assigned_teachers validation errors
fix: users - handle email uniqueness in bulk import
fix: uploads - verify MIME type detection
feat: add skip request flow for mandatory courses
docs: add CLAUDE.md development guide
```

### 3.3 Commit Commands

```bash
# Stage specific files
git add backend/apps/courses/serializers.py
git add backend/apps/courses/views.py

# Commit with message
git commit -m "fix: courses - resolve assigned_teachers validation errors"

# Amend last commit (before push)
git commit --amend -m "fix: courses - resolve assigned_teachers validation"
```

---

## Phase 4: Architecture Review

### 4.1 Directory Structure

```bash
# Backend apps
ls -la backend/apps/

# Frontend pages
ls -la frontend/src/pages/admin/
ls -la frontend/src/pages/teacher/

# Shared utilities
ls -la backend/utils/
```

### 4.2 Key Patterns Checklist

| Pattern | Location | Check |
|---------|----------|-------|
| Tenant isolation | All views | `@tenant_required` + `request.tenant` |
| Admin-only | Admin views | `@admin_only` |
| Serializer context | Course/User serializers | `context={'request': request}` |
| Queryset matching | M2M fields | Matches list endpoint logic |
| FormData uploads | Frontend | No manual `Content-Type` header |

### 4.3 Dependency Graph

```bash
# Backend migrations dependency order
ls backend/apps/*/migrations/*.py | grep -v __init__

# Check for migration conflicts (duplicate numbers)
find backend/apps -name "*.py" -path "*/migrations/*" | xargs -I{} basename {} | sort | uniq -d
```

---

## Phase 5: Deployment Pipeline

### 5.1 Local → Staging (if applicable)

```bash
git checkout main
git pull origin main
git merge fix/your-branch --no-edit
git push origin main
```

### 5.2 Production Deploy (Droplet)

```bash
# SSH in
ssh root@YOUR_DROPLET_IP

# Deploy
cd /opt/lms

git fetch origin main
git reset --hard origin/main

docker compose -f docker-compose.prod.yml run --rm web python manage.py migrate --noinput

docker compose -f docker-compose.prod.yml up -d --build web worker

# Frontend (if changed)
docker compose -f docker-compose.prod.yml build --no-cache frontend
docker compose -f docker-compose.prod.yml run --rm frontend
docker compose -f docker-compose.prod.yml up -d nginx

# Verify
docker compose -f docker-compose.prod.yml ps
curl -s http://localhost/health/
```

### 5.3 Post-Deploy Verification

```bash
# Services up
docker compose -f docker-compose.prod.yml ps

# Health
curl -s https://learnpuddle.com/health/

# Logs
docker compose -f docker-compose.prod.yml logs --tail=50 web
```

---

## Phase 6: Common Bug Fixes Reference

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| "Invalid pk - object does not exist" | Serializer queryset mismatch | Align `assigned_teachers` / `assigned_groups` with list endpoints |
| File upload fails / empty body | Manual `Content-Type: multipart/form-data` | Remove header; let Axios set boundary |
| 403 Tenant / Forbidden | Tenant not resolved | Check Host header, `X-Tenant-Subdomain` |
| Email already exists (bulk) | Global vs tenant check | Use tenant-scoped or clear error message |
| Migration conflict | Duplicate migration numbers | Rename, fix dependencies, remove duplicates |
| Blank white screen | Stale frontend in volume | Rebuild frontend, `run --rm frontend`, restart nginx |

---

## Quick Reference: One-Liners

```bash
# Full local check
cd /opt/lms && black backend/ && docker compose exec web pytest -q

# Deploy to production (on Droplet)
cd /opt/lms && git fetch origin main && git reset --hard origin/main && docker compose -f docker-compose.prod.yml run --rm web python manage.py migrate --noinput && docker compose -f docker-compose.prod.yml up -d --build web worker
```
