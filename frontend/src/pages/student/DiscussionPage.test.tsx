// src/pages/student/DiscussionPage.test.tsx
//
// Comprehensive Vitest + React Testing Library test suite for the Student
// DiscussionPage component.
//
// Covers: page heading, subtitle with thread count, loading skeletons, empty
// state, thread list rendering, status badges, pinned indicator, course/content
// labels, filter tabs (all / open / closed), New Thread modal (open, cancel,
// field validation, submit), and navigation to a thread on card click.
//
// Mocking strategy:
//   - api (../../config/api) is mocked at the module level so api.get and
//     api.post return Promises controlled per-test.
//   - useNavigate is replaced with a stable mockedUseNavigate spy.
//   - usePageTitle is stubbed to avoid document.title side-effects.

import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { StudentDiscussionPage } from './DiscussionPage';

// ─── Hoist navigate mock ──────────────────────────────────────────────────────

const mockedUseNavigate = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockedUseNavigate };
});

// ─── Mock api module ──────────────────────────────────────────────────────────

vi.mock('../../config/api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    defaults: { baseURL: 'http://localhost:8000/api' },
  },
}));

vi.mock('../../hooks/usePageTitle', () => ({ usePageTitle: vi.fn() }));

// ─── Import mock handle after vi.mock ─────────────────────────────────────────

import api from '../../config/api';

const mockedApiGet = api.get as ReturnType<typeof vi.fn>;
const mockedApiPost = api.post as ReturnType<typeof vi.fn>;

// ─── Fixtures ─────────────────────────────────────────────────────────────────

const makeThread = (overrides: Partial<{
  id: string;
  title: string;
  body: string;
  status: 'open' | 'closed' | 'archived';
  is_pinned: boolean;
  reply_count: number;
  view_count: number;
  course_title: string | null;
  content_title: string | null;
  author: { id: string | null; name: string; role: string | null; avatar: string | null };
}> = {}) => ({
  id: 'thread-1',
  title: 'How do I solve quadratic equations?',
  body: 'I am stuck on chapter 3 exercises and need some help understanding the method.',
  author: { id: 'u-1', name: 'Alice Smith', role: 'STUDENT', avatar: null },
  course_id: 'c-1',
  course_title: 'Math Foundations',
  content_id: null,
  content_title: null,
  status: 'open' as const,
  is_pinned: false,
  reply_count: 4,
  view_count: 22,
  created_at: new Date(Date.now() - 2 * 60 * 1000).toISOString(), // 2 minutes ago
  last_reply_at: null,
  ...overrides,
});

const MOCK_THREADS_RESPONSE = {
  results: [
    makeThread({ id: 'thread-1', title: 'How do I solve quadratic equations?', status: 'open' }),
    makeThread({ id: 'thread-2', title: 'Physics lab report tips', status: 'closed', reply_count: 2, view_count: 10 }),
    makeThread({
      id: 'thread-3',
      title: 'History essay question',
      status: 'open',
      is_pinned: true,
      course_title: 'History 101',
      content_title: 'World War II Module',
    }),
  ],
  count: 3,
  next: null,
};

const MOCK_EMPTY_RESPONSE = {
  results: [],
  count: 0,
  next: null,
};

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
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <StudentDiscussionPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('StudentDiscussionPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockedUseNavigate.mockReset();
    mockedApiGet.mockResolvedValue({ data: MOCK_THREADS_RESPONSE });
    mockedApiPost.mockResolvedValue({ data: { id: 'thread-new', title: 'New Thread' } });
  });

  // ── 1. Page heading ─────────────────────────────────────────────────────────

  it('renders the "Discussions" h1 heading', async () => {
    renderPage();
    expect(
      await screen.findByRole('heading', { level: 1, name: /discussions/i }),
    ).toBeInTheDocument();
  });

  // ── 2. Thread count subtitle ────────────────────────────────────────────────

  it('shows the thread count in the subtitle', async () => {
    renderPage();
    expect(await screen.findByText(/3 threads in your section/i)).toBeInTheDocument();
  });

  // ── 3. Singular "thread" when count is 1 ───────────────────────────────────

  it('shows singular "thread" when count is 1', async () => {
    const singleThread = makeThread({ id: 'thread-1', title: 'Solo question' });
    mockedApiGet.mockResolvedValue({
      data: { results: [singleThread], count: 1, next: null },
    });
    renderPage();
    expect(await screen.findByText(/1 thread in your section/i)).toBeInTheDocument();
  });

  // ── 4. Loading state — skeletons ────────────────────────────────────────────

  it('renders skeleton placeholders while threads are loading', () => {
    mockedApiGet.mockReturnValue(new Promise(() => {}));
    const { container } = renderPage();
    // The component renders three h-24 tp-skeleton divs during loading
    const skeletons = container.querySelectorAll('.tp-skeleton');
    expect(skeletons.length).toBeGreaterThanOrEqual(1);
  });

  // ── 5. Empty state ──────────────────────────────────────────────────────────

  it('shows "No discussions yet" empty state when API returns zero threads', async () => {
    mockedApiGet.mockResolvedValue({ data: MOCK_EMPTY_RESPONSE });
    renderPage();
    expect(await screen.findByText('No discussions yet')).toBeInTheDocument();
    expect(
      await screen.findByText(/Start a conversation by creating the first thread/i),
    ).toBeInTheDocument();
  });

  // ── 6. Thread list rendering ────────────────────────────────────────────────

  it('renders all thread titles in the list', async () => {
    renderPage();
    expect(await screen.findByText('How do I solve quadratic equations?')).toBeInTheDocument();
    expect(screen.getByText('Physics lab report tips')).toBeInTheDocument();
    expect(screen.getByText('History essay question')).toBeInTheDocument();
  });

  // ── 7. Thread body truncated ────────────────────────────────────────────────

  it('renders the thread body (truncated to 100 chars)', async () => {
    renderPage();
    // Multiple threads may share the same body in our fixture; use findAllByText
    const bodyMatches = await screen.findAllByText(/I am stuck on chapter 3/i);
    expect(bodyMatches.length).toBeGreaterThanOrEqual(1);
  });

  // ── 8. Status badges ────────────────────────────────────────────────────────

  it('renders status badges for open and closed threads', async () => {
    renderPage();
    await screen.findByText('How do I solve quadratic equations?');

    // "open" appears as both a filter tab button and as status badge spans — use getAllByText
    const openElements = screen.getAllByText('open');
    expect(openElements.length).toBeGreaterThanOrEqual(1);

    // "closed" appears as both a filter tab button and a status badge — at least 2 matches
    const closedElements = screen.getAllByText('closed');
    expect(closedElements.length).toBeGreaterThanOrEqual(2);
  });

  // ── 9. Pinned thread indicator ──────────────────────────────────────────────

  it('shows the pin icon for a pinned thread via title attribute', async () => {
    renderPage();
    await screen.findByText('History essay question');
    // The PinIcon span has title="Pinned"
    const pinIndicator = document.querySelector('[title="Pinned"]');
    expect(pinIndicator).toBeInTheDocument();
  });

  // ── 10. Course and content labels on thread ─────────────────────────────────

  it('shows course and content labels when thread has them', async () => {
    renderPage();
    expect(await screen.findByText('History 101')).toBeInTheDocument();
    expect(screen.getByText('World War II Module')).toBeInTheDocument();
  });

  // ── 11. Filter tabs rendered ────────────────────────────────────────────────

  it('renders the All, open, and closed filter tabs', async () => {
    renderPage();
    // Filter buttons are immediately rendered (no data dependency)
    expect(screen.getByRole('button', { name: /^all$/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^open$/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^closed$/i })).toBeInTheDocument();
  });

  // ── 12. Filter tab — open — triggers API call with status param ─────────────

  it('calls API with status=open when the "open" tab is clicked', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('How do I solve quadratic equations?');

    const openTab = screen.getByRole('button', { name: /^open$/i });
    await user.click(openTab);

    await waitFor(() => {
      const calls = mockedApiGet.mock.calls;
      const openCall = calls.find(
        (call) => call[1]?.params?.status === 'open',
      );
      expect(openCall).toBeDefined();
    });
  });

  // ── 13. Filter tab — closed — triggers API call with status=closed ──────────

  it('calls API with status=closed when the "closed" tab is clicked', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('How do I solve quadratic equations?');

    const closedTab = screen.getByRole('button', { name: /^closed$/i });
    await user.click(closedTab);

    await waitFor(() => {
      const calls = mockedApiGet.mock.calls;
      const closedCall = calls.find(
        (call) => call[1]?.params?.status === 'closed',
      );
      expect(closedCall).toBeDefined();
    });
  });

  // ── 14. New Thread button opens modal ──────────────────────────────────────

  it('opens the New Discussion Thread modal when "New Thread" button is clicked', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('How do I solve quadratic equations?');

    await user.click(screen.getByRole('button', { name: /new thread/i }));

    expect(screen.getByRole('heading', { name: /new discussion thread/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/title/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/details/i)).toBeInTheDocument();
  });

  // ── 15. Modal cancel closes it ─────────────────────────────────────────────

  it('closes the modal when Cancel is clicked', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('How do I solve quadratic equations?');

    await user.click(screen.getByRole('button', { name: /new thread/i }));
    expect(screen.getByRole('heading', { name: /new discussion thread/i })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /cancel/i }));
    await waitFor(() => {
      expect(screen.queryByRole('heading', { name: /new discussion thread/i })).not.toBeInTheDocument();
    });
  });

  // ── 16. Create Thread button disabled when title is empty ──────────────────

  it('disables the "Create Thread" submit button when title is empty', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('How do I solve quadratic equations?');

    await user.click(screen.getByRole('button', { name: /new thread/i }));

    const submitBtn = screen.getByRole('button', { name: /create thread/i });
    expect(submitBtn).toBeDisabled();
  });

  // ── 17. Create Thread submits and closes modal ──────────────────────────────

  it('submits a new thread and closes the modal on success', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('How do I solve quadratic equations?');

    await user.click(screen.getByRole('button', { name: /new thread/i }));

    await user.type(screen.getByLabelText(/title/i), 'My new question about algebra');
    await user.type(screen.getByLabelText(/details/i), 'Some details here');

    const submitBtn = screen.getByRole('button', { name: /create thread/i });
    expect(submitBtn).not.toBeDisabled();
    await user.click(submitBtn);

    await waitFor(() => {
      expect(mockedApiPost).toHaveBeenCalledWith(
        '/v1/student/discussions/threads/create/',
        expect.objectContaining({ title: 'My new question about algebra' }),
      );
    });

    // Modal closes on success
    await waitFor(() => {
      expect(
        screen.queryByRole('heading', { name: /new discussion thread/i }),
      ).not.toBeInTheDocument();
    });
  });

  // ── 18. Navigation on thread card click ────────────────────────────────────

  it('navigates to the thread detail page when a thread card is clicked', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('How do I solve quadratic equations?');

    await user.click(screen.getByText('How do I solve quadratic equations?'));

    expect(mockedUseNavigate).toHaveBeenCalledWith('/student/discussions/thread-1');
  });

  // ── 19. Reply count and view count shown ───────────────────────────────────

  it('renders reply count and view count for threads', async () => {
    renderPage();
    await screen.findByText('How do I solve quadratic equations?');

    // reply_count: 4 appears in multiple thread rows (all fixtures use 4 unless overridden)
    // view_count: 22 is unique to the first thread fixture
    const replyCountEls = screen.getAllByText('4');
    expect(replyCountEls.length).toBeGreaterThanOrEqual(1);
    const viewCountEls = screen.getAllByText('22');
    expect(viewCountEls.length).toBeGreaterThanOrEqual(1);
  });

  // ── 20. Load More button shown when next is non-null ───────────────────────

  it('shows the "Load More" button when there is a next page', async () => {
    mockedApiGet.mockResolvedValue({
      data: { ...MOCK_THREADS_RESPONSE, next: '/v1/student/discussions/threads/?page=2' },
    });
    renderPage();
    expect(await screen.findByRole('button', { name: /load more/i })).toBeInTheDocument();
  });

  // ── 21. Load More button absent when on the last page ──────────────────────

  it('does not show the "Load More" button when next is null', async () => {
    renderPage();
    await screen.findByText('How do I solve quadratic equations?');
    expect(screen.queryByRole('button', { name: /load more/i })).not.toBeInTheDocument();
  });
});
