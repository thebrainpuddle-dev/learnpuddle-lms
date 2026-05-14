// src/pages/admin/CoursesPage.test.tsx
//
// FE-038: Tests for the Admin Courses management page.
// Covers: loading state, empty states (with/without search), error states,
//         table view rendering, board (Kanban) view, search / filter,
//         delete flow, publish toggle, duplicate, bulk selection + actions,
//         pagination, and mode-label column headers.
//
// Mocking strategy:
//   - CoursesPage calls `api` directly (not via a service class), so we mock
//     `../../config/api` to control HTTP responses.
//   - `useAuthStore` is fully mocked so we can test role-gated UI (canPublish).
//   - `useModeLabels` is mocked to return deterministic label strings.
//   - `usePageTitle` is stubbed to avoid side-effects.

import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { CoursesPage } from './CoursesPage';
import { ToastProvider } from '../../components/common';
import api from '../../config/api';
import { useAuthStore } from '../../stores/authStore';

// ── Module mocks ──────────────────────────────────────────────────────────────

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return { ...actual, useNavigate: () => mockNavigate };
});

// Mock api — CoursesPage calls api.get / api.delete / api.post / api.patch directly.
vi.mock('../../config/api', () => ({
  __esModule: true,
  default: {
    get:    vi.fn(),
    post:   vi.fn(),
    patch:  vi.fn(),
    delete: vi.fn(),
    interceptors: {
      request:  { use: vi.fn() },
      response: { use: vi.fn() },
    },
  },
}));

vi.mock('../../stores/authStore');

vi.mock('../../hooks/usePageTitle', () => ({ usePageTitle: vi.fn() }));

vi.mock('../../hooks/useModeLabels', () => ({
  useModeLabels: () => ({
    label: (key: string) => {
      const map: Record<string, string> = {
        course:         'Course',
        assignment:     'Assignment',
        learner_plural: 'Teachers',
      };
      return map[key] ?? key;
    },
    mode: 'education',
    modeLabels: {},
  }),
}));

// ── Typed mock helpers ────────────────────────────────────────────────────────

const mockedApi = api as unknown as {
  get:    ReturnType<typeof vi.fn>;
  post:   ReturnType<typeof vi.fn>;
  patch:  ReturnType<typeof vi.fn>;
  delete: ReturnType<typeof vi.fn>;
};

const mockedUseAuthStore = useAuthStore as unknown as ReturnType<typeof vi.fn>;

// ── Fixtures ──────────────────────────────────────────────────────────────────

const COURSE_DRAFT = {
  id: 'c-1',
  title: 'Introduction to Teaching',
  slug: 'intro-teaching',
  description: 'A foundation course.',
  thumbnail: null,
  thumbnail_url: null,
  is_mandatory: false,
  deadline: null,
  estimated_hours: 4,
  assigned_to_all: false,
  is_published: false,
  is_active: true,
  module_count: 2,
  content_count: 5,
  assigned_teacher_count: 3,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-02T00:00:00Z',
};

const COURSE_PUBLISHED = {
  id: 'c-2',
  title: 'Advanced Pedagogy',
  slug: 'advanced-pedagogy',
  description: 'Advanced teaching techniques.',
  thumbnail: null,
  thumbnail_url: null,
  is_mandatory: true,
  deadline: '2026-06-30T00:00:00Z',
  estimated_hours: 8,
  assigned_to_all: true,
  is_published: true,
  is_active: true,
  module_count: 4,
  content_count: 12,
  assigned_teacher_count: 0,
  created_at: '2026-01-03T00:00:00Z',
  updated_at: '2026-01-04T00:00:00Z',
};

const ADMIN_USER = {
  id: 'admin-1',
  role: 'SCHOOL_ADMIN' as const,
  email: 'admin@school.com',
  first_name: 'Admin',
  last_name: 'User',
  is_active: true,
  email_verified: true,
  created_at: '2026-01-01T00:00:00Z',
};

function makePaginatedResponse(
  results = [COURSE_DRAFT, COURSE_PUBLISHED],
  extra: { next?: string | null; previous?: string | null; count?: number } = {},
) {
  return {
    count: extra.count ?? results.length,
    next: extra.next ?? null,
    previous: extra.previous ?? null,
    results,
  };
}

// ── Render helper ─────────────────────────────────────────────────────────────

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries:   { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
}

function renderPage(initialPath = '/admin/courses') {
  const qc = makeQueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }} initialEntries={[initialPath]}>
          <CoursesPage />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

// ── Global setup ──────────────────────────────────────────────────────────────

beforeEach(() => {
  vi.resetAllMocks();
  mockNavigate.mockReset();

  // Default: SCHOOL_ADMIN (canPublish = true, canDuplicate = true, canBulk = true)
  mockedUseAuthStore.mockReturnValue({ user: ADMIN_USER });

  // Default: two courses (one draft, one published)
  mockedApi.get.mockResolvedValue({ data: makePaginatedResponse() });
  mockedApi.delete.mockResolvedValue({ data: {} });
  mockedApi.patch.mockResolvedValue({ data: { ...COURSE_DRAFT, is_published: true } });
  mockedApi.post.mockImplementation((url: string) => {
    if (url === '/courses/c-1/publish/') {
      return Promise.resolve({ data: { is_published: true } });
    }
    if (url === '/courses/c-2/publish/') {
      return Promise.resolve({ data: { is_published: false } });
    }
    if (url === '/courses/bulk-action/') {
      return Promise.resolve({ data: { message: '1 course published', affected_count: 1, requested_count: 1 } });
    }
    return Promise.resolve({
      data: { ...COURSE_DRAFT, id: 'c-3', title: 'Copy of Introduction to Teaching' },
    });
  });
});

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('CoursesPage', () => {
  // ── 1. Page render states ─────────────────────────────────────────────────

  describe('page render states', () => {
    it('shows loading indicator while data is fetching', () => {
      mockedApi.get.mockReturnValue(new Promise(() => {})); // never resolves
      renderPage();
      expect(screen.getByText('Loading...')).toBeInTheDocument();
    });

    it('shows "No courses found" empty state when no courses exist', async () => {
      mockedApi.get.mockResolvedValue({ data: makePaginatedResponse([], { count: 0 }) });
      renderPage();
      await waitFor(() =>
        expect(screen.getByText('No courses found')).toBeInTheDocument(),
      );
      expect(
        screen.getByText('Get started by creating your first course'),
      ).toBeInTheDocument();
      // Empty-state Create Course button should be present
      const createBtns = screen.getAllByRole('button', { name: /create course/i });
      expect(createBtns.length).toBeGreaterThanOrEqual(1);
    });

    it('shows search-specific hint when empty due to a search query', async () => {
      const user = userEvent.setup();
      mockedApi.get.mockResolvedValue({ data: makePaginatedResponse([], { count: 0 }) });
      renderPage();

      const searchInput = screen.getByRole('searchbox');
      await user.type(searchInput, 'xyz');

      await waitFor(() =>
        expect(screen.getByText('No courses found')).toBeInTheDocument(),
      );
      expect(
        screen.getByText('Try adjusting your search or filters'),
      ).toBeInTheDocument();
      // "Get started" button should NOT appear when filtering
      expect(
        screen.queryByText('Get started by creating your first course'),
      ).not.toBeInTheDocument();
    });

    it('shows error message for a non-auth API failure', async () => {
      mockedApi.get.mockRejectedValue({ response: { status: 500 } });
      renderPage();
      await waitFor(() =>
        expect(
          screen.getByText('Failed to load courses. Please try again.'),
        ).toBeInTheDocument(),
      );
      expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
    });

    it('shows session-expired message for a 401 error', async () => {
      mockedApi.get.mockRejectedValue({ response: { status: 401 } });
      renderPage();
      await waitFor(() =>
        expect(
          screen.getByText('Your session has expired. Redirecting to login…'),
        ).toBeInTheDocument(),
      );
    });
  });

  // ── 2. Table view — course list rendering ─────────────────────────────────

  describe('table view — course list', () => {
    it('renders both course titles after data loads', async () => {
      renderPage();
      await waitFor(() =>
        expect(screen.getByText('Introduction to Teaching')).toBeInTheDocument(),
      );
      expect(screen.getByText('Advanced Pedagogy')).toBeInTheDocument();
    });

    it('shows "Draft" badge for an unpublished course', async () => {
      renderPage();
      await waitFor(() =>
        expect(screen.getByText('Introduction to Teaching')).toBeInTheDocument(),
      );
      // "Draft" also appears as a <option> in the status filter dropdown —
      // use getAllByText and verify at least one is the span badge.
      const draftEls = screen.getAllByText('Draft');
      const draftBadge = draftEls.find(
        (el) => el.tagName === 'SPAN' && el.className.includes('rounded-full'),
      );
      expect(draftBadge).toBeDefined();
    });

    it('shows "Published" badge for a published course', async () => {
      renderPage();
      await waitFor(() =>
        expect(screen.getByText('Published')).toBeInTheDocument(),
      );
    });

    it('shows "Mandatory" badge for mandatory courses', async () => {
      renderPage();
      await waitFor(() =>
        expect(screen.getByText('Mandatory')).toBeInTheDocument(),
      );
    });

    it('shows "All Teachers" for courses assigned_to_all', async () => {
      renderPage();
      await waitFor(() =>
        expect(screen.getByText('All Teachers')).toBeInTheDocument(),
      );
    });

    it('renders mode-label strings in table column headers', async () => {
      renderPage();
      await waitFor(() =>
        expect(screen.getByText('Introduction to Teaching')).toBeInTheDocument(),
      );
      // Column headers driven by label('course') and label('assignment')
      expect(screen.getByRole('columnheader', { name: 'Course' })).toBeInTheDocument();
      expect(screen.getByRole('columnheader', { name: 'Assignment' })).toBeInTheDocument();
    });
  });

  // ── 3. Search and filters ─────────────────────────────────────────────────

  describe('search and filters', () => {
    it('typing in the search box triggers api.get with search param', async () => {
      const user = userEvent.setup();
      renderPage();
      await waitFor(() =>
        expect(screen.getByText('Introduction to Teaching')).toBeInTheDocument(),
      );

      const searchInput = screen.getByRole('searchbox');
      await user.clear(searchInput);
      await user.type(searchInput, 'pedagogy');

      await waitFor(() =>
        expect(mockedApi.get).toHaveBeenCalledWith(
          expect.stringContaining('search=pedagogy'),
        ),
      );
    });

    it('selecting "Published" filter triggers api.get with is_published=true', async () => {
      const user = userEvent.setup();
      renderPage();
      await waitFor(() =>
        expect(screen.getByText('Introduction to Teaching')).toBeInTheDocument(),
      );

      const publishedSelect = screen.getByDisplayValue('All Status');
      await user.selectOptions(publishedSelect, 'true');

      await waitFor(() =>
        expect(mockedApi.get).toHaveBeenCalledWith(
          expect.stringContaining('is_published=true'),
        ),
      );
    });

    it('selecting "Mandatory" filter triggers api.get with is_mandatory=true', async () => {
      const user = userEvent.setup();
      renderPage();
      await waitFor(() =>
        expect(screen.getByText('Introduction to Teaching')).toBeInTheDocument(),
      );

      const mandatorySelect = screen.getByDisplayValue('All Types');
      await user.selectOptions(mandatorySelect, 'true');

      await waitFor(() =>
        expect(mockedApi.get).toHaveBeenCalledWith(
          expect.stringContaining('is_mandatory=true'),
        ),
      );
    });
  });

  // ── 4. Navigation ─────────────────────────────────────────────────────────

  describe('navigation', () => {
    it('clicking the Create Course button navigates to /admin/courses/new', async () => {
      const user = userEvent.setup();
      renderPage();
      await waitFor(() =>
        expect(screen.getByText('Introduction to Teaching')).toBeInTheDocument(),
      );

      // Header-level "Create Course" button
      await user.click(screen.getByRole('button', { name: /create course/i }));
      expect(mockNavigate).toHaveBeenCalledWith('/admin/courses/new');
    });

    it('clicking the Edit button navigates to /admin/courses/:id/edit', async () => {
      const user = userEvent.setup();
      renderPage();
      await waitFor(() =>
        expect(screen.getByText('Introduction to Teaching')).toBeInTheDocument(),
      );

      // Edit buttons have title="Edit" (icon-only)
      const editBtns = screen.getAllByTitle('Edit');
      await user.click(editBtns[0]);
      expect(mockNavigate).toHaveBeenCalledWith('/admin/courses/c-1/edit');
    });
  });

  // ── 5. Delete course ──────────────────────────────────────────────────────

  describe('delete course', () => {
    it('clicking the Delete trash icon opens a confirmation modal', async () => {
      const user = userEvent.setup();
      renderPage();
      await waitFor(() =>
        expect(screen.getByText('Introduction to Teaching')).toBeInTheDocument(),
      );

      await user.click(screen.getAllByTitle('Delete')[0]);

      await waitFor(() =>
        expect(screen.getByText('Delete Course')).toBeInTheDocument(),
      );
      expect(
        screen.getByText('Are you sure you want to delete this course? This action cannot be undone.'),
      ).toBeInTheDocument();
    });

    it('clicking Cancel closes the modal without calling api.delete', async () => {
      const user = userEvent.setup();
      renderPage();
      await waitFor(() =>
        expect(screen.getByText('Introduction to Teaching')).toBeInTheDocument(),
      );

      await user.click(screen.getAllByTitle('Delete')[0]);
      await waitFor(() =>
        expect(screen.getByText('Delete Course')).toBeInTheDocument(),
      );

      await user.click(screen.getByRole('button', { name: /^cancel$/i }));

      expect(screen.queryByText('Delete Course')).not.toBeInTheDocument();
      expect(mockedApi.delete).not.toHaveBeenCalled();
    });

    it('confirming delete calls api.delete and shows success toast', async () => {
      const user = userEvent.setup();
      renderPage();
      await waitFor(() =>
        expect(screen.getByText('Introduction to Teaching')).toBeInTheDocument(),
      );

      await user.click(screen.getAllByTitle('Delete')[0]);
      await waitFor(() =>
        expect(screen.getByText('Delete Course')).toBeInTheDocument(),
      );

      // The modal confirm button is inside the button-row alongside Cancel.
      // Use the Cancel button's parent container to scope the Delete click.
      const cancelBtn = screen.getByRole('button', { name: /^cancel$/i });
      const btnRow = cancelBtn.parentElement!;
      await user.click(within(btnRow).getByRole('button', { name: /^delete$/i }));

      await waitFor(() =>
        expect(mockedApi.delete).toHaveBeenCalledWith('/courses/c-1/'),
      );
      await waitFor(() =>
        expect(screen.getByText('Course deleted')).toBeInTheDocument(),
      );
    });
  });

  // ── 6. Publish / Unpublish ────────────────────────────────────────────────

  describe('publish / unpublish', () => {
    it('SCHOOL_ADMIN sees Publish / Unpublish icon buttons in each row', async () => {
      renderPage();
      await waitFor(() =>
        expect(screen.getByText('Introduction to Teaching')).toBeInTheDocument(),
      );
      // COURSE_DRAFT is not published → "Publish" button visible
      expect(screen.getByTitle('Publish')).toBeInTheDocument();
      // COURSE_PUBLISHED is published → "Unpublish" button visible
      expect(screen.getByTitle('Unpublish')).toBeInTheDocument();
    });

    it('clicking Publish calls the guarded publish endpoint', async () => {
      const user = userEvent.setup();
      renderPage();
      await waitFor(() =>
        expect(screen.getByText('Introduction to Teaching')).toBeInTheDocument(),
      );

      await user.click(screen.getByTitle('Publish'));

      await waitFor(() =>
        expect(mockedApi.post).toHaveBeenCalledWith('/courses/c-1/publish/', {
          action: 'publish',
        }),
      );
    });

    it('HOD role user does not see Publish / Unpublish buttons', async () => {
      mockedUseAuthStore.mockReturnValue({
        user: { ...ADMIN_USER, role: 'HOD' },
      });
      renderPage();
      await waitFor(() =>
        expect(screen.getByText('Introduction to Teaching')).toBeInTheDocument(),
      );
      expect(screen.queryByTitle('Publish')).not.toBeInTheDocument();
      expect(screen.queryByTitle('Unpublish')).not.toBeInTheDocument();
    });
  });

  // ── 7. Duplicate course ───────────────────────────────────────────────────

  describe('duplicate course', () => {
    it('clicking Duplicate calls api.post and navigates to the new course edit page', async () => {
      const user = userEvent.setup();
      renderPage();
      await waitFor(() =>
        expect(screen.getByText('Introduction to Teaching')).toBeInTheDocument(),
      );

      await user.click(screen.getAllByTitle('Duplicate')[0]);

      await waitFor(() =>
        expect(mockedApi.post).toHaveBeenCalledWith('/courses/c-1/duplicate/'),
      );
      await waitFor(() =>
        expect(mockNavigate).toHaveBeenCalledWith('/admin/courses/c-3/edit'),
      );
    });
  });

  // ── 8. View toggle — board (Kanban) view ──────────────────────────────────

  describe('view toggle', () => {
    it('switching to board view shows Draft and Published Kanban columns', async () => {
      const user = userEvent.setup();
      renderPage();
      await waitFor(() =>
        expect(screen.getByText('Introduction to Teaching')).toBeInTheDocument(),
      );

      await user.click(screen.getByTitle('Board view'));

      await waitFor(() => {
        // Kanban column headings
        expect(screen.getByRole('heading', { level: 3, name: 'Draft' })).toBeInTheDocument();
        expect(screen.getByRole('heading', { level: 3, name: 'Published' })).toBeInTheDocument();
      });
      // COURSE_DRAFT appears in board view
      expect(screen.getByText('Introduction to Teaching')).toBeInTheDocument();
    });

    it('switching back to table view restores table column headers', async () => {
      const user = userEvent.setup();
      renderPage();
      await waitFor(() =>
        expect(screen.getByText('Introduction to Teaching')).toBeInTheDocument(),
      );

      await user.click(screen.getByTitle('Board view'));
      await waitFor(() =>
        expect(screen.getByRole('heading', { level: 3, name: 'Draft' })).toBeInTheDocument(),
      );

      await user.click(screen.getByTitle('Table view'));

      await waitFor(() =>
        expect(screen.getByRole('columnheader', { name: 'Course' })).toBeInTheDocument(),
      );
    });
  });

  // ── 9. Bulk selection and actions ─────────────────────────────────────────

  describe('bulk selection and actions', () => {
    it('checking a row checkbox shows BulkActionsBar with "selected" label', async () => {
      const user = userEvent.setup();
      renderPage();
      await waitFor(() =>
        expect(screen.getByText('Introduction to Teaching')).toBeInTheDocument(),
      );

      await user.click(
        screen.getByRole('checkbox', { name: /select introduction to teaching/i }),
      );

      await waitFor(() =>
        expect(screen.getByText('selected')).toBeInTheDocument(),
      );
    });

    it('Select All selects every course in the current page', async () => {
      const user = userEvent.setup();
      renderPage();
      await waitFor(() =>
        expect(screen.getByText('Introduction to Teaching')).toBeInTheDocument(),
      );

      await user.click(
        screen.getByRole('checkbox', { name: /select all courses/i }),
      );

      // BulkActionsBar shows count badge = 2
      await waitFor(() => {
        const badge = screen.getByText('2');
        expect(badge).toBeInTheDocument();
      });
      expect(screen.getByText('selected')).toBeInTheDocument();
    });

    it('clicking Bulk Publish calls api.post with publish action', async () => {
      mockedApi.post.mockResolvedValue({
        data: { message: '1 course published', affected_count: 1, requested_count: 1 },
      });
      const user = userEvent.setup();
      renderPage();
      await waitFor(() =>
        expect(screen.getByText('Introduction to Teaching')).toBeInTheDocument(),
      );

      await user.click(
        screen.getByRole('checkbox', { name: /select introduction to teaching/i }),
      );

      // Row-level icon buttons also carry accessible name "Publish" via title="Publish".
      // Scope to the BulkActionsBar fixed container to avoid ambiguity.
      const selectedLabel = await screen.findByText('selected');
      const bulkBar = selectedLabel.closest('div[class*="fixed"]')!;
      const publishBtn = within(bulkBar).getByRole('button', { name: /^publish$/i });
      await user.click(publishBtn);

      await waitFor(() =>
        expect(mockedApi.post).toHaveBeenCalledWith('/courses/bulk-action/', {
          action: 'publish',
          course_ids: ['c-1'],
        }),
      );
    });

    it('clicking Bulk Delete shows a confirmation dialog before executing', async () => {
      const user = userEvent.setup();
      renderPage();
      await waitFor(() =>
        expect(screen.getByText('Introduction to Teaching')).toBeInTheDocument(),
      );

      await user.click(
        screen.getByRole('checkbox', { name: /select introduction to teaching/i }),
      );

      // Row-level trash-icon buttons also have accessible name "Delete" via title.
      // Scope to the BulkActionsBar to get the bulk-action Delete button only.
      const selectedLabel = await screen.findByText('selected');
      const bulkBar = selectedLabel.closest('div[class*="fixed"]')!;
      const bulkDeleteBtn = within(bulkBar).getByRole('button', { name: /^delete$/i });
      await user.click(bulkDeleteBtn);

      // BulkActionsBar requiresConfirmation=true → Headless UI Dialog opens
      await waitFor(() =>
        expect(screen.getByRole('dialog')).toBeInTheDocument(),
      );
    });
  });

  // ── 10. Pagination ────────────────────────────────────────────────────────

  describe('pagination', () => {
    it('shows "Next" button when data.next is set', async () => {
      mockedApi.get.mockResolvedValue({
        data: makePaginatedResponse([COURSE_DRAFT], {
          count: 20,
          next: '/courses/?page=2',
        }),
      });
      renderPage();
      await waitFor(() =>
        expect(screen.getByText('Introduction to Teaching')).toBeInTheDocument(),
      );
      // The pagination strip renders two sets of Next/Previous buttons (mobile + desktop)
      // because CSS responsive hiding doesn't apply in jsdom. Use getAllByRole.
      const nextBtns = screen.getAllByRole('button', { name: /next/i });
      expect(nextBtns.length).toBeGreaterThanOrEqual(1);
    });

    it('shows "Previous" button when data.previous is set', async () => {
      mockedApi.get.mockResolvedValue({
        data: makePaginatedResponse([COURSE_PUBLISHED], {
          count: 20,
          previous: '/courses/?page=1',
        }),
      });
      renderPage();
      await waitFor(() =>
        expect(screen.getByText('Advanced Pedagogy')).toBeInTheDocument(),
      );
      const prevBtns = screen.getAllByRole('button', { name: /previous/i });
      expect(prevBtns.length).toBeGreaterThanOrEqual(1);
    });
  });
});
