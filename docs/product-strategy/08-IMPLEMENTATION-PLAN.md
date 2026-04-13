# LearnPuddle — Implementation Plan

---

## Executive Summary

Transform LearnPuddle from a school-specific LMS into a **horizontal B2B training platform** serving any organization (schools, gyms, coaching centers, corporates). This plan covers infrastructure migration, UI/UX overhaul, backend generalization, and new feature development across **4 phases over 14-16 weeks**.

**MVP Scope**: 2 personas — **Admin (Owner)** + **Guide (Teacher/Trainer)**. No Student/Parent until Phase 2+.

**Design Direction**: Dark sidebar, glassmorphism cards, gradient accents, animated data viz — inspired by [LearnAI Behance reference](https://www.behance.net/gallery/236530469/AI-E-Learning-SaaS-Educational-Platform-EdtechLMS).

**Infrastructure**: Neon (DB) + Railway (compute) + Cloudflare R2 (storage) + Postmark (email) + Sentry + BetterStack (monitoring).

---

## Table of Contents

1. [Current State Assessment](#1-current-state-assessment)
2. [Target Architecture](#2-target-architecture)
3. [Infrastructure Stack](#3-infrastructure-stack)
4. [UI/UX Design System](#4-uiux-design-system)
5. [Backend Refactoring](#5-backend-refactoring)
6. [Frontend Migration & Redesign](#6-frontend-migration--redesign)
7. [New Feature Implementation](#7-new-feature-implementation)
8. [Vertical Template System](#8-vertical-template-system)
9. [Phase-by-Phase Roadmap](#9-phase-by-phase-roadmap)
10. [Risk Register](#10-risk-register)

---

## 1. Current State Assessment

### What We Have (Reusable)

| Layer | Reusability | Notes |
|-------|------------|-------|
| Multi-tenant architecture | **95%** | Subdomain isolation, TenantManager, context-vars — production-grade |
| Auth system (JWT + SSO + 2FA) | **95%** | Email-based auth, token rotation, blacklist — keep as-is |
| Course → Module → Content hierarchy | **90%** | Core data model is solid, just needs vocabulary abstraction |
| Video pipeline (HLS + transcription + auto-quiz) | **95%** | Unique competitive advantage — keep entirely |
| Gamification engine (XP, badges, streaks, leaderboards) | **90%** | Needs config per vertical, but engine is complete |
| Skills + Certifications | **85%** | Rename some fields, add vertical-specific skill taxonomies |
| Billing (Stripe, 4 tiers) | **90%** | Works as-is, just update plan names/limits |
| Notifications + Reminders | **90%** | Channel abstraction already exists |
| Reports + Analytics | **85%** | Add vertical-specific report templates |
| Discussions | **90%** | Generic enough already |
| PWA (installable) | **100%** | Keep as-is |
| Webhooks | **100%** | Keep as-is |
| Ops monitoring | **100%** | Keep as-is |

### What Needs Changing

| Area | Effort | Description |
|------|--------|-------------|
| **Role system** | Medium | Generalize TEACHER/HOD/IB_COORDINATOR → configurable per vertical |
| **Terminology** | Medium | "Teacher" → "Guide", "School" → "Organization" throughout codebase |
| **User model fields** | Medium | `subjects`, `grades`, `department`, `designation` → generic metadata |
| **Frontend build** | Medium | CRA → Vite migration (CRA is dead, no dark mode support, slow builds) |
| **UI design** | Large | Complete visual overhaul to match Behance-quality design |
| **Infrastructure** | Medium | DigitalOcean → Neon + Railway + R2 |
| **New modules** | Large | Attendance, Schedule, Goal tracking (for gym/corporate verticals) |

### Key Metrics

- **13 Django apps** — 85% reusable
- **30+ frontend pages** — 80% reusable (layout + components change, logic stays)
- **20 UI components** in `/components/ui/` — all need visual update
- **4 Zustand stores** — keep, extend with new vertical config
- **16 API service files** — keep, add new services for new modules
- **9 custom hooks** — keep as-is

---

## 2. Target Architecture

### System Architecture (Post-Migration)

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLOUDFLARE                                │
│  DNS (wildcard *.learnpuddle.com) + CDN + DDoS + WAF            │
│  R2 Storage (media, videos, certificates)                        │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────┴──────────────────────────────────────┐
│                        RAILWAY                                   │
│                                                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐            │
│  │  Django API  │  │ Celery      │  │ Celery Beat  │            │
│  │  (Gunicorn)  │  │ Worker(s)   │  │ (Scheduler)  │            │
│  │  Port 8000   │  │             │  │              │            │
│  └──────┬───────┘  └──────┬──────┘  └──────┬───────┘            │
│         │                 │                │                     │
│  ┌──────┴─────────────────┴────────────────┴───────┐            │
│  │                  Railway Redis                    │            │
│  │            (Cache + Celery Broker)                │            │
│  └───────────────────────────────────────────────────┘            │
│                                                                  │
│  ┌─────────────┐                                                │
│  │  React SPA   │  (Static build served via Cloudflare Pages    │
│  │  (Vite)      │   or Railway static service)                  │
│  └─────────────┘                                                │
└──────────────────────────────────────────────────────────────────┘
                           │
┌──────────────────────────┴──────────────────────────────────────┐
│                         NEON                                     │
│  PostgreSQL 16 (Serverless, autoscaling, branching)              │
│  Main branch: production                                         │
│  Dev branches: per-feature (auto-deleted after merge)            │
└──────────────────────────────────────────────────────────────────┘
```

### Data Flow

```
User (browser/PWA)
  → Cloudflare CDN (static assets)
  → Railway (Django API)
    → Neon PostgreSQL (data)
    → Railway Redis (cache + sessions)
    → Cloudflare R2 (media files via signed URLs)
    → Celery Worker (background: video processing, emails, streaks)
      → Postmark (transactional email)
      → faster-whisper (transcription)
      → LLM (quiz generation)
```

---

## 3. Infrastructure Stack

### Database: Neon (Serverless PostgreSQL)

**Why Neon over Supabase/PlanetScale:**
- Native PostgreSQL (no MySQL translation layer, no PostgREST dependency)
- Database branching for preview environments (like Git branches for DB)
- Autoscaling compute (0 → N, scales to zero when idle)
- Point-in-time restore (built-in, no setup)
- 10GB free tier, then pay-per-use

| Scale | Compute | Storage | Monthly Cost |
|-------|---------|---------|-------------|
| MVP (50 tenants) | 0.25 CU | 5 GB | **$0** (free tier) |
| Growth (500 tenants) | 1-2 CU | 25 GB | **$50-100** |
| Scale (5000 tenants) | 4-8 CU | 100 GB | **$200-500** |

**Migration steps:**
1. `pg_dump` existing DigitalOcean PostgreSQL
2. Create Neon project (Singapore region for India latency)
3. `pg_restore` into Neon
4. Update `DATABASE_URL` in Railway env
5. Set up Neon branching for staging/preview

### Compute: Railway

**Why Railway over Render/Fly.io:**
- First-class Docker support (our existing docker-compose translates directly)
- Built-in Redis (no separate service needed)
- Automatic deploys from GitHub
- Private networking between services (API ↔ Redis ↔ Worker)
- Sleep-on-idle for dev environments
- $5/mo hobby plan, then usage-based

| Service | Spec | Monthly Cost |
|---------|------|-------------|
| Django API | 1 vCPU, 1GB RAM | $5-20 |
| Celery Worker | 1 vCPU, 1GB RAM | $5-20 |
| Celery Beat | 0.5 vCPU, 256MB RAM | $2-5 |
| Redis | 256MB | $3-5 |
| **Total** | | **$15-50** |

**At scale (5000 tenants):** Horizontal scaling via Railway replicas → $200-600/mo

### Storage: Cloudflare R2

**Why R2 over S3/DO Spaces:**
- **Zero egress fees** — video streaming costs nothing for bandwidth
- S3-compatible API (drop-in replacement for boto3)
- Built-in CDN via Cloudflare network
- $0.015/GB/month storage (vs S3's $0.023)

| Scale | Storage | Bandwidth | Monthly Cost |
|-------|---------|-----------|-------------|
| MVP | 50 GB | 500 GB | **$0.75** |
| Growth | 500 GB | 5 TB | **$7.50** |
| Scale | 5 TB | 50 TB | **$75** |

**Migration steps:**
1. Install `django-storages` with S3 backend (already have this)
2. Configure R2 credentials (S3-compatible)
3. Migrate existing media via `rclone sync`
4. Update `STORAGE_ENDPOINT` to R2

### Email: Postmark

**Why Postmark over Resend/SES:**
- 99%+ inbox delivery rate (best in class)
- Dedicated IP included at scale
- Message streams (separate transactional from marketing)
- $15/mo for 10K emails, $85/mo for 50K

| Type | Examples | Volume |
|------|----------|--------|
| Transactional | Password reset, invitation, verification | ~500/mo at MVP |
| Notification | Assignment due, course assigned, reminders | ~5K/mo at 500 tenants |
| Marketing | Onboarding drip, feature announcements | ~1K/mo |

### Monitoring: Sentry + BetterStack

| Tool | Purpose | Cost |
|------|---------|------|
| **Sentry** | Error tracking, performance monitoring, session replay | Free tier (5K events/mo) → $26/mo |
| **BetterStack** | Uptime monitoring, status page, log aggregation | Free tier → $24/mo |
| **Railway Metrics** | CPU, memory, request count, latency | Included |
| **Neon Dashboard** | Query performance, connection count, storage | Included |

### CI/CD: GitHub Actions

```yaml
# .github/workflows/deploy.yml
on:
  push:
    branches: [main]

jobs:
  test:
    - Run pytest (backend)
    - Run vitest (frontend)
    - Run type-check (tsc --noEmit)
    - Run lint (ruff + eslint)

  deploy:
    needs: test
    - Railway deploy (auto via GitHub integration)
    - Neon migration (via django migrate)
    - Cloudflare Pages deploy (frontend build)
```

### Total Infrastructure Cost

| Scale | Neon | Railway | R2 | Postmark | Monitoring | Total |
|-------|------|---------|-----|----------|-----------|-------|
| **MVP** (50 tenants) | $0 | $15 | $1 | $0 | $0 | **$16/mo** |
| **Growth** (500 tenants) | $75 | $50 | $8 | $15 | $26 | **$174/mo** |
| **Scale** (5000 tenants) | $350 | $400 | $75 | $85 | $50 | **$960/mo** |

Compare with current DigitalOcean: $12-26/mo for single VPS (no redundancy, no auto-scaling, manual ops).

---

## 4. UI/UX Design System

### Design Direction (Behance Reference Analysis)

Based on the [LearnAI E-Learning SaaS](https://www.behance.net/gallery/236530469/AI-E-Learning-SaaS-Educational-Platform-EdtechLMS) reference, the design language is:

#### Visual Identity

| Element | Specification |
|---------|--------------|
| **Layout** | Dark sidebar (fixed) + light content area, top header bar |
| **Cards** | Glassmorphism (translucent, backdrop-blur, subtle border) |
| **Colors** | Deep navy/slate sidebar, gradient accent buttons, muted content backgrounds |
| **Typography** | Inter (already using) — clean, modern, high readability |
| **Borders** | Rounded-2xl (16px), soft shadows, no hard edges |
| **Data Viz** | Gradient area charts, donut/ring progress, animated counters |
| **Icons** | Lucide React (line icons, consistent stroke width) |
| **Spacing** | Generous whitespace, 24-32px section gaps, 16px card padding |
| **Animations** | Subtle micro-interactions (hover lifts, progress fills, page transitions) |
| **Dark Mode** | Not for MVP — light mode only with dark sidebar |

#### Color System (Design Tokens)

```typescript
// Design tokens — CSS custom properties
const tokens = {
  // Sidebar (dark)
  sidebar: {
    bg: '#0F172A',          // slate-900
    bgHover: '#1E293B',     // slate-800
    text: '#94A3B8',        // slate-400
    textActive: '#FFFFFF',
    accent: '#6366F1',      // indigo-500
    accentGlow: '#818CF8',  // indigo-400
  },

  // Content area (light)
  surface: {
    bg: '#F8FAFC',          // slate-50
    card: '#FFFFFF',
    cardHover: '#F1F5F9',   // slate-100
    border: '#E2E8F0',      // slate-200
    borderSubtle: '#F1F5F9',
  },

  // Typography
  text: {
    primary: '#0F172A',     // slate-900
    secondary: '#475569',   // slate-600
    muted: '#94A3B8',       // slate-400
    inverse: '#FFFFFF',
  },

  // Accents (gradient pairs)
  accent: {
    primary: ['#6366F1', '#8B5CF6'],    // indigo → violet
    success: ['#10B981', '#34D399'],    // emerald
    warning: ['#F59E0B', '#FBBF24'],    // amber
    danger: ['#EF4444', '#F87171'],     // red
    info: ['#3B82F6', '#60A5FA'],       // blue
  },

  // Glassmorphism
  glass: {
    bg: 'rgba(255, 255, 255, 0.7)',
    blur: '12px',
    border: 'rgba(255, 255, 255, 0.2)',
  },

  // Per-tenant (overridable)
  brand: {
    primary: 'var(--brand-primary)',     // from tenant config
    primaryLight: 'var(--brand-primary-light)',
    primaryDark: 'var(--brand-primary-dark)',
  },
};
```

#### Component Design Specifications

**Sidebar (Dark, Fixed)**
```
Width: 280px (expanded) / 72px (collapsed)
Background: #0F172A (slate-900)
Logo area: 72px height, centered
Nav items: 48px height, 16px padding, rounded-xl
Active indicator: 3px left accent bar + bg highlight
Section dividers: 1px slate-700 with 8px label
Bottom section: user avatar, settings, collapse toggle
Transition: width 300ms ease-in-out
```

**Header Bar**
```
Height: 64px
Background: white, border-bottom 1px slate-200
Left: breadcrumb (with chevron separators)
Center: search bar (if applicable)
Right: notifications bell (with badge count), user avatar dropdown
```

**Stat Cards (Dashboard)**
```
Height: auto (content-driven)
Background: white, rounded-2xl, shadow-sm
Padding: 24px
Icon: 48px circle with gradient background
Value: text-3xl font-bold
Label: text-sm text-secondary
Trend: arrow + percentage, green/red
Optional: sparkline chart (bottom)
```

**Data Tables**
```
Header: text-xs uppercase tracking-wide text-muted, border-bottom
Rows: 56px height, hover:bg-slate-50
Cells: text-sm, proper alignment (numbers right-aligned)
Actions: icon buttons (edit, delete, more), appear on hover
Pagination: bottom, centered, rounded buttons
Bulk select: checkbox column, floating action bar
```

**Charts (Dashboard)**
```
Library: Recharts (migrate from Chart.js for React-native animations)
Area charts: gradient fill (primary color, 20% opacity → 0%)
Bar charts: rounded corners (radius: 8px), gradient fill
Donut charts: thick stroke (24px), center label with value
Colors: use accent gradient pairs
Tooltips: glassmorphism style, rounded-xl
Grid: dotted lines, subtle (slate-200)
```

**Forms**
```
Inputs: h-11 (44px), rounded-xl, border slate-200, focus:ring-2 focus:ring-indigo-500
Labels: text-sm font-medium text-slate-700, mb-1.5
Helper text: text-xs text-slate-500, mt-1
Error text: text-xs text-red-500, mt-1
Buttons: h-11, rounded-xl, font-medium
  Primary: gradient indigo→violet, white text, hover:shadow-lg
  Secondary: white bg, slate-200 border, hover:bg-slate-50
  Danger: gradient red→rose, white text
```

**Modals/Dialogs**
```
Backdrop: bg-black/50, backdrop-blur-sm
Container: max-w-lg, rounded-2xl, shadow-2xl
Header: px-6 py-4, border-bottom, text-lg font-semibold
Body: px-6 py-4
Footer: px-6 py-4, border-top, flex justify-end gap-3
Animation: scale(0.95)→scale(1) + opacity, 200ms
```

**Empty States**
```
Illustration: simple line art or abstract shapes (not heavy illustrations)
Headline: text-lg font-semibold text-slate-800
Description: text-sm text-slate-500, max-w-sm, text-center
CTA: primary gradient button
```

#### Page Layouts

**Dashboard (Admin)**
```
┌──────────────────────────────────────────────────────────────┐
│ Header: "Welcome back, [Name]" + date/time                   │
├──────────────────────────────────────────────────────────────┤
│ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐                        │
│ │People│ │Courses│ │Active│ │Compl.│  ← 4 stat cards        │
│ │ 124  │ │  18  │ │ 89%  │ │ 67%  │                        │
│ └──────┘ └──────┘ └──────┘ └──────┘                        │
├──────────────────────────┬───────────────────────────────────┤
│ Engagement Trends        │ Course Completion                 │
│ [area chart, 7-30 days]  │ [donut chart, by course]         │
│                          │                                   │
├──────────────────────────┴───────────────────────────────────┤
│ Recent Activity                                              │
│ [timeline with avatars, actions, timestamps]                 │
├──────────────────────────────────────────────────────────────┤
│ Top Performers            │ Upcoming Deadlines               │
│ [leaderboard, top 5]      │ [list with countdown badges]    │
└──────────────────────────────────────────────────────────────┘
```

**Dashboard (Guide/Learner)**
```
┌──────────────────────────────────────────────────────────────┐
│ Header: "Good morning, [Name]" + streak/XP bar               │
├──────────────────────────────────────────────────────────────┤
│ ┌──────────────────────┐ ┌────────────────────────────────┐ │
│ │ Daily Quest           │ │ My Progress Ring               │ │
│ │ [3 quest items]       │ │ [circular progress + level]    │ │
│ │ [XP rewards]          │ │ [badges earned]                │ │
│ └──────────────────────┘ └────────────────────────────────┘ │
├──────────────────────────────────────────────────────────────┤
│ Continue Learning                                            │
│ ┌────────┐ ┌────────┐ ┌────────┐                           │
│ │Course 1│ │Course 2│ │Course 3│  ← horizontal scroll      │
│ │[thumb] │ │[thumb] │ │[thumb] │                           │
│ │[prog%] │ │[prog%] │ │[prog%] │                           │
│ └────────┘ └────────┘ └────────┘                           │
├──────────────────────────────────────────────────────────────┤
│ Upcoming Assignments     │ Skill Progress                    │
│ [cards with due dates]   │ [radar chart or bar segments]    │
└──────────────────────────────────────────────────────────────┘
```

### Design System File Structure

```
frontend/src/
├── design-system/
│   ├── tokens/
│   │   ├── colors.ts           # Color palette + semantic colors
│   │   ├── typography.ts       # Font sizes, weights, line heights
│   │   ├── spacing.ts          # Spacing scale
│   │   ├── shadows.ts          # Shadow definitions
│   │   └── index.ts            # Barrel export
│   ├── components/             # Upgraded UI components
│   │   ├── Button.tsx
│   │   ├── Card.tsx
│   │   ├── Input.tsx
│   │   ├── Select.tsx
│   │   ├── Dialog.tsx
│   │   ├── DataTable.tsx
│   │   ├── Badge.tsx
│   │   ├── Avatar.tsx
│   │   ├── Tooltip.tsx
│   │   ├── Progress.tsx
│   │   ├── Tabs.tsx
│   │   ├── Switch.tsx
│   │   ├── Dropdown.tsx
│   │   ├── Toast.tsx
│   │   ├── Skeleton.tsx
│   │   ├── EmptyState.tsx
│   │   └── StatCard.tsx
│   ├── layout/
│   │   ├── Sidebar.tsx          # Dark sidebar (shared, role-aware)
│   │   ├── Header.tsx           # Top bar (shared)
│   │   ├── PageShell.tsx        # Sidebar + header + content wrapper
│   │   ├── ContentArea.tsx      # Main content with padding/max-width
│   │   └── MobileNav.tsx        # Bottom nav for mobile
│   ├── charts/
│   │   ├── AreaChart.tsx        # Gradient area chart
│   │   ├── DonutChart.tsx       # Ring/donut with center label
│   │   ├── BarChart.tsx         # Rounded bar chart
│   │   └── Sparkline.tsx        # Inline mini chart
│   └── theme/
│       ├── ThemeProvider.tsx     # CSS var injection + tenant branding
│       └── cn.ts                # clsx + tailwind-merge utility
```

---

## 5. Backend Refactoring

### 5.1 Terminology Generalization

The most pervasive change: rename school-specific terms to generic ones.

#### Role Mapping

| Current | Generic | School Vertical | Gym Vertical | Corporate Vertical |
|---------|---------|----------------|-------------|-------------------|
| SUPER_ADMIN | SUPER_ADMIN | (same) | (same) | (same) |
| SCHOOL_ADMIN | ADMIN | Principal | Gym Owner | HR Manager |
| TEACHER | GUIDE | Teacher | Trainer | Employee |
| HOD | LEAD | Head of Dept | Head Trainer | Team Lead |
| IB_COORDINATOR | COORDINATOR | IB Coordinator | Program Coordinator | L&D Coordinator |

**Implementation:**

```python
# apps/users/models.py — Updated role choices
class User(AbstractUser):
    class Role(models.TextChoices):
        SUPER_ADMIN = 'SUPER_ADMIN', 'Super Admin'
        ADMIN = 'ADMIN', 'Admin'                    # was SCHOOL_ADMIN
        GUIDE = 'GUIDE', 'Guide'                    # was TEACHER
        LEAD = 'LEAD', 'Lead'                       # was HOD
        COORDINATOR = 'COORDINATOR', 'Coordinator'  # was IB_COORDINATOR
```

**Data migration:** Rename existing role values in DB:
```python
# Migration
User.objects.filter(role='SCHOOL_ADMIN').update(role='ADMIN')
User.objects.filter(role='TEACHER').update(role='GUIDE')
User.objects.filter(role='HOD').update(role='LEAD')
User.objects.filter(role='IB_COORDINATOR').update(role='COORDINATOR')
```

#### Model Renames

| Current Model | New Model | Changes |
|--------------|-----------|---------|
| TeacherProgress | LearnerProgress | Rename `teacher` FK → `user` FK |
| TeacherGroup | UserGroup | Rename throughout |
| TeacherInvitation | Invitation | Remove "Teacher" prefix |
| TeacherQuestClaim | QuestClaim | Remove "Teacher" prefix |
| TeacherXPSummary | XPSummary | Remove "Teacher" prefix |
| TeacherBadge | UserBadge | Remove "Teacher" prefix |
| TeacherStreak | UserStreak | Remove "Teacher" prefix |
| TeacherSkill | UserSkill | Remove "Teacher" prefix |
| TeacherCertification | UserCertification | Remove "Teacher" prefix |

**Approach:** Use Django's `db_table` Meta option to avoid actual DB table renames:
```python
class LearnerProgress(models.Model):
    class Meta:
        db_table = 'progress_teacherprogress'  # Keep old table name
```

#### Field Renames

| Model | Current Field | New Field | Notes |
|-------|--------------|-----------|-------|
| User | employee_id | member_id | Generic identifier |
| User | subjects | tags | JSON list, vertical-specific meaning |
| User | grades | levels | JSON list, vertical-specific meaning |
| User | department | group_name | Generic grouping |
| User | designation | title | Generic job/role title |
| User | date_of_joining | joined_at | DateField, generic |
| User | teacher_groups | user_groups | M2M rename |
| Course | assigned_teachers | assigned_users | M2M rename |
| Tenant | max_teachers | max_users | Limit field |

**Approach:** Same `db_column` trick to avoid data migration:
```python
member_id = models.CharField(max_length=50, db_column='employee_id', blank=True)
```

### 5.2 Vertical Type System

Add vertical awareness to the Tenant model:

```python
# apps/tenants/models.py — New field
class Tenant(models.Model):
    class VerticalType(models.TextChoices):
        SCHOOL = 'school', 'School / Education'
        GYM = 'gym', 'Gym / Fitness'
        CORPORATE = 'corporate', 'Corporate / Enterprise'
        COACHING = 'coaching', 'Coaching Center'
        GENERIC = 'generic', 'Generic Training'

    vertical_type = models.CharField(
        max_length=20,
        choices=VerticalType.choices,
        default=VerticalType.GENERIC,
    )
```

### 5.3 Terminology Configuration System

Instead of hardcoding "Teacher" or "Student" in the backend, store vocabulary per tenant:

```python
# apps/tenants/models.py — New field on Tenant
class Tenant(models.Model):
    # ... existing fields ...

    vocabulary = models.JSONField(
        default=dict,
        blank=True,
        help_text="Vertical-specific terminology overrides",
    )
    # Example:
    # {
    #   "admin": "Principal",
    #   "guide": "Teacher",
    #   "learner": "Student",        # for Phase 2
    #   "course": "PD Module",
    #   "group": "Department",
    #   "organization": "School",
    # }
```

**Default vocabularies per vertical:**

```python
VERTICAL_DEFAULTS = {
    'school': {
        'admin': 'Principal',
        'guide': 'Teacher',
        'learner': 'Student',
        'course': 'PD Module',
        'group': 'Department',
        'organization': 'School',
        'assignment': 'Assignment',
        'certificate': 'PD Certificate',
    },
    'gym': {
        'admin': 'Gym Owner',
        'guide': 'Trainer',
        'learner': 'Member',
        'course': 'Program',
        'group': 'Class',
        'organization': 'Gym',
        'assignment': 'Workout',
        'certificate': 'Achievement',
    },
    'corporate': {
        'admin': 'HR Manager',
        'guide': 'Instructor',
        'learner': 'Employee',
        'course': 'Training Module',
        'group': 'Team',
        'organization': 'Company',
        'assignment': 'Task',
        'certificate': 'Completion Certificate',
    },
}
```

**API endpoint:** `GET /api/v1/tenants/vocabulary/` — returns merged (defaults + tenant overrides).

**Frontend consumption:** Zustand `tenantStore` loads vocabulary on init, all components reference `vocab.guide` instead of hardcoded "Teacher".

### 5.4 API Endpoint Changes

| Current | New | Notes |
|---------|-----|-------|
| `/api/v1/users/auth/register-teacher/` | `/api/v1/users/auth/register-user/` | Generic user registration |
| `/api/teachers/` | `/api/v1/users/guides/` | List/manage guides |
| `/api/teachers/{id}/` | `/api/v1/users/guides/{id}/` | Guide detail |
| `/api/teachers/bulk-import/` | `/api/v1/users/guides/bulk-import/` | Bulk import |
| `/api/teachers/bulk-action/` | `/api/v1/users/guides/bulk-action/` | Bulk actions |
| `/api/v1/teacher/courses/` | `/api/v1/my/courses/` | Learner's courses |
| `/api/v1/teacher/progress/` | `/api/v1/my/progress/` | Learner's progress |
| `/api/v1/teacher/assignments/` | `/api/v1/my/assignments/` | Learner's assignments |

**Backward compatibility:** Keep old endpoints as aliases for 1 release cycle, then remove.

### 5.5 New Backend Models (Phase 2+)

These are NOT in MVP but planned for vertical expansion:

#### Attendance Model (School + Gym verticals)

```python
class AttendanceRecord(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    date = models.DateField()
    status = models.CharField(choices=[
        ('present', 'Present'),
        ('absent', 'Absent'),
        ('late', 'Late'),
        ('excused', 'Excused'),
    ])
    check_in = models.TimeField(null=True)
    check_out = models.TimeField(null=True)
    notes = models.TextField(blank=True)
    marked_by = models.ForeignKey(User, null=True, related_name='attendance_marked')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['tenant', 'user', 'date']
```

#### Schedule Model (All verticals)

```python
class ScheduleEvent(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    event_type = models.CharField(choices=[
        ('class', 'Class/Session'),
        ('deadline', 'Deadline'),
        ('meeting', 'Meeting'),
        ('custom', 'Custom'),
    ])
    course = models.ForeignKey(Course, null=True, on_delete=models.SET_NULL)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    recurrence_rule = models.CharField(max_length=255, blank=True)  # iCal RRULE
    assigned_users = models.ManyToManyField(User, blank=True)
    location = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey(User, related_name='created_events')
    created_at = models.DateTimeField(auto_now_add=True)
```

#### Goal Model (Gym vertical, extensible)

```python
class Goal(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    goal_type = models.CharField(choices=[
        ('numeric', 'Numeric Target'),
        ('boolean', 'Yes/No Completion'),
        ('streak', 'Streak/Consistency'),
    ])
    target_value = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    current_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    unit = models.CharField(max_length=50, blank=True)  # "kg", "reps", "hours"
    deadline = models.DateField(null=True)
    status = models.CharField(choices=[
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('abandoned', 'Abandoned'),
    ], default='active')
    created_at = models.DateTimeField(auto_now_add=True)
```

---

## 6. Frontend Migration & Redesign

### 6.1 CRA → Vite Migration

**Why migrate:**
- CRA is officially deprecated (no maintenance since 2023)
- Vite: 10-20x faster HMR, native ESM, better TypeScript support
- Vite supports CSS custom properties for dark mode (needed for design system)
- Vite tree-shaking is superior (smaller bundle)

**Migration steps (2-3 days):**

1. **Install Vite + plugins:**
   ```bash
   npm install -D vite @vitejs/plugin-react
   npm uninstall react-scripts
   ```

2. **Create `vite.config.ts`:**
   ```typescript
   import { defineConfig } from 'vite';
   import react from '@vitejs/plugin-react';

   export default defineConfig({
     plugins: [react()],
     server: {
       port: 3000,
       proxy: {
         '/api': 'http://localhost:8000',
       },
     },
     resolve: {
       alias: {
         '@': '/src',
       },
     },
     build: {
       outDir: 'build',
       sourcemap: true,
     },
   });
   ```

3. **Move `public/index.html` → `index.html` (root)**

4. **Replace `REACT_APP_` env vars with `VITE_`** (search & replace)

5. **Update `package.json` scripts:**
   ```json
   {
     "scripts": {
       "dev": "vite",
       "build": "tsc && vite build",
       "preview": "vite preview",
       "test": "vitest"
     }
   }
   ```

6. **Replace `react-scripts test` with `vitest`**

7. **Update path aliases in `tsconfig.json`:**
   ```json
   {
     "compilerOptions": {
       "baseUrl": ".",
       "paths": { "@/*": ["src/*"] }
     }
   }
   ```

### 6.2 Chart Library Migration

**Chart.js → Recharts:**
- Recharts is React-native (no canvas, uses SVG)
- Supports gradient fills, animations, responsive containers natively
- Better integration with React state/transitions
- Smaller bundle for the charts we need

**Affected files:**
- `src/pages/admin/AnalyticsPage.tsx`
- `src/pages/admin/DashboardPage.tsx`
- `src/pages/superadmin/DashboardPage.tsx`
- `src/components/teacher/dashboard/` (various widgets)

### 6.3 Layout Refactoring

**Current:** 3 separate layouts (AdminLayout, TeacherLayout, SuperAdminLayout) with duplicated code.

**Target:** Single `PageShell` component with role-aware sidebar config:

```typescript
// src/design-system/layout/PageShell.tsx
interface PageShellProps {
  children: React.ReactNode;
}

export function PageShell({ children }: PageShellProps) {
  const { user } = useAuthStore();
  const navConfig = getNavConfig(user.role); // role-aware nav items

  return (
    <div className="flex h-screen bg-surface-bg">
      <Sidebar config={navConfig} />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header />
        <main className="flex-1 overflow-y-auto p-6">
          {children}
        </main>
      </div>
    </div>
  );
}
```

**Sidebar navigation config per role:**

```typescript
// Admin sidebar
const adminNav = [
  { icon: LayoutDashboard, label: 'Dashboard', path: '/admin' },
  { icon: Users, label: vocab.guide + 's', path: '/admin/people' },
  { icon: BookOpen, label: vocab.course + 's', path: '/admin/courses' },
  { icon: ClipboardCheck, label: 'Assignments', path: '/admin/assignments' },
  { icon: BarChart3, label: 'Analytics', path: '/admin/analytics' },
  { icon: Trophy, label: 'Gamification', path: '/admin/gamification' },
  { icon: Award, label: 'Certificates', path: '/admin/certificates' },
  { icon: MessageSquare, label: 'Discussions', path: '/admin/discussions' },
  { icon: Bell, label: 'Reminders', path: '/admin/reminders' },
  { icon: Settings, label: 'Settings', path: '/admin/settings' },
];

// Guide sidebar
const guideNav = [
  { icon: LayoutDashboard, label: 'Dashboard', path: '/dashboard' },
  { icon: BookOpen, label: 'My ' + vocab.course + 's', path: '/courses' },
  { icon: ClipboardCheck, label: 'Assignments', path: '/assignments' },
  { icon: Trophy, label: 'Achievements', path: '/achievements' },
  { icon: Target, label: 'Skills', path: '/skills' },
  { icon: User, label: 'Profile', path: '/profile' },
];
```

### 6.4 Page-by-Page Redesign Scope

| Page | Effort | Changes |
|------|--------|---------|
| **Admin Dashboard** | Large | New stat cards, gradient charts, activity feed, redesigned layout |
| **Admin People** (was Teachers) | Medium | New data table design, bulk actions bar, avatar grid view option |
| **Admin Courses** | Medium | Card grid with thumbnails, status badges, progress bars |
| **Admin Course Editor** | Medium | Tab-based editor, inline module editing, drag-drop reorder |
| **Admin Analytics** | Large | Recharts migration, new chart types, date range picker |
| **Admin Settings** | Small | Form styling update, section cards |
| **Admin Gamification** | Medium | XP config cards, badge gallery, streak visualization |
| **Admin Certificates** | Small | Template gallery, preview modal |
| **Guide Dashboard** | Large | Quest cards, progress ring, course carousel, streak widget |
| **Guide Course View** | Medium | Video player redesign, transcript panel, progress sidebar |
| **Guide Assignments** | Medium | Card-based list, submission modal redesign |
| **Guide Quiz** | Small | Question card styling, progress bar |
| **Guide Profile** | Small | Avatar upload, stats display, badge showcase |
| **Login Page** | Medium | Split layout (illustration + form), gradient accent |
| **Onboarding** | Medium | Step wizard with progress indicator |
| **Super Admin** | Small | Minimal changes (internal tool) |

---

## 7. New Feature Implementation

### 7.1 MVP Features (Phase 1-2)

These are needed for the Hyderabad school gig and core platform:

| Feature | Priority | Effort | Notes |
|---------|----------|--------|-------|
| Vocabulary/terminology system | P0 | 3 days | Powers all vertical-specific labels |
| Unified layout (PageShell) | P0 | 3 days | Single sidebar + header for all roles |
| Design system components | P0 | 5 days | All 16 base components restyled |
| Dashboard redesign (Admin) | P0 | 3 days | Stat cards, charts, activity feed |
| Dashboard redesign (Guide) | P0 | 3 days | Quest, progress, courses, streaks |
| People management page | P0 | 2 days | Replaces TeachersPage with generic |
| Course listing redesign | P1 | 2 days | Card grid, filtering, search |
| Reports page redesign | P1 | 2 days | Chart migration, new visualizations |
| Onboarding flow | P1 | 3 days | Guided setup for new tenants |
| Responsive mobile layout | P1 | 3 days | Bottom nav, swipe gestures, touch targets |

### 7.2 Post-MVP Features (Phase 3-4)

| Feature | Vertical | Effort | Notes |
|---------|----------|--------|-------|
| Attendance tracking | School, Gym | 1 week | Check-in/out, daily reports, calendar view |
| Schedule/Timetable | All | 1 week | Calendar widget, recurring events, reminders |
| Goal tracking | Gym | 1 week | Numeric targets, progress charts, milestones |
| Student/Member persona | All | 2 weeks | New role, limited dashboard, parent access |
| Template marketplace | Platform | 2 weeks | Browse, preview, install vertical templates |
| WhatsApp notifications | India | 3 days | Via Twilio/360dialog API |
| Hindi/vernacular UI | India | 1 week | i18n already set up, just need translations |
| Bulk data import wizard | All | 3 days | CSV upload with preview, validation, mapping |

---

## 8. Vertical Template System

### How Templates Work

A "template" is a configuration bundle that customizes the platform for a specific vertical:

```typescript
interface VerticalTemplate {
  id: string;                    // 'school-cbse', 'gym-fitness', 'corporate-compliance'
  name: string;                  // 'CBSE School'
  vertical: VerticalType;        // 'school' | 'gym' | 'corporate' | 'coaching'

  vocabulary: Record<string, string>;  // Role/entity label overrides

  defaultCourses?: CourseTemplate[];   // Pre-built courses to seed
  defaultSkills?: SkillTemplate[];     // Pre-built skill taxonomy
  defaultBadges?: BadgeTemplate[];     // Pre-built badge definitions

  featureFlags: {                      // Which features are enabled
    attendance: boolean;
    schedule: boolean;
    goals: boolean;
    discussions: boolean;
    certificates: boolean;
    gamification: boolean;
  };

  branding: {
    primaryColor: string;
    secondaryColor: string;
    illustration: string;        // Onboarding illustration
  };

  onboardingSteps: string[];     // Ordered setup steps
}
```

### Template Application Flow

```
1. New org signs up → picks vertical (school/gym/corporate/other)
2. System loads vertical template
3. Tenant.vocabulary = template.vocabulary
4. Tenant.vertical_type = template.vertical
5. Seed default courses/skills/badges if template provides them
6. Apply feature flags
7. Apply branding defaults
8. Show vertical-specific onboarding wizard
```

### Day-1 Templates

| Template | Target | Pre-built Content |
|----------|--------|-------------------|
| **CBSE School** | Indian CBSE schools | NEP 2020 PD courses, CBSE pedagogy, ICT skills |
| **IB School** | IB World Schools | IB PYP/MYP/DP frameworks, ATL skills, CAS tracking |
| **Generic School** | Any school | Basic PD structure, classroom management |
| **Fitness Studio** | Gyms, yoga studios | Workout programs, nutrition basics |
| **Corporate L&D** | Mid-size companies | Compliance (POSH, safety), onboarding |
| **Coaching Center** | Test prep, tutoring | Course structure, assignment tracking |

---

## 9. Phase-by-Phase Roadmap

### Phase 1: Foundation (Weeks 1-4)

**Goal:** Infrastructure migration + CRA→Vite + design system + backend generalization

| Week | Tasks | Deliverables |
|------|-------|-------------|
| **W1** | Vite migration, Tailwind config update, design token setup | Frontend builds with Vite, new color system |
| **W1** | Neon DB setup, Railway project creation, R2 bucket setup | Infrastructure provisioned |
| **W2** | Design system components (Button, Card, Input, Select, Dialog, DataTable, Badge, Avatar, Progress, Tabs, Switch, Tooltip, Toast, Skeleton, EmptyState, StatCard) | 16 components built and tested |
| **W2** | Backend role rename (TEACHER→GUIDE, SCHOOL_ADMIN→ADMIN), vocabulary system | New roles, vocabulary API endpoint |
| **W3** | Unified Sidebar + Header + PageShell layout | Single layout system for all roles |
| **W3** | Backend model renames (db_table/db_column approach), API aliases | All "Teacher*" models aliased |
| **W4** | Chart migration (Chart.js → Recharts), chart components | AreaChart, DonutChart, BarChart, Sparkline |
| **W4** | Vertical type + template config system | Tenant.vertical_type, vocabulary defaults |

**Exit criteria:** App runs on Vite, new design system components exist, backend uses generic terms, infrastructure deployed.

### Phase 2: Core Redesign (Weeks 5-8)

**Goal:** Redesign all primary pages with new design system

| Week | Tasks | Deliverables |
|------|-------|-------------|
| **W5** | Admin Dashboard redesign (stat cards, charts, activity feed) | Production-ready admin dashboard |
| **W5** | Login page redesign (split layout, branding) | Beautiful login experience |
| **W6** | Guide Dashboard redesign (quests, progress ring, course carousel) | Production-ready guide dashboard |
| **W6** | People Management page (was TeachersPage) | Generic user management with vocabulary |
| **W7** | Course Listing + Course Editor redesign | Card grid, tab-based editor |
| **W7** | Analytics/Reports page (Recharts, date picker) | New chart visualizations |
| **W8** | Gamification pages (admin settings, guide achievements) | Restyled gamification UI |
| **W8** | Settings, Billing, Certificates pages | Updated form designs |

**Exit criteria:** All primary pages redesigned, app looks like the Behance reference.

### Phase 3: Polish + Vertical (Weeks 9-12)

**Goal:** Mobile responsiveness, onboarding, first vertical template, production hardening

| Week | Tasks | Deliverables |
|------|-------|-------------|
| **W9** | Mobile responsive layout (bottom nav, touch targets) | Full mobile experience |
| **W9** | Onboarding wizard (vertical selection, branding setup, first course) | Guided 5-minute setup |
| **W10** | CBSE School template (vocabulary, default courses, skills) | First complete vertical template |
| **W10** | Production deployment (Railway + Neon + R2 + Cloudflare) | Live on new infrastructure |
| **W11** | Email templates (Postmark), notification redesign | Professional transactional emails |
| **W11** | Monitoring setup (Sentry, BetterStack, health checks) | Full observability |
| **W12** | Performance optimization (lazy loading, bundle splitting, caching) | <2s page load, <100ms API |
| **W12** | Security audit, penetration testing basics | OWASP top 10 verified |

**Exit criteria:** Production-ready on new infra, mobile works, school template live, monitoring active.

### Phase 4: Expansion (Weeks 13-16)

**Goal:** Additional templates, new features, Hyderabad school deployment

| Week | Tasks | Deliverables |
|------|-------|-------------|
| **W13** | Gym/Fitness template (vocabulary, programs, goals concept) | Second vertical ready |
| **W13** | Corporate template (compliance courses, team structure) | Third vertical ready |
| **W14** | Attendance tracking module (backend + frontend) | Attendance for school/gym |
| **W14** | Schedule/Calendar module (backend + frontend) | Calendar for all verticals |
| **W15** | WhatsApp notification integration (India) | Teacher nudges via WhatsApp |
| **W15** | Bulk import wizard (CSV upload with validation) | Easy data migration for clients |
| **W16** | Hyderabad school deployment + customization | First paying customer live |
| **W16** | Documentation, API docs, deployment runbook | Operational documentation |

**Exit criteria:** 3 vertical templates, attendance + schedule modules, first school deployed.

### Milestone Summary

```
Week 4  → Foundation complete (infra + design system + backend generalized)
Week 8  → Core redesign complete (all pages look production-grade)
Week 12 → Production launch (new infra, monitoring, mobile, school template)
Week 16 → Multi-vertical ready (3 templates, new modules, first customer)
```

---

## 10. Risk Register

| Risk | Impact | Probability | Mitigation |
|------|--------|------------|------------|
| **Vite migration breaks existing functionality** | High | Low | Run full test suite before/after, keep CRA branch as rollback |
| **Neon latency from India** | Medium | Medium | Choose Singapore region, enable connection pooling, add Redis caching layer |
| **Railway cold starts affect UX** | Medium | Low | Keep minimum 1 instance warm, use health checks to prevent sleep |
| **Design system takes longer than expected** | Medium | Medium | Start with 8 critical components, add rest incrementally |
| **Backend rename breaks API consumers** | High | Low | Use db_column/db_table aliases, keep old endpoints for 1 cycle |
| **Recharts bundle size** | Low | Low | Tree-shake, lazy-load chart pages |
| **School client has custom requirements** | Medium | High | Build customization as vocabulary/template config, not code forks |
| **Scope creep into Student persona** | High | Medium | Hard scope gate: MVP is Admin + Guide only, Student is Phase 2 |

---

## Appendix A: File Change Map

### Backend Files to Modify

```
backend/
├── apps/
│   ├── tenants/
│   │   ├── models.py              # Add vertical_type, vocabulary fields
│   │   ├── serializers.py         # Add vocabulary serializer
│   │   └── views.py               # Add vocabulary endpoint
│   ├── users/
│   │   ├── models.py              # Rename roles, rename fields (db_column)
│   │   ├── serializers.py         # Update role references
│   │   ├── views.py               # Rename teacher → guide views
│   │   └── urls.py                # Add new URL patterns, keep aliases
│   ├── courses/
│   │   ├── models.py              # Rename assigned_teachers → assigned_users
│   │   ├── serializers.py         # Update field references
│   │   └── views.py               # Update variable names
│   ├── progress/
│   │   ├── models.py              # Rename TeacherProgress → LearnerProgress (db_table)
│   │   ├── serializers.py         # Update references
│   │   └── views.py               # Update variable names
│   └── [all other apps]           # Minor: update "teacher" references in queries
├── utils/
│   ├── decorators.py              # Rename @admin_only → check new role names
│   └── tenant_middleware.py       # No changes needed
└── config/
    └── settings.py                # Update CELERY_BEAT task names
```

### Frontend Files to Create

```
frontend/src/
├── design-system/                 # NEW — entire directory
│   ├── tokens/                    # 5 files
│   ├── components/                # 16 files
│   ├── layout/                    # 5 files
│   ├── charts/                    # 4 files
│   └── theme/                     # 2 files
```

### Frontend Files to Modify

```
frontend/
├── vite.config.ts                 # NEW (replaces react-scripts)
├── index.html                     # MOVE from public/ to root
├── tailwind.config.js             # UPDATE colors, add design tokens
├── src/
│   ├── config/
│   │   ├── api.ts                 # Update env var prefix (REACT_APP_ → VITE_)
│   │   └── theme.ts              # Integrate with new design tokens
│   ├── stores/
│   │   └── tenantStore.ts         # Add vocabulary state
│   ├── types/
│   │   └── index.ts               # Rename Teacher types → Guide types
│   ├── pages/
│   │   ├── admin/                 # All pages — apply new layout + components
│   │   ├── teacher/ → guide/      # Rename directory, update imports
│   │   └── auth/                  # Redesign login page
│   ├── components/
│   │   ├── layout/                # REPLACE with design-system/layout
│   │   ├── ui/                    # REPLACE with design-system/components
│   │   └── teacher/ → guide/      # Rename directory
│   └── services/
│       └── teacherService.ts      # Rename → guideService.ts
```

### Frontend Files to Delete

```
frontend/
├── src/react-app-env.d.ts         # CRA-specific
├── src/reportWebVitals.ts         # CRA-specific (use Sentry instead)
├── src/setupTests.ts              # Replace with vitest setup
└── public/index.html              # Moved to root
```

---

## Appendix B: Database Migration Plan

### Safe Migration Strategy

All renames use Django's `db_column` and `db_table` to avoid destructive migrations:

```python
# Step 1: Add new role values alongside old ones
class Migration(migrations.Migration):
    operations = [
        # Add ADMIN, GUIDE, LEAD, COORDINATOR as valid choices
        migrations.AlterField(
            model_name='user',
            name='role',
            field=models.CharField(max_length=20, choices=[
                ('SUPER_ADMIN', 'Super Admin'),
                ('SCHOOL_ADMIN', 'School Admin'),  # keep old
                ('ADMIN', 'Admin'),                  # add new
                ('TEACHER', 'Teacher'),              # keep old
                ('GUIDE', 'Guide'),                  # add new
                ('HOD', 'HOD'),                      # keep old
                ('LEAD', 'Lead'),                    # add new
                ('IB_COORDINATOR', 'IB Coordinator'),# keep old
                ('COORDINATOR', 'Coordinator'),      # add new
            ]),
        ),
    ]

# Step 2: Data migration — update role values
class Migration(migrations.Migration):
    operations = [
        migrations.RunPython(
            lambda apps, schema_editor: apps.get_model('users', 'User').objects.filter(
                role='SCHOOL_ADMIN'
            ).update(role='ADMIN'),
        ),
        # ... same for TEACHER→GUIDE, HOD→LEAD, IB_COORDINATOR→COORDINATOR
    ]

# Step 3: Remove old role choices
class Migration(migrations.Migration):
    operations = [
        migrations.AlterField(
            model_name='user',
            name='role',
            field=models.CharField(max_length=20, choices=[
                ('SUPER_ADMIN', 'Super Admin'),
                ('ADMIN', 'Admin'),
                ('GUIDE', 'Guide'),
                ('LEAD', 'Lead'),
                ('COORDINATOR', 'Coordinator'),
            ]),
        ),
    ]
```

### Rollback Plan

Every migration has a reverse operation. If any step fails:
1. `python manage.py migrate <app> <previous_migration>`
2. All `db_column`/`db_table` changes are non-destructive (old columns/tables still exist)
3. No data is deleted — only values are updated

---

## Appendix C: Infrastructure Migration Checklist

### Pre-Migration

- [ ] Export full PostgreSQL dump from DigitalOcean
- [ ] Inventory all environment variables
- [ ] List all cron jobs / Celery Beat schedules
- [ ] Document current Nginx configuration
- [ ] Export media files list with sizes
- [ ] Set up Neon project (Singapore region)
- [ ] Set up Railway project with services
- [ ] Set up Cloudflare R2 bucket
- [ ] Set up Postmark account + domain verification
- [ ] Set up Sentry project
- [ ] Set up BetterStack monitors

### Migration Day

- [ ] Put current production in maintenance mode
- [ ] Final `pg_dump` from DigitalOcean
- [ ] `pg_restore` into Neon
- [ ] Verify data integrity (row counts, spot checks)
- [ ] `rclone sync` media to Cloudflare R2
- [ ] Deploy Django to Railway
- [ ] Deploy frontend to Cloudflare Pages (or Railway static)
- [ ] Update DNS (Cloudflare) to point to Railway
- [ ] Verify wildcard SSL (*.learnpuddle.com)
- [ ] Test critical paths (login, course view, video playback)
- [ ] Test background tasks (Celery worker + beat)
- [ ] Monitor error rates for 2 hours
- [ ] Disable maintenance mode

### Post-Migration

- [ ] Keep DigitalOcean running for 7 days (rollback window)
- [ ] Set up Neon daily backups
- [ ] Configure Railway auto-scaling rules
- [ ] Set up BetterStack uptime alerts
- [ ] Configure Sentry alert rules
- [ ] Document new runbook for operations
- [ ] Decommission DigitalOcean after 30 days
