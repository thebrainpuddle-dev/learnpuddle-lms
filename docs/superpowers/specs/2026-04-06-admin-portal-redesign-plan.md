# LearnPuddle Admin Portal Redesign — Implementation Plan

**Date:** 2026-04-06
**Spec:** `2026-04-06-admin-portal-redesign-design.md`
**Constraint:** No git commit/add/push

---

## Phase 1: Navigation & Cleanup (Agent 1)

**Goal:** Remove deleted pages, update sidebar to 9 items, clean routes.

### Steps:

1. **Delete 9 page files:**
   - `frontend/src/pages/admin/SkillsMatrixPage.tsx`
   - `frontend/src/pages/admin/GamificationSettingsPage.tsx`
   - `frontend/src/pages/admin/ManagerDashboardPage.tsx`
   - `frontend/src/pages/admin/AnnouncementsPage.tsx`
   - `frontend/src/pages/admin/MediaLibraryPage.tsx`
   - `frontend/src/pages/admin/AICourseGeneratorPage.tsx`
   - `frontend/src/pages/admin/AIStudioPage.tsx`
   - `frontend/src/pages/admin/ReportsPage.tsx`
   - `frontend/src/pages/admin/SkipRequestsPage.tsx`

2. **Before deleting, extract reusable content:**
   - From `SkipRequestsPage.tsx`: Extract the skip request list/review UI into `components/certifications/ApprovalsTab.tsx`
   - From `ReportsPage.tsx`: Extract report table components into `components/analytics/ReportDrillDown.tsx`
   - From `MediaLibraryPage.tsx`: Extract file browser into `components/courses/FilePicker.tsx`
   - From `AICourseGeneratorPage.tsx` + `AIStudioPage.tsx`: Extract AI generation logic into `components/courses/AIGenerationPanel.tsx`

3. **Update `AdminSidebar.tsx`:**
   - Remove nav items for deleted pages
   - Keep exactly: Dashboard, Courses, Teachers, Groups, Certifications, Analytics, Reminders, Billing, Settings
   - Update icons if needed

4. **Update `App.tsx`:**
   - Remove Route entries for deleted pages
   - Remove lazy imports for deleted pages
   - Ensure remaining routes are correct

5. **Update `admin/index.ts`:**
   - Remove exports for deleted pages
   - Add exports for new extracted components

6. **Verify:** No broken imports, app compiles, all 9 sidebar links work.

---

## Phase 2: Terminology (Agent 2)

**Goal:** Replace all "Guide"/"Guides" with "Teacher"/"Teachers" in user-facing strings.

### Steps:

1. **Search all frontend files** for case-insensitive "guide" in strings/JSX:
   ```
   grep -rn "Guide\|guide" frontend/src/ --include="*.tsx" --include="*.ts"
   ```

2. **Replace in known files:**
   - `DashboardPage.tsx`: "Total Guides" → "Total Teachers", "Add Guide" → "Add Teacher", "Guides" usage bar label
   - `TopNav.tsx`: line 71 "Guides" → "Teachers", line 426 "Guide" role label → "Teacher"
   - `TeacherSidebar.tsx`: line 156 "Guide" → "Teacher"

3. **Replace in all other files** found by search. Only change user-facing strings, not variable names or API fields.

4. **Verify:** Search again — zero occurrences of "Guide"/"Guides" as user-facing teacher terminology.

---

## Phase 3A: Dashboard (Agent 3)

**Goal:** Redesign dashboard with calendar, compact plan badge, real top performers.

### Steps:

1. **Create `components/dashboard/DeadlinesCalendar.tsx`:**
   - Month-view calendar widget
   - Shows: course deadlines, assignment due dates, certification expiries
   - Data source: new API endpoint or aggregate from existing course/assignment data
   - Click on date shows list of items due
   - Use a lightweight calendar library (e.g., react-day-picker or custom grid)

2. **Create `components/dashboard/PlanBadge.tsx`:**
   - Small inline badge showing plan name (e.g., "Pro", "Free", "Enterprise")
   - Click opens modal with: plan details, usage bars (teachers used/max, courses used/max, storage used/max), upgrade button
   - Replace current large plan card in dashboard

3. **Update `DashboardPage.tsx`:**
   - Replace recent activity timeline with `<DeadlinesCalendar />`
   - Replace plan card with `<PlanBadge />`
   - Update top performers calculation: fetch real data from progress/submission endpoints
   - Add tooltips to all quick action buttons and stats
   - Fix layout: calendar left, top performers right

4. **Backend (if needed):**
   - Endpoint: `GET /api/v1/dashboard/deadlines/?month=2026-04` returning dates with deadline items
   - Can aggregate from Course.deadline, Assignment.due_date, Certification expiry

5. **Verify:** Dashboard renders correctly, calendar shows data, plan badge opens modal.

---

## Phase 3B: Courses & AI (Agent 4)

**Goal:** Integrate AI generation into course editor, add file picker, lesson planner.

### Steps:

1. **Create `components/courses/AIGenerationPanel.tsx`:**
   - Panel within course editor (tab or expandable section)
   - Two input modes: PDF upload OR topic text description
   - "Generate" button triggers AI analysis
   - Results display: lesson outline, quiz questions (grouped by difficulty), assignment prompts
   - "Apply" buttons to add generated content as modules/content items
   - Loading states, error handling

2. **Create `components/courses/LessonPlanner.tsx`:**
   - Analyzes uploaded document or topic
   - Generates: learning objectives, content breakdown into scenes, activity sequence
   - Displays structured outline with drag-to-reorder
   - "Create Modules" button converts outline into actual course modules

3. **Create `components/courses/FilePicker.tsx`:**
   - Modal file browser for selecting existing uploads
   - Search, filter by type (images, documents, videos)
   - Shows thumbnails/icons, file name, size, upload date
   - Select → inserts into current content item
   - Replaces need for standalone Media Library page

4. **Update `CourseEditorPage.tsx` and `course-editor/*`:**
   - Add "Generate with AI" tab/button in editor toolbar
   - Add file picker button in content upload areas
   - Add course activity tab showing recent progress/submissions for this course

5. **Backend:**
   - New endpoint: `POST /api/v1/courses/{id}/ai/lesson-plan/`
     - Accepts: `file` (PDF) or `topic` (text)
     - Returns: structured lesson plan JSON
   - Existing assignment generation endpoint stays as-is

6. **Verify:** Can generate content from PDF/topic, file picker works, no regressions in course editing.

---

## Phase 3C: Certifications (Agent 5)

**Goal:** Add 3-tab layout with Approvals and IB Dashboard.

### Steps:

1. **Create `components/certifications/ApprovalsTab.tsx`:**
   - Port UI logic from deleted `SkipRequestsPage.tsx`
   - Sub-tabs: All / Pending / Approved / Rejected
   - Add course-wise dropdown filter at top
   - Use existing `adminService.listSkipRequests()` and `adminService.reviewSkipRequest()`
   - Approve/Reject actions with confirmation dialog

2. **Create `components/certifications/IBDashboard.tsx`:**
   - School-level IB compliance view
   - Metrics: % teachers certified per required cert, overall compliance score
   - Ranking/comparison data (if multi-school data available via super admin)
   - Table: certification name, required count, certified count, compliance %

3. **Update `CertificationsPage.tsx`:**
   - Add tab bar: Certifications | Approvals | IB Dashboard
   - Default tab: Certifications (current content)
   - Approvals tab renders `<ApprovalsTab />`
   - IB Dashboard tab renders `<IBDashboard />`

4. **Backend:**
   - New endpoint: `GET /api/v1/certifications/ib-dashboard/`
     - Returns compliance metrics per certification for current tenant
   - Ensure skip request endpoints work correctly with course filter param

5. **Verify:** All 3 tabs render, approvals workflow works end-to-end, IB dashboard shows data.

---

## Phase 3D: Analytics & Reports (Agent 6)

**Goal:** Add new charts, merge Reports as drill-down.

### Steps:

1. **Create new chart components in `components/analytics/`:**
   - `DeadlineAdherenceChart.tsx` — line chart: % teachers meeting deadlines over time
   - `CertComplianceChart.tsx` — bar chart: compliance % per required certification
   - `ApprovalTrendsChart.tsx` — stacked bar: skip requests volume + approval rate over time
   - `CourseEffectivenessChart.tsx` — scatter plot: completion rate vs avg score per course

2. **Create `components/analytics/ReportDrillDown.tsx`:**
   - Extracted from `ReportsPage.tsx`
   - Tabular data view with sorting, filtering
   - Export buttons: CSV, PDF
   - Opens as expandable section or modal from each chart's "Details" button

3. **Update `AnalyticsPage.tsx`:**
   - Add new chart components to layout
   - Each chart has a "View Details" or "Export" button → opens drill-down
   - Remove any links to old Reports page
   - Responsive grid layout for charts

4. **Backend:**
   - `GET /api/v1/analytics/deadline-adherence/?period=30d`
   - `GET /api/v1/analytics/cert-compliance/`
   - `GET /api/v1/analytics/approval-trends/?period=90d`
   - `GET /api/v1/analytics/course-effectiveness/`
   - Each returns chart-ready data (labels, datasets)

5. **Verify:** All charts render with real or placeholder data, drill-down opens and exports work.

---

## Phase 3E: Reminders & Search (Agent 7)

**Goal:** Redesign reminders with automation, build command palette.

### Steps:

**Reminders:**

1. **Create `components/reminders/RulesSection.tsx`:**
   - List of automated reminder rules
   - Pre-configured smart defaults (deadline 3-day, 1-day; weekly incomplete digest; cert expiry 30-day, 7-day; assignment overdue 1-day, 3-day)
   - Toggle on/off per rule
   - Edit trigger days
   - Add custom rule

2. **Create `components/reminders/ManualSendSection.tsx`:**
   - Recipient picker: individual teachers, groups, or all
   - Message editor
   - Send now or schedule for later

3. **Create `components/reminders/HistorySection.tsx`:**
   - Log of all sent reminders (automated + manual)
   - Columns: date, type, recipients, subject, status
   - Filter by date range, type, recipient

4. **Update `RemindersPage.tsx`:**
   - 3-section layout: Rules | Manual Send | History
   - Tab or accordion layout

5. **Backend:**
   - New model: `ReminderRule` (type, trigger_days, is_active, tenant, created_at)
   - Migration for new model
   - Celery beat task: `evaluate_reminder_rules` — runs daily, checks rules, creates reminders
   - API: `GET/POST/PATCH/DELETE /api/v1/reminders/rules/`
   - API: `GET /api/v1/reminders/history/`

**Search / Command Palette:**

6. **Create `components/shared/CommandPalette.tsx`:**
   - Modal overlay triggered by Cmd+K / Ctrl+K
   - Search input with debounced API call
   - Categorized results: Courses, Teachers, Groups, Certifications, Pages
   - Keyboard navigation (arrow keys + Enter)
   - Click result → navigate to item

7. **Update `TopNav.tsx`:**
   - Replace SearchBar with CommandPalette trigger button
   - Show "Search... ⌘K" in nav bar

8. **Backend:**
   - New endpoint: `GET /api/v1/search/?q=<query>`
   - Searches across: Course (title, description), User/Teacher (name, email), TeacherGroup (name), Certification (name)
   - Returns categorized results with type, id, title, url

9. **Verify:** Reminder rules CRUD works, auto-send fires, command palette searches across all models.

---

## Phase 3F: Billing & Settings (Agent 8)

**Goal:** Razorpay/UPI billing, settings reduction.

### Steps:

**Billing:**

1. **Create `services/razorpayService.ts`:**
   - Initialize Razorpay checkout
   - Handle payment success/failure callbacks
   - Verify payment signature

2. **Update `BillingPage.tsx`:**
   - Current plan display with usage metrics
   - Plan comparison cards (Free / Pro / Enterprise)
   - "Upgrade" button → Razorpay checkout modal
   - Payment methods: Credit/Debit Card, UPI, Net Banking
   - Invoice history table with download links

3. **Backend:**
   - `apps/billing/razorpay_service.py`: Create order, verify payment, handle webhooks
   - `apps/billing/views.py`: Add Razorpay order creation + webhook endpoint
   - `apps/billing/urls.py`: New routes for Razorpay flow
   - Install `razorpay` Python package
   - Environment vars: `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`

**Settings:**

4. **Update `SettingsPage.tsx`:**
   - Reduce to 3 sections: School Profile / Branding / Security
   - School Profile: name, email, phone, address, subdomain (read-only)
   - Branding: logo upload, primary color, secondary color, font family
   - Security: password policy, 2FA toggle, session timeout, SSO config
   - Remove all other sections

5. **Verify:** Razorpay checkout opens, test payment works (test mode), settings save correctly.

---

## Phase 4: Integration & Verification

**Goal:** Ensure everything works together, no broken imports or routes.

### Steps:

1. **Build check:** `npm run build` — must succeed with zero errors
2. **Route verification:** Navigate to all 9 sidebar items — each loads correctly
3. **Deleted page verification:** Old URLs return 404 or redirect
4. **Import audit:** No dangling imports to deleted files
5. **Console check:** Zero console errors during normal navigation
6. **Terminology check:** Search for "Guide" — zero user-facing occurrences
7. **Responsive check:** All pages render on mobile viewport
8. **API check:** All new endpoints return valid responses
9. **Test run:** Existing tests pass (`npm test`, `pytest`)

---

## Agent Communication File

Each agent updates `docs/superpowers/agent-state.md`:

```markdown
## Agent State

| Agent | Phase | Status | Files Changed | Notes |
|-------|-------|--------|---------------|-------|
| 1-nav-cleanup | 1 | pending | — | — |
| 2-terminology | 2 | pending | — | — |
| 3-dashboard | 3A | pending | — | — |
| 4-courses-ai | 3B | pending | — | — |
| 5-certifications | 3C | pending | — | — |
| 6-analytics | 3D | pending | — | — |
| 7-reminders-search | 3E | pending | — | — |
| 8-billing-settings | 3F | pending | — | — |
```

**Protocol:**
- Update status: `pending` → `in-progress` → `done`
- List all files changed in your column
- Note any blockers or cross-agent dependencies
- If you need something from another agent, add to Notes and wait for their status to be `done`

---

## Estimated Scope

| Agent | New Files | Modified Files | Deleted Files | Backend Changes |
|-------|-----------|---------------|---------------|-----------------|
| 1 | 4 extracted components | 3 (sidebar, routes, index) | 9 pages | None |
| 2 | 0 | ~15-20 files | 0 | None |
| 3 | 2 (calendar, plan badge) | 1 (dashboard) | 0 | 1 endpoint |
| 4 | 3 (AI panel, planner, picker) | 2-3 (editor files) | 0 | 1-2 endpoints |
| 5 | 2 (approvals tab, IB dashboard) | 1 (certifications) | 0 | 1 endpoint |
| 6 | 5 (4 charts + drill-down) | 1 (analytics) | 0 | 4 endpoints |
| 7 | 4 (3 reminder sections + palette) | 2 (reminders, topnav) | 0 | 3 endpoints + model |
| 8 | 1 (razorpay service) | 2 (billing, settings) | 0 | 2-3 endpoints + package |
| **Total** | **~21** | **~28** | **9** | **~14 endpoints** |
