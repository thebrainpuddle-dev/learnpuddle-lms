# Brain LMS

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

After running `create_demo_tenant`, you can log in with:

| Role | Email | Password |
|------|-------|----------|
| Admin | admin@demo.com | demo123 |
| Teacher | teacher@demo.com | demo123 |

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

## Contributing

This is a private repository. Please contact the maintainers for contribution guidelines.

## License

Private - All rights reserved.

---

Built with ❤️ using Django and React
