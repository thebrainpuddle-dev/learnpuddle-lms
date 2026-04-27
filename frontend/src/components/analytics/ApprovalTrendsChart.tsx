// src/components/analytics/ApprovalTrendsChart.tsx
//
// Stacked bar chart: skip request volume + approval rates over time.
// Two series: Approved (green), Rejected (red), Pending (amber).
// Data fetched live from /reports/analytics/approval-trends/.

import React, { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer,
} from 'recharts';
import { CheckBadgeIcon, EyeIcon } from '@heroicons/react/24/outline';
import {
  adminReportsService,
  type ApprovalTrendsPoint,
} from '../../services/adminReportsService';

/* ── Component ─────────────────────────────────────────────────── */

interface ApprovalTrendsChartProps {
  onViewDetails?: () => void;
}

export const ApprovalTrendsChart: React.FC<ApprovalTrendsChartProps> = ({
  onViewDetails,
}) => {
  const { data: rawData, isLoading, isError } = useQuery<ApprovalTrendsPoint[]>({
    queryKey: ['approvalTrends'],
    queryFn: () => adminReportsService.approvalTrends(),
    staleTime: 5 * 60 * 1000,
  });

  const data: ApprovalTrendsPoint[] = rawData ?? [];

  const chartData = useMemo(
    () => data.map((d) => ({
      name: d.period,
      Approved: d.approved,
      Rejected: d.rejected,
      Pending: d.pending,
    })),
    [data]
  );

  const totalApproved = data.reduce((s, d) => s + d.approved, 0);
  const totalAll = data.reduce((s, d) => s + d.approved + d.rejected + d.pending, 0);
  const approvalRate = totalAll > 0 ? Math.round((totalApproved / totalAll) * 100) : 0;

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <CheckBadgeIcon className="h-5 w-5 text-amber-600" />
          <h2 className="font-semibold text-gray-900">Skip Request Trends</h2>
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

      {/* Summary stat */}
      <div className="mb-3 flex items-baseline gap-2">
        <span className="text-2xl font-bold text-gray-900">
          {isLoading || isError ? '—' : `${approvalRate}%`}
        </span>
        <span className="text-sm text-gray-500">
          {isLoading || isError ? 'overall approval rate' : `overall approval rate (${totalAll} total requests)`}
        </span>
      </div>

      <div className="h-56">
        {isLoading ? (
          <div className="flex items-center justify-center h-full">
            <div className="h-6 w-6 border-2 border-amber-300 border-t-amber-600 rounded-full animate-spin" />
          </div>
        ) : isError ? (
          <div className="flex items-center justify-center h-full text-red-400 text-sm">
            Failed to load skip request data
          </div>
        ) : data.length > 0 ? (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="name" tick={{ fontSize: 12 }} />
              <YAxis allowDecimals={false} />
              <Tooltip />
              <Legend iconSize={12} wrapperStyle={{ paddingTop: 8 }} />
              <Bar dataKey="Approved" stackId="a" fill="#10b981" radius={[0, 0, 0, 0]} />
              <Bar dataKey="Rejected" stackId="a" fill="#ef4444" radius={[0, 0, 0, 0]} />
              <Bar dataKey="Pending" stackId="a" fill="#f59e0b" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <div className="flex items-center justify-center h-full text-gray-400 text-sm">
            No skip request data yet
          </div>
        )}
      </div>
    </div>
  );
};
