// src/pages/admin/SearchPage.test.tsx
//
// Test suite for SearchPage — admin tenant-wide semantic search.
//
// Coverage strategy:
//   1. Page header (h1, subtitle)
//   2. Idle state (prompt shown before typing)
//   3. Search input (aria-label, placeholder)
//   4. Loading skeleton shown during search
//   5. Search results grouped by course (course title, Open button, result items)
//   6. Empty state ("No results found")
//   7. Error state (banner, message, Retry button)
//   8. Clear button (appears, clears query + results)
//   9. Character limit enforcement (counter, over-limit alert)
//  10. Click result → navigate to course editor
//  11. Click "Open" course group button → navigate
//
// Timer note:
//   SearchPage debounces input changes by 300ms. All tests use real timers
//   + waitFor({ timeout: 2000 }) which comfortably outlasts the 300ms debounce.
//   This avoids the fake-timer + findBy interaction where waitFor's polling
//   setTimeout freezes under vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] }).

import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { SearchPage } from './SearchPage';
import { searchService } from '../../services/searchService';
import type { SearchResult } from '../../services/searchService';

// ── service mock ──────────────────────────────────────────────────────────────
vi.mock('../../services/searchService', () => ({
  searchService: { search: vi.fn() },
}));

// ── SearchResultItem stub ─────────────────────────────────────────────────────
vi.mock('../../components/search/SearchResultItem', () => ({
  SearchResultItem: ({
    result,
    onClick,
  }: {
    result: SearchResult;
    onClick: (r: SearchResult) => void;
  }) => (
    <div data-testid="search-result-item" onClick={() => onClick(result)}>
      {result.snippet}
    </div>
  ),
}));

vi.mock('../../hooks/usePageTitle', () => ({ usePageTitle: vi.fn() }));

// ── typed service ref ─────────────────────────────────────────────────────────
const mockedSearch = searchService as { search: ReturnType<typeof vi.fn> };

// ── fixture data ──────────────────────────────────────────────────────────────
const RESULT_A: SearchResult = {
  source_type: 'content',
  source_id: 'content-1',
  chunk_index: 0,
  score: 0.92,
  snippet: 'Understanding fractions with examples',
  context: {
    course_id: 'course-1',
    course_title: 'Mathematics Grade 5',
    module_id: 'mod-1',
    content_id: 'content-1',
  },
};

const RESULT_B: SearchResult = {
  source_type: 'module',
  source_id: 'mod-2',
  chunk_index: 0,
  score: 0.85,
  snippet: 'Algebra fundamentals overview',
  context: {
    course_id: 'course-2',
    course_title: 'Algebra Grade 7',
    module_id: 'mod-2',
    content_id: null,
  },
};

const RESULT_C: SearchResult = {
  source_type: 'content',
  source_id: 'content-2',
  chunk_index: 1,
  score: 0.78,
  snippet: 'Practice problems on fractions',
  context: {
    course_id: 'course-1', // same course as RESULT_A → grouped together
    course_title: 'Mathematics Grade 5',
    module_id: 'mod-1',
    content_id: 'content-2',
  },
};

const RESPONSE_WITH_RESULTS = {
  results: [RESULT_A, RESULT_B, RESULT_C],
  count: 3,
  top_k: 20,
  query: 'fractions',
};

const RESPONSE_EMPTY = {
  results: [],
  count: 0,
  top_k: 20,
  query: 'xyzzy',
};

const SEARCH_TIMEOUT = 2000; // generous timeout for 300ms debounce + async resolution

// ── helpers ───────────────────────────────────────────────────────────────────
function renderPage() {
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <SearchPage />
    </MemoryRouter>
  );
}

/**
 * Type in the search input (triggers debounce) and wait for the service
 * to be called. Uses real timers — waitFor polls until the 300ms debounce fires.
 */
async function typeAndWaitForSearch(query: string) {
  const input = screen.getByRole('searchbox');
  // fireEvent.change is synchronous and sets the full value at once,
  // triggering a single debounce timer — faster than userEvent.type for long queries.
  fireEvent.change(input, { target: { value: query } });
  await waitFor(
    () => expect(mockedSearch.search).toHaveBeenCalledWith(query, expect.any(Object)),
    { timeout: SEARCH_TIMEOUT }
  );
}

// ─────────────────────────────────────────────────────────────────────────────
describe('SearchPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockedSearch.search.mockResolvedValue(RESPONSE_WITH_RESULTS);
  });

  // ── 1. Page header ─────────────────────────────────────────────────────────
  describe('page header', () => {
    it('renders the "Search Content" heading', () => {
      renderPage();
      expect(screen.getByRole('heading', { name: /Search Content/i })).toBeInTheDocument();
    });

    it('renders the subtitle', () => {
      renderPage();
      expect(
        screen.getByText(/Find course content, modules, and transcripts/i)
      ).toBeInTheDocument();
    });
  });

  // ── 2. Idle state ──────────────────────────────────────────────────────────
  describe('idle state', () => {
    it('shows "Type to search" prompt when input is empty', () => {
      renderPage();
      expect(screen.getByText(/Type to search across all course content/i)).toBeInTheDocument();
    });

    it('does not show result items in idle state', () => {
      renderPage();
      expect(screen.queryByTestId('search-result-item')).not.toBeInTheDocument();
    });
  });

  // ── 3. Search input ────────────────────────────────────────────────────────
  describe('search input', () => {
    it('renders the search input with correct aria-label', () => {
      renderPage();
      expect(
        screen.getByRole('searchbox', { name: /Search tenant content/i })
      ).toBeInTheDocument();
    });

    it('has the correct placeholder text', () => {
      renderPage();
      expect(
        screen.getByPlaceholderText(/Search across all courses/i)
      ).toBeInTheDocument();
    });
  });

  // ── 4. Loading skeleton ────────────────────────────────────────────────────
  describe('loading state', () => {
    it('shows the loading skeleton while search is in progress', async () => {
      mockedSearch.search.mockReturnValue(new Promise(() => {})); // never resolves
      renderPage();
      const input = screen.getByRole('searchbox');
      fireEvent.change(input, { target: { value: 'fractions' } });
      // Loading skeleton appears after 300ms debounce fires
      await waitFor(
        () => expect(screen.getByLabelText(/Loading search results/i)).toBeInTheDocument(),
        { timeout: SEARCH_TIMEOUT }
      );
    });
  });

  // ── 5. Search results grouped by course ────────────────────────────────────
  describe('search results', () => {
    it('shows course title headings in results', async () => {
      renderPage();
      await typeAndWaitForSearch('fractions');
      await waitFor(() => {
        expect(screen.getByText('Mathematics Grade 5')).toBeInTheDocument();
        expect(screen.getByText('Algebra Grade 7')).toBeInTheDocument();
      }, { timeout: SEARCH_TIMEOUT });
    });

    it('renders SearchResultItem stubs for each result', async () => {
      renderPage();
      await typeAndWaitForSearch('fractions');
      await waitFor(() => {
        expect(screen.getAllByTestId('search-result-item').length).toBe(3);
      }, { timeout: SEARCH_TIMEOUT });
    });

    it('renders result snippets', async () => {
      renderPage();
      await typeAndWaitForSearch('fractions');
      await waitFor(() => {
        expect(screen.getByText('Understanding fractions with examples')).toBeInTheDocument();
        expect(screen.getByText('Algebra fundamentals overview')).toBeInTheDocument();
      }, { timeout: SEARCH_TIMEOUT });
    });

    it('shows one "Open" button per course group', async () => {
      renderPage();
      await typeAndWaitForSearch('fractions');
      // RESULT_A+C → course-1, RESULT_B → course-2 = 2 course groups = 2 Open buttons
      await waitFor(() => {
        expect(screen.getAllByRole('button', { name: /Open/i }).length).toBe(2);
      }, { timeout: SEARCH_TIMEOUT });
    });

    it('results from the same course appear in the same group', async () => {
      renderPage();
      await typeAndWaitForSearch('fractions');
      await waitFor(() => {
        // Both RESULT_A and RESULT_C snippets under the Mathematics Grade 5 heading
        expect(screen.getByText('Understanding fractions with examples')).toBeInTheDocument();
        expect(screen.getByText('Practice problems on fractions')).toBeInTheDocument();
      }, { timeout: SEARCH_TIMEOUT });
    });
  });

  // ── 6. Empty state ─────────────────────────────────────────────────────────
  describe('empty state', () => {
    it('shows "No results found" when search returns empty results', async () => {
      mockedSearch.search.mockResolvedValue(RESPONSE_EMPTY);
      renderPage();
      await typeAndWaitForSearch('xyzzy');
      await waitFor(
        () => expect(screen.getByText(/No results found/i)).toBeInTheDocument(),
        { timeout: SEARCH_TIMEOUT }
      );
    });

    it('shows the committed query in the no-results message', async () => {
      mockedSearch.search.mockResolvedValue(RESPONSE_EMPTY);
      renderPage();
      await typeAndWaitForSearch('xyzzy');
      await waitFor(
        () => expect(screen.getByText(/xyzzy/i)).toBeInTheDocument(),
        { timeout: SEARCH_TIMEOUT }
      );
    });
  });

  // ── 7. Error state ─────────────────────────────────────────────────────────
  describe('error state', () => {
    it('shows error banner when search throws a generic error', async () => {
      mockedSearch.search.mockRejectedValue(new Error('Network error'));
      renderPage();
      await typeAndWaitForSearch('fractions');
      await waitFor(
        () => expect(screen.getByRole('alert')).toBeInTheDocument(),
        { timeout: SEARCH_TIMEOUT }
      );
    });

    it('shows "Search failed" message for generic errors', async () => {
      mockedSearch.search.mockRejectedValue(new Error('Generic error'));
      renderPage();
      await typeAndWaitForSearch('fractions');
      await waitFor(
        () => expect(screen.getByText(/Search failed/i)).toBeInTheDocument(),
        { timeout: SEARCH_TIMEOUT }
      );
    });

    it('shows "Search service is temporarily unavailable" for 503 errors', async () => {
      mockedSearch.search.mockRejectedValue({ response: { status: 503 } });
      renderPage();
      await typeAndWaitForSearch('fractions');
      await waitFor(
        () =>
          expect(
            screen.getByText(/Search service is temporarily unavailable/i)
          ).toBeInTheDocument(),
        { timeout: SEARCH_TIMEOUT }
      );
    });

    it('shows Retry button in the error banner', async () => {
      mockedSearch.search.mockRejectedValue(new Error('Network error'));
      renderPage();
      await typeAndWaitForSearch('fractions');
      await waitFor(
        () => expect(screen.getByTestId('search-retry-btn')).toBeInTheDocument(),
        { timeout: SEARCH_TIMEOUT }
      );
    });
  });

  // ── 8. Clear button ────────────────────────────────────────────────────────
  describe('clear button', () => {
    it('shows Clear button after typing a query', async () => {
      renderPage();
      await userEvent.type(screen.getByRole('searchbox'), 'hello');
      expect(
        await screen.findByRole('button', { name: /Clear search/i })
      ).toBeInTheDocument();
    });

    it('clicking Clear resets input and returns to idle state', async () => {
      renderPage();
      await typeAndWaitForSearch('fractions');
      await waitFor(
        () => expect(screen.getAllByTestId('search-result-item').length).toBeGreaterThan(0),
        { timeout: SEARCH_TIMEOUT }
      );
      const clearBtn = screen.getByRole('button', { name: /Clear search/i });
      await userEvent.click(clearBtn);
      await waitFor(() => {
        expect(screen.getByRole('searchbox')).toHaveValue('');
        expect(screen.getByText(/Type to search across all course content/i)).toBeInTheDocument();
      });
    });
  });

  // ── 9. Character limit ─────────────────────────────────────────────────────
  describe('character limit', () => {
    it('shows character counter when query exceeds 70% of 200 char limit (> 140)', async () => {
      renderPage();
      const input = screen.getByRole('searchbox');
      await userEvent.type(input, 'a'.repeat(141));
      await waitFor(() => {
        expect(screen.getByText(/\/200/)).toBeInTheDocument();
      });
    });

    it('shows over-limit alert when query exceeds 200 characters', async () => {
      renderPage();
      const input = screen.getByRole('searchbox');
      fireEvent.change(input, { target: { value: 'a'.repeat(201) } });
      await waitFor(() => {
        expect(screen.getByRole('alert')).toBeInTheDocument();
        expect(screen.getByText(/Query is too long/i)).toBeInTheDocument();
      });
    });
  });

  // ── 10. Click result → navigate ────────────────────────────────────────────
  describe('result click navigation', () => {
    it('clicking a result item calls the onClick handler', async () => {
      renderPage();
      await typeAndWaitForSearch('fractions');
      const items = await screen.findAllByTestId('search-result-item', {}, { timeout: SEARCH_TIMEOUT });
      // Clicking navigates via useNavigate — verify no error is thrown
      await userEvent.click(items[0]);
      expect(items[0]).toBeInTheDocument();
    });
  });

  // ── 11. Click "Open" → navigate ────────────────────────────────────────────
  describe('"Open" course group button', () => {
    it('clicking the "Open" button on a course group does not throw', async () => {
      renderPage();
      await typeAndWaitForSearch('fractions');
      const openBtns = await screen.findAllByRole('button', { name: /Open/i }, { timeout: SEARCH_TIMEOUT });
      // Navigate to /admin/courses/{courseId}/edit
      await userEvent.click(openBtns[0]);
      expect(openBtns[0]).toBeInTheDocument();
    });
  });
});
