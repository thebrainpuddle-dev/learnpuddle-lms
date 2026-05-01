// src/pages/student/StudyNotesPage.test.tsx
//
// Comprehensive Vitest + React Testing Library test suite for the Student
// StudyNotesPage component.
//
// Covers: page heading, loading spinner, empty state (no courses), course
// accordion (expand / collapse / lazy-load), search filter (match / no match),
// content list within an expanded course, content item click selects right panel,
// summary-available indicator (green check), and the placeholder right panel
// shown when no content is selected.
//
// Mocking strategy:
//   - studentService is mocked at the module level so getStudentCourses,
//     getStudySummaries, and getStudentCourseDetail are vi.fn() spies.
//   - StudySummaryPanel is stubbed with a simple data-testid div because it is
//     a complex component with its own async SSE logic unrelated to this page.
//   - usePageTitle is stubbed to avoid document.title side-effects.

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { StudyNotesPage } from './StudyNotesPage';

// ─── Stub heavy transitive deps that hang in happy-dom ────────────────────────
// These are imported by StudySummaryPanel. Even though StudySummaryPanel itself
// is mocked with a factory, Vitest v4 may still resolve its module graph.
// Mocking them here is defensive and prevents the worker from stalling.

vi.mock('../../components/student/FlashcardReview', () => ({
  FlashcardReview: () => null,
}));

vi.mock('../../components/student/MindMapTab', () => ({
  MindMapTab: () => null,
}));

// @xyflow/react uses ResizeObserver + requestAnimationFrame at module load,
// which blocks the happy-dom worker. Mock it here in addition to setupTests.ts
// to ensure the mock is registered before this test file's module graph is resolved.
vi.mock('@xyflow/react', () => ({
  ReactFlow: () => null,
  MiniMap: () => null,
  Controls: () => null,
  Background: () => null,
  Panel: () => null,
  Handle: () => null,
  useNodesState: () => [[], () => {}],
  useEdgesState: () => [[], () => {}],
  Position: { Top: 'top', Bottom: 'bottom', Left: 'left', Right: 'right' },
  MarkerType: { ArrowClosed: 'arrowclosed' },
  BackgroundVariant: { Dots: 'dots', Lines: 'lines', Cross: 'cross' },
}));

// Mock api to prevent the circular authStore→gamificationService→api chain
// from hanging during module graph resolution.
vi.mock('../../config/api', () => ({
  __esModule: true,
  default: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
    defaults: { baseURL: 'http://localhost:8000/api' },
  },
}));

// ─── Stub the heavy StudySummaryPanel ─────────────────────────────────────────

vi.mock('../../components/student/StudySummaryPanel', () => ({
  StudySummaryPanel: ({ contentTitle, onClose }: { contentTitle: string; onClose?: () => void }) => (
    <div data-testid="study-summary-panel">
      <span>{contentTitle}</span>
      {onClose && <button onClick={onClose}>Close panel</button>}
    </div>
  ),
}));

// ─── Module mocks ─────────────────────────────────────────────────────────────

vi.mock('../../services/studentService', () => ({
  studentService: {
    getStudentCourses: vi.fn(),
    getStudySummaries: vi.fn(),
    getStudentCourseDetail: vi.fn(),
  },
}));

vi.mock('../../hooks/usePageTitle', () => ({ usePageTitle: vi.fn() }));

// ─── Import mock handles after vi.mock ────────────────────────────────────────

import { studentService } from '../../services/studentService';

const mockedStudentService = studentService as unknown as {
  [K in keyof typeof studentService]: ReturnType<typeof vi.fn>;
};

// ─── Fixtures ─────────────────────────────────────────────────────────────────

const makeCourseListItem = (overrides: Partial<{
  id: string;
  title: string;
}> = {}) => ({
  id: 'c-1',
  title: 'Math Foundations',
  slug: 'math',
  description: 'Core math',
  thumbnail: null,
  is_mandatory: false,
  deadline: null,
  estimated_hours: '3',
  is_published: true,
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  progress_percentage: 0,
  completed_content_count: 0,
  total_content_count: 5,
  ...overrides,
});

const makeCourseDetail = (courseId: string, courseTitle: string) => ({
  id: courseId,
  title: courseTitle,
  slug: 'math',
  description: 'Core math',
  thumbnail: null,
  is_mandatory: false,
  deadline: null,
  estimated_hours: '3',
  is_published: true,
  is_active: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  progress: { completed_content_count: 1, total_content_count: 5, percentage: 20 },
  modules: [
    {
      id: 'mod-1',
      title: 'Module 1: Introduction',
      description: '',
      order: 1,
      is_active: true,
      completed_content_count: 1,
      total_content_count: 3,
      completion_percentage: 33,
      is_completed: false,
      is_locked: false,
      lock_reason: '',
      contents: [
        {
          id: 'ct-1',
          title: 'Algebra Basics',
          content_type: 'DOCUMENT' as const,
          order: 1,
          is_mandatory: true,
          is_active: true,
          status: 'NOT_STARTED' as const,
          progress_percentage: 0,
          video_progress_seconds: 0,
          is_completed: false,
          is_locked: false,
          lock_reason: '',
          has_transcript: false,
        },
        {
          id: 'ct-2',
          title: 'Intro Video',
          content_type: 'VIDEO' as const,
          order: 2,
          is_mandatory: false,
          is_active: true,
          status: 'NOT_STARTED' as const,
          progress_percentage: 0,
          video_progress_seconds: 0,
          is_completed: false,
          is_locked: false,
          lock_reason: '',
          has_transcript: true, // summarizable video
        },
        {
          id: 'ct-3',
          title: 'Link Resource',
          content_type: 'LINK' as const, // NOT summarizable
          order: 3,
          is_mandatory: false,
          is_active: true,
          status: 'NOT_STARTED' as const,
          progress_percentage: 0,
          video_progress_seconds: 0,
          is_completed: false,
          is_locked: false,
          lock_reason: '',
        },
        {
          id: 'ct-4',
          title: 'Text Reading',
          content_type: 'TEXT' as const,
          order: 4,
          is_mandatory: false,
          is_active: true,
          status: 'NOT_STARTED' as const,
          progress_percentage: 0,
          video_progress_seconds: 0,
          is_completed: false,
          is_locked: false,
          lock_reason: '',
        },
      ],
    },
  ],
});

const MOCK_COURSES = [
  makeCourseListItem({ id: 'c-1', title: 'Math Foundations' }),
  makeCourseListItem({ id: 'c-2', title: 'Science Lab' }),
];

const MOCK_SUMMARIES = [
  {
    id: 'sum-1',
    content_id: 'ct-1',
    content_title: 'Algebra Basics',
    content_type: 'DOCUMENT',
    course_title: 'Math Foundations',
    status: 'READY' as const,
    is_shared: false,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 'sum-2',
    content_id: 'ct-99', // not in any expanded course detail
    content_title: 'Other Content',
    content_type: 'TEXT',
    course_title: 'Other Course',
    status: 'GENERATING' as const, // not READY — should NOT show check
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
];

// ─── Render helper ─────────────────────────────────────────────────────────────

const makeQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: Infinity, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  });

const renderPage = () =>
  render(
    <QueryClientProvider client={makeQueryClient()}>
      <MemoryRouter>
        <StudyNotesPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('StudyNotesPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockedStudentService.getStudentCourses.mockResolvedValue(MOCK_COURSES);
    mockedStudentService.getStudySummaries.mockResolvedValue(MOCK_SUMMARIES);
    mockedStudentService.getStudentCourseDetail.mockImplementation((id: string) =>
      Promise.resolve(makeCourseDetail(id, id === 'c-1' ? 'Math Foundations' : 'Science Lab')),
    );
  });

  // ── 1. Page heading ─────────────────────────────────────────────────────────

  it('renders "AI Study Summaries" h1 heading', async () => {
    renderPage();
    expect(
      await screen.findByRole('heading', { level: 1, name: /ai study summaries/i }),
    ).toBeInTheDocument();
  });

  // ── 2. Page subtitle ────────────────────────────────────────────────────────

  it('renders the subtitle describing the feature', async () => {
    renderPage();
    expect(
      await screen.findByText(/generate ai-powered summaries/i),
    ).toBeInTheDocument();
  });

  // ── 3. Loading state ────────────────────────────────────────────────────────

  it('renders a loading spinner while courses are being fetched', () => {
    mockedStudentService.getStudentCourses.mockReturnValue(new Promise(() => {}));
    renderPage();
    // The loading state renders a role="status" or aria-label="Loading" element
    const loadingEl =
      screen.queryByRole('status') ||
      document.querySelector('[aria-label="Loading"]') ||
      document.querySelector('.animate-spin');
    expect(loadingEl).not.toBeNull();
  });

  // ── 4. Course list rendered ─────────────────────────────────────────────────

  it('renders each enrolled course as an accordion row', async () => {
    renderPage();
    expect(await screen.findByText('Math Foundations')).toBeInTheDocument();
    expect(screen.getByText('Science Lab')).toBeInTheDocument();
  });

  // ── 5. Search input present ─────────────────────────────────────────────────

  it('renders the search input with correct placeholder', async () => {
    renderPage();
    expect(
      await screen.findByPlaceholderText(/search courses and content/i),
    ).toBeInTheDocument();
  });

  // ── 6. Empty state — no courses ─────────────────────────────────────────────

  it('shows "No courses available" when API returns an empty course list', async () => {
    mockedStudentService.getStudentCourses.mockResolvedValue([]);
    renderPage();
    expect(await screen.findByText(/no courses available/i)).toBeInTheDocument();
  });

  // ── 7. Expanding a course calls getStudentCourseDetail ─────────────────────

  it('calls getStudentCourseDetail when a course row is clicked to expand', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Math Foundations');

    const mathBtn = screen.getByRole('button', { name: /math foundations/i });
    await user.click(mathBtn);

    await waitFor(() => {
      expect(mockedStudentService.getStudentCourseDetail).toHaveBeenCalledWith('c-1');
    });
  });

  // ── 8. Content items shown after expansion ─────────────────────────────────

  it('shows summarizable content items after expanding a course', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Math Foundations');

    await user.click(screen.getByRole('button', { name: /math foundations/i }));

    // Algebra Basics (DOCUMENT), Intro Video (VIDEO with transcript), Text Reading (TEXT) — 3 items
    expect(await screen.findByText('Algebra Basics')).toBeInTheDocument();
    expect(screen.getByText('Intro Video')).toBeInTheDocument();
    expect(screen.getByText('Text Reading')).toBeInTheDocument();
  });

  // ── 9. Non-summarizable content (LINK) excluded ────────────────────────────

  it('does NOT show non-summarizable LINK content after expansion', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Math Foundations');

    await user.click(screen.getByRole('button', { name: /math foundations/i }));
    await screen.findByText('Algebra Basics'); // wait for items to appear

    expect(screen.queryByText('Link Resource')).not.toBeInTheDocument();
  });

  // ── 10. Content item count badge ───────────────────────────────────────────

  it('shows the summarizable content count badge once detail is loaded', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Math Foundations');

    await user.click(screen.getByRole('button', { name: /math foundations/i }));
    await screen.findByText('Algebra Basics'); // wait for items

    // 3 summarizable items: DOCUMENT + VIDEO (has_transcript) + TEXT
    expect(screen.getByText('3')).toBeInTheDocument();
  });

  // ── 11. Selecting content opens StudySummaryPanel ──────────────────────────

  it('shows the StudySummaryPanel when a content item is selected', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Math Foundations');

    await user.click(screen.getByRole('button', { name: /math foundations/i }));
    await screen.findByText('Algebra Basics');

    await user.click(screen.getByRole('button', { name: /algebra basics/i }));

    await waitFor(() => {
      expect(screen.getByTestId('study-summary-panel')).toBeInTheDocument();
    });
  });

  // ── 12. Summary available indicator shown for READY content ────────────────

  it('shows a summary-available check badge for content with a READY summary', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Math Foundations');

    await user.click(screen.getByRole('button', { name: /math foundations/i }));
    await screen.findByText('Algebra Basics');

    // "Algebra Basics" (ct-1) has a READY summary in MOCK_SUMMARIES
    const checkBadge = document.querySelector('[title="Summary available"]');
    expect(checkBadge).toBeInTheDocument();
  });

  // ── 13. Placeholder right panel shown when no content is selected ───────────

  it('shows the "Select a content item" placeholder before any content is chosen', async () => {
    renderPage();
    expect(await screen.findByText('Select a content item')).toBeInTheDocument();
    expect(
      screen.getByText(/choose a video, document, or text from the left panel/i),
    ).toBeInTheDocument();
  });

  // ── 14. Collapsing an already-expanded course hides its items ───────────────

  it('collapses and hides content items when an expanded course is clicked again', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Math Foundations');

    const mathBtn = screen.getByRole('button', { name: /math foundations/i });

    // Expand
    await user.click(mathBtn);
    await screen.findByText('Algebra Basics');

    // Collapse
    await user.click(mathBtn);
    await waitFor(() => {
      expect(screen.queryByText('Algebra Basics')).not.toBeInTheDocument();
    });
  });

  // ── 15. Search filters courses and content ─────────────────────────────────

  it('filters courses by search query — only matching courses/content shown', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Math Foundations');
    await screen.findByText('Science Lab');

    const searchInput = screen.getByPlaceholderText(/search courses and content/i);
    await user.type(searchInput, 'Science');

    await waitFor(() => {
      expect(screen.getByText('Science Lab')).toBeInTheDocument();
      expect(screen.queryByText('Math Foundations')).not.toBeInTheDocument();
    });
  });

  // ── 16. Search with no match shows empty message ───────────────────────────

  it('shows "No matching content found" when search yields no results', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Math Foundations');

    const searchInput = screen.getByPlaceholderText(/search courses and content/i);
    await user.type(searchInput, 'xyznotexist');

    await waitFor(() => {
      expect(screen.getByText('No matching content found')).toBeInTheDocument();
    });
  });

  // ── 17. Detail is only fetched once (not re-fetched on re-expand) ──────────

  it('does not call getStudentCourseDetail a second time when re-expanding a course', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('Math Foundations');

    const mathBtn = screen.getByRole('button', { name: /math foundations/i });

    // Expand → collapse → re-expand
    await user.click(mathBtn);
    await screen.findByText('Algebra Basics');
    await user.click(mathBtn);
    await user.click(mathBtn);

    // Detail was fetched only once despite three clicks
    expect(mockedStudentService.getStudentCourseDetail).toHaveBeenCalledTimes(1);
  });
});
