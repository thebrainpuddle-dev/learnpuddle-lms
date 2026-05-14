// src/pages/teacher/TeacherStudyNotesPage.test.tsx
//
// FE-056: Tests for the Teacher AI Study Notes page.
// Covers: page header, loading spinner, search input, course list in accordion,
//         course expansion (lazy detail load via api.get), content items list,
//         isSummarizable filter (VIDEO+transcript / DOCUMENT / TEXT only),
//         "Summary available" checkmark from summaryExistsMap, content selection
//         → StudySummaryPanel shown, "Select a content item" placeholder,
//         search filtering, and empty states.
//
// Mocking strategy:
//   - api.get mocked via vi.mock('../../config/api') — handles multiple URL paths
//   - StudySummaryPanel stubbed as a minimal div to isolate page logic
//   - usePageTitle stubbed

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { TeacherStudyNotesPage } from './TeacherStudyNotesPage';

// ── Module mocks ──────────────────────────────────────────────────────────────

vi.mock('../../config/api', () => ({
  default: { get: vi.fn() },
}));

vi.mock('../../components/student/StudySummaryPanel', () => ({
  StudySummaryPanel: ({ contentTitle }: { contentTitle: string }) => (
    <div data-testid="study-summary-panel">{contentTitle}</div>
  ),
}));

vi.mock('../../hooks/usePageTitle', () => ({ usePageTitle: vi.fn() }));

// ── Typed mock helper ─────────────────────────────────────────────────────────

import api from '../../config/api';
const mockApiGet = api.get as ReturnType<typeof vi.fn>;

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
        // staleTime: Infinity prevents TanStack Query from scheduling an
        // immediate refetch after queries resolve (staleTime: 0 default would
        // trigger background refetches that interfere with act() settling).
        staleTime: Infinity,
        // refetchOnWindowFocus: false prevents happy-dom focus events from
        // triggering extra refetch cycles during test execution.
        refetchOnWindowFocus: false,
      },
    },
  });
}

function renderPage() {
  return render(
    <QueryClientProvider client={makeClient()}>
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <TeacherStudyNotesPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// ── Fixtures ──────────────────────────────────────────────────────────────────

const mockCourses = [
  { id: 'course-1', title: 'Algebra Fundamentals', is_published: true },
  { id: 'course-2', title: 'IB PYP Framework', is_published: true },
];

const mockCourseDetail = {
  id: 'course-1',
  title: 'Algebra Fundamentals',
  modules: [
    {
      id: 'mod-1',
      title: 'Module 1: Basics',
      order: 1,
      contents: [
        // Summarizable: VIDEO with transcript
        { id: 'ct-1', title: 'Introduction Video', content_type: 'VIDEO', has_transcript: true, order: 1 },
        // Summarizable: DOCUMENT
        { id: 'ct-2', title: 'Reading Material', content_type: 'DOCUMENT', has_transcript: false, order: 2 },
        // NOT summarizable: AI_CLASSROOM
        { id: 'ct-3', title: 'AI Classroom Session', content_type: 'AI_CLASSROOM', has_transcript: false, order: 3 },
        // NOT summarizable: VIDEO without transcript
        { id: 'ct-4', title: 'Raw Video No Transcript', content_type: 'VIDEO', has_transcript: false, order: 4 },
      ],
    },
  ],
};

// Only ct-1 has READY summary → gets the check badge
const mockSummaries = [
  { content_id: 'ct-1', status: 'READY' },
  { content_id: 'ct-2', status: 'PENDING' },
];

/** Standard api.get implementation that routes by URL */
function setupDefaultMocks() {
  mockApiGet.mockImplementation((url: string) => {
    if (url === '/v1/teacher/courses/') return Promise.resolve({ data: mockCourses });
    if (url === '/v1/teacher/study-summaries/') return Promise.resolve({ data: mockSummaries });
    if (url.includes('/v1/teacher/courses/')) return Promise.resolve({ data: mockCourseDetail });
    return Promise.reject(new Error(`Unexpected URL: ${url}`));
  });
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('TeacherStudyNotesPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  // ── Loading ─────────────────────────────────────────────────────────────────

  it('shows loading spinner while courses query is pending', () => {
    mockApiGet.mockReturnValue(new Promise(() => {})); // never resolves
    renderPage();
    expect(screen.getByRole('status', { name: /loading/i })).toBeInTheDocument();
  });

  // ── Page header ─────────────────────────────────────────────────────────────

  it('renders "AI Study Notes" heading', async () => {
    setupDefaultMocks();
    renderPage();
    expect(
      await screen.findByRole('heading', { level: 1, name: /ai study notes/i }),
    ).toBeInTheDocument();
  });

  it('renders subtitle text about AI-powered summaries', async () => {
    setupDefaultMocks();
    renderPage();
    expect(
      await screen.findByText(/generate ai-powered summaries/i),
    ).toBeInTheDocument();
  });

  // ── Search input ────────────────────────────────────────────────────────────

  it('renders search input with placeholder', async () => {
    setupDefaultMocks();
    renderPage();
    expect(
      await screen.findByPlaceholderText(/search courses and content/i),
    ).toBeInTheDocument();
  });

  // ── Course list ─────────────────────────────────────────────────────────────

  it('renders course titles in the accordion list', async () => {
    setupDefaultMocks();
    renderPage();
    expect(await screen.findByRole('button', { name: /algebra fundamentals/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /ib pyp framework/i })).toBeInTheDocument();
  });

  it('shows "No courses available" empty state when no courses', async () => {
    mockApiGet.mockImplementation((url: string) => {
      if (url === '/v1/teacher/courses/') return Promise.resolve({ data: [] });
      if (url === '/v1/teacher/study-summaries/') return Promise.resolve({ data: [] });
      return Promise.reject(new Error('Unexpected URL'));
    });
    renderPage();
    expect(await screen.findByText('No courses available')).toBeInTheDocument();
  });

  // ── Course expansion ────────────────────────────────────────────────────────

  it('expands course and shows content items after click', async () => {
    const user = userEvent.setup();
    setupDefaultMocks();
    renderPage();
    const courseBtn = await screen.findByRole('button', { name: /algebra fundamentals/i });
    await user.click(courseBtn);
    // Should show summarizable content items
    expect(await screen.findByText('Introduction Video')).toBeInTheDocument();
    expect(screen.getByText('Reading Material')).toBeInTheDocument();
  });

  it('filters out non-summarizable content (AI_CLASSROOM, VIDEO without transcript)', async () => {
    const user = userEvent.setup();
    setupDefaultMocks();
    renderPage();
    const courseBtn = await screen.findByRole('button', { name: /algebra fundamentals/i });
    await user.click(courseBtn);
    await screen.findByText('Introduction Video'); // wait for expansion
    // AI_CLASSROOM and VIDEO-without-transcript should NOT appear
    expect(screen.queryByText('AI Classroom Session')).not.toBeInTheDocument();
    expect(screen.queryByText('Raw Video No Transcript')).not.toBeInTheDocument();
  });

  it('calls api.get for course detail on first expansion', async () => {
    const user = userEvent.setup();
    setupDefaultMocks();
    renderPage();
    await screen.findByRole('button', { name: /algebra fundamentals/i });
    await user.click(screen.getByRole('button', { name: /algebra fundamentals/i }));
    await screen.findByText('Introduction Video');
    expect(mockApiGet).toHaveBeenCalledWith('/v1/teacher/courses/course-1/');
  });

  it('shows "No summarizable content in this course" when course has no summarizable items', async () => {
    const user = userEvent.setup();
    const emptyCourseDetail = {
      id: 'course-2',
      title: 'IB PYP Framework',
      modules: [
        {
          id: 'mod-x',
          title: 'Module X',
          order: 1,
          contents: [
            { id: 'ct-x', title: 'AI Classroom', content_type: 'AI_CLASSROOM', order: 1 },
          ],
        },
      ],
    };
    mockApiGet.mockImplementation((url: string) => {
      if (url === '/v1/teacher/courses/') return Promise.resolve({ data: mockCourses });
      if (url === '/v1/teacher/study-summaries/') return Promise.resolve({ data: [] });
      if (url.includes('course-2')) return Promise.resolve({ data: emptyCourseDetail });
      return Promise.reject(new Error('Unexpected URL'));
    });
    renderPage();
    const ibBtn = await screen.findByRole('button', { name: /ib pyp framework/i });
    await user.click(ibBtn);
    expect(
      await screen.findByText('No summarizable content in this course'),
    ).toBeInTheDocument();
  });

  // ── Summary available badge ─────────────────────────────────────────────────

  it('shows "Summary available" badge for content with READY summary', async () => {
    const user = userEvent.setup();
    setupDefaultMocks();
    renderPage();
    await user.click(await screen.findByRole('button', { name: /algebra fundamentals/i }));
    await screen.findByText('Introduction Video');
    // ct-1 has READY status → should show the "Summary available" checkmark badge
    expect(screen.getByTitle('Summary available')).toBeInTheDocument();
  });

  it('does not show "Summary available" badge for content with PENDING summary', async () => {
    const user = userEvent.setup();
    setupDefaultMocks();
    renderPage();
    await user.click(await screen.findByRole('button', { name: /algebra fundamentals/i }));
    await screen.findByText('Reading Material'); // ct-2, status PENDING
    // Only one badge (for ct-1) should exist
    expect(screen.getAllByTitle('Summary available')).toHaveLength(1);
  });

  // ── Content selection → StudySummaryPanel ───────────────────────────────────

  it('shows "Select a content item" placeholder before any selection', async () => {
    setupDefaultMocks();
    renderPage();
    expect(await screen.findByText('Select a content item')).toBeInTheDocument();
  });

  it('renders StudySummaryPanel stub when a content item is selected', async () => {
    const user = userEvent.setup();
    setupDefaultMocks();
    renderPage();
    await user.click(await screen.findByRole('button', { name: /algebra fundamentals/i }));
    const videoBtn = await screen.findByRole('button', { name: /introduction video/i });
    await user.click(videoBtn);
    expect(screen.getByTestId('study-summary-panel')).toBeInTheDocument();
    // The stub renders contentTitle as its text content
    expect(screen.getByTestId('study-summary-panel')).toHaveTextContent('Introduction Video');
  });

  it('hides "Select a content item" placeholder after selection', async () => {
    const user = userEvent.setup();
    setupDefaultMocks();
    renderPage();
    await user.click(await screen.findByRole('button', { name: /algebra fundamentals/i }));
    const videoBtn = await screen.findByRole('button', { name: /introduction video/i });
    await user.click(videoBtn);
    // On desktop the browser panel stays visible, placeholder is replaced by panel
    expect(screen.queryByText('Select a content item')).not.toBeInTheDocument();
  });

  // ── Search filtering ────────────────────────────────────────────────────────

  it('filters courses by search term', async () => {
    const user = userEvent.setup();
    setupDefaultMocks();
    renderPage();
    await screen.findByRole('button', { name: /algebra fundamentals/i });
    const searchInput = screen.getByPlaceholderText(/search courses and content/i);
    await user.type(searchInput, 'IB');
    // "Algebra Fundamentals" should disappear, "IB PYP Framework" stays
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: /algebra fundamentals/i })).not.toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: /ib pyp framework/i })).toBeInTheDocument();
  });

  it('shows "No matching content found" when search has no results', async () => {
    const user = userEvent.setup();
    setupDefaultMocks();
    renderPage();
    await screen.findByRole('button', { name: /algebra fundamentals/i });
    const searchInput = screen.getByPlaceholderText(/search courses and content/i);
    await user.type(searchInput, 'zzznomatch');
    expect(await screen.findByText('No matching content found')).toBeInTheDocument();
  });
});
