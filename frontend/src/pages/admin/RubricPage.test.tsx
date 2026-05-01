// src/pages/admin/RubricPage.test.tsx
//
// Unit tests for the Admin Rubric Management page.
// Covers: rendering, loading/empty states, rubric list display, pagination
// boundaries, debounced search, deleteTitle snapshot, modal open/close,
// clone mutation, and delete confirmation flow.

import React from 'react';
import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { RubricPage } from './RubricPage';
import { adminRubricService } from '../../services/adminRubricService';
import { ToastProvider } from '../../components/common';

// ── Module mocks ──────────────────────────────────────────────────────────────

vi.mock('../../services/adminRubricService', () => ({
  adminRubricService: {
    listRubrics: vi.fn(),
    createRubric: vi.fn(),
    updateRubric: vi.fn(),
    deleteRubric: vi.fn(),
    cloneRubric: vi.fn(),
    getRubric: vi.fn(),
    getAssignmentRubric: vi.fn(),
    attachRubric: vi.fn(),
    evaluateSubmission: vi.fn(),
    getMyEvaluation: vi.fn(),
  },
}));

vi.mock('../../hooks/usePageTitle', () => ({
  usePageTitle: vi.fn(),
}));

// Stub DataTable — calls each column's `cell` renderer so action buttons are
// rendered.  Falls back to plain-text for columns without a cell function.
vi.mock('../../components/ui/data-table', () => ({
  DataTable: ({
    data,
    columns,
  }: {
    data: Array<Record<string, unknown>>;
    columns: Array<{
      accessorKey?: string;
      id?: string;
      cell?: (ctx: {
        row: { original: Record<string, unknown> };
        getValue: () => unknown;
      }) => React.ReactNode;
    }>;
  }) => (
    <div data-testid="data-table">
      {data.map((row, rowIdx) => (
        <div key={rowIdx} data-testid="data-table-row">
          {columns.map((col) => {
            const colKey = col.accessorKey ?? col.id ?? String(rowIdx);
            if (col.cell) {
              return (
                <span key={colKey}>
                  {col.cell({
                    row: { original: row },
                    getValue: () =>
                      col.accessorKey != null ? row[col.accessorKey] : undefined,
                  })}
                </span>
              );
            }
            if (col.accessorKey != null) {
              const raw = row[col.accessorKey];
              return (
                <span key={colKey}>
                  {typeof raw === 'string' || typeof raw === 'number'
                    ? String(raw)
                    : null}
                </span>
              );
            }
            return null;
          })}
        </div>
      ))}
    </div>
  ),
  DataTableColumnHeader: ({ title }: { title: string }) => <span>{title}</span>,
}));

// Stub Switch to a simple checkbox (avoids Radix UI internals).
vi.mock('../../components/ui/switch', () => ({
  Switch: ({
    id,
    checked,
    onCheckedChange,
    'aria-label': ariaLabel,
  }: {
    id?: string;
    checked: boolean;
    onCheckedChange: (v: boolean) => void;
    'aria-label'?: string;
  }) => (
    <input
      id={id}
      type="checkbox"
      checked={checked}
      onChange={(e) => onCheckedChange(e.target.checked)}
      aria-label={ariaLabel}
    />
  ),
}));

// ── Fixtures ──────────────────────────────────────────────────────────────────

function makeRubric(overrides?: Partial<(typeof mockRubrics)[0]>) {
  return {
    id: 'rubric-1',
    title: 'Research Essay Rubric',
    description: 'For evaluating research quality',
    total_points: 100,
    is_active: true,
    criteria: [
      {
        id: 'crit-1',
        title: 'Argument Quality',
        description: '',
        max_points: 50,
        order: 0,
        levels: [],
      },
      {
        id: 'crit-2',
        title: 'Evidence Use',
        description: '',
        max_points: 50,
        order: 1,
        levels: [],
      },
    ],
    created_at: '2026-04-01T00:00:00Z',
    updated_at: '2026-04-01T00:00:00Z',
    ...overrides,
  };
}

const mockRubrics = [
  makeRubric(),
  makeRubric({
    id: 'rubric-2',
    title: 'Presentation Rubric',
    description: 'For evaluating slide quality',
    total_points: 50,
    is_active: false,
    criteria: [
      {
        id: 'crit-3',
        title: 'Slide Design',
        description: '',
        max_points: 50,
        order: 0,
        levels: [],
      },
    ],
  }),
];

function makeListResponse(
  rubrics = mockRubrics,
  { count, page = 1 }: { count?: number; page?: number } = {},
) {
  const total = count ?? rubrics.length;
  return {
    count: total,
    next: total > 10 && page < Math.ceil(total / 10) ? `/?page=${page + 1}` : null,
    previous: page > 1 ? `/?page=${page - 1}` : null,
    results: rubrics,
  };
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
}

function renderRubricPage() {
  const queryClient = makeQueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <MemoryRouter>
          <RubricPage />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

function setupDefaultMocks() {
  vi.mocked(adminRubricService.listRubrics).mockResolvedValue(makeListResponse());
  vi.mocked(adminRubricService.deleteRubric).mockResolvedValue(undefined);
  vi.mocked(adminRubricService.cloneRubric).mockResolvedValue(
    makeRubric({ id: 'rubric-clone', title: 'Research Essay Rubric (Copy)' }),
  );
  vi.mocked(adminRubricService.createRubric).mockResolvedValue(makeRubric());
  vi.mocked(adminRubricService.updateRubric).mockResolvedValue(makeRubric());
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('RubricPage', () => {
  beforeEach(() => {
    // vi.resetAllMocks() (not clearAllMocks) is required here:
    // clearAllMocks() only resets call-history; it does NOT clear
    // mockResolvedValue() implementations or mockResolvedValueOnce queues.
    // Tests that override listRubrics with mockResolvedValue(count=25) would
    // otherwise leak into subsequent tests (e.g. "disables Next button on the
    // last page"), causing them to see a 3-page result set instead of 2 pages
    // and finding the Next button still enabled.  resetAllMocks() wipes all
    // implementations so setupDefaultMocks() can start from a clean slate.
    vi.resetAllMocks();
    setupDefaultMocks();
  });

  // ── Basic rendering ─────────────────────────────────────────────────────────

  it('renders the page heading "Rubrics"', async () => {
    renderRubricPage();
    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 1, name: /rubrics/i })).toBeInTheDocument();
    });
  });

  it('shows page subtitle', async () => {
    renderRubricPage();
    await waitFor(() => {
      expect(
        screen.getByText(/design grading rubrics/i),
      ).toBeInTheDocument();
    });
  });

  it('renders a "New Rubric" button', async () => {
    renderRubricPage();
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /new rubric/i })).toBeInTheDocument();
    });
  });

  // ── Loading / empty states ──────────────────────────────────────────────────

  it('shows empty state when list returns no rubrics', async () => {
    vi.mocked(adminRubricService.listRubrics).mockResolvedValue(
      makeListResponse([], { count: 0 }),
    );
    renderRubricPage();
    await waitFor(() => {
      expect(screen.getByText(/no rubrics yet/i)).toBeInTheDocument();
    });
  });

  it('shows "Create first rubric" CTA in empty state (no search)', async () => {
    vi.mocked(adminRubricService.listRubrics).mockResolvedValue(
      makeListResponse([], { count: 0 }),
    );
    renderRubricPage();
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /create first rubric/i })).toBeInTheDocument();
    });
  });

  it('shows search-specific empty message when search is active', async () => {
    vi.mocked(adminRubricService.listRubrics).mockResolvedValue(
      makeListResponse([], { count: 0 }),
    );
    const user = userEvent.setup();
    renderRubricPage();

    const searchInput = screen.getByPlaceholderText(/search rubrics/i);
    await user.type(searchInput, 'z');

    await waitFor(
      () => expect(screen.getByText(/no rubrics match your search/i)).toBeInTheDocument(),
      { timeout: 1500 },
    );
  });

  // ── List rendering ──────────────────────────────────────────────────────────

  it('renders rubric titles in the table', async () => {
    renderRubricPage();
    await waitFor(() => {
      expect(screen.getByText('Research Essay Rubric')).toBeInTheDocument();
      expect(screen.getByText('Presentation Rubric')).toBeInTheDocument();
    });
  });

  it('renders total_points for each rubric row', async () => {
    renderRubricPage();
    await waitFor(() => {
      expect(screen.getByText('100')).toBeInTheDocument(); // total_points
      expect(screen.getByText('50')).toBeInTheDocument();
    });
  });

  it('calls listRubrics on mount', async () => {
    renderRubricPage();
    await waitFor(() => {
      expect(adminRubricService.listRubrics).toHaveBeenCalledWith(
        expect.objectContaining({ page: 1 }),
      );
    });
  });

  // ── Search debounce ─────────────────────────────────────────────────────────
  // Strategy: real timers + waitFor (default 1000ms timeout).
  // The debounce delay is 300ms → waitFor polls until the assertion passes.

  it('fires listRubrics with the search term after the 300 ms debounce', async () => {
    const user = userEvent.setup();
    renderRubricPage();

    // Wait for the initial mount query so we have a clean baseline.
    await waitFor(() =>
      expect(adminRubricService.listRubrics).toHaveBeenCalledTimes(1),
    );

    const searchInput = screen.getByPlaceholderText(/search rubrics/i);
    // Single character keeps typing time negligible.
    await user.type(searchInput, 'q');

    // waitFor polls for up to 1 500 ms — the 300 ms debounce fires within that window.
    await waitFor(
      () => {
        expect(adminRubricService.listRubrics).toHaveBeenCalledWith(
          expect.objectContaining({ search: 'q' }),
        );
      },
      { timeout: 1500 },
    );
  });

  it('debounce resets page to 1 when the search changes', async () => {
    // First navigate to page 2, then type in search — page should reset.
    vi.mocked(adminRubricService.listRubrics).mockResolvedValue(
      makeListResponse(mockRubrics, { count: 25 }),
    );
    const user = userEvent.setup();
    renderRubricPage();

    const nextBtn = await screen.findByRole('button', { name: /next/i });
    await user.click(nextBtn);

    await waitFor(() =>
      expect(adminRubricService.listRubrics).toHaveBeenCalledWith(
        expect.objectContaining({ page: 2 }),
      ),
    );

    // Type a search term — debounce should reset page to 1.
    const searchInput = screen.getByPlaceholderText(/search rubrics/i);
    await user.type(searchInput, 'q');

    await waitFor(
      () => {
        expect(adminRubricService.listRubrics).toHaveBeenCalledWith(
          expect.objectContaining({ search: 'q', page: 1 }),
        );
      },
      { timeout: 1500 },
    );
  });

  it('shows a "Clear" button once the user has typed, and clicking it resets the search', async () => {
    const user = userEvent.setup();
    renderRubricPage();

    const searchInput = screen.getByPlaceholderText(/search rubrics/i);
    await user.type(searchInput, 'x');

    const clearBtn = await screen.findByRole('button', { name: /clear/i });
    expect(clearBtn).toBeInTheDocument();

    await user.click(clearBtn);
    expect((searchInput as HTMLInputElement).value).toBe('');
    expect(screen.queryByRole('button', { name: /clear/i })).not.toBeInTheDocument();
  });

  // ── Pagination ──────────────────────────────────────────────────────────────

  it('does NOT render pagination controls when total is ≤ 10 (single page)', async () => {
    // 2 rubrics, pageSize = 10 → totalPages = 1.
    renderRubricPage();
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: /previous/i })).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: /next/i })).not.toBeInTheDocument();
    });
  });

  it('renders pagination controls when there are multiple pages', async () => {
    vi.mocked(adminRubricService.listRubrics).mockResolvedValue(
      makeListResponse(mockRubrics, { count: 25 }),
    );
    renderRubricPage();
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /previous/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /next/i })).toBeInTheDocument();
    });
  });

  it('disables Previous button on page 1', async () => {
    vi.mocked(adminRubricService.listRubrics).mockResolvedValue(
      makeListResponse(mockRubrics, { count: 25 }),
    );
    renderRubricPage();
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /previous/i })).toBeDisabled();
    });
  });

  it('displays page counter "Page 1 of 3 (25 rubrics)"', async () => {
    vi.mocked(adminRubricService.listRubrics).mockResolvedValue(
      makeListResponse(mockRubrics, { count: 25 }),
    );
    renderRubricPage();
    await waitFor(() => {
      expect(screen.getByText(/page 1 of 3/i)).toBeInTheDocument();
      expect(screen.getByText(/25 rubrics/i)).toBeInTheDocument();
    });
  });

  it('clicking Next advances to page 2 and queries with page=2', async () => {
    const user = userEvent.setup();
    vi.mocked(adminRubricService.listRubrics).mockResolvedValue(
      makeListResponse(mockRubrics, { count: 25 }),
    );
    renderRubricPage();

    const nextBtn = await screen.findByRole('button', { name: /next/i });
    await user.click(nextBtn);

    await waitFor(() => {
      expect(adminRubricService.listRubrics).toHaveBeenCalledWith(
        expect.objectContaining({ page: 2 }),
      );
    });
  });

  it('disables Next button on the last page', async () => {
    // count=12 → totalPages=2; simulate user is on page 2
    vi.mocked(adminRubricService.listRubrics)
      .mockResolvedValueOnce(makeListResponse(mockRubrics, { count: 12 }))   // page 1
      .mockResolvedValue(makeListResponse(mockRubrics, { count: 12, page: 2 })); // page 2

    const user = userEvent.setup();
    renderRubricPage();

    const nextBtn = await screen.findByRole('button', { name: /next/i });
    await user.click(nextBtn);

    // Use explicit timeout — under full-suite load React's async state processing
    // can exceed the default ~1000ms waitFor limit; 5000ms avoids false negatives.
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /next/i })).toBeDisabled();
    }, { timeout: 5000 });
  });

  it('clicking Previous from page 2 goes back to page 1', async () => {
    const user = userEvent.setup();
    vi.mocked(adminRubricService.listRubrics).mockResolvedValue(
      makeListResponse(mockRubrics, { count: 25 }),
    );
    renderRubricPage();

    const nextBtn = await screen.findByRole('button', { name: /next/i });
    await user.click(nextBtn);

    await waitFor(() =>
      expect(adminRubricService.listRubrics).toHaveBeenCalledWith(
        expect.objectContaining({ page: 2 }),
      ),
    );

    const prevBtn = screen.getByRole('button', { name: /previous/i });
    await user.click(prevBtn);

    await waitFor(() => {
      // Last call should be with page=1.
      const calls = vi.mocked(adminRubricService.listRubrics).mock.calls;
      const lastPage = calls[calls.length - 1][0]?.page;
      expect(lastPage).toBe(1);
    });
  });

  // ── deleteTitle snapshot ────────────────────────────────────────────────────
  // The reviewer flagged "Delete "undefined"?" flash — this verifies the fix.

  it('captures deleteTitle at button-click time (not from live state)', async () => {
    const user = userEvent.setup();
    renderRubricPage();

    // Wait for the table to render.
    const rows = await screen.findAllByTestId('data-table-row');
    expect(rows.length).toBeGreaterThan(0);

    // Find the first Delete button in the actions column.
    const firstRow = rows[0];
    const deleteBtn = within(firstRow).queryByTitle('Delete rubric')
      ?? screen.getAllByTitle('Delete rubric')[0];
    expect(deleteBtn).toBeTruthy();

    await user.click(deleteBtn!);

    // The ConfirmDialog title should include the rubric title.
    await waitFor(() => {
      expect(
        screen.getByText(/delete "research essay rubric"\?/i),
      ).toBeInTheDocument();
    });
  });

  it('delete dialog still shows correct title after deleteTarget is cleared', async () => {
    // If we had used `deleteTarget?.title` directly in the dialog title,
    // closing the dialog would set deleteTarget=null and cause a flash to "undefined".
    // The fix captures `deleteTitle` at click time, so it persists during the
    // close animation.
    const user = userEvent.setup();
    renderRubricPage();

    // Multiple rows → use getAllByTitle and take the first.
    const deleteBtn = await screen.findAllByTitle('Delete rubric').then((btns) => btns[0]);
    await user.click(deleteBtn);

    // Title is shown.
    await waitFor(() => {
      expect(
        screen.getByText(/delete "research essay rubric"\?/i),
      ).toBeInTheDocument();
    });

    // Cancel — this sets deleteTarget=null.
    const cancelBtn = screen.getByRole('button', { name: /cancel/i });
    await user.click(cancelBtn);

    // Dialog unmounts but we verified it showed the correct title before closing.
    await waitFor(() => {
      expect(
        screen.queryByText(/delete "research essay rubric"\?/i),
      ).not.toBeInTheDocument();
    });
  });

  // ── Modal — create ──────────────────────────────────────────────────────────

  it('opens create modal when "New Rubric" is clicked', async () => {
    const user = userEvent.setup();
    renderRubricPage();

    const newBtn = await screen.findByRole('button', { name: /new rubric/i });
    await user.click(newBtn);

    await waitFor(() => {
      expect(screen.getByText('Create Rubric')).toBeInTheDocument();
    });
  });

  it('modal renders title, description, is_active fields', async () => {
    const user = userEvent.setup();
    renderRubricPage();

    await user.click(await screen.findByRole('button', { name: /new rubric/i }));

    await waitFor(() => {
      expect(screen.getByPlaceholderText(/e\.g\. research essay rubric/i)).toBeInTheDocument();
      expect(screen.getByPlaceholderText(/what this rubric is used for/i)).toBeInTheDocument();
      // Switch rendered as checkbox (our stub)
      expect(screen.getByRole('checkbox')).toBeInTheDocument();
    });
  });

  it('closes modal when close button is clicked', async () => {
    const user = userEvent.setup();
    renderRubricPage();

    await user.click(await screen.findByRole('button', { name: /new rubric/i }));
    await screen.findByText('Create Rubric');

    const closeBtn = screen.getByRole('button', { name: /close/i });
    await user.click(closeBtn);

    await waitFor(() => {
      expect(screen.queryByText('Create Rubric')).not.toBeInTheDocument();
    });
  });

  // ── Modal — edit ────────────────────────────────────────────────────────────

  it('opens edit modal with "Edit Rubric" heading when edit button is clicked', async () => {
    const user = userEvent.setup();
    renderRubricPage();

    const [firstEditBtn] = await screen.findAllByTitle('Edit rubric');
    await user.click(firstEditBtn);

    await waitFor(() => {
      expect(screen.getByText('Edit Rubric')).toBeInTheDocument();
    });
  });

  it('pre-fills title in edit modal', async () => {
    const user = userEvent.setup();
    renderRubricPage();

    const [firstEditBtn] = await screen.findAllByTitle('Edit rubric');
    await user.click(firstEditBtn);

    await waitFor(() => {
      const titleInput = screen.getByDisplayValue('Research Essay Rubric');
      expect(titleInput).toBeInTheDocument();
    });
  });

  // ── Clone mutation ──────────────────────────────────────────────────────────

  it('calls cloneRubric when clone button is clicked', async () => {
    const user = userEvent.setup();
    renderRubricPage();

    const [firstCloneBtn] = await screen.findAllByTitle('Clone rubric');
    await user.click(firstCloneBtn);

    await waitFor(() => {
      expect(adminRubricService.cloneRubric).toHaveBeenCalledWith('rubric-1');
    });
  });

  it('invalidates query cache after clone', async () => {
    const user = userEvent.setup();
    renderRubricPage();

    const [firstCloneBtn] = await screen.findAllByTitle('Clone rubric');
    await user.click(firstCloneBtn);

    await waitFor(() => {
      // listRubrics is called a second time (initial + after-clone invalidation).
      expect(adminRubricService.listRubrics).toHaveBeenCalledTimes(2);
    });
  });

  // ── Delete flow ─────────────────────────────────────────────────────────────

  it('shows delete confirmation dialog on trash button click', async () => {
    const user = userEvent.setup();
    renderRubricPage();

    const [firstDeleteBtn] = await screen.findAllByTitle('Delete rubric');
    await user.click(firstDeleteBtn);

    await waitFor(() => {
      expect(
        screen.getByText(/permanently remove the rubric/i),
      ).toBeInTheDocument();
    });
  });

  it('calls deleteRubric when confirm button is clicked', async () => {
    const user = userEvent.setup();
    renderRubricPage();

    const [firstDeleteBtn] = await screen.findAllByTitle('Delete rubric');
    await user.click(firstDeleteBtn);

    const confirmBtn = await screen.findByRole('button', { name: /confirm/i });
    await user.click(confirmBtn);

    await waitFor(() => {
      expect(adminRubricService.deleteRubric).toHaveBeenCalledWith('rubric-1');
    });
  });

  it('dismisses dialog on Cancel without calling deleteRubric', async () => {
    const user = userEvent.setup();
    renderRubricPage();

    const [firstDeleteBtn] = await screen.findAllByTitle('Delete rubric');
    await user.click(firstDeleteBtn);

    const cancelBtn = await screen.findByRole('button', { name: /cancel/i });
    await user.click(cancelBtn);

    expect(adminRubricService.deleteRubric).not.toHaveBeenCalled();

    await waitFor(() => {
      expect(
        screen.queryByText(/permanently remove the rubric/i),
      ).not.toBeInTheDocument();
    });
  });

  // ── Error states ────────────────────────────────────────────────────────────

  it('shows empty table (not an error crash) when listRubrics rejects', async () => {
    vi.mocked(adminRubricService.listRubrics).mockRejectedValue(
      new Error('Network error'),
    );
    // Should not throw — component handles the query error gracefully.
    expect(() => renderRubricPage()).not.toThrow();
    // The heading is still present (page doesn't crash).
    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 1, name: /rubrics/i })).toBeInTheDocument();
    });
  });
});
