// src/components/analytics/DeadlineAdherenceChart.tsx
//
// Line chart showing % of teachers meeting deadlines over time.
// Uses placeholder data — TODO: wire to backend analytics endpoint.

import React, { useMemo } from 'react';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { ClockIcon, EyeIcon } from '@heroicons/react/24/outline';

/* ── Types ─────────────────────────────────────────────────────── */

interface DeadlineDataPoint {
  period: string; // e.g. "Week 1", "Jan 2026"
  adherencePercent: number; // 0-100
  totalTeachers: number;
  onTime: number;
  late: number;
}

interface DeadlineAdherenceChartProps {
  onViewDetails?: () => void;
}

/* ── Placeholder data (TODO: replace with API call) ──────────── */

const MOCK_DATA: DeadlineDataPoint[] = [
  { period: 'Oct 2025', adherencePercent: 72, totalTeachers: 50, onTime: 36, late: 14 },
  { period: 'Nov 2025', adherencePercent: 78, totalTeachers: 50, onTime: 39, late: 11 },
  { period: 'Dec 2025', adherencePercent: 65, totalTeachers: 48, onTime: 31, late: 17 },
  { period: 'Jan 2026', adherencePercent: 80, totalTeachers: 52, onTime: 42, late: 10 },
  { period: 'Feb 2026', adherencePercent: 85, totalTeachers: 52, onTime: 44, late: 8 },
  { period: 'Mar 2026', adherencePercent: 88, totalTeachers: 55, onTime: 48, late: 7 },
];

/* ── Custom tooltip ───────────────────────────────────────────── */

const CustomTooltip = ({ active, payload }: any) => {
  if (!active || !payload?.length) return null;
  const pt: DeadlineDataPoint = payload[0].payload;
  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-sm px-3 py-2 text-xs">
      <p className="font-medium text-gray-900">{pt.period}</p>
      <p className="text-gray-600">Adherence: {pt.adherencePercent}%</p>
      <p className="text-gray-600">On time: {pt.onTime} / {pt.totalTeachers}</p>
    </div>
  );
};

/* ── Component ─────────────────────────────────────────────────── */

export const DeadlineAdherenceChart: React.FC<DeadlineAdherenceChartProps> = ({
  onViewDetails,
}) => {
  // TODO: Replace with useQuery call to backend endpoint
  // const { data } = useQuery({ queryKey: ['deadlineAdherence'], queryFn: ... });
  const data = MOCK_DATA;

  const chartData = useMemo(
    () => data.map((d) => ({ ...d, name: d.period })),
    [data]
  );

  const latest = data[data.length - 1];

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <ClockIcon className="h-5 w-5 text-emerald-600" />
          <h2 className="font-semibold text-gray-900">Deadline Adherence</h2>
        </div>
        {onViewDetails && (
          <button
            type="button"
            onClick={onViewDetails}
            className="inline-flex items-center gap-1 text-xs font-medium text-primary-600 hover:text-primary-700"
          >
            <EyeIcon className="h-4 w-4" />
            View Details
          </button>
        )}
      </div>

      {/* Current stat */}
      <div className="mb-3 flex items-baseline gap-2">
        <span className="text-2xl font-bold text-gray-900">{latest?.adherencePercent ?? 0}%</span>
        <span className="text-sm text-gray-500">current adherence rate</span>
      </div>

      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="name" tick={{ fontSize: 12 }} />
            <YAxis domain={[0, 100]} tickFormatter={(v) => `${v}%`} />
            <Tooltip content={<CustomTooltip />} />
            <Area
              type="monotone"
              dataKey="adherencePercent"
              name="Adherence %"
              stroke="#10b981"
              fill="rgba(16, 185, 129, 0.1)"
              strokeWidth={2}
              dot={{ fill: '#10b981', r: 5 }}
              activeDot={{ r: 7 }}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};
