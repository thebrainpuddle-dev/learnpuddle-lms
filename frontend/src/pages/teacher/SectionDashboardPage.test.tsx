// src/pages/teacher/SectionDashboardPage.test.tsx
//
// FE-061: Tests for the Teacher Section Dashboard page.
// Covers: page header (section title, academic year, grade band), back button
//         navigation, tab bar (Students / Courses / Analytics / Assignments /
//         Attendance), tab switching via URL search params, loading skeleton,
//         error state, Students tab (student list, active/inactive badge,
//         student search filter), Courses tab (course list, published badge),
//         Assignments tab (assignment list, quiz/assignment badge, no-due-date),
//         empty states per tab, AttendanceTab render delegation.
//
// Mocking strategy:
//   - academicsService.getSectionDashboard via vi.mock('../../services/academicsService')
//   - AttendanceCard, AttendanceLoader, ExportAttendanceModal stubbed
//   - useNavigate + useSearchParams mocked via importOriginal spread
//   - usePageTitle stubbed
//   - Route params provided via MemoryRouter initialEntries with Routes wrapper

import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { SectionDashboardPage } from './SectionDashboardPage';

// ── Module mocks ──────────────────────────────────────────────────────────────

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock('../../services/academicsService', () => ({
  academicsService: {
    getSectionDashboard: vi.fn(),
  },
}));

// Stub heavy attendance sub-components
vi.mock('../../components/attendance/AttendanceCard', () => ({
  AttendanceCard: () => <div data-testid="attendance-card" />,
}));
vi.mock('../../components/attendance/AttendanceLoader', () => ({
  AttendanceLoader: () => <div data-testid="attendance-loader" />,
}));
vi.mock('../../components/attendance/ExportAttendanceModal', () => ({
  ExportAttendanceModal: () => <div data-testid="export-attendance-modal" />,
}));

vi.mock('../../hooks/usePageTitle', () => ({ usePageTitle: vi.fn() }));

// api.get is used inside AttendanceTab — stub so it doesn't throw
vi.mock('../../config/api', () => ({
  default: { get: vi.fn().mockReturnValue(new Promise(() => {})) },
}));

// ── Typed mock helper ─────────────────────────────────────────────────────────

import { academicsService } from '../../services/academicsService';
const mockGetSectionDashboard = academicsService.getSectionDashboard as ReturnType<typeof vi.fn>;

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
}

function renderPage(sectionId = 'sec-1', search = '') {
  const path = `/teacher/sections/${sectionId}/dashboard${search}`;
  return render(
    <QueryClientProvider client={makeClient()}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route
            path="/teacher/sections/:sectionId/dashboard"
            element={<SectionDashboardPage />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// ── Fixtures ──────────────────────────────────────────────────────────────────

const mockSection = {
  id: 'sec-1',
  name: 'Section A',
  grade_name: 'Grade 10',
  grade_short_code: 'G10',
  grade_band_name: 'Secondary',
  academic_year: '2024-25',
};

function makeStudentsResponse() {
  return {
    section: mockSection,
    tab: 'students',
    total: 2,
    students: [
      {
        id: 'std-1',
        first_name: 'Alice',
        last_name: 'Johnson',
        email: 'alice@school.edu',
        student_id: 'STU001',
        is_active: true,
        last_login: '2024-04-20T10:00:00Z',
      },
      {
        id: 'std-2',
        first_name: 'Bob',
        last_name: 'Smith',
        email: 'bob@school.edu',
        student_id: 'STU002',
        is_active: false,
        last_login: null,
      },
    ],
  };
}

function makeCoursesResponse() {
  return {
    section: mockSection,
    tab: 'courses',
    courses: [
      {
        id: 'crs-1',
        title: 'Algebra Fundamentals',
        slug: 'algebra-fundamentals',
        is_published: true,
        is_active: true,
        created_at: '2024-01-01T00:00:00Z',
        student_count: 25,
      },
      {
        id: 'crs-2',
        title: 'IB PYP Framework',
        slug: 'ib-pyp-framework',
        is_published: false,
        is_active: true,
        created_at: '2024-02-01T00:00:00Z',
        student_count: 12,
      },
    ],
  };
}

function makeAssignmentsResponse() {
  return {
    section: mockSection,
    tab: 'assignments',
    assignments: [
      {
        id: 'asgn-1',
        title: 'Algebra Quiz 1',
        course_id: 'crs-1',
        due_date: new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString(), // 7 days future
        max_score: '100',
        is_quiz: true,
      },
      {
        id: 'asgn-2',
        title: 'IB Essay Assignment',
        course_id: 'crs-2',
        due_date: null,
        max_score: '50',
        is_quiz: false,
      },
    ],
  };
}

function makeAnalyticsResponse() {
  return {
    section: mockSection,
    tab: 'analytics',
    stats: {
      total_students: 30,
      active_students_7d: 22,
      inactive_students: 8,
      total_courses: 4,
    },
  };
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('SectionDashboardPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Default: students tab resolves, others never resolve
    mockGetSectionDashboard.mockImplementation(
      (_sectionId: string, tab: string) => {
        if (tab === 'students') return Promise.resolve(makeStudentsResponse());
        return new Promise(() => {}); // don't resolve non-active tabs
      },
    );
  });

  // ── Header ──────────────────────────────────────────────────────────────────

  it('renders the section title from API data', async () => {
    renderPage();
    expect(
      await screen.findByRole('heading', { level: 1, name: /grade 10 - section a/i }),
    ).toBeInTheDocument();
  });

  it('renders the academic year badge', async () => {
    renderPage();
    expect(await screen.findByText('2024-25')).toBeInTheDocument();
  });

  it('renders the grade band name as subtitle', async () => {
    renderPage();
    expect(await screen.findByText('Secondary')).toBeInTheDocument();
  });

  it('navigates to /teacher/my-classes on back button click', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole('heading', { name: /grade 10 - section a/i });
    await user.click(screen.getByRole('button', { name: /back to my classes/i }));
    expect(mockNavigate).toHaveBeenCalledWith('/teacher/my-classes');
  });

  // ── Tab bar ─────────────────────────────────────────────────────────────────

  it('renders all five tab buttons', async () => {
    renderPage();
    await screen.findByRole('heading', { name: /grade 10 - section a/i });

    const tablist = screen.getByRole('tablist');
    expect(within(tablist).getByRole('tab', { name: /students/i })).toBeInTheDocument();
    expect(within(tablist).getByRole('tab', { name: /courses/i })).toBeInTheDocument();
    expect(within(tablist).getByRole('tab', { name: /analytics/i })).toBeInTheDocument();
    expect(within(tablist).getByRole('tab', { name: /assignments/i })).toBeInTheDocument();
    expect(within(tablist).getByRole('tab', { name: /attendance/i })).toBeInTheDocument();
  });

  it('students tab is selected by default (no ?tab param)', async () => {
    renderPage();
    await screen.findByRole('heading', { name: /grade 10 - section a/i });

    const tablist = screen.getByRole('tablist');
    const studentsTab = within(tablist).getByRole('tab', { name: /students/i });
    expect(studentsTab).toHaveAttribute('aria-selected', 'true');
  });

  it('switches to courses tab when courses tab is clicked', async () => {
    const user = userEvent.setup();
    mockGetSectionDashboard.mockImplementation((_id: string, tab: string) => {
      if (tab === 'students') return Promise.resolve(makeStudentsResponse());
      if (tab === 'courses') return Promise.resolve(makeCoursesResponse());
      return new Promise(() => {});
    });

    renderPage();
    await screen.findByText('Alice Johnson'); // students loaded

    const tablist = screen.getByRole('tablist');
    await user.click(within(tablist).getByRole('tab', { name: /courses/i }));

    expect(await screen.findByText('Algebra Fundamentals')).toBeInTheDocument();
  });

  // ── Loading state ────────────────────────────────────────────────────────────

  it('shows loading skeleton while students are loading', () => {
    mockGetSectionDashboard.mockReturnValue(new Promise(() => {}));
    renderPage();
    const skeletons = document.querySelectorAll('.tp-skeleton');
    expect(skeletons.length).toBeGreaterThanOrEqual(1);
  });

  // ── Error state ──────────────────────────────────────────────────────────────

  it('shows error state when students query fails', async () => {
    mockGetSectionDashboard.mockRejectedValue(new Error('Network failure'));
    renderPage();
    expect(await screen.findByText('Failed to load data')).toBeInTheDocument();
    expect(screen.getByText('Network failure')).toBeInTheDocument();
  });

  // ── Students tab ─────────────────────────────────────────────────────────────

  it('renders student full names in the students table', async () => {
    renderPage();
    expect(await screen.findByText('Alice Johnson')).toBeInTheDocument();
    expect(screen.getByText('Bob Smith')).toBeInTheDocument();
  });

  it('renders student IDs in the students table', async () => {
    renderPage();
    await screen.findByText('Alice Johnson');
    expect(screen.getByText('STU001')).toBeInTheDocument();
    expect(screen.getByText('STU002')).toBeInTheDocument();
  });

  it('renders Active badge for active students', async () => {
    renderPage();
    await screen.findByText('Alice Johnson');
    expect(screen.getByText('Active')).toBeInTheDocument();
  });

  it('renders Inactive badge for inactive students', async () => {
    renderPage();
    await screen.findByText('Bob Smith');
    expect(screen.getByText('Inactive')).toBeInTheDocument();
  });

  it('shows student count badge on Students tab', async () => {
    renderPage();
    await screen.findByText('Alice Johnson');
    // total: 2 from response — badge appears on the tab
    const tablist = screen.getByRole('tablist');
    const studentsTab = within(tablist).getByRole('tab', { name: /students/i });
    // badge count "2" should be visible inside or near the tab
    expect(studentsTab.textContent).toMatch(/2/);
  });

  it('filters students by search input', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Alice Johnson');

    const searchInput = screen.getByPlaceholderText(/search by name, id, or email/i);
    await user.type(searchInput, 'alice');

    await waitFor(() => {
      expect(screen.queryByText('Bob Smith')).not.toBeInTheDocument();
    });
    expect(screen.getByText('Alice Johnson')).toBeInTheDocument();
  });

  it('shows empty students state when no students returned', async () => {
    mockGetSectionDashboard.mockResolvedValue({
      section: mockSection,
      tab: 'students',
      total: 0,
      students: [],
    });
    renderPage();
    expect(
      await screen.findByText('No students in this section'),
    ).toBeInTheDocument();
  });

  // ── Courses tab ──────────────────────────────────────────────────────────────

  it('renders course titles in courses tab', async () => {
    const user = userEvent.setup();
    mockGetSectionDashboard.mockImplementation((_id: string, tab: string) => {
      if (tab === 'students') return Promise.resolve(makeStudentsResponse());
      if (tab === 'courses') return Promise.resolve(makeCoursesResponse());
      return new Promise(() => {});
    });

    renderPage();
    await screen.findByText('Alice Johnson');

    const tablist = screen.getByRole('tablist');
    await user.click(within(tablist).getByRole('tab', { name: /courses/i }));

    expect(await screen.findByText('Algebra Fundamentals')).toBeInTheDocument();
    expect(screen.getByText('IB PYP Framework')).toBeInTheDocument();
  });

  it('shows empty courses state when no courses returned', async () => {
    const user = userEvent.setup();
    mockGetSectionDashboard.mockImplementation((_id: string, tab: string) => {
      if (tab === 'students') return Promise.resolve(makeStudentsResponse());
      if (tab === 'courses') return Promise.resolve({ section: mockSection, tab: 'courses', courses: [] });
      return new Promise(() => {});
    });

    renderPage();
    await screen.findByText('Alice Johnson');

    const tablist = screen.getByRole('tablist');
    await user.click(within(tablist).getByRole('tab', { name: /courses/i }));

    expect(await screen.findByText('No courses targeting this section')).toBeInTheDocument();
  });

  // ── Assignments tab ──────────────────────────────────────────────────────────

  it('renders assignment titles in assignments tab', async () => {
    const user = userEvent.setup();
    mockGetSectionDashboard.mockImplementation((_id: string, tab: string) => {
      if (tab === 'students') return Promise.resolve(makeStudentsResponse());
      if (tab === 'assignments') return Promise.resolve(makeAssignmentsResponse());
      return new Promise(() => {});
    });

    renderPage();
    await screen.findByText('Alice Johnson');

    const tablist = screen.getByRole('tablist');
    await user.click(within(tablist).getByRole('tab', { name: /assignments/i }));

    expect(await screen.findByText('Algebra Quiz 1')).toBeInTheDocument();
    expect(screen.getByText('IB Essay Assignment')).toBeInTheDocument();
  });

  it('shows "Quiz" badge for quiz assignments', async () => {
    const user = userEvent.setup();
    mockGetSectionDashboard.mockImplementation((_id: string, tab: string) => {
      if (tab === 'students') return Promise.resolve(makeStudentsResponse());
      if (tab === 'assignments') return Promise.resolve(makeAssignmentsResponse());
      return new Promise(() => {});
    });

    renderPage();
    await screen.findByText('Alice Johnson');

    const tablist = screen.getByRole('tablist');
    await user.click(within(tablist).getByRole('tab', { name: /assignments/i }));

    await screen.findByText('Algebra Quiz 1');
    expect(screen.getByText('Quiz')).toBeInTheDocument();
    expect(screen.getByText('Assignment')).toBeInTheDocument();
  });

  it('shows "No due date" for assignment with null due_date', async () => {
    const user = userEvent.setup();
    mockGetSectionDashboard.mockImplementation((_id: string, tab: string) => {
      if (tab === 'students') return Promise.resolve(makeStudentsResponse());
      if (tab === 'assignments') return Promise.resolve(makeAssignmentsResponse());
      return new Promise(() => {});
    });

    renderPage();
    await screen.findByText('Alice Johnson');

    const tablist = screen.getByRole('tablist');
    await user.click(within(tablist).getByRole('tab', { name: /assignments/i }));

    await screen.findByText('IB Essay Assignment');
    expect(screen.getByText('No due date')).toBeInTheDocument();
  });

  it('shows empty assignments state when no assignments returned', async () => {
    const user = userEvent.setup();
    mockGetSectionDashboard.mockImplementation((_id: string, tab: string) => {
      if (tab === 'students') return Promise.resolve(makeStudentsResponse());
      if (tab === 'assignments') return Promise.resolve({ section: mockSection, tab: 'assignments', assignments: [] });
      return new Promise(() => {});
    });

    renderPage();
    await screen.findByText('Alice Johnson');

    const tablist = screen.getByRole('tablist');
    await user.click(within(tablist).getByRole('tab', { name: /assignments/i }));

    expect(
      await screen.findByText('No assignments for this section'),
    ).toBeInTheDocument();
  });

  // ── Analytics tab ─────────────────────────────────────────────────────────

  it('renders analytics stat cards when analytics data is loaded', async () => {
    const user = userEvent.setup();
    mockGetSectionDashboard.mockImplementation((_id: string, tab: string) => {
      if (tab === 'students') return Promise.resolve(makeStudentsResponse());
      if (tab === 'analytics') return Promise.resolve(makeAnalyticsResponse());
      return new Promise(() => {});
    });

    renderPage();
    await screen.findByText('Alice Johnson');

    const tablist = screen.getByRole('tablist');
    await user.click(within(tablist).getByRole('tab', { name: /analytics/i }));

    await screen.findByText('Total Students');
    expect(screen.getByText('30')).toBeInTheDocument();
    expect(screen.getByText('22')).toBeInTheDocument(); // Active 7d
  });

  // ── Attendance tab ────────────────────────────────────────────────────────

  it('renders attendance tab content (stubbed components)', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Alice Johnson');

    const tablist = screen.getByRole('tablist');
    await user.click(within(tablist).getByRole('tab', { name: /attendance/i }));

    // AttendanceLoader is shown while attendance data loads (mocked api.get never resolves)
    expect(screen.getByTestId('attendance-loader')).toBeInTheDocument();
  });
});
