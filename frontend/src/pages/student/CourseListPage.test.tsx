// src/pages/student/CourseListPage.test.tsx
//
// Comprehensive Vitest + React Testing Library test suite for the Student
// CourseListPage component.
//
// Covers: page heading, subtitle, search input, status filter buttons with
// counts, course grid rendering, progress percentages, status badges, navigation
// on card click, all four status filter modes, title/description search, empty
// state variants (no enrollment vs. no match), and loading skeleton.
//
// Mocking strategy:
//   - studentService.getStudentCourses is a vi.fn() that returns a Promise.
//   - useNavigate is replaced with a stable mockedUseNavigate spy.
//   - usePageTitle is stubbed to avoid document.title side-effects.

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { CourseListPage } from './CourseListPage';
import { studentService } from '../../services/studentService';

// ── Module mocks ──────────────────────────────────────────────────────────────

const mockedUseNavigate = vi.fn();

vi.mock('../../services/studentService', () => ({
  studentService: {
    getStudentCourses: vi.fn(),
    getStudentDashboard: vi.fn(), // needed to avoid module init errors
  },
}));

vi.mock('../../hooks/usePageTitle', () => ({ usePageTitle: vi.fn() }));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockedUseNavigate };
});

// ── Typed mock helper ─────────────────────────────────────────────────────────

const mockedGetStudentCourses = studentService.getStudentCourses as ReturnType<typeof vi.fn>;

// ── Fixtures ──────────────────────────────────────────────────────────────────

const MOCK_COURSES = [
  {
    id: 'c-1',
    title: 'Math Foundations',
    description: 'Core math concepts',
    thumbnail: null,
    progress_percentage: 0,
    completed_content_count: 0,
    total_content_count: 10,
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
    description: 'Hands-on lab work',
    thumbnail: null,
    progress_percentage: 45,
    completed_content_count: 5,
    total_content_count: 11,
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
    description: 'World history',
    thumbnail: null,
    progress_percentage: 100,
    completed_content_count: 8,
    total_content_count: 8,
    deadline: null,
    estimated_hours: '0',
    slug: 'history',
    is_mandatory: false,
    is_published: true,
    is_active: true,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
];

// ── Render helper ─────────────────────────────────────────────────────────────

const makeQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: Infinity, refetchOnWindowFocus: false },
    },
  });

const renderPage = () =>
  render(
    <QueryClientProvider client={makeQueryClient()}>
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <CourseListPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('CourseListPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockedUseNavigate.mockReset();
    mockedGetStudentCourses.mockResolvedValue(MOCK_COURSES);
  });

  // ── 1. Page heading ─────────────────────────────────────────────────────────

  describe('page heading', () => {
    it('renders "My Courses" h1 heading', async () => {
      renderPage();
      await waitFor(() => {
        expect(
          screen.getByRole('heading', { level: 1, name: /my courses/i }),
        ).toBeInTheDocument();
      });
    });

    it('renders subtitle "Browse and continue your enrolled courses"', async () => {
      renderPage();
      await waitFor(() => {
        expect(
          screen.getByText('Browse and continue your enrolled courses'),
        ).toBeInTheDocument();
      });
    });
  });

  // ── 2. Search input ─────────────────────────────────────────────────────────

  describe('search input', () => {
    it('renders the search input with placeholder "Search courses..."', async () => {
      renderPage();
      // The input is present immediately (not gated on query resolution).
      expect(
        screen.getByPlaceholderText(/Search courses/i),
      ).toBeInTheDocument();
    });
  });

  // ── 3. Status filter buttons ────────────────────────────────────────────────

  describe('status filter buttons', () => {
    it('renders All, Not Started, In Progress, and Completed filter buttons', async () => {
      renderPage();
      // Wait for data so counts are populated.
      await screen.findByText('Math Foundations');

      expect(screen.getByRole('button', { name: /^All/i })).toBeInTheDocument();
      // Multiple elements may carry "Not Started" (badge + filter pill); at least
      // one button with that accessible name must exist.
      expect(
        screen.getAllByRole('button', { name: /not started/i }).length,
      ).toBeGreaterThanOrEqual(1);
      expect(
        screen.getAllByRole('button', { name: /in progress/i }).length,
      ).toBeGreaterThanOrEqual(1);
      expect(
        screen.getAllByRole('button', { name: /completed/i }).length,
      ).toBeGreaterThanOrEqual(1);
    });

    it('shows correct counts: All 3, Not Started 1, In Progress 1, Completed 1', async () => {
      renderPage();
      await screen.findByText('Math Foundations');

      // The "All" filter pill textContent is "All3".
      const allBtn = screen.getByRole('button', { name: /^All/i });
      expect(allBtn).toHaveTextContent('3');

      // Find the filter pill for each status by matching the compact
      // "<Label><digit>" text pattern — this distinguishes them from course
      // card status badges that do not contain a count digit.
      const notStartedFilter = screen
        .getAllByRole('button', { name: /not started/i })
        .find((btn) => /^Not Started\d+$/.test(btn.textContent ?? ''));
      expect(notStartedFilter).toBeDefined();
      expect(notStartedFilter).toHaveTextContent('1');

      const inProgressFilter = screen
        .getAllByRole('button', { name: /in progress/i })
        .find((btn) => /^In Progress\d+$/.test(btn.textContent ?? ''));
      expect(inProgressFilter).toBeDefined();
      expect(inProgressFilter).toHaveTextContent('1');

      const completedFilter = screen
        .getAllByRole('button', { name: /completed/i })
        .find((btn) => /^Completed\d+$/.test(btn.textContent ?? ''));
      expect(completedFilter).toBeDefined();
      expect(completedFilter).toHaveTextContent('1');
    });
  });

  // ── 4. Course grid rendering ────────────────────────────────────────────────

  describe('course grid rendering', () => {
    it('renders all three courses in grid view by default', async () => {
      renderPage();
      expect(await screen.findByText('Math Foundations')).toBeInTheDocument();
      expect(screen.getByText('Science Lab')).toBeInTheDocument();
      expect(screen.getByText('History 101')).toBeInTheDocument();
    });

    it('shows "45%" progress for Science Lab', async () => {
      renderPage();
      await screen.findByText('Science Lab');
      expect(screen.getByText('45%')).toBeInTheDocument();
    });
  });

  // ── 5. Navigation ───────────────────────────────────────────────────────────

  describe('navigation', () => {
    it('clicking a course card navigates to /student/courses/<id>', async () => {
      renderPage();
      await screen.findByText('Science Lab');

      await userEvent.click(screen.getByText('Science Lab'));

      expect(mockedUseNavigate).toHaveBeenCalledWith('/student/courses/c-2');
    });
  });

  // ── 6. Status filter — In Progress ─────────────────────────────────────────

  describe('status filter — In Progress', () => {
    it('shows only Science Lab and hides other courses', async () => {
      renderPage();
      await screen.findByText('Math Foundations');

      const inProgressFilter = screen
        .getAllByRole('button', { name: /in progress/i })
        .find((btn) => /^In Progress\d+$/.test(btn.textContent ?? ''));
      await userEvent.click(inProgressFilter!);

      await waitFor(() => {
        expect(screen.getByText('Science Lab')).toBeInTheDocument();
        expect(screen.queryByText('Math Foundations')).not.toBeInTheDocument();
        expect(screen.queryByText('History 101')).not.toBeInTheDocument();
      });
    });
  });

  // ── 7. Status filter — Completed ───────────────────────────────────────────

  describe('status filter — Completed', () => {
    it('shows only History 101 and hides other courses', async () => {
      renderPage();
      await screen.findByText('Math Foundations');

      const completedFilter = screen
        .getAllByRole('button', { name: /completed/i })
        .find((btn) => /^Completed\d+$/.test(btn.textContent ?? ''));
      await userEvent.click(completedFilter!);

      await waitFor(() => {
        expect(screen.getByText('History 101')).toBeInTheDocument();
        expect(screen.queryByText('Math Foundations')).not.toBeInTheDocument();
        expect(screen.queryByText('Science Lab')).not.toBeInTheDocument();
      });
    });
  });

  // ── 8. Status filter — Not Started ─────────────────────────────────────────

  describe('status filter — Not Started', () => {
    it('shows only Math Foundations and hides other courses', async () => {
      renderPage();
      await screen.findByText('Math Foundations');

      const notStartedFilter = screen
        .getAllByRole('button', { name: /not started/i })
        .find((btn) => /^Not Started\d+$/.test(btn.textContent ?? ''));
      await userEvent.click(notStartedFilter!);

      await waitFor(() => {
        expect(screen.getByText('Math Foundations')).toBeInTheDocument();
        expect(screen.queryByText('Science Lab')).not.toBeInTheDocument();
        expect(screen.queryByText('History 101')).not.toBeInTheDocument();
      });
    });
  });

  // ── 9. Search filtering ─────────────────────────────────────────────────────

  describe('search filtering', () => {
    it('filters by title — typing "History" shows only History 101', async () => {
      renderPage();
      await screen.findByText('Math Foundations');

      await userEvent.type(
        screen.getByPlaceholderText(/Search courses/i),
        'History',
      );

      await waitFor(() => {
        expect(screen.getByText('History 101')).toBeInTheDocument();
        expect(screen.queryByText('Math Foundations')).not.toBeInTheDocument();
        expect(screen.queryByText('Science Lab')).not.toBeInTheDocument();
      });
    });

    it('filters by description — typing "lab work" shows only Science Lab', async () => {
      renderPage();
      await screen.findByText('Math Foundations');

      await userEvent.type(
        screen.getByPlaceholderText(/Search courses/i),
        'lab work',
      );

      await waitFor(() => {
        expect(screen.getByText('Science Lab')).toBeInTheDocument();
        expect(screen.queryByText('Math Foundations')).not.toBeInTheDocument();
        expect(screen.queryByText('History 101')).not.toBeInTheDocument();
      });
    });
  });

  // ── 10. Empty state ─────────────────────────────────────────────────────────

  describe('empty state', () => {
    it('shows "No courses found" heading and filter hint after filter + search yields nothing', async () => {
      renderPage();
      await screen.findByText('Math Foundations');

      // Activate "In Progress" filter first.
      const inProgressFilter = screen
        .getAllByRole('button', { name: /in progress/i })
        .find((btn) => /^In Progress\d+$/.test(btn.textContent ?? ''));
      await userEvent.click(inProgressFilter!);

      // Then type a search that doesn't match the in-progress course.
      await userEvent.type(
        screen.getByPlaceholderText(/Search courses/i),
        'xyz',
      );

      await waitFor(() => {
        expect(screen.getByRole('heading', { name: /no courses found/i })).toBeInTheDocument();
      });
    });

    it('shows "No courses have been enrolled yet" when API returns empty array', async () => {
      mockedGetStudentCourses.mockResolvedValue([]);
      renderPage();

      await waitFor(() => {
        expect(
          screen.getByText('No courses have been enrolled yet'),
        ).toBeInTheDocument();
      });
    });

    it('shows "Try adjusting your search or filters" when search yields no match', async () => {
      renderPage();
      await screen.findByText('Math Foundations');

      await userEvent.type(
        screen.getByPlaceholderText(/Search courses/i),
        'xyznotexist',
      );

      await waitFor(() => {
        expect(
          screen.getByText('Try adjusting your search or filters'),
        ).toBeInTheDocument();
      });
    });
  });

  // ── 11. Loading skeleton ────────────────────────────────────────────────────

  describe('loading skeleton', () => {
    it('shows 6 skeleton placeholder divs while the query is pending', () => {
      // Return a promise that never resolves so the component stays in loading state.
      mockedGetStudentCourses.mockReturnValue(new Promise(() => {}));
      renderPage();

      const skeletons = document.querySelectorAll('.tp-skeleton');
      expect(skeletons).toHaveLength(6);
    });
  });

  // ── 12. All filter labels present ───────────────────────────────────────────

  describe('all filter labels', () => {
    it('renders All, Not Started, In Progress, and Completed filter pills', async () => {
      renderPage();
      await screen.findByText('Math Foundations');

      // Confirm the four filter pills exist by their compact textContent patterns.
      expect(screen.getByRole('button', { name: /^All/i })).toBeInTheDocument();

      expect(
        screen
          .getAllByRole('button', { name: /not started/i })
          .some((btn) => /^Not Started\d+$/.test(btn.textContent ?? '')),
      ).toBe(true);

      expect(
        screen
          .getAllByRole('button', { name: /in progress/i })
          .some((btn) => /^In Progress\d+$/.test(btn.textContent ?? '')),
      ).toBe(true);

      expect(
        screen
          .getAllByRole('button', { name: /completed/i })
          .some((btn) => /^Completed\d+$/.test(btn.textContent ?? '')),
      ).toBe(true);
    });
  });
});
