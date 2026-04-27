// src/pages/admin/EngagementHeatmapPage.tsx
//
// Admin Engagement Heatmap — tenant-wide day-of-week × hour-of-day grid
// showing when teachers actually engage with the LMS.
//
// Backed by GET /api/reports/engagement/heatmap/ (see
// backend/apps/reports/engagement_views.py). Data is aggregated from
// `TeacherProgress.last_accessed` — the most reliable "something
// happened" signal we have per-teacher.
//
// We render a custom CSS-grid heatmap (no extra libs) with a colour
// scale from cool (empty) to warm (hottest cell). The user can switch
// between UTC and their browser-local timezone, and restrict to a
// rolling window of 7 / 30 / 90 days.

import React, { useMemo, useState } from 'react';
import axios from 'axios';
import { useQuery } from '@tanstack/react-query';
import {
  CalendarDaysIcon,
  ClockIcon,
  ExclamationTriangleIcon,
  ArrowPathIcon,
  FireIcon,
} from '@heroicons/react/24/outline';
import { Loading } from '../../components/common';
import { Badge } from '../../components/ui/badge';
import { Button } from '../../components/common/Button';
import {
  adminReportsService,
  type EngagementHeatmapResponse,
} from '../../services/adminReportsService';
import { usePageTitle } from '../../hooks/usePageTitle';

// ── Constants ────────────────────────────────────────────────────────────────

/** Monday-first, matching Python's `datetime.weekday()` used on the server. */
const DAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'] as const;

/** Window presets in days. */
const WINDOW_PRESETS = [
  { value: 7, label: 'Last 7 days' },
  { value: 30, label: 'Last 30 days' },
  { value: 90, label: 'Last 90 days' },
] as const;

// ── Helpers ──────────────────────────────────────────────────────────────────

function getErrorMessage(err: unknown, fallback: string): string {
  if (axios.isAxiosError(err)) {
    const data = err.response?.data as { detail?: string; error?: string } | undefined;
    if (data?.detail) return data.detail;
    if (data?.error) return data.error;
    if (err.message) return err.message;
  }
  if (err instanceof Error) return err.message;
  return fallback;
}

/**
 * Map a cell's count to a Tailwind background class on a 0..max scale.
 * Five steps keep the palette readable and a11y-friendly — we avoid a
 * continuous gradient because browsers interpolate RGB inconsistently
 * at low intensities.
 */
function bucketColor(count: number, max: number): string {
  if (count === 0 || max === 0) return 'bg-slate-100';
  const ratio = count / max;
  if (ratio > 0.8) return 'bg-blue-700 text-white';
  if (ratio > 0.6) return 'bg-blue-600 text-white';
  if (ratio > 0.4) return 'bg-blue-500 text-white';
  if (ratio > 0.2) return 'bg-blue-300';
  return 'bg-blue-100';
}

/** Return ISO YYYY-MM-DD `days` days ago from today (UTC). */
function isoDaysAgo(days: number): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - days);
  return d.toISOString().slice(0, 10);
}

function isoTomorrow(): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() + 1);
  return d.toISOString().slice(0, 10);
}

function formatHour(h: number): string {
  if (h === 0) return '12a';
  if (h === 12) return '12p';
  return h < 12 ? `${h}a` : `${h - 12}p`;
}

/** Browser's best-guess IANA tz, falling back to UTC. */
function detectBrowserTz(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  } catch {
    return 'UTC';
  }
}

// ── Page ─────────────────────────────────────────────────────────────────────

export const EngagementHeatmapPage: React.FC = () => {
  usePageTitle('Engagement Heatmap');

  const browserTz = useMemo(detectBrowserTz, []);
  const [tzMode, setTzMode] = useState<'local' | 'utc'>('local');
  const [windowDays, setWindowDays] = useState<number>(30);

  const tz = tzMode === 'utc' ? 'UTC' : browserTz;
  const start = useMemo(() => isoDaysAgo(windowDays), [windowDays]);
  const end = useMemo(() => isoTomorrow(), [windowDays]);

  const query = useQuery<EngagementHeatmapResponse>({
    queryKey: ['admin', 'engagement-heatmap', { tz, start, end }],
    queryFn: () => adminReportsService.engagementHeatmap({ tz, start, end }),
  });

  if (query.isLoading) {
    return <Loading />;
  }

  if (query.isError) {
    return (
      <div className="p-6">
        <div
          role="alert"
          data-testid="heatmap-error"
          className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-800"
        >
          <div className="flex items-start gap-3">
            <ExclamationTriangleIcon className="h-5 w-5 flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <h3 className="font-semibold">Could not load engagement heatmap</h3>
              <p className="mt-1 text-sm">
                {getErrorMessage(query.error, 'Please try again.')}
              </p>
              <Button
                variant="secondary"
                className="mt-3"
                onClick={() => query.refetch()}
              >
                <ArrowPathIcon className="h-4 w-4 mr-2" />
                Retry
              </Button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const data = query.data;
  const cells = data?.cells ?? [];
  const max = data?.max_cell ?? 0;
  const total = data?.total_events ?? 0;

  // Build a day→hour→cell lookup so rendering is O(1) per cell.
  const cellIndex = new Map<string, number>();
  for (const c of cells) cellIndex.set(`${c.day}:${c.hour}`, c.count);

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <header className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <FireIcon className="h-6 w-6 text-primary-600" />
            Engagement Heatmap
          </h1>
          <p className="text-sm text-slate-600 mt-1">
            When your teachers actually use the LMS. Each cell is a
            day-of-week × hour-of-day bucket, colour-coded by activity.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2">
            <label htmlFor="heatmap-window" className="text-sm text-slate-600">
              Window
            </label>
            <select
              id="heatmap-window"
              value={windowDays}
              onChange={(e) => setWindowDays(Number(e.target.value))}
              className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-primary-500 focus:ring-primary-500"
            >
              {WINDOW_PRESETS.map((p) => (
                <option key={p.value} value={p.value}>
                  {p.label}
                </option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-2">
            <label htmlFor="heatmap-tz" className="text-sm text-slate-600">
              Timezone
            </label>
            <select
              id="heatmap-tz"
              value={tzMode}
              onChange={(e) => setTzMode(e.target.value as 'local' | 'utc')}
              className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-primary-500 focus:ring-primary-500"
            >
              <option value="local">Local ({browserTz})</option>
              <option value="utc">UTC</option>
            </select>
          </div>
        </div>
      </header>

      {/* Summary strip */}
      <section
        aria-label="Summary"
        className="grid grid-cols-1 sm:grid-cols-3 gap-4"
      >
        <SummaryCard
          icon={<CalendarDaysIcon className="h-5 w-5 text-primary-600" />}
          label="Window"
          value={data ? `${data.start} → ${data.end}` : '—'}
        />
        <SummaryCard
          icon={<ClockIcon className="h-5 w-5 text-sky-600" />}
          label="Total activity events"
          value={total.toLocaleString()}
          testId="stat-total-events"
        />
        <SummaryCard
          icon={<FireIcon className="h-5 w-5 text-amber-600" />}
          label="Peak cell"
          value={max.toLocaleString()}
          testId="stat-peak-cell"
        />
      </section>

      {/* Heatmap grid */}
      <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold text-slate-900">
            Activity by day and hour
          </h2>
          <Badge variant="outline">
            {data?.timezone ?? 'UTC'}
            {data?.tz_fallback ? ' (fallback)' : ''}
          </Badge>
        </div>

        {total === 0 ? (
          <EmptyHeatmap />
        ) : (
          <div className="overflow-x-auto">
            <div
              data-testid="heatmap-grid"
              role="grid"
              aria-label="Engagement heatmap: 7 days by 24 hours"
              className="inline-grid gap-1"
              style={{
                gridTemplateColumns: '56px repeat(24, minmax(22px, 1fr))',
              }}
            >
              {/* Hour header row */}
              <div aria-hidden />
              {Array.from({ length: 24 }, (_, h) => (
                <div
                  key={`h-${h}`}
                  className="text-[10px] text-slate-500 text-center tabular-nums"
                  aria-hidden
                >
                  {formatHour(h)}
                </div>
              ))}

              {/* Day rows */}
              {DAY_LABELS.map((label, day) => (
                <React.Fragment key={label}>
                  <div
                    className="text-xs font-medium text-slate-600 flex items-center justify-end pr-2"
                    aria-hidden
                  >
                    {label}
                  </div>
                  {Array.from({ length: 24 }, (_, hour) => {
                    const count = cellIndex.get(`${day}:${hour}`) ?? 0;
                    const color = bucketColor(count, max);
                    return (
                      <div
                        key={`${day}-${hour}`}
                        role="gridcell"
                        data-testid={`heatmap-cell-${day}-${hour}`}
                        data-count={count}
                        title={`${label} ${formatHour(hour)} — ${count} event${count === 1 ? '' : 's'}`}
                        className={`h-6 rounded-sm text-[10px] flex items-center justify-center tabular-nums ${color}`}
                      >
                        {count > 0 ? count : ''}
                      </div>
                    );
                  })}
                </React.Fragment>
              ))}
            </div>

            {/* Legend */}
            <div
              data-testid="heatmap-legend"
              className="mt-4 flex items-center gap-3 text-xs text-slate-600"
              aria-label="Color scale legend"
            >
              <span>Less</span>
              <div className="h-3 w-4 rounded-sm bg-slate-100 border border-slate-200" />
              <div className="h-3 w-4 rounded-sm bg-blue-100" />
              <div className="h-3 w-4 rounded-sm bg-blue-300" />
              <div className="h-3 w-4 rounded-sm bg-blue-500" />
              <div className="h-3 w-4 rounded-sm bg-blue-600" />
              <div className="h-3 w-4 rounded-sm bg-blue-700" />
              <span>More</span>
            </div>
          </div>
        )}
      </section>
    </div>
  );
};

// ── Subcomponents ────────────────────────────────────────────────────────────

interface SummaryCardProps {
  icon: React.ReactNode;
  label: string;
  value: string;
  testId?: string;
}

const SummaryCard: React.FC<SummaryCardProps> = ({ icon, label, value, testId }) => (
  <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
    <div className="flex items-center gap-3">
      <div className="h-10 w-10 rounded-full bg-slate-50 flex items-center justify-center">
        {icon}
      </div>
      <div className="min-w-0">
        <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
        <p
          className="text-lg font-semibold text-slate-900 truncate"
          data-testid={testId}
        >
          {value}
        </p>
      </div>
    </div>
  </div>
);

const EmptyHeatmap: React.FC = () => (
  <div
    data-testid="heatmap-empty"
    className="flex flex-col items-center justify-center text-center py-16"
  >
    <FireIcon className="h-10 w-10 text-slate-300 mb-3" />
    <p className="text-sm font-medium text-slate-700">
      No engagement yet in this window
    </p>
    <p className="text-xs text-slate-500 max-w-sm mt-1">
      Once teachers start opening courses, watching videos, or submitting
      work, their activity will light up this grid.
    </p>
  </div>
);

export default EngagementHeatmapPage;
