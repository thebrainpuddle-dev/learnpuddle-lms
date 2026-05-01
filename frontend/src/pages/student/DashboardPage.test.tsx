// src/pages/student/DashboardPage.test.tsx

import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { DashboardPage } from './DashboardPage';
import { studentService } from '../../services/studentService';
import { useAuthStore } from '../../stores/authStore';
import { useTenantStore } from '../../stores/tenantStore';

// ─── Hoist navigate mock so the factory closure can capture it ────────────────
const mockedUseNavigate = vi.fn();

vi.mock('../../stores/authStore');
vi.mock('../../stores/tenantStore');
vi.mock('../../services/studentService', () => ({
  studentService: {
    getStudentDashboard: vi.fn(),
    getStudentCourses: vi.fn(),
  },
}));
vi.mock('../../hooks/usePageTitle', () => ({ usePageTitle: vi.fn() }));
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockedUseNavigate };
});

// ─── Typed mock handles ────────────────────────────────────────────────────────
const mockedUseAuthStore = useAuthStore as unknown as ReturnType<typeof vi.fn>;
const mockedUseTenantStore = useTenantStore as unknown as ReturnType<typeof vi.fn>;
const mockedStudentService = studentService as unknown as {
  [K in keyof typeof studentService]: ReturnType<typeof vi.fn>;
};

// ─── Fixtures ─────────────────────────────────────────────────────────────────

const MOCK_DASHBOARD = {
  stats: {
    overall_progress: 45,
    total_courses: 3,
    completed_courses: 1,
    pending_assignments: 2,
  },
  continue_learning: {
    course_id: 'c-1',
    course_title: 'Math Foundations',
    content_id: 'cnt-1',
    content_title: 'Algebra Basics',
    progress_percentage: 45,
  },
  deadlines: [
    { id: 'd-1', type: 'assignment', title: 'Algebra Homework', days_left: 2 },
    { id: 'd-2', type: 'course', title: 'Physics Exam', days_left: 0 },
    { id: 'd-3', type: 'assignment', title: 'History Essay', days_left: 1 },
  ],
};

const MOCK_COURSES = [
  {
    id: 'c-1',
    title: 'Math Foundations',
    description: 'Core math',
    thumbnail: null,
    progress_percentage: 45,
    completed_content_count: 5,
    total_content_count: 11,
    deadline: null,
    estimated_hours: '3',
    slug: 'math',
    is_mandatory: false,
    is_published: true,
    is_active: true,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 'c-2',
    title: 'Science Lab',
    description: 'Lab work',
    thumbnail: null,
    progress_percentage: 0,
    completed_content_count: 0,
    total_content_count: 8,
    deadline: '2026-12-31T00:00:00Z',
    estimated_hours: '2',
    slug: 'science',
    is_mandatory: false,
    is_published: true,
    is_active: true,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 'c-3',
    title: 'History 101',
    description: 'History',
    thumbnail: null,
    progress_percentage: 100,
    completed_content_count: 10,
    total_content_count: 10,
    deadline: null,
    estimated_hours: '4',
    slug: 'history',
    is_mandatory: false,
    is_published: true,
    is_active: true,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
];

// ─── Test helpers ─────────────────────────────────────────────────────────────

const makeQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        staleTime: Infinity,
        refetchOnWindowFocus: false,
      },
    },
  });

const renderPage = () =>
  render(
    <QueryClientProvider client={makeQueryClient()}>
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );

// ─── Suite ────────────────────────────────────────────────────────────────────

describe('Student DashboardPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();

    mockedUseAuthStore.mockReturnValue({ user: { first_name: 'Alice' } });
    mockedUseTenantStore.mockReturnValue({
      theme: { name: 'Test School', welcomeMessage: null },
    });

    mockedStudentService.getStudentDashboard.mockResolvedValue(MOCK_DASHBOARD);
    mockedStudentService.getStudentCourses.mockResolvedValue(MOCK_COURSES);
  });

  // ── 1. Greeting ─────────────────────────────────────────────────────────────

  it('renders the greeting with the user\'s first name', async () => {
    renderPage();
    expect(
      await screen.findByText(/Good (morning|afternoon|evening), Alice/),
    ).toBeInTheDocument();
  });

  // ── 2. Pending assignments in subtitle ──────────────────────────────────────

  it('shows pending assignments count in the subtitle', async () => {
    renderPage();
    expect(await screen.findByText(/2 assignments pending/)).toBeInTheDocument();
  });

  // ── 3. Stat card labels ──────────────────────────────────────────────────────

  it('renders all four stat card labels', async () => {
    renderPage();
    expect(await screen.findByText('Overall Progress')).toBeInTheDocument();
    expect(await screen.findByText('Total Courses')).toBeInTheDocument();
    expect(await screen.findByText('Completed')).toBeInTheDocument();
    expect(await screen.findByText('Pending Assignments')).toBeInTheDocument();
  });

  // ── 4. Overall progress value ────────────────────────────────────────────────

  it('renders the overall progress value as a percentage', async () => {
    renderPage();
    // The stat card shows "45%" for overall_progress: 45 — multiple elements may
    // contain this text (stat card + course progress bar), so use findAllByText
    const matches = await screen.findAllByText('45%');
    expect(matches.length).toBeGreaterThanOrEqual(1);
  });

  // ── 5. Continue learning card ────────────────────────────────────────────────

  it('shows the continue learning card when data is present', async () => {
    renderPage();
    // "Math Foundations" may appear in both the continue-learning card and the
    // My Courses list, so use findAllByText and assert at least one exists.
    const courseTitles = await screen.findAllByText('Math Foundations');
    expect(courseTitles.length).toBeGreaterThanOrEqual(1);
    expect(await screen.findByText('Up next: Algebra Basics')).toBeInTheDocument();
    expect(await screen.findByText('45% complete')).toBeInTheDocument();
  });

  // ── 6. Navigate on continue learning click ───────────────────────────────────

  it('navigates to the course page when the continue learning card is clicked', async () => {
    const user = userEvent.setup();
    renderPage();

    // The continue-learning card is the only button that contains "Up next:" in
    // its accessible name / visible text. Find it via the unique child text.
    const upNextText = await screen.findByText(/Up next:/);
    const continueBtn = upNextText.closest('button') as HTMLElement;
    await user.click(continueBtn);

    expect(mockedUseNavigate).toHaveBeenCalledWith('/student/courses/c-1');
  });

  // ── 7. Continue learning hidden when null ────────────────────────────────────

  it('hides the continue learning card when continue_learning is null', async () => {
    mockedStudentService.getStudentDashboard.mockResolvedValue({
      ...MOCK_DASHBOARD,
      continue_learning: null,
    });
    renderPage();

    // Wait for data to load (stat cards should be present)
    await screen.findByText('Overall Progress');

    // The "Continue Learning" label inside the card should not be in the document
    expect(screen.queryByText(/Continue Learning/i)).not.toBeInTheDocument();
  });

  // ── 8. My Courses section ────────────────────────────────────────────────────

  it('renders the My Courses heading and all course titles', async () => {
    renderPage();
    expect(await screen.findByText('My Courses')).toBeInTheDocument();
    expect(await screen.findByText('Science Lab')).toBeInTheDocument();
    expect(await screen.findByText('History 101')).toBeInTheDocument();
  });

  // ── 9. Course lesson counts ──────────────────────────────────────────────────

  it('shows the completed / total lessons count for a course', async () => {
    renderPage();
    // Math Foundations: 5 completed out of 11 total
    expect(await screen.findByText('5/11 lessons')).toBeInTheDocument();
  });

  // ── 10. View All courses navigation ─────────────────────────────────────────

  it('navigates to /student/courses when "View All" in My Courses is clicked', async () => {
    const user = userEvent.setup();
    renderPage();

    // "View All" appears in both My Courses and Achievements; grab all and click the first
    // (which belongs to the My Courses section that appears before Achievements)
    const viewAllButtons = await screen.findAllByRole('button', {
      name: /view all/i,
    });
    await user.click(viewAllButtons[0]);

    expect(mockedUseNavigate).toHaveBeenCalledWith('/student/courses');
  });

  // ── 11. Empty courses state ──────────────────────────────────────────────────

  it('shows the empty state when no courses are assigned', async () => {
    mockedStudentService.getStudentCourses.mockResolvedValue([]);
    renderPage();
    expect(await screen.findByText(/No courses assigned yet/)).toBeInTheDocument();
    expect(
      await screen.findByRole('button', { name: /browse courses/i }),
    ).toBeInTheDocument();
  });

  // ── 12. Upcoming deadlines ───────────────────────────────────────────────────

  it('renders the upcoming deadlines list', async () => {
    renderPage();
    expect(await screen.findByText('Algebra Homework')).toBeInTheDocument();
    expect(await screen.findByText('Physics Exam')).toBeInTheDocument();
    expect(await screen.findByText('History Essay')).toBeInTheDocument();
  });

  // ── 13. Due today text ───────────────────────────────────────────────────────

  it('shows "Due today" for a deadline with days_left: 0', async () => {
    renderPage();
    expect(await screen.findByText('Due today')).toBeInTheDocument();
  });

  // ── 14. Due tomorrow text ────────────────────────────────────────────────────

  it('shows "Due tomorrow" for a deadline with days_left: 1', async () => {
    renderPage();
    expect(await screen.findByText('Due tomorrow')).toBeInTheDocument();
  });

  // ── 15. No upcoming deadlines empty state ────────────────────────────────────

  it('shows the empty state when there are no upcoming deadlines', async () => {
    mockedStudentService.getStudentDashboard.mockResolvedValue({
      ...MOCK_DASHBOARD,
      deadlines: [],
    });
    renderPage();
    expect(await screen.findByText(/No upcoming deadlines/)).toBeInTheDocument();
  });

  // ── 16. All deadlines link navigation ────────────────────────────────────────

  it('navigates to /student/assignments when the "All" deadlines button is clicked', async () => {
    const user = userEvent.setup();
    renderPage();

    const allBtn = await screen.findByRole('button', { name: /^all$/i });
    await user.click(allBtn);

    expect(mockedUseNavigate).toHaveBeenCalledWith('/student/assignments');
  });

  // ── 17. View All achievements navigation ─────────────────────────────────────

  it('navigates to /student/achievements when "View All" in Achievements is clicked', async () => {
    const user = userEvent.setup();
    renderPage();

    // The Achievements "View All" is the second "View All" button on the page
    const viewAllButtons = await screen.findAllByRole('button', {
      name: /view all/i,
    });
    // At least one "View All" must be tied to Achievements
    const achievementsSection = (await screen.findByText('Achievements')).closest(
      'div.bg-white',
    ) as HTMLElement;
    const achievementsViewAll = within(achievementsSection).getByRole('button', {
      name: /view all/i,
    });
    await user.click(achievementsViewAll);

    expect(mockedUseNavigate).toHaveBeenCalledWith('/student/achievements');
  });

  // ── 18. Loading skeleton ─────────────────────────────────────────────────────

  it('shows loading skeletons while data is being fetched', () => {
    // Both services hang indefinitely — data never resolves
    mockedStudentService.getStudentDashboard.mockReturnValue(new Promise(() => {}));
    mockedStudentService.getStudentCourses.mockReturnValue(new Promise(() => {}));

    const { container } = renderPage();

    // The component renders tp-skeleton elements or animate-pulse classes while loading
    const skeletons = container.querySelectorAll('.tp-skeleton');
    const pulsing = container.querySelectorAll('.animate-pulse');
    expect(skeletons.length + pulsing.length).toBeGreaterThanOrEqual(1);
  });

  // ── 19. Courses sorted in-progress first ────────────────────────────────────

  it('shows in-progress courses before not-started courses in My Courses', async () => {
    renderPage();

    // Wait until the course list is rendered by waiting for the Science Lab entry
    await screen.findByText('Science Lab');

    // "Math Foundations" appears twice (continue-learning card + My Courses list).
    // Grab the one that lives inside a My Courses row button (has "lessons" sibling).
    const allMathTitles = screen.getAllByText('Math Foundations');
    // The My Courses row buttons each contain a "X/Y lessons" span
    const mathRow = allMathTitles
      .map((el) => el.closest('button'))
      .find((btn) => btn && btn.textContent?.includes('lessons')) as HTMLElement;

    const scienceTitle = screen.getByText('Science Lab');
    const scienceRow = scienceTitle.closest('button') as HTMLElement;

    // Math (45% — in-progress) must appear before Science (0% — not-started) in the DOM
    expect(
      mathRow.compareDocumentPosition(scienceRow) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  // ── Bonus: days_left N > 1 shows "{N} days left" ────────────────────────────

  it('shows "{N} days left" for a deadline with days_left > 1', async () => {
    renderPage();
    expect(await screen.findByText('2 days left')).toBeInTheDocument();
  });

  // ── Bonus: Achievements section always shows badge hint ──────────────────────

  it('always renders the "Complete courses to earn badges" hint in Achievements', async () => {
    renderPage();
    expect(
      await screen.findByText('Complete courses to earn badges'),
    ).toBeInTheDocument();
  });

  // ── Bonus: welcomeMessage rendered when theme has one ────────────────────────

  it('renders the welcome message when theme.welcomeMessage is set', async () => {
    mockedUseTenantStore.mockReturnValue({
      theme: {
        name: 'Test School',
        welcomeMessage: 'Welcome back, learner!',
      },
    });
    renderPage();
    expect(await screen.findByText('Welcome back, learner!')).toBeInTheDocument();
  });

  // ── Bonus: welcomeMessage hidden when null ───────────────────────────────────

  it('does not render a welcome message when theme.welcomeMessage is null', async () => {
    renderPage();
    // No custom welcome message should appear (null → nothing rendered)
    await screen.findByText('Overall Progress'); // ensure page is rendered
    expect(screen.queryByText('Welcome back, learner!')).not.toBeInTheDocument();
  });
});
