// src/pages/teacher/DiscussionPage.test.tsx
//
// FE-059: Tests for the Teacher Student Discussions page.
// Covers: page header ("Student Discussions"), loading state (skeleton cards),
//         empty state ("No discussions yet"), thread list rendering (title,
//         body preview, author name, status badge, reply/view counts),
//         pinned thread indicator (title="Pinned"), section filter dropdown,
//         status filter buttons (all/open/closed/archived), navigation on
//         thread click, "Load More" button visibility and interaction.
//
// Mocking strategy:
//   - api.get via vi.mock('../../config/api') — routes by URL + params
//   - useNavigate mocked via importOriginal spread
//   - usePageTitle stubbed

import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { DiscussionPage } from './DiscussionPage';

// ── Module mocks ──────────────────────────────────────────────────────────────

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock('../../config/api', () => ({
  default: { get: vi.fn() },
}));

vi.mock('../../hooks/usePageTitle', () => ({ usePageTitle: vi.fn() }));

// ── Typed mock helper ─────────────────────────────────────────────────────────

import api from '../../config/api';
const mockApiGet = api.get as ReturnType<typeof vi.fn>;

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
}

function renderPage() {
  return render(
    <QueryClientProvider client={makeClient()}>
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <DiscussionPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// ── Fixtures ──────────────────────────────────────────────────────────────────

const mockSections = [
  { id: 'sec-1', name: 'Section A', grade_name: 'Grade 10', display_name: 'Grade 10 - Section A' },
  { id: 'sec-2', name: 'Section B', grade_name: 'Grade 11', display_name: 'Grade 11 - Section B' },
];

const mockThreads = [
  {
    id: 'thread-1',
    title: 'Help with quadratic equations',
    body: 'I am stuck on problem 3 from the homework sheet',
    author: { id: 'std-1', name: 'Alice Johnson', role: 'STUDENT', avatar: null },
    section_id: 'sec-1',
    section_name: 'Section A',
    grade_name: 'Grade 10',
    course_id: 'course-1',
    course_title: 'Algebra Fundamentals',
    content_id: null,
    content_title: null,
    status: 'open' as const,
    is_pinned: false,
    is_announcement: false,
    reply_count: 5,
    view_count: 23,
    created_at: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(), // 2h ago
    last_reply_at: null,
  },
  {
    id: 'thread-2',
    title: 'Question about IB criteria',
    body: 'Can someone clarify the criterion A rubric?',
    author: { id: 'std-2', name: 'Bob Smith', role: 'STUDENT', avatar: null },
    section_id: 'sec-1',
    section_name: 'Section A',
    grade_name: 'Grade 10',
    course_id: 'course-2',
    course_title: 'IB PYP Framework',
    content_id: null,
    content_title: null,
    status: 'closed' as const,
    is_pinned: true,
    is_announcement: false,
    reply_count: 12,
    view_count: 47,
    created_at: new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString(), // 1d ago
    last_reply_at: null,
  },
];

function makeThreadsResponse(
  threads = mockThreads,
  count = mockThreads.length,
  next: string | null = null,
) {
  return { results: threads, count, next };
}

/** Standard api.get mock that routes by URL */
function setupDefaultMocks(
  options: { threads?: typeof mockThreads; next?: string | null } = {},
) {
  const { threads = mockThreads, next = null } = options;
  mockApiGet.mockImplementation((url: string) => {
    if (url === '/v1/teacher/discussions/sections/')
      return Promise.resolve({ data: mockSections });
    if (url === '/v1/teacher/discussions/threads/')
      return Promise.resolve({ data: makeThreadsResponse(threads, threads.length, next) });
    return Promise.reject(new Error(`Unexpected URL: ${url}`));
  });
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('DiscussionPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  // ── Page header ─────────────────────────────────────────────────────────────

  it('renders "Student Discussions" heading', async () => {
    setupDefaultMocks();
    renderPage();
    expect(
      await screen.findByRole('heading', { level: 1, name: /student discussions/i }),
    ).toBeInTheDocument();
  });

  it('renders subtitle text', async () => {
    setupDefaultMocks();
    renderPage();
    expect(
      await screen.findByText(/monitor and participate in student discussions/i),
    ).toBeInTheDocument();
  });

  // ── Loading state ────────────────────────────────────────────────────────────

  it('shows skeleton loading cards while threads are loading', () => {
    // sections resolves, threads never resolves
    mockApiGet.mockImplementation((url: string) => {
      if (url === '/v1/teacher/discussions/sections/')
        return Promise.resolve({ data: mockSections });
      return new Promise(() => {}); // never resolves
    });
    renderPage();
    // Skeleton divs have tp-skeleton class
    const skeletons = document.querySelectorAll('.tp-skeleton');
    expect(skeletons.length).toBeGreaterThanOrEqual(1);
  });

  // ── Thread list ──────────────────────────────────────────────────────────────

  it('renders thread titles', async () => {
    setupDefaultMocks();
    renderPage();
    expect(await screen.findByText('Help with quadratic equations')).toBeInTheDocument();
    expect(screen.getByText('Question about IB criteria')).toBeInTheDocument();
  });

  it('renders thread body preview text', async () => {
    setupDefaultMocks();
    renderPage();
    expect(
      await screen.findByText(/i am stuck on problem 3/i),
    ).toBeInTheDocument();
  });

  it('renders author name in thread card', async () => {
    setupDefaultMocks();
    renderPage();
    expect(await screen.findByText('Alice Johnson')).toBeInTheDocument();
  });

  it('renders open status badge for open thread', async () => {
    setupDefaultMocks();
    renderPage();
    await screen.findByText('Help with quadratic equations');
    // Open status shown as "open" badge
    const badges = screen.getAllByText('open');
    expect(badges.length).toBeGreaterThanOrEqual(1);
  });

  it('renders closed status badge for closed thread', async () => {
    setupDefaultMocks();
    renderPage();
    await screen.findByText('Question about IB criteria');
    const badges = screen.getAllByText('closed');
    expect(badges.length).toBeGreaterThanOrEqual(1);
  });

  it('shows reply count for threads', async () => {
    setupDefaultMocks();
    renderPage();
    await screen.findByText('Help with quadratic equations');
    // reply counts: 5 and 12
    expect(screen.getByText('5')).toBeInTheDocument();
    expect(screen.getByText('12')).toBeInTheDocument();
  });

  it('shows view count for threads', async () => {
    setupDefaultMocks();
    renderPage();
    await screen.findByText('Help with quadratic equations');
    expect(screen.getByText('23')).toBeInTheDocument();
    expect(screen.getByText('47')).toBeInTheDocument();
  });

  it('shows "Pinned" title attribute for pinned thread', async () => {
    setupDefaultMocks();
    renderPage();
    await screen.findByText('Question about IB criteria');
    // is_pinned: true → renders PinIcon with title="Pinned"
    expect(screen.getByTitle('Pinned')).toBeInTheDocument();
  });

  it('does not show pinned indicator for non-pinned thread', async () => {
    // Only thread-1 which is non-pinned
    setupDefaultMocks({ threads: [mockThreads[0]] });
    renderPage();
    await screen.findByText('Help with quadratic equations');
    expect(screen.queryByTitle('Pinned')).not.toBeInTheDocument();
  });

  it('shows thread count in filter bar', async () => {
    setupDefaultMocks();
    renderPage();
    // totalCount = 2, renders "2 threads"
    expect(await screen.findByText(/2 threads/i)).toBeInTheDocument();
  });

  // ── Empty state ─────────────────────────────────────────────────────────────

  it('shows "No discussions yet" empty state when no threads', async () => {
    mockApiGet.mockImplementation((url: string) => {
      if (url === '/v1/teacher/discussions/sections/')
        return Promise.resolve({ data: [] });
      if (url === '/v1/teacher/discussions/threads/')
        return Promise.resolve({ data: makeThreadsResponse([], 0, null) });
      return Promise.reject(new Error('Unexpected URL'));
    });
    renderPage();
    expect(await screen.findByText('No discussions yet')).toBeInTheDocument();
  });

  // ── Navigation ───────────────────────────────────────────────────────────────

  it('navigates to thread detail on thread click', async () => {
    const user = userEvent.setup();
    setupDefaultMocks();
    renderPage();
    const threadBtn = await screen.findByRole('button', {
      name: /help with quadratic equations/i,
    });
    await user.click(threadBtn);
    expect(mockNavigate).toHaveBeenCalledWith('/teacher/discussions/thread-1');
  });

  // ── Section filter ───────────────────────────────────────────────────────────

  it('renders sections from API in the section filter dropdown', async () => {
    setupDefaultMocks();
    renderPage();
    // Wait for section options to appear in the select (sections query resolves)
    await waitFor(() => {
      const select = screen.getByRole('combobox');
      expect(within(select).getByText(/grade 10 - section a/i)).toBeInTheDocument();
    });
    const select = screen.getByRole('combobox');
    expect(within(select).getByText(/grade 11 - section b/i)).toBeInTheDocument();
  });

  it('sends section_id param when section is selected', async () => {
    const user = userEvent.setup();
    setupDefaultMocks();
    renderPage();
    await screen.findByText('Help with quadratic equations');

    const select = screen.getByRole('combobox');
    await user.selectOptions(select, 'sec-1');

    await waitFor(() => {
      const threadCalls = mockApiGet.mock.calls.filter(
        (c: unknown[]) => (c[0] as string) === '/v1/teacher/discussions/threads/',
      );
      const lastCall = threadCalls[threadCalls.length - 1];
      expect((lastCall[1] as { params: Record<string, string> }).params.section_id).toBe('sec-1');
    });
  });

  // ── Status filter ────────────────────────────────────────────────────────────

  it('renders status filter buttons: all, open, closed, archived', async () => {
    setupDefaultMocks();
    renderPage();
    await screen.findByText('Help with quadratic equations');

    const filterBar = document.querySelector('.rounded-xl.bg-gray-50.border');
    expect(filterBar).not.toBeNull();
    const container = filterBar as HTMLElement;

    expect(within(container).getByRole('button', { name: /^all$/i })).toBeInTheDocument();
    expect(within(container).getByRole('button', { name: /^open$/i })).toBeInTheDocument();
    expect(within(container).getByRole('button', { name: /^closed$/i })).toBeInTheDocument();
    expect(within(container).getByRole('button', { name: /^archived$/i })).toBeInTheDocument();
  });

  it('sends status param when status filter is changed', async () => {
    const user = userEvent.setup();
    setupDefaultMocks();
    renderPage();
    await screen.findByText('Help with quadratic equations');

    // Click "open" filter
    const filterBar = document.querySelector('.rounded-xl.bg-gray-50.border') as HTMLElement;
    await user.click(within(filterBar).getByRole('button', { name: /^open$/i }));

    await waitFor(() => {
      const threadCalls = mockApiGet.mock.calls.filter(
        (c: unknown[]) => (c[0] as string) === '/v1/teacher/discussions/threads/',
      );
      const lastCall = threadCalls[threadCalls.length - 1];
      expect((lastCall[1] as { params: Record<string, string> }).params.status).toBe('open');
    });
  });

  // ── Load More ────────────────────────────────────────────────────────────────

  it('shows "Load More" button when there is a next page', async () => {
    setupDefaultMocks({ next: '/v1/teacher/discussions/threads/?page=2' });
    renderPage();
    await screen.findByText('Help with quadratic equations');
    expect(screen.getByRole('button', { name: /load more/i })).toBeInTheDocument();
  });

  it('does NOT show "Load More" button when there is no next page', async () => {
    setupDefaultMocks({ next: null });
    renderPage();
    await screen.findByText('Help with quadratic equations');
    expect(screen.queryByRole('button', { name: /load more/i })).not.toBeInTheDocument();
  });

  it('calls threads API with page=2 when "Load More" is clicked', async () => {
    const user = userEvent.setup();
    setupDefaultMocks({ next: '/v1/teacher/discussions/threads/?page=2' });
    renderPage();
    await screen.findByText('Help with quadratic equations');

    await user.click(screen.getByRole('button', { name: /load more/i }));

    await waitFor(() => {
      const threadCalls = mockApiGet.mock.calls.filter(
        (c: unknown[]) => (c[0] as string) === '/v1/teacher/discussions/threads/',
      );
      const pageCalls = threadCalls.filter(
        (c: unknown[]) => (c[1] as { params: Record<string, string> }).params?.page === '2',
      );
      expect(pageCalls.length).toBeGreaterThanOrEqual(1);
    });
  });

  // ── Course / section labels in thread card ──────────────────────────────────

  it('renders course title label when thread has course_title', async () => {
    setupDefaultMocks();
    renderPage();
    await screen.findByText('Help with quadratic equations');
    // course_title: 'Algebra Fundamentals'
    expect(screen.getByText('Algebra Fundamentals')).toBeInTheDocument();
  });

  it('renders grade-section label in thread card', async () => {
    setupDefaultMocks();
    renderPage();
    await screen.findByText('Help with quadratic equations');
    // grade_name: 'Grade 10', section_name: 'Section A' → "Grade 10 - Section A"
    const gradeLabels = screen.getAllByText(/grade 10 - section a/i);
    expect(gradeLabels.length).toBeGreaterThanOrEqual(1);
  });
});
