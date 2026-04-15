// src/pages/teacher/MyCertificationsPage.tsx
//
// Teacher self-service view of their professional development certifications.
// Shows summary cards, required certifications checklist, and full cert list.

import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Clock,
  Shield,
  Award,
  ExternalLink,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { cn } from '../../design-system/theme/cn';
import { usePageTitle } from '../../hooks/usePageTitle';
import api from '../../config/api';

// ── Types ──────────────────────────────────────────────────────────────

interface CertSummary {
  total: number;
  completed: number;
  expiring: number;
  expired: number;
  required_total: number;
  required_met: number;
  missing_count: number;
}

interface Certification {
  id: string;
  certification_type: string;
  certification_type_display: string;
  custom_name: string;
  status: 'VALID' | 'EXPIRING' | 'EXPIRED' | 'NOT_STARTED';
  completed_date: string | null;
  expiry_date: string | null;
  certificate_url: string;
  provider: string;
  notes: string;
}

interface RequiredCert {
  certification_type: string;
  display_name: string;
  status: 'VALID' | 'EXPIRING' | 'EXPIRED' | 'NOT_STARTED';
  held: boolean;
}

interface MissingCert {
  certification_type: string;
  display_name: string;
  reason: 'not_started' | 'expired';
}

interface MyCertsResponse {
  summary: CertSummary;
  certifications: Certification[];
  required: RequiredCert[];
  missing: MissingCert[];
}

// ── Helpers ────────────────────────────────────────────────────────────

const STATUS_CONFIG: Record<string, { label: string; color: string; bg: string; icon: React.ElementType }> = {
  VALID: { label: 'Valid', color: 'text-green-700', bg: 'bg-green-50 border-green-200', icon: CheckCircle2 },
  EXPIRING: { label: 'Expiring Soon', color: 'text-amber-700', bg: 'bg-amber-50 border-amber-200', icon: AlertTriangle },
  EXPIRED: { label: 'Expired', color: 'text-red-700', bg: 'bg-red-50 border-red-200', icon: XCircle },
  NOT_STARTED: { label: 'Not Started', color: 'text-gray-500', bg: 'bg-gray-50 border-gray-200', icon: Clock },
};

function formatDate(d: string | null): string {
  if (!d) return '—';
  return new Date(d).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
}

function daysUntil(d: string | null): number | null {
  if (!d) return null;
  const diff = Math.ceil((new Date(d).getTime() - Date.now()) / 86400000);
  return diff;
}

// ── Component ──────────────────────────────────────────────────────────

export function MyCertificationsPage() {
  usePageTitle('My Certifications');
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const { data, isLoading, error } = useQuery<MyCertsResponse>({
    queryKey: ['my-certifications'],
    queryFn: () => api.get('/teacher/certifications/').then((r) => r.data),
  });

  if (isLoading) {
    return (
      <div className="space-y-6 p-6">
        <div className="h-8 w-64 bg-gray-200 rounded animate-pulse" />
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-24 bg-gray-100 rounded-xl animate-pulse" />
          ))}
        </div>
        <div className="space-y-3">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-16 bg-gray-100 rounded-lg animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="p-6">
        <div className="bg-red-50 border border-red-200 rounded-xl p-6 text-center">
          <XCircle className="h-8 w-8 text-red-400 mx-auto mb-2" />
          <p className="text-red-700 font-medium">Failed to load certifications</p>
          <p className="text-red-500 text-sm mt-1">Please try refreshing the page.</p>
        </div>
      </div>
    );
  }

  const { summary, certifications, required, missing } = data;
  const compliancePercent = summary.required_total > 0
    ? Math.round((summary.required_met / summary.required_total) * 100)
    : 0;

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">My Certifications & PD</h1>
        <p className="mt-1 text-sm text-gray-500">
          Track your professional development, required certifications, and training status.
        </p>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <SummaryCard
          title="Compliance"
          value={`${compliancePercent}%`}
          subtitle={`${summary.required_met} of ${summary.required_total} required`}
          color={compliancePercent === 100 ? 'green' : compliancePercent >= 60 ? 'amber' : 'red'}
          icon={Shield}
        />
        <SummaryCard
          title="Valid Certifications"
          value={summary.completed}
          subtitle={`${summary.total} total tracked`}
          color="green"
          icon={CheckCircle2}
        />
        <SummaryCard
          title="Expiring Soon"
          value={summary.expiring}
          subtitle="Within 90 days"
          color={summary.expiring > 0 ? 'amber' : 'green'}
          icon={AlertTriangle}
        />
        <SummaryCard
          title="Action Needed"
          value={summary.missing_count + summary.expired}
          subtitle="Missing or expired"
          color={summary.missing_count + summary.expired > 0 ? 'red' : 'green'}
          icon={Award}
        />
      </div>

      {/* Required Certifications Checklist */}
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-100">
          <h2 className="text-base font-semibold text-gray-900">Required Certifications</h2>
          <p className="text-xs text-gray-500 mt-0.5">
            These certifications are mandatory for all teaching staff.
          </p>
        </div>
        <div className="divide-y divide-gray-100">
          {required.map((req) => {
            const cfg = STATUS_CONFIG[req.status];
            const Icon = cfg.icon;
            return (
              <div key={req.certification_type} className="flex items-center gap-3 px-5 py-3">
                <Icon className={cn('h-5 w-5 flex-shrink-0', cfg.color)} />
                <span className="flex-1 text-sm font-medium text-gray-800">{req.display_name}</span>
                <span className={cn('text-xs font-medium px-2.5 py-1 rounded-full border', cfg.bg, cfg.color)}>
                  {cfg.label}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Missing / Action Items */}
      {missing.length > 0 && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-5">
          <h3 className="text-sm font-semibold text-red-800 mb-2">Action Required</h3>
          <ul className="space-y-1.5">
            {missing.map((m) => (
              <li key={m.certification_type} className="flex items-center gap-2 text-sm text-red-700">
                <XCircle className="h-4 w-4 flex-shrink-0" />
                <span>
                  <strong>{m.display_name}</strong>
                  {m.reason === 'expired' ? ' — Certificate has expired, renewal required' : ' — Not yet completed'}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* All Certifications */}
      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-100">
          <h2 className="text-base font-semibold text-gray-900">All Certifications</h2>
          <p className="text-xs text-gray-500 mt-0.5">
            Complete list of your professional development records.
          </p>
        </div>

        {certifications.length === 0 ? (
          <div className="px-5 py-12 text-center">
            <Award className="h-10 w-10 text-gray-300 mx-auto mb-3" />
            <p className="text-sm text-gray-500">No certifications recorded yet.</p>
            <p className="text-xs text-gray-400 mt-1">Contact your admin to add your PD records.</p>
          </div>
        ) : (
          <div className="divide-y divide-gray-100">
            {certifications.map((cert) => {
              const cfg = STATUS_CONFIG[cert.status];
              const Icon = cfg.icon;
              const isExpanded = expandedId === cert.id;
              const days = daysUntil(cert.expiry_date);

              return (
                <div key={cert.id} className="group">
                  <button
                    onClick={() => setExpandedId(isExpanded ? null : cert.id)}
                    className="w-full flex items-center gap-3 px-5 py-3.5 text-left hover:bg-gray-50 transition-colors"
                  >
                    <Icon className={cn('h-5 w-5 flex-shrink-0', cfg.color)} />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-gray-800 truncate">
                        {cert.certification_type_display}
                        {cert.custom_name && <span className="text-gray-500"> — {cert.custom_name}</span>}
                      </p>
                      {cert.provider && (
                        <p className="text-xs text-gray-400 truncate">{cert.provider}</p>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      {cert.status === 'EXPIRING' && days !== null && (
                        <span className="text-xs font-medium text-amber-600">{days}d left</span>
                      )}
                      <span className={cn('text-xs font-medium px-2 py-0.5 rounded-full border', cfg.bg, cfg.color)}>
                        {cfg.label}
                      </span>
                      {isExpanded ? (
                        <ChevronUp className="h-4 w-4 text-gray-400" />
                      ) : (
                        <ChevronDown className="h-4 w-4 text-gray-400" />
                      )}
                    </div>
                  </button>

                  {isExpanded && (
                    <div className="px-5 pb-4 pt-0 ml-8 grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-2 text-sm">
                      <div>
                        <span className="text-gray-400 text-xs">Completed</span>
                        <p className="text-gray-700">{formatDate(cert.completed_date)}</p>
                      </div>
                      <div>
                        <span className="text-gray-400 text-xs">Expires</span>
                        <p className="text-gray-700">{formatDate(cert.expiry_date)}</p>
                      </div>
                      {cert.provider && (
                        <div>
                          <span className="text-gray-400 text-xs">Provider</span>
                          <p className="text-gray-700">{cert.provider}</p>
                        </div>
                      )}
                      {cert.certificate_url && (
                        <div>
                          <span className="text-gray-400 text-xs">Certificate</span>
                          <a
                            href={cert.certificate_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="flex items-center gap-1 text-indigo-600 hover:text-indigo-800"
                          >
                            View Certificate <ExternalLink className="h-3.5 w-3.5" />
                          </a>
                        </div>
                      )}
                      {cert.notes && (
                        <div className="sm:col-span-2">
                          <span className="text-gray-400 text-xs">Notes</span>
                          <p className="text-gray-700">{cert.notes}</p>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Summary Card ───────────────────────────────────────────────────────

function SummaryCard({
  title,
  value,
  subtitle,
  color,
  icon: Icon,
}: {
  title: string;
  value: string | number;
  subtitle: string;
  color: 'green' | 'amber' | 'red';
  icon: React.ElementType;
}) {
  const colors = {
    green: { bg: 'bg-green-50', border: 'border-green-200', icon: 'text-green-500', value: 'text-green-700' },
    amber: { bg: 'bg-amber-50', border: 'border-amber-200', icon: 'text-amber-500', value: 'text-amber-700' },
    red: { bg: 'bg-red-50', border: 'border-red-200', icon: 'text-red-500', value: 'text-red-700' },
  }[color];

  return (
    <div className={cn('rounded-xl border p-4', colors.bg, colors.border)}>
      <div className="flex items-center justify-between">
        <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">{title}</p>
        <Icon className={cn('h-5 w-5', colors.icon)} />
      </div>
      <p className={cn('text-2xl font-bold mt-1', colors.value)}>{value}</p>
      <p className="text-xs text-gray-500 mt-0.5">{subtitle}</p>
    </div>
  );
}
