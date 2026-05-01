// src/pages/student/MAICBrowsePage.test.tsx
//
// Vitest + React Testing Library suite for MAICBrowsePage.
//
// Covers: page heading, subtitle, "Browse" and "My Classrooms" tabs, search
// input (shown on Browse only), classroom cards (click navigation), empty
// states for both tabs, delete action, loading spinner, Create button, and
// status badges on student-owned classrooms.
//
// Mocking strategy:
//   - maicStudentApi (listClassrooms + myClassrooms + deleteClassroom) is
//     controlled per-test via mockResolvedValue / mockRejectedValue.
//   - deleteStoredClassroom is stubbed to prevent IndexedDB access in tests.
//   - usePageTitle is stubbed to avoid document.title side-effects.
//   - useNavigate is hoisted for navigation assertions.

import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { MAICBrowsePage } from './MAICBrowsePage';

// ─── Hoist navigate mock ──────────────────────────────────────────────────────

const mockedUseNavigate = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockedUseNavigate };
});

// ─── Module mocks ─────────────────────────────────────────────────────────────

vi.mock('../../hooks/usePageTitle', () => ({ usePageTitle: vi.fn() }));

vi.mock('../../services/openmaicService', () => ({
  maicStudentApi: {
    listClassrooms: vi.fn(),
    myClassrooms: vi.fn(),
    deleteClassroom: vi.fn(),
    getClassroom: vi.fn(),
    createClassroom: vi.fn(),
  },
}));

vi.mock('../../lib/maicDb', () => ({
  deleteStoredClassroom: vi.fn().mockResolvedValue(undefined),
}));

// ─── Import mock handles after vi.mock ────────────────────────────────────────

import { maicStudentApi } from '../../services/openmaicService';
import { deleteStoredClassroom } from '../../lib/maicDb';
import type { MAICClassroomMeta } from '../../types/maic';

const mockedListClassrooms = maicStudentApi.listClassrooms as ReturnType<typeof vi.fn>;
const mockedMyClassrooms = maicStudentApi.myClassrooms as ReturnType<typeof vi.fn>;
const mockedDeleteClassroom = maicStudentApi.deleteClassroom as ReturnType<typeof vi.fn>;
const mockedDeleteStoredClassroom = deleteStoredClassroom as ReturnType<typeof vi.fn>;

// ─── Fixtures ─────────────────────────────────────────────────────────────────

const makeClassroom = (overrides: Partial<MAICClassroomMeta> = {}): MAICClassroomMeta => ({
  id: 'cls-1',
  title: 'Introduction to Photosynthesis',
  description: 'Learn how plants make food',
  topic: 'Biology',
  status: 'READY',
  is_public: true,
  scene_count: 8,
  estimated_minutes: 15,
  course_id: null,
  images_pending: false,
  created_at: '2026-03-01T00:00:00Z',
  updated_at: '2026-03-01T00:00:00Z',
  ...overrides,
});

const BROWSE_CLASSROOMS: MAICClassroomMeta[] = [
  makeClassroom({ id: 'cls-1', title: 'Introduction to Photosynthesis' }),
  makeClassroom({ id: 'cls-2', title: 'Gravity and Motion', description: 'Physics basics', scene_count: 5, estimated_minutes: 10 }),
];

const MY_CLASSROOMS: MAICClassroomMeta[] = [
  makeClassroom({ id: 'my-1', title: 'My Algebra Classroom', status: 'READY', scene_count: 6 }),
  makeClassroom({ id: 'my-2', title: 'My Chemistry Draft', status: 'DRAFT', scene_count: 0 }),
  makeClassroom({ id: 'my-3', title: 'Generating Now', status: 'GENERATING', scene_count: 0 }),
];

// ─── Helpers ──────────────────────────────────────────────────────────────────

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
        <MAICBrowsePage />
      </MemoryRouter>
    </QueryClientProvider>,
  );

// ─── Suite ────────────────────────────────────────────────────────────────────

describe('MAICBrowsePage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockedListClassrooms.mockResolvedValue({ data: BROWSE_CLASSROOMS });
    mockedMyClassrooms.mockResolvedValue({ data: MY_CLASSROOMS });
    mockedDeleteClassroom.mockResolvedValue({ data: {} });
    mockedDeleteStoredClassroom.mockResolvedValue(undefined);
  });

  // ── 1. Page heading ──────────────────────────────────────────────────────────

  it('renders the "AI Classroom" page heading', async () => {
    renderPage();
    expect(
      await screen.findByRole('heading', { level: 1, name: /ai classroom/i }),
    ).toBeInTheDocument();
  });

  // ── 2. Subtitle ───────────────────────────────────────────────────────────────

  it('renders the subtitle about browsing or creating classrooms', async () => {
    renderPage();
    expect(
      await screen.findByText(/browse classrooms or create your own ai-powered interactive lessons/i),
    ).toBeInTheDocument();
  });

  // ── 3. Create button ──────────────────────────────────────────────────────────

  it('renders a "Create" button in the header', async () => {
    renderPage();
    expect(await screen.findByRole('button', { name: /create/i })).toBeInTheDocument();
  });

  it('navigates to /student/ai-classroom/new when Create is clicked', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole('button', { name: /create$/i }));

    expect(mockedUseNavigate).toHaveBeenCalledWith('/student/ai-classroom/new');
  });

  // ── 4. Tabs render ────────────────────────────────────────────────────────────

  it('renders both "Browse" and "My Classrooms" tab buttons', async () => {
    renderPage();
    expect(await screen.findByRole('button', { name: /^browse$/i })).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: /^my classrooms$/i })).toBeInTheDocument();
  });

  // ── 5. Browse tab is the default active tab ───────────────────────────────────

  it('shows the Browse tab content by default', async () => {
    renderPage();
    expect(await screen.findByText('Introduction to Photosynthesis')).toBeInTheDocument();
    expect(await screen.findByText('Gravity and Motion')).toBeInTheDocument();
  });

  // ── 6. Search input on Browse tab ─────────────────────────────────────────────

  it('renders the search input on the Browse tab', async () => {
    renderPage();
    expect(
      await screen.findByPlaceholderText(/search classrooms/i),
    ).toBeInTheDocument();
  });

  it('hides the search input when My Classrooms tab is active', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole('button', { name: /^my classrooms$/i }));

    await waitFor(() => {
      expect(screen.queryByPlaceholderText(/search classrooms/i)).not.toBeInTheDocument();
    });
  });

  // ── 7. Search triggers refetch with search param ──────────────────────────────

  it('refetches classrooms with the typed search term', async () => {
    const user = userEvent.setup();
    renderPage();

    const input = await screen.findByPlaceholderText(/search classrooms/i);
    await user.type(input, 'photo');

    await waitFor(() => {
      // The query is keyed on the search term, so listClassrooms is called again
      expect(mockedListClassrooms).toHaveBeenCalledWith(
        expect.objectContaining({ search: 'photo' }),
      );
    });
  });

  // ── 8. Classroom cards navigate correctly ─────────────────────────────────────

  it('navigates to the classroom player when a Browse card is clicked', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByText('Introduction to Photosynthesis'));

    expect(mockedUseNavigate).toHaveBeenCalledWith('/student/ai-classroom/cls-1');
  });

  it('navigates to the classroom player when a second Browse card is clicked', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByText('Gravity and Motion'));

    expect(mockedUseNavigate).toHaveBeenCalledWith('/student/ai-classroom/cls-2');
  });

  // ── 9. My Classrooms tab ──────────────────────────────────────────────────────

  it('switches to My Classrooms tab and shows student classrooms', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole('button', { name: /^my classrooms$/i }));

    expect(await screen.findByText('My Algebra Classroom')).toBeInTheDocument();
    expect(await screen.findByText('My Chemistry Draft')).toBeInTheDocument();
    expect(await screen.findByText('Generating Now')).toBeInTheDocument();
  });

  it('navigates to the classroom player when a My-Classrooms card title is clicked', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole('button', { name: /^my classrooms$/i }));
    await user.click(await screen.findByText('My Algebra Classroom'));

    expect(mockedUseNavigate).toHaveBeenCalledWith('/student/ai-classroom/my-1');
  });

  // ── 10. Status badges ─────────────────────────────────────────────────────────

  it('shows "Ready" status badge on a READY student classroom', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole('button', { name: /^my classrooms$/i }));
    expect(await screen.findByText('Ready')).toBeInTheDocument();
  });

  it('shows "Draft" status badge on a DRAFT student classroom', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole('button', { name: /^my classrooms$/i }));
    expect(await screen.findByText('Draft')).toBeInTheDocument();
  });

  it('shows "Generating..." status badge on a GENERATING student classroom', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole('button', { name: /^my classrooms$/i }));
    expect(await screen.findByText('Generating...')).toBeInTheDocument();
  });

  // ── 11. Delete action ─────────────────────────────────────────────────────────

  it('renders a delete button for each student classroom', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole('button', { name: /^my classrooms$/i }));

    const deleteButtons = await screen.findAllByTitle('Delete classroom');
    expect(deleteButtons).toHaveLength(MY_CLASSROOMS.length);
  });

  it('calls deleteClassroom and deleteStoredClassroom with the correct id', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole('button', { name: /^my classrooms$/i }));

    const deleteButtons = await screen.findAllByTitle('Delete classroom');
    await user.click(deleteButtons[0]); // delete "My Algebra Classroom" (my-1)

    await waitFor(() => {
      expect(mockedDeleteClassroom).toHaveBeenCalledWith('my-1');
      expect(mockedDeleteStoredClassroom).toHaveBeenCalledWith('my-1');
    });
  });

  // ── 12. Browse empty state ────────────────────────────────────────────────────

  it('shows "No classrooms available" when the Browse query returns empty', async () => {
    mockedListClassrooms.mockResolvedValue({ data: [] });
    renderPage();

    expect(await screen.findByText('No classrooms available')).toBeInTheDocument();
    expect(
      await screen.findByText(/check back later for new ai classroom sessions from your teachers/i),
    ).toBeInTheDocument();
  });

  // ── 13. My Classrooms empty state ────────────────────────────────────────────

  it('shows "No classrooms yet" when My Classrooms returns empty', async () => {
    mockedMyClassrooms.mockResolvedValue({ data: [] });
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole('button', { name: /^my classrooms$/i }));

    expect(await screen.findByText('No classrooms yet')).toBeInTheDocument();
    expect(
      await screen.findByText(/create your first ai classroom on any educational topic/i),
    ).toBeInTheDocument();
  });

  it('navigates to /student/ai-classroom/new when "Create Classroom" button in empty state is clicked', async () => {
    mockedMyClassrooms.mockResolvedValue({ data: [] });
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole('button', { name: /^my classrooms$/i }));
    await user.click(await screen.findByRole('button', { name: /create classroom/i }));

    expect(mockedUseNavigate).toHaveBeenCalledWith('/student/ai-classroom/new');
  });

  // ── 14. Loading spinner ───────────────────────────────────────────────────────

  it('shows a loading spinner while the Browse classrooms query is in-flight', () => {
    mockedListClassrooms.mockReturnValue(new Promise(() => {}));
    renderPage();

    // An animate-spin div is rendered during loading
    const spinner = document.querySelector('.animate-spin');
    expect(spinner).not.toBeNull();
  });

  it('shows a loading spinner while the My Classrooms query is in-flight', async () => {
    mockedMyClassrooms.mockReturnValue(new Promise(() => {}));
    const user = userEvent.setup();
    renderPage();

    // First let the Browse tab settle, then switch
    await screen.findByText('Introduction to Photosynthesis');
    await user.click(screen.getByRole('button', { name: /^my classrooms$/i }));

    await waitFor(() => {
      const spinner = document.querySelector('.animate-spin');
      expect(spinner).not.toBeNull();
    });
  });
});
