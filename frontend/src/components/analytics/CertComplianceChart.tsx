// src/components/analytics/CertComplianceChart.tsx
//
// Horizontal bar chart showing compliance % per required certification.
// Color coded: green (>80%), yellow (50-80%), red (<50%).
// Uses placeholder data — TODO: wire to backend analytics endpoint.

import React, { useMemo } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell,
  ResponsiveContainer,
} from 'recharts';
import { ShieldCheckIcon, EyeIcon } from '@heroicons/react/24/outline';

/* ── Types ─────────────────────────────────────────────────────── */

interface CertComplianceItem {
  certName: string;
  compliancePercent: number; // 0-100
  certified: number;
  total: number;
}

interface CertComplianceChartProps {
  onViewDetails?: () => void;
}

/* ── Placeholder data (TODO: replace with API call) ──────────── */

const MOCK_DATA: CertComplianceItem[] = [
  { certName: 'Child Safety', compliancePercent: 92, certified: 46, total: 50 },
  { certName: 'First Aid', compliancePercent: 74, certified: 37, total: 50 },
  { certName: 'IB Methods', compliancePercent: 60, certified: 30, total: 50 },
  { certName: 'Digital Literacy', compliancePercent: 45, certified: 22, total: 49 },
  { certName: 'Data Privacy', compliancePercent: 88, certified: 44, total: 50 },
];

/* ── Helpers ───────────────────────────────────────────────────── */

function complianceColor(pct: number): string {
  if (pct >= 80) return '#10b981'; // green
  if (pct >= 50) return '#f59e0b'; // yellow / amber
  return '#ef4444'; // red
}

/* ── Custom tooltip ───────────────────────────────────────────── */

const CustomTooltip = ({ active, payload }: any) => {
  if (!active || !payload?.length) return null;
  const item: CertComplianceItem & { name: string } = payload[0].payload;
  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-sm px-3 py-2 text-xs">
      <p className="font-medium text-gray-900">{item.certName}</p>
      <p className="text-gray-600">{item.compliancePercent}% ({item.certified}/{item.total} teachers)</p>
    </div>
  );
};

/* ── Component ─────────────────────────────────────────────────── */

export const CertComplianceChart: React.FC<CertComplianceChartProps> = ({
  onViewDetails,
}) => {
  // TODO: Replace with useQuery call to backend endpoint
  // const { data } = useQuery({ queryKey: ['certCompliance'], queryFn: ... });
  const data = MOCK_DATA;

  const chartData = useMemo(
    () => data.map((d) => ({ ...d, name: d.certName })),
    [data]
  );

  const avgCompliance =
    data.length > 0
      ? Math.round(data.reduce((sum, d) => sum + d.compliancePercent, 0) / data.length)
      : 0;

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <ShieldCheckIcon className="h-5 w-5 text-indigo-600" />
          <h2 className="font-semibold text-gray-900">Certification Compliance</h2>
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
        <span className="text-2xl font-bold text-gray-900">{avgCompliance}%</span>
        <span className="text-sm text-gray-500">average compliance</span>
      </div>

      {/* Legend */}
      <div className="mb-3 flex flex-wrap gap-3 text-xs text-gray-500">
        <div className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-emerald-500" /> &ge;80%</div>
        <div className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-amber-500" /> 50-79%</div>
        <div className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-red-500" /> &lt;50%</div>
      </div>

      <div className="h-56">
        {data.length > 0 ? (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" horizontal={false} />
              <XAxis
                type="number"
                domain={[0, 100]}
                tickFormatter={(v) => `${v}%`}
              />
              <YAxis dataKey="name" type="category" width={110} tick={{ fontSize: 12 }} />
              <Tooltip content={<CustomTooltip />} />
              <Bar dataKey="compliancePercent" name="Compliance %" radius={[0, 4, 4, 0]} barSize={24}>
                {chartData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={complianceColor(entry.compliancePercent)} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <div className="flex items-center justify-center h-full text-gray-400 text-sm">
            No certification data yet
          </div>
        )}
      </div>
    </div>
  );
};
