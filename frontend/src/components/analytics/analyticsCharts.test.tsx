// src/components/analytics/analyticsCharts.test.tsx
//
// Tests for DeadlineAdherenceChart, ApprovalTrendsChart, CourseEffectivenessChart.
//
// All three components use @tanstack/react-query to fetch data.
// Coverage:
//   - Loading state (spinner visible, headline stat shows "—" where applicable)
//   - Error state (error message visible, headline stat shows "—" where applicable)
//   - Empty-data state (empty-state message visible)
//   - Populated-data state (chart rendered, headline stat accurate)
//   - onViewDetails callback
//   - difficultyColor classification (CourseEffectivenessChart legend)
//
// recharts has no SVG layout in jsdom — each chart type is stubbed so tests
// don't depend on SVG rendering (same pattern as SkillRadarPage.test.tsx).

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { DeadlineAdherenceChart } from './DeadlineAdherenceChart';
import { ApprovalTrendsChart } from './ApprovalTrendsChart';
import { CourseEffectivenessChart } from './CourseEffectivenessChart';
import { adminReportsService } from '../../services/adminReportsService';
import type {
  DeadlineAdherencePoint,
  ApprovalTrendsPoint,
  CourseEffectivenessItem,
} from '../../services/adminReportsService';

// ── Mock recharts (no SVG layout in jsdom) ────────────────────────────────────

vi.mock('recharts', () => {
  const Stub = ({ children }: { children?: React.ReactNode }) => (
    <div data-testid="recharts-stub">{children}</div>
  );
  return {
    AreaChart: Stub,
    BarChart: Stub,
    ScatterChart: Stub,
    Area: () => null,
    Bar: ({ dataKey }: { dataKey: string }) => (
      <div data-testid={`bar-${dataKey}`}>{dataKey}</div>
    ),
    Scatter: ({ data }: { data?: unknown[] }) => (
      <div data-testid="scatter" data-count={data?.length ?? 0} />
    ),
    XAxis: () => null,
    YAxis: () => null,
    ZAxis: () => null,
    CartesianGrid: () => null,
    Tooltip: () => null,
    Legend: () => <div data-testid="recharts-legend" />,
    Cell: () => null,
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
      <div data-testid="responsive-container">{children}</div>
    ),
  };
});

// ── Mock adminReportsService ──────────────────────────────────────────────────

vi.mock('../../services/adminReportsService', () => ({
  adminReportsService: {
    deadlineAdherence: vi.fn(),
    approvalTrends: vi.fn(),
    courseEffectiveness: vi.fn(),
  },
}));

const mockedDeadlineAdherence = vi.mocked(adminReportsService.deadlineAdherence);
const mockedApprovalTrends = vi.mocked(adminReportsService.approvalTrends);
const mockedCourseEffectiveness = vi.mocked(adminReportsService.courseEffectiveness);

// ── Fixtures ──────────────────────────────────────────────────────────────────

const DEADLINE_POINTS: DeadlineAdherencePoint[] = [
  { period: 'Jan 2026', adherencePercent: 80.0, totalTeachers: 10, onTime: 8, late: 2 },
  { period: 'Feb 2026', adherencePercent: 90.0, totalTeachers: 10, onTime: 9, late: 1 },
];

const APPROVAL_POINTS: ApprovalTrendsPoint[] = [
  { period: 'Jan 2026', approved: 15, rejected: 3, pending: 2 },
  { period: 'Feb 2026', approved: 20, rejected: 1, pending: 5 },
];

const EFFECTIVENESS_ITEMS: CourseEffectivenessItem[] = [
  { courseId: 'c1', courseName: 'Course Alpha', completionRate: 85.0, avgScore: 88.0, enrolledCount: 20 },
  { courseId: 'c2', courseName: 'Course Beta',  completionRate: 45.0, avgScore: 40.0, enrolledCount: 10 },
];

// ── Test harness helpers ──────────────────────────────────────────────────────

function makeQC() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function wrap(ui: React.ReactElement, qc = makeQC()) {
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// DeadlineAdherenceChart
// ─────────────────────────────────────────────────────────────────────────────

describe('DeadlineAdherenceChart', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('renders the card heading', async () => {
    mockedDeadlineAdherence.mockResolvedValue([]);
    wrap(<DeadlineAdherenceChart />);
    expect(screen.getByText('Deadline Adherence')).toBeInTheDocument();
  });

  // ── Loading state ─────────────────────────────────────────────────────────

  it('shows a loading spinner while fetching', async () => {
    mockedDeadlineAdherence.mockReturnValue(new Promise(() => {})); // never resolves
    wrap(<DeadlineAdherenceChart />);

    await waitFor(() => {
      expect(document.querySelector('.animate-spin')).toBeTruthy();
    });
  });

  it('headline stat shows "—" during loading', async () => {
    mockedDeadlineAdherence.mockReturnValue(new Promise(() => {}));
    wrap(<DeadlineAdherenceChart />);

    // The stat placeholder shows "—" while in-flight
    await waitFor(() => {
      expect(screen.getByText('—')).toBeInTheDocument();
    });
  });

  // ── Error state ───────────────────────────────────────────────────────────

  it('shows an error message when the fetch fails', async () => {
    mockedDeadlineAdherence.mockRejectedValue(new Error('Network error'));
    wrap(<DeadlineAdherenceChart />);

    await waitFor(() => {
      expect(screen.getByText(/failed to load deadline data/i)).toBeInTheDocument();
    });
  });

  it('headline stat shows "—" on error', async () => {
    mockedDeadlineAdherence.mockRejectedValue(new Error('Network error'));
    wrap(<DeadlineAdherenceChart />);

    await waitFor(() => {
      expect(screen.getByText('—')).toBeInTheDocument();
    });
    // The error message, not a percentage, is also visible
    expect(screen.queryByText(/%$/)).toBeNull();
  });

  // ── Empty state ───────────────────────────────────────────────────────────

  it('shows empty-state message when no data is returned', async () => {
    mockedDeadlineAdherence.mockResolvedValue([]);
    wrap(<DeadlineAdherenceChart />);

    await waitFor(() => {
      expect(screen.getByText(/no deadline data yet/i)).toBeInTheDocument();
    });
  });

  it('does not render the chart container when data is empty', async () => {
    mockedDeadlineAdherence.mockResolvedValue([]);
    wrap(<DeadlineAdherenceChart />);

    await waitFor(() => {
      expect(screen.getByText(/no deadline data yet/i)).toBeInTheDocument();
    });
    expect(screen.queryByTestId('responsive-container')).toBeNull();
  });

  // ── Data state ────────────────────────────────────────────────────────────

  it('renders the chart container when data is present', async () => {
    mockedDeadlineAdherence.mockResolvedValue(DEADLINE_POINTS);
    wrap(<DeadlineAdherenceChart />);

    await waitFor(() => {
      expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
    });
  });

  it('headline stat shows the latest adherence percentage', async () => {
    mockedDeadlineAdherence.mockResolvedValue(DEADLINE_POINTS);
    wrap(<DeadlineAdherenceChart />);

    // Latest point is Feb 2026 → 90%
    await waitFor(() => {
      expect(screen.getByText('90%')).toBeInTheDocument();
    });
  });

  it('does not show the loading spinner once data has loaded', async () => {
    mockedDeadlineAdherence.mockResolvedValue(DEADLINE_POINTS);
    wrap(<DeadlineAdherenceChart />);

    await waitFor(() => {
      expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
    });
    expect(document.querySelector('.animate-spin')).toBeNull();
  });

  // ── onViewDetails callback ────────────────────────────────────────────────

  it('calls onViewDetails when "View Details" button is clicked', async () => {
    mockedDeadlineAdherence.mockResolvedValue([]);
    const onViewDetails = vi.fn();
    wrap(<DeadlineAdherenceChart onViewDetails={onViewDetails} />);

    const btn = await screen.findByRole('button', { name: /view details/i });
    await userEvent.click(btn);

    expect(onViewDetails).toHaveBeenCalledOnce();
  });

  it('does not render "View Details" button when prop is omitted', async () => {
    mockedDeadlineAdherence.mockResolvedValue([]);
    wrap(<DeadlineAdherenceChart />);

    await waitFor(() => {
      expect(screen.getByText(/no deadline data yet/i)).toBeInTheDocument();
    });
    expect(screen.queryByRole('button', { name: /view details/i })).toBeNull();
  });

  // ── stat label ────────────────────────────────────────────────────────────

  it('renders the stat label "current adherence rate"', async () => {
    mockedDeadlineAdherence.mockResolvedValue([]);
    wrap(<DeadlineAdherenceChart />);

    await waitFor(() => {
      expect(screen.getByText('current adherence rate')).toBeInTheDocument();
    });
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// ApprovalTrendsChart
// ─────────────────────────────────────────────────────────────────────────────

describe('ApprovalTrendsChart', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('renders the card heading "Skip Request Trends"', async () => {
    mockedApprovalTrends.mockResolvedValue([]);
    wrap(<ApprovalTrendsChart />);
    expect(screen.getByText('Skip Request Trends')).toBeInTheDocument();
  });

  // ── Loading state ─────────────────────────────────────────────────────────

  it('shows a loading spinner while fetching', async () => {
    mockedApprovalTrends.mockReturnValue(new Promise(() => {}));
    wrap(<ApprovalTrendsChart />);

    await waitFor(() => {
      expect(document.querySelector('.animate-spin')).toBeTruthy();
    });
  });

  it('headline stat shows "—" during loading', async () => {
    mockedApprovalTrends.mockReturnValue(new Promise(() => {}));
    wrap(<ApprovalTrendsChart />);

    await waitFor(() => {
      expect(screen.getByText('—')).toBeInTheDocument();
    });
  });

  it('subtitle shows "overall approval rate" (no request count) during loading', async () => {
    mockedApprovalTrends.mockReturnValue(new Promise(() => {}));
    wrap(<ApprovalTrendsChart />);

    await waitFor(() => {
      expect(screen.getByText('—')).toBeInTheDocument();
    });
    // Subtitle should not contain "(N total requests)" while loading
    expect(screen.getByText('overall approval rate')).toBeInTheDocument();
    expect(screen.queryByText(/total requests/)).toBeNull();
  });

  // ── Error state ───────────────────────────────────────────────────────────

  it('shows an error message when the fetch fails', async () => {
    mockedApprovalTrends.mockRejectedValue(new Error('Network error'));
    wrap(<ApprovalTrendsChart />);

    await waitFor(() => {
      expect(screen.getByText(/failed to load skip request data/i)).toBeInTheDocument();
    });
  });

  it('headline stat shows "—" on error', async () => {
    mockedApprovalTrends.mockRejectedValue(new Error('Network error'));
    wrap(<ApprovalTrendsChart />);

    await waitFor(() => {
      expect(screen.getByText('—')).toBeInTheDocument();
    });
  });

  it('subtitle shows "overall approval rate" (no request count) on error', async () => {
    mockedApprovalTrends.mockRejectedValue(new Error('Network error'));
    wrap(<ApprovalTrendsChart />);

    await waitFor(() => {
      expect(screen.getByText('—')).toBeInTheDocument();
    });
    expect(screen.getByText('overall approval rate')).toBeInTheDocument();
    expect(screen.queryByText(/total requests/)).toBeNull();
  });

  // ── Empty state ───────────────────────────────────────────────────────────

  it('shows empty-state message when no data is returned', async () => {
    mockedApprovalTrends.mockResolvedValue([]);
    wrap(<ApprovalTrendsChart />);

    await waitFor(() => {
      expect(screen.getByText(/no skip request data yet/i)).toBeInTheDocument();
    });
  });

  // ── Data state ────────────────────────────────────────────────────────────

  it('renders the chart container when data is present', async () => {
    mockedApprovalTrends.mockResolvedValue(APPROVAL_POINTS);
    wrap(<ApprovalTrendsChart />);

    await waitFor(() => {
      expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
    });
  });

  it('headline stat shows the computed approval rate percentage', async () => {
    // Points: approved=35, rejected=4, pending=7 → total=46
    // approvalRate = Math.round(35/46*100) = 76%
    mockedApprovalTrends.mockResolvedValue(APPROVAL_POINTS);
    wrap(<ApprovalTrendsChart />);

    const totalApproved = APPROVAL_POINTS.reduce((s, d) => s + d.approved, 0); // 35
    const totalAll = APPROVAL_POINTS.reduce(
      (s, d) => s + d.approved + d.rejected + d.pending,
      0,
    ); // 46
    const expected = `${Math.round((totalApproved / totalAll) * 100)}%`;

    await waitFor(() => {
      expect(screen.getByText(expected)).toBeInTheDocument();
    });
  });

  it('subtitle shows total request count when data is loaded', async () => {
    mockedApprovalTrends.mockResolvedValue(APPROVAL_POINTS);
    wrap(<ApprovalTrendsChart />);

    const totalAll = APPROVAL_POINTS.reduce(
      (s, d) => s + d.approved + d.rejected + d.pending,
      0,
    ); // 46

    await waitFor(() => {
      expect(
        screen.getByText(new RegExp(`overall approval rate \\(${totalAll} total requests\\)`)),
      ).toBeInTheDocument();
    });
  });

  it('renders Approved, Rejected and Pending bars via recharts stubs', async () => {
    mockedApprovalTrends.mockResolvedValue(APPROVAL_POINTS);
    wrap(<ApprovalTrendsChart />);

    await waitFor(() => {
      expect(screen.getByTestId('bar-Approved')).toBeInTheDocument();
      expect(screen.getByTestId('bar-Rejected')).toBeInTheDocument();
      expect(screen.getByTestId('bar-Pending')).toBeInTheDocument();
    });
  });

  // ── onViewDetails callback ────────────────────────────────────────────────

  it('calls onViewDetails when "View Details" button is clicked', async () => {
    mockedApprovalTrends.mockResolvedValue([]);
    const onViewDetails = vi.fn();
    wrap(<ApprovalTrendsChart onViewDetails={onViewDetails} />);

    const btn = await screen.findByRole('button', { name: /view details/i });
    await userEvent.click(btn);

    expect(onViewDetails).toHaveBeenCalledOnce();
  });

  it('does not render "View Details" button when prop is omitted', async () => {
    mockedApprovalTrends.mockResolvedValue([]);
    wrap(<ApprovalTrendsChart />);

    await waitFor(() => {
      expect(screen.getByText(/no skip request data yet/i)).toBeInTheDocument();
    });
    expect(screen.queryByRole('button', { name: /view details/i })).toBeNull();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// CourseEffectivenessChart
// ─────────────────────────────────────────────────────────────────────────────

describe('CourseEffectivenessChart', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('renders the card heading "Course Effectiveness"', async () => {
    mockedCourseEffectiveness.mockResolvedValue([]);
    wrap(<CourseEffectivenessChart />);
    expect(screen.getByText('Course Effectiveness')).toBeInTheDocument();
  });

  // ── Loading state ─────────────────────────────────────────────────────────

  it('shows a loading spinner while fetching', async () => {
    mockedCourseEffectiveness.mockReturnValue(new Promise(() => {}));
    wrap(<CourseEffectivenessChart />);

    await waitFor(() => {
      expect(document.querySelector('.animate-spin')).toBeTruthy();
    });
  });

  // ── Error state ───────────────────────────────────────────────────────────

  it('shows an error message when the fetch fails', async () => {
    mockedCourseEffectiveness.mockRejectedValue(new Error('Network error'));
    wrap(<CourseEffectivenessChart />);

    await waitFor(() => {
      expect(screen.getByText(/failed to load course data/i)).toBeInTheDocument();
    });
  });

  // ── Empty state ───────────────────────────────────────────────────────────

  it('shows empty-state message when no data is returned', async () => {
    mockedCourseEffectiveness.mockResolvedValue([]);
    wrap(<CourseEffectivenessChart />);

    await waitFor(() => {
      expect(screen.getByText(/no course data yet/i)).toBeInTheDocument();
    });
  });

  // ── Legend ────────────────────────────────────────────────────────────────

  it('renders the difficulty-classification legend labels', async () => {
    mockedCourseEffectiveness.mockResolvedValue([]);
    wrap(<CourseEffectivenessChart />);

    await waitFor(() => {
      expect(screen.getByText(/easy \(high completion \+ score\)/i)).toBeInTheDocument();
      expect(screen.getByText(/balanced/i)).toBeInTheDocument();
      expect(screen.getByText(/challenging \(low completion or score\)/i)).toBeInTheDocument();
    });
  });

  // ── Data state ────────────────────────────────────────────────────────────

  it('renders the chart container when data is present', async () => {
    mockedCourseEffectiveness.mockResolvedValue(EFFECTIVENESS_ITEMS);
    wrap(<CourseEffectivenessChart />);

    await waitFor(() => {
      expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
    });
  });

  it('passes all data points to the Scatter stub', async () => {
    mockedCourseEffectiveness.mockResolvedValue(EFFECTIVENESS_ITEMS);
    wrap(<CourseEffectivenessChart />);

    await waitFor(() => {
      const scatter = screen.getByTestId('scatter');
      expect(scatter).toHaveAttribute('data-count', `${EFFECTIVENESS_ITEMS.length}`);
    });
  });

  it('does not render chart when data array is empty', async () => {
    mockedCourseEffectiveness.mockResolvedValue([]);
    wrap(<CourseEffectivenessChart />);

    await waitFor(() => {
      expect(screen.getByText(/no course data yet/i)).toBeInTheDocument();
    });
    expect(screen.queryByTestId('responsive-container')).toBeNull();
  });

  it('does not show a loading spinner after data loads', async () => {
    mockedCourseEffectiveness.mockResolvedValue(EFFECTIVENESS_ITEMS);
    wrap(<CourseEffectivenessChart />);

    await waitFor(() => {
      expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
    });
    expect(document.querySelector('.animate-spin')).toBeNull();
  });

  // ── onViewDetails callback ────────────────────────────────────────────────

  it('calls onViewDetails when "View Details" button is clicked', async () => {
    mockedCourseEffectiveness.mockResolvedValue([]);
    const onViewDetails = vi.fn();
    wrap(<CourseEffectivenessChart onViewDetails={onViewDetails} />);

    const btn = await screen.findByRole('button', { name: /view details/i });
    await userEvent.click(btn);

    expect(onViewDetails).toHaveBeenCalledOnce();
  });

  it('does not render "View Details" button when prop is omitted', async () => {
    mockedCourseEffectiveness.mockResolvedValue([]);
    wrap(<CourseEffectivenessChart />);

    await waitFor(() => {
      expect(screen.getByText(/no course data yet/i)).toBeInTheDocument();
    });
    expect(screen.queryByRole('button', { name: /view details/i })).toBeNull();
  });
});
