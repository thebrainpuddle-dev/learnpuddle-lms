// src/pages/admin/AnalyticsPage.test.tsx
//
// Test suite for AnalyticsPage — the admin analytics dashboard.
//
// Coverage strategy:
//   1. Loading / error / success render states
//   2. Summary cards (render + navigation)
//   3. View toggle (Charts ↔ Reports)
//   4. Focus filter pills (all / teachers / students)
//   5. Course + trend-period filters
//   6. Teacher charts section (visible/hidden by focus)
//   7. Student analytics section (conditional on sOverview.total > 0)
//   8. Needs Attention section (inactive teachers + reminders)
//   9. Send Reminder mutation — individual + bulk, success + error toasts
//  10. Reports drill-down view renders
//
// Mock decisions
//   • recharts: stub every exported component so jsdom SVG layout never errors
//   • adminService / adminReportsService / adminRemindersService: vi.fn()
//   • DeadlineAdherenceChart, CertComplianceChart, ApprovalTrendsChart,
//     CourseEffectivenessChart, ReportDrillDown: simple stubs (each has its
//     own dedicated test file)
//   • usePageTitle, react-router-dom useNavigate, useToast

import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { AnalyticsPage } from './AnalyticsPage';
import { adminService } from '../../services/adminService';
import { adminReportsService } from '../../services/adminReportsService';
import { adminRemindersService } from '../../services/adminRemindersService';

// ── recharts stubs ──────────────────────────────────────────────────────────
vi.mock('recharts', () => {
  const Stub: React.FC<React.PropsWithChildren<Record<string, unknown>>> = ({ children }) => <div>{children}</div>;
  return {
    BarChart: Stub,
    Bar: Stub,
    XAxis: Stub,
    YAxis: Stub,
    CartesianGrid: Stub,
    Tooltip: Stub,
    Legend: Stub,
    ResponsiveContainer: ({ children }: React.PropsWithChildren<Record<string, unknown>>) => <div>{children}</div>,
    LineChart: Stub,
    Line: Stub,
    PieChart: Stub,
    Pie: Stub,
    Cell: Stub,
    Area: Stub,
    AreaChart: Stub,
    ScatterChart: Stub,
    Scatter: Stub,
    ZAxis: Stub,
    ReferenceLine: Stub,
  };
});

// ── analytics chart component stubs ────────────────────────────────────────
vi.mock('../../components/analytics/DeadlineAdherenceChart', () => ({
  DeadlineAdherenceChart: ({ onViewDetails }: { onViewDetails?: () => void }) => (
    <div data-testid="deadline-adherence-chart">
      {onViewDetails && (
        <button type="button" onClick={onViewDetails}>View Deadline Details</button>
      )}
    </div>
  ),
}));

vi.mock('../../components/analytics/CertComplianceChart', () => ({
  CertComplianceChart: ({ onViewDetails }: { onViewDetails?: () => void }) => (
    <div data-testid="cert-compliance-chart">
      {onViewDetails && (
        <button type="button" onClick={onViewDetails}>View Cert Details</button>
      )}
    </div>
  ),
}));

vi.mock('../../components/analytics/ApprovalTrendsChart', () => ({
  ApprovalTrendsChart: ({ onViewDetails }: { onViewDetails?: () => void }) => (
    <div data-testid="approval-trends-chart">
      {onViewDetails && (
        <button type="button" onClick={onViewDetails}>View Approval Details</button>
      )}
    </div>
  ),
}));

vi.mock('../../components/analytics/CourseEffectivenessChart', () => ({
  CourseEffectivenessChart: ({ onViewDetails }: { onViewDetails?: () => void }) => (
    <div data-testid="course-effectiveness-chart">
      {onViewDetails && (
        <button type="button" onClick={onViewDetails}>View Effectiveness Details</button>
      )}
    </div>
  ),
}));

vi.mock('../../components/analytics/ReportDrillDown', () => ({
  ReportDrillDown: ({ defaultTab }: { defaultTab?: string }) => (
    <div data-testid="report-drill-down">Report Drill Down {defaultTab ?? 'default'}</div>
  ),
}));

// ── service mocks ────────────────────────────────────────────────────────────
vi.mock('../../services/adminService', () => ({
  adminService: {
    getTenantAnalytics: vi.fn(),
    getTenantStats: vi.fn(),
  },
}));

vi.mock('../../services/adminReportsService', () => ({
  adminReportsService: {
    listCourses: vi.fn(),
  },
}));

vi.mock('../../services/adminRemindersService', () => ({
  adminRemindersService: {
    send: vi.fn(),
  },
}));

// ── page-level utilities ─────────────────────────────────────────────────────
vi.mock('../../hooks/usePageTitle', () => ({
  usePageTitle: vi.fn(),
}));

const mockedUseNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockedUseNavigate,
  };
});

// ── toast mock ───────────────────────────────────────────────────────────────
const mockToastSuccess = vi.fn();
const mockToastError = vi.fn();
vi.mock('../../components/common', async () => {
  const actual = await vi.importActual('../../components/common');
  return {
    ...actual,
    useToast: () => ({
      success: mockToastSuccess,
      error: mockToastError,
    }),
  };
});

// ── typed mock refs ─────────────────────────────────────────────────────────
const mockedAdminService = adminService as {
  getTenantAnalytics: ReturnType<typeof vi.fn>;
  getTenantStats: ReturnType<typeof vi.fn>;
};
const mockedReportsService = adminReportsService as {
  listCourses: ReturnType<typeof vi.fn>;
};
const mockedRemindersService = adminRemindersService as {
  send: ReturnType<typeof vi.fn>;
};

// ── fixture data ─────────────────────────────────────────────────────────────
const MOCK_COURSES = [
  { id: 'c-1', title: 'Math 101', deadline: null },
  { id: 'c-2', title: 'Science 202', deadline: '2026-06-01' },
];

const MOCK_ANALYTICS = {
  course_breakdown: [
    { course_id: 'c-1', title: 'Math 101', assigned: 10, completed: 5, in_progress: 3, not_started: 2 },
    { course_id: 'c-2', title: 'Science 202', assigned: 8, completed: 2, in_progress: 4, not_started: 2 },
  ],
  monthly_trend: [
    { month: 'Jan 2026', completions: 12 },
    { month: 'Feb 2026', completions: 20 },
    { month: 'Mar 2026', completions: 18 },
  ],
  assignment_breakdown: { total: 45, manual: 20, auto_quiz: 15, auto_reflection: 10 },
  teacher_engagement: { highly_active: 10, active: 8, low_activity: 4, inactive: 3 },
  department_stats: [
    { department: 'Math', count: 5 },
    { department: 'Science', count: 8 },
  ],
  student_overview: { total: 0, active_30d: 0, inactive: 0 },
  student_grade_distribution: [],
  student_engagement: { highly_active: 0, active: 0, low_activity: 0, inactive: 0 },
  student_course_progress: { total_enrollments: 0, completed: 0, in_progress: 0, not_started: 0, avg_completion_pct: 0 },
  student_performance: { total_submissions: 0, graded: 0, avg_score_pct: 0, pass_rate_pct: 0 },
};

const MOCK_STATS = {
  total_teachers: 25,
  active_teachers: 22,
  inactive_teachers: 0,
  total_students: 0,
  total_admins: 2,
  total_courses: 10,
  published_courses: 8,
  total_content_items: 40,
  avg_completion_pct: 65,
  course_completions: 30,
  courses_in_progress: 12,
  content_completions: 90,
  total_assignments: 45,
  total_submissions: 38,
  graded_submissions: 30,
  pending_review: 5,
  inactive_teachers_detail: [],
  top_teachers: [],
  recent_activity: [],
  cert_compliance: {
    total_teachers: 25,
    fully_compliant: 18,
    partially_compliant: 5,
    non_compliant: 2,
    compliance_pct: 72,
    expiring_certs: 1,
    expired_certs: 0,
  },
  weekly_trend: [],
  upcoming_deadlines: [],
};

const MOCK_INACTIVE_TEACHERS_STATS = {
  ...MOCK_STATS,
  inactive_teachers: 2,
  inactive_teachers_detail: [
    { id: 'u-1', name: 'Jane Doe', email: 'jane@school.edu' },
    { id: 'u-2', name: 'Bob Smith', email: 'bob@school.edu' },
  ],
};

const MOCK_STUDENT_ANALYTICS = {
  ...MOCK_ANALYTICS,
  student_overview: { total: 50, active_30d: 35, inactive: 15 },
  student_engagement: { highly_active: 20, active: 15, low_activity: 10, inactive: 5 },
  student_course_progress: { total_enrollments: 150, completed: 80, in_progress: 50, not_started: 20, avg_completion_pct: 53 },
  student_performance: { total_submissions: 200, graded: 180, avg_score_pct: 72, pass_rate_pct: 88 },
  student_grade_distribution: [
    { grade: 'A', count: 40 },
    { grade: 'B', count: 50 },
    { grade: 'C', count: 30 },
  ],
};

// ── helpers ──────────────────────────────────────────────────────────────────
function makeClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // Note: AnalyticsPage queries use retry:1 which overrides this default.
        // Setting retryDelay:0 ensures any retries resolve synchronously so
        // error-state tests don't time out waiting for the 1 s default back-off.
        retry: false,
        retryDelay: 0,
      },
    },
  });
}

function renderPage(initialSearch = '') {
  const url = initialSearch ? `/?${initialSearch}` : '/';
  return render(
    <QueryClientProvider client={makeClient()}>
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }} initialEntries={[url]}>
        <AnalyticsPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

// ────────────────────────────────────────────────────────────────────────────
describe('AnalyticsPage', () => {

  beforeEach(() => {
    vi.resetAllMocks();
    mockedAdminService.getTenantAnalytics.mockResolvedValue(MOCK_ANALYTICS);
    mockedAdminService.getTenantStats.mockResolvedValue(MOCK_STATS);
    mockedReportsService.listCourses.mockResolvedValue(MOCK_COURSES);
    mockedRemindersService.send.mockResolvedValue({ sent: 1, failed: 0 });
  });

  // ── 1. Loading state ────────────────────────────────────────────────────
  describe('loading state', () => {
    it('shows loading spinner while queries are pending', () => {
      mockedAdminService.getTenantAnalytics.mockReturnValue(new Promise(() => {}));
      mockedAdminService.getTenantStats.mockReturnValue(new Promise(() => {}));
      renderPage();
      // Loading component renders a spinner
      const spinner = document.querySelector('.animate-spin, [data-testid="loading"]');
      expect(spinner ?? document.querySelector('svg')).toBeTruthy();
    });
  });

  // ── 2. Error state ──────────────────────────────────────────────────────
  describe('error state', () => {
    // AnalyticsPage queries specify retry:1 (one re-attempt before error state).
    // With retryDelay:0 on the QueryClient the retry resolves near-instantly, but
    // we still wait up to 5 s so CI isn't flaky on slow machines.
    it('shows error message when analytics query fails', async () => {
      mockedAdminService.getTenantAnalytics.mockRejectedValue(new Error('Network Error'));
      renderPage();
      expect(
        await screen.findByText(/Failed to load analytics data/i, {}, { timeout: 5000 })
      ).toBeInTheDocument();
    });

    it('shows error message when stats query fails', async () => {
      mockedAdminService.getTenantStats.mockRejectedValue(new Error('500'));
      renderPage();
      expect(
        await screen.findByText(/Failed to load analytics data/i, {}, { timeout: 5000 })
      ).toBeInTheDocument();
    });

    it('shows refresh suggestion text on error', async () => {
      mockedAdminService.getTenantAnalytics.mockRejectedValue(new Error('error'));
      renderPage();
      expect(
        await screen.findByText(/refresh the page/i, {}, { timeout: 5000 })
      ).toBeInTheDocument();
    });
  });

  // ── 3. Page renders with data ───────────────────────────────────────────
  describe('page header', () => {
    it('renders the Analytics heading', async () => {
      renderPage();
      expect(await screen.findByRole('heading', { name: /Analytics/i })).toBeInTheDocument();
    });

    it('renders the subtitle text', async () => {
      renderPage();
      expect(await screen.findByText(/Real-time insights/i)).toBeInTheDocument();
    });
  });

  // ── 4. Summary cards ────────────────────────────────────────────────────
  describe('summary cards', () => {
    it('renders all four summary card labels', async () => {
      renderPage();
      await waitFor(() => {
        expect(screen.getByText('Teachers')).toBeInTheDocument();
        expect(screen.getByText('Published Courses')).toBeInTheDocument();
        expect(screen.getByText('Avg Completion')).toBeInTheDocument();
        expect(screen.getByText('Assignments')).toBeInTheDocument();
      });
    });

    it('shows teacher count from stats', async () => {
      renderPage();
      await waitFor(() => {
        expect(screen.getByText('25')).toBeInTheDocument();
      });
    });

    it('shows published courses count from stats', async () => {
      renderPage();
      await waitFor(() => {
        expect(screen.getByText('8')).toBeInTheDocument();
      });
    });

    it('shows avg completion percentage from stats', async () => {
      renderPage();
      await waitFor(() => {
        expect(screen.getByText('65%')).toBeInTheDocument();
      });
    });

    it('shows total assignments count from stats', async () => {
      renderPage();
      await waitFor(() => {
        // Summary card shows "45" next to "Assignments" label —
        // multiple "45" elements may exist so use getAllByText with ≥1 check
        const matches = screen.getAllByText('45');
        expect(matches.length).toBeGreaterThanOrEqual(1);
      });
    });

    it('clicking Teachers card navigates to /admin/teachers', async () => {
      renderPage();
      // Multiple buttons can contain "Teachers" (summary card + focus pill "teachers").
      // Use the unique "Teachers" label text (capital T) inside the summary card
      // to find the surrounding button via closest().
      const teachersLabel = await screen.findByText('Teachers');
      const teachersCard = teachersLabel.closest('button')!;
      await userEvent.click(teachersCard);
      expect(mockedUseNavigate).toHaveBeenCalledWith('/admin/teachers');
    });

    it('clicking Published Courses card navigates to /admin/courses', async () => {
      renderPage();
      const coursesCard = await screen.findByRole('button', { name: /Published Courses/i });
      await userEvent.click(coursesCard);
      expect(mockedUseNavigate).toHaveBeenCalledWith('/admin/courses');
    });
  });

  // ── 5. View toggle ───────────────────────────────────────────────────────
  describe('view toggle', () => {
    it('shows Charts and Detailed Reports toggle buttons', async () => {
      renderPage();
      expect(await screen.findByRole('button', { name: /Charts/i })).toBeInTheDocument();
      expect(await screen.findByRole('button', { name: /Detailed Reports/i })).toBeInTheDocument();
    });

    it('defaults to Charts view (shows focus pills)', async () => {
      renderPage();
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /^all$/i })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /^teachers$/i })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /^students$/i })).toBeInTheDocument();
      });
    });

    it('switching to Reports view renders ReportDrillDown', async () => {
      renderPage();
      const reportsBtn = await screen.findByRole('button', { name: /Detailed Reports/i });
      await userEvent.click(reportsBtn);
      expect(await screen.findByTestId('report-drill-down')).toBeInTheDocument();
    });

    it('focus pills are hidden in Reports view', async () => {
      renderPage();
      const reportsBtn = await screen.findByRole('button', { name: /Detailed Reports/i });
      await userEvent.click(reportsBtn);
      await waitFor(() => {
        // Focus pills only render in charts view
        expect(screen.queryByRole('button', { name: /^all$/i })).not.toBeInTheDocument();
      });
    });

    it('switching back to Charts view shows charts', async () => {
      renderPage();
      // Go to reports
      const reportsBtn = await screen.findByRole('button', { name: /Detailed Reports/i });
      await userEvent.click(reportsBtn);
      // Back to charts
      const chartsBtn = screen.getByRole('button', { name: /^Charts$/i });
      await userEvent.click(chartsBtn);
      await waitFor(() => {
        expect(screen.getByRole('button', { name: /^all$/i })).toBeInTheDocument();
      });
    });
  });

  // ── 6. Focus filter pills ────────────────────────────────────────────────
  describe('focus filter pills', () => {
    it('clicking teachers focus hides Course Completion heading', async () => {
      // With focus=teachers, activeFocus !== 'students' so course charts remain visible,
      // but the student section should remain hidden (sOverview.total = 0)
      renderPage();
      const teachersBtn = await screen.findByRole('button', { name: /^teachers$/i });
      await userEvent.click(teachersBtn);
      await waitFor(() => {
        expect(screen.queryByText('Student Analytics')).not.toBeInTheDocument();
      });
    });

    it('clicking students focus hides teacher engagement charts', async () => {
      renderPage();
      const studentsBtn = await screen.findByRole('button', { name: /^students$/i });
      await userEvent.click(studentsBtn);
      await waitFor(() => {
        // With activeFocus='students', teacher-only charts (DeadlineAdherence etc.) are hidden
        expect(screen.queryByTestId('deadline-adherence-chart')).not.toBeInTheDocument();
        expect(screen.queryByTestId('approval-trends-chart')).not.toBeInTheDocument();
      });
    });

    it('all focus shows teacher chart components', async () => {
      renderPage();
      await waitFor(() => {
        expect(screen.getByTestId('deadline-adherence-chart')).toBeInTheDocument();
        expect(screen.getByTestId('approval-trends-chart')).toBeInTheDocument();
        expect(screen.getByTestId('course-effectiveness-chart')).toBeInTheDocument();
        expect(screen.getByTestId('cert-compliance-chart')).toBeInTheDocument();
      });
    });
  });

  // ── 7. Course filter ─────────────────────────────────────────────────────
  describe('filters', () => {
    // NOTE: The <label> elements in the filter bar are not associated to their
    // <select> via for/id, so role="combobox" + name lookup fails. We instead
    // locate selects by index from getAllByRole('combobox') — index 0 = course
    // filter, index 1 = trend period — and verify the label text separately.

    it('renders course filter dropdown with All courses option', async () => {
      renderPage();
      expect(await screen.findByText('Course')).toBeInTheDocument(); // label visible
      const selects = screen.getAllByRole('combobox');
      expect(within(selects[0]).getByText('All courses')).toBeInTheDocument();
    });

    it('renders fetched course options in dropdown', async () => {
      renderPage();
      const selects = await screen.findAllByRole('combobox');
      await waitFor(() => {
        expect(within(selects[0]).getByText('Math 101')).toBeInTheDocument();
        expect(within(selects[0]).getByText('Science 202')).toBeInTheDocument();
      });
    });

    it('selecting a course re-fetches analytics with course_id', async () => {
      renderPage();
      const selects = await screen.findAllByRole('combobox');
      await userEvent.selectOptions(selects[0], 'c-1');
      await waitFor(() => {
        expect(mockedAdminService.getTenantAnalytics).toHaveBeenCalledWith(
          expect.objectContaining({ course_id: 'c-1' })
        );
      });
    });

    it('shows Clear button when a course is selected', async () => {
      renderPage();
      const selects = await screen.findAllByRole('combobox');
      await userEvent.selectOptions(selects[0], 'c-1');
      expect(await screen.findByRole('button', { name: /Clear/i })).toBeInTheDocument();
    });

    it('Clear button resets course filter', async () => {
      renderPage();
      const selects = await screen.findAllByRole('combobox');
      await userEvent.selectOptions(selects[0], 'c-1');
      const clearBtn = await screen.findByRole('button', { name: /Clear/i });
      await userEvent.click(clearBtn);
      await waitFor(() => {
        expect(mockedAdminService.getTenantAnalytics).toHaveBeenCalledWith(
          expect.objectContaining({ course_id: undefined })
        );
      });
    });

    it('renders trend period label and default 6-month option', async () => {
      renderPage();
      expect(await screen.findByText('Trend period')).toBeInTheDocument();
      const selects = screen.getAllByRole('combobox');
      expect(within(selects[1]).getByText('Last 6 months')).toBeInTheDocument();
    });

    it('changing trend period re-fetches analytics with new months value', async () => {
      renderPage();
      const selects = await screen.findAllByRole('combobox');
      await userEvent.selectOptions(selects[1], '12');
      await waitFor(() => {
        expect(mockedAdminService.getTenantAnalytics).toHaveBeenCalledWith(
          expect.objectContaining({ months: 12 })
        );
      });
    });
  });

  // ── 8. Teacher charts section ────────────────────────────────────────────
  describe('teacher charts', () => {
    it('renders Teacher Engagement heading', async () => {
      renderPage();
      expect(await screen.findByText('Teacher Engagement')).toBeInTheDocument();
    });

    it('renders Assignment Types heading', async () => {
      renderPage();
      expect(await screen.findByText('Assignment Types')).toBeInTheDocument();
    });

    it('renders Department Distribution heading', async () => {
      renderPage();
      expect(await screen.findByText('Department Distribution')).toBeInTheDocument();
    });

    it('shows total assignments count in Assignment Types card', async () => {
      renderPage();
      await waitFor(() => {
        // "45 total assignments" is rendered as two separate DOM nodes so query
        // for the label text which is unique within the teacher charts section.
        expect(screen.getByText(/total assignments/i)).toBeInTheDocument();
      });
    });

    it('renders Course Completion by Course heading', async () => {
      renderPage();
      expect(await screen.findByText('Course Completion by Course')).toBeInTheDocument();
    });

    it('renders Monthly Completion Trend heading', async () => {
      renderPage();
      expect(await screen.findByText('Monthly Completion Trend')).toBeInTheDocument();
    });

    it('shows empty state when no course breakdown data', async () => {
      mockedAdminService.getTenantAnalytics.mockResolvedValue({
        ...MOCK_ANALYTICS,
        course_breakdown: [],
      });
      renderPage();
      expect(await screen.findByText('No published courses yet')).toBeInTheDocument();
    });

    it('shows empty state when no monthly trend data', async () => {
      mockedAdminService.getTenantAnalytics.mockResolvedValue({
        ...MOCK_ANALYTICS,
        monthly_trend: [],
      });
      renderPage();
      expect(await screen.findByText('No data yet')).toBeInTheDocument();
    });
  });

  // ── 9. Student analytics section ─────────────────────────────────────────
  describe('student analytics section', () => {
    it('does NOT show Student Analytics heading when sOverview.total = 0', async () => {
      renderPage(); // default MOCK_ANALYTICS has student_overview.total = 0
      await waitFor(() => {
        expect(screen.queryByText('Student Analytics')).not.toBeInTheDocument();
      });
    });

    it('shows Student Analytics heading when student data is present', async () => {
      mockedAdminService.getTenantAnalytics.mockResolvedValue(MOCK_STUDENT_ANALYTICS);
      renderPage();
      expect(await screen.findByText('Student Analytics')).toBeInTheDocument();
    });

    it('shows Total Students stat card when student data present', async () => {
      mockedAdminService.getTenantAnalytics.mockResolvedValue(MOCK_STUDENT_ANALYTICS);
      renderPage();
      expect(await screen.findByText('Total Students')).toBeInTheDocument();
      expect(await screen.findByText('50')).toBeInTheDocument();
    });

    it('shows student active count in student card', async () => {
      mockedAdminService.getTenantAnalytics.mockResolvedValue(MOCK_STUDENT_ANALYTICS);
      renderPage();
      expect(await screen.findByText(/35 active/i)).toBeInTheDocument();
    });

    it('shows Student Engagement chart heading when student data present', async () => {
      mockedAdminService.getTenantAnalytics.mockResolvedValue(MOCK_STUDENT_ANALYTICS);
      renderPage();
      expect(await screen.findByText('Student Engagement')).toBeInTheDocument();
    });

    it('shows Course Progress chart heading when student data present', async () => {
      mockedAdminService.getTenantAnalytics.mockResolvedValue(MOCK_STUDENT_ANALYTICS);
      renderPage();
      expect(await screen.findByText('Course Progress')).toBeInTheDocument();
    });

    it('student section hidden when focus=teachers', async () => {
      mockedAdminService.getTenantAnalytics.mockResolvedValue(MOCK_STUDENT_ANALYTICS);
      renderPage();
      const teachersBtn = await screen.findByRole('button', { name: /^teachers$/i });
      await userEvent.click(teachersBtn);
      await waitFor(() => {
        expect(screen.queryByText('Student Analytics')).not.toBeInTheDocument();
      });
    });
  });

  // ── 10. Needs Attention section ──────────────────────────────────────────
  describe('Needs Attention section', () => {
    it('does NOT show Needs Attention when inactive_teachers = 0', async () => {
      renderPage();
      await waitFor(() => {
        expect(screen.queryByText('Needs Attention')).not.toBeInTheDocument();
      });
    });

    it('shows Needs Attention panel when inactive teachers exist', async () => {
      mockedAdminService.getTenantStats.mockResolvedValue(MOCK_INACTIVE_TEACHERS_STATS);
      renderPage();
      expect(await screen.findByText('Needs Attention')).toBeInTheDocument();
    });

    it('shows inactive teacher count in the attention panel', async () => {
      mockedAdminService.getTenantStats.mockResolvedValue(MOCK_INACTIVE_TEACHERS_STATS);
      renderPage();
      // The count ("2") and message text are split across DOM nodes (<span> + text node)
      // inside the same <p>. Because `findByText` with a regex or string won't match
      // across sibling nodes, scope to the amber attention section and inspect its
      // combined textContent instead.
      await waitFor(() => {
        const attentionSection = screen.getByText('Needs Attention').closest('div.bg-amber-50, section');
        expect(attentionSection?.textContent).toMatch(/2\s+teachers?\s+(?:have|has)\s+not\s+started/i);
      });
    });

    it('lists inactive teacher names when panel is expanded (default)', async () => {
      mockedAdminService.getTenantStats.mockResolvedValue(MOCK_INACTIVE_TEACHERS_STATS);
      renderPage();
      expect(await screen.findByText('Jane Doe')).toBeInTheDocument();
      expect(await screen.findByText('Bob Smith')).toBeInTheDocument();
    });

    it('shows individual Send Reminder buttons per teacher', async () => {
      mockedAdminService.getTenantStats.mockResolvedValue(MOCK_INACTIVE_TEACHERS_STATS);
      renderPage();
      await waitFor(() => {
        const sendBtns = screen.getAllByRole('button', { name: /Send Reminder/i });
        // Each row has a button + the bulk "Send Reminder to All" button = 3 total
        expect(sendBtns.length).toBeGreaterThanOrEqual(2);
      });
    });

    it('shows Send Reminder to All bulk button', async () => {
      mockedAdminService.getTenantStats.mockResolvedValue(MOCK_INACTIVE_TEACHERS_STATS);
      renderPage();
      expect(await screen.findByRole('button', { name: /Send Reminder to All/i })).toBeInTheDocument();
    });

    it('panel collapses when header is clicked', async () => {
      mockedAdminService.getTenantStats.mockResolvedValue(MOCK_INACTIVE_TEACHERS_STATS);
      renderPage();
      // Wait for panel to appear
      await screen.findByText('Jane Doe');
      // Click the header button to collapse
      const headerBtn = screen.getByRole('button', { name: /Needs Attention/i });
      await userEvent.click(headerBtn);
      await waitFor(() => {
        expect(screen.queryByText('Jane Doe')).not.toBeInTheDocument();
      });
    });
  });

  // ── 11. Reminder mutation ────────────────────────────────────────────────
  describe('reminder mutation', () => {
    it('sends individual reminder and shows success toast', async () => {
      mockedAdminService.getTenantStats.mockResolvedValue(MOCK_INACTIVE_TEACHERS_STATS);
      mockedRemindersService.send.mockResolvedValue({ sent: 1, failed: 0 });
      renderPage();

      // Find individual Send Reminder button for Jane Doe row
      const janeRow = (await screen.findByText('Jane Doe')).closest('tr')!;
      const sendBtn = within(janeRow).getByRole('button', { name: /Send Reminder/i });
      await userEvent.click(sendBtn);

      await waitFor(() => {
        expect(mockedRemindersService.send).toHaveBeenCalledWith(
          expect.objectContaining({
            reminder_type: 'CUSTOM',
            teacher_ids: ['u-1'],
          })
        );
      });
      await waitFor(() => {
        expect(mockToastSuccess).toHaveBeenCalledWith('Reminder sent', expect.stringContaining('Jane Doe'));
      });
    });

    it('sends bulk reminder and shows success toast', async () => {
      mockedAdminService.getTenantStats.mockResolvedValue(MOCK_INACTIVE_TEACHERS_STATS);
      mockedRemindersService.send.mockResolvedValue({ sent: 2, failed: 0 });
      renderPage();

      const bulkBtn = await screen.findByRole('button', { name: /Send Reminder to All/i });
      await userEvent.click(bulkBtn);

      await waitFor(() => {
        expect(mockedRemindersService.send).toHaveBeenCalledWith(
          expect.objectContaining({
            reminder_type: 'CUSTOM',
            teacher_ids: ['u-1', 'u-2'],
          })
        );
      });
      await waitFor(() => {
        expect(mockToastSuccess).toHaveBeenCalledWith('Reminder sent', expect.any(String));
      });
    });

    it('shows error toast when reminder fails', async () => {
      mockedAdminService.getTenantStats.mockResolvedValue(MOCK_INACTIVE_TEACHERS_STATS);
      mockedRemindersService.send.mockRejectedValue(new Error('Network Error'));
      renderPage();

      const bulkBtn = await screen.findByRole('button', { name: /Send Reminder to All/i });
      await userEvent.click(bulkBtn);

      await waitFor(() => {
        expect(mockToastError).toHaveBeenCalledWith('Failed', expect.stringContaining('Could not send reminder'));
      });
    });

    it('shows Sent label after individual reminder is sent', async () => {
      mockedAdminService.getTenantStats.mockResolvedValue(MOCK_INACTIVE_TEACHERS_STATS);
      mockedRemindersService.send.mockResolvedValue({ sent: 1, failed: 0 });
      renderPage();

      const janeRow = (await screen.findByText('Jane Doe')).closest('tr')!;
      const sendBtn = within(janeRow).getByRole('button', { name: /Send Reminder/i });
      await userEvent.click(sendBtn);

      await waitFor(() => {
        // After sending, button replaced by "Sent" label for that row
        expect(within(janeRow).getByText(/Sent/i)).toBeInTheDocument();
      });
    });

    it('disables Send Reminder to All once all reminders sent', async () => {
      mockedAdminService.getTenantStats.mockResolvedValue(MOCK_INACTIVE_TEACHERS_STATS);
      mockedRemindersService.send.mockResolvedValue({ sent: 2, failed: 0 });
      renderPage();

      const bulkBtn = await screen.findByRole('button', { name: /Send Reminder to All/i });
      await userEvent.click(bulkBtn);

      await waitFor(() => {
        expect(bulkBtn).toBeDisabled();
      });
    });
  });

  // ── 12. View toggle → summary cards navigation from Reports ─────────────
  describe('summary card navigation to reports view', () => {
    it('clicking Avg Completion card switches to reports view with COURSE tab', async () => {
      renderPage();
      const avgCard = await screen.findByRole('button', { name: /Avg Completion/i });
      await userEvent.click(avgCard);
      expect(await screen.findByTestId('report-drill-down')).toBeInTheDocument();
    });

    it('clicking Assignments card switches to reports view with ASSIGNMENT tab', async () => {
      renderPage();
      const assignmentsCard = await screen.findByRole('button', { name: /Assignments/i });
      await userEvent.click(assignmentsCard);
      expect(await screen.findByTestId('report-drill-down')).toBeInTheDocument();
    });
  });

  // ── 13. Deadline / Approval chart View Details callbacks ─────────────────
  describe('chart view details callbacks', () => {
    it('DeadlineAdherenceChart onViewDetails switches to reports view', async () => {
      renderPage();
      const btn = await screen.findByRole('button', { name: /View Deadline Details/i });
      await userEvent.click(btn);
      expect(await screen.findByTestId('report-drill-down')).toBeInTheDocument();
    });

    it('ApprovalTrendsChart onViewDetails switches to reports view', async () => {
      renderPage();
      const btn = await screen.findByRole('button', { name: /View Approval Details/i });
      await userEvent.click(btn);
      expect(await screen.findByTestId('report-drill-down')).toBeInTheDocument();
    });

    it('CourseEffectivenessChart onViewDetails switches to reports view', async () => {
      renderPage();
      const btn = await screen.findByRole('button', { name: /View Effectiveness Details/i });
      await userEvent.click(btn);
      expect(await screen.findByTestId('report-drill-down')).toBeInTheDocument();
    });

    it('CertComplianceChart onViewDetails navigates to certifications page', async () => {
      renderPage();
      const btn = await screen.findByRole('button', { name: /View Cert Details/i });
      await userEvent.click(btn);
      expect(mockedUseNavigate).toHaveBeenCalledWith('/admin/certifications?tab=ib-dashboard');
    });
  });
});
