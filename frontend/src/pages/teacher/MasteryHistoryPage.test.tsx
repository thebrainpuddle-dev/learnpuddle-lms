// src/pages/teacher/MasteryHistoryPage.test.tsx
//
// Tests for the TASK-018 Mastery Points history page.
// Covers: heading + back link, summary card, ledger rendering, filter wiring,
//         empty state, and CSV export (including formula-injection hardening).

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { MasteryHistoryPage, downloadMasteryCsv } from './MasteryHistoryPage';
import { masteryService } from '../../services/masteryService';
import { ToastProvider } from '../../components/common';

// ── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock('../../services/masteryService', async () => {
  const actual = await vi.importActual<typeof import('../../services/masteryService')>(
    '../../services/masteryService',
  );
  return {
    ...actual,
    masteryService: {
      getTeacherSummary: vi.fn(),
      getTeacherHistory: vi.fn(),
      getAdminLeaderboard: vi.fn(),
    },
  };
});

vi.mock('../../hooks/usePageTitle', () => ({
  usePageTitle: vi.fn(),
}));

// Stub DataTable so tests can read row content without wrestling TanStack.
vi.mock('../../components/ui/data-table', () => ({
  DataTable: ({
    data,
    columns,
  }: {
    data: Array<Record<string, unknown>>;
    columns: Array<{ id?: string; accessorKey?: string }>;
  }) => (
    <div data-testid="data-table">
      <span>{data.length} rows</span>
      {data.map((row, i) => (
        <div key={i} data-testid="data-table-row">
          {Object.entries(row).map(([k, v]) => {
            if (typeof v === 'string' || typeof v === 'number') {
              return <span key={k}>{String(v)}</span>;
            }
            return null;
          })}
        </div>
      ))}
      <span data-testid="data-table-cols" hidden>
        {columns.length}
      </span>
    </div>
  ),
  DataTableColumnHeader: ({ title }: { title: string }) => <span>{title}</span>,
}));

// ── Fixtures ──────────────────────────────────────────────────────────────────

const mockSummary = {
  teacher_id: 'me',
  teacher_name: 'Me',
  teacher_email: 'me@school.com',
  total_mastery_points: '125.50',
  mp_this_month: '40.00',
  mp_this_week: '20.00',
  last_mp_at: '2026-04-19T10:00:00Z',
};

const mockHistory = {
  count: 2,
  next: null,
  previous: null,
  results: [
    {
      id: 'tx-1',
      teacher: 'me',
      teacher_name: 'Me',
      teacher_email: 'me@school.com',
      amount: '12.50',
      reason: 'quiz_mastery' as const,
      description: 'Algebra Quiz 3',
      reference_id: 'sub-1',
      reference_type: 'quiz_submission',
      skill_code: '',
      created_at: '2026-04-18T09:00:00Z',
    },
    {
      id: 'tx-2',
      teacher: 'me',
      teacher_name: 'Me',
      teacher_email: 'me@school.com',
      amount: '25.00',
      reason: 'course_mastery_bonus' as const,
      description: 'Pedagogy 101 mastered',
      reference_id: 'course-1',
      reference_type: 'course',
      skill_code: '',
      created_at: '2026-04-15T09:00:00Z',
    },
  ],
};

// ── Setup ─────────────────────────────────────────────────────────────────────

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
}

function renderPage() {
  const qc = makeQueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <MemoryRouter>
          <MasteryHistoryPage />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

function setupMocks(historyOverride?: typeof mockHistory) {
  vi.mocked(masteryService.getTeacherSummary).mockResolvedValue(mockSummary);
  vi.mocked(masteryService.getTeacherHistory).mockResolvedValue(
    historyOverride ?? mockHistory,
  );
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('MasteryHistoryPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    setupMocks();
  });

  it('renders page heading and back link to achievements', async () => {
    renderPage();
    expect(
      await screen.findByRole('heading', { level: 1, name: /mastery points/i }),
    ).toBeInTheDocument();
    const back = screen.getByTestId('mastery-back-to-achievements');
    expect(back).toHaveAttribute('href', '/teacher/achievements');
  });

  it('displays the teacher total MP from summary', async () => {
    renderPage();
    const totalEl = await screen.findByTestId('mastery-total-mp');
    await waitFor(() => {
      // 125.50 formatted to 2 decimals once the summary query resolves
      expect(totalEl).toHaveTextContent('125.50');
    });
  });

  it('renders MP transactions in the ledger', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('data-table')).toBeInTheDocument();
    });
    // Both rows render
    expect(screen.getByText('2 rows')).toBeInTheDocument();
    await waitFor(() => {
      expect(masteryService.getTeacherHistory).toHaveBeenCalledWith({
        page: 1,
        source: undefined,
      });
    });
  });

  it('refetches with reason filter when the source select changes', async () => {
    const user = userEvent.setup();
    renderPage();

    const select = await screen.findByTestId('mastery-source-filter');
    await user.selectOptions(select, 'quiz_mastery');

    await waitFor(() => {
      expect(masteryService.getTeacherHistory).toHaveBeenCalledWith({
        page: 1,
        source: 'quiz_mastery',
      });
    });
  });

  it('shows empty state when no MP transactions exist', async () => {
    setupMocks({
      count: 0,
      next: null,
      previous: null,
      results: [],
    });
    renderPage();
    expect(
      await screen.findByText(/no mastery point transactions yet/i),
    ).toBeInTheDocument();
  });

  it('enables CSV export when rows are present', async () => {
    renderPage();
    const btn = await screen.findByTestId('mastery-export-csv');
    await waitFor(() => {
      expect(btn).not.toBeDisabled();
    });
  });
});

// ── CSV hardening unit tests ──────────────────────────────────────────────────

describe('downloadMasteryCsv', () => {
  const originalCreate = URL.createObjectURL;
  const originalRevoke = URL.revokeObjectURL;

  let capturedBlobText = '';

  beforeEach(() => {
    capturedBlobText = '';
    // jsdom doesn't implement Blob.text consistently, so intercept the Blob
    // that downloadMasteryCsv hands to URL.createObjectURL.
    const BlobCtor = global.Blob;
    vi.stubGlobal(
      'Blob',
      class extends BlobCtor {
        constructor(parts: BlobPart[], options?: BlobPropertyBag) {
          super(parts, options);
          capturedBlobText = parts.map((p) => String(p)).join('');
        }
      },
    );
    URL.createObjectURL = vi.fn(() => 'blob:mock');
    URL.revokeObjectURL = vi.fn();
    // Prevent jsdom from actually following the download link.
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    URL.createObjectURL = originalCreate;
    URL.revokeObjectURL = originalRevoke;
    vi.restoreAllMocks();
  });

  it('prefixes formula-injection payloads with a leading apostrophe', () => {
    downloadMasteryCsv(
      [{ Date: '2026-04-19', Description: '=SUM(A1:A10)' }],
      'test.csv',
    );
    // Header row + 1 data row
    expect(capturedBlobText).toMatch(/'=SUM/);
  });

  it('no-ops when given an empty rows array', () => {
    downloadMasteryCsv([], 'test.csv');
    expect(URL.createObjectURL).not.toHaveBeenCalled();
  });
});
