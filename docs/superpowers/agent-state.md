# Agent State — Admin Portal Redesign

**Spec:** `specs/2026-04-06-admin-portal-redesign-design.md`
**Plan:** `specs/2026-04-06-admin-portal-redesign-plan.md`

## Status

| Agent | Phase | Status | Files Changed | Notes |
|-------|-------|--------|---------------|-------|
| 1-nav-cleanup | 1 | done | See notes below | Phase 1 complete, no TS errors |
| 2-terminology | 2 | done | TeacherSidebar.tsx, DashboardPage.tsx, TopNav.tsx | All "Guide"→"Teacher" replacements complete, 0 TS errors |
| 3-dashboard | 3A | done | DashboardPage.tsx, components/dashboard/DeadlinesCalendar.tsx, components/dashboard/PlanBadge.tsx | Calendar, plan badge, top performers, tooltips — 0 TS errors |
| 4-courses-ai | 3B | done | CourseEditorPage.tsx, course-editor/types.ts, components/courses/AIGenerationPanel.tsx, components/courses/LessonPlanner.tsx, components/courses/CourseActivity.tsx | AI Tools: unified 4-step wizard (Input->Outline->Generate->Apply), LessonPlanner re-exports AIGenerationPanel, Apply-to-Course actually creates modules+content, 0 TS errors |
| 5-certifications | 3C | done | CertificationsPage.tsx, IBDashboard.tsx (new) | 3-tab layout with URL params, approvals + IB dashboard integrated, 0 TS errors |
| 6-analytics | 3D | done | AnalyticsPage.tsx + 4 new chart components | 4 charts + ReportDrillDown integration, 0 TS errors |
| 7-reminders-search | 3E | done | RemindersPage.tsx, TopNav.tsx, + 4 new components | Reminders 3-tab layout, CommandPalette (Cmd+K), 0 TS errors |
| 8-billing-settings | 3F | done | BillingPage.tsx, SettingsPage.tsx, services/razorpayService.ts | Razorpay + UPI billing, Settings reduced to 3 tabs, 0 TS errors |

## File Ownership

- **Agent 1:** `AdminSidebar.tsx`, `App.tsx`, `admin/index.ts`, all deleted page files
- **Agent 2:** Any file with "Guide"/"Guides" user-facing strings
- **Agent 3:** `DashboardPage.tsx`, `components/dashboard/*`
- **Agent 4:** `CourseEditorPage.tsx`, `course-editor/*`, `components/courses/*`
- **Agent 5:** `CertificationsPage.tsx`, `components/certifications/*`
- **Agent 6:** `AnalyticsPage.tsx`, `components/analytics/*`
- **Agent 7:** `RemindersPage.tsx`, `SearchBar.tsx`→`CommandPalette.tsx`, `TopNav.tsx`, `components/reminders/*`
- **Agent 8:** `BillingPage.tsx`, `SettingsPage.tsx`, `services/razorpayService.ts`

## Shared Components (created by agents, usable by all)

- `components/certifications/ApprovalsTab.tsx` — skip-request approval panel (from SkipRequestsPage)
- `components/analytics/ReportDrillDown.tsx` — course/assignment report table with CSV export (from ReportsPage)
- `components/courses/FilePicker.tsx` — media picker modal (from MediaLibraryPage)
- `components/courses/AIGenerationPanel.tsx` — Unified 4-step AI course generation wizard (Input->Outline Review->Content Generation->Review & Apply). Replaces old flat AIGenerationPanel + LessonPlanner with a single progressive flow that actually creates modules and content via `createModule()` / `createContent()` API calls.

## Agent 1 Completed Work

**Deleted pages (9):** SkipRequestsPage, ReportsPage, MediaLibraryPage, AICourseGeneratorPage, AIStudioPage, SkillsMatrixPage, GamificationSettingsPage, ManagerDashboardPage, AnnouncementsPage (+ ReportsPage.test.tsx)

**Extracted components (4):** ApprovalsTab, ReportDrillDown, FilePicker, AIGenerationPanel

**Updated navigation (3 files):**
- `components/layout/AdminSidebar.tsx` — 9 nav items (Dashboard, Courses, Teachers, Groups, Certifications, Analytics, Reminders, Billing, Settings)
- `design-system/layout/Sidebar.tsx` — matching 9-item ADMIN_NAV, cleaned unused imports
- `design-system/layout/TopNav.tsx` — removed deleted-page entries from ADMIN_NAV, cleaned unused imports

**Updated routing:**
- `App.tsx` — removed 7 lazy imports and 7 Route entries for deleted pages
- `pages/admin/index.ts` — removed 8 deleted-page exports, kept 10 valid exports

**Reference cleanup:**
- `config/opsRouteMap.ts` — removed /admin/media and /admin/announcements mappings, added certifications/billing
- `components/tour/tourConfig.ts` — removed admin-media and admin-announcements tour steps
- `components/tour/TourContext.test.tsx` — updated /admin/reports references to /admin/analytics
- `pages/admin/DashboardPage.tsx` — fixed AI Generator quick action href to /admin/courses/new
- `pages/admin/course-editor/ModuleContentEditor.tsx` — removed stale AI Studio link
- `pages/admin/AnalyticsPage.tsx` — redirected /admin/reports navigation to /admin/analytics (TODO for Agent 6)

**Verification:** `npx tsc --noEmit` passes with zero errors

## Agent 3 Completed Work

**New components (2):**
- `components/dashboard/DeadlinesCalendar.tsx` — Month-view grid calendar with dot indicators, click-to-expand detail panel. Mock data with TODO for API.
- `components/dashboard/PlanBadge.tsx` — Compact pill badge; click opens modal with usage bars + Manage/Upgrade Plan button. Escape/backdrop to close.

**Updated `DashboardPage.tsx`:**
- Replaced activity feed with `<DeadlinesCalendar />`
- Replaced large plan card with inline `<PlanBadge />` next to welcome heading
- Top performers show calculated score (completion + submission rates) with subtitle
- Added `title` tooltips on all stat cards, metric cards, quick actions, header button, performer rows
- Layout: Stats -> Metrics -> Quick Actions -> Calendar (col-7) + Top Performers (col-5)
- Removed unused imports and UsageBar sub-component

**Verification:** `npx tsc --noEmit` passes with zero errors

## Agent 6 Completed Work

**New chart components (4):**
- `components/analytics/DeadlineAdherenceChart.tsx` — Line chart: % teachers meeting deadlines over time, with summary stat
- `components/analytics/CertComplianceChart.tsx` — Horizontal bar chart: compliance % per certification, color-coded (green/yellow/red)
- `components/analytics/ApprovalTrendsChart.tsx` — Stacked bar chart: skip request volume (approved/rejected/pending) over time
- `components/analytics/CourseEffectivenessChart.tsx` — Scatter plot: completion rate vs avg score per course, bubble-sized by enrollment

**AnalyticsPage.tsx updates:**
- Added Charts/Reports view toggle (URL param `?view=reports`)
- Integrated `ReportDrillDown` component as drill-down tab with URL params (`tab`, `course_id`, `assignment_id`, `status`)
- Wired `goToReports()` to open the ReportDrillDown panel (resolved Agent 1's TODO)
- Added 4 new chart components in responsive 2-column grid (rows 3-4)
- Each chart has "View Details" button that switches to Reports drill-down
- All charts use `react-chartjs-2` (consistent with existing page)
- All charts use placeholder/mock data with TODO comments for API integration

**Verification:** `npx tsc --noEmit` passes with zero errors

## Agent 8 Completed Work

**New file created:**
- `services/razorpayService.ts` — Razorpay SDK loader, types (RazorpayOrder, RazorpayPaymentResponse, Plan, CurrentPlanInfo, Invoice), API service functions (getPlans, getCurrentPlan, createOrder, verifyPayment, getInvoices)

**BillingPage.tsx — full rewrite:**
- Removed Stripe-based billing (useBillingStore, billingService imports)
- Added Razorpay + UPI integration with dynamic SDK loading
- Current Plan section: plan name, status, renewal date, usage bars (teachers/courses/storage)
- Plan Comparison section: cards with INR pricing, features, limits, "Upgrade" button
- Razorpay checkout flow: createOrder -> open Razorpay modal -> verifyPayment -> refresh
- Invoice History section: table with date, invoice #, amount, GST, total, status, PDF download
- Payment methods banner (UPI, cards, net banking, wallets)
- All prices displayed in INR using Intl.NumberFormat

**SettingsPage.tsx — restructured to 3 tabs:**
- Tab 1 - School Profile: name, email, phone, address (editable), subdomain (read-only)
- Tab 2 - Branding: logo upload with preview, primary/secondary color pickers, font family selector, live preview
- Tab 3 - Security: password policy (min length, require uppercase/lowercase/numbers/special), 2FA toggle for all teachers, session timeout dropdown (30min-8hr), SSO config (enable/disable, provider selector, client ID/secret)
- Removed old "Account" section (status/plan display)
- Each section has its own Save button
- Security section uses local state with TODO endpoints for backend

**Verification:** `npx tsc --noEmit` passes with zero errors

## Agent 7 Completed Work

**New components created (4):**
- `components/reminders/RulesSection.tsx` — Automated reminder rules with toggle switches, inline trigger-day editing, 6 pre-configured defaults (DEADLINE_APPROACHING 3d/1d, COURSE_INCOMPLETE weekly, CERT_EXPIRING 30d/7d, ASSIGNMENT_OVERDUE 1d off by default), "Add Custom Rule" button
- `components/reminders/ManualSendSection.tsx` — One-off reminder composer with type selector, subject/message fields, teacher search/picker with chips, send-now vs schedule radio, preview panel, uses existing `adminRemindersService` API
- `components/reminders/HistorySection.tsx` — History log with filters (All/Manual/Automated), subject search, paginated table (date, type badge, subject, delivery counts, status), refresh button
- `components/shared/CommandPalette.tsx` — Platform-wide Cmd+K / Ctrl+K modal, debounced search (300ms), categorized results (Pages hardcoded, Courses/Content from API), keyboard navigation (arrow keys, Enter, Escape), click-outside-to-close, no external dependencies

**RemindersPage.tsx — full rewrite:**
- Replaced flat 2-column composer+history layout with 3-tab design (Rules / Manual Send / History)
- Tab navigation with icons (CpuChipIcon, PaperAirplaneIcon, ClockIcon)
- History auto-refreshes when user sends a reminder from Manual Send tab
- Removed all inline form logic (delegated to sub-components)

**TopNav.tsx updates:**
- Imported and rendered `CommandPalette` component
- Added `commandPaletteOpen` state + global `keydown` listener for Cmd+K / Ctrl+K
- Wired existing search button `onClick` to open the command palette
- Did NOT touch sidebar labels, role labels, or navigation items (owned by Agent 1/2)

**Verification:** `npx tsc --noEmit` passes with zero errors

## Agent 4 — AI Tools Rewrite (2026-04-06)

**AIGenerationPanel.tsx — full rewrite as 4-step wizard:**
- Step 1 (Input): Topic or PDF input with content type checkboxes (Lesson/Quiz/Interactive), quiz difficulty selector, drag-and-drop PDF zone
- Step 2 (Outline Review): Editable module cards with inline title/description editing, move up/down/delete, content type badges (click to cycle), expand/collapse, add module
- Step 3 (Content Generation): Progressive per-module generation using `aiService.generateContent()`, per-module status indicators (pending/generating/done/failed), overall progress bar, cancel support
- Step 4 (Review & Apply): Expandable preview of generated lesson text + quiz questions, **Apply to Course button that actually works** — calls `createModule()` then `createContent()` for each module with progress tracking, error handling per module, and course data invalidation on success
- Horizontal stepper with completed/active/future state indicators
- Fade transitions between steps
- Error states with inline red borders, not just toasts

**LessonPlanner.tsx — replaced with re-export:**
- `export { AIGenerationPanel as LessonPlanner }` for backwards compatibility

**CourseEditorPage.tsx updates:**
- Removed AI sub-tab toggle (no more "Generate with AI" / "Plan Lesson" tabs)
- Renders `<AIGenerationPanel />` directly with `courseId`, `onApplyComplete` (invalidates course query), `onSwitchTab` (switches to Content tab)
- Removed stub `handleApplyOutline` and `handleCreateModulesFromPlan` handlers (now handled inside AIGenerationPanel)
- Removed "Coming next" badge section (Drag-and-drop, Match-the-pairs) from Assignment Builder
- Removed unused imports (LessonPlanner, AcademicCapIcon, CourseOutline type)
- Added `useQueryClient` for course data invalidation after AI apply

**Verification:** `npx tsc --noEmit` passes with zero errors

## Blockers

_None yet_
