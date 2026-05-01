// src/pages/admin/ReportBuilderEditorPage.test.tsx
//
// FE-064: Tests for the Admin Report Builder Editor (create + edit modes).
// Covers: page heading, form sections (Basics / Filters / Group by / Aggregates),
//         name validation, back/cancel navigation, createDefinition call on submit,
//         success navigation, loading state in edit mode, definition hydration.
//
// Mocking strategy:
//   - reportBuilderService (getDefinition, createDefinition, updateDefinition)
//   - useReportBuilderStore → returns static schema + ensureSchema stub
//   - FilterBuilder / GroupByChips / AggregateBuilder → stubs (avoid DOM complexity)
//   - useToast → stub (requires ToastProvider context)
//   - useNavigate via importOriginal spread
//   - usePageTitle stubbed

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ReportBuilderEditorPage } from './ReportBuilderEditorPage';

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

// Static schema returned by the store mock
const MOCK_SCHEMA = [
  {
    name: 'teacher_progress' as const,
    label: 'Teacher Progress',
    fields: ['user', 'course', 'progress_pct'],
    operators: ['eq', 'ne', 'gt'] as const,
    aggregates: ['count', 'avg'] as const,
  },
  {
    name: 'courses' as const,
    label: 'Courses',
    fields: ['id', 'title'],
    operators: ['eq'] as const,
    aggregates: ['count'] as const,
  },
];

vi.mock('../../stores/reportBuilderStore', () => ({
  useReportBuilderStore: () => ({
    schema: MOCK_SCHEMA,
    ensureSchema: vi.fn().mockResolvedValue(MOCK_SCHEMA),
  }),
}));

vi.mock('../../services/reportBuilderService', () => ({
  reportBuilderService: {
    getDefinition: vi.fn(),
    createDefinition: vi.fn(),
    updateDefinition: vi.fn(),
  },
  normaliseGroupBy: (raw: unknown) =>
    Array.isArray(raw)
      ? raw.map((f: unknown) =>
          typeof f === 'string' ? { field: f } : (f as { field: string }),
        )
      : [],
  serialiseGroupBy: (entries: { field: string }[]) => entries.map((e) => e.field),
}));

vi.mock('../../components/reportBuilder/FilterBuilder', () => ({
  FilterBuilder: () => <div data-testid="filter-builder" />,
}));

vi.mock('../../components/reportBuilder/GroupByChips', () => ({
  GroupByChips: () => <div data-testid="group-by-chips" />,
}));

vi.mock('../../components/reportBuilder/AggregateBuilder', () => ({
  AggregateBuilder: () => <div data-testid="aggregate-builder" />,
}));

vi.mock('../../components/common/Toast', () => ({
  useToast: () => mockToast,
}));

vi.mock('../../hooks/usePageTitle', () => ({ usePageTitle: vi.fn() }));

// ── Typed mock helpers ────────────────────────────────────────────────────────

import { reportBuilderService } from '../../services/reportBuilderService';

const mockCreate = reportBuilderService.createDefinition as ReturnType<typeof vi.fn>;
const mockUpdate = reportBuilderService.updateDefinition as ReturnType<typeof vi.fn>;
const mockGetDefinition = reportBuilderService.getDefinition as ReturnType<typeof vi.fn>;

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
}

/** Render in create mode (no :id param) */
function renderCreate() {
  return render(
    <QueryClientProvider client={makeClient()}>
      <MemoryRouter initialEntries={['/admin/reports/builder/new']}>
        <Routes>
          <Route path="/admin/reports/builder/new" element={<ReportBuilderEditorPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** Render in edit mode with :id = 'def-1' */
function renderEdit() {
  return render(
    <QueryClientProvider client={makeClient()}>
      <MemoryRouter initialEntries={['/admin/reports/builder/def-1/edit']}>
        <Routes>
          <Route
            path="/admin/reports/builder/:id/edit"
            element={<ReportBuilderEditorPage />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// ── Fixtures ──────────────────────────────────────────────────────────────────

function makeDefinition() {
  return {
    id: 'def-1',
    name: 'Active Teacher Report',
    description: 'Tracks teacher activity over time.',
    data_source: 'teacher_progress',
    filters_json: [],
    group_by_json: [],
    aggregates_json: [],
    created_by: null,
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-03-01T00:00:00Z',
    is_soft_deleted: false,
  };
}

function makeSavedDefinition(overrides = {}) {
  return { ...makeDefinition(), ...overrides };
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('ReportBuilderEditorPage — create mode', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockCreate.mockResolvedValue(makeSavedDefinition({ id: 'new-def-99' }));
  });

  it('renders "New report" heading', () => {
    renderCreate();
    expect(
      screen.getByRole('heading', { level: 1, name: /new report/i }),
    ).toBeInTheDocument();
  });

  it('renders "Basics" section header', () => {
    renderCreate();
    expect(screen.getByRole('heading', { level: 2, name: /basics/i })).toBeInTheDocument();
  });

  it('renders name input with placeholder', () => {
    renderCreate();
    const nameInput = screen.getByTestId('editor-name');
    expect(nameInput).toBeInTheDocument();
    expect(nameInput).toHaveAttribute(
      'placeholder',
      'e.g. Active teachers per department',
    );
  });

  it('renders description textarea', () => {
    renderCreate();
    expect(screen.getByTestId('editor-description')).toBeInTheDocument();
  });

  it('renders data source select with schema options', () => {
    renderCreate();
    const select = screen.getByTestId('editor-data-source');
    expect(select).toBeInTheDocument();
    // Options come from MOCK_SCHEMA
    expect(screen.getByRole('option', { name: 'Teacher Progress' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Courses' })).toBeInTheDocument();
  });

  it('shows "Name is required" validation error when submitted empty', async () => {
    const user = userEvent.setup();
    renderCreate();
    // Submit without filling name
    const submitBtn = screen.getByTestId('editor-submit');
    await user.click(submitBtn);
    expect(await screen.findByRole('alert')).toHaveTextContent('Name is required');
  });

  it('back button (arrow) navigates to /admin/reports/builder', async () => {
    const user = userEvent.setup();
    renderCreate();
    const backBtn = screen.getByRole('button', { name: /back to list/i });
    await user.click(backBtn);
    expect(mockNavigate).toHaveBeenCalledWith('/admin/reports/builder');
  });

  it('Cancel button navigates to /admin/reports/builder', async () => {
    const user = userEvent.setup();
    renderCreate();
    const cancelBtn = screen.getByRole('button', { name: /cancel/i });
    await user.click(cancelBtn);
    expect(mockNavigate).toHaveBeenCalledWith('/admin/reports/builder');
  });

  it('calls createDefinition with name on valid submit', async () => {
    const user = userEvent.setup();
    renderCreate();
    await user.type(screen.getByTestId('editor-name'), 'My New Report');
    await user.click(screen.getByTestId('editor-submit'));
    await waitFor(() => expect(mockCreate).toHaveBeenCalledTimes(1));
    const payload = mockCreate.mock.calls[0][0];
    expect(payload.name).toBe('My New Report');
  });

  it('navigates to detail page after successful create', async () => {
    const user = userEvent.setup();
    renderCreate();
    await user.type(screen.getByTestId('editor-name'), 'My New Report');
    await user.click(screen.getByTestId('editor-submit'));
    await waitFor(() =>
      expect(mockNavigate).toHaveBeenCalledWith('/admin/reports/builder/new-def-99'),
    );
  });
});

describe('ReportBuilderEditorPage — edit mode', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUpdate.mockResolvedValue(makeDefinition());
  });

  it('shows loading state while definition loads', () => {
    mockGetDefinition.mockReturnValue(new Promise(() => {}));
    renderEdit();
    expect(screen.getByTestId('editor-loading')).toBeInTheDocument();
    expect(screen.getByText('Loading report…')).toBeInTheDocument();
  });

  it('renders "Edit report" heading after definition loads', async () => {
    mockGetDefinition.mockResolvedValue(makeDefinition());
    renderEdit();
    expect(
      await screen.findByRole('heading', { level: 1, name: /edit report/i }),
    ).toBeInTheDocument();
  });

  it('hydrates name input with existing definition name', async () => {
    mockGetDefinition.mockResolvedValue(makeDefinition());
    renderEdit();
    await screen.findByRole('heading', { level: 1, name: /edit report/i });
    const nameInput = screen.getByTestId('editor-name') as HTMLInputElement;
    expect(nameInput.value).toBe('Active Teacher Report');
  });

  it('calls updateDefinition (not create) on submit', async () => {
    const user = userEvent.setup();
    mockGetDefinition.mockResolvedValue(makeDefinition());
    renderEdit();
    await screen.findByRole('heading', { level: 1, name: /edit report/i });
    // Submit via "Save changes" button
    await user.click(screen.getByTestId('editor-submit'));
    await waitFor(() => expect(mockUpdate).toHaveBeenCalledWith('def-1', expect.objectContaining({ name: 'Active Teacher Report' })));
    expect(mockCreate).not.toHaveBeenCalled();
  });
});
