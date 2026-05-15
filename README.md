# LearnPuddle LMS

A modern, multi-tenant Learning Management System built with Django and React.

![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![Django](https://img.shields.io/badge/Django-5.0-green.svg)
![React](https://img.shields.io/badge/React-18-61dafb.svg)
![TypeScript](https://img.shields.io/badge/TypeScript-5.0-3178c6.svg)
![License](https://img.shields.io/badge/License-Private-red.svg)

## Features

### Multi-Tenant Architecture
- **Subdomain-based isolation** - Each school/organization gets their own subdomain
- **Custom branding** - Tenant-specific logos, colors, and fonts
- **Data isolation** - Complete separation of tenant data

### Admin Dashboard
- 📊 **Analytics & Reports** - Course completion rates, assignment status
- 👥 **Teacher Management** - Create, organize teachers into groups
- 📚 **Course Management** - Create courses with modules and content
- 📝 **Assignment Management** - Create and track assignments
- 🔔 **Reminders** - Send bulk or targeted email/in-app notifications
- ⚙️ **Settings** - Customize branding and tenant settings

### Teacher Portal
- 📖 **My Courses** - View assigned courses and track progress
- ▶️ **Content Player** - Watch videos, read documents, complete lessons
- 📋 **Assignments** - View and submit assignments
- 🔔 **Notifications** - Real-time notification bell with unread count
- 👤 **Profile** - Manage profile and preferences

### Technical Features
- 🔐 **JWT Authentication** - Secure token-based auth with refresh
- 🎨 **Dynamic Theming** - CSS variables for tenant-specific styling
- 📱 **Responsive Design** - Works on desktop and mobile
- 🔄 **Real-time Updates** - React Query for data fetching and caching
- 🍞 **Toast Notifications** - User feedback for all actions

## Tech Stack

### Backend
- **Framework:** Django 5.0 + Django REST Framework
- **Database:** PostgreSQL
- **Authentication:** Simple JWT
- **Task Queue:** (Ready for Celery integration)

### Frontend
- **Framework:** React 18 with TypeScript
- **Styling:** Tailwind CSS
- **State Management:** Zustand
- **Data Fetching:** TanStack Query (React Query)
- **Icons:** Heroicons
- **Routing:** React Router DOM v6

## Project Structure

```
brain-lms/
├── backend/
│   ├── apps/
│   │   ├── tenants/        # Multi-tenancy
│   │   ├── users/          # Authentication & users
│   │   ├── courses/        # Course management
│   │   ├── progress/       # Teacher progress tracking
│   │   ├── notifications/  # In-app notifications
│   │   ├── reminders/      # Email reminders
│   │   ├── reports/        # Analytics & reports
│   │   └── uploads/        # File uploads
│   ├── config/             # Django settings
│   ├── utils/              # Shared utilities
│   └── requirements.txt
│
├── frontend/
│   ├── src/
│   │   ├── components/     # Reusable UI components
│   │   ├── pages/          # Page components
│   │   ├── services/       # API services
│   │   ├── stores/         # Zustand stores
│   │   └── config/         # App configuration
│   ├── public/
│   └── package.json
│
└── README.md
```

## Getting Started

### Prerequisites
- Python 3.11+
- Node.js 18+
- PostgreSQL 14+
- Docker (optional, for database)

### Backend Setup

1. **Navigate to backend directory:**
   ```bash
   cd backend
   ```

2. **Create virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables:**
   ```bash
   cp .env.example .env
   # Edit .env with your database credentials
   ```

5. **Start PostgreSQL (using Docker):**
   ```bash
   docker-compose up -d
   ```

6. **Run migrations:**
   ```bash
   python manage.py migrate
   ```

7. **Create demo tenant:**
   ```bash
   python manage.py create_demo_tenant
   ```

8. **Start the server:**
   ```bash
   python manage.py runserver 0.0.0.0:8000
   ```

### Frontend Setup

1. **Navigate to frontend directory:**
   ```bash
   cd frontend
   ```

2. **Install dependencies:**
   ```bash
   npm install
   ```

3. **Start development server:**
   ```bash
   npm start
   ```

4. **Open in browser:**
   ```
   http://localhost:3000
   ```

### Demo Credentials

After running `create_demo_tenant`, configure test login credentials via environment variables:
- `DEMO_TENANT_ADMIN_EMAIL`
- `DEMO_TENANT_ADMIN_PASSWORD`

## API Endpoints

### Authentication
- `POST /api/users/auth/login/` - Login
- `POST /api/users/auth/refresh/` - Refresh token
- `POST /api/users/auth/logout/` - Logout

### Courses (Admin)
- `GET /api/courses/` - List courses
- `POST /api/courses/` - Create course
- `GET /api/courses/{id}/` - Get course details
- `PATCH /api/courses/{id}/` - Update course
- `DELETE /api/courses/{id}/` - Delete course

### Teacher Portal
- `GET /api/teacher/dashboard/` - Dashboard stats
- `GET /api/teacher/courses/` - My courses
- `GET /api/teacher/courses/{id}/` - Course details
- `POST /api/teacher/progress/` - Mark content complete
- `GET /api/teacher/assignments/` - My assignments
- `POST /api/teacher/assignments/{id}/submit/` - Submit assignment

### Notifications
- `GET /api/notifications/` - List notifications
- `GET /api/notifications/unread-count/` - Unread count
- `POST /api/notifications/{id}/read/` - Mark as read
- `POST /api/notifications/mark-all-read/` - Mark all read

## Environment Variables

### Backend (.env)
```env
SECRET_KEY=your-secret-key
DEBUG=True
DATABASE_URL=postgres://user:pass@localhost:5432/brain_lms
ALLOWED_HOSTS=localhost,127.0.0.1
```

### Frontend (.env.development)
```env
REACT_APP_API_URL=http://localhost:8000/api
```

## Deployment

### Production Checklist
- [ ] Set `DEBUG=False`
- [ ] Configure proper `ALLOWED_HOSTS`
- [ ] Set up SSL/HTTPS
- [ ] Configure production database
- [ ] Set up static file serving (nginx/CDN)
- [ ] Configure email backend for reminders
- [ ] Set up media storage (S3/CDN)

## CI/CD (GitHub Actions)

Pipeline file: `.github/workflows/ci.yml`

### Branch behavior
- `develop` push:
  - backend/frontend tests
  - staging images build + push
  - staging deploy over SSH
- `main` push:
  - backend/frontend tests
  - production images build + push
  - production deploy over SSH

### Required GitHub secrets

#### Production
- `DEPLOY_HOST`
- `DEPLOY_USER`
- `DEPLOY_SSH_KEY`
- `DEPLOY_PORT` (optional, defaults to `22`)

#### Staging
- `STAGING_HOST`
- `STAGING_USER`
- `STAGING_SSH_KEY`
- `STAGING_PORT` (optional, defaults to `22`)

### Deployment execution model
Deploy jobs use native OpenSSH (not `appleboy/ssh-action`) for reliability:
1. Start SSH agent with private key.
2. Pin host key with `ssh-keyscan` into `~/.ssh/known_hosts`.
3. Run remote deploy script via `ssh ... 'bash -se'`:
   - pull CI-built `backend:$SHA` and `nginx:$SHA` images from GHCR
   - tag them locally as `lms-backend:latest` and `lms-nginx:latest`
   - `docker compose pull db redis`
   - start `db` + `redis`
   - run `migrate`
   - run `collectstatic`
   - restart stack
   - run origin health check script

Production deploys should not build backend or frontend/nginx images on the droplet during the normal CI path. The droplet should only pull immutable CI-built images, run migrations/static collection, restart, and health-check.

### Troubleshooting

#### Error: `ssh: unexpected packet in response to channel open: <nil>`
This commonly appears with `drone-ssh`/`appleboy/ssh-action` in some server + SSH configurations.

Mitigation in this repo:
- CI now uses native `ssh` from the runner with:
  - `BatchMode=yes`
  - `StrictHostKeyChecking=yes`
  - `ServerAliveInterval=30`
  - `ServerAliveCountMax=3`

If deploy still fails:
1. Verify host/user/key/port secrets.
2. Confirm key format is valid OpenSSH private key.
3. Validate server key exchange manually from a local terminal:
   ```bash
   ssh -p <PORT> <USER>@<HOST> "echo ok"
   ```
4. Check server auth and SSH daemon logs (`/var/log/auth.log`).
5. Ensure no forced-login banner or shell startup script blocks non-interactive SSH commands.

### Manual deploy (fallback)
If CI deploy is blocked, run this on the target server:
```bash
cd /opt/lms
NEW_SHA=<commit-sha-to-deploy>
REGISTRY=ghcr.io/thebrainpuddle-dev/learnpuddle-lms

# Requires a GHCR token/user with read access to the repo packages.
docker login ghcr.io
docker pull "${REGISTRY}/backend:${NEW_SHA}"
docker tag "${REGISTRY}/backend:${NEW_SHA}" lms-backend:latest
docker pull "${REGISTRY}/nginx:${NEW_SHA}"
docker tag "${REGISTRY}/nginx:${NEW_SHA}" lms-nginx:latest
docker compose -f docker-compose.prod.yml pull db redis
docker compose -f docker-compose.prod.yml up -d db redis
docker compose -f docker-compose.prod.yml run --rm -T web python manage.py migrate --noinput
docker compose -f docker-compose.prod.yml run --rm -T -u root web python manage.py collectstatic --noinput
docker compose -f docker-compose.prod.yml up -d --remove-orphans
./scripts/check-origin-health.sh docker-compose.prod.yml learnpuddle.com
```

## Contributing

This is a private repository. Please contact the maintainers for contribution guidelines.

## License

Private - All rights reserved.

---

Built with ❤️ using Django and React
