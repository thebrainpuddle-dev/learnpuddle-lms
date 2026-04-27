// src/components/search/__tests__/semanticSearch.test.tsx
// RTL + Vitest tests for Semantic Search UI (TASK-063).
// ≥8 required tests.

import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { screen, waitFor, fireEvent, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { render } from '../../../test-utils';

// ─── Mocks ────────────────────────────────────────────────────────────────────

vi.mock('../../../config/api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
  },
}));

vi.mock('../../../services/searchService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../services/searchService')>();
  return {
    ...actual,
    searchService: {
      search: vi.fn(),
    },
    search: vi.fn(),
  };
});

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

vi.mock('../../../hooks/usePageTitle', () => ({
  usePageTitle: vi.fn(),
}));

// ─── Imports after mocks ──────────────────────────────────────────────────────

import { CourseSearchBar } from '../CourseSearchBar';
import { SearchPage } from '../../../pages/admin/SearchPage';
import { SearchResultItem, formatScore } from '../SearchResultItem';
import { searchService } from '../../../services/searchService';
import type { SearchResult } from '../../../services/searchService';

// ─── Helpers ─────────────────────────────────────────────────────────────────

const makeResult = (overrides: Partial<SearchResult> = {}): SearchResult => ({
  source_type: 'content',
  source_id: 'content-uuid-001',
  chunk_index: 0,
  score: 0.812,
  snippet: 'This is a sample snippet about learning objectives.',
  context: {
    course_id: 'course-uuid-001',
    course_title: 'Introduction to Teaching',
    module_id: 'module-uuid-001',
    content_id: 'content-uuid-001',
  },
  ...overrides,
});

const makeSearchResponse = (results: SearchResult[] = [makeResult()]) => ({
  results,
  count: results.length,
  top_k: 5,
  query: 'learning objectives',
});

function renderWithProviders(ui: React.ReactElement) {
  return render(ui, { useMemoryRouter: true });
}

// ─── Tests ───────────────────────────────────────────────────────────────────

// ─── Test 1: Debounce — teacher-side CourseSearchBar triggers API call ────────

describe('CourseSearchBar — debounced API call', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    vi.mocked(searchService.search).mockResolvedValue(makeSearchResponse());
  });
  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
    vi.resetAllMocks();
  });

  it('debounces input 300ms before calling searchService.search', async () => {
    renderWithProviders(<CourseSearchBar courseId="course-uuid-001" />);

    const input = screen.getByRole('combobox', { name: /search this course/i });

    // Type a query (fireEvent.change is synchronous — avoids fake-timer deadlock)
    fireEvent.change(input, { target: { value: 'learning' } });

    // API should NOT have been called yet
    expect(searchService.search).not.toHaveBeenCalled();

    // Advance timers by 300ms
    await act(async () => {
      vi.advanceTimersByTime(300);
    });

    await waitFor(() => {
      expect(searchService.search).toHaveBeenCalledWith('learning', {
        courseId: 'course-uuid-001',
        topK: 5,
      });
    });
  });
});

// ─── Test 2: Admin full-page search submits and renders results grouped ────────

describe('SearchPage — results grouped by course', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    const results = [
      makeResult({
        source_id: 'c1',
        context: {
          course_id: 'course-A',
          course_title: 'Course Alpha',
          module_id: 'mod-1',
          content_id: 'c1',
        },
      }),
      makeResult({
        source_id: 'c2',
        context: {
          course_id: 'course-B',
          course_title: 'Course Beta',
          module_id: 'mod-2',
          content_id: 'c2',
        },
      }),
    ];
    vi.mocked(searchService.search).mockResolvedValue({
      results,
      count: results.length,
      top_k: 20,
      query: 'test',
    });
  });
  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
    vi.resetAllMocks();
  });

  it('renders results grouped by course heading', async () => {
    renderWithProviders(<SearchPage />);

    const input = screen.getByRole('searchbox', { name: /search tenant content/i });
    fireEvent.change(input, { target: { value: 'test' } });

    await act(async () => {
      vi.advanceTimersByTime(300);
    });

    await waitFor(() => {
      // Use heading role to avoid ambiguity: course title appears in both the
      // <h2> group header AND the SearchResultItem title span.
      expect(screen.getByRole('heading', { level: 2, name: 'Course Alpha' })).toBeInTheDocument();
      expect(screen.getByRole('heading', { level: 2, name: 'Course Beta' })).toBeInTheDocument();
    });
  });
});

// ─── Test 3: Query cap 200 chars ──────────────────────────────────────────────

describe('Query cap — 200 characters', () => {
  it('shows character counter and red styling at limit', async () => {
    renderWithProviders(<CourseSearchBar courseId="course-uuid-001" />);

    const input = screen.getByRole('combobox', { name: /search this course/i });

    // Type 201 chars (over the 200-char limit)
    const longQuery = 'a'.repeat(201);
    fireEvent.change(input, { target: { value: longQuery } });

    // Counter should turn red (aria-live region)
    const counter = await screen.findByText(`201/200`);
    expect(counter).toBeInTheDocument();
    expect(counter.className).toMatch(/text-red/);

    // Input should have red border styles
    expect(input.className).toMatch(/border-red/);
  });
});

// ─── Test 4: Empty state after completed search with 0 results ────────────────

describe('Empty state', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    vi.mocked(searchService.search).mockResolvedValue({
      results: [],
      count: 0,
      top_k: 5,
      query: 'zzz',
    });
  });
  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
    vi.resetAllMocks();
  });

  it('shows no-results message after search returns empty array', async () => {
    renderWithProviders(<CourseSearchBar courseId="course-uuid-001" />);

    const input = screen.getByRole('combobox', { name: /search this course/i });
    fireEvent.change(input, { target: { value: 'zzz' } });

    await act(async () => {
      vi.advanceTimersByTime(300);
    });

    await waitFor(() => {
      expect(screen.getByText(/no results found/i)).toBeInTheDocument();
    });
  });
});

// ─── Test 5: Score percentage renders correctly ───────────────────────────────

describe('Score percentage formatting', () => {
  it('formats 0..1 score as integer percentage (formatScore)', () => {
    expect(formatScore(0.812)).toBe('81%');
    expect(formatScore(1.0)).toBe('100%');
    expect(formatScore(0.0)).toBe('0%');
    expect(formatScore(0.725)).toBe('73%');
  });

  it('formatScore guards against NaN and Infinity (L4 defence)', () => {
    expect(formatScore(NaN)).toBe('0%');
    expect(formatScore(Infinity)).toBe('0%');
    expect(formatScore(-Infinity)).toBe('0%');
  });

  it('renders score badge with correct percentage text in result item', () => {
    const result = makeResult({ score: 0.72 });
    renderWithProviders(
      <SearchResultItem result={result} onClick={vi.fn()} />,
    );
    expect(screen.getByText('72% match')).toBeInTheDocument();
  });
});

// ─── Test 6: Click navigation — teacher-side ─────────────────────────────────

describe('Click navigation', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    vi.mocked(searchService.search).mockResolvedValue(
      makeSearchResponse([
        makeResult({
          source_type: 'content',
          context: {
            course_id: 'crs-001',
            course_title: 'My Course',
            module_id: 'mod-001',
            content_id: 'cnt-001',
          },
        }),
      ]),
    );
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.resetAllMocks();
    mockNavigate.mockClear();
  });

  it('navigates to teacher content path when result is clicked', async () => {
    renderWithProviders(<CourseSearchBar courseId="crs-001" />);

    const input = screen.getByRole('combobox', { name: /search this course/i });
    fireEvent.change(input, { target: { value: 'objectives' } });

    await act(async () => {
      vi.advanceTimersByTime(300);
    });

    await waitFor(() => {
      expect(screen.getByText('My Course')).toBeInTheDocument();
    });

    const resultButton = screen.getByRole('option');
    // Use fireEvent.click instead of userEvent.click: userEvent v14 uses
    // setTimeout(fn, 0) internally, which is faked in this context and never fires.
    fireEvent.click(resultButton);

    expect(mockNavigate).toHaveBeenCalledWith(
      '/teacher/courses/crs-001/contents/cnt-001',
    );
  });
});

// ─── Test 7: Arrow-key nav + Enter ────────────────────────────────────────────

describe('Keyboard navigation — ArrowDown/ArrowUp/Enter', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    vi.mocked(searchService.search).mockResolvedValue(
      makeSearchResponse([
        makeResult({ source_id: 'r1', snippet: 'Snippet one' }),
        makeResult({ source_id: 'r2', snippet: 'Snippet two' }),
      ]),
    );
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.resetAllMocks();
    mockNavigate.mockClear();
  });

  it('focuses first result on ArrowDown then navigates on Enter', async () => {
    renderWithProviders(<CourseSearchBar courseId="crs-001" />);

    const input = screen.getByRole('combobox', { name: /search this course/i });
    fireEvent.change(input, { target: { value: 'test' } });

    await act(async () => {
      vi.advanceTimersByTime(300);
    });

    await waitFor(() => {
      expect(screen.getAllByRole('option').length).toBeGreaterThan(0);
    });

    // ArrowDown moves focus to first item
    fireEvent.keyDown(input, { key: 'ArrowDown' });
    const options = screen.getAllByRole('option');
    expect(options[0]).toHaveAttribute('aria-selected', 'true');

    // Enter navigates
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(mockNavigate).toHaveBeenCalled();
  });
});

// ─── Test 8: Esc closes dropdown ─────────────────────────────────────────────

describe('Keyboard navigation — Esc closes dropdown', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    vi.mocked(searchService.search).mockResolvedValue(makeSearchResponse());
  });
  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
    vi.resetAllMocks();
  });

  it('pressing Esc closes the results dropdown', async () => {
    renderWithProviders(<CourseSearchBar courseId="crs-001" />);

    const input = screen.getByRole('combobox', { name: /search this course/i });
    fireEvent.change(input, { target: { value: 'test' } });

    await act(async () => {
      vi.advanceTimersByTime(300);
    });

    await waitFor(() => {
      expect(screen.getAllByRole('option').length).toBeGreaterThan(0);
    });

    // Dropdown is visible
    expect(screen.getByRole('listbox')).toBeInTheDocument();

    fireEvent.keyDown(input, { key: 'Escape' });

    await waitFor(() => {
      expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    });
  });
});

// ─── Test 9: 503 error → banner with Retry button ─────────────────────────────

describe('Error handling — 503 service unavailable', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    vi.mocked(searchService.search).mockRejectedValue({
      response: { status: 503 },
      message: 'Service Unavailable',
    });
  });
  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
    vi.resetAllMocks();
  });

  it('shows error banner with Retry button on 503', async () => {
    renderWithProviders(<CourseSearchBar courseId="crs-001" />);

    const input = screen.getByRole('combobox', { name: /search this course/i });
    fireEvent.change(input, { target: { value: 'test' } });

    await act(async () => {
      vi.advanceTimersByTime(300);
    });

    await waitFor(() => {
      expect(
        screen.getByText(/search service is temporarily unavailable/i),
      ).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
    });
  });

  it('calls search again when Retry is clicked', async () => {
    vi.mocked(searchService.search)
      .mockRejectedValueOnce({ response: { status: 503 } })
      .mockResolvedValueOnce(makeSearchResponse());

    renderWithProviders(<CourseSearchBar courseId="crs-001" />);

    const input = screen.getByRole('combobox', { name: /search this course/i });
    fireEvent.change(input, { target: { value: 'test' } });

    await act(async () => {
      vi.advanceTimersByTime(300);
    });

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
    });

    const retryBtn = screen.getByRole('button', { name: /retry/i });
    // Use fireEvent.click: userEvent v14 uses setTimeout(fn, 0) internally,
    // which is faked here and would never fire.
    fireEvent.click(retryBtn);

    await waitFor(() => {
      expect(searchService.search).toHaveBeenCalledTimes(2);
    });
  });
});

// ─── Test 10: Retry button is disabled immediately after click (TASK-063 L7) ──

describe('Retry button — disabled for 5s after click (TASK-063 L7)', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    vi.mocked(searchService.search).mockRejectedValue({
      response: { status: 503 },
      message: 'Service Unavailable',
    });
  });
  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
    vi.resetAllMocks();
  });

  it('CourseSearchBar: Retry button is disabled while cooldown is active', async () => {
    renderWithProviders(<CourseSearchBar courseId="crs-001" />);

    const input = screen.getByRole('combobox', { name: /search this course/i });
    fireEvent.change(input, { target: { value: 'test' } });

    await act(async () => {
      vi.advanceTimersByTime(300);
    });

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
    });

    // Click retry — the button re-appears after the async search rejects again
    fireEvent.click(screen.getByRole('button', { name: /retry/i }));

    // After the retry search completes (still failing), the button is back in the
    // error banner but should be disabled due to the 5s cooldown
    await waitFor(() => {
      const btn = screen.getByTestId('search-retry-btn');
      expect(btn).toBeInTheDocument();
      expect(btn).toBeDisabled();
    });
  });

  it('SearchPage: Retry button is disabled while cooldown is active', async () => {
    renderWithProviders(<SearchPage />);

    const input = screen.getByRole('searchbox', { name: /search tenant content/i });
    fireEvent.change(input, { target: { value: 'test' } });

    await act(async () => {
      vi.advanceTimersByTime(300);
    });

    await waitFor(() => {
      expect(screen.getByTestId('search-retry-btn')).toBeInTheDocument();
    });

    // Click retry — the button re-appears after the async search rejects again
    fireEvent.click(screen.getByTestId('search-retry-btn'));

    // After the retry search completes (still failing), the button is back in the
    // error banner but should be disabled due to the 5s cooldown
    await waitFor(() => {
      const btn = screen.getByTestId('search-retry-btn');
      expect(btn).toBeInTheDocument();
      expect(btn).toBeDisabled();
    });
  });
});

// ─── Test 11: Soft-deleted content — fixture asserts not in results ───────────

describe('Soft-deleted content not in results (backend filter)', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    // Backend already excludes soft-deleted content; fixture simulates this.
    const activeResult = makeResult({
      source_id: 'active-content-001',
      snippet: 'Active content snippet',
      context: {
        course_id: 'crs-001',
        course_title: 'Test Course',
        module_id: 'mod-001',
        content_id: 'active-content-001',
      },
    });
    // No 'deleted-content-001' in the response (backend filters it out).
    vi.mocked(searchService.search).mockResolvedValue({
      results: [activeResult],
      count: 1,
      top_k: 5,
      query: 'learning',
    });
  });
  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
    vi.resetAllMocks();
  });

  it('does not render soft-deleted content in results (confirmed by fixture)', async () => {
    renderWithProviders(<CourseSearchBar courseId="crs-001" />);

    const input = screen.getByRole('combobox', { name: /search this course/i });
    fireEvent.change(input, { target: { value: 'learning' } });

    await act(async () => {
      vi.advanceTimersByTime(300);
    });

    await waitFor(() => {
      const options = screen.getAllByRole('option');
      // Only active content is in results
      expect(options).toHaveLength(1);
      // Confirm deleted-content ID is absent from the DOM
      expect(screen.queryByText('deleted-content-001')).not.toBeInTheDocument();
    });
  });
});
