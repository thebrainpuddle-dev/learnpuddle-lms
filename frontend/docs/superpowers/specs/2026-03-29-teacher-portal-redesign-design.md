# Teacher Portal Redesign — Design Spec

**Date:** 2026-03-29
**Reference:** Braicademy UI screenshot
**Scope:** Teacher/Guide portal only (admin portal unchanged)

---

## Design Direction

Dark theme LMS dashboard matching Braicademy reference. Dark navy sidebar with teal accent highlights. All teacher pages use dark card-based UI with consistent color tokens.

### Key Decisions
- **Approach:** Teacher portal first, admin portal later (Option C)
- **Data strategy:** UI first with mock/placeholder data for new features (watch time, study statistics chart), real backend for existing endpoints
- **Sidebar color:** Tenant-configurable accent, default teal (#4ECDC4)
- **Terminology:** Teacher-centric ("Classroom" not "Gamification", "Assessments" not "Assignments")
- **Mobile:** Priority-stacked feed + bottom tab nav

---

## Layout Architecture

### Desktop (≥1024px)
- **Sidebar:** Fixed left, 240px wide, dark navy (#1A1A2E)
- **Main content:** Flexible width, max 1400px centered
- **Right panel:** Inline within main content grid (320px on XL screens)

### Mobile (<1024px)
- Sidebar becomes slide-out drawer
- Bottom tab navigation: Overview | Courses | Assessments | Announce | More
- Content stacks vertically

### Sidebar Items
1. Overview (Dashboard)
2. My Courses
3. Classroom (course viewer)
4. Announcements
5. Assessments
6. Reports
7. Settings (bottom)
8. Support (bottom)
9. Logout (bottom)

---

## Color Tokens

```
Teacher Portal (tp-*):
  bg:              #0F0F23  (page background)
  sidebar:         #1A1A2E  (sidebar bg)
  sidebar-hover:   #232340
  sidebar-active:  #2A2A4A
  sidebar-border:  #2E2E4E
  card:            #16213E  (card backgrounds)
  card-hover:      #1A2744
  card-border:     #1E2D50
  accent:          #4ECDC4  (teal, default)
  accent-light:    #6EDDD6
  accent-dark:     #3ABDB4
  text:            #FFFFFF
  text-secondary:  #A0AEC0
  text-muted:      #718096

Status (shared):
  success:         #48BB78 / green-400
  warning:         #ECC94B / yellow-400
  danger:          #FC8181 / red-400
  info:            #63B3ED / blue-400
```

---

## Screen Specifications

### 1. Overview (Dashboard)

**Stat Cards Row:** 4 cards — Watch Time, Completed, Certificates, In Progress
- Dark card bg (#16213E), white text, colored icon backgrounds
- Responsive: 4 columns → 2×2 → stacked

**Study Statistics:** Bar chart (Recharts) showing weekly hours
- Teal bars with rounded tops
- Week/Month toggle
- Dark card with subtle grid lines

**Classroom Table:** Active courses at-a-glance
- Columns: Course (thumbnail+title), Progress (bar+%), Status (badge), Action (button)
- 5 rows max, "View All" link
- Dark rows with hover highlight

**Right Panel (XL screens):**
- Continue Learning CTA card (teal gradient)
- Upcoming Assessments list
- Announcements list

### 2. My Courses

**Views:** Grid (default) and List, toggle in filter bar

**Grid View:** 3 columns, dark cards with:
- Thumbnail (or placeholder), hover play overlay
- Status badge overlay
- Title, description, progress bar, meta (lessons, hours)

**List View:** Table-like rows with thumbnail, title, progress, status, deadline

**Filters:** Search + status pills (All | Not Started | In Progress | Completed) + view toggle

### 3. Assessments

**Stats Bar:** 3 mini cards — Pending, Avg Score, Completed

**Tabs:** All | Pending | Submitted | Graded (with counts)

**Assessment Cards:** 2-column grid, each card shows:
- Type icon (quiz/assignment), title, course name
- Status badge (color-coded)
- Score (if graded)
- Due date with urgency coloring
- Action buttons (Start/Submit/View)

### 4. Reports (maps to existing Gamification page)

Unchanged in this phase — visual dark theme applied via layout.

### 5. Classroom (maps to existing CourseViewPage)

Unchanged in this phase — visual dark theme applied via layout.

---

## Typography

- **Headings:** Inter, bold — 24px (h1), 16px (section), 14px (card)
- **Body:** 14px regular, 13px secondary
- **Captions:** 11px semibold uppercase tracking-wide (10px for smallest)
- **Stats:** 24px bold (stat cards), 32px bold (hero stats)
- All text in white/light gray on dark backgrounds

---

## Components Modified

| File | Change |
|------|--------|
| `tailwind.config.cjs` | Added `tp-*` color tokens |
| `src/assets/styles/index.css` | Added `.tp-scrollbar`, `.tp-skeleton` utilities |
| `src/components/layout/TeacherLayout.tsx` | Full rewrite: dark 3-column layout |
| `src/components/layout/TeacherSidebar.tsx` | Full rewrite: dark navy sidebar, Lucide icons |
| `src/components/layout/TeacherHeader.tsx` | Full rewrite: dark header with search + notifications |
| `src/components/layout/MobileBottomNav.tsx` | Full rewrite: dark bottom tabs |
| `src/App.tsx` | Teacher routes use `TeacherLayout` instead of `PageShell` |
| `src/pages/teacher/DashboardPage.tsx` | Full rewrite: dark overview with stat cards, chart, classroom table |
| `src/pages/teacher/MyCoursesPage.tsx` | Full rewrite: dark grid/list view with filters |
| `src/pages/teacher/AssignmentsPage.tsx` | Full rewrite: dark assessments with tabs and cards |

---

## Backend Gaps (for later)

1. **Watch time aggregation** — New endpoint for monthly watch time stats
2. **Certificate count** — Endpoint returning earned certificate count
3. **Study statistics time-series** — Weekly/monthly learning hours data for chart
