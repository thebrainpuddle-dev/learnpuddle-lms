// src/components/analytics/ActivityHeatmap.test.tsx
//
// Unit tests for the ActivityHeatmap component.
// Covers rendering, data display, edge cases, and interaction.

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { format, subDays } from 'date-fns';
import { ActivityHeatmap, type HeatmapDay } from './ActivityHeatmap';

// ── Helpers ───────────────────────────────────────────────────────────────────

/** Return today's date as 'yyyy-MM-dd' string. */
function today(): string {
  return format(new Date(), 'yyyy-MM-dd');
}

/** Return a date N days ago as 'yyyy-MM-dd'. */
function daysAgo(n: number): string {
  return format(subDays(new Date(), n), 'yyyy-MM-dd');
}

const wrapper = ({ children }: { children: React.ReactNode }) => <>{children}</>;

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('ActivityHeatmap', () => {
  it('renders without crashing with empty data', () => {
    render(<ActivityHeatmap data={[]} />);
    // No legend labels
    expect(screen.getByText('Less')).toBeInTheDocument();
    expect(screen.getByText('More')).toBeInTheDocument();
  });

  it('renders title when provided', () => {
    render(<ActivityHeatmap data={[]} title="My Learning Activity" />);
    expect(screen.getByText('My Learning Activity')).toBeInTheDocument();
  });

  it('does not render title section when title prop is omitted', () => {
    const { queryByText } = render(<ActivityHeatmap data={[]} />);
    // No h3 title element
    expect(queryByText('active days')).not.toBeInTheDocument();
  });

  it('shows active days count in header', () => {
    const data: HeatmapDay[] = [
      { date: daysAgo(1), value: 50 },
      { date: daysAgo(2), value: 30 },
      { date: daysAgo(3), value: 0 },  // 0 value = not active
    ];
    render(<ActivityHeatmap data={data} title="Activity" />);
    expect(screen.getByText('2 active days')).toBeInTheDocument();
  });

  it('shows total value with metric label', () => {
    const data: HeatmapDay[] = [
      { date: daysAgo(1), value: 100 },
      { date: daysAgo(2), value: 200 },
    ];
    render(<ActivityHeatmap data={data} title="Activity" metricLabel="XP" />);
    expect(screen.getByText(/300.*XP/)).toBeInTheDocument();
  });

  it('uses default metricLabel "XP" when not specified', () => {
    const data: HeatmapDay[] = [{ date: daysAgo(1), value: 50 }];
    render(<ActivityHeatmap data={data} title="Activity" />);
    expect(screen.getByText(/50.*XP/)).toBeInTheDocument();
  });

  it('uses custom metricLabel when provided', () => {
    const data: HeatmapDay[] = [{ date: daysAgo(1), value: 10 }];
    render(<ActivityHeatmap data={data} title="Activity" metricLabel="lessons" />);
    expect(screen.getByText(/10.*lessons/)).toBeInTheDocument();
  });

  it('renders day cells with aria-labels for past dates', () => {
    const date = daysAgo(1);
    const data: HeatmapDay[] = [{ date, value: 75 }];
    render(<ActivityHeatmap data={data} />);

    // Past dates get the full aria-label
    const cell = screen.getByLabelText(`${date}: 75 XP`);
    expect(cell).toBeInTheDocument();
  });

  it('renders future dates with just the date string as aria-label', () => {
    // Pin "today" to a Wednesday so Thur/Fri/Sat in the same week are always
    // future cells, regardless of what day the test suite runs.
    // (On Saturdays the real endOfWeek === today → zero future days → test fails.)
    vi.useFakeTimers({ toFake: ['Date'] });
    vi.setSystemTime(new Date('2026-04-22')); // Wednesday

    try {
      // Future dates should be dimmed and have aria-label = dateStr only
      const data: HeatmapDay[] = [];
      const { container } = render(<ActivityHeatmap data={data} />);

      // Find any element with an aria-label that looks like a future date
      const futureCells = container.querySelectorAll('[aria-label]');
      const futureDateCells = Array.from(futureCells).filter(cell => {
        const label = cell.getAttribute('aria-label') ?? '';
        // Future cells have just the date (no metric value suffix)
        return /^\d{4}-\d{2}-\d{2}$/.test(label);
      });
      // Thu Apr-23, Fri Apr-24, Sat Apr-25 are all future relative to Wed Apr-22
      expect(futureDateCells.length).toBeGreaterThan(0);
    } finally {
      vi.useRealTimers();
    }
  });

  it('shows "No activity" in tooltip for zero-value cells', () => {
    const date = daysAgo(5);
    const data: HeatmapDay[] = [{ date, value: 0 }];
    render(<ActivityHeatmap data={data} />);

    const cell = screen.getByLabelText(`${date}: 0 XP`);
    fireEvent.mouseEnter(cell);

    expect(screen.getByText('No activity')).toBeInTheDocument();
  });

  it('shows value in tooltip for non-zero cells', () => {
    const date = daysAgo(3);
    const data: HeatmapDay[] = [{ date, value: 150 }];
    render(<ActivityHeatmap data={data} />);

    const cell = screen.getByLabelText(`${date}: 150 XP`);
    fireEvent.mouseEnter(cell);

    expect(screen.getByText(/150.*XP/)).toBeInTheDocument();
  });

  it('shows formatted date in tooltip', () => {
    const date = daysAgo(3);
    const data: HeatmapDay[] = [{ date, value: 50 }];
    render(<ActivityHeatmap data={data} />);

    const cell = screen.getByLabelText(`${date}: 50 XP`);
    fireEvent.mouseEnter(cell);

    // Tooltip should show a human-readable date (e.g. "Monday, 14 Apr 2026")
    // The exact format matches: EEEE, dd MMM yyyy
    const tooltipEl = document.querySelector('.fixed.z-50');
    expect(tooltipEl).not.toBeNull();
    expect(tooltipEl!.textContent).toMatch(/\w+, \d{2} \w+ \d{4}/);
  });

  it('hides tooltip on mouse leave', () => {
    const date = daysAgo(3);
    const data: HeatmapDay[] = [{ date, value: 50 }];
    render(<ActivityHeatmap data={data} />);

    const cell = screen.getByLabelText(`${date}: 50 XP`);
    fireEvent.mouseEnter(cell);
    expect(document.querySelector('.fixed.z-50')).not.toBeNull();

    fireEvent.mouseLeave(cell);
    expect(document.querySelector('.fixed.z-50')).toBeNull();
  });

  it('renders legend with 5 color swatches', () => {
    const { container } = render(<ActivityHeatmap data={[]} />);
    // Legend row has "Less" + 5 color divs + "More"
    const legend = container.querySelector('.flex.items-center.gap-1\\.5');
    expect(legend).not.toBeNull();
    const swatches = legend!.querySelectorAll('div');
    expect(swatches).toHaveLength(5);
  });

  it('renders month labels on x-axis', () => {
    render(<ActivityHeatmap data={[]} weeks={52} />);
    // Should have at least one month abbreviation visible
    const monthAbbrs = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                        'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const found = monthAbbrs.some(m => screen.queryByText(m) !== null);
    expect(found).toBe(true);
  });

  it('accepts custom weeks prop', () => {
    // Just smoke-test that it renders with fewer weeks
    const { container } = render(<ActivityHeatmap data={[]} weeks={12} />);
    // Grid should have week columns
    const grid = container.querySelector('.flex.gap-\\[3px\\]');
    expect(grid).not.toBeNull();
  });

  it('accepts custom colorScale prop', () => {
    const customColors: [string, string, string, string, string] = [
      '#fff', '#ffd', '#ffa', '#ff7', '#ff0',
    ];
    // Should render without errors
    const { container } = render(
      <ActivityHeatmap data={[]} colorScale={customColors} />,
    );
    expect(container.firstChild).not.toBeNull();
  });

  it('renders day labels (Mon, Wed, Fri) on y-axis', () => {
    render(<ActivityHeatmap data={[]} />);
    expect(screen.getByText('Mon')).toBeInTheDocument();
    expect(screen.getByText('Wed')).toBeInTheDocument();
    expect(screen.getByText('Fri')).toBeInTheDocument();
  });

  it('handles data with duplicate dates gracefully (last wins)', () => {
    // Map deduplication: duplicate dates overwrite earlier entries
    const date = daysAgo(2);
    const data: HeatmapDay[] = [
      { date, value: 10 },
      { date, value: 99 }, // should win
    ];
    render(<ActivityHeatmap data={data} />);
    const cell = screen.getByLabelText(`${date}: 99 XP`);
    expect(cell).toBeInTheDocument();
  });

  it('applies custom className to root element', () => {
    const { container } = render(
      <ActivityHeatmap data={[]} className="my-custom-class" />,
    );
    expect(container.firstChild).toHaveClass('my-custom-class');
  });
});

// ── getLevel helper (extracted for unit testing) ──────────────────────────────

describe('ActivityHeatmap color levels', () => {
  // We test the visual output by checking the backgroundColor on day cells
  it('level 0 color applied to zero-value cells', () => {
    const date = daysAgo(1);
    const data: HeatmapDay[] = [{ date, value: 0 }];
    render(<ActivityHeatmap data={data} />);

    const cell = screen.getByLabelText(`${date}: 0 XP`);
    // Level 0 = '#f0fdf4'
    expect(cell).toHaveStyle({ backgroundColor: '#f0fdf4' });
  });

  it('high-value cells get darker color', () => {
    // value=1000, max=1000 → ratio=1.0 → level 4
    const date = daysAgo(1);
    const data: HeatmapDay[] = [{ date, value: 1000 }];
    render(<ActivityHeatmap data={data} />);

    const cell = screen.getByLabelText(`${date}: 1,000 XP`);
    // Level 4 = '#14532d'
    expect(cell).toHaveStyle({ backgroundColor: '#14532d' });
  });
});
