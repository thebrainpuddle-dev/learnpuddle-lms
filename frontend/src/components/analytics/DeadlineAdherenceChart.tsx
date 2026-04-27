// src/components/analytics/DeadlineAdherenceChart.tsx
//
// Area chart: % of teachers meeting deadlines over time.
// Data fetched live from /reports/analytics/deadline-adherence/.

import React, { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { ClockIcon, EyeIcon } from '@heroicons/react/24/outline';
import {
  adminReportsService,
  type DeadlineAdherencePoint,
} from '../../services/adminReportsService';

/* ── Custom tooltip ───────────────────────────────────────────── */

const CustomTooltip = ({ active, payload }: any) => {
  if (!active || !payload?.length) return null;
  const pt: DeadlineAdherencePoint = payload[0].payload;
  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-sm px-3 py-2 text-xs">
      <p className="font-medium text-gray-900">{pt.period}</p>
      <p className="text-gray-600">Adherence: {pt.adherencePercent}%</p>
      <p className="text-gray-600">On time: {pt.onTime} / {pt.totalTeachers}</p>
    </div>
  );
};

/* ── Component ─────────────────────────────────────────────────── */

interface DeadlineAdherenceChartProps {
  onViewDetails?: () => void;
}

export const DeadlineAdherenceChart: React.FC<DeadlineAdherenceChartProps> = ({
  onViewDetails,
}) => {
  const { data: rawData, isLoading, isError } = useQuery<DeadlineAdherencePoint[]>({
    queryKey: ['deadlineAdherence'],
    queryFn: () => adminReportsService.deadlineAdherence(),
    staleTime: 5 * 60 * 1000,
  });

  const data: DeadlineAdherencePoint[] = rawData ?? [];

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
        <span className="text-2xl font-bold text-gray-900">
          {isLoading || isError ? '—' : `${latest?.adherencePercent ?? 0}%`}
        </span>
        <span className="text-sm text-gray-500">current adherence rate</span>
      </div>

      <div className="h-56">
        {isLoading ? (
          <div className="flex items-center justify-center h-full">
            <div className="h-6 w-6 border-2 border-emerald-300 border-t-emerald-600 rounded-full animate-spin" />
          </div>
        ) : isError ? (
          <div className="flex items-center justify-center h-full text-red-400 text-sm">
            Failed to load deadline data
          </div>
        ) : data.length > 0 ? (
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
        ) : (
          <div className="flex items-center justify-center h-full text-gray-400 text-sm">
            No deadline data yet
          </div>
        )}
      </div>
    </div>
  );
};
