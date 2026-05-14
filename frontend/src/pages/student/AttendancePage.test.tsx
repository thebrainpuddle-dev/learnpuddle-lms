// src/pages/student/AttendancePage.test.tsx
//
// Comprehensive Vitest + React Testing Library test suite for StudentAttendancePage.
//
// Covers: page heading, export button, loading state, error state, month navigation,
// attendance stats, calendar grid, empty-state, and calendar legend.
//
// Mocking strategy:
//   - api (axios instance) is mocked via vi.mock so queryFn calls resolve controlled data.
//   - useTenantStore is mocked to satisfy AttendanceLoader's theme requirement.
//   - usePageTitle is stubbed to avoid document.title side-effects.
//   - ExportAttendanceModal is mocked to keep the test surface focused on the page.

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { StudentAttendancePage } from './AttendancePage';

// ─── Module mocks ─────────────────────────────────────────────────────────────

vi.mock('../../config/api', () => ({
  __esModule: true,
  default: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));

vi.mock('../../stores/tenantStore', () => ({
  useTenantStore: vi.fn(() => ({ theme: { name: 'Test School', logo: null } })),
}));

vi.mock('../../hooks/usePageTitle', () => ({ usePageTitle: vi.fn() }));

// Stub the modal so we don't have to deal with Headless UI portals
vi.mock('../../components/attendance/ExportAttendanceModal', () => ({
  ExportAttendanceModal: ({ open, onClose }: { open: boolean; onClose: () => void }) =>
    open ? (
      <div data-testid="export-modal">
        <button onClick={onClose}>Close Modal</button>
      </div>
    ) : null,
}));

// ─── Import api AFTER mock ─────────────────────────────────────────────────────

import api from '../../config/api';

const mockedApi = api as unknown as { get: ReturnType<typeof vi.fn> };

// ─── Fixtures ─────────────────────────────────────────────────────────────────

const MOCK_ATTENDANCE_RESPONSE = {
  month: '2026-04',
  summary: {
    total_days: 20,
    present: 15,
    late: 3,
    absent: 2,
    excused: 0,
    attendance_rate: 90,
    on_time_pct: 75,
    late_pct: 15,
    absent_pct: 10,
  },
  days: [
    { date: '2026-04-01', status: 'PRESENT', remarks: '' },
    { date: '2026-04-02', status: 'LATE', remarks: 'Arrived 10 min late' },
    { date: '2026-04-03', status: 'ABSENT', remarks: 'Sick' },
    { date: '2026-04-07', status: 'PRESENT', remarks: '' },
    { date: '2026-04-08', status: 'EXCUSED', remarks: 'School trip' },
  ],
};

const MOCK_EMPTY_RESPONSE = {
  month: '2026-04',
  summary: {
    total_days: 0,
    present: 0,
    late: 0,
    absent: 0,
    excused: 0,
    attendance_rate: 0,
    on_time_pct: 0,
    late_pct: 0,
    absent_pct: 0,
  },
  days: [],
};

// ─── Test helpers ─────────────────────────────────────────────────────────────

const makeQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        staleTime: Infinity,
        refetchOnWindowFocus: false,
      },
    },
  });

const renderPage = () =>
  render(
    <QueryClientProvider client={makeQueryClient()}>
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <StudentAttendancePage />
      </MemoryRouter>
    </QueryClientProvider>,
  );

// ─── Suite ────────────────────────────────────────────────────────────────────

describe('StudentAttendancePage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockedApi.get.mockResolvedValue({ data: MOCK_ATTENDANCE_RESPONSE });
  });

  // ── 1. Page heading ──────────────────────────────────────────────────────────

  it('renders the "My Attendance" page heading', async () => {
    renderPage();
    expect(
      await screen.findByRole('heading', { level: 1, name: /my attendance/i }),
    ).toBeInTheDocument();
  });

  // ── 2. Subtitle ───────────────────────────────────────────────────────────────

  it('renders the subtitle about the current academic year', async () => {
    renderPage();
    expect(
      await screen.findByText(/your attendance record for the current academic year/i),
    ).toBeInTheDocument();
  });

  // ── 3. Export CSV button ──────────────────────────────────────────────────────

  it('renders the "Export CSV" button', async () => {
    renderPage();
    expect(
      await screen.findByRole('button', { name: /export csv/i }),
    ).toBeInTheDocument();
  });

  it('opens the export modal when the Export CSV button is clicked', async () => {
    const user = userEvent.setup();
    renderPage();

    const exportBtn = await screen.findByRole('button', { name: /export csv/i });
    await user.click(exportBtn);

    expect(screen.getByTestId('export-modal')).toBeInTheDocument();
  });

  it('closes the export modal when the modal calls onClose', async () => {
    const user = userEvent.setup();
    renderPage();

    const exportBtn = await screen.findByRole('button', { name: /export csv/i });
    await user.click(exportBtn);

    const closeBtn = screen.getByRole('button', { name: /close modal/i });
    await user.click(closeBtn);

    expect(screen.queryByTestId('export-modal')).not.toBeInTheDocument();
  });

  // ── 4. Loading state ──────────────────────────────────────────────────────────

  it('shows the attendance loader while the query is in-flight', () => {
    mockedApi.get.mockReturnValue(new Promise(() => {}));
    const { container } = renderPage();

    // AttendanceLoader renders an animate-spin element
    const spinner = container.querySelector('.animate-spin');
    expect(spinner).toBeInTheDocument();
  });

  it('shows "Loading attendance..." text while loading', () => {
    mockedApi.get.mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getByText(/loading attendance/i)).toBeInTheDocument();
  });

  // ── 5. Error state ────────────────────────────────────────────────────────────

  it('shows the error state when the API call fails', async () => {
    mockedApi.get.mockRejectedValue(new Error('Network error'));
    renderPage();
    expect(await screen.findByText(/unable to load attendance/i)).toBeInTheDocument();
  });

  it('shows the "Please try again later" hint in the error state', async () => {
    mockedApi.get.mockRejectedValue(new Error('Network error'));
    renderPage();
    expect(await screen.findByText(/please try again later/i)).toBeInTheDocument();
  });

  // ── 6. Attendance stats visible after data loads ──────────────────────────────

  it('renders the attendance rate from the summary', async () => {
    renderPage();
    // AttendanceCard renders "{attendance_rate}%" as the big number
    expect(await screen.findByText('90%')).toBeInTheDocument();
  });

  it('renders the On-Time percentage in the card legend', async () => {
    renderPage();
    expect(await screen.findByText('75%')).toBeInTheDocument();
  });

  it('renders the Late percentage in the card legend', async () => {
    renderPage();
    expect(await screen.findByText('15%')).toBeInTheDocument();
  });

  it('renders the Absent percentage in the card legend', async () => {
    renderPage();
    expect(await screen.findByText('10%')).toBeInTheDocument();
  });

  // ── 7. Month name in calendar header ──────────────────────────────────────────

  it('renders the current month name in the calendar', async () => {
    renderPage();

    // The component initialises to the current month; confirm the calendar nav
    // h3 "{Month} {Year}" is present after data loads. Use month + year to
    // distinguish from the AttendanceCard h3 "{Month} Attendance".
    const now = new Date();
    const MONTH_NAMES = [
      'January', 'February', 'March', 'April', 'May', 'June',
      'July', 'August', 'September', 'October', 'November', 'December',
    ];
    const expectedMonth = MONTH_NAMES[now.getMonth()];

    expect(
      await screen.findByRole('heading', {
        level: 3,
        name: new RegExp(`${expectedMonth}.*${now.getFullYear()}`, 'i'),
      }),
    ).toBeInTheDocument();
  });

  // ── 8. Calendar navigation — previous month ───────────────────────────────────

  it('navigates to the previous month when the left-chevron button is clicked', async () => {
    const user = userEvent.setup();
    renderPage();

    // Wait for data to load before clicking nav
    await screen.findByText('90%');

    const now = new Date();
    const MONTH_NAMES = [
      'January', 'February', 'March', 'April', 'May', 'June',
      'July', 'August', 'September', 'October', 'November', 'December',
    ];
    const prevMonthIndex = now.getMonth() === 0 ? 11 : now.getMonth() - 1;
    const prevYear = now.getMonth() === 0 ? now.getFullYear() - 1 : now.getFullYear();
    const expectedMonthName = MONTH_NAMES[prevMonthIndex];

    const prevBtn = screen.getByRole('button', { name: /previous month/i });
    await user.click(prevBtn);

    expect(
      screen.getByRole('heading', {
        level: 3,
        name: new RegExp(`${expectedMonthName}.*${prevYear}`, 'i'),
      }),
    ).toBeInTheDocument();
  });

  // ── 9. Calendar — next month button disabled on current month ─────────────────

  it('disables the next-month button when viewing the current month', async () => {
    renderPage();

    // Wait for data to load
    await screen.findByText('90%');

    // The next-month button has disabled attribute when isCurrentMonth is true
    expect(screen.getByRole('button', { name: /next month/i })).toBeDisabled();
  });

  // ── 10. Calendar legend labels ────────────────────────────────────────────────

  it('renders all four calendar legend labels', async () => {
    renderPage();

    // The component renders a legend row with Present / Late / Absent / Excused.
    // Use getAllByText because these labels also appear in day-cell tooltip overlays
    // and in the AttendanceCard legend (Late, Absent), causing getByText to throw
    // "multiple elements found".
    await screen.findByText('90%'); // wait for data

    expect(screen.getAllByText('Present').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Late').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Absent').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Excused').length).toBeGreaterThanOrEqual(1);
  });

  // ── 11. Day cells are rendered ────────────────────────────────────────────────

  it('renders the day cells for the calendar grid', async () => {
    const { container } = renderPage();

    // Wait for content to load
    await screen.findByText('90%');

    // The calendar grid is a 7-column grid; day cells should be present
    const gridCols7 = container.querySelector('.grid-cols-7');
    expect(gridCols7).toBeInTheDocument();
  });

  // ── 12. Day-of-week headers ───────────────────────────────────────────────────

  it('renders all seven day-of-week headers (Mon–Sun)', async () => {
    renderPage();

    await screen.findByText('90%'); // wait for data

    for (const dayName of ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']) {
      expect(screen.getByText(dayName)).toBeInTheDocument();
    }
  });

  // ── 13. Empty state when total_days is 0 ─────────────────────────────────────

  it('shows the "No attendance records for this month" empty state when total_days is 0', async () => {
    mockedApi.get.mockResolvedValue({ data: MOCK_EMPTY_RESPONSE });
    renderPage();

    expect(
      await screen.findByText(/no attendance records for this month/i),
    ).toBeInTheDocument();
  });

  it('shows the empty-state hint about attendance import when total_days is 0', async () => {
    mockedApi.get.mockResolvedValue({ data: MOCK_EMPTY_RESPONSE });
    renderPage();

    expect(
      await screen.findByText(/attendance data will appear once imported/i),
    ).toBeInTheDocument();
  });

  // ── 14. API is called with the correct month param ────────────────────────────

  it('calls the attendance API with the current month string', async () => {
    renderPage();

    await screen.findByText('90%');

    const now = new Date();
    const expectedMonth = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;

    expect(mockedApi.get).toHaveBeenCalledWith(
      '/v1/student/attendance/',
      expect.objectContaining({ params: { month: expectedMonth } }),
    );
  });

  // ── 15. Month name in AttendanceCard title ────────────────────────────────────

  it('passes the correct month name to the AttendanceCard title', async () => {
    renderPage();

    const now = new Date();
    const MONTH_NAMES = [
      'January', 'February', 'March', 'April', 'May', 'June',
      'July', 'August', 'September', 'October', 'November', 'December',
    ];
    const currentMonthName = MONTH_NAMES[now.getMonth()];

    // AttendanceCard renders the title as an h3 like "April Attendance"
    expect(
      await screen.findByText(new RegExp(`${currentMonthName} Attendance`, 'i')),
    ).toBeInTheDocument();
  });
});
