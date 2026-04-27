// src/components/analytics/ActivityHeatmap.tsx
//
// GitHub-style activity heatmap — shows daily XP / activity for the past year.
// Pure CSS/React implementation; no Nivo or extra dependency required.
//
// Usage:
//   <ActivityHeatmap data={dailyData} title="Learning Activity" />
//   where dailyData is: { date: 'YYYY-MM-DD'; value: number }[]

import React, { useMemo } from 'react';
import {
  startOfWeek,
  endOfWeek,
  eachDayOfInterval,
  subDays,
  format,
  getDay,
  startOfDay,
  parseISO,
  isValid,
  eachWeekOfInterval,
} from 'date-fns';
import { cn } from '../../lib/utils';

// ── Types ─────────────────────────────────────────────────────────────────────

export interface HeatmapDay {
  /** ISO date string: 'YYYY-MM-DD' */
  date: string;
  /** Numeric value (XP earned, content pieces completed, etc.) */
  value: number;
}

interface ActivityHeatmapProps {
  /** Daily activity data points */
  data: HeatmapDay[];
  /** Optional title displayed above the heatmap */
  title?: string;
  /** Label for the metric (shown in tooltip) */
  metricLabel?: string;
  /** How many weeks to display (default: 52 = one year) */
  weeks?: number;
  /** Custom colour scale: 5-element array from lowest to highest */
  colorScale?: [string, string, string, string, string];
  className?: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const DEFAULT_COLORS: [string, string, string, string, string] = [
  '#f0fdf4', // level 0 — no activity
  '#bbf7d0', // level 1 — low
  '#4ade80', // level 2 — medium-low
  '#16a34a', // level 3 — medium-high
  '#14532d', // level 4 — high
];

const MONTH_ABBR = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const DAY_ABBR = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const DISPLAYED_DAYS = [1, 3, 5]; // Mon, Wed, Fri indices to label on Y axis
/** Width of each week column in pixels — used for month-label X positions. */
const CELL_COLUMN_WIDTH = 13;

function getLevel(value: number, max: number): 0 | 1 | 2 | 3 | 4 {
  if (value === 0 || max === 0) return 0;
  const ratio = value / max;
  if (ratio < 0.15) return 1;
  if (ratio < 0.40) return 2;
  if (ratio < 0.70) return 3;
  return 4;
}

// ── Component ─────────────────────────────────────────────────────────────────

export const ActivityHeatmap: React.FC<ActivityHeatmapProps> = ({
  data,
  title,
  metricLabel = 'XP',
  weeks = 52,
  colorScale = DEFAULT_COLORS,
  className,
}) => {
  const [tooltip, setTooltip] = React.useState<{
    date: string;
    value: number;
    x: number;
    y: number;
  } | null>(null);

  // Build a date → value lookup
  const lookup = useMemo(() => {
    const map = new Map<string, number>();
    for (const d of data) {
      map.set(d.date, d.value);
    }
    return map;
  }, [data]);

  // Compute date range: last `weeks` complete weeks + current partial week.
  // Memoize on `weeks` so the dates are stable references across re-renders.
  const today = useMemo(() => startOfDay(new Date()), []);
  const rangeEnd = useMemo(() => endOfWeek(today, { weekStartsOn: 0 }), [today]);
  const rangeStart = useMemo(
    () => startOfWeek(subDays(today, (weeks - 1) * 7), { weekStartsOn: 0 }),
    [today, weeks],
  );

  // All weeks in range
  const weekStarts = useMemo(
    () => eachWeekOfInterval({ start: rangeStart, end: rangeEnd }, { weekStartsOn: 0 }),
    [rangeStart, rangeEnd],
  );

  // All days in range (for max calculation)
  const allDays = useMemo(
    () => eachDayOfInterval({ start: rangeStart, end: rangeEnd }),
    [rangeStart, rangeEnd],
  );

  const max = useMemo(() => {
    let m = 0;
    for (const d of allDays) {
      const v = lookup.get(format(d, 'yyyy-MM-dd')) ?? 0;
      if (v > m) m = v;
    }
    return m;
  }, [allDays, lookup]);

  const totalValue = useMemo(() => {
    let sum = 0;
    for (const [, v] of lookup) sum += v;
    return sum;
  }, [lookup]);

  const activeDays = useMemo(() => {
    let count = 0;
    for (const d of allDays) {
      if ((lookup.get(format(d, 'yyyy-MM-dd')) ?? 0) > 0) count++;
    }
    return count;
  }, [allDays, lookup]);

  // Month labels: figure out which week-column each month starts in
  const monthLabels = useMemo(() => {
    const labels: { col: number; label: string }[] = [];
    let lastMonth = -1;
    weekStarts.forEach((weekStart, col) => {
      const month = weekStart.getMonth();
      if (month !== lastMonth) {
        labels.push({ col, label: MONTH_ABBR[month] });
        lastMonth = month;
      }
    });
    return labels;
  }, [weekStarts]);

  return (
    <div className={cn('rounded-xl border border-gray-200 bg-white p-5', className)}>
      {/* Header */}
      {title && (
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-gray-900">{title}</h3>
          <div className="flex items-center gap-4 text-xs text-gray-500">
            <span>{activeDays} active days</span>
            <span className="font-medium text-gray-700">
              {totalValue.toLocaleString()} {metricLabel}
            </span>
          </div>
        </div>
      )}

      <div className="relative overflow-x-auto">
        <div className="flex gap-1 min-w-0">
          {/* Day labels (Y axis) */}
          <div className="flex flex-col gap-[3px] pt-5 pr-1 flex-shrink-0">
            {Array.from({ length: 7 }).map((_, dayIdx) => (
              <div
                key={dayIdx}
                className="h-[10px] flex items-center"
                style={{ marginBottom: '2px' }}
              >
                {DISPLAYED_DAYS.includes(dayIdx) ? (
                  <span className="text-[10px] leading-none text-gray-400 w-6 text-right">
                    {DAY_ABBR[dayIdx]}
                  </span>
                ) : (
                  <span className="w-6" />
                )}
              </div>
            ))}
          </div>

          {/* Grid */}
          <div className="flex-1 overflow-x-auto">
            {/* Month labels (X axis) */}
            <div className="relative h-5 mb-1">
              {monthLabels.map(({ col, label }) => (
                <span
                  key={`${col}-${label}`}
                  className="absolute text-[10px] text-gray-400 leading-none"
                  style={{ left: col * CELL_COLUMN_WIDTH }}
                >
                  {label}
                </span>
              ))}
            </div>

            {/* Week columns */}
            <div className="flex gap-[3px]">
              {weekStarts.map((weekStart, weekIdx) => {
                const days = eachDayOfInterval({
                  start: weekStart,
                  end: endOfWeek(weekStart, { weekStartsOn: 0 }),
                });

                return (
                  <div key={weekIdx} className="flex flex-col gap-[3px]">
                    {days.map((day) => {
                      const dateStr = format(day, 'yyyy-MM-dd');
                      const value = lookup.get(dateStr) ?? 0;
                      const level = getLevel(value, max);
                      const isFuture = day > today;
                      const dayOfWeek = getDay(day);

                      return (
                        <div
                          key={dateStr}
                          className="h-[10px] w-[10px] rounded-sm transition-transform hover:scale-125 cursor-default"
                          style={{
                            backgroundColor: isFuture ? '#f9fafb' : colorScale[level],
                            opacity: isFuture ? 0.3 : 1,
                            outline: tooltip?.date === dateStr ? '1.5px solid #2563eb' : undefined,
                          }}
                          aria-label={isFuture ? dateStr : `${dateStr}: ${value.toLocaleString()} ${metricLabel}`}
                          onMouseEnter={(e) => {
                            if (isFuture) return;
                            const rect = e.currentTarget.getBoundingClientRect();
                            setTooltip({ date: dateStr, value, x: rect.left, y: rect.top });
                          }}
                          onMouseLeave={() => setTooltip(null)}
                        />
                      );
                    })}
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* Tooltip */}
        {tooltip && (
          <div
            className="fixed z-50 pointer-events-none px-2 py-1.5 rounded-md bg-gray-900 text-white text-xs shadow-lg whitespace-nowrap"
            style={{
              left: tooltip.x,
              top: tooltip.y - 40,
              transform: 'translateX(-50%)',
            }}
          >
            <p className="font-medium">
              {tooltip.value > 0
                ? `${tooltip.value.toLocaleString()} ${metricLabel}`
                : 'No activity'}
            </p>
            <p className="text-gray-300 text-[11px]">
              {isValid(parseISO(tooltip.date))
                ? format(parseISO(tooltip.date), 'EEEE, dd MMM yyyy')
                : tooltip.date}
            </p>
          </div>
        )}
      </div>

      {/* Legend */}
      <div className="flex items-center gap-1.5 mt-3 justify-end">
        <span className="text-[10px] text-gray-400">Less</span>
        {colorScale.map((color, i) => (
          <div
            key={i}
            className="h-2.5 w-2.5 rounded-sm"
            style={{ backgroundColor: color }}
          />
        ))}
        <span className="text-[10px] text-gray-400">More</span>
      </div>
    </div>
  );
};

export default ActivityHeatmap;
