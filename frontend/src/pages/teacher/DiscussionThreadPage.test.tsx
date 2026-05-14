// src/pages/teacher/DiscussionThreadPage.test.tsx
//
// FE-062: Tests for the Teacher Discussion Thread detail page.
// Covers: loading state (skeleton), "Thread not found" state, thread header
//         (title, status badge, body, author, view/reply counts, grade-section
//         label, course label), replies list (author, body), "No replies yet"
//         empty state, reply form visible for open threads, reply form hidden
//         for closed threads, Submit button disabled while body is empty,
//         reply form submission calls API, subscribe/unsubscribe button toggle,
//         moderation controls (Close/Reopen, Pin/Unpin) shown when can_moderate,
//         Hide reply button visible for moderators, ConfirmDialog on hide,
//         "Replying to NAME" context appears after clicking Reply on a reply.
//
// Mocking strategy:
//   - api.get / api.post / api.patch / api.delete via vi.mock('../../config/api')
//   - useAuthStore mocked with a fixed user
//   - ConfirmDialog stubbed for simplicity
//   - useNavigate mocked via importOriginal spread
//   - usePageTitle stubbed
//   - Route params provided via MemoryRouter initialEntries + Routes wrapper

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { DiscussionThreadPage } from './DiscussionThreadPage';

// ── Module mocks ──────────────────────────────────────────────────────────────

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock('../../config/api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

vi.mock('../../stores/authStore', () => ({
  useAuthStore: vi.fn((selector: (s: { user: { id: string; first_name: string } }) => unknown) =>
    selector({ user: { id: 'teacher-1', first_name: 'Teacher' } }),
  ),
}));

// Stub ConfirmDialog for easy trigger/cancel
vi.mock('../../components/common/ConfirmDialog', () => ({
  ConfirmDialog: ({
    isOpen,
    onConfirm,
    onClose,
    title,
  }: {
    isOpen: boolean;
    onConfirm: () => void;
    onClose: () => void;
    title: string;
  }) =>
    isOpen ? (
      <div data-testid="confirm-dialog">
        <p>{title}</p>
        <button onClick={onConfirm}>Confirm Hide</button>
        <button onClick={onClose}>Cancel</button>
      </div>
    ) : null,
}));

vi.mock('../../hooks/usePageTitle', () => ({ usePageTitle: vi.fn() }));

// ── Typed mock helpers ────────────────────────────────────────────────────────

import api from '../../config/api';
const mockApiGet = api.get as ReturnType<typeof vi.fn>;
const mockApiPost = api.post as ReturnType<typeof vi.fn>;
const mockApiPatch = api.patch as ReturnType<typeof vi.fn>;
const mockApiDelete = api.delete as ReturnType<typeof vi.fn>;

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
}

function renderPage(threadId = 'thread-1') {
  return render(
    <QueryClientProvider client={makeClient()}>
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }} initialEntries={[`/teacher/discussions/${threadId}`]}>
        <Routes>
          <Route
            path="/teacher/discussions/:threadId"
            element={<DiscussionThreadPage />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// ── Fixtures ──────────────────────────────────────────────────────────────────

function makeThread(overrides: Record<string, unknown> = {}) {
  return {
    id: 'thread-1',
    title: 'Help with quadratic equations',
    body: 'I am stuck on problem 3. Can any teacher help?',
    author: { id: 'std-1', name: 'Alice Johnson', role: 'STUDENT', avatar: null },
    section_id: 'sec-1',
    section_name: 'Section A',
    grade_name: 'Grade 10',
    course_id: 'crs-1',
    course_title: 'Algebra Fundamentals',
    content_id: null,
    content_title: null,
    status: 'open',
    is_pinned: false,
    is_announcement: false,
    is_subscribed: false,
    can_moderate: false,
    reply_count: 2,
    view_count: 15,
    created_at: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
    last_reply_at: null,
    replies: [
      {
        id: 'reply-1',
        body: 'Great question! The key is to factor first.',
        author: { id: 'teacher-1', name: 'Mr. Roberts', role: 'TEACHER', avatar: null },
        like_count: 3,
        is_liked: false,
        is_edited: false,
        depth: 0,
        parent_id: null,
        created_at: new Date(Date.now() - 60 * 60 * 1000).toISOString(),
        children: [],
      },
      {
        id: 'reply-2',
        body: 'Thank you for the help!',
        author: { id: 'std-1', name: 'Alice Johnson', role: 'STUDENT', avatar: null },
        like_count: 0,
        is_liked: false,
        is_edited: false,
        depth: 0,
        parent_id: null,
        created_at: new Date(Date.now() - 30 * 60 * 1000).toISOString(),
        children: [],
      },
    ],
    ...overrides,
  };
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('DiscussionThreadPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockApiGet.mockResolvedValue({ data: makeThread() });
    mockApiPost.mockResolvedValue({ data: {} });
    mockApiPatch.mockResolvedValue({ data: {} });
    mockApiDelete.mockResolvedValue({ data: {} });
  });

  // ── Loading state ────────────────────────────────────────────────────────────

  it('shows loading skeleton while thread is loading', () => {
    mockApiGet.mockReturnValue(new Promise(() => {}));
    renderPage();
    const skeletons = document.querySelectorAll('.tp-skeleton');
    expect(skeletons.length).toBeGreaterThanOrEqual(1);
  });

  // ── Thread not found ─────────────────────────────────────────────────────────

  it('shows "Thread not found" when query returns undefined', async () => {
    // Simulate error (query rejects → data stays undefined)
    mockApiGet.mockRejectedValue(new Error('Not found'));
    renderPage();
    expect(await screen.findByText('Thread not found')).toBeInTheDocument();
    expect(screen.getByText(/this discussion thread may have been deleted/i)).toBeInTheDocument();
  });

  // ── Thread header ────────────────────────────────────────────────────────────

  it('renders the thread title', async () => {
    renderPage();
    expect(
      await screen.findByRole('heading', { level: 1, name: /help with quadratic equations/i }),
    ).toBeInTheDocument();
  });

  it('renders the thread body text', async () => {
    renderPage();
    expect(
      await screen.findByText(/i am stuck on problem 3/i),
    ).toBeInTheDocument();
  });

  it('renders the author name', async () => {
    renderPage();
    await screen.findByRole('heading', { level: 1 });
    // Alice Johnson appears in thread header + as reply author (reply-2)
    const matches = screen.getAllByText('Alice Johnson');
    expect(matches.length).toBeGreaterThanOrEqual(1);
  });

  it('renders the status badge (open)', async () => {
    renderPage();
    await screen.findByRole('heading', { level: 1 });
    expect(screen.getByText('open')).toBeInTheDocument();
  });

  it('renders the grade-section label', async () => {
    renderPage();
    await screen.findByRole('heading', { level: 1 });
    expect(screen.getByText(/grade 10 - section a/i)).toBeInTheDocument();
  });

  it('renders the course title label', async () => {
    renderPage();
    await screen.findByRole('heading', { level: 1 });
    expect(screen.getByText('Algebra Fundamentals')).toBeInTheDocument();
  });

  it('renders view count and reply count in meta row', async () => {
    renderPage();
    await screen.findByRole('heading', { level: 1 });
    expect(screen.getByText(/15 views/i)).toBeInTheDocument();
    expect(screen.getByText(/2 replies/i)).toBeInTheDocument();
  });

  // ── Back button ──────────────────────────────────────────────────────────────

  it('navigates to /teacher/discussions when back button is clicked', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole('heading', { level: 1 });
    await user.click(screen.getByRole('button', { name: /back to discussions/i }));
    expect(mockNavigate).toHaveBeenCalledWith('/teacher/discussions');
  });

  // ── Subscribe button ─────────────────────────────────────────────────────────

  it('shows "Subscribe" button when not subscribed', async () => {
    renderPage();
    await screen.findByRole('heading', { level: 1 });
    expect(screen.getByRole('button', { name: /subscribe/i })).toBeInTheDocument();
  });

  it('shows "Subscribed" button when already subscribed', async () => {
    mockApiGet.mockResolvedValue({ data: makeThread({ is_subscribed: true }) });
    renderPage();
    await screen.findByRole('heading', { level: 1 });
    expect(screen.getByRole('button', { name: /subscribed/i })).toBeInTheDocument();
  });

  it('calls POST subscribe API when subscribe button is clicked', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole('heading', { level: 1 });
    await user.click(screen.getByRole('button', { name: /^subscribe$/i }));
    await waitFor(() => {
      expect(mockApiPost).toHaveBeenCalledWith(
        '/v1/teacher/discussions/threads/thread-1/subscribe/',
      );
    });
  });

  // ── Replies list ─────────────────────────────────────────────────────────────

  it('renders reply author names', async () => {
    renderPage();
    await screen.findByRole('heading', { level: 1 });
    expect(screen.getByText('Mr. Roberts')).toBeInTheDocument();
  });

  it('renders reply body text', async () => {
    renderPage();
    expect(
      await screen.findByText(/the key is to factor first/i),
    ).toBeInTheDocument();
  });

  it('renders "Teacher" badge for teacher replies', async () => {
    renderPage();
    await screen.findByText('Mr. Roberts');
    expect(screen.getByText('Teacher')).toBeInTheDocument();
  });

  it('renders "No replies yet." when thread has no replies', async () => {
    mockApiGet.mockResolvedValue({ data: makeThread({ replies: [], reply_count: 0 }) });
    renderPage();
    expect(await screen.findByText('No replies yet.')).toBeInTheDocument();
  });

  // ── Reply form ───────────────────────────────────────────────────────────────

  it('shows reply textarea when thread is open', async () => {
    renderPage();
    await screen.findByRole('heading', { level: 1 });
    expect(
      screen.getByPlaceholderText(/reply to this discussion/i),
    ).toBeInTheDocument();
  });

  it('does NOT show reply textarea when thread is closed', async () => {
    mockApiGet.mockResolvedValue({ data: makeThread({ status: 'closed' }) });
    renderPage();
    await screen.findByRole('heading', { level: 1 });
    expect(
      screen.queryByPlaceholderText(/reply to this discussion/i),
    ).not.toBeInTheDocument();
  });

  it('Reply submit button is disabled when textarea is empty', async () => {
    renderPage();
    await screen.findByRole('heading', { level: 1 });
    // The submit button is inside the reply form — scope to the form element
    // to avoid ambiguity with reply-card "Reply" buttons
    const form = document.querySelector('form') as HTMLElement;
    const submitBtn = form.querySelector('button[type="submit"]') as HTMLButtonElement;
    expect(submitBtn).toBeDisabled();
  });

  it('Reply submit button becomes enabled when text is entered', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole('heading', { level: 1 });
    const textarea = screen.getByPlaceholderText(/reply to this discussion/i);
    await user.type(textarea, 'Here is my answer');
    const form = document.querySelector('form') as HTMLElement;
    const submitBtn = form.querySelector('button[type="submit"]') as HTMLButtonElement;
    expect(submitBtn).not.toBeDisabled();
  });

  it('calls POST replies API when reply form is submitted', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole('heading', { level: 1 });
    const textarea = screen.getByPlaceholderText(/reply to this discussion/i);
    await user.type(textarea, 'Here is my answer');
    const form = document.querySelector('form') as HTMLElement;
    const submitBtn = form.querySelector('button[type="submit"]') as HTMLButtonElement;
    await user.click(submitBtn);
    await waitFor(() => {
      expect(mockApiPost).toHaveBeenCalledWith(
        '/v1/teacher/discussions/threads/thread-1/replies/',
        { body: 'Here is my answer' },
      );
    });
  });

  // ── Moderation controls ──────────────────────────────────────────────────────

  it('shows "Close Thread" button when can_moderate and thread is open', async () => {
    mockApiGet.mockResolvedValue({ data: makeThread({ can_moderate: true }) });
    renderPage();
    await screen.findByRole('heading', { level: 1 });
    expect(screen.getByRole('button', { name: /close thread/i })).toBeInTheDocument();
  });

  it('shows "Reopen Thread" button when can_moderate and thread is closed', async () => {
    mockApiGet.mockResolvedValue({ data: makeThread({ can_moderate: true, status: 'closed', replies: [] }) });
    renderPage();
    await screen.findByRole('heading', { level: 1 });
    expect(screen.getByRole('button', { name: /reopen thread/i })).toBeInTheDocument();
  });

  it('shows "Pin" button when can_moderate and thread is not pinned', async () => {
    mockApiGet.mockResolvedValue({ data: makeThread({ can_moderate: true }) });
    renderPage();
    await screen.findByRole('heading', { level: 1 });
    expect(screen.getByRole('button', { name: /^pin$/i })).toBeInTheDocument();
  });

  it('calls PATCH moderate API with {status: "closed"} when Close Thread is clicked', async () => {
    const user = userEvent.setup();
    mockApiGet.mockResolvedValue({ data: makeThread({ can_moderate: true }) });
    renderPage();
    await screen.findByRole('heading', { level: 1 });
    await user.click(screen.getByRole('button', { name: /close thread/i }));
    await waitFor(() => {
      expect(mockApiPatch).toHaveBeenCalledWith(
        '/v1/teacher/discussions/threads/thread-1/moderate/',
        { status: 'closed' },
      );
    });
  });

  it('does NOT show moderation controls when can_moderate is false', async () => {
    renderPage(); // default can_moderate: false
    await screen.findByRole('heading', { level: 1 });
    expect(screen.queryByRole('button', { name: /close thread/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^pin$/i })).not.toBeInTheDocument();
  });

  // ── Hide reply ───────────────────────────────────────────────────────────────

  it('shows "Hide" button on replies when can_moderate', async () => {
    mockApiGet.mockResolvedValue({ data: makeThread({ can_moderate: true }) });
    renderPage();
    await screen.findByText(/the key is to factor first/i);
    const hideButtons = screen.getAllByRole('button', { name: /^hide$/i });
    expect(hideButtons.length).toBeGreaterThanOrEqual(1);
  });

  it('opens ConfirmDialog when Hide is clicked', async () => {
    const user = userEvent.setup();
    mockApiGet.mockResolvedValue({ data: makeThread({ can_moderate: true }) });
    renderPage();
    await screen.findByText(/the key is to factor first/i);
    const hideButtons = screen.getAllByRole('button', { name: /^hide$/i });
    await user.click(hideButtons[0]);
    expect(screen.getByTestId('confirm-dialog')).toBeInTheDocument();
    expect(screen.getByText('Hide Reply')).toBeInTheDocument();
  });

  it('calls POST moderate API on hide confirm', async () => {
    const user = userEvent.setup();
    mockApiGet.mockResolvedValue({ data: makeThread({ can_moderate: true }) });
    renderPage();
    await screen.findByText(/the key is to factor first/i);
    const hideButtons = screen.getAllByRole('button', { name: /^hide$/i });
    await user.click(hideButtons[0]);
    await user.click(screen.getByRole('button', { name: /confirm hide/i }));
    await waitFor(() => {
      expect(mockApiPost).toHaveBeenCalledWith(
        expect.stringContaining('/moderate/'),
        expect.objectContaining({ action: 'hide' }),
      );
    });
  });

  // ── Replying-to context ──────────────────────────────────────────────────────

  it('shows "Replying to NAME" context after clicking Reply on a reply', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText(/the key is to factor first/i);
    const replyButtons = screen.getAllByRole('button', { name: /^reply$/i });
    await user.click(replyButtons[0]);
    // "Replying to" container appears — use the "Replying to" text span
    expect(screen.getByText(/replying to/i)).toBeInTheDocument();
    // Mr. Roberts now appears twice: reply card author + "Replying to" context
    const mrRobertsEls = screen.getAllByText('Mr. Roberts');
    expect(mrRobertsEls.length).toBeGreaterThanOrEqual(2);
  });
});
