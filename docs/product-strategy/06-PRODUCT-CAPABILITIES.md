# LearnPuddle — Product Capabilities (What's Built Today)

---

## Architecture

| Layer | Technology |
|-------|-----------|
| Backend | Django 5.2 + Django REST Framework |
| Frontend | React 19 + TypeScript + Tailwind CSS |
| Database | PostgreSQL 15 (multi-tenant, shared DB) |
| Cache/Queue | Redis 7 |
| Background Jobs | Celery 5.3 + Celery Beat |
| Video | ffmpeg + HLS adaptive streaming |
| Speech-to-Text | faster-whisper (OpenAI Whisper) |
| Storage | Local FS / S3 (MinIO / DO Spaces / AWS S3) |
| Auth | SimpleJWT + Google OAuth2 + TOTP 2FA |
| Payments | Stripe |
| State Management | Zustand |
| Data Fetching | TanStack Query (React Query) |
| Monitoring | Prometheus + Django health checks |
| Containers | Docker + Docker Compose |
| Reverse Proxy | Nginx 1.25 |
| Production | DigitalOcean + Cloudflare |

---

## Backend Apps (13 Total)

| App | Purpose |
|-----|---------|
| **tenants** | Multi-tenancy, plans, feature flags, SSO config, custom domains |
| **users** | Auth (email + JWT), roles, soft-delete, SSO, 2FA/TOTP, invitations |
| **courses** | Course → Module → Content hierarchy, learning paths, search |
| **progress** | Progress tracking, assignments, quizzes, skills, certifications, gamification |
| **notifications** | In-app notifications, auto-archival (90 days), cleanup tasks |
| **reminders** | Bulk email/in-app reminders (manual + automated campaigns) |
| **reports** | Completion reports, assignment reports, CSV export |
| **billing** | Stripe subscriptions, payment history, webhook processing |
| **media** | File uploads, CDN-ready storage, quota management |
| **uploads** | Transient file handling (thumbnails, documents) |
| **discussions** | Thread-based forums on courses (likes, replies, subscriptions) |
| **webhooks** | Stripe + external service integrations |
| **ops** | Health checks, incidents, maintenance scheduling, dead letter queue |

---

## Feature Inventory

### Multi-Tenancy & Platform

| Feature | Status |
|---------|--------|
| Subdomain-based tenant isolation | Production |
| Per-tenant branding (logo, colors, fonts) | Production |
| 5 user roles (Super Admin, School Admin, Teacher, HOD, IB Coordinator) | Production |
| Feature flags per tenant | Production |
| Plan-based limits (teachers, courses, storage) | Production |
| Custom domain support | Built |
| Tenant soft-delete with audit trail | Production |
| Super Admin portal (manage all tenants) | Production |

### Course & Content Management

| Feature | Status |
|---------|--------|
| Course → Module → Content hierarchy | Production |
| Content types: Video, PDF, Documents, Text | Production |
| Course publish/draft workflow | Production |
| Mandatory courses with deadlines | Production |
| Course thumbnails with cloud storage | Production |
| Learning paths (sequenced courses) | Built |
| Full-text search | Production |

### Video Pipeline

| Feature | Status |
|---------|--------|
| HLS transcoding (adaptive bitrate) | Production |
| Duration validation (configurable max) | Production |
| Thumbnail auto-generation | Production |
| Speech-to-text transcription (Whisper) | Production |
| VTT captions with click-to-seek | Production |
| Auto-quiz generation from transcript (LLM) | Production |
| Tenant-isolated storage paths | Production |
| HLS.js player with quality selection | Production |
| Transcript panel with timing sync | Production |
| Progress tracking (seconds watched) | Production |

### Assignments & Quizzes

| Feature | Status |
|---------|--------|
| Reflection assignments (text submission) | Production |
| Quiz assignments (MCQ + short answer) | Production |
| Auto-generated quizzes from video transcripts | Production |
| Manual quiz creation by admin | Production |
| Due dates with deadline enforcement | Production |
| Passing score thresholds | Production |
| Score tracking and export | Production |

### Gamification

| Feature | Status |
|---------|--------|
| XP system with configurable point values | Production |
| 5 badge categories (milestone, streak, completion, skill, special) | Production |
| 5 criteria types (XP threshold, courses completed, streak days, etc.) | Production |
| Streak tracking with freeze mechanics (2/month) | Production |
| Leaderboards (weekly, monthly, all-time) | Production |
| 10 proficiency levels (Associate Educator → Master Educator) | Production |
| Daily quests | Production |
| Opt-out and anonymization options | Production |
| Immutable XP transaction ledger | Production |

### Skills & Certifications

| Feature | Status |
|---------|--------|
| Custom skills per tenant (name, category, proficiency 1-5) | Production |
| Skills mapped to courses (which level each course teaches) | Production |
| Teacher skill progress tracking | Production |
| Skill gap analysis | Production |
| Skills matrix heatmap visualization | Production |
| Certificate templates | Production |
| PDF certificate generation | Production |
| Certificate tracking and download | Production |

### Authentication & Security

| Feature | Status |
|---------|--------|
| Email + password authentication | Production |
| JWT tokens (15min access, 7-day refresh) | Production |
| Token rotation and blacklist | Production |
| Google SSO (OAuth2/OIDC) | Production |
| TOTP 2FA (authenticator apps) | Production |
| Per-tenant SSO enforcement | Production |
| Teacher invitation system (bulk email) | Production |
| Password reset flow | Production |

### Notifications & Reminders

| Feature | Status |
|---------|--------|
| In-app notifications (5 types) | Production |
| Read status tracking | Production |
| Auto-archival (90 days) | Production |
| Auto-deletion (30 days after archive) | Production |
| Manual reminder campaigns (email + in-app) | Production |
| Automated reminders (deadline/assignment triggers) | Production |
| Delivery tracking (pending → sent → failed) | Production |

### Reports & Analytics

| Feature | Status |
|---------|--------|
| Course completion reports | Production |
| Assignment submission reports | Production |
| Engagement metrics (active users, avg completion time) | Production |
| Chart.js visualizations (bar, line, pie, donut) | Production |
| Completion trends over time | Production |
| CSV export | Production |
| Manager dashboard (department-level visibility) | Production |

### Billing & Subscriptions

| Feature | Status |
|---------|--------|
| 4 plan tiers (Free, Starter, Pro, Enterprise) | Production |
| Stripe customer + subscription creation | Production |
| Monthly/yearly billing toggle | Production |
| Payment history tracking | Production |
| Invoice management | Production |
| Webhook handling (6 event types) | Production |
| Trial period support | Production |
| Cancel + reactivate workflows | Production |
| Plan change preview (proration) | Production |

### Discussions

| Feature | Status |
|---------|--------|
| Thread-based discussions on courses | Production |
| Replies and nested threads | Production |
| Likes | Production |
| Subscriptions (follow threads) | Production |

### Mobile & PWA

| Feature | Status |
|---------|--------|
| Web App Manifest (standalone display) | Production |
| App shortcuts (Courses, Dashboard) | Production |
| Install prompts (workbox) | Production |
| Update detection + prompts | Production |
| Responsive design (Tailwind mobile-first) | Production |
| Installable on Chrome/Android + iOS | Production |

### Operations & Monitoring

| Feature | Status |
|---------|--------|
| Health checks (liveness + readiness) | Production |
| Incident tracking | Built |
| Maintenance scheduling | Built |
| Dead letter queue (failed task recovery) | Built |
| Audit logging | Production |

---

## Frontend Pages (30+)

### Public/Marketing
- Product Landing Page
- School Signup (onboarding)

### Authentication (7 pages)
- Tenant Login, Super Admin Login
- Forgot Password, Reset Password
- Email Verification, SSO Callback
- Accept Invitation

### Super Admin Portal (5 pages)
- Platform Dashboard, Schools List, School Detail
- Operations Center, Demo Bookings

### Admin Portal (15+ pages)
- Dashboard, Courses List, Course Editor (nested)
- Teachers Management, Create Teacher, Groups
- Reminders, Announcements, Reports, Analytics
- Skills Matrix, Gamification Settings, Certifications
- Media Library, Billing, Settings, Security

### Learner Portal (8+ pages)
- Dashboard (XP, badges, streak, courses)
- My Courses, Course Viewer (video + transcript)
- Assignments, Quiz Page
- Profile, Skills Matrix, Gamification
- Manager Dashboard (for HOD/Coordinator)

---

## Deployment

| Environment | Stack |
|------------|-------|
| Local Dev | Docker Compose (6 services) |
| Production | Docker Compose + Nginx + Cloudflare |
| Server | DigitalOcean Droplet (Singapore, $12-26/mo) |
| Storage | DO Spaces (SGP1) + CDN |
| Email | Resend (SMTP) |
| CI/CD | GitHub Actions |
| DNS | Cloudflare (wildcard *.learnpuddle.com) |

**Current capacity**: Single VPS sufficient for 50+ organizations, thousands of users.
