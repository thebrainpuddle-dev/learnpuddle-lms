// src/pages/admin/EngagementHeatmapPage.test.tsx
//
// Tests for the Admin Engagement Heatmap page.
// Covers: grid rendering, legend, empty state, error state, timezone toggle
// triggering a refetch with the expected params.

import React from 'react';
import {
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { EngagementHeatmapPage } from './EngagementHeatmapPage';
import { adminReportsService } from '../../services/adminReportsService';
import { ToastProvider } from '../../components/common';

// ── Mocks ────────────────────────────────────────────────────────────────

vi.mock('../../services/adminReportsService', () => ({
  adminReportsService: {
    engagementHeatmap: vi.fn(),
  },
}));

vi.mock('../../hooks/usePageTitle', () => ({
  usePageTitle: vi.fn(),
}));

const mockedHeatmap = vi.mocked(adminReportsService.engagementHeatmap);

// ── Fixtures ─────────────────────────────────────────────────────────────

function buildCells(): { day: number; hour: number; count: number }[] {
  const out: { day: number; hour: number; count: number }[] = [];
  for (let d = 0; d < 7; d++) {
    for (let h = 0; h < 24; h++) {
      out.push({ day: d, hour: h, count: 0 });
    }
  }
  return out;
}

function fixtureWithActivity() {
  const cells = buildCells();
  // Monday 09:00 → 5 events
  cells.find((c) => c.day === 0 && c.hour === 9)!.count = 5;
  // Wednesday 14:00 → 12 events (peak)
  cells.find((c) => c.day === 2 && c.hour === 14)!.count = 12;
  return {
    timezone: 'UTC',
    tz_fallback: false,
    start: '2026-03-21',
    end: '2026-04-20',
    total_events: 17,
    max_cell: 12,
    cells,
  };
}

function emptyFixture() {
  return {
    timezone: 'UTC',
    tz_fallback: false,
    start: '2026-03-21',
    end: '2026-04-20',
    total_events: 0,
    max_cell: 0,
    cells: buildCells(),
  };
}

// ── Harness ──────────────────────────────────────────────────────────────

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ToastProvider>
          <EngagementHeatmapPage />
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// ── Tests ────────────────────────────────────────────────────────────────

describe('EngagementHeatmapPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('renders the 7x24 grid with counts in active cells', async () => {
    mockedHeatmap.mockResolvedValue(fixtureWithActivity());

    renderPage();

    const grid = await screen.findByTestId('heatmap-grid');
    expect(grid).toBeInTheDocument();

    // Monday 09:00 bucket shows 5
    const mon9 = within(grid).getByTestId('heatmap-cell-0-9');
    expect(mon9).toHaveAttribute('data-count', '5');
    expect(mon9).toHaveTextContent('5');

    // Wednesday 14:00 bucket shows 12 (peak)
    const wed14 = within(grid).getByTestId('heatmap-cell-2-14');
    expect(wed14).toHaveAttribute('data-count', '12');
    expect(wed14).toHaveTextContent('12');

    // A quiet cell renders but has no count text
    const sun3 = within(grid).getByTestId('heatmap-cell-6-3');
    expect(sun3).toHaveAttribute('data-count', '0');
    expect(sun3).toHaveTextContent('');

    // Summary reflects the API
    expect(screen.getByTestId('stat-total-events')).toHaveTextContent('17');
    expect(screen.getByTestId('stat-peak-cell')).toHaveTextContent('12');
  });

  it('renders the colour-scale legend', async () => {
    mockedHeatmap.mockResolvedValue(fixtureWithActivity());

    renderPage();

    const legend = await screen.findByTestId('heatmap-legend');
    expect(legend).toBeInTheDocument();
    expect(within(legend).getByText(/Less/i)).toBeInTheDocument();
    expect(within(legend).getByText(/More/i)).toBeInTheDocument();
  });

  it('refetches with tz=UTC when the user switches timezone to UTC', async () => {
    const user = userEvent.setup();
    mockedHeatmap.mockResolvedValue(fixtureWithActivity());

    renderPage();

    // Wait for the loading state to resolve and the controls to mount.
    await screen.findByTestId('heatmap-grid');
    await waitFor(() => expect(mockedHeatmap).toHaveBeenCalledTimes(1));

    const tzSelect = screen.getByLabelText(/Timezone/i);
    await user.selectOptions(tzSelect, 'utc');

    await waitFor(() => {
      const lastCall = mockedHeatmap.mock.calls.at(-1);
      expect(lastCall?.[0]).toMatchObject({ tz: 'UTC' });
    });
  });

  it('shows the empty state when total_events is zero', async () => {
    mockedHeatmap.mockResolvedValue(emptyFixture());

    renderPage();

    await waitFor(() =>
      expect(screen.getByTestId('heatmap-empty')).toBeInTheDocument(),
    );
    expect(
      screen.getByText(/No engagement yet in this window/i),
    ).toBeInTheDocument();
    // Grid is not rendered in the empty state
    expect(screen.queryByTestId('heatmap-grid')).toBeNull();
  });

  it('renders a recoverable error state when the API fails', async () => {
    mockedHeatmap.mockRejectedValue(new Error('boom'));

    renderPage();

    await waitFor(() =>
      expect(screen.getByTestId('heatmap-error')).toBeInTheDocument(),
    );
    expect(
      screen.getByText(/Could not load engagement heatmap/i),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Retry/i })).toBeInTheDocument();
  });

  it('refetches when the window preset changes', async () => {
    const user = userEvent.setup();
    mockedHeatmap.mockResolvedValue(fixtureWithActivity());

    renderPage();

    await screen.findByTestId('heatmap-grid');
    await waitFor(() => expect(mockedHeatmap).toHaveBeenCalled());
    const firstStart = mockedHeatmap.mock.calls[0][0]?.start;

    const windowSelect = screen.getByLabelText(/Window/i);
    await user.selectOptions(windowSelect, '7');

    await waitFor(() => {
      const latest = mockedHeatmap.mock.calls.at(-1);
      expect(latest?.[0]?.start).toBeDefined();
      // A 7-day window must produce a more recent `start` than the default 30-day window.
      expect(String(latest?.[0]?.start) > String(firstStart)).toBe(true);
    });
  });
});
