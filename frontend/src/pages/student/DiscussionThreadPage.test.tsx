// src/pages/student/DiscussionThreadPage.test.tsx
//
// Comprehensive Vitest + React Testing Library test suite for the
// StudentDiscussionThreadPage component.
//
// Covers: loading state, not-found state, back navigation, thread header
// rendering (title, body, status badge, author, view/reply counts,
// course/content labels), subscribe button states + mutation, replies section
// heading, empty-replies state, reply card rendering (teacher badge, like
// count, edited indicator, Reply/Edit/Delete buttons), edit flow, delete flow
// (ConfirmDialog), reply input visibility (open vs. closed), reply submission,
// and the "Replying to" context banner.
//
// Mocking strategy:
//   - api (../../config/api) is mocked at the module level.
//   - useAuthStore is mocked to return { user: { id: 'user-1' } } by default
//     so the current user owns reply-2 (Bob) in the fixture.
//   - useNavigate / useParams are patched via react-router-dom mock.
//   - usePageTitle is stubbed to suppress document.title side-effects.
//   - ConfirmDialog is replaced with a simple test double.

import React from 'react';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { StudentDiscussionThreadPage } from './DiscussionThreadPage';

// ─── Hoist navigate mock ──────────────────────────────────────────────────────

const mockedUseNavigate = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockedUseNavigate,
    useParams: () => ({ threadId: 'thread-1' }),
  };
});

// ─── Mock api module ──────────────────────────────────────────────────────────

vi.mock('../../config/api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    defaults: { baseURL: 'http://localhost:8000/api' },
  },
}));

// ─── Mock stores ──────────────────────────────────────────────────────────────

vi.mock('../../stores/authStore', () => ({
  useAuthStore: vi.fn(),
}));

// ─── Mock usePageTitle ────────────────────────────────────────────────────────

vi.mock('../../hooks/usePageTitle', () => ({ usePageTitle: vi.fn() }));

// ─── Mock ConfirmDialog ───────────────────────────────────────────────────────

vi.mock('../../components/common/ConfirmDialog', () => ({
  ConfirmDialog: ({ isOpen, onClose, onConfirm, confirmLabel }: any) =>
    isOpen ? (
      <div data-testid="confirm-dialog">
        <button onClick={onConfirm}>{confirmLabel ?? 'Confirm'}</button>
        <button onClick={onClose}>Cancel</button>
      </div>
    ) : null,
}));

// ─── Import mock handles after vi.mock ────────────────────────────────────────

import api from '../../config/api';
import { useAuthStore } from '../../stores/authStore';

const mockedApiGet = api.get as ReturnType<typeof vi.fn>;
const mockedApiPost = api.post as ReturnType<typeof vi.fn>;
const mockedApiPut = api.put as ReturnType<typeof vi.fn>;
const mockedApiDelete = api.delete as ReturnType<typeof vi.fn>;
const mockedUseAuthStore = useAuthStore as ReturnType<typeof vi.fn>;

// ─── Fixtures ─────────────────────────────────────────────────────────────────

const MOCK_THREAD = {
  id: 'thread-1',
  title: 'How do photosynthesis work?',
  body: 'I am confused about the light reactions.',
  author: { id: 'user-99', name: 'Alice Chen', role: 'STUDENT', avatar: null },
  course_title: 'Biology 101',
  content_title: null,
  status: 'open' as const,
  is_pinned: false,
  is_subscribed: false,
  can_edit: false,
  reply_count: 2,
  view_count: 15,
  created_at: new Date(Date.now() - 60 * 60 * 1000).toISOString(),
  replies: [
    {
      id: 'reply-1',
      body: 'Great question! Photosynthesis has two stages.',
      author: { id: 'teacher-1', name: 'Mr. Smith', role: 'TEACHER', avatar: null },
      like_count: 3,
      is_liked: false,
      is_edited: false,
      depth: 0,
      parent_id: null,
      created_at: new Date(Date.now() - 30 * 60 * 1000).toISOString(),
      children: [],
    },
    {
      id: 'reply-2',
      body: 'Thank you for the explanation!',
      author: { id: 'user-1', name: 'Bob', role: 'STUDENT', avatar: null },
      like_count: 0,
      is_liked: false,
      is_edited: true,
      depth: 0,
      parent_id: null,
      created_at: new Date(Date.now() - 15 * 60 * 1000).toISOString(),
      children: [],
    },
  ],
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
        <StudentDiscussionThreadPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('StudentDiscussionThreadPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockedUseNavigate.mockReset();
    // Default: current user is user-1 (owns reply-2 / Bob)
    mockedUseAuthStore.mockImplementation((selector: any) =>
      selector({ user: { id: 'user-1' } }),
    );
    // Default: successful thread fetch
    mockedApiGet.mockResolvedValue({ data: MOCK_THREAD });
    // Default: mutations resolve cleanly
    mockedApiPost.mockResolvedValue({ data: {} });
    mockedApiPut.mockResolvedValue({ data: {} });
    mockedApiDelete.mockResolvedValue({ data: {} });
  });

  // ── 1. Loading state ─────────────────────────────────────────────────────────

  it('shows tp-skeleton divs while the thread is loading', () => {
    mockedApiGet.mockReturnValue(new Promise(() => {}));
    const { container } = renderPage();
    const skeletons = container.querySelectorAll('.tp-skeleton');
    expect(skeletons.length).toBeGreaterThanOrEqual(1);
  });

  it('does not render the thread title while loading', () => {
    mockedApiGet.mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.queryByRole('heading', { level: 1 })).not.toBeInTheDocument();
  });

  // ── 2. Not found state ───────────────────────────────────────────────────────

  it('shows "Thread not found" when the API returns null data', async () => {
    mockedApiGet.mockResolvedValue({ data: null });
    renderPage();
    expect(await screen.findByText('Thread not found')).toBeInTheDocument();
    expect(
      screen.getByText(/This discussion thread may have been deleted/i),
    ).toBeInTheDocument();
  });

  // ── 3. Back button ───────────────────────────────────────────────────────────

  it('renders the Back to Discussions button', async () => {
    renderPage();
    expect(await screen.findByRole('button', { name: /back to discussions/i })).toBeInTheDocument();
  });

  it('navigates to /student/discussions when Back button is clicked', async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('button', { name: /back to discussions/i }));
    expect(mockedUseNavigate).toHaveBeenCalledWith('/student/discussions');
  });

  // ── 4. Thread header — title ─────────────────────────────────────────────────

  it('renders the thread title as an h1 heading', async () => {
    renderPage();
    expect(
      await screen.findByRole('heading', { level: 1, name: 'How do photosynthesis work?' }),
    ).toBeInTheDocument();
  });

  // ── 5. Thread header — body ──────────────────────────────────────────────────

  it('renders the thread body text', async () => {
    renderPage();
    expect(
      await screen.findByText('I am confused about the light reactions.'),
    ).toBeInTheDocument();
  });

  // ── 6. Thread header — status badge ─────────────────────────────────────────

  it('renders the open status badge', async () => {
    renderPage();
    // At least one span/element with the text "open" (the badge)
    const openEls = await screen.findAllByText('open');
    expect(openEls.length).toBeGreaterThanOrEqual(1);
  });

  // ── 7. Thread header — author name ──────────────────────────────────────────

  it('renders the thread author name in the header', async () => {
    renderPage();
    expect(await screen.findByText('Alice Chen')).toBeInTheDocument();
  });

  // ── 8. View count + reply count ──────────────────────────────────────────────

  it('renders the view count in the thread footer', async () => {
    renderPage();
    expect(await screen.findByText('15 views')).toBeInTheDocument();
  });

  it('renders the reply count in the thread footer', async () => {
    renderPage();
    expect(await screen.findByText('2 replies')).toBeInTheDocument();
  });

  // ── 9. Course / content labels ───────────────────────────────────────────────

  it('shows the course label when course_title is set', async () => {
    renderPage();
    expect(await screen.findByText('Biology 101')).toBeInTheDocument();
  });

  it('does not show a content label when content_title is null', async () => {
    renderPage();
    await screen.findByText('Biology 101'); // wait for data
    // content_title is null in the fixture — no separate label expected
    expect(screen.queryByText('content_title')).not.toBeInTheDocument();
  });

  it('shows the content label when content_title is set', async () => {
    mockedApiGet.mockResolvedValue({
      data: { ...MOCK_THREAD, content_title: 'Light Reactions Module' },
    });
    renderPage();
    expect(await screen.findByText('Light Reactions Module')).toBeInTheDocument();
  });

  it('does not render the labels container when both course_title and content_title are null', async () => {
    mockedApiGet.mockResolvedValue({
      data: { ...MOCK_THREAD, course_title: null, content_title: null },
    });
    renderPage();
    await screen.findByRole('heading', { level: 1 });
    expect(screen.queryByText('Biology 101')).not.toBeInTheDocument();
  });

  // ── 10. Subscribe button — unsubscribed state ────────────────────────────────

  it('shows "Subscribe" when is_subscribed is false', async () => {
    renderPage();
    expect(await screen.findByRole('button', { name: /subscribe/i })).toBeInTheDocument();
    // Make sure the text is "Subscribe", not "Subscribed"
    expect(screen.getByRole('button', { name: /^subscribe$/i })).toBeInTheDocument();
  });

  // ── 11. Subscribe button — subscribed state ──────────────────────────────────

  it('shows "Subscribed" when is_subscribed is true', async () => {
    mockedApiGet.mockResolvedValue({ data: { ...MOCK_THREAD, is_subscribed: true } });
    renderPage();
    expect(await screen.findByRole('button', { name: /subscribed/i })).toBeInTheDocument();
  });

  // ── 12. Subscribe click calls the API ────────────────────────────────────────

  it('calls api.post for subscribe when the Subscribe button is clicked', async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('button', { name: /^subscribe$/i }));
    await waitFor(() => {
      expect(mockedApiPost).toHaveBeenCalledWith(
        '/v1/student/discussions/threads/thread-1/subscribe/',
      );
    });
  });

  // ── 13. Replies section heading ──────────────────────────────────────────────

  it('renders "Replies" h2 with the count in parentheses', async () => {
    renderPage();
    expect(await screen.findByRole('heading', { level: 2, name: /replies/i })).toBeInTheDocument();
    // reply_count = 2
    expect(screen.getByText('(2)')).toBeInTheDocument();
  });

  // ── 14. Empty replies state ──────────────────────────────────────────────────

  it('shows "No replies yet. Be the first to respond!" when replies array is empty', async () => {
    mockedApiGet.mockResolvedValue({ data: { ...MOCK_THREAD, replies: [] } });
    renderPage();
    expect(
      await screen.findByText('No replies yet. Be the first to respond!'),
    ).toBeInTheDocument();
  });

  // ── 15. Reply card — author name + body ─────────────────────────────────────

  it('renders each reply card with its author name and body', async () => {
    renderPage();
    expect(await screen.findByText('Mr. Smith')).toBeInTheDocument();
    expect(screen.getByText('Great question! Photosynthesis has two stages.')).toBeInTheDocument();
    expect(screen.getByText('Bob')).toBeInTheDocument();
    expect(screen.getByText('Thank you for the explanation!')).toBeInTheDocument();
  });

  // ── 16. Teacher badge ────────────────────────────────────────────────────────

  it('shows "Teacher" badge for a reply whose author role is TEACHER', async () => {
    renderPage();
    expect(await screen.findByText('Teacher')).toBeInTheDocument();
  });

  it('does not show a "Teacher" badge for STUDENT replies', async () => {
    renderPage();
    await screen.findByText('Bob'); // wait for data
    // Only one Teacher badge (for Mr. Smith)
    expect(screen.queryAllByText('Teacher').length).toBe(1);
  });

  // ── 17. Like count ───────────────────────────────────────────────────────────

  it('shows the like count when like_count > 0', async () => {
    renderPage();
    // reply-1 has like_count = 3
    expect(await screen.findByText('3')).toBeInTheDocument();
  });

  // ── 18. "(edited)" indicator ─────────────────────────────────────────────────

  it('shows "(edited)" for a reply where is_edited is true', async () => {
    renderPage();
    expect(await screen.findByText('(edited)')).toBeInTheDocument();
  });

  // Helper: returns all per-card "Reply" action buttons (inline-flex, not type=submit)
  // The ReplyCard's Reply button has class "inline-flex" and is NOT type=submit.
  // The form submit button is type="submit".
  const getReplyActionBtns = (container: HTMLElement) =>
    Array.from(container.querySelectorAll('button:not([type="submit"])')).filter(
      (btn) => btn.textContent?.trim() === 'Reply',
    );

  // ── 19. "Reply" button — visible when depth < MAX_NESTING_DEPTH ─────────────

  it('shows "Reply" action buttons on replies whose depth is less than 3', async () => {
    const { container } = renderPage();
    await screen.findByText('Mr. Smith');
    // Both fixture replies are at depth 0 — both should have a per-card Reply action button
    expect(getReplyActionBtns(container).length).toBeGreaterThanOrEqual(2);
  });

  // ── 20. "Reply" button — absent when depth >= MAX_NESTING_DEPTH ─────────────

  it('hides the per-reply "Reply" action button on replies at depth >= 3', async () => {
    mockedApiGet.mockResolvedValue({
      data: {
        ...MOCK_THREAD,
        replies: [
          {
            ...MOCK_THREAD.replies[0],
            id: 'reply-deep',
            depth: 3,
          },
        ],
      },
    });
    const { container } = renderPage();
    await screen.findByText('Mr. Smith');
    // depth = 3 → canNest is false → no per-card Reply action button rendered
    expect(getReplyActionBtns(container).length).toBe(0);
  });

  // ── 21. Own reply — Edit and Delete buttons ──────────────────────────────────

  it('shows Edit and Delete buttons only for the current user own reply', async () => {
    renderPage();
    await screen.findByText('Bob');
    // Edit and Delete are only on reply-2 (Bob, user-1 = current user)
    expect(screen.getByRole('button', { name: /edit/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /delete/i })).toBeInTheDocument();
    // There is one Teacher reply (Mr. Smith, teacher-1 != user-1) — no extra edit/delete
    expect(screen.queryAllByRole('button', { name: /edit/i }).length).toBe(1);
    expect(screen.queryAllByRole('button', { name: /delete/i }).length).toBe(1);
  });

  // ── 22. Edit flow ────────────────────────────────────────────────────────────

  it('clicking Edit replaces the body with a textarea pre-filled with the reply body', async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('button', { name: /edit/i }));
    // After clicking Edit there are two textareas: the edit textarea (index 0)
    // and the reply input at the bottom (index 1).  The edit one is first.
    const textareas = screen.getAllByRole('textbox') as HTMLTextAreaElement[];
    expect(textareas[0].value).toBe('Thank you for the explanation!');
  });

  it('clicking Cancel in edit mode reverts to the original body text', async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('button', { name: /edit/i }));
    // The edit textarea is the first textbox in the DOM
    const editTextarea = screen.getAllByRole('textbox')[0] as HTMLTextAreaElement;
    await user.clear(editTextarea);
    await user.type(editTextarea, 'Modified text');
    await user.click(screen.getByRole('button', { name: /cancel/i }));
    // Original body is back; only the reply input textbox remains
    expect(screen.getByText('Thank you for the explanation!')).toBeInTheDocument();
    // After cancel the edit textarea is gone — only the reply input remains
    expect(screen.getAllByRole('textbox').length).toBe(1);
  });

  it('clicking Save calls api.put with the edited body and hides the textarea', async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('button', { name: /edit/i }));
    const editTextarea = screen.getAllByRole('textbox')[0] as HTMLTextAreaElement;
    await user.clear(editTextarea);
    await user.type(editTextarea, 'edited text');
    await user.click(screen.getByRole('button', { name: /save/i }));
    await waitFor(() => {
      expect(mockedApiPut).toHaveBeenCalledWith(
        '/v1/student/discussions/threads/thread-1/replies/reply-2/',
        { body: 'edited text' },
      );
    });
    // Edit textarea closes after Save; only reply input textbox remains
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: /save/i })).not.toBeInTheDocument();
    });
  });

  // ── 23. Delete flow ──────────────────────────────────────────────────────────

  it('clicking Delete opens the ConfirmDialog', async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('button', { name: /delete/i }));
    expect(screen.getByTestId('confirm-dialog')).toBeInTheDocument();
  });

  it('confirming Delete calls api.delete with the correct URL', async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('button', { name: /delete/i }));
    // Scope to the ConfirmDialog to avoid matching the card's own Delete button
    const dialog = screen.getByTestId('confirm-dialog');
    await user.click(within(dialog).getByRole('button', { name: /delete/i }));
    await waitFor(() => {
      expect(mockedApiDelete).toHaveBeenCalledWith(
        '/v1/student/discussions/threads/thread-1/replies/reply-2/',
      );
    });
  });

  it('clicking Cancel in ConfirmDialog does not call api.delete', async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('button', { name: /delete/i }));
    await user.click(screen.getByRole('button', { name: /cancel/i }));
    expect(mockedApiDelete).not.toHaveBeenCalled();
    expect(screen.queryByTestId('confirm-dialog')).not.toBeInTheDocument();
  });

  // ── 24. Reply input — open thread ────────────────────────────────────────────

  it('renders the reply textarea and submit button for an open thread', async () => {
    const { container } = renderPage();
    await screen.findByRole('heading', { level: 1 });
    expect(screen.getByPlaceholderText('Write a reply...')).toBeInTheDocument();
    // The form submit button has type="submit" — verify it is present
    const submitBtns = container.querySelectorAll('button[type="submit"]');
    expect(submitBtns.length).toBeGreaterThanOrEqual(1);
  });

  // ── 25. Reply input — closed thread ─────────────────────────────────────────

  it('does not render the reply textarea for a closed thread', async () => {
    mockedApiGet.mockResolvedValue({ data: { ...MOCK_THREAD, status: 'closed' } });
    renderPage();
    await screen.findByRole('heading', { level: 1 });
    expect(screen.queryByPlaceholderText('Write a reply...')).not.toBeInTheDocument();
  });

  // ── 26. Submit reply ─────────────────────────────────────────────────────────

  it('calls api.post with the reply body when the reply form is submitted', async () => {
    const user = userEvent.setup();
    renderPage();
    const textarea = await screen.findByPlaceholderText('Write a reply...');
    await user.type(textarea, 'A new reply from the test');
    fireEvent.submit(textarea.closest('form')!);
    await waitFor(() => {
      expect(mockedApiPost).toHaveBeenCalledWith(
        '/v1/student/discussions/threads/thread-1/replies/',
        expect.objectContaining({ body: 'A new reply from the test' }),
      );
    });
  });

  it('clears the textarea after a successful reply submission', async () => {
    const user = userEvent.setup();
    renderPage();
    const textarea = await screen.findByPlaceholderText('Write a reply...');
    await user.type(textarea, 'Some text');
    fireEvent.submit(textarea.closest('form')!);
    await waitFor(() => {
      expect(mockedApiPost).toHaveBeenCalled();
    });
    // On success the query is invalidated and replyBody is cleared
    await waitFor(() => {
      expect((screen.getByPlaceholderText('Write a reply...') as HTMLTextAreaElement).value).toBe('');
    });
  });

  // ── 27. Replying to context banner ───────────────────────────────────────────

  it('shows "Replying to {name}" banner when a Reply button on a reply is clicked', async () => {
    const user = userEvent.setup();
    const { container } = renderPage();
    await screen.findByText('Mr. Smith');
    await user.click(getReplyActionBtns(container)[0]);
    expect(await screen.findByText(/Replying to/i)).toBeInTheDocument();
    // "Mr. Smith" now appears both in the reply card AND in the banner — both are correct
    expect(screen.getAllByText('Mr. Smith').length).toBeGreaterThanOrEqual(1);
  });

  it('clears the "Replying to" banner when its X button is clicked', async () => {
    const user = userEvent.setup();
    const { container } = renderPage();
    await screen.findByText('Mr. Smith');
    await user.click(getReplyActionBtns(container)[0]);
    await screen.findByText(/Replying to/i);
    // The close button is a sibling of the "Replying to" span inside the banner row
    const bannerText = screen.getByText(/Replying to/i);
    const bannerRow = bannerText.closest('div')!;
    const closeBtn = bannerRow.querySelector('button')!;
    await user.click(closeBtn);
    await waitFor(() => {
      expect(screen.queryByText(/Replying to/i)).not.toBeInTheDocument();
    });
  });

  it('includes parent_id in the payload when replying to a specific reply', async () => {
    const user = userEvent.setup();
    const { container } = renderPage();
    await screen.findByText('Mr. Smith');
    // Click the per-card Reply action button on reply-1 (Mr. Smith)
    await user.click(getReplyActionBtns(container)[0]);
    const textarea = screen.getByPlaceholderText('Write a reply...');
    await user.type(textarea, 'Nested reply here');
    fireEvent.submit(textarea.closest('form')!);
    await waitFor(() => {
      expect(mockedApiPost).toHaveBeenCalledWith(
        '/v1/student/discussions/threads/thread-1/replies/',
        expect.objectContaining({ body: 'Nested reply here', parent_id: 'reply-1' }),
      );
    });
  });
});
