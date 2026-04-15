// src/components/certifications/IBDashboard.tsx
//
// IB Compliance Dashboard. Fetches real data from the staff-certifications
// endpoint and shows IB training compliance, safety compliance, overall
// PD compliance rate, per-certification breakdown, and a gap analysis
// listing teachers missing required certifications.

import React, { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  GraduationCap,
  ShieldCheck,
  ShieldAlert,
  AlertTriangle,
  Users,
  CheckCircle,
  XCircle,
  Loader2,
} from 'lucide-react';
import api from '../../config/api';
import { cn } from '../../lib/utils';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Badge } from '../../components/ui/badge';

// -- Types -------------------------------------------------------------------

interface StaffCert {
  id: string;
  certification_type: string;
  display_name: string;
  status: 'VALID' | 'EXPIRING' | 'EXPIRED' | 'NOT_STARTED';
  completed_date: string | null;
  expiry_date: string | null;
}

interface TeacherWithCerts {
  id: string;
  name: string;
  email: string;
  certifications: StaffCert[];
}

interface ComplianceCategoryEntry {
  required: number;
  completed: number;
}

interface StaffCertSummary {
  total_teachers: number;
  ib_trained_count: number;
  ib_trained_percentage: number;
  expiring_count: number;
  compliance_categories: Record<string, ComplianceCategoryEntry>;
}

interface StaffCertsResponse {
  summary: StaffCertSummary;
  teachers: TeacherWithCerts[];
}

// -- Constants ---------------------------------------------------------------

/** Cert types that are IB-related */
const IB_CERT_TYPES = ['IB_CAT1', 'IB_CAT2', 'IB_CAT3', 'IB_LEADER'];

/** Cert types that are safety-related */
const SAFETY_CERT_TYPES = ['POCSO', 'FIRST_AID', 'FIRE_SAFETY'];

/** All tracked cert types for overall compliance */
const ALL_TRACKED_TYPES = [
  ...IB_CERT_TYPES,
  ...SAFETY_CERT_TYPES,
  'CHILD_SAFEGUARDING',
  'POSH',
];

const CERT_LABELS: Record<string, string> = {
  IB_CAT1: 'IB Category 1 Workshop',
  IB_CAT2: 'IB Category 2 Workshop',
  IB_CAT3: 'IB Category 3 Workshop',
  IB_LEADER: 'IB Leadership Workshop',
  POCSO: 'POCSO Awareness',
  FIRST_AID: 'First Aid Certification',
  FIRE_SAFETY: 'Fire Safety Training',
  CHILD_SAFEGUARDING: 'Child Safeguarding',
  POSH: 'POSH Training',
  CWSN: 'CWSN Training',
  GOOGLE_CERT: 'Google Certified Educator',
  MENTAL_HEALTH: 'Mental Health & Wellbeing',
  ANTI_BULLYING: 'Anti-Bullying Training',
};

// -- Helpers -----------------------------------------------------------------

function compliancePercent(completed: number, required: number): number {
  if (required === 0) return 100;
  return Math.round((completed / required) * 100);
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

function progressBarBgColor(pct: number): string {
  if (pct >= 90) return 'bg-emerald-100';
  if (pct >= 70) return 'bg-amber-100';
  return 'bg-red-100';
}

function badgeVariant(pct: number): 'success' | 'warning' | 'destructive' {
  if (pct >= 90) return 'success';
  if (pct >= 70) return 'warning';
  return 'destructive';
}

/** Count how many teachers have a VALID cert for a given type */
function countCertified(teachers: TeacherWithCerts[], certType: string): number {
  return teachers.filter((t) =>
    t.certifications.some(
      (c) => c.certification_type === certType && (c.status === 'VALID' || c.status === 'EXPIRING'),
    ),
  ).length;
}

/** Count how many certs of a given type are expiring */
function countExpiring(teachers: TeacherWithCerts[], certType: string): number {
  return teachers.filter((t) =>
    t.certifications.some(
      (c) => c.certification_type === certType && c.status === 'EXPIRING',
    ),
  ).length;
}

// -- Component ---------------------------------------------------------------

export const IBDashboard: React.FC = () => {
  const {
    data: certData,
    isLoading,
    isError,
    error,
  } = useQuery<StaffCertsResponse>({
    queryKey: ['staffCertifications'],
    queryFn: async () => {
      const res = await api.get('/tenants/staff-certifications/');
      return res.data;
    },
  });

  const summary = certData?.summary;
  const teachers = certData?.teachers ?? [];

  // Compute IB training compliance (Cat 1 workshops)
  const ibTrainingPct = summary?.ib_trained_percentage ?? 0;

  // Compute safety compliance: teachers with POCSO + First Aid + Fire Safety
  const safetyCompliance = useMemo(() => {
    if (teachers.length === 0) return { count: 0, pct: 0 };
    const compliant = teachers.filter((t) => {
      const validTypes = new Set(
        t.certifications
          .filter((c) => c.status === 'VALID' || c.status === 'EXPIRING')
          .map((c) => c.certification_type),
      );
      return SAFETY_CERT_TYPES.every((type) => validTypes.has(type));
    });
    return {
      count: compliant.length,
      pct: Math.round((compliant.length / teachers.length) * 100),
    };
  }, [teachers]);

  // Overall compliance rate from summary
  const overallComplianceRate = useMemo(() => {
    if (!summary?.compliance_categories) return 0;
    const cats = Object.values(summary.compliance_categories);
    if (cats.length === 0) return 0;
    const totalRequired = cats.reduce((s, c) => s + c.required, 0);
    const totalCompleted = cats.reduce((s, c) => s + c.completed, 0);
    return totalRequired > 0 ? Math.round((totalCompleted / totalRequired) * 100) : 0;
  }, [summary]);

  // Per-certification breakdown
  const certBreakdown = useMemo(() => {
    if (teachers.length === 0) return [];
    return ALL_TRACKED_TYPES.map((type) => {
      const certified = countCertified(teachers, type);
      const expiring = countExpiring(teachers, type);
      const pct = compliancePercent(certified, teachers.length);
      return {
        type,
        label: CERT_LABELS[type] || type,
        required: teachers.length,
        certified,
        expiring,
        pct,
      };
    }).sort((a, b) => a.pct - b.pct); // lowest first
  }, [teachers]);

  // Gap analysis: teachers missing IB Cat 1 or safety certs
  const gapAnalysis = useMemo(() => {
    if (teachers.length === 0) return [];
    const requiredTypes = ['IB_CAT1', ...SAFETY_CERT_TYPES];
    return teachers
      .map((teacher) => {
        const validTypes = new Set(
          teacher.certifications
            .filter((c) => c.status === 'VALID' || c.status === 'EXPIRING')
            .map((c) => c.certification_type),
        );
        const missing = requiredTypes.filter((type) => !validTypes.has(type));
        return { teacher, missing };
      })
      .filter((entry) => entry.missing.length > 0)
      .sort((a, b) => b.missing.length - a.missing.length);
  }, [teachers]);

  // Loading state
  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Card key={i} className="animate-pulse">
              <CardHeader className="pb-2">
                <div className="h-4 bg-gray-200 rounded w-2/3" />
              </CardHeader>
              <CardContent>
                <div className="h-8 bg-gray-200 rounded w-1/3" />
              </CardContent>
            </Card>
          ))}
        </div>
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-8 w-8 text-indigo-400 animate-spin" />
        </div>
      </div>
    );
  }

  // Error state
  if (isError) {
    return (
      <div className="text-center py-12">
        <ShieldAlert className="h-12 w-12 mx-auto mb-3 text-red-300" />
        <p className="text-gray-700 font-medium">Failed to load IB compliance data</p>
        <p className="text-sm text-gray-500 mt-1">
          {(error as any)?.message || 'Please try again later.'}
        </p>
      </div>
    );
  }

  const totalExpiring = summary?.expiring_count ?? 0;

  return (
    <div className="space-y-6">
      {/* Summary cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-gray-500">
              IB Training Compliance
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-3">
              <GraduationCap className={cn('h-8 w-8', complianceColor(ibTrainingPct))} />
              <div>
                <span className={cn('text-3xl font-bold', complianceColor(ibTrainingPct))}>
                  {ibTrainingPct}%
                </span>
                <span className="text-sm text-gray-400 ml-1">
                  ({summary?.ib_trained_count ?? 0}/{summary?.total_teachers ?? 0})
                </span>
              </div>
            </div>
            <p className="text-xs text-gray-500 mt-2">
              Teachers with IB Cat 1 workshop
            </p>
            <div className="mt-1 h-2 w-full rounded-full bg-gray-200">
              <div
                className={cn('h-2 rounded-full transition-all', progressBarColor(ibTrainingPct))}
                style={{ width: `${Math.min(ibTrainingPct, 100)}%` }}
              />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-gray-500">
              Safety Compliance
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-3">
              <ShieldCheck className={cn('h-8 w-8', complianceColor(safetyCompliance.pct))} />
              <div>
                <span className={cn('text-3xl font-bold', complianceColor(safetyCompliance.pct))}>
                  {safetyCompliance.pct}%
                </span>
                <span className="text-sm text-gray-400 ml-1">
                  ({safetyCompliance.count}/{teachers.length})
                </span>
              </div>
            </div>
            <p className="text-xs text-gray-500 mt-2">
              POCSO + First Aid + Fire Safety
            </p>
            <div className="mt-1 h-2 w-full rounded-full bg-gray-200">
              <div
                className={cn('h-2 rounded-full transition-all', progressBarColor(safetyCompliance.pct))}
                style={{ width: `${Math.min(safetyCompliance.pct, 100)}%` }}
              />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-gray-500">
              Overall PD Compliance
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-3">
              <CheckCircle className={cn('h-8 w-8', complianceColor(overallComplianceRate))} />
              <span className={cn('text-3xl font-bold', complianceColor(overallComplianceRate))}>
                {overallComplianceRate}%
              </span>
            </div>
            <p className="text-xs text-gray-500 mt-2">
              Across all tracked certifications
            </p>
            <div className="mt-1 h-2 w-full rounded-full bg-gray-200">
              <div
                className={cn('h-2 rounded-full transition-all', progressBarColor(overallComplianceRate))}
                style={{ width: `${Math.min(overallComplianceRate, 100)}%` }}
              />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-gray-500">
              Expiring Certifications
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-3">
              <AlertTriangle
                className={cn(
                  'h-8 w-8',
                  totalExpiring > 0 ? 'text-amber-500' : 'text-gray-300',
                )}
              />
              <span
                className={cn(
                  'text-3xl font-bold',
                  totalExpiring > 0 ? 'text-amber-600' : 'text-gray-900',
                )}
              >
                {totalExpiring}
              </span>
            </div>
            <p className="text-xs text-gray-500 mt-2">
              Within the next 30 days
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Per-certification compliance breakdown */}
      {certBreakdown.length > 0 && (
        <div>
          <h3 className="text-lg font-semibold text-gray-900 mb-3">
            Per-Certification Compliance
          </h3>
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5 space-y-4">
            {certBreakdown.map((bar) => (
              <div key={bar.type} className="space-y-1">
                <div className="flex items-center justify-between text-sm">
                  <span className="font-medium text-gray-700">{bar.label}</span>
                  <div className="flex items-center gap-2">
                    {bar.expiring > 0 && (
                      <span className="text-xs text-amber-600 font-medium">
                        {bar.expiring} expiring
                      </span>
                    )}
                    <span className={cn('font-semibold', complianceColor(bar.pct))}>
                      {bar.certified}/{bar.required} ({bar.pct}%)
                    </span>
                  </div>
                </div>
                <div className={cn('h-3 w-full rounded-full', progressBarBgColor(bar.pct))}>
                  <div
                    className={cn(
                      'h-3 rounded-full transition-all duration-700 ease-out',
                      progressBarColor(bar.pct),
                    )}
                    style={{ width: `${Math.min(bar.pct, 100)}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Gap Analysis */}
      <div>
        <h3 className="text-lg font-semibold text-gray-900 mb-3">
          Gap Analysis
        </h3>
        <p className="text-sm text-gray-500 mb-4">
          Teachers missing required certifications (IB Cat 1, POCSO, First Aid, Fire Safety).
          Addresses DPDPA (Digital Personal Data Protection Act) compliance requirements.
        </p>

        {gapAnalysis.length === 0 ? (
          <div className="text-center py-8 bg-white rounded-xl border border-gray-200">
            <CheckCircle className="h-10 w-10 mx-auto mb-2 text-emerald-400" />
            <p className="text-sm font-medium text-gray-700">
              All teachers have the required certifications.
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
                      Teacher
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Missing Certifications
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Gaps
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-100">
                  {gapAnalysis.slice(0, 20).map(({ teacher, missing }) => (
                    <tr key={teacher.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3">
                        <div className="text-sm font-medium text-gray-900">
                          {teacher.name}
                        </div>
                        <div className="text-xs text-gray-500">{teacher.email}</div>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex flex-wrap gap-1.5">
                          {missing.map((type) => (
                            <span
                              key={type}
                              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-red-50 text-red-700 border border-red-200"
                            >
                              <XCircle className="h-3 w-3" />
                              {CERT_LABELS[type] || type}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <Badge variant="destructive">{missing.length}</Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {gapAnalysis.length > 20 && (
                <div className="px-4 py-3 bg-gray-50 border-t border-gray-200 text-sm text-gray-500">
                  Showing 20 of {gapAnalysis.length} teachers with gaps.
                  View the Staff PD Tracker for the complete list.
                </div>
              )}
            </div>

            {/* Mobile cards */}
            <div className="md:hidden space-y-3">
              {gapAnalysis.slice(0, 10).map(({ teacher, missing }) => (
                <div
                  key={teacher.id}
                  className="bg-white rounded-xl border border-gray-200 shadow-sm p-4"
                >
                  <div className="flex items-start justify-between mb-2">
                    <div>
                      <p className="text-sm font-semibold text-gray-900">
                        {teacher.name}
                      </p>
                      <p className="text-xs text-gray-500">{teacher.email}</p>
                    </div>
                    <Badge variant="destructive">{missing.length} gaps</Badge>
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {missing.map((type) => (
                      <span
                        key={type}
                        className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-red-50 text-red-700 border border-red-200"
                      >
                        <XCircle className="h-3 w-3" />
                        {CERT_LABELS[type] || type}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
              {gapAnalysis.length > 10 && (
                <p className="text-sm text-center text-gray-500 py-2">
                  + {gapAnalysis.length - 10} more teachers with gaps
                </p>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
};
