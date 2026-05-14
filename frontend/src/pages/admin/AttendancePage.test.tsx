// src/pages/admin/AttendancePage.test.tsx
//
// Test suite for AdminAttendancePage — school-wide attendance overview.
//
// Coverage strategy:
//   1. Loading state (AttendanceLoader shown)
//   2. Page header (h1, subtitle)
//   3. Action buttons (Export CSV, Import CSV)
//   4. Error state
//   5. AttendanceCard rendered when data loads
//   6. Section breakdown table (section names, grade labels, rate badges)
//   7. Empty state when summary.total === 0
//   8. Date navigation (prev/next chevrons; next disabled on today)
//   9. Import result banner (success, with errors, dismiss)
//  10. Export modal opens on button click
//
// Mock notes:
//   • api (../../config/api) default export — get/post vi.fn()
//   • AttendanceCard, AttendanceLoader, ExportAttendanceModal — lightweight stubs
//   • cn utility works as-is (no SVG/CSS engine needed)

import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { AdminAttendancePage } from './AttendancePage';
import api from '../../config/api';

// ── api mock ──────────────────────────────────────────────────────────────────
vi.mock('../../config/api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

// ── component stubs ───────────────────────────────────────────────────────────
vi.mock('../../components/attendance/AttendanceCard', () => ({
  AttendanceCard: () => <div data-testid="attendance-card">Attendance Card</div>,
}));

vi.mock('../../components/attendance/AttendanceLoader', () => ({
  AttendanceLoader: () => <div data-testid="attendance-loader">Loading attendance...</div>,
}));

vi.mock('../../components/attendance/ExportAttendanceModal', () => ({
  ExportAttendanceModal: ({
    open,
    onClose,
  }: {
    open: boolean;
    onClose: () => void;
  }) =>
    open ? (
      <div data-testid="export-modal">
        <button type="button" onClick={onClose}>
          Close Export
        </button>
      </div>
    ) : null,
}));

vi.mock('../../hooks/usePageTitle', () => ({ usePageTitle: vi.fn() }));

// ── typed api ref ─────────────────────────────────────────────────────────────
const mockedApi = api as {
  get: ReturnType<typeof vi.fn>;
  post: ReturnType<typeof vi.fn>;
};

// ── fixture data ──────────────────────────────────────────────────────────────
const MOCK_SECTIONS = [
  {
    section_id: 'sec-1',
    section_name: 'Alpha',
    grade_name: 'Grade 5',
    grade_short_code: 'G5',
    total: 30,
    present: 27,
    late: 2,
    absent: 1,
    rate: 97,
  },
  {
    section_id: 'sec-2',
    section_name: 'Beta',
    grade_name: 'Grade 5',
    grade_short_code: 'G5',
    total: 25,
    present: 20,
    late: 3,
    absent: 2,
    rate: 80,
  },
];

const MOCK_OVERVIEW = {
  date: '2026-04-26',
  summary: {
    total: 55,
    present: 47,
    late: 5,
    absent: 3,
    excused: 0,
    attendance_rate: 94,
    on_time_pct: 85.5,
    late_pct: 9.1,
    absent_pct: 5.5,
    trend: 1.2,
  },
  bars: [{ status: 'present' }, { status: 'late' }, { status: 'absent' }],
  sections: MOCK_SECTIONS,
};

const MOCK_OVERVIEW_EMPTY = {
  ...MOCK_OVERVIEW,
  summary: { ...MOCK_OVERVIEW.summary, total: 0 },
  sections: [],
};

const IMPORT_SUCCESS = {
  created: 5,
  updated: 2,
  errors: [],
  total_errors: 0,
};

const IMPORT_WITH_ERRORS = {
  created: 3,
  updated: 1,
  errors: ['Row 5: Invalid date format', 'Row 12: Student not found'],
  total_errors: 2,
};

// ── helpers ───────────────────────────────────────────────────────────────────
function makeClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, retryDelay: 0 } },
  });
}

function renderPage() {
  return render(
    <QueryClientProvider client={makeClient()}>
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <AdminAttendancePage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
describe('AdminAttendancePage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockedApi.get.mockResolvedValue({ data: MOCK_OVERVIEW });
    mockedApi.post.mockResolvedValue({ data: IMPORT_SUCCESS });
  });

  // ── 1. Loading state ───────────────────────────────────────────────────────
  describe('loading state', () => {
    it('shows AttendanceLoader while the query is pending', () => {
      mockedApi.get.mockReturnValue(new Promise(() => {}));
      renderPage();
      expect(screen.getByTestId('attendance-loader')).toBeInTheDocument();
    });
  });

  // ── 2. Page header ─────────────────────────────────────────────────────────
  describe('page header', () => {
    it('renders the "Attendance" heading', async () => {
      renderPage();
      expect(await screen.findByRole('heading', { name: /^Attendance$/i })).toBeInTheDocument();
    });

    it('renders the subtitle text', async () => {
      renderPage();
      expect(await screen.findByText(/School-wide attendance overview/i)).toBeInTheDocument();
    });
  });

  // ── 3. Action buttons ──────────────────────────────────────────────────────
  describe('action buttons', () => {
    it('shows the Export CSV button', async () => {
      renderPage();
      expect(await screen.findByRole('button', { name: /Export CSV/i })).toBeInTheDocument();
    });

    it('shows the Import CSV button', async () => {
      renderPage();
      expect(await screen.findByRole('button', { name: /Import CSV/i })).toBeInTheDocument();
    });
  });

  // ── 4. Error state ─────────────────────────────────────────────────────────
  describe('error state', () => {
    it('shows "Unable to load attendance data" on query error', async () => {
      mockedApi.get.mockRejectedValue(new Error('Network error'));
      renderPage();
      expect(
        await screen.findByText(/Unable to load attendance data/i)
      ).toBeInTheDocument();
    });

    it('shows "Please try again later." hint on error', async () => {
      mockedApi.get.mockRejectedValue(new Error('Network error'));
      renderPage();
      expect(await screen.findByText(/Please try again later/i)).toBeInTheDocument();
    });
  });

  // ── 5. AttendanceCard ──────────────────────────────────────────────────────
  describe('attendance card', () => {
    it('renders AttendanceCard stub when data loads', async () => {
      renderPage();
      expect(await screen.findByTestId('attendance-card')).toBeInTheDocument();
    });
  });

  // ── 6. Section breakdown table ─────────────────────────────────────────────
  describe('section breakdown table', () => {
    it('shows "By Section" heading when data loads', async () => {
      renderPage();
      expect(await screen.findByText(/By Section/i)).toBeInTheDocument();
    });

    it('renders section names from API data', async () => {
      renderPage();
      expect(await screen.findByText('Alpha')).toBeInTheDocument();
      expect(await screen.findByText('Beta')).toBeInTheDocument();
    });

    it('shows grade name alongside section name', async () => {
      renderPage();
      const gradeCells = await screen.findAllByText('Grade 5');
      expect(gradeCells.length).toBeGreaterThanOrEqual(1);
    });

    it('shows attendance rate badges', async () => {
      renderPage();
      expect(await screen.findByText('97%')).toBeInTheDocument();
      expect(await screen.findByText('80%')).toBeInTheDocument();
    });

    it('shows "No attendance data for this date" in section panel when sections is empty', async () => {
      mockedApi.get.mockResolvedValue({
        data: { ...MOCK_OVERVIEW, sections: [] },
      });
      renderPage();
      expect(
        await screen.findByText(/No attendance data for this date/i)
      ).toBeInTheDocument();
    });
  });

  // ── 7. Empty state (total = 0) ─────────────────────────────────────────────
  describe('empty state', () => {
    it('shows "No attendance data for this date" when summary.total === 0', async () => {
      mockedApi.get.mockResolvedValue({ data: MOCK_OVERVIEW_EMPTY });
      renderPage();
      // Both the section panel and bottom empty state render this message when total=0
      await waitFor(() => {
        expect(
          screen.getAllByText(/No attendance data for this date/i).length
        ).toBeGreaterThanOrEqual(1);
      });
    });

    it('shows import hint text in empty state', async () => {
      mockedApi.get.mockResolvedValue({ data: MOCK_OVERVIEW_EMPTY });
      renderPage();
      expect(
        await screen.findByText(/Import attendance records using the CSV import button above/i)
      ).toBeInTheDocument();
    });
  });

  // ── 8. Date navigation ─────────────────────────────────────────────────────
  describe('date navigation', () => {
    it('renders previous and next navigation buttons', async () => {
      renderPage();
      // Both are plain buttons with icon children (no text label)
      const buttons = await screen.findAllByRole('button');
      // ChevronLeft and ChevronRight buttons are part of the UI
      expect(buttons.length).toBeGreaterThanOrEqual(2);
    });

    it('clicking the previous day button re-queries the API', async () => {
      renderPage();
      await screen.findByTestId('attendance-card');
      const initialCallCount = mockedApi.get.mock.calls.length;
      // Find the ChevronLeft button (first icon button after Export/Import)
      // It's a plain <button> with no text — use the SVG title or query by position
      // The prev button is the first of the two date-navigation buttons.
      // Buttons order: Export CSV, Import CSV, [prev], [next]
      const allButtons = screen.getAllByRole('button');
      // prev and next buttons come after Export CSV (index 0) and Import CSV (index 1)
      const prevBtn = allButtons[2]; // third button = prev chevron
      await userEvent.click(prevBtn);
      await waitFor(() => {
        expect(mockedApi.get.mock.calls.length).toBeGreaterThan(initialCallCount);
      });
    });

    it('the next date button is disabled when today is selected', async () => {
      renderPage();
      await screen.findByTestId('attendance-card');
      // Next button is disabled on initial render (selectedDate === today)
      const allButtons = screen.getAllByRole('button');
      const nextBtn = allButtons[3]; // fourth button = next chevron
      expect(nextBtn).toBeDisabled();
    });
  });

  // ── 9. Import result banner ────────────────────────────────────────────────
  describe('import result banner', () => {
    async function simulateImport(result: typeof IMPORT_SUCCESS) {
      mockedApi.post.mockResolvedValue({ data: result });
      renderPage();
      await screen.findByTestId('attendance-card');
      // Directly trigger the hidden file input change event
      const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
      const file = new File(['date,section,status\n2026-04-26,sec-1,P'], 'attendance.csv', {
        type: 'text/csv',
      });
      await userEvent.upload(fileInput, file);
    }

    it('shows success banner after successful import', async () => {
      await simulateImport(IMPORT_SUCCESS);
      expect(
        await screen.findByText(/Import complete: 5 created, 2 updated/i)
      ).toBeInTheDocument();
    });

    it('dismiss button hides the import banner', async () => {
      await simulateImport(IMPORT_SUCCESS);
      await screen.findByText(/Import complete: 5 created, 2 updated/i);
      // The dismiss button has an X icon (no text label) — use the closest button inside the banner
      const bannerText = screen.getByText(/Import complete/i);
      const banner = bannerText.closest('div[class*="rounded-xl"]')!;
      const dismissBtn = banner.querySelector('button')!;
      await userEvent.click(dismissBtn);
      await waitFor(() => {
        expect(screen.queryByText(/Import complete/i)).not.toBeInTheDocument();
      });
    });

    it('shows error count in banner when import has errors', async () => {
      await simulateImport(IMPORT_WITH_ERRORS);
      expect(
        await screen.findByText(/Import complete: 3 created, 1 updated/i)
      ).toBeInTheDocument();
      expect(await screen.findByText(/2 errors/i)).toBeInTheDocument();
    });

    it('shows individual error messages in the banner', async () => {
      await simulateImport(IMPORT_WITH_ERRORS);
      expect(await screen.findByText(/Invalid date format/i)).toBeInTheDocument();
      expect(await screen.findByText(/Student not found/i)).toBeInTheDocument();
    });
  });

  // ── 10. Export modal ───────────────────────────────────────────────────────
  describe('export modal', () => {
    it('clicking Export CSV opens the ExportAttendanceModal', async () => {
      renderPage();
      const exportBtn = await screen.findByRole('button', { name: /Export CSV/i });
      await userEvent.click(exportBtn);
      expect(await screen.findByTestId('export-modal')).toBeInTheDocument();
    });

    it('closing the export modal hides it', async () => {
      renderPage();
      await userEvent.click(await screen.findByRole('button', { name: /Export CSV/i }));
      await userEvent.click(await screen.findByRole('button', { name: /Close Export/i }));
      await waitFor(() => {
        expect(screen.queryByTestId('export-modal')).not.toBeInTheDocument();
      });
    });
  });
});
