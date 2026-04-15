# Teacher Study Notes, Mind Map & Parent Portal — Design Spec

**Date:** 2026-04-13
**Status:** Approved

---

## Overview

Three features for LearnPuddle LMS, implemented in phases:

1. **Teacher Study Notes** — Port student AI Study Summaries to teacher portal with sharing capability
2. **Mind Map** — NotebookLM-style interactive concept graph as a 5th tab in StudySummaryPanel
3. **Parent Portal** — Magic-link authenticated read-only dashboard for parents

---

## Phase 1: Teacher Study Notes

### Data Model

Extend `StudySummary` model with two fields:

- `generated_by` (FK → User, nullable) — teacher who created it. Null for student-generated.
- `is_shared` (BooleanField, default=False) — when True, students see the teacher's summary

Unique constraint changes: `unique_together = (student, content, generated_by)` to allow both a student and teacher summary for the same content.

### Backend API

```
POST /api/v1/teacher/study-summaries/generate/     → SSE stream (reuses study_summary_service)
GET  /api/v1/teacher/study-summaries/               → List teacher's summaries
GET  /api/v1/teacher/study-summaries/<id>/           → Detail
DELETE /api/v1/teacher/study-summaries/<id>/delete/  → Delete
PATCH /api/v1/teacher/study-summaries/<id>/share/    → Toggle is_shared
```

Decorators: `@teacher_or_admin`, `@tenant_required`, `@check_feature("feature_maic")`

### Student-Side Enhancement

When student opens content, check for shared teacher summary first. If found, display with "Shared by teacher" badge. Student can still generate their own.

### Frontend

- `TeacherStudyNotesPage.tsx` — Two-panel layout mirroring student version
- `StudySummaryPanel.tsx` — Add `mode: 'student' | 'teacher'` prop. Teacher mode shows "Share with students" toggle.
- `TeacherSidebar.tsx` — Add "AI Study Notes" under AI Learning section (Sparkles icon)
- Route: `/teacher/study-notes`

---

## Phase 2: Mind Map

### Data Shape

Added to `summary_data` JSONField as `mind_map` key:

```json
{
  "mind_map": {
    "nodes": [
      { "id": "n1", "label": "Photosynthesis", "type": "core", "description": "..." },
      { "id": "n2", "label": "Chlorophyll", "type": "concept", "description": "..." }
    ],
    "edges": [
      { "source": "n1", "target": "n2", "label": "requires" }
    ]
  }
}
```

Node types: `core`, `concept`, `process`, `detail`

### LLM Prompt

Extend system prompt with mind map instructions:
- Central "core" node for main topic
- 4-8 "concept" nodes, 3-6 "process" nodes, 3-5 "detail" nodes
- 12-20 nodes total, 15-25 edges
- Each node: id, label (2-4 words), type, description (1-2 sentences)
- Each edge: source, target, label (1-2 words)

### SSE Event

New event `mind_map` streamed between `quiz_prep` and `done`.

### Visualization

React Flow (`@xyflow/react`) with Dagre auto-layout (`@dagrejs/dagre`).

Node styling by type:
- **Core** — Large, indigo background, white text
- **Concept** — Medium, white bg, indigo border
- **Process** — Medium, purple-50 bg, purple border
- **Detail** — Small, gray-50 bg, gray border

Interactivity:
- Zoom/pan (built-in)
- Click node → info panel with description + related terms
- Minimap, Fit View button, Fullscreen toggle
- Animated bezier edges with labels

### Dependencies

```
@xyflow/react @dagrejs/dagre
```

### Component

`MindMapTab.tsx` — renders inside StudySummaryPanel as 5th tab for both student and teacher modes.

---

## Phase 3: Parent Portal

### Authentication

Magic link flow:
1. Parent visits `/parent` → email input
2. `POST /api/v1/parent/auth/request-link/` — validates email against student `parent_email` fields
3. Sends email with signed JWT (15-min expiry, contains parent_email + tenant_id + student_ids[])
4. Parent clicks link → `/parent/verify?token=<jwt>`
5. `POST /api/v1/parent/auth/verify/` → exchanges for session token (24h) + refresh token (7d)

Security:
- Magic link is single-use
- Rate limit: 3 requests per email per hour
- No email enumeration (same success message regardless)
- Read-only access only

### Data Model

```python
class ParentSession(models.Model):
    id = UUIDField(primary_key=True)
    tenant = ForeignKey(Tenant)
    parent_email = EmailField()
    students = ManyToManyField(User, related_name='parent_sessions')
    session_token = CharField(max_length=255, unique=True)
    refresh_token = CharField(max_length=255, unique=True)
    is_active = BooleanField(default=True)
    created_at = DateTimeField(auto_now_add=True)
    expires_at = DateTimeField()
    last_accessed = DateTimeField(auto_now=True)
```

### Backend API

```
POST /api/v1/parent/auth/request-link/     → Send magic link
POST /api/v1/parent/auth/verify/           → Exchange token for session
POST /api/v1/parent/auth/refresh/          → Refresh session
POST /api/v1/parent/auth/logout/           → Invalidate session

GET  /api/v1/parent/children/              → List linked students
GET  /api/v1/parent/children/<id>/overview/ → Full child dashboard data
```

### Dashboard Data

`/children/<id>/overview/` returns:
- Student info (name, grade, section)
- Course progress (title, progress_pct, last_accessed)
- Assignments (title, course, due_date, status, grade)
- Attendance (present, absent, late, total, rate_pct)
- Study time (weekly_hours, daily_breakdown)
- Recent activity (action, subject, timestamp)

### Frontend

**Layout:** No sidebar. Minimal top bar with tenant logo, parent email, child selector, logout.

**Pages:**
- `ParentLoginPage.tsx` — Email input form
- `ParentVerifyPage.tsx` — Token exchange + redirect
- `ParentDashboardPage.tsx` — Scrollable card-based dashboard

**Dashboard Cards:**
1. CourseProgressCard — Progress bars per course
2. AssignmentsCard — Status-colored table
3. AttendanceCard — Donut chart + rate
4. StudyTimeCard — Weekly bar chart
5. RecentActivityCard — Timeline

**Routes:**
```
/parent           → ParentLoginPage
/parent/verify    → ParentVerifyPage
/parent/dashboard → ParentDashboardPage
```

**Child Selector:** Dropdown if parent_email matches multiple students.

---

## File Summary

### New Backend Files (8)
- `parent_models.py`, `parent_views.py`, `parent_urls.py`
- `parent_auth.py`, `parent_email.py`
- `teacher_study_views.py`
- `migrations/0032_study_summary_teacher_fields.py`
- `migrations/0033_parent_session.py`

### Modified Backend Files (5)
- `study_summary_service.py` — Mind map prompt + SSE event
- `study_summary_views.py` — Check shared teacher summaries
- `study_summary_models.py` — Add generated_by, is_shared
- `teacher_urls.py` — Include teacher study summary URLs
- Project `urls.py` — Include parent URLs

### New Frontend Files (16)
- `pages/teacher/TeacherStudyNotesPage.tsx`
- `pages/parent/ParentLoginPage.tsx`, `ParentVerifyPage.tsx`, `ParentDashboardPage.tsx`
- `components/parent/ParentLayout.tsx`, `ChildSelector.tsx`
- `components/parent/CourseProgressCard.tsx`, `AssignmentsCard.tsx`, `AttendanceCard.tsx`, `StudyTimeCard.tsx`, `RecentActivityCard.tsx`
- `components/student/MindMapTab.tsx`
- `services/parentService.ts`, `services/teacherStudyService.ts`
- `stores/parentStore.ts`
- `types/parent.ts`

### Modified Frontend Files (5)
- `StudySummaryPanel.tsx` — mode prop, mind map tab, share toggle
- `TeacherSidebar.tsx` — AI Study Notes nav entry
- `studentService.ts` — Check shared summaries
- `types/studySummary.ts` — Mind map types, generated_by, is_shared
- `App.tsx` — Parent + teacher study notes routes
