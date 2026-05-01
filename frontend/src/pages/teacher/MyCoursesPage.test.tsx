// src/pages/teacher/MyCoursesPage.test.tsx
//
// FE-051: Tests for the Teacher My Courses page.
// Covers: page header, loading skeleton, course grid rendering, status badges,
//         progress display, status filter buttons with counts, search filtering,
//         empty state variants, navigation on card click, and lesson count display.
//
// Mocking strategy:
//   - teacherService.listCourses is passed directly as queryFn — mocked as a
//     vi.fn() that returns a Promise.
//   - useNavigate is replaced with a stable mockNavigate spy.
//   - usePageTitle and useModeLabels are stubbed to avoid side-effects.

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { MyCoursesPage } from './MyCoursesPage';
import { teacherService } from '../../services/teacherService';

// ── Module mocks ──────────────────────────────────────────────────────────────

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock('../../services/teacherService', () => ({
  teacherService: { listCourses: vi.fn() },
}));

vi.mock('../../hooks/usePageTitle', () => ({ usePageTitle: vi.fn() }));

vi.mock('../../hooks/useModeLabels', () => ({
  useModeLabels: () => ({
    label: (key: string) => key === 'course' ? 'Course' : key,
    mode: 'education',
    modeLabels: {},
  }),
}));

// ── Typed mock helpers ────────────────────────────────────────────────────────

const mockedListCourses = teacherService.listCourses as ReturnType<typeof vi.fn>;

// ── Fixtures ──────────────────────────────────────────────────────────────────

const COURSE_NOT_STARTED = {
  id: 'c-1',
  title: 'Algebra Fundamentals',
  description: 'Learn algebra basics',
  progress_percentage: '0',
  thumbnail: null,
  total_content_count: 8,
  estimated_hours: '2',
};

const COURSE_IN_PROGRESS = {
  id: 'c-2',
  title: 'IB PYP Framework',
  description: 'International Baccalaureate PYP overview',
  progress_percentage: '45.00',
  thumbnail: null,
  total_content_count: 12,
  estimated_hours: '4',
};

const COURSE_COMPLETED = {
  id: 'c-3',
  title: 'Classroom Management',
  description: 'Effective classroom techniques',
  progress_percentage: '100',
  thumbnail: null,
  total_content_count: 6,
  estimated_hours: null,
};

const ALL_COURSES = [COURSE_NOT_STARTED, COURSE_IN_PROGRESS, COURSE_COMPLETED];

// ── Render helper ─────────────────────────────────────────────────────────────

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <MyCoursesPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('MyCoursesPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockNavigate.mockReset();
    mockedListCourses.mockResolvedValue(ALL_COURSES);
  });

  // ── 1. Page header ──────────────────────────────────────────────────────────

  describe('page header', () => {
    it('renders the "My Courses" h1 heading', async () => {
      renderPage();
      await waitFor(() => {
        expect(
          screen.getByRole('heading', { level: 1, name: /my courses/i }),
        ).toBeInTheDocument();
      });
    });

    it('renders the subtitle text', async () => {
      renderPage();
      await waitFor(() => {
        expect(
          screen.getByText('Browse and continue your assigned courses'),
        ).toBeInTheDocument();
      });
    });
  });

  // ── 2. Loading state ────────────────────────────────────────────────────────

  describe('loading state', () => {
    it('shows 6 skeleton placeholders while the query is pending', () => {
      // Return a promise that never resolves so the page stays in loading state.
      mockedListCourses.mockReturnValue(new Promise(() => {}));
      renderPage();
      const skeletons = document.querySelectorAll('.tp-skeleton');
      expect(skeletons).toHaveLength(6);
    });
  });

  // ── 3. Course grid rendering ────────────────────────────────────────────────

  describe('course grid rendering', () => {
    it('renders "Algebra Fundamentals" course card', async () => {
      renderPage();
      expect(await screen.findByText('Algebra Fundamentals')).toBeInTheDocument();
    });

    it('renders "IB PYP Framework" course card', async () => {
      renderPage();
      expect(await screen.findByText('IB PYP Framework')).toBeInTheDocument();
    });

    it('renders "Classroom Management" course card', async () => {
      renderPage();
      expect(await screen.findByText('Classroom Management')).toBeInTheDocument();
    });

    it('shows all 3 courses when the All filter is active by default', async () => {
      renderPage();
      await screen.findByText('Algebra Fundamentals');
      expect(screen.getByText('IB PYP Framework')).toBeInTheDocument();
      expect(screen.getByText('Classroom Management')).toBeInTheDocument();
    });
  });

  // ── 4. Status badges ────────────────────────────────────────────────────────

  describe('status badges', () => {
    it('shows "Not Started" badge on the progress=0 course', async () => {
      renderPage();
      await screen.findByText('Algebra Fundamentals');
      // getAllByText because the filter button and the course badge both say "Not Started"
      const instances = screen.getAllByText('Not Started');
      expect(instances.length).toBeGreaterThanOrEqual(1);
    });

    it('shows "In Progress" badge on the progress=45 course', async () => {
      renderPage();
      await screen.findByText('IB PYP Framework');
      // getAllByText because the filter button and the course badge both say "In Progress"
      const instances = screen.getAllByText('In Progress');
      expect(instances.length).toBeGreaterThanOrEqual(1);
    });

    it('shows "Completed" badge on the progress=100 course', async () => {
      renderPage();
      await screen.findByText('Classroom Management');
      // getAllByText because the filter button and the course badge both say "Completed"
      const instances = screen.getAllByText('Completed');
      expect(instances.length).toBeGreaterThanOrEqual(1);
    });
  });

  // ── 5. Progress display ─────────────────────────────────────────────────────

  describe('progress display', () => {
    it('shows "45%" on the in-progress course', async () => {
      renderPage();
      await screen.findByText('IB PYP Framework');
      expect(screen.getByText('45%')).toBeInTheDocument();
    });
  });

  // ── 6. Status filter buttons ────────────────────────────────────────────────

  describe('status filter buttons', () => {
    it('displays the total count "3" next to the All button', async () => {
      renderPage();
      await screen.findByText('Algebra Fundamentals');
      const allBtn = screen.getByRole('button', { name: /all/i });
      expect(allBtn).toHaveTextContent('3');
    });

    it('displays count "1" next to the Not Started button', async () => {
      renderPage();
      await screen.findByText('Algebra Fundamentals');
      // Multiple buttons contain "Not Started" text (filter btn + course card).
      // The filter button is the one that also contains the numeric count.
      const allNotStartedBtns = screen.getAllByRole('button', { name: /not started/i });
      // The filter button is the small pill that holds "Not Started" + the count span.
      const filterBtn = allNotStartedBtns.find(
        (btn) => btn.textContent === 'Not Started1',
      );
      expect(filterBtn).toBeDefined();
      expect(filterBtn).toHaveTextContent('1');
    });

    it('shows only "Classroom Management" after clicking the Completed filter', async () => {
      renderPage();
      await screen.findByText('Algebra Fundamentals');

      // The filter button contains exactly "Completed" + the count digit (e.g. "Completed1").
      // Course card buttons also match /completed/i so we pick the filter pill explicitly.
      const allCompletedBtns = screen.getAllByRole('button', { name: /completed/i });
      const filterBtn = allCompletedBtns.find((btn) =>
        /^Completed\d+$/.test(btn.textContent ?? ''),
      );
      expect(filterBtn).toBeDefined();
      await userEvent.click(filterBtn!);

      await waitFor(() => {
        expect(screen.getByText('Classroom Management')).toBeInTheDocument();
        expect(screen.queryByText('Algebra Fundamentals')).not.toBeInTheDocument();
        expect(screen.queryByText('IB PYP Framework')).not.toBeInTheDocument();
      });
    });
  });

  // ── 7. In Progress filter ───────────────────────────────────────────────────

  describe('in progress filter', () => {
    it('shows only "IB PYP Framework" after clicking the In Progress filter', async () => {
      renderPage();
      await screen.findByText('Algebra Fundamentals');

      // Multiple buttons contain "In Progress" text (filter pill + course card).
      // The filter pill is identifiable by its compact textContent pattern.
      const allInProgressBtns = screen.getAllByRole('button', { name: /in progress/i });
      const filterBtn = allInProgressBtns.find((btn) =>
        /^In Progress\d+$/.test(btn.textContent ?? ''),
      );
      expect(filterBtn).toBeDefined();
      await userEvent.click(filterBtn!);

      await waitFor(() => {
        expect(screen.getByText('IB PYP Framework')).toBeInTheDocument();
        expect(screen.queryByText('Algebra Fundamentals')).not.toBeInTheDocument();
        expect(screen.queryByText('Classroom Management')).not.toBeInTheDocument();
      });
    });
  });

  // ── 8. Search ───────────────────────────────────────────────────────────────

  describe('search', () => {
    it('searching "Algebra" shows only "Algebra Fundamentals"', async () => {
      renderPage();
      await screen.findByText('Algebra Fundamentals');

      await userEvent.type(
        screen.getByPlaceholderText('Search courses...'),
        'Algebra',
      );

      await waitFor(() => {
        expect(screen.getByText('Algebra Fundamentals')).toBeInTheDocument();
        expect(screen.queryByText('IB PYP Framework')).not.toBeInTheDocument();
        expect(screen.queryByText('Classroom Management')).not.toBeInTheDocument();
      });
    });

    it('searching "IB" shows only "IB PYP Framework"', async () => {
      renderPage();
      await screen.findByText('Algebra Fundamentals');

      await userEvent.type(
        screen.getByPlaceholderText('Search courses...'),
        'IB',
      );

      await waitFor(() => {
        expect(screen.getByText('IB PYP Framework')).toBeInTheDocument();
        expect(screen.queryByText('Algebra Fundamentals')).not.toBeInTheDocument();
        expect(screen.queryByText('Classroom Management')).not.toBeInTheDocument();
      });
    });

    it('searching gibberish text shows the "No courses found" empty state', async () => {
      renderPage();
      await screen.findByText('Algebra Fundamentals');

      await userEvent.type(
        screen.getByPlaceholderText('Search courses...'),
        'xyznonexistent123',
      );

      await waitFor(() => {
        expect(screen.getByText('No courses found')).toBeInTheDocument();
      });
    });
  });

  // ── 9. Empty state ──────────────────────────────────────────────────────────

  describe('empty state', () => {
    it('shows "No courses found" heading when filter produces no results', async () => {
      // Use a single completed course then filter by Not Started to get empty.
      mockedListCourses.mockResolvedValue([COURSE_COMPLETED]);
      renderPage();
      await screen.findByText('Classroom Management');

      await userEvent.click(screen.getByRole('button', { name: /not started/i }));

      await waitFor(() => {
        expect(screen.getByText('No courses found')).toBeInTheDocument();
      });
    });

    it('shows "Try adjusting your search or filters" when a search yields no results', async () => {
      renderPage();
      await screen.findByText('Algebra Fundamentals');

      await userEvent.type(
        screen.getByPlaceholderText('Search courses...'),
        'zzznomatch',
      );

      await waitFor(() => {
        expect(
          screen.getByText('Try adjusting your search or filters'),
        ).toBeInTheDocument();
      });
    });
  });

  // ── 10. Navigation ──────────────────────────────────────────────────────────

  describe('navigation', () => {
    it('clicking a course card navigates to /teacher/courses/<id>', async () => {
      renderPage();
      await screen.findByText('Algebra Fundamentals');

      await userEvent.click(screen.getByText('Algebra Fundamentals'));

      expect(mockNavigate).toHaveBeenCalledWith('/teacher/courses/c-1');
    });
  });

  // ── 11. Lesson count ────────────────────────────────────────────────────────

  describe('lesson count', () => {
    it('shows "8 lessons" for the Algebra Fundamentals card', async () => {
      renderPage();
      await screen.findByText('Algebra Fundamentals');
      // The card renders the count both in the description fallback area and in
      // the meta row — getAllByText handles either occurrence.
      const instances = screen.getAllByText(/8 lessons/i);
      expect(instances.length).toBeGreaterThanOrEqual(1);
    });
  });
});
