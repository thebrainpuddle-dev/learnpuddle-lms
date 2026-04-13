# Student Portal — Complete Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a full STUDENT role and portal to LearnPuddle LMS — from backend models through frontend pages — with all OpenMAIC features adapted for students, admin/teacher integration for student management, and production deployment on Digital Ocean.

**Architecture:** Extends the existing multi-tenant architecture by adding `STUDENT` as a new role on the User model. Students get their own URL namespace (`/api/v1/student/`), frontend route tree (`/student/*`), layout, and sidebar. Admin manages students. Teachers can view student progress. OpenMAIC features are re-exposed through student-scoped API endpoints that reference the same underlying models (CoursePodcast, StudyNotes, etc.) but enforce student-specific access control.

**Tech Stack:** Django 4.2 + DRF, React 19 + TypeScript + Vite, PostgreSQL 15, Redis 7, Celery, Tailwind CSS, Zustand, React Query, Docker Compose on Digital Ocean.

---

## Table of Contents

1. [Platform Architecture — How Student Fits In](#1-platform-architecture)
2. [Who Creates Students & Enrollment Flow](#2-student-creation--enrollment)
3. [Backend Implementation](#3-backend-implementation)
4. [Frontend Implementation](#4-frontend-implementation)
5. [OpenMAIC Features for Students](#5-openmaic-features-for-students)
6. [Admin Portal — Student Management](#6-admin-portal-student-management)
7. [Teacher Portal — Student Visibility](#7-teacher-portal-student-visibility)
8. [Digital Ocean Deployment](#8-digital-ocean-deployment)
9. [Migration & Data Safety](#9-migration--data-safety)
10. [Testing Strategy](#10-testing-strategy)

---

## 1. Platform Architecture

### Current State (Before Student Portal)

```
┌─────────────────────────────────────────────────────────┐
│                    LEARNPUDDLE LMS                       │
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ SUPER ADMIN  │  │ SCHOOL ADMIN │  │   TEACHER    │  │
│  │   Portal     │  │   Portal     │  │   Portal     │  │
│  │ /super-admin │  │ /admin       │  │ /teacher     │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
│                                                          │
│  Roles: SUPER_ADMIN, SCHOOL_ADMIN, TEACHER, HOD,        │
│         IB_COORDINATOR                                   │
│  No STUDENT role exists.                                 │
└─────────────────────────────────────────────────────────┘
```

### Target State (With Student Portal)

```
┌───────────────────────────────────────────────────────────────────────┐
│                         LEARNPUDDLE LMS                               │
│                                                                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────┐ │
│  │ SUPER ADMIN  │  │ SCHOOL ADMIN │  │   TEACHER    │  │ STUDENT  │ │
│  │   Portal     │  │   Portal     │  │   Portal     │  │  Portal  │ │
│  │ /super-admin │  │ /admin       │  │ /teacher     │  │ /student │ │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └────┬─────┘ │
│         │                  │                  │               │       │
│         │     Manages      │    Views         │   Consumes    │       │
│         │     Schools      │    Student       │   Content     │       │
│         │                  │    Progress      │   Submits     │       │
│         │                  │    + Creates     │   Assignments │       │
│         │                  │    Students      │   Uses MAIC   │       │
│         │                  │    + Assigns     │               │       │
│         │                  │    Courses       │               │       │
│         │                  │                  │               │       │
│  ┌──────┴──────────────────┴──────────────────┴───────────────┴─────┐ │
│  │                    SHARED BACKEND                                │ │
│  │  Django REST Framework + PostgreSQL + Redis + Celery             │ │
│  │  Tenant Isolation: TenantManager auto-filters all queries       │ │
│  │  Auth: JWT + optional 2FA/SSO                                   │ │
│  └──────────────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────────────┘
```

### Role Hierarchy & Access Matrix

| Resource | SUPER_ADMIN | SCHOOL_ADMIN | TEACHER | HOD | STUDENT |
|----------|-------------|--------------|---------|-----|---------|
| Manage Schools | ✅ | ❌ | ❌ | ❌ | ❌ |
| Manage Teachers | ✅ | ✅ | ❌ | ❌ | ❌ |
| **Manage Students** | ✅ | ✅ | ❌ | ❌ | ❌ |
| Create Courses | ✅ | ✅ | ✅ (authoring) | ❌ | ❌ |
| Assign Courses | ✅ | ✅ | ❌ | ❌ | ❌ |
| View Course Content | ✅ | ✅ | ✅ | ✅ | **✅** |
| Submit Assignments | ❌ | ❌ | ✅ | ✅ | **✅** |
| **View Student Progress** | ✅ | ✅ | **✅** | **✅** | ❌ |
| Generate Podcasts | ❌ | ❌ | ✅ | ❌ | ❌ |
| **Listen to Podcasts** | ❌ | ❌ | ✅ | ❌ | **✅** |
| Generate Study Notes | ❌ | ❌ | ✅ | ❌ | ❌ |
| **View Study Notes** | ❌ | ❌ | ✅ | ❌ | **✅** |
| **AI Persona Chat** | ❌ | ❌ | ✅ | ❌ | **✅** |
| **Classroom Collab** | ❌ | ❌ | ✅ | ❌ | **✅** |
| **Interactive Lessons** | ❌ | ❌ | ✅ | ❌ | **✅** |
| **Scenarios** | ❌ | ❌ | ✅ | ❌ | **✅** |
| Gamification | ❌ | ❌ | ✅ | ❌ | **✅** |
| Certificates | ❌ | ❌ | ✅ | ❌ | **✅** |

### Key Design Decisions

1. **Students are tenant-scoped** — just like teachers, each student belongs to exactly one school (tenant).
2. **Courses are shared** — the same Course model serves both teachers and students. Admin assigns courses to either/both.
3. **Separate progress tracking** — `StudentProgress` model parallels `TeacherProgress` (separate table, same schema pattern).
4. **OpenMAIC features are consumption-only for students** — students can listen to podcasts, view notes, chat with personas, join classrooms, but cannot *generate* new podcasts or notes.
5. **Admin manages students** — via the admin portal (create, import, invite, deactivate).
6. **Teachers can view student progress** — read-only dashboards showing student completion and grades.
7. **Student cannot see teacher data** — complete isolation between student and teacher portals.

---

## 2. Student Creation & Enrollment

### Who Can Create Students

| Method | Actor | Endpoint | Notes |
|--------|-------|----------|-------|
| Direct Create | SCHOOL_ADMIN | `POST /api/v1/students/create/` | Single student registration |
| Bulk CSV Import | SCHOOL_ADMIN | `POST /api/v1/students/bulk-import/` | Up to 500 students per CSV |
| Invitation Link | SCHOOL_ADMIN | `POST /api/v1/students/invitations/` | Email invitation with signup link |
| **Self-Registration** | STUDENT | `POST /api/v1/students/register/` | Optional — feature-flagged per tenant |

### Student-Specific User Fields

The existing User model needs minimal changes. Students share base fields (email, name, password, tenant) but have student-specific metadata:

```python
# Added to User model
ROLE_CHOICES = [
    ('SUPER_ADMIN', 'Super Admin'),
    ('SCHOOL_ADMIN', 'School Admin'),
    ('TEACHER', 'Teacher'),
    ('HOD', 'Head of Department'),
    ('IB_COORDINATOR', 'IB Coordinator'),
    ('STUDENT', 'Student'),  # ← NEW
]

# Student-specific fields (on User model, nullable for non-students)
student_id = CharField(max_length=50, blank=True)         # School-assigned student ID
grade_level = CharField(max_length=50, blank=True)        # e.g., "Grade 9", "Year 11"
section = CharField(max_length=50, blank=True)            # e.g., "Section A", "Room 201"
parent_email = EmailField(blank=True)                     # Optional parent contact
enrollment_date = DateField(null=True, blank=True)        # When enrolled
```

### Course Assignment for Students

Reuse the existing Course assignment pattern with a new field:

```python
# On Course model — NEW fields
assigned_students = ManyToManyField('users.User', related_name='student_assigned_courses', blank=True)
assigned_to_all_students = BooleanField(default=False)
# assigned_groups already works for student groups too (TeacherGroup → SchoolGroup rename or add StudentGroup)
```

### Enrollment Flow

```
1. ADMIN creates student account(s)
   → POST /api/v1/students/create/   (direct)
   → POST /api/v1/students/bulk-import/  (CSV)
   → POST /api/v1/students/invitations/  (email invite)

2. ADMIN assigns courses
   → PATCH /api/v1/courses/{id}/  (add to assigned_students or assigned_to_all_students)

3. STUDENT logs in
   → POST /api/users/auth/login/  (portal="tenant")
   → role=STUDENT detected → redirect to /student/dashboard

4. STUDENT views assigned courses
   → GET /api/v1/student/courses/  (filtered by assignment)

5. STUDENT consumes content
   → GET /api/v1/student/courses/{id}/  (course detail + modules + content)
   → POST /api/v1/student/progress/{content_id}/complete/  (mark complete)

6. STUDENT submits assignments
   → GET /api/v1/student/assignments/  (list)
   → POST /api/v1/student/assignments/{id}/submit/  (submit)
   → POST /api/v1/student/quizzes/{id}/submit/  (quiz)
```

---

## 3. Backend Implementation

### 3.1 User Model Changes

**File:** `apps/users/models.py`

```python
# Add to ROLE_CHOICES
('STUDENT', 'Student'),

# Add property
@property
def is_student(self):
    return self.role == 'STUDENT'

# Add student-specific fields
student_id = models.CharField(max_length=50, blank=True, default='')
grade_level = models.CharField(max_length=50, blank=True, default='')
section = models.CharField(max_length=50, blank=True, default='')
parent_email = models.EmailField(blank=True, default='')
enrollment_date = models.DateField(null=True, blank=True)
```

### 3.2 New Decorator

**File:** `utils/decorators.py`

```python
def student_only(view_func):
    """Require STUDENT role."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.user.role != 'STUDENT':
            raise PermissionDenied("Student access only.")
        return view_func(request, *args, **kwargs)
    return wrapper

def student_or_admin(view_func):
    """Require STUDENT, SCHOOL_ADMIN, or SUPER_ADMIN."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.user.role not in ('STUDENT', 'SCHOOL_ADMIN', 'SUPER_ADMIN'):
            raise PermissionDenied()
        return view_func(request, *args, **kwargs)
    return wrapper
```

### 3.3 Course Model Changes

**File:** `apps/courses/models.py`

```python
# On Course model — add student assignment fields
assigned_students = models.ManyToManyField(
    'users.User', related_name='student_assigned_courses', blank=True,
    limit_choices_to={'role': 'STUDENT'}
)
assigned_to_all_students = models.BooleanField(
    default=False, help_text="Assign to all students in tenant"
)
```

### 3.4 Student Progress Model

**File:** `apps/progress/models.py` — add `StudentProgress` model

```python
class StudentProgress(models.Model):
    """Track individual student progress through course content."""
    STATUS_CHOICES = [
        ('NOT_STARTED', 'Not Started'),
        ('IN_PROGRESS', 'In Progress'),
        ('COMPLETED', 'Completed'),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE)
    student = models.ForeignKey('users.User', on_delete=models.CASCADE,
                                related_name='student_progress',
                                limit_choices_to={'role': 'STUDENT'})
    course = models.ForeignKey('courses.Course', on_delete=models.CASCADE)
    content = models.ForeignKey('courses.Content', on_delete=models.CASCADE, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='NOT_STARTED')
    progress_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    last_accessed = models.DateTimeField(auto_now=True)
    video_progress_seconds = models.PositiveIntegerField(default=0)

    objects = TenantManager()
    class Meta:
        db_table = 'student_progress'
        unique_together = [('student', 'course', 'content')]
        indexes = [
            models.Index(fields=['tenant', 'student', 'status']),
            models.Index(fields=['tenant', 'course', 'status']),
        ]
```

### 3.5 URL Structure

**New file:** `apps/courses/student_urls.py`

```python
# Mounted at /api/v1/student/ in config/urls.py
urlpatterns = [
    # Dashboard
    path("dashboard/", student_views.student_dashboard, name="student_dashboard"),
    path("calendar/", student_views.student_calendar, name="student_calendar"),

    # Courses
    path("courses/", student_views.student_course_list, name="student_course_list"),
    path("courses/<uuid:course_id>/", student_views.student_course_detail, name="student_course_detail"),

    # Progress
    path("progress/content/<uuid:content_id>/start/", student_views.student_start_content, name="student_start_content"),
    path("progress/content/<uuid:content_id>/", student_views.student_update_progress, name="student_update_progress"),
    path("progress/content/<uuid:content_id>/complete/", student_views.student_complete_content, name="student_complete_content"),

    # Assignments & Quizzes
    path("assignments/", student_views.student_assignment_list, name="student_assignment_list"),
    path("assignments/<uuid:assignment_id>/submit/", student_views.student_submit_assignment, name="student_submit_assignment"),
    path("assignments/<uuid:assignment_id>/submission/", student_views.student_submission_detail, name="student_submission_detail"),
    path("quizzes/<uuid:assignment_id>/", student_views.student_quiz_detail, name="student_quiz_detail"),
    path("quizzes/<uuid:assignment_id>/submit/", student_views.student_submit_quiz, name="student_submit_quiz"),

    # Certificates
    path("courses/<uuid:course_id>/certificate/", student_views.student_certificate, name="student_certificate"),

    # Interactive Lessons
    path("ai-studio/lessons/<uuid:lesson_id>/", student_views.student_get_lesson, name="student_get_lesson"),
    path("ai-studio/lessons/<uuid:lesson_id>/reflect/", student_views.student_submit_reflection, name="student_submit_reflection"),
    path("ai-studio/lessons/<uuid:lesson_id>/quiz-answer/", student_views.student_submit_quiz_answer, name="student_submit_quiz_answer"),
    path("ai-studio/lessons/<uuid:lesson_id>/progress/", student_views.student_update_lesson_progress, name="student_update_lesson_progress"),

    # Scenarios
    path("ai-studio/scenarios/<uuid:scenario_id>/", student_views.student_get_scenario, name="student_get_scenario"),
    path("ai-studio/scenarios/<uuid:scenario_id>/attempt/", student_views.student_submit_scenario_attempt, name="student_submit_scenario_attempt"),

    # ─── OpenMAIC: Podcasts (read-only) ───
    path("podcasts/<uuid:course_id>/", student_views.student_podcast_list, name="student_podcast_list"),
    path("podcasts/detail/<uuid:podcast_id>/", student_views.student_podcast_detail, name="student_podcast_detail"),

    # ─── OpenMAIC: Study Notes (read-only) ───
    path("notes/", student_views.student_notes_list, name="student_notes_list"),
    path("notes/<uuid:notes_id>/", student_views.student_notes_detail, name="student_notes_detail"),
    path("notes/<uuid:notes_id>/export/", student_views.student_notes_export, name="student_notes_export"),

    # ─── OpenMAIC: AI Persona Chat ───
    path("personas/", student_views.student_persona_list, name="student_persona_list"),
    path("personas/sessions/", student_views.student_persona_sessions, name="student_persona_sessions"),
    path("personas/sessions/create/", student_views.student_persona_create_session, name="student_persona_create_session"),
    path("personas/sessions/<uuid:session_id>/", student_views.student_persona_session_detail, name="student_persona_session_detail"),
    path("personas/sessions/<uuid:session_id>/message/", student_views.student_persona_send_message, name="student_persona_send_message"),

    # ─── OpenMAIC: Classroom Collaboration ───
    path("classroom/<uuid:course_id>/", student_views.student_classroom_list, name="student_classroom_list"),
    path("classroom/create/", student_views.student_classroom_create, name="student_classroom_create"),
    path("classroom/session/<uuid:session_id>/", student_views.student_classroom_detail, name="student_classroom_detail"),
    path("classroom/session/<uuid:session_id>/join/", student_views.student_classroom_join, name="student_classroom_join"),
    path("classroom/session/<uuid:session_id>/leave/", student_views.student_classroom_leave, name="student_classroom_leave"),
    path("classroom/session/<uuid:session_id>/note/", student_views.student_classroom_add_note, name="student_classroom_add_note"),

    # Gamification
    path("gamification/summary/", student_views.student_gamification_summary, name="student_gamification_summary"),

    # Search
    path("search/", student_views.student_search, name="student_search"),
]
```

**New file:** `apps/users/student_admin_urls.py`

```python
# Mounted at /api/v1/students/ in config/urls.py (admin-accessible)
urlpatterns = [
    path("", student_admin_views.student_list, name="student_list"),
    path("create/", student_admin_views.student_create, name="student_create"),
    path("bulk-import/", student_admin_views.student_bulk_import, name="student_bulk_import"),
    path("bulk-action/", student_admin_views.student_bulk_action, name="student_bulk_action"),
    path("invitations/", student_admin_views.student_invitations, name="student_invitations"),
    path("bulk-invite/", student_admin_views.student_bulk_invite, name="student_bulk_invite"),
    path("<uuid:student_id>/", student_admin_views.student_detail, name="student_detail"),
    path("<uuid:student_id>/restore/", student_admin_views.student_restore, name="student_restore"),
    path("deleted/", student_admin_views.student_deleted_list, name="student_deleted_list"),
]
```

**Root URL mounting** (`config/urls.py`):

```python
# Add these to _api_patterns
path("student/", include("apps.courses.student_urls")),
path("student/", include("apps.progress.student_urls")),
path("students/", include("apps.users.student_admin_urls")),
```

### 3.6 Tenant Feature Flag

**File:** `apps/tenants/models.py`

```python
# Add to Tenant model
feature_students = models.BooleanField(default=False, help_text="Enable student portal")
max_students = models.PositiveIntegerField(default=50, help_text="Maximum student accounts")
```

**Plan presets update** (`apps/tenants/services.py`):

| Plan | max_students | feature_students |
|------|-------------|------------------|
| FREE | 0 | False |
| STARTER | 100 | True |
| PRO | 500 | True |
| ENTERPRISE | 9999 | True |

### 3.7 Login Flow Change

**File:** `apps/users/views.py` — `login_view`

```python
# In the role→redirect mapping, add:
if user.role == 'STUDENT':
    # Students login through tenant portal (portal="tenant"), same as teachers
    # Frontend handles the redirect to /student/dashboard
    pass
```

No backend login change needed — the same JWT login endpoint works. The frontend reads `user.role` from the response and routes to `/student/dashboard`.

### 3.8 New Backend Files Summary

| File | Purpose | Lines (est.) |
|------|---------|-------------|
| `apps/courses/student_views.py` | Student course/content/OpenMAIC views | ~600 |
| `apps/courses/student_urls.py` | Student URL routing | ~60 |
| `apps/progress/student_views.py` | Student progress/assignment/quiz views | ~400 |
| `apps/progress/student_urls.py` | Student progress URL routing | ~30 |
| `apps/users/student_admin_views.py` | Admin student management views | ~350 |
| `apps/users/student_admin_urls.py` | Admin student management URLs | ~15 |
| `apps/users/student_serializers.py` | Student-specific serializers | ~120 |
| Migration files (×3) | users, courses, progress, tenants | ~80 |

---

## 4. Frontend Implementation

### 4.1 Route Tree

```
/student
├── /dashboard                    # StudentDashboard
├── /courses                      # StudentCourseList
├── /courses/:courseId             # StudentCourseView (player)
├── /assignments                  # StudentAssignmentList
├── /quizzes/:assignmentId        # StudentQuizPage
├── /podcasts                     # StudentPodcastPage
├── /study-notes                  # StudentStudyNotesPage
├── /discussions                  # StudentDiscussionPage
├── /discussions/:threadId        # StudentDiscussionThreadPage
├── /classroom                    # StudentClassroomPage
├── /gamification                 # StudentGamificationPage
├── /profile                      # StudentProfilePage
└── /settings/security            # StudentSecurityPage
```

### 4.2 New Frontend Files

```
frontend/src/
├── pages/student/
│   ├── DashboardPage.tsx           # Progress overview, continue learning, deadlines
│   ├── CourseListPage.tsx          # Assigned courses grid
│   ├── CourseViewPage.tsx          # Course player (modules, content, interactive)
│   ├── AssignmentListPage.tsx      # Pending/submitted/graded assignments
│   ├── QuizPage.tsx               # Quiz taking UI
│   ├── PodcastPage.tsx            # Listen to course podcasts (reuse teacher component)
│   ├── StudyNotesPage.tsx         # View study notes (reuse with read-only flag)
│   ├── DiscussionPage.tsx         # Discussion forums
│   ├── DiscussionThreadPage.tsx   # Thread detail
│   ├── ClassroomPage.tsx          # Study groups
│   ├── GamificationPage.tsx       # XP, badges, streaks
│   ├── ProfilePage.tsx            # Student profile
│   └── SecurityPage.tsx           # Password, 2FA
├── components/
│   ├── layout/
│   │   ├── StudentLayout.tsx      # Layout wrapper (sidebar + header + content)
│   │   └── StudentSidebar.tsx     # Navigation sidebar
│   └── student/
│       ├── StudentMiniPlayer.tsx   # Floating podcast player
│       └── StudentAIChat.tsx       # AI Persona chat panel
├── services/
│   └── studentService.ts          # Student API client functions
└── (App.tsx updates)              # New route definitions
```

### 4.3 StudentSidebar Navigation

```typescript
const STUDENT_NAV = [
  // Main
  { label: 'Dashboard', icon: Home, path: '/student/dashboard' },
  { label: 'My Courses', icon: BookOpen, path: '/student/courses' },

  // Learning Tools (OpenMAIC)
  { label: 'Podcasts', icon: Headphones, path: '/student/podcasts' },
  { label: 'Study Notes', icon: FileText, path: '/student/study-notes' },
  { label: 'Discussions', icon: MessageSquare, path: '/student/discussions' },
  { label: 'Study Groups', icon: Users, path: '/student/classroom' },

  // Assessments
  { label: 'Assignments', icon: ClipboardList, path: '/student/assignments' },

  // Achievements
  { label: 'Achievements', icon: Trophy, path: '/student/gamification' },
];
```

### 4.4 StudentLayout Design

- **Color scheme:** Blue accent (differentiated from teacher's orange and admin's dark theme)
  - Primary: `#3B82F6` (blue-500) — student brand color
  - Background: `#F8FAFC` (slate-50)
  - Sidebar: White with blue active indicator
- **Responsive:** Desktop sidebar (240px) + mobile bottom nav
- **Header:** Student name, avatar, notification bell, help button
- **Mobile bottom nav:** Dashboard, Courses, Assignments, Chat, More

### 4.5 Login Page Update

**File:** `frontend/src/pages/auth/LoginPage.tsx`

```typescript
// In the role-based redirect after login:
case 'STUDENT':
  navigate('/student/dashboard');
  break;
```

### 4.6 App.tsx Route Registration

```tsx
// Lazy imports
const StudentDashboard = React.lazy(() => import('./pages/student/DashboardPage'));
const StudentCourseList = React.lazy(() => import('./pages/student/CourseListPage'));
// ... etc

// Routes
<Route path="/student" element={
  <ProtectedRoute allowedRoles={['STUDENT']}>
    <StudentLayout />
  </ProtectedRoute>
}>
  <Route path="dashboard" element={<StudentDashboard />} />
  <Route path="courses" element={<StudentCourseList />} />
  <Route path="courses/:courseId" element={<StudentCourseView />} />
  <Route path="assignments" element={<StudentAssignmentList />} />
  <Route path="quizzes/:assignmentId" element={<StudentQuizPage />} />
  <Route path="podcasts" element={<StudentPodcastPage />} />
  <Route path="study-notes" element={<StudentStudyNotesPage />} />
  <Route path="discussions" element={<StudentDiscussionPage />} />
  <Route path="discussions/:threadId" element={<StudentDiscussionThreadPage />} />
  <Route path="classroom" element={<StudentClassroomPage />} />
  <Route path="gamification" element={<StudentGamificationPage />} />
  <Route path="profile" element={<StudentProfilePage />} />
  <Route path="settings/security" element={<StudentSecurityPage />} />
</Route>
```

### 4.7 Student API Service

**File:** `frontend/src/services/studentService.ts`

```typescript
import api from '../config/api';

// Dashboard
export const studentDashboardApi = {
  dashboard: () => api.get('/v1/student/dashboard/'),
  calendar: (month: string) => api.get('/v1/student/calendar/', { params: { month } }),
};

// Courses
export const studentCourseApi = {
  list: () => api.get('/v1/student/courses/'),
  detail: (courseId: string) => api.get(`/v1/student/courses/${courseId}/`),
  search: (query: string) => api.get('/v1/student/search/', { params: { q: query } }),
};

// Progress
export const studentProgressApi = {
  startContent: (contentId: string) => api.post(`/v1/student/progress/content/${contentId}/start/`),
  updateProgress: (contentId: string, data: any) => api.patch(`/v1/student/progress/content/${contentId}/`, data),
  completeContent: (contentId: string) => api.post(`/v1/student/progress/content/${contentId}/complete/`),
};

// Assignments
export const studentAssignmentApi = {
  list: () => api.get('/v1/student/assignments/'),
  submit: (assignmentId: string, data: any) => api.post(`/v1/student/assignments/${assignmentId}/submit/`, data),
  submission: (assignmentId: string) => api.get(`/v1/student/assignments/${assignmentId}/submission/`),
  quizDetail: (assignmentId: string) => api.get(`/v1/student/quizzes/${assignmentId}/`),
  submitQuiz: (assignmentId: string, answers: any) => api.post(`/v1/student/quizzes/${assignmentId}/submit/`, answers),
};

// OpenMAIC — Podcasts (read-only)
export const studentPodcastApi = {
  list: (courseId: string) => api.get(`/v1/student/podcasts/${courseId}/`),
  detail: (podcastId: string) => api.get(`/v1/student/podcasts/detail/${podcastId}/`),
};

// OpenMAIC — Study Notes (read-only)
export const studentNotesApi = {
  list: (courseId: string) => api.get('/v1/student/notes/', { params: { course_id: courseId } }),
  detail: (notesId: string) => api.get(`/v1/student/notes/${notesId}/`),
  export: (notesId: string, format: 'markdown' | 'html') =>
    api.get(`/v1/student/notes/${notesId}/export/`, { params: { format }, responseType: 'text' }),
};

// OpenMAIC — AI Persona Chat
export const studentPersonaApi = {
  listPersonas: () => api.get('/v1/student/personas/'),
  listSessions: (courseId: string) => api.get('/v1/student/personas/sessions/', { params: { course_id: courseId } }),
  createSession: (data: any) => api.post('/v1/student/personas/sessions/create/', data),
  sessionDetail: (sessionId: string) => api.get(`/v1/student/personas/sessions/${sessionId}/`),
  sendMessage: (sessionId: string, message: string) =>
    api.post(`/v1/student/personas/sessions/${sessionId}/message/`, { message }),
};

// OpenMAIC — Classroom
export const studentClassroomApi = {
  list: (courseId: string) => api.get(`/v1/student/classroom/${courseId}/`),
  create: (data: any) => api.post('/v1/student/classroom/create/', data),
  detail: (sessionId: string) => api.get(`/v1/student/classroom/session/${sessionId}/`),
  join: (sessionId: string) => api.post(`/v1/student/classroom/session/${sessionId}/join/`),
  leave: (sessionId: string) => api.post(`/v1/student/classroom/session/${sessionId}/leave/`),
  addNote: (sessionId: string, markdown: string) =>
    api.post(`/v1/student/classroom/session/${sessionId}/note/`, { content_markdown: markdown }),
};

// Gamification
export const studentGamificationApi = {
  summary: () => api.get('/v1/student/gamification/summary/'),
};
```

---

## 5. OpenMAIC Features for Students

### Feature-by-Feature Breakdown

| Feature | Teacher Access | Student Access | Difference |
|---------|--------------|----------------|------------|
| **Podcasts** | Generate + Listen | Listen only | Students see READY podcasts from their assigned courses. No generate button. |
| **Study Notes** | Generate + View + Export + Delete | View + Export only | Students see READY notes. Can export but not generate or delete. |
| **AI Persona Chat** | Full chat with 4 personas | Full chat with 4 personas | Same experience. Student persona prompts tuned for student context. |
| **Classroom** | Create + Join + Notes | Create + Join + Notes | Same experience. Student classrooms are separate from teacher classrooms (separate participant pool). |
| **Interactive Lessons** | View + Reflect + Quiz | View + Reflect + Quiz | Same experience. StudentProgress replaces TeacherProgress for tracking. |
| **Scenarios** | Play through + Score | Play through + Score | Same experience. Attempts tracked under student. |
| **Gamification** | XP + Badges + Streaks + Leaderboard | XP + Badges + Streaks + Leaderboard | Same system. Student leaderboard is separate from teacher leaderboard. |

### Student Persona Adjustments

Students get a modified persona prompt set:

```python
STUDENT_PERSONA_CONFIGS = {
    "TEACHER": {
        "name": "Professor Ada",
        "system_prompt": "You are tutoring a student. Explain concepts clearly..."
    },
    "TA": {
        "name": "Sam (TA)",
        "system_prompt": "You are helping a student with their coursework..."
    },
    "STUDY_BUDDY": {
        "name": "Riley",
        "system_prompt": "You are a fellow student studying the same material..."
    },
    "SOCRATIC": {
        "name": "Dr. Socrates",
        "system_prompt": "Guide the student through questions. Never give answers directly..."
    },
}
```

### OpenMAIC Data Isolation

- **Podcasts & Notes:** Generated by teachers/admins, visible to students assigned to that course. Students can't see who generated them.
- **Persona Sessions:** Completely separate. Student sessions stored in same `AIPersonaSession` table with `student` FK (the teacher FK is nullable; student FK added).
- **Classroom Sessions:** Separate participant pool. A student classroom session is distinct from a teacher one (enforced by querying `ClassroomParticipant` with student role).

---

## 6. Admin Portal — Student Management

### New Admin Pages

| Page | Route | Purpose |
|------|-------|---------|
| Student List | `/admin/students` | List, search, filter students |
| Add Student | `/admin/students/new` | Create single student |
| Student Detail | `/admin/students/:id` | View/edit student profile |
| Bulk Import | `/admin/students` (modal) | CSV import students |
| Student Progress | `/admin/analytics` (tab) | Student progress analytics |

### Admin Sidebar Addition

```typescript
// In AdminSidebar.tsx — add under "Teachers"
{ label: 'Students', icon: GraduationCap, path: '/admin/students' },
```

### Course Editor — Student Assignment

The existing course editor's "Audience" tab needs a new section:

```
┌─────────────────────────────────────────┐
│ Audience Tab                             │
│                                          │
│ TEACHERS                                 │
│ ☐ Assign to all teachers                │
│ [Select teachers...] [Select groups...]  │
│                                          │
│ ─────────────────────────────────────── │
│                                          │
│ STUDENTS                          ← NEW │
│ ☐ Assign to all students                │
│ [Select students...] [Select groups...]  │
│                                          │
└─────────────────────────────────────────┘
```

### Tenant Feature Gating

Admin dashboard shows "Students" nav item only when `tenant.feature_students === true`. The plan upgrade page explains the feature.

---

## 7. Teacher Portal — Student Visibility

### What Teachers Can See

Teachers get a **read-only** view of student progress for courses they're associated with (created_by or assigned to teach).

| View | Route | Data |
|------|-------|------|
| Student Progress Tab | `/teacher/courses/:id` (new tab) | List of students assigned to course with completion % |
| Assignment Submissions | `/teacher/assignments` (new tab) | Student submissions for courses the teacher is linked to |

### Teacher Views — Backend

```python
# apps/progress/teacher_views.py — add

@api_view(['GET'])
@permission_classes([IsAuthenticated])
@teacher_or_admin
@tenant_required
def teacher_student_progress(request, course_id):
    """Teacher views student progress for a course they're associated with."""
    course = get_object_or_404(Course, id=course_id, tenant=request.tenant)
    # Verify teacher is associated with this course
    # Return student progress data (read-only)
```

### Implementation Note

Teachers CANNOT modify student records. This is strictly read-only. If a teacher needs to grade student work, the admin enables a `feature_teacher_grading` flag (future scope — not in v1).

---

## 8. Digital Ocean Deployment

### Current Infrastructure (No Changes Needed)

The existing Docker Compose production setup supports the student portal with **zero infrastructure changes**:

```
Digital Ocean Droplet
├── nginx (port 80/443) — reverse proxy
├── web (port 8000) — Django API (Gunicorn, 3 workers)
├── asgi (port 8001) — WebSocket (Daphne)
├── worker — Celery background tasks
├── beat — Celery scheduler
├── db (port 5432) — PostgreSQL 15
├── redis (port 6379) — Cache + broker
└── flower (port 5555) — Celery monitoring
```

### Why No Infrastructure Changes

1. **Same Django app** — student views are just new Django views in the same `web` container.
2. **Same React build** — student pages are lazy-loaded React components in the same frontend bundle.
3. **Same database** — student data goes in the same PostgreSQL instance (new tables via migration).
4. **Same auth** — JWT login works for students (same endpoint, different role).
5. **Same tenant resolution** — students access via `school.learnpuddle.com` (same subdomain).
6. **Same Celery** — no new background tasks needed (students consume, not generate).

### Deployment Steps

```bash
# SSH into droplet
ssh root@DROPLET_IP

# Navigate to project
cd /opt/lms

# Pull latest code
git pull origin main

# Rebuild web + nginx (frontend included in nginx multi-stage build)
docker compose -f docker-compose.prod.yml build --no-cache web nginx

# Run migrations (creates student tables)
docker compose -f docker-compose.prod.yml run --rm web python manage.py migrate

# Collect static files
docker compose -f docker-compose.prod.yml run --rm -u root web python manage.py collectstatic --noinput

# Restart all services
docker compose -f docker-compose.prod.yml up -d

# Verify
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f web --tail=50
```

### Scaling Considerations (Future)

If student load grows significantly:

| Metric | Current | Action |
|--------|---------|--------|
| Concurrent users >200 | 3 Gunicorn workers | Increase to 6-8 workers: `GUNICORN_WORKERS=8` |
| Database connections >50 | CONN_MAX_AGE=600 | Add PgBouncer connection pooler |
| Storage >50GB | DO Spaces | Already supported via `STORAGE_BACKEND=s3` |
| WebSocket connections >500 | Single Daphne | Add Redis-backed channel layer (already configured) |

### Environment Variables (No New Ones)

The student portal uses the same environment variables. No new secrets or API keys needed.

---

## 9. Migration & Data Safety

### Database Migrations

Three migration files needed:

```
1. apps/users/migrations/XXXX_add_student_role_and_fields.py
   - Add 'STUDENT' to ROLE_CHOICES
   - Add student_id, grade_level, section, parent_email, enrollment_date fields

2. apps/courses/migrations/XXXX_add_student_assignment_fields.py
   - Add assigned_students M2M field
   - Add assigned_to_all_students boolean

3. apps/progress/migrations/XXXX_create_student_progress.py
   - Create student_progress table

4. apps/tenants/migrations/XXXX_add_student_feature_flag.py
   - Add feature_students boolean
   - Add max_students integer
```

### Migration Safety

- **All migrations are additive** — no destructive changes, no column renames, no data deletions.
- **No existing data affected** — new fields are all nullable/blank or have defaults.
- **Backward compatible** — existing teacher/admin flows work unchanged.
- **Rollback safe** — can reverse migrations without data loss.

### Pre-Deploy Checklist

- [ ] Run `python manage.py makemigrations` to generate migration files
- [ ] Run `python manage.py migrate --plan` to preview changes
- [ ] Run `python manage.py migrate` on staging first
- [ ] Verify existing teacher login still works
- [ ] Verify existing admin dashboard still works
- [ ] Create test student account
- [ ] Assign course to student
- [ ] Verify student login and course access

---

## 10. Testing Strategy

### Backend Tests

```
tests/
├── test_student_auth.py          # Login, registration, invitation
├── test_student_courses.py       # Course listing, detail, content access
├── test_student_progress.py      # Progress tracking, completion
├── test_student_assignments.py   # Assignment submission, quiz
├── test_student_openmaic.py      # Podcast/notes access, persona chat
├── test_student_classroom.py     # Classroom join/leave/notes
├── test_student_admin.py         # Admin student management
└── test_student_isolation.py     # Students can't see teacher data
```

### Key Test Scenarios

1. **Auth isolation:** Student can't access `/api/v1/teacher/*` endpoints
2. **Tenant isolation:** Student from School A can't see School B data
3. **Course access:** Student only sees courses assigned to them
4. **OpenMAIC read-only:** Student can't hit podcast/notes generate endpoints
5. **Progress tracking:** Content completion updates correctly
6. **Gamification:** XP awarded on completion, badges earned
7. **Admin CRUD:** Admin can create/edit/delete/import students

### Frontend Tests

- Component rendering tests for each student page
- Route guard tests (STUDENT role only)
- API service mock tests
- E2E flow: login → dashboard → course → complete content → certificate

---

## Implementation Order

### Phase 1: Foundation (Backend Core)
1. User model changes (STUDENT role + fields)
2. Tenant feature flag (feature_students, max_students)
3. Course model changes (assigned_students)
4. StudentProgress model
5. Decorators (@student_only, @student_or_admin)
6. Migrations

### Phase 2: Student API
7. Student dashboard views
8. Student course list/detail views
9. Student progress views (start/update/complete)
10. Student assignment/quiz views
11. Student URL wiring

### Phase 3: Admin Student Management
12. Admin student CRUD views
13. Admin bulk import/invite
14. Admin student URL wiring
15. Course editor audience tab update (frontend)

### Phase 4: OpenMAIC for Students
16. Student podcast views (read-only)
17. Student study notes views (read-only)
18. Student persona chat views
19. Student classroom views
20. Student URL wiring for OpenMAIC

### Phase 5: Frontend — Student Portal
21. StudentLayout + StudentSidebar
22. StudentDashboard page
23. StudentCourseList + StudentCourseView
24. StudentAssignmentList + StudentQuizPage
25. StudentPodcastPage + StudentStudyNotesPage
26. StudentClassroomPage
27. Student API service
28. App.tsx route wiring
29. Login redirect update

### Phase 6: Teacher Integration
30. Teacher student progress views
31. Teacher assignment grading views (read-only display)

### Phase 7: Polish & Deploy
32. Student guided tour
33. Gamification for students
34. Testing
35. Deploy to Digital Ocean

---

## Summary

The student portal is a **parallel consumer role** that reuses the same backend infrastructure, same database, same Docker setup, and same deployment pipeline. The key additions are:

- **1 new role** on the User model
- **~5 new database tables** (student_progress + student-specific M2M)
- **~30 new API endpoints** under `/api/v1/student/`
- **~15 new React pages** under `/student/*`
- **~10 admin pages/components** for student management
- **0 infrastructure changes** on Digital Ocean

The OpenMAIC features are consumption-only for students (no generation), with their own persona session pool and classroom participant pool. Admin manages everything. Teachers get read-only visibility.

**Estimated scope:** ~4,000 lines backend + ~5,000 lines frontend.
