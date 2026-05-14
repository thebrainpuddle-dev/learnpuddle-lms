// src/pages/parent/ParentDashboardPage.test.tsx
//
// Vitest + React Testing Library tests for ParentDashboardPage.
// Covers: header rendering, logout, empty/loading/error states in DashboardContent,
// child data cards, multiple-children selector.

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// ── Module mocks ──────────────────────────────────────────────────────────────

const mockNavigate = vi.fn();

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

vi.mock('../../stores/tenantStore', () => ({
  useTenantStore: vi.fn(),
}));

vi.mock('../../stores/parentStore', () => ({
  useParentStore: vi.fn(),
}));

vi.mock('../../services/parentService', () => ({
  parentService: {
    getChildOverview: vi.fn(),
    logout: vi.fn().mockResolvedValue(undefined),
  },
}));

// ── Typed mock helpers ────────────────────────────────────────────────────────

import { useTenantStore } from '../../stores/tenantStore';
import { useParentStore } from '../../stores/parentStore';
import { parentService } from '../../services/parentService';
import { ParentDashboardPage } from './ParentDashboardPage';

const mockedUseTenantStore = useTenantStore as unknown as ReturnType<typeof vi.fn>;
const mockedUseParentStore = useParentStore as unknown as ReturnType<typeof vi.fn>;
const mockedGetChildOverview = parentService.getChildOverview as ReturnType<typeof vi.fn>;
const mockedLogout = parentService.logout as ReturnType<typeof vi.fn>;

// ── Helpers ───────────────────────────────────────────────────────────────────

const mockSetSelectedChild = vi.fn();
const mockClearSession = vi.fn();

const makeQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: Infinity, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  });

const CHILD_ONE = {
  id: 'child-1',
  first_name: 'Alice',
  last_name: 'Smith',
  grade_level: 'Grade 8',
  section: 'A',
};

const CHILD_TWO = {
  id: 'child-2',
  first_name: 'Bob',
  last_name: 'Smith',
  grade_level: 'Grade 6',
  section: 'B',
};

const OVERVIEW_DATA = {
  courses: [
    {
      id: 'course-1',
      title: 'Mathematics Fundamentals',
      course_type: 'mandatory',
      is_mandatory: true,
      deadline: null,
      total_contents: 10,
      completed_contents: 7,
      progress_percentage: 70,
      status: 'IN_PROGRESS',
      last_accessed: new Date(Date.now() - 3600_000).toISOString(), // 1 hour ago
    },
  ],
  assignments: [
    {
      id: 'asgn-1',
      title: 'Algebra Quiz 1',
      course_title: 'Mathematics Fundamentals',
      due_date: '2026-05-01T00:00:00Z',
      max_score: 100,
      is_mandatory: true,
      submission_status: 'NOT_SUBMITTED',
      score: null,
    },
  ],
  attendance: {
    total_days: 20,
    present_days: 18,
    absent_days: 2,
    attendance_percentage: 90,
  },
  study_time: {
    total_video_seconds: 7200,
    total_video_minutes: 120,
    courses_in_progress: 2,
    courses_completed: 1,
  },
  recent_activity: [
    {
      course_title: 'Mathematics Fundamentals',
      content_title: 'Chapter 1 Video',
      status: 'COMPLETED',
      last_accessed: new Date(Date.now() - 7200_000).toISOString(), // 2 hours ago
      completed_at: new Date(Date.now() - 7200_000).toISOString(),
    },
  ],
};

function renderPage() {
  return render(
    <QueryClientProvider client={makeQueryClient()}>
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }} initialEntries={['/parent/dashboard']}>
        <ParentDashboardPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('ParentDashboardPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();

    mockedUseTenantStore.mockReturnValue({
      theme: { name: 'Test School', logo: null },
    });

    mockedUseParentStore.mockReturnValue({
      parentEmail: 'parent@test.com',
      children: [CHILD_ONE],
      selectedChildId: 'child-1',
      setSelectedChild: mockSetSelectedChild,
      clearSession: mockClearSession,
    });

    mockedLogout.mockResolvedValue(undefined);
  });

  // ── 1. Header rendering ───────────────────────────────────────────────────

  describe('header rendering', () => {
    it('renders the tenant name in the header', () => {
      mockedGetChildOverview.mockReturnValue(new Promise(() => {}));
      renderPage();
      expect(screen.getByText('Test School')).toBeInTheDocument();
    });

    it('renders "Parent Portal" subtitle in the header', () => {
      mockedGetChildOverview.mockReturnValue(new Promise(() => {}));
      renderPage();
      expect(screen.getByText('Parent Portal')).toBeInTheDocument();
    });

    it('renders the parent email in the header', () => {
      mockedGetChildOverview.mockReturnValue(new Promise(() => {}));
      renderPage();
      expect(screen.getByText('parent@test.com')).toBeInTheDocument();
    });

    it('renders a logout button', () => {
      mockedGetChildOverview.mockReturnValue(new Promise(() => {}));
      renderPage();
      expect(screen.getByTitle('Logout')).toBeInTheDocument();
    });

    it('renders tenant initial when no logo', () => {
      mockedGetChildOverview.mockReturnValue(new Promise(() => {}));
      renderPage();
      expect(screen.getByText('T')).toBeInTheDocument(); // 'T' for 'Test School'
    });

    it('renders tenant logo img when logo is provided', () => {
      mockedUseTenantStore.mockReturnValue({
        theme: { name: 'Test School', logo: 'https://cdn.example.com/logo.png' },
      });
      mockedGetChildOverview.mockReturnValue(new Promise(() => {}));
      renderPage();
      expect(screen.getByAltText('Test School')).toHaveAttribute(
        'src',
        'https://cdn.example.com/logo.png',
      );
    });
  });

  // ── 2. Logout ─────────────────────────────────────────────────────────────

  describe('logout', () => {
    it('calls parentService.logout() when logout button is clicked', async () => {
      const user = userEvent.setup();
      mockedGetChildOverview.mockResolvedValue(OVERVIEW_DATA);
      renderPage();

      await user.click(screen.getByTitle('Logout'));

      await waitFor(() => {
        expect(mockedLogout).toHaveBeenCalled();
      });
    });

    it('calls clearSession when logout button is clicked', async () => {
      const user = userEvent.setup();
      mockedGetChildOverview.mockResolvedValue(OVERVIEW_DATA);
      renderPage();

      await user.click(screen.getByTitle('Logout'));

      await waitFor(() => {
        expect(mockClearSession).toHaveBeenCalled();
      });
    });

    it('navigates to /parent after logout', async () => {
      const user = userEvent.setup();
      mockedGetChildOverview.mockResolvedValue(OVERVIEW_DATA);
      renderPage();

      await user.click(screen.getByTitle('Logout'));

      await waitFor(() => {
        expect(mockNavigate).toHaveBeenCalledWith('/parent', { replace: true });
      });
    });
  });

  // ── 3. No-children empty state ────────────────────────────────────────────

  describe('no children linked', () => {
    it('shows "No children linked to your account." when children array is empty', () => {
      mockedUseParentStore.mockReturnValue({
        parentEmail: 'parent@test.com',
        children: [],
        selectedChildId: null,
        setSelectedChild: mockSetSelectedChild,
        clearSession: mockClearSession,
      });
      renderPage();
      expect(
        screen.getByText('No children linked to your account.'),
      ).toBeInTheDocument();
    });

    it('does not show child info card when no children', () => {
      mockedUseParentStore.mockReturnValue({
        parentEmail: 'parent@test.com',
        children: [],
        selectedChildId: null,
        setSelectedChild: mockSetSelectedChild,
        clearSession: mockClearSession,
      });
      renderPage();
      expect(screen.queryByText('Alice Smith')).not.toBeInTheDocument();
    });
  });

  // ── 4. DashboardContent loading state ────────────────────────────────────

  describe('DashboardContent loading state', () => {
    it('shows spinner while child overview is loading', () => {
      mockedGetChildOverview.mockReturnValue(new Promise(() => {}));
      renderPage();
      // Loader2 icon is rendered as an SVG; check for the spinner container
      const spinner = document.querySelector('.animate-spin');
      expect(spinner).toBeInTheDocument();
    });

    it('does not show child name while loading', () => {
      mockedGetChildOverview.mockReturnValue(new Promise(() => {}));
      renderPage();
      expect(screen.queryByText('Alice Smith')).not.toBeInTheDocument();
    });
  });

  // ── 5. DashboardContent error state ──────────────────────────────────────

  describe('DashboardContent error state', () => {
    it('shows "Failed to load data." when getChildOverview rejects', async () => {
      mockedGetChildOverview.mockRejectedValue(new Error('Server error'));
      renderPage();
      expect(await screen.findByText(/failed to load data/i)).toBeInTheDocument();
    });

    it('does not show StudentInfoCard on error', async () => {
      mockedGetChildOverview.mockRejectedValue(new Error('Server error'));
      renderPage();
      await screen.findByText(/failed to load data/i);
      expect(screen.queryByText('Alice Smith')).not.toBeInTheDocument();
    });
  });

  // ── 6. StudentInfoCard ────────────────────────────────────────────────────

  describe('StudentInfoCard', () => {
    it("shows child's full name", async () => {
      mockedGetChildOverview.mockResolvedValue(OVERVIEW_DATA);
      renderPage();
      expect(await screen.findByText('Alice Smith')).toBeInTheDocument();
    });

    it("shows child's grade level", async () => {
      mockedGetChildOverview.mockResolvedValue(OVERVIEW_DATA);
      renderPage();
      await screen.findByText('Alice Smith');
      expect(screen.getByText('Grade 8')).toBeInTheDocument();
    });

    it("shows child's section", async () => {
      mockedGetChildOverview.mockResolvedValue(OVERVIEW_DATA);
      renderPage();
      await screen.findByText('Alice Smith');
      expect(screen.getByText('Section A')).toBeInTheDocument();
    });

    it('shows initials avatar (AS for Alice Smith)', async () => {
      mockedGetChildOverview.mockResolvedValue(OVERVIEW_DATA);
      renderPage();
      await screen.findByText('Alice Smith');
      expect(screen.getByText('AS')).toBeInTheDocument();
    });
  });

  // ── 7. CourseProgressCard ─────────────────────────────────────────────────

  describe('CourseProgressCard', () => {
    it('shows "Course Progress" heading', async () => {
      mockedGetChildOverview.mockResolvedValue(OVERVIEW_DATA);
      renderPage();
      expect(await screen.findByText('Course Progress')).toBeInTheDocument();
    });

    it('shows course title', async () => {
      mockedGetChildOverview.mockResolvedValue(OVERVIEW_DATA);
      renderPage();
      // Course title appears in both CourseProgressCard and AssignmentsCard
      const elements = await screen.findAllByText('Mathematics Fundamentals');
      expect(elements.length).toBeGreaterThan(0);
    });

    it('shows course progress percentage', async () => {
      mockedGetChildOverview.mockResolvedValue(OVERVIEW_DATA);
      renderPage();
      await screen.findAllByText('Mathematics Fundamentals');
      expect(screen.getByText('70%')).toBeInTheDocument();
    });

    it('shows "No courses enrolled." when courses array is empty', async () => {
      mockedGetChildOverview.mockResolvedValue({ ...OVERVIEW_DATA, courses: [] });
      renderPage();
      expect(await screen.findByText('No courses enrolled.')).toBeInTheDocument();
    });
  });

  // ── 8. AssignmentsCard ────────────────────────────────────────────────────

  describe('AssignmentsCard', () => {
    it('shows "Assignments" heading', async () => {
      mockedGetChildOverview.mockResolvedValue(OVERVIEW_DATA);
      renderPage();
      expect(await screen.findByText('Assignments')).toBeInTheDocument();
    });

    it('shows assignment title in the table', async () => {
      mockedGetChildOverview.mockResolvedValue(OVERVIEW_DATA);
      renderPage();
      expect(await screen.findByText('Algebra Quiz 1')).toBeInTheDocument();
    });

    it('shows assignment submission status badge', async () => {
      mockedGetChildOverview.mockResolvedValue(OVERVIEW_DATA);
      renderPage();
      await screen.findByText('Algebra Quiz 1');
      expect(screen.getByText('NOT SUBMITTED')).toBeInTheDocument();
    });

    it('shows "No assignments yet." when assignments array is empty', async () => {
      mockedGetChildOverview.mockResolvedValue({ ...OVERVIEW_DATA, assignments: [] });
      renderPage();
      expect(await screen.findByText('No assignments yet.')).toBeInTheDocument();
    });
  });

  // ── 9. AttendanceCard ─────────────────────────────────────────────────────

  describe('AttendanceCard', () => {
    it('shows "Attendance" heading', async () => {
      mockedGetChildOverview.mockResolvedValue(OVERVIEW_DATA);
      renderPage();
      expect(await screen.findByText('Attendance')).toBeInTheDocument();
    });

    it('shows attendance percentage in the donut center', async () => {
      mockedGetChildOverview.mockResolvedValue(OVERVIEW_DATA);
      renderPage();
      await screen.findByText('Attendance');
      expect(screen.getByText('90%')).toBeInTheDocument();
    });

    it('shows present days count', async () => {
      mockedGetChildOverview.mockResolvedValue(OVERVIEW_DATA);
      renderPage();
      await screen.findByText('Attendance');
      expect(screen.getByText(/present \(18\)/i)).toBeInTheDocument();
    });

    it('shows absent days count', async () => {
      mockedGetChildOverview.mockResolvedValue(OVERVIEW_DATA);
      renderPage();
      await screen.findByText('Attendance');
      expect(screen.getByText(/absent \(2\)/i)).toBeInTheDocument();
    });

    it('shows "No attendance data available." when total_days is 0', async () => {
      mockedGetChildOverview.mockResolvedValue({
        ...OVERVIEW_DATA,
        attendance: { total_days: 0, present_days: 0, absent_days: 0, attendance_percentage: 0 },
      });
      renderPage();
      expect(await screen.findByText('No attendance data available.')).toBeInTheDocument();
    });
  });

  // ── 10. StudyTimeCard ─────────────────────────────────────────────────────

  describe('StudyTimeCard', () => {
    it('shows "Study Time" heading', async () => {
      mockedGetChildOverview.mockResolvedValue(OVERVIEW_DATA);
      renderPage();
      expect(await screen.findByText('Study Time')).toBeInTheDocument();
    });

    it('shows total video minutes badge', async () => {
      mockedGetChildOverview.mockResolvedValue(OVERVIEW_DATA);
      renderPage();
      await screen.findByText('Study Time');
      expect(screen.getByText('120m video time')).toBeInTheDocument();
    });

    it('shows courses in progress count', async () => {
      mockedGetChildOverview.mockResolvedValue(OVERVIEW_DATA);
      renderPage();
      await screen.findByText('Study Time');
      expect(screen.getByText('2')).toBeInTheDocument(); // courses_in_progress
    });

    it('shows courses completed count', async () => {
      mockedGetChildOverview.mockResolvedValue(OVERVIEW_DATA);
      renderPage();
      await screen.findByText('Study Time');
      expect(screen.getByText('1')).toBeInTheDocument(); // courses_completed
    });

    it('shows "In Progress" label', async () => {
      mockedGetChildOverview.mockResolvedValue(OVERVIEW_DATA);
      renderPage();
      expect(await screen.findByText('In Progress')).toBeInTheDocument();
    });

    it('shows "Completed" label', async () => {
      mockedGetChildOverview.mockResolvedValue(OVERVIEW_DATA);
      renderPage();
      expect(await screen.findByText('Completed')).toBeInTheDocument();
    });
  });

  // ── 11. RecentActivityCard ────────────────────────────────────────────────

  describe('RecentActivityCard', () => {
    it('shows "Recent Activity" heading', async () => {
      mockedGetChildOverview.mockResolvedValue(OVERVIEW_DATA);
      renderPage();
      expect(await screen.findByText('Recent Activity')).toBeInTheDocument();
    });

    it('shows activity course title', async () => {
      mockedGetChildOverview.mockResolvedValue(OVERVIEW_DATA);
      renderPage();
      // Mathematics Fundamentals appears in both CourseProgressCard and RecentActivityCard
      await screen.findByText('Recent Activity');
      const elements = screen.getAllByText('Mathematics Fundamentals');
      expect(elements.length).toBeGreaterThanOrEqual(1);
    });

    it('shows activity content title', async () => {
      mockedGetChildOverview.mockResolvedValue(OVERVIEW_DATA);
      renderPage();
      await screen.findByText('Recent Activity');
      expect(screen.getByText(/Chapter 1 Video/)).toBeInTheDocument();
    });

    it('shows activity status badge', async () => {
      mockedGetChildOverview.mockResolvedValue(OVERVIEW_DATA);
      renderPage();
      await screen.findByText('Recent Activity');
      // STATUS badge for COMPLETED in recent activity
      const completed = screen.getAllByText('COMPLETED');
      expect(completed.length).toBeGreaterThanOrEqual(1);
    });

    it('shows "No recent activity." when activities array is empty', async () => {
      mockedGetChildOverview.mockResolvedValue({ ...OVERVIEW_DATA, recent_activity: [] });
      renderPage();
      expect(await screen.findByText('No recent activity.')).toBeInTheDocument();
    });
  });

  // ── 12. Multiple children — child selector ────────────────────────────────

  describe('multiple children selector', () => {
    beforeEach(() => {
      mockedUseParentStore.mockReturnValue({
        parentEmail: 'parent@test.com',
        children: [CHILD_ONE, CHILD_TWO],
        selectedChildId: 'child-1',
        setSelectedChild: mockSetSelectedChild,
        clearSession: mockClearSession,
      });
    });

    it('renders a child selector dropdown when multiple children exist', () => {
      mockedGetChildOverview.mockReturnValue(new Promise(() => {}));
      renderPage();
      const selector = screen.getByRole('combobox');
      expect(selector).toBeInTheDocument();
    });

    it('renders all children as options in the selector', () => {
      mockedGetChildOverview.mockReturnValue(new Promise(() => {}));
      renderPage();
      expect(screen.getByRole('option', { name: /Alice Smith/i })).toBeInTheDocument();
      expect(screen.getByRole('option', { name: /Bob Smith/i })).toBeInTheDocument();
    });

    it('does not show selector when only one child', () => {
      mockedUseParentStore.mockReturnValue({
        parentEmail: 'parent@test.com',
        children: [CHILD_ONE],
        selectedChildId: 'child-1',
        setSelectedChild: mockSetSelectedChild,
        clearSession: mockClearSession,
      });
      mockedGetChildOverview.mockReturnValue(new Promise(() => {}));
      renderPage();
      expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
    });

    it('calls setSelectedChild when a different child is selected', async () => {
      const user = userEvent.setup();
      mockedGetChildOverview.mockReturnValue(new Promise(() => {}));
      renderPage();

      await user.selectOptions(screen.getByRole('combobox'), 'child-2');

      expect(mockSetSelectedChild).toHaveBeenCalledWith('child-2');
    });
  });
});
