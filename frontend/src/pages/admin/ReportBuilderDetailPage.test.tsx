// src/pages/admin/ReportBuilderDetailPage.test.tsx
//
// FE-065: Tests for the Admin Report Builder Detail page.
// Covers: loading state, error state, header (name h1, data source badge,
//         Edit/Run now/Export CSV buttons), Overview tab (description, Filters
//         / Group by / Aggregates sections), Preview tab prompt, Schedules tab
//         empty state, schedules list, schedule toggle and delete, back navigation.
//
// Mocking strategy:
//   - reportBuilderService (getDefinition, listRuns, listSchedules,
//     runDefinition, exportDefinition, updateSchedule, deleteSchedule)
//   - PreviewTable / RunHistoryTable / ScheduleForm → stubs
//   - ConfirmDialog → stub with Confirm/Cancel buttons
//   - useToast → stub (requires ToastProvider context)
//   - useNavigate via importOriginal spread
//   - usePageTitle stubbed
//
// Tabs (Overview/Preview/History/Schedules) are real @headlessui/react
// TabGroup components. Inactive panels are unmounted by default, so tests
// click the relevant tab before asserting panel content.

import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ReportBuilderDetailPage } from './ReportBuilderDetailPage';

// ── Module mocks ──────────────────────────────────────────────────────────────

const mockNavigate = vi.fn();
const mockToast = {
  success: vi.fn(),
  error: vi.fn(),
  warning: vi.fn(),
  info: vi.fn(),
  showToast: vi.fn(),
};

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock('../../services/reportBuilderService', () => ({
  reportBuilderService: {
    getDefinition: vi.fn(),
    listRuns: vi.fn(),
    listSchedules: vi.fn(),
    runDefinition: vi.fn(),
    exportDefinition: vi.fn(),
    updateSchedule: vi.fn(),
    deleteSchedule: vi.fn(),
    createSchedule: vi.fn(),
    getDownloadUrl: vi.fn(),
  },
  normaliseGroupBy: (raw: unknown) =>
    Array.isArray(raw)
      ? raw.map((f: unknown) =>
          typeof f === 'string' ? { field: f } : (f as { field: string }),
        )
      : [],
}));

vi.mock('../../components/reportBuilder/PreviewTable', () => ({
  PreviewTable: ({ errorMessage }: { errorMessage?: string | null }) => (
    <div data-testid="preview-table">{errorMessage ?? 'preview-table-stub'}</div>
  ),
}));

vi.mock('../../components/reportBuilder/RunHistoryTable', () => ({
  RunHistoryTable: () => <div data-testid="run-history-table" />,
}));

vi.mock('../../components/reportBuilder/ScheduleForm', () => ({
  ScheduleForm: ({ open }: { open: boolean }) =>
    open ? <div data-testid="schedule-form" /> : null,
}));

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
        <button onClick={onConfirm}>Confirm</button>
        <button onClick={onClose}>Cancel</button>
      </div>
    ) : null,
}));

vi.mock('../../components/common/Toast', () => ({
  useToast: () => mockToast,
}));

vi.mock('../../hooks/usePageTitle', () => ({ usePageTitle: vi.fn() }));

// ── Typed mock helpers ────────────────────────────────────────────────────────

import { reportBuilderService } from '../../services/reportBuilderService';

const mockGetDefinition = reportBuilderService.getDefinition as ReturnType<typeof vi.fn>;
const mockListRuns = reportBuilderService.listRuns as ReturnType<typeof vi.fn>;
const mockListSchedules = reportBuilderService.listSchedules as ReturnType<typeof vi.fn>;
const mockRunDefinition = reportBuilderService.runDefinition as ReturnType<typeof vi.fn>;
const mockDeleteSchedule = reportBuilderService.deleteSchedule as ReturnType<typeof vi.fn>;
const mockUpdateSchedule = reportBuilderService.updateSchedule as ReturnType<typeof vi.fn>;

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
}

function renderPage(id = 'def-1') {
  const path = `/admin/reports/builder/${id}`;
  return render(
    <QueryClientProvider client={makeClient()}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route
            path="/admin/reports/builder/:id"
            element={<ReportBuilderDetailPage />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// ── Fixtures ──────────────────────────────────────────────────────────────────

function makeDefinition(overrides: Record<string, unknown> = {}) {
  return {
    id: 'def-1',
    name: 'Active Teacher Report',
    description: 'Tracks teacher activity over the past 30 days.',
    data_source: 'teacher_progress',
    filters_json: [],
    group_by_json: [],
    aggregates_json: [],
    created_by: null,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-03-15T10:00:00Z',
    is_soft_deleted: false,
    ...overrides,
  };
}

function makeSchedule(overrides: Record<string, unknown> = {}) {
  return {
    id: 'sch-1',
    cadence: 'weekly',
    run_at_hour: 8,
    run_at_day_of_week: 1,
    run_at_day_of_month: null,
    recipients_json: ['admin@school.com', 'hod@school.com'],
    enabled: true,
    last_run_at: null,
    last_run_status: 'never_run',
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
    ...overrides,
  };
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('ReportBuilderDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Default: all queries resolve with valid data
    mockGetDefinition.mockResolvedValue(makeDefinition());
    mockListRuns.mockResolvedValue([]);
    mockListSchedules.mockResolvedValue([]);
  });

  // ── Loading state ─────────────────────────────────────────────────────────

  it('shows loading state while definition loads', () => {
    mockGetDefinition.mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getByTestId('detail-loading')).toBeInTheDocument();
    expect(screen.getByText('Loading report…')).toBeInTheDocument();
  });

  // ── Error state ───────────────────────────────────────────────────────────

  it('shows error state when definition query rejects', async () => {
    mockGetDefinition.mockRejectedValue(new Error('Not found'));
    renderPage();
    expect(
      await screen.findByTestId('detail-error'),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/report not found or you don't have access/i),
    ).toBeInTheDocument();
  });

  // ── Header ────────────────────────────────────────────────────────────────

  it('renders report name as h1', async () => {
    renderPage();
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Active Teacher Report' }),
    ).toBeInTheDocument();
  });

  it('renders data source badge for teacher_progress', async () => {
    renderPage();
    await screen.findByRole('heading', { level: 1 });
    expect(screen.getByText('Teacher Progress')).toBeInTheDocument();
  });

  it('Edit button navigates to /admin/reports/builder/:id/edit', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole('heading', { level: 1 });
    await user.click(screen.getByTestId('detail-edit'));
    expect(mockNavigate).toHaveBeenCalledWith('/admin/reports/builder/def-1/edit');
  });

  it('back button navigates to /admin/reports/builder', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole('heading', { level: 1 });
    await user.click(screen.getByRole('button', { name: /back to list/i }));
    expect(mockNavigate).toHaveBeenCalledWith('/admin/reports/builder');
  });

  it('Run now button is visible', async () => {
    renderPage();
    await screen.findByRole('heading', { level: 1 });
    expect(screen.getByTestId('detail-run')).toBeInTheDocument();
  });

  it('Export CSV button is visible', async () => {
    renderPage();
    await screen.findByRole('heading', { level: 1 });
    expect(screen.getByTestId('detail-export')).toBeInTheDocument();
  });

  // ── Overview tab (default selected) ───────────────────────────────────────

  it('Overview tab: renders description text', async () => {
    renderPage();
    await screen.findByRole('heading', { level: 1 });
    expect(
      screen.getByText('Tracks teacher activity over the past 30 days.'),
    ).toBeInTheDocument();
  });

  it('Overview tab: shows "None" for empty filters', async () => {
    renderPage();
    await screen.findByRole('heading', { level: 1 });
    const overviewPanel = screen.getByTestId('overview-panel');
    // "None" appears for Filters, Group by, Aggregates — all empty
    const noneEls = within(overviewPanel).getAllByText('None');
    expect(noneEls.length).toBeGreaterThanOrEqual(3);
  });

  it('Overview tab: shows filter code block when filters present', async () => {
    mockGetDefinition.mockResolvedValue(
      makeDefinition({
        filters_json: [{ field: 'progress_pct', op: 'gte', value: 80 }],
      }),
    );
    renderPage();
    await screen.findByRole('heading', { level: 1 });
    expect(screen.getByText(/progress_pct/)).toBeInTheDocument();
    expect(screen.getByText(/gte/)).toBeInTheDocument();
  });

  it('Overview tab: shows aggregate when aggregates present', async () => {
    mockGetDefinition.mockResolvedValue(
      makeDefinition({
        aggregates_json: [{ fn: 'count', field: 'id', alias: 'total' }],
      }),
    );
    renderPage();
    await screen.findByRole('heading', { level: 1 });
    expect(screen.getByText(/count\(id\)/)).toBeInTheDocument();
    expect(screen.getByText(/as total/)).toBeInTheDocument();
  });

  // ── Preview tab ───────────────────────────────────────────────────────────

  it('Preview tab: shows "Click Run now" prompt before any run', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole('heading', { level: 1 });
    await user.click(screen.getByRole('tab', { name: /preview/i }));
    // Text is split across <p>Click <strong>Run now</strong> to preview results.</p>
    // so we assert against the preview panel's textContent directly.
    const previewPanel = await screen.findByTestId('preview-panel');
    expect(previewPanel.textContent).toMatch(/click.*run now.*to preview results/i);
  });

  it('Preview tab: Run now button calls runDefinition', async () => {
    const user = userEvent.setup();
    mockRunDefinition.mockReturnValue(new Promise(() => {})); // never resolves
    renderPage();
    await screen.findByRole('heading', { level: 1 });
    await user.click(screen.getByTestId('detail-run'));
    await waitFor(() => expect(mockRunDefinition).toHaveBeenCalledTimes(1));
  });

  // ── Schedules tab ─────────────────────────────────────────────────────────

  it('Schedules tab: shows "No schedules yet." when empty', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole('heading', { level: 1 });
    await user.click(screen.getByRole('tab', { name: /schedules/i }));
    expect(await screen.findByTestId('schedules-empty')).toBeInTheDocument();
    expect(screen.getByText('No schedules yet.')).toBeInTheDocument();
  });

  it('Schedules tab: shows New schedule button', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole('heading', { level: 1 });
    await user.click(screen.getByRole('tab', { name: /schedules/i }));
    expect(await screen.findByTestId('new-schedule-btn')).toBeInTheDocument();
  });

  it('Schedules tab: renders schedule cadence and time', async () => {
    mockListSchedules.mockResolvedValue([makeSchedule()]);
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole('heading', { level: 1 });
    await user.click(screen.getByRole('tab', { name: /schedules/i }));
    // cadence = weekly, dow = 1, hour = 8
    expect(await screen.findByText(/weekly/i)).toBeInTheDocument();
    expect(screen.getByText(/at 8:00 UTC/i)).toBeInTheDocument();
  });

  it('Schedules tab: shows recipient count', async () => {
    mockListSchedules.mockResolvedValue([makeSchedule()]);
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole('heading', { level: 1 });
    await user.click(screen.getByRole('tab', { name: /schedules/i }));
    // 2 recipients
    expect(await screen.findByText(/2 recipients/i)).toBeInTheDocument();
  });

  it('Schedules tab: delete button opens confirm dialog', async () => {
    mockListSchedules.mockResolvedValue([makeSchedule()]);
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole('heading', { level: 1 });
    await user.click(screen.getByRole('tab', { name: /schedules/i }));
    await screen.findByTestId('delete-schedule-sch-1');
    await user.click(screen.getByTestId('delete-schedule-sch-1'));
    expect(await screen.findByTestId('confirm-dialog')).toBeInTheDocument();
    expect(screen.getByText('Delete schedule?')).toBeInTheDocument();
  });

  it('Schedules tab: confirms delete calls deleteSchedule API', async () => {
    mockDeleteSchedule.mockResolvedValue(undefined);
    mockListSchedules.mockResolvedValue([makeSchedule()]);
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole('heading', { level: 1 });
    await user.click(screen.getByRole('tab', { name: /schedules/i }));
    await screen.findByTestId('delete-schedule-sch-1');
    await user.click(screen.getByTestId('delete-schedule-sch-1'));
    await screen.findByTestId('confirm-dialog');
    await user.click(screen.getByRole('button', { name: 'Confirm' }));
    await waitFor(() =>
      expect(mockDeleteSchedule).toHaveBeenCalledWith('def-1', 'sch-1'),
    );
  });

  it('Schedules tab: enable checkbox toggle calls updateSchedule', async () => {
    mockUpdateSchedule.mockResolvedValue(makeSchedule({ enabled: false }));
    mockListSchedules.mockResolvedValue([makeSchedule()]);
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole('heading', { level: 1 });
    await user.click(screen.getByRole('tab', { name: /schedules/i }));
    const toggle = await screen.findByTestId('schedule-toggle-sch-1');
    await user.click(toggle);
    await waitFor(() =>
      expect(mockUpdateSchedule).toHaveBeenCalledWith(
        'def-1',
        'sch-1',
        expect.objectContaining({ enabled: false }),
      ),
    );
  });
});
