// src/components/analytics/CertComplianceChart.tsx
//
// Horizontal bar chart showing compliance % per required certification.
// Color coded: green (>80%), yellow (50-80%), red (<50%).
// Fetches real data from /tenants/staff-certifications/ endpoint.

import React, { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell,
  ResponsiveContainer,
} from 'recharts';
import { ShieldCheckIcon, EyeIcon } from '@heroicons/react/24/outline';
import api from '../../config/api';

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

interface ComplianceCategory {
  required: number;
  completed: number;
}

interface StaffCertsSummary {
  summary: {
    total_teachers: number;
    compliance_categories: Record<string, ComplianceCategory>;
  };
}

/* ── Display labels for cert types ─────────────────────────────── */

const CERT_LABELS: Record<string, string> = {
  IB_CAT1: 'IB Cat 1 Workshop',
  IB_CAT2: 'IB Cat 2 Workshop',
  IB_CAT3: 'IB Cat 3 Workshop',
  POCSO: 'POCSO Awareness',
  FIRST_AID: 'First Aid',
  FIRE_SAFETY: 'Fire Safety',
  CHILD_SAFEGUARDING: 'Child Safeguarding',
  POSH: 'POSH Training',
  IB_LEADER: 'IB Leadership',
};

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
  const { data: certResponse, isLoading } = useQuery<StaffCertsSummary>({
    queryKey: ['staffCertifications'],
    queryFn: async () => {
      const res = await api.get('/tenants/staff-certifications/');
      return res.data;
    },
    staleTime: 5 * 60 * 1000,
  });

  const data: CertComplianceItem[] = useMemo(() => {
    const categories = certResponse?.summary?.compliance_categories;
    if (!categories) return [];
    return Object.entries(categories).map(([type, cat]) => ({
      certName: CERT_LABELS[type] || type,
      compliancePercent: cat.required > 0 ? Math.round((cat.completed / cat.required) * 100) : 0,
      certified: cat.completed,
      total: cat.required,
    })).sort((a, b) => b.compliancePercent - a.compliancePercent);
  }, [certResponse]);

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
        <span className="text-2xl font-bold text-gray-900">
          {isLoading ? '—' : `${avgCompliance}%`}
        </span>
        <span className="text-sm text-gray-500">average compliance</span>
      </div>

      {/* Legend */}
      <div className="mb-3 flex flex-wrap gap-3 text-xs text-gray-500">
        <div className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-emerald-500" /> &ge;80%</div>
        <div className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-amber-500" /> 50-79%</div>
        <div className="flex items-center gap-1"><span className="h-2 w-2 rounded-full bg-red-500" /> &lt;50%</div>
      </div>

      <div className="h-56">
        {isLoading ? (
          <div className="flex items-center justify-center h-full">
            <div className="h-6 w-6 border-2 border-indigo-300 border-t-indigo-600 rounded-full animate-spin" />
          </div>
        ) : data.length > 0 ? (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={chartData} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" horizontal={false} />
              <XAxis
                type="number"
                domain={[0, 100]}
                tickFormatter={(v) => `${v}%`}
              />
              <YAxis dataKey="name" type="category" width={120} tick={{ fontSize: 11 }} />
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
