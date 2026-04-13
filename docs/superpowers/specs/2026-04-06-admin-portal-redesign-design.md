# LearnPuddle Admin Portal Redesign — Design Spec

**Date:** 2026-04-06
**Status:** Approved
**Scope:** School Admin (tenant) portal — all pages, navigation, terminology, features

---

## 1. Navigation — Sidebar Reduction

**Current:** 16 sidebar items
**Target:** 9 sidebar items

| # | Item | Icon | Status |
|---|------|------|--------|
| 1 | Dashboard | LayoutDashboard | Keep |
| 2 | Courses | BookOpen | Keep (absorbs AI Generator, AI Studio, Media Library) |
| 3 | Teachers | Users | Keep (rename from "Guides" everywhere) |
| 4 | Groups | FolderTree | Keep as-is |
| 5 | Certifications | Award | Keep (add Approvals tab, IB Dashboard tab) |
| 6 | Analytics | BarChart3 | Keep (absorbs Reports as drill-down) |
| 7 | Reminders | Bell | Keep (redesign: automated rules + manual + history) |
| 8 | Billing | CreditCard | Keep (switch to Razorpay + UPI) |
| 9 | Settings | Settings | Keep (reduce to 3 sections) |

**Removed pages:**
- Skills Matrix → deleted
- Gamification Settings → deleted
- Manager Dashboard → deleted
- Announcements → deleted
- Media Library (standalone) → file picker inside course editor
- AI Generator (standalone) → built into course creation flow
- AI Studio (standalone) → built into course creation flow
- Reports (standalone) → merged into Analytics as drill-down
- Skip Requests (standalone) → moved to Certifications > Approvals tab

**Files to delete:**
- `SkillsMatrixPage.tsx`
- `GamificationSettingsPage.tsx`
- `ManagerDashboardPage.tsx`
- `AnnouncementsPage.tsx`
- `MediaLibraryPage.tsx` (standalone page only; file picker component stays)
- `AICourseGeneratorPage.tsx`
- `AIStudioPage.tsx`
- `ReportsPage.tsx` (content moves to Analytics)
- `SkipRequestsPage.tsx` (content moves to Certifications)

**Files to modify:**
- `AdminSidebar.tsx` — reduce to 9 items
- `App.tsx` — remove routes for deleted pages, update remaining routes
- `admin/index.ts` — update exports

---

## 2. Global Changes

### 2.1 Terminology: "Guides" → "Teachers"

Every occurrence of "Guide/Guides" referring to teachers must be replaced with "Teacher/Teachers".

**Known locations:**
- `DashboardPage.tsx` — "Total Guides" (line 93), "Add Guide" (line 222), "Guides" usage bar (line 256)
- `TopNav.tsx` — "Guides" (line 71), "Guide" role label (line 426)
- `TeacherSidebar.tsx` — "Guide" role label (line 156)
- All other frontend files containing "Guide"/"Guides" in user-facing strings

**Approach:** Global search-and-replace with manual review per file. Backend models/API already use "TEACHER".

### 2.2 Search — Platform-Wide Command Palette

**Current:** `SearchBar.tsx` (267 lines) only searches courses/content via `/courses/search/?q={query}`.

**Target:** Platform-wide command palette (Cmd+K / Ctrl+K) that searches:
- Courses (title, description)
- Teachers (name, email)
- Groups (name)
- Certifications (name)
- Platform sections (navigate to pages)

**Implementation:**
- New `CommandPalette.tsx` component replacing current `SearchBar.tsx`
- Backend: New `/api/v1/search/` endpoint that searches across models
- Frontend: Modal overlay with categorized results, keyboard navigation
- Each result type has an icon prefix and click navigates to that item

### 2.3 Tooltips

Add descriptive tooltips to all action buttons and key UI elements. Examples:
- AI Course Generator button → "Use AI to generate assignments and course questions"
- Quick action buttons → brief description of what each does
- Dashboard stats cards → what the metric measures

---

## 3. Page Specifications

### 3.1 Dashboard

**Keep as-is:**
- Hero stats (Total Teachers, Active Courses, Completion Rate, Pending Reviews)
- Quick actions section

**Changes:**

| Element | Change |
|---------|--------|
| Plan Card | Compact badge showing plan name (e.g., "Pro"). Click expands modal with full plan details, limits, usage bars |
| Top Performers | Calculate from actual submission rate + course finish rate (not placeholder 0%) |
| Recent Activity | Remove timeline feed. Replace with **Deadlines Calendar** — month view showing upcoming course deadlines, assignment due dates, certification expiries |
| "Add Guide" button | Rename to "Add Teacher" |
| "Total Guides" stat | Rename to "Total Teachers" |
| AI Generator quick action | Rename to "AI Course/Assignment Generator". Tooltip: "Use AI to generate assignments and course questions" |
| Activity feed | Replace with calendar widget showing deadlines. Course-specific activity moves to individual course detail pages |

**Dashboard layout:**
```
┌─────────────────────────────────────────────┐
│  [Stats Row: Teachers | Courses | Rate | Reviews] │
├──────────────────────┬──────────────────────┤
│  Quick Actions       │  Plan Badge [Pro ▸]  │
│  (4 action cards)    │  (click → modal)     │
├──────────────────────┼──────────────────────┤
│  Deadlines Calendar  │  Top Performers      │
│  (month view)        │  (by submission+     │
│                      │   finish rate)        │
└──────────────────────┴──────────────────────┘
```

### 3.2 Courses

**Keep as-is:**
- Course listing with filters, search, pagination
- Course creation form (title, description, thumbnail, modules, content)
- Course editor with module/content management

**Changes:**

| Element | Change |
|---------|--------|
| AI Generation | Build into course creation flow. After creating a course shell, offer "Generate with AI" option that accepts: PDF upload OR topic description. Generates: lesson outline, quiz questions (multiple difficulty), assignment prompts. Based on OpenMAIC approach. |
| Lesson Planner | Add to course editor: analyzes uploaded docs/topic to generate structured lesson outlines with learning objectives, logical scenes, sequenced activities |
| Media Library | Remove standalone page. Add file picker within course content editor that browses existing uploads with search/filter |
| Course Activity | Add activity tab within individual course detail showing recent submissions, completions, teacher progress for that course |

**AI generation flow (within course editor):**
```
Course Editor
  └─ "Generate with AI" tab/button
       ├─ Upload PDF  ─or─  Enter topic description
       ├─ AI analyzes content
       └─ Generates:
            ├─ Lesson outline (scenes, objectives, activities)
            ├─ Quiz questions (easy/medium/hard)
            ├─ Assignment prompts
            └─ (Future: animated slides, narration scripts, simulations)
```

**Backend:** The existing AI generation endpoints (`/api/v1/courses/{id}/modules/{mid}/contents/generate-assignments/`) remain. New endpoint needed for lesson planning from PDF/topic.

### 3.3 Teachers

**Keep as-is:**
- Teacher list with search, filters, bulk actions
- Create teacher form
- Teacher detail/edit
- CSV bulk import

No changes beyond the global "Guides" → "Teachers" terminology fix.

### 3.4 Groups

**Keep as-is — no changes.**

Current functionality (create/edit/delete groups, assign members, assign courses to groups) is sufficient.

### 3.5 Certifications

**Current:** Single list of certifications.

**Target:** 3-tab layout:

| Tab | Content |
|-----|---------|
| **Certifications** | List of mandatory certifications for teachers. Create/edit/delete certs. Status tracking per teacher. |
| **Approvals** | Skip request approval workflow. Teachers request to skip certification courses. Admin approves/rejects. Filterable by course (dropdown). Tabs within: All / Pending / Approved / Rejected. (Content from current `SkipRequestsPage.tsx`) |
| **IB Dashboard** | School-level IB compliance ranking. Percentage of teachers certified. Comparison metrics. (New — requires backend endpoint) |

**Implementation:**
- Move `SkipRequestsPage.tsx` content into `CertificationsPage.tsx` as a tab
- Add course-wise dropdown filter to Approvals tab
- Add IB Dashboard tab (new component)
- Wire skip request API (`adminService.listSkipRequests`, `adminService.reviewSkipRequest`) into the Approvals tab

### 3.6 Analytics (absorbs Reports)

**Current:** Basic analytics charts + separate Reports page.

**Target:** Enhanced analytics with Reports as drill-down view.

**Charts to add:**
- Deadline Adherence — % of teachers meeting deadlines over time
- Certification Compliance — % certified per required certification
- Approval Trends — skip request volume and approval rates over time
- Course Effectiveness — completion rate vs. average score per course

**Reports integration:**
- "Export" or "Detailed View" button on each chart opens drill-down with tabular data
- Export to CSV/PDF from drill-down view
- Remove standalone Reports route

**Files affected:**
- `AnalyticsPage.tsx` — add new chart components, add drill-down views
- `ReportsPage.tsx` — extract reusable report table components, then delete page
- Backend: New analytics endpoints for deadline adherence, cert compliance, approval trends

### 3.7 Reminders

**Current:** Manual reminder creation and sending.

**Target:** Automated rules + manual override + history log.

**3 sections:**

| Section | Description |
|---------|-------------|
| **Rules** | Automated reminder rules. E.g., "Send reminder 3 days before any course deadline", "Weekly digest of incomplete courses", "Certification expiry 30-day warning". Toggle on/off per rule. Smart defaults pre-configured. |
| **Manual Send** | One-off reminder to specific teachers or groups. Select recipients, write message, send immediately or schedule. |
| **History** | Log of all sent reminders (auto + manual). Filterable by date, type, recipient. Shows delivery status. |

**Automated rule types:**
- `DEADLINE_APPROACHING` — X days before course deadline (default: 3, 1)
- `COURSE_INCOMPLETE` — weekly digest for teachers with incomplete courses
- `CERT_EXPIRING` — X days before certification expiry (default: 30, 7)
- `ASSIGNMENT_OVERDUE` — X days after assignment due date (default: 1, 3)

**Backend:**
- New `ReminderRule` model with: `rule_type`, `trigger_days`, `is_active`, `tenant`
- Celery beat task to evaluate rules daily and create/send reminders
- Existing `COURSE_DEADLINE`, `ASSIGNMENT_DUE`, `CUSTOM` types remain valid

### 3.8 Billing

**Current:** Stripe-based billing (not relevant for Indian market).

**Target:** Razorpay + UPI integration.

**Features:**
- Current plan display with usage metrics
- Plan comparison and upgrade flow
- Razorpay checkout integration (credit card, debit card, UPI, net banking)
- Invoice history and download
- Payment receipt generation

**Backend:**
- Replace/supplement Stripe SDK with Razorpay SDK
- Razorpay webhook handler for payment confirmation
- UPI payment flow support
- Invoice model updates for Indian GST compliance

**Files affected:**
- `BillingPage.tsx` — redesign payment UI for Razorpay
- `apps/billing/` — new Razorpay integration service
- New: `apps/billing/razorpay_service.py`

### 3.9 Settings

**Current:** Multiple settings sections.

**Target:** 3 sections only.

| Section | Contents |
|---------|----------|
| **School Profile** | School name, email, phone, address, subdomain display |
| **Branding** | Logo upload, primary color, secondary color, font family |
| **Security** | Password policies, 2FA settings, session timeout, SSO configuration |

**Remove:** Any settings sections beyond these 3 (notification preferences move to Reminders rules, feature flags managed by super admin only).

---

## 4. Backend Changes Summary

| Area | Change | Priority |
|------|--------|----------|
| Search endpoint | New `/api/v1/search/` — cross-model search | P1 |
| Analytics endpoints | Deadline adherence, cert compliance, approval trends, course effectiveness | P1 |
| Reminder rules | `ReminderRule` model + Celery beat evaluation | P1 |
| AI lesson planner | Endpoint for PDF/topic → lesson outline generation | P2 |
| Razorpay integration | Payment service, webhooks, UPI flow | P2 |
| IB Dashboard | School-level certification compliance endpoint | P2 |
| Gamification removal | Remove/deprecate gamification endpoints (keep models for data) | P3 |
| Reports merge | Deprecate standalone report endpoints (keep data logic) | P3 |

---

## 5. Frontend File Impact Matrix

| File | Action | Agent |
|------|--------|-------|
| `AdminSidebar.tsx` | Edit: reduce to 9 items | Navigation |
| `App.tsx` | Edit: remove deleted routes, update paths | Navigation |
| `admin/index.ts` | Edit: update exports | Navigation |
| `DashboardPage.tsx` | Edit: calendar, plan badge, top performers, terminology | Dashboard |
| `CoursesPage.tsx` | Edit: minor (add AI generation entry point) | Courses |
| `CourseEditorPage.tsx` | Edit: add AI generation tab, file picker, activity tab | Courses |
| `course-editor/*` | Edit: integrate AI generation, lesson planner | Courses |
| `TeachersPage.tsx` | No changes (terminology only) | Terminology |
| `GroupsPage.tsx` | No changes | — |
| `CertificationsPage.tsx` | Edit: add 3-tab layout, approvals, IB dashboard | Certifications |
| `AnalyticsPage.tsx` | Edit: new charts, reports drill-down integration | Analytics |
| `RemindersPage.tsx` | Edit: redesign with rules/manual/history sections | Reminders |
| `BillingPage.tsx` | Edit: Razorpay + UPI integration | Billing |
| `SettingsPage.tsx` | Edit: reduce to 3 sections | Settings |
| `SearchBar.tsx` | Replace: command palette | Search |
| `TopNav.tsx` | Edit: terminology, integrate command palette | Navigation |
| `TeacherSidebar.tsx` | Edit: terminology | Terminology |
| `SkillsMatrixPage.tsx` | Delete | Cleanup |
| `GamificationSettingsPage.tsx` | Delete | Cleanup |
| `ManagerDashboardPage.tsx` | Delete | Cleanup |
| `AnnouncementsPage.tsx` | Delete | Cleanup |
| `MediaLibraryPage.tsx` | Delete (keep file picker component) | Cleanup |
| `AICourseGeneratorPage.tsx` | Delete (logic moves to course editor) | Cleanup |
| `AIStudioPage.tsx` | Delete (logic moves to course editor) | Cleanup |
| `ReportsPage.tsx` | Delete (content moves to Analytics) | Cleanup |
| `SkipRequestsPage.tsx` | Delete (content moves to Certifications) | Cleanup |

---

## 6. Agent Workstream Decomposition

### Agent 1: Navigation & Cleanup
**Scope:** Sidebar, routing, deleted pages, exports
**Dependencies:** None (runs first)
**Files:** `AdminSidebar.tsx`, `App.tsx`, `admin/index.ts`, 9 deleted page files
**Communication:** Signals completion before other agents start modifying pages

### Agent 2: Terminology
**Scope:** "Guides" → "Teachers" globally
**Dependencies:** Agent 1 (needs routes stabilized)
**Files:** All frontend files containing "Guide"/"Guides" in user-facing strings
**Communication:** Provides list of changed files so other agents don't conflict

### Agent 3: Dashboard
**Scope:** Dashboard redesign — calendar, plan badge, top performers, tooltips
**Dependencies:** Agent 1 (sidebar done), Agent 2 (terminology done)
**Files:** `DashboardPage.tsx`, new `DeadlinesCalendar.tsx`, new `PlanBadge.tsx`

### Agent 4: Courses & AI
**Scope:** AI generation integration, lesson planner, file picker, course activity
**Dependencies:** Agent 1 (cleanup done)
**Files:** `CourseEditorPage.tsx`, `course-editor/*`, new AI components
**Backend:** AI lesson planner endpoint

### Agent 5: Certifications
**Scope:** 3-tab layout, approvals integration, IB dashboard
**Dependencies:** Agent 1 (skip requests page deleted, content extracted)
**Files:** `CertificationsPage.tsx`, new `ApprovalsTab.tsx`, new `IBDashboard.tsx`
**Backend:** IB dashboard endpoint

### Agent 6: Analytics & Reports
**Scope:** New charts, reports drill-down, export functionality
**Dependencies:** Agent 1 (reports page deleted, content extracted)
**Files:** `AnalyticsPage.tsx`, new chart components
**Backend:** New analytics endpoints

### Agent 7: Reminders & Search
**Scope:** Reminder rules/manual/history redesign, command palette
**Dependencies:** Agent 1 (routes stable)
**Files:** `RemindersPage.tsx`, `SearchBar.tsx` → `CommandPalette.tsx`, `TopNav.tsx`
**Backend:** `ReminderRule` model, Celery tasks, search endpoint

### Agent 8: Billing & Settings
**Scope:** Razorpay/UPI integration, settings reduction
**Dependencies:** Agent 1 (routes stable)
**Files:** `BillingPage.tsx`, `SettingsPage.tsx`
**Backend:** Razorpay service, billing model updates

---

## 7. Execution Order

```
Phase 1 (Foundation):
  Agent 1: Navigation & Cleanup  ─── must complete first

Phase 2 (Global):
  Agent 2: Terminology            ─── after Agent 1

Phase 3 (Parallel — all independent):
  Agent 3: Dashboard              ┐
  Agent 4: Courses & AI           │
  Agent 5: Certifications         ├── all run in parallel
  Agent 6: Analytics & Reports    │
  Agent 7: Reminders & Search     │
  Agent 8: Billing & Settings     ┘

Phase 4 (Integration):
  Final verification — ensure no import breaks, route conflicts, or style inconsistencies
```

---

## 8. Communication Protocol

Agents communicate via a shared `docs/superpowers/agent-state.md` file:

```markdown
## Agent State
| Agent | Status | Last Updated | Notes |
|-------|--------|-------------|-------|
| 1-nav | done | ... | 9 pages deleted, sidebar updated |
| 2-term | done | ... | 47 files changed |
| 3-dash | in-progress | ... | calendar component done |
...
```

**Rules:**
1. Never modify files owned by another agent (see File Impact Matrix)
2. If you need a shared component, create it in `components/shared/` and note it in state file
3. Backend changes: each agent owns specific apps/endpoints (no overlap)
4. All agents read `admin/index.ts` but only Agent 1 writes to it
5. Import changes: if you delete an export another agent imports, leave a TODO comment

---

## 9. Success Criteria

- [ ] Sidebar shows exactly 9 items
- [ ] Zero occurrences of "Guide"/"Guides" referring to teachers in UI
- [ ] Command palette searches across courses, teachers, groups, certifications, pages
- [ ] Dashboard shows deadlines calendar instead of activity feed
- [ ] Plan card is compact badge with expand-to-modal behavior
- [ ] Top performers calculated from real submission + finish rate data
- [ ] AI course generation accessible from within course editor
- [ ] Certifications has 3 tabs: Certs / Approvals / IB Dashboard
- [ ] Analytics includes 4 new chart types + reports drill-down
- [ ] Reminders has automated rules, manual send, and history
- [ ] Billing integrates Razorpay + UPI
- [ ] Settings reduced to 3 sections: Profile / Branding / Security
- [ ] All deleted pages return 404 (no broken routes)
- [ ] No console errors or broken imports
- [ ] All existing tests pass (modified tests updated)
