// src/components/certifications/IBDashboard.tsx
//
// School-level IB compliance dashboard showing per-certification
// compliance metrics with progress bars and summary cards.
// TODO: Replace placeholder data with actual API endpoint once backend
// provides /api/v1/tenants/ib-compliance/ or similar.

import React, { useMemo } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Badge } from '../../components/ui/badge';
import {
  ShieldCheckIcon,
  ChartBarIcon,
  UserGroupIcon,
  ExclamationTriangleIcon,
  CheckCircleIcon,
} from '@heroicons/react/24/outline';

// ── Types ────────────────────────────────────────────────────────────

interface CertComplianceRow {
  certificationName: string;
  requiredCount: number;
  certifiedCount: number;
  expiringWithin30: number;
}

interface IBComplianceData {
  schoolName: string;
  overallCompliancePercent: number;
  totalTeachers: number;
  totalCertificationsRequired: number;
  totalCertified: number;
  certifications: CertComplianceRow[];
}

// ── Placeholder data ─────────────────────────────────────────────────
// TODO: Fetch from API — GET /api/v1/tenants/ib-compliance/

const PLACEHOLDER_DATA: IBComplianceData = {
  schoolName: 'Your School',
  overallCompliancePercent: 72,
  totalTeachers: 48,
  totalCertificationsRequired: 6,
  totalCertified: 4,
  certifications: [
    { certificationName: 'IB Category 1 — Teaching & Learning', requiredCount: 48, certifiedCount: 42, expiringWithin30: 3 },
    { certificationName: 'IB Category 2 — Leading Learning', requiredCount: 12, certifiedCount: 10, expiringWithin30: 1 },
    { certificationName: 'IB Category 3 — Programme Development', requiredCount: 48, certifiedCount: 31, expiringWithin30: 0 },
    { certificationName: 'Child Safeguarding Level 1', requiredCount: 48, certifiedCount: 48, expiringWithin30: 5 },
    { certificationName: 'First Aid & CPR', requiredCount: 48, certifiedCount: 36, expiringWithin30: 2 },
    { certificationName: 'Data Protection & FERPA', requiredCount: 48, certifiedCount: 28, expiringWithin30: 0 },
  ],
};

// ── Helpers ──────────────────────────────────────────────────────────

function compliancePercent(certified: number, required: number): number {
  if (required === 0) return 100;
  return Math.round((certified / required) * 100);
}

function complianceColor(pct: number): string {
  if (pct >= 90) return 'text-emerald-600';
  if (pct >= 70) return 'text-amber-600';
  return 'text-red-600';
}

function progressBarColor(pct: number): string {
  if (pct >= 90) return 'bg-emerald-500';
  if (pct >= 70) return 'bg-amber-500';
  return 'bg-red-500';
}

function badgeVariant(pct: number): 'success' | 'warning' | 'destructive' {
  if (pct >= 90) return 'success';
  if (pct >= 70) return 'warning';
  return 'destructive';
}

// ── Component ────────────────────────────────────────────────────────

export const IBDashboard: React.FC = () => {
  // TODO: Replace with useQuery hook once backend endpoint is available
  // const { data, isLoading } = useQuery({
  //   queryKey: ['ibCompliance'],
  //   queryFn: () => api.get('/tenants/ib-compliance/').then(r => r.data),
  // });
  const data = PLACEHOLDER_DATA;

  const sortedCertifications = useMemo(() => {
    return [...data.certifications].sort((a, b) => {
      const pctA = compliancePercent(a.certifiedCount, a.requiredCount);
      const pctB = compliancePercent(b.certifiedCount, b.requiredCount);
      return pctA - pctB; // lowest compliance first
    });
  }, [data.certifications]);

  const overallPct = data.overallCompliancePercent;
  const totalExpiring = data.certifications.reduce((sum, c) => sum + c.expiringWithin30, 0);

  return (
    <div className="space-y-6">
      {/* Notice banner */}
      <div className="rounded-lg border border-blue-200 bg-blue-50 p-4">
        <p className="text-sm text-blue-700">
          <strong>Preview:</strong> This dashboard uses sample data. The IB compliance API
          endpoint is under development. Metrics will be live once connected.
        </p>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-gray-500">
              Overall Compliance
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-3">
              <ChartBarIcon className={`h-8 w-8 ${complianceColor(overallPct)}`} />
              <div>
                <span className={`text-3xl font-bold ${complianceColor(overallPct)}`}>
                  {overallPct}%
                </span>
              </div>
            </div>
            <div className="mt-2 h-2 w-full rounded-full bg-gray-200">
              <div
                className={`h-2 rounded-full transition-all ${progressBarColor(overallPct)}`}
                style={{ width: `${Math.min(overallPct, 100)}%` }}
              />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-gray-500">
              Total Teachers
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-3">
              <UserGroupIcon className="h-8 w-8 text-indigo-500" />
              <span className="text-3xl font-bold text-gray-900">
                {data.totalTeachers}
              </span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-gray-500">
              Certifications Met
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-3">
              <CheckCircleIcon className="h-8 w-8 text-emerald-500" />
              <span className="text-3xl font-bold text-gray-900">
                {data.totalCertified}
                <span className="text-lg font-normal text-gray-400">
                  /{data.totalCertificationsRequired}
                </span>
              </span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-gray-500">
              Expiring in 30 Days
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-3">
              <ExclamationTriangleIcon
                className={`h-8 w-8 ${totalExpiring > 0 ? 'text-amber-500' : 'text-gray-300'}`}
              />
              <span className="text-3xl font-bold text-gray-900">
                {totalExpiring}
              </span>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Per-certification compliance table */}
      <div>
        <h3 className="text-lg font-semibold text-gray-900 mb-3">
          Certification Compliance Breakdown
        </h3>

        {sortedCertifications.length === 0 ? (
          <div className="text-center py-12 text-gray-500 border border-gray-200 rounded-lg bg-white">
            <ShieldCheckIcon className="h-12 w-12 mx-auto mb-3 text-gray-300" />
            <p className="font-medium">No certification requirements configured.</p>
            <p className="text-sm mt-1">
              Define required certifications in the Certifications tab to see compliance data.
            </p>
          </div>
        ) : (
          <>
            {/* Desktop table */}
            <div className="hidden md:block overflow-x-auto bg-white rounded-xl border border-gray-200 shadow-sm">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Certification
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Required
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Certified
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Compliance
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Expiring Soon
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-100">
                  {sortedCertifications.map((cert) => {
                    const pct = compliancePercent(cert.certifiedCount, cert.requiredCount);
                    return (
                      <tr key={cert.certificationName} className="hover:bg-gray-50">
                        <td className="px-4 py-3">
                          <div className="text-sm font-medium text-gray-900">
                            {cert.certificationName}
                          </div>
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-700">
                          {cert.requiredCount}
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-700">
                          {cert.certifiedCount}
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-3">
                            <div className="flex-1 max-w-[120px]">
                              <div className="h-2 w-full rounded-full bg-gray-200">
                                <div
                                  className={`h-2 rounded-full transition-all ${progressBarColor(pct)}`}
                                  style={{ width: `${Math.min(pct, 100)}%` }}
                                />
                              </div>
                            </div>
                            <Badge variant={badgeVariant(pct)}>{pct}%</Badge>
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          {cert.expiringWithin30 > 0 ? (
                            <span className="inline-flex items-center gap-1 text-sm text-amber-600 font-medium">
                              <ExclamationTriangleIcon className="h-4 w-4" />
                              {cert.expiringWithin30}
                            </span>
                          ) : (
                            <span className="text-sm text-gray-400">-</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Mobile cards */}
            <div className="md:hidden space-y-3">
              {sortedCertifications.map((cert) => {
                const pct = compliancePercent(cert.certifiedCount, cert.requiredCount);
                return (
                  <div key={cert.certificationName} className="bg-white rounded-xl border border-gray-200 shadow-sm p-4">
                    <div className="flex items-start justify-between gap-3 mb-3">
                      <p className="text-sm font-semibold text-gray-900">
                        {cert.certificationName}
                      </p>
                      <Badge variant={badgeVariant(pct)}>{pct}%</Badge>
                    </div>
                    <div className="h-2 w-full rounded-full bg-gray-200 mb-3">
                      <div
                        className={`h-2 rounded-full transition-all ${progressBarColor(pct)}`}
                        style={{ width: `${Math.min(pct, 100)}%` }}
                      />
                    </div>
                    <div className="grid grid-cols-3 gap-2 text-xs text-gray-600">
                      <div>
                        <span className="block font-medium text-gray-500">Required</span>
                        <span className="text-gray-900">{cert.requiredCount}</span>
                      </div>
                      <div>
                        <span className="block font-medium text-gray-500">Certified</span>
                        <span className="text-gray-900">{cert.certifiedCount}</span>
                      </div>
                      <div>
                        <span className="block font-medium text-gray-500">Expiring</span>
                        {cert.expiringWithin30 > 0 ? (
                          <span className="text-amber-600 font-medium">{cert.expiringWithin30}</span>
                        ) : (
                          <span className="text-gray-400">-</span>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </>
        )}
      </div>
    </div>
  );
};
