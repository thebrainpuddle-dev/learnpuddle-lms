// src/components/certifications/StaffPDTrackerTab.tsx
//
// Staff Professional Development (PD) Tracker. Shows certification compliance
// across all teachers with summary cards, compliance breakdown bars, a
// teacher-certification matrix, and CRUD operations via modal forms.

import React, { Fragment, useMemo, useState, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Dialog, Transition } from '@headlessui/react';
import { z } from 'zod';
import { Controller } from 'react-hook-form';
import {
  GraduationCap,
  Award,
  Shield,
  ShieldCheck,
  ShieldAlert,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Clock,
  Users,
  Plus,
  Pencil,
  Trash2,
  Search,
  Filter,
  X,
  Loader2,
  ChevronDown,
  ExternalLink,
  FileText,
} from 'lucide-react';
import api from '../../config/api';
import { cn } from '../../lib/utils';
import { useZodForm } from '../../hooks/useZodForm';
import { useToast } from '../../components/common';
import { Badge } from '../../components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/common/Button';

// -- Types -------------------------------------------------------------------

interface StaffCert {
  id: string;
  certification_type: string;
  display_name: string;
  custom_name: string;
  status: 'VALID' | 'EXPIRING' | 'EXPIRED' | 'NOT_STARTED';
  completed_date: string | null;
  expiry_date: string | null;
  certificate_url: string;
  provider: string;
  notes: string;
  created_at: string;
  updated_at: string;
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

interface TeacherOption {
  id: string;
  first_name: string;
  last_name: string;
  email: string;
}

// -- Constants ---------------------------------------------------------------

const CERT_TYPE_OPTIONS = [
  { value: 'IB_CAT1', label: 'IB Category 1 Workshop' },
  { value: 'IB_CAT2', label: 'IB Category 2 Workshop' },
  { value: 'IB_CAT3', label: 'IB Category 3 Workshop' },
  { value: 'IB_LEADER', label: 'IB Leadership Workshop' },
  { value: 'FIRST_AID', label: 'First Aid Certification' },
  { value: 'POCSO', label: 'POCSO Awareness Training' },
  { value: 'POSH', label: 'POSH Training' },
  { value: 'FIRE_SAFETY', label: 'Fire Safety Training' },
  { value: 'CHILD_SAFEGUARDING', label: 'Child Safeguarding' },
  { value: 'CWSN', label: 'CWSN (Children with Special Needs) Training' },
  { value: 'CPR', label: 'CPR Certification' },
  { value: 'GOOGLE_CERT', label: 'Google Certified Educator' },
  { value: 'MENTAL_HEALTH', label: 'Mental Health & Wellbeing Training' },
  { value: 'ANTI_BULLYING', label: 'Anti-Bullying Training' },
  { value: 'BACKGROUND_CHECK', label: 'Background / Police Verification' },
  { value: 'TEACHING_LICENSE', label: 'Teaching License' },
  { value: 'SUBJECT_CERT', label: 'Subject Specialization Certificate' },
  { value: 'DIGITAL_LITERACY', label: 'Digital Literacy / EdTech Training' },
  { value: 'NEP_TRAINING', label: 'NEP 2020 Training' },
  { value: 'OTHER', label: 'Other' },
] as const;

const CERT_TYPE_DISPLAY: Record<string, string> = Object.fromEntries(
  CERT_TYPE_OPTIONS.map((t) => [t.value, t.label]),
);

/** Default visible columns in the teacher matrix */
const DEFAULT_VISIBLE_COLUMNS = [
  'IB_CAT1',
  'IB_CAT2',
  'POCSO',
  'FIRST_AID',
  'FIRE_SAFETY',
  'CHILD_SAFEGUARDING',
] as const;

const ALL_COLUMN_OPTIONS = CERT_TYPE_OPTIONS.map((t) => t.value);

type CertStatus = StaffCert['status'];

const STATUS_CONFIG: Record<
  CertStatus,
  {
    color: string;
    bgColor: string;
    badgeVariant: 'success' | 'warning' | 'destructive' | 'secondary';
    label: string;
  }
> = {
  VALID: { color: 'text-emerald-600', bgColor: 'bg-emerald-50', badgeVariant: 'success', label: 'Valid' },
  EXPIRING: { color: 'text-amber-600', bgColor: 'bg-amber-50', badgeVariant: 'warning', label: 'Expiring Soon' },
  EXPIRED: { color: 'text-red-600', bgColor: 'bg-red-50', badgeVariant: 'destructive', label: 'Expired' },
  NOT_STARTED: { color: 'text-gray-400', bgColor: 'bg-gray-50', badgeVariant: 'secondary', label: 'Not Started' },
};

type FilterStatus = 'ALL' | 'COMPLIANT' | 'NEEDS_TRAINING' | 'EXPIRING';

// -- Helpers -----------------------------------------------------------------

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '--';
  return new Date(dateStr).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
  });
}

function formatDateFull(dateStr: string | null): string {
  if (!dateStr) return '--';
  return new Date(dateStr).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

function progressBarColor(pct: number): string {
  if (pct >= 80) return 'bg-emerald-500';
  if (pct >= 50) return 'bg-amber-500';
  return 'bg-red-500';
}

function progressBarBgColor(pct: number): string {
  if (pct >= 80) return 'bg-emerald-100';
  if (pct >= 50) return 'bg-amber-100';
  return 'bg-red-100';
}

function complianceTextColor(pct: number): string {
  if (pct >= 80) return 'text-emerald-700';
  if (pct >= 50) return 'text-amber-700';
  return 'text-red-700';
}

function badgeVariantForPct(pct: number): 'success' | 'warning' | 'destructive' {
  if (pct >= 80) return 'success';
  if (pct >= 50) return 'warning';
  return 'destructive';
}

/** Check if a teacher is "IB trained" (has at least IB_CAT1 with VALID status) */
function isTeacherIBTrained(certs: StaffCert[]): boolean {
  return certs.some(
    (c) => c.certification_type === 'IB_CAT1' && c.status === 'VALID',
  );
}

/** Check if a teacher is "fully compliant" (all default columns are VALID) */
function isTeacherCompliant(certs: StaffCert[]): boolean {
  const validTypes = new Set(
    certs.filter((c) => c.status === 'VALID').map((c) => c.certification_type),
  );
  return DEFAULT_VISIBLE_COLUMNS.every((col) => validTypes.has(col));
}

/** Check if a teacher has any expiring certs */
function hasExpiringCerts(certs: StaffCert[]): boolean {
  return certs.some((c) => c.status === 'EXPIRING');
}

// -- Zod Schema --------------------------------------------------------------

const CertFormSchema = z.object({
  teacher_id: z.string().min(1, 'Teacher is required'),
  certification_type: z.string().min(1, 'Certification type is required'),
  custom_name: z.string().max(200).optional().default(''),
  completed_date: z.string().optional().default(''),
  expiry_date: z.string().optional().default(''),
  provider: z.string().max(200).optional().default(''),
  certificate_url: z
    .string()
    .url('Must be a valid URL')
    .or(z.literal(''))
    .optional()
    .default(''),
  notes: z.string().max(2000).optional().default(''),
});

type CertFormData = z.infer<typeof CertFormSchema>;

// -- Skeleton ----------------------------------------------------------------

function SkeletonRow() {
  return (
    <div className="animate-pulse flex items-center gap-4 px-4 py-3 border-b border-gray-100">
      <div className="h-4 bg-gray-200 rounded w-32" />
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="h-6 w-6 bg-gray-200 rounded-full" />
      ))}
    </div>
  );
}

function SkeletonCards() {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {Array.from({ length: 4 }).map((_, i) => (
        <Card key={i}>
          <CardHeader className="pb-2">
            <div className="h-4 bg-gray-200 rounded w-24 animate-pulse" />
          </CardHeader>
          <CardContent>
            <div className="h-8 bg-gray-200 rounded w-16 animate-pulse" />
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

// -- Component ---------------------------------------------------------------

export function StaffPDTrackerTab() {
  const queryClient = useQueryClient();
  const toast = useToast();

  // ---- State ---------------------------------------------------------------
  const [searchQuery, setSearchQuery] = useState('');
  const [filterStatus, setFilterStatus] = useState<FilterStatus>('ALL');
  const [visibleColumns, setVisibleColumns] = useState<string[]>([
    ...DEFAULT_VISIBLE_COLUMNS,
  ]);
  const [showColumnPicker, setShowColumnPicker] = useState(false);
  const [sortAsc, setSortAsc] = useState(true);

  // Modal state
  const [modalOpen, setModalOpen] = useState(false);
  const [editingCert, setEditingCert] = useState<(StaffCert & { teacher_id: string }) | null>(null);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);

  // Cell click: opens modal pre-filled with teacher+type
  const [prefillTeacherId, setPrefillTeacherId] = useState('');
  const [prefillCertType, setPrefillCertType] = useState('');

  // ---- Data ----------------------------------------------------------------
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

  const { data: teachersList } = useQuery<TeacherOption[]>({
    queryKey: ['teachersList'],
    queryFn: async () => {
      const res = await api.get('/teachers/');
      return res.data.results ?? res.data;
    },
  });

  // ---- Mutations -----------------------------------------------------------
  const createMutation = useMutation({
    mutationFn: (data: CertFormData) =>
      api.post('/tenants/staff-certifications/create/', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['staffCertifications'] });
      toast.success('Certification added');
      closeModal();
    },
    onError: (err: any) => {
      const detail =
        err?.response?.data?.detail ||
        Object.values(err?.response?.data || {}).flat().join('. ') ||
        'Failed to create certification';
      toast.error(String(detail));
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<CertFormData> }) =>
      api.patch(`/tenants/staff-certifications/${id}/update/`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['staffCertifications'] });
      toast.success('Certification updated');
      closeModal();
    },
    onError: (err: any) => {
      const detail =
        err?.response?.data?.detail ||
        Object.values(err?.response?.data || {}).flat().join('. ') ||
        'Failed to update certification';
      toast.error(String(detail));
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) =>
      api.delete(`/tenants/staff-certifications/${id}/delete/`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['staffCertifications'] });
      toast.success('Certification deleted');
      setDeleteConfirmId(null);
    },
    onError: () => {
      toast.error('Failed to delete certification');
    },
  });

  // ---- Modal helpers -------------------------------------------------------
  function openCreateModal(teacherId = '', certType = '') {
    setEditingCert(null);
    setPrefillTeacherId(teacherId);
    setPrefillCertType(certType);
    setModalOpen(true);
  }

  function openEditModal(cert: StaffCert, teacherId: string) {
    setEditingCert({ ...cert, teacher_id: teacherId });
    setPrefillTeacherId('');
    setPrefillCertType('');
    setModalOpen(true);
  }

  function closeModal() {
    setModalOpen(false);
    setEditingCert(null);
    setPrefillTeacherId('');
    setPrefillCertType('');
  }

  // ---- Derived data --------------------------------------------------------
  const summary = certData?.summary;
  const teachers = certData?.teachers ?? [];

  // Compute overall compliance rate
  const overallComplianceRate = useMemo(() => {
    if (!summary?.compliance_categories) return 0;
    const cats = Object.values(summary.compliance_categories);
    if (cats.length === 0) return 0;
    const totalRequired = cats.reduce((s, c) => s + c.required, 0);
    const totalCompleted = cats.reduce((s, c) => s + c.completed, 0);
    return totalRequired > 0 ? Math.round((totalCompleted / totalRequired) * 100) : 0;
  }, [summary]);

  // Filter and sort teachers
  const filteredTeachers = useMemo(() => {
    let list = [...teachers];

    // Search by name
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      list = list.filter(
        (t) =>
          t.name.toLowerCase().includes(q) ||
          t.email.toLowerCase().includes(q),
      );
    }

    // Filter by status
    if (filterStatus === 'COMPLIANT') {
      list = list.filter((t) => isTeacherCompliant(t.certifications));
    } else if (filterStatus === 'NEEDS_TRAINING') {
      list = list.filter((t) => !isTeacherCompliant(t.certifications));
    } else if (filterStatus === 'EXPIRING') {
      list = list.filter((t) => hasExpiringCerts(t.certifications));
    }

    // Sort by name
    list.sort((a, b) => {
      const cmp = a.name.localeCompare(b.name);
      return sortAsc ? cmp : -cmp;
    });

    return list;
  }, [teachers, searchQuery, filterStatus, sortAsc]);

  // Build compliance bars data
  const complianceBars = useMemo(() => {
    if (!summary?.compliance_categories) return [];
    return Object.entries(summary.compliance_categories).map(([key, val]) => ({
      type: key,
      label: CERT_TYPE_DISPLAY[key] || key,
      required: val.required,
      completed: val.completed,
      pct: val.required > 0 ? Math.round((val.completed / val.required) * 100) : 0,
    }));
  }, [summary]);

  // ---- Render helpers ------------------------------------------------------

  /** Render a certification cell in the teacher matrix */
  const renderCertCell = useCallback(
    (teacher: TeacherWithCerts, certType: string) => {
      const cert = teacher.certifications.find(
        (c) => c.certification_type === certType,
      );

      if (!cert) {
        // Not started -- clickable to add
        return (
          <button
            onClick={() => openCreateModal(teacher.id, certType)}
            className="flex items-center justify-center w-full h-full py-1 text-gray-300 hover:text-gray-500 transition-colors"
            title={`Add ${CERT_TYPE_DISPLAY[certType]} for ${teacher.name}`}
          >
            <span className="text-lg">--</span>
          </button>
        );
      }

      const cfg = STATUS_CONFIG[cert.status];
      let Icon = CheckCircle;
      if (cert.status === 'EXPIRING') Icon = AlertTriangle;
      if (cert.status === 'EXPIRED') Icon = XCircle;
      if (cert.status === 'NOT_STARTED') Icon = Clock;

      return (
        <button
          onClick={() => openEditModal(cert, teacher.id)}
          className={cn(
            'flex flex-col items-center justify-center w-full h-full py-1 rounded transition-colors',
            `hover:${cfg.bgColor}`,
          )}
          title={`${cfg.label}${cert.completed_date ? ` - ${formatDate(cert.completed_date)}` : ''}`}
        >
          <Icon className={cn('h-4 w-4', cfg.color)} />
          {cert.completed_date && (
            <span className={cn('text-[10px] mt-0.5 leading-tight', cfg.color)}>
              {formatDate(cert.completed_date)}
            </span>
          )}
        </button>
      );
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [openCreateModal, openEditModal],
  );

  // ---- Loading / Error states -----------------------------------------------

  if (isLoading) {
    return (
      <div className="space-y-6">
        <SkeletonCards />
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
          {Array.from({ length: 5 }).map((_, i) => (
            <SkeletonRow key={i} />
          ))}
        </div>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="text-center py-12">
        <ShieldAlert className="h-12 w-12 mx-auto mb-3 text-red-300" />
        <p className="text-gray-700 font-medium">Failed to load staff certifications</p>
        <p className="text-sm text-gray-500 mt-1">
          {(error as any)?.message || 'Please try again later.'}
        </p>
      </div>
    );
  }

  // ---- Main render ----------------------------------------------------------

  return (
    <div className="space-y-6">
      {/* ──── Summary Cards ──────────────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-gray-500">
              Total Teachers
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-3">
              <Users className="h-8 w-8 text-indigo-500" />
              <span className="text-3xl font-bold text-gray-900">
                {summary?.total_teachers ?? 0}
              </span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-gray-500">
              IB Trained
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-3">
              <GraduationCap className="h-8 w-8 text-blue-500" />
              <div>
                <span className={cn('text-3xl font-bold', complianceTextColor(summary?.ib_trained_percentage ?? 0))}>
                  {summary?.ib_trained_percentage ?? 0}%
                </span>
                <span className="text-sm text-gray-400 ml-1">
                  ({summary?.ib_trained_count ?? 0}/{summary?.total_teachers ?? 0})
                </span>
              </div>
            </div>
            <div className="mt-2 h-2 w-full rounded-full bg-gray-200">
              <div
                className={cn(
                  'h-2 rounded-full transition-all duration-700 ease-out',
                  progressBarColor(summary?.ib_trained_percentage ?? 0),
                )}
                style={{ width: `${Math.min(summary?.ib_trained_percentage ?? 0, 100)}%` }}
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
                  (summary?.expiring_count ?? 0) > 0 ? 'text-amber-500' : 'text-gray-300',
                )}
              />
              <span
                className={cn(
                  'text-3xl font-bold',
                  (summary?.expiring_count ?? 0) > 0 ? 'text-amber-600' : 'text-gray-900',
                )}
              >
                {summary?.expiring_count ?? 0}
              </span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-gray-500">
              Compliance Rate
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-3">
              <ShieldCheck className={cn('h-8 w-8', complianceTextColor(overallComplianceRate))} />
              <span className={cn('text-3xl font-bold', complianceTextColor(overallComplianceRate))}>
                {overallComplianceRate}%
              </span>
            </div>
            <div className="mt-2 h-2 w-full rounded-full bg-gray-200">
              <div
                className={cn(
                  'h-2 rounded-full transition-all duration-700 ease-out',
                  progressBarColor(overallComplianceRate),
                )}
                style={{ width: `${Math.min(overallComplianceRate, 100)}%` }}
              />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* ──── Compliance Breakdown Bars ──────────────────────────────── */}
      {complianceBars.length > 0 && (
        <div>
          <h3 className="text-lg font-semibold text-gray-900 mb-3">
            Certification Compliance Breakdown
          </h3>
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5 space-y-4">
            {complianceBars.map((bar) => (
              <div key={bar.type} className="space-y-1">
                <div className="flex items-center justify-between text-sm">
                  <span className="font-medium text-gray-700">{bar.label}</span>
                  <span className={cn('font-semibold', complianceTextColor(bar.pct))}>
                    {bar.completed}/{bar.required} ({bar.pct}%)
                  </span>
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

      {/* ──── Filter Bar ─────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3">
        {/* Search */}
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search teacher name..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9 pr-3 py-2 w-full text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>

        {/* Status filter */}
        <select
          value={filterStatus}
          onChange={(e) => setFilterStatus(e.target.value as FilterStatus)}
          className="px-3 py-2 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white"
        >
          <option value="ALL">All Teachers</option>
          <option value="COMPLIANT">Compliant</option>
          <option value="NEEDS_TRAINING">Needs Training</option>
          <option value="EXPIRING">Expiring</option>
        </select>

        {/* Column picker toggle */}
        <div className="relative">
          <button
            onClick={() => setShowColumnPicker(!showColumnPicker)}
            className="flex items-center gap-1.5 px-3 py-2 text-sm border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
          >
            <Filter className="h-4 w-4 text-gray-500" />
            Columns
            <ChevronDown className="h-3 w-3 text-gray-400" />
          </button>
          {showColumnPicker && (
            <div className="absolute right-0 mt-1 w-64 bg-white border border-gray-200 rounded-lg shadow-lg z-20 p-3 max-h-72 overflow-y-auto">
              <p className="text-xs font-semibold text-gray-500 uppercase mb-2">
                Visible Columns
              </p>
              {ALL_COLUMN_OPTIONS.map((col) => (
                <label
                  key={col}
                  className="flex items-center gap-2 py-1 text-sm text-gray-700 cursor-pointer hover:bg-gray-50 rounded px-1"
                >
                  <input
                    type="checkbox"
                    checked={visibleColumns.includes(col)}
                    onChange={(e) => {
                      if (e.target.checked) {
                        setVisibleColumns((prev) => [...prev, col]);
                      } else {
                        setVisibleColumns((prev) =>
                          prev.filter((c) => c !== col),
                        );
                      }
                    }}
                    className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                  />
                  {CERT_TYPE_DISPLAY[col]}
                </label>
              ))}
              <button
                onClick={() => setShowColumnPicker(false)}
                className="mt-2 w-full text-xs text-center text-blue-600 hover:text-blue-700 font-medium"
              >
                Done
              </button>
            </div>
          )}
        </div>

        {/* Add certification button */}
        <Button
          onClick={() => openCreateModal()}
          className="flex items-center gap-1.5"
        >
          <Plus className="h-4 w-4" />
          Add Certification
        </Button>
      </div>

      {/* ──── Teacher Certification Matrix ──────────────────────────── */}
      {filteredTeachers.length === 0 ? (
        <div className="text-center py-12 text-gray-500 border border-gray-200 rounded-lg bg-white">
          <GraduationCap className="h-12 w-12 mx-auto mb-3 text-gray-300" />
          <p className="font-medium">No teachers found</p>
          <p className="text-sm mt-1">
            {searchQuery || filterStatus !== 'ALL'
              ? 'Try adjusting your search or filters.'
              : 'Add teachers to your school to start tracking certifications.'}
          </p>
        </div>
      ) : (
        <>
          {/* Desktop table */}
          <div className="hidden md:block overflow-x-auto bg-white rounded-xl border border-gray-200 shadow-sm">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th
                    className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer select-none whitespace-nowrap"
                    onClick={() => setSortAsc(!sortAsc)}
                  >
                    Teacher {sortAsc ? '\u2191' : '\u2193'}
                  </th>
                  {visibleColumns.map((col) => (
                    <th
                      key={col}
                      className="px-3 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider whitespace-nowrap"
                    >
                      {(CERT_TYPE_DISPLAY[col] || col).replace(
                        /^IB Category (\d) Workshop$/,
                        'IB Cat $1',
                      ).replace(' Certification', '').replace(' Training', '').replace(' Awareness', '')}
                    </th>
                  ))}
                  <th className="px-3 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-100">
                {filteredTeachers.map((teacher) => (
                  <tr key={teacher.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3 whitespace-nowrap">
                      <div className="text-sm font-medium text-gray-900">
                        {teacher.name}
                      </div>
                      <div className="text-xs text-gray-500">{teacher.email}</div>
                    </td>
                    {visibleColumns.map((col) => (
                      <td
                        key={col}
                        className="px-3 py-2 text-center"
                      >
                        {renderCertCell(teacher, col)}
                      </td>
                    ))}
                    <td className="px-3 py-2 text-center">
                      <button
                        onClick={() => openCreateModal(teacher.id)}
                        className="text-gray-400 hover:text-blue-600 transition-colors"
                        title={`Add certification for ${teacher.name}`}
                      >
                        <Plus className="h-4 w-4 inline" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Mobile cards */}
          <div className="md:hidden space-y-3">
            {filteredTeachers.map((teacher) => (
              <div
                key={teacher.id}
                className="bg-white rounded-xl border border-gray-200 shadow-sm p-4"
              >
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <p className="text-sm font-semibold text-gray-900">
                      {teacher.name}
                    </p>
                    <p className="text-xs text-gray-500">{teacher.email}</p>
                  </div>
                  <button
                    onClick={() => openCreateModal(teacher.id)}
                    className="text-blue-600 hover:text-blue-700"
                  >
                    <Plus className="h-4 w-4" />
                  </button>
                </div>

                <div className="space-y-2">
                  {visibleColumns.map((col) => {
                    const cert = teacher.certifications.find(
                      (c) => c.certification_type === col,
                    );
                    const shortLabel = (CERT_TYPE_DISPLAY[col] || col)
                      .replace(/^IB Category (\d) Workshop$/, 'IB Cat $1')
                      .replace(' Certification', '')
                      .replace(' Training', '');

                    if (!cert) {
                      return (
                        <div
                          key={col}
                          className="flex items-center justify-between text-sm"
                        >
                          <span className="text-gray-500">{shortLabel}</span>
                          <button
                            onClick={() => openCreateModal(teacher.id, col)}
                            className="text-gray-300 hover:text-gray-500 text-xs"
                          >
                            -- Add
                          </button>
                        </div>
                      );
                    }

                    const cfg = STATUS_CONFIG[cert.status];
                    return (
                      <button
                        key={col}
                        onClick={() => openEditModal(cert, teacher.id)}
                        className="flex items-center justify-between text-sm w-full text-left hover:bg-gray-50 rounded px-1 -mx-1 py-0.5"
                      >
                        <span className="text-gray-700">{shortLabel}</span>
                        <Badge variant={cfg.badgeVariant} className="text-[10px]">
                          {cert.status === 'VALID' && cert.completed_date
                            ? formatDate(cert.completed_date)
                            : cfg.label}
                        </Badge>
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {/* ──── Add / Edit Modal ───────────────────────────────────────── */}
      <CertFormModal
        open={modalOpen}
        onClose={closeModal}
        editingCert={editingCert}
        prefillTeacherId={prefillTeacherId}
        prefillCertType={prefillCertType}
        teachersList={teachersList ?? []}
        isSaving={createMutation.isPending || updateMutation.isPending}
        onSubmit={(data) => {
          if (editingCert) {
            const { teacher_id, ...rest } = data;
            updateMutation.mutate({ id: editingCert.id, data: rest });
          } else {
            createMutation.mutate(data);
          }
        }}
        onDelete={(id) => {
          closeModal();
          setTimeout(() => setDeleteConfirmId(id), 200);
        }}
      />

      {/* ──── Delete Confirmation ────────────────────────────────────── */}
      <Transition show={!!deleteConfirmId} as={Fragment}>
        <Dialog
          as="div"
          className="relative z-50"
          onClose={() => setDeleteConfirmId(null)}
        >
          <Transition.Child
            as={Fragment}
            enter="ease-out duration-200"
            enterFrom="opacity-0"
            enterTo="opacity-100"
            leave="ease-in duration-150"
            leaveFrom="opacity-100"
            leaveTo="opacity-0"
          >
            <div className="fixed inset-0 bg-black/30" aria-hidden="true" />
          </Transition.Child>
          <div className="fixed inset-0 overflow-y-auto">
            <div className="flex min-h-full items-center justify-center p-4">
              <Transition.Child
                as={Fragment}
                enter="ease-out duration-200"
                enterFrom="opacity-0 scale-95"
                enterTo="opacity-100 scale-100"
                leave="ease-in duration-150"
                leaveFrom="opacity-100 scale-100"
                leaveTo="opacity-0 scale-95"
              >
                <Dialog.Panel className="w-full max-w-sm rounded-xl bg-white p-6 shadow-xl">
                  <Dialog.Title className="text-lg font-semibold text-gray-900">
                    Delete Certification
                  </Dialog.Title>
                  <p className="mt-2 text-sm text-gray-600">
                    Are you sure you want to delete this certification record? This
                    action cannot be undone.
                  </p>
                  <div className="mt-5 flex items-center justify-end gap-3">
                    <Button
                      variant="outline"
                      onClick={() => setDeleteConfirmId(null)}
                      disabled={deleteMutation.isPending}
                    >
                      Cancel
                    </Button>
                    <Button
                      variant="danger"
                      onClick={() => {
                        if (deleteConfirmId) deleteMutation.mutate(deleteConfirmId);
                      }}
                      disabled={deleteMutation.isPending}
                    >
                      {deleteMutation.isPending ? (
                        <>
                          <Loader2 className="h-4 w-4 animate-spin mr-1" />
                          Deleting...
                        </>
                      ) : (
                        'Delete'
                      )}
                    </Button>
                  </div>
                </Dialog.Panel>
              </Transition.Child>
            </div>
          </div>
        </Dialog>
      </Transition>
    </div>
  );
}

// -- Form Modal Component ----------------------------------------------------

interface CertFormModalProps {
  open: boolean;
  onClose: () => void;
  editingCert: (StaffCert & { teacher_id: string }) | null;
  prefillTeacherId: string;
  prefillCertType: string;
  teachersList: TeacherOption[];
  isSaving: boolean;
  onSubmit: (data: CertFormData) => void;
  onDelete?: (id: string) => void;
}

function CertFormModal({
  open,
  onClose,
  editingCert,
  prefillTeacherId,
  prefillCertType,
  teachersList,
  isSaving,
  onSubmit,
  onDelete,
}: CertFormModalProps) {
  const isEdit = !!editingCert;

  const form = useZodForm({
    schema: CertFormSchema,
    defaultValues: {
      teacher_id: '',
      certification_type: '',
      custom_name: '',
      completed_date: '',
      expiry_date: '',
      provider: '',
      certificate_url: '',
      notes: '',
    },
  });

  // Reset form when modal opens
  React.useEffect(() => {
    if (open) {
      if (editingCert) {
        form.reset({
          teacher_id: editingCert.teacher_id,
          certification_type: editingCert.certification_type,
          custom_name: editingCert.custom_name || '',
          completed_date: editingCert.completed_date || '',
          expiry_date: editingCert.expiry_date || '',
          provider: editingCert.provider || '',
          certificate_url: editingCert.certificate_url || '',
          notes: editingCert.notes || '',
        });
      } else {
        form.reset({
          teacher_id: prefillTeacherId || '',
          certification_type: prefillCertType || '',
          custom_name: '',
          completed_date: '',
          expiry_date: '',
          provider: '',
          certificate_url: '',
          notes: '',
        });
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, editingCert, prefillTeacherId, prefillCertType]);

  const watchedCertType = form.watch('certification_type');

  return (
    <Transition show={open} as={Fragment}>
      <Dialog as="div" className="relative z-50" onClose={onClose}>
        <Transition.Child
          as={Fragment}
          enter="ease-out duration-200"
          enterFrom="opacity-0"
          enterTo="opacity-100"
          leave="ease-in duration-150"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-black/30" aria-hidden="true" />
        </Transition.Child>
        <div className="fixed inset-0 overflow-y-auto">
          <div className="flex min-h-full items-center justify-center p-4">
            <Transition.Child
              as={Fragment}
              enter="ease-out duration-200"
              enterFrom="opacity-0 scale-95"
              enterTo="opacity-100 scale-100"
              leave="ease-in duration-150"
              leaveFrom="opacity-100 scale-100"
              leaveTo="opacity-0 scale-95"
            >
              <Dialog.Panel className="w-full max-w-lg rounded-xl bg-white shadow-xl">
                {/* Header */}
                <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
                  <Dialog.Title className="text-lg font-semibold text-gray-900 flex items-center gap-2">
                    <Award className="h-5 w-5 text-blue-600" />
                    {isEdit ? 'Edit Certification' : 'Add Certification'}
                  </Dialog.Title>
                  <button
                    onClick={onClose}
                    className="text-gray-400 hover:text-gray-600 transition-colors"
                  >
                    <X className="h-5 w-5" />
                  </button>
                </div>

                {/* Form */}
                <form
                  onSubmit={form.handleSubmit(onSubmit)}
                  className="px-6 py-4 space-y-4 max-h-[70vh] overflow-y-auto"
                >
                  {/* Teacher */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Teacher <span className="text-red-500">*</span>
                    </label>
                    <Controller
                      control={form.control}
                      name="teacher_id"
                      render={({ field, fieldState }) => (
                        <>
                          <select
                            {...field}
                            disabled={isEdit}
                            className={cn(
                              'w-full px-3 py-2 text-sm border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white',
                              fieldState.error
                                ? 'border-red-300'
                                : 'border-gray-300',
                              isEdit && 'bg-gray-100 cursor-not-allowed',
                            )}
                          >
                            <option value="">Select teacher...</option>
                            {teachersList.map((t) => (
                              <option key={t.id} value={t.id}>
                                {t.first_name} {t.last_name} ({t.email})
                              </option>
                            ))}
                          </select>
                          {fieldState.error && (
                            <p className="mt-1 text-xs text-red-600">
                              {fieldState.error.message}
                            </p>
                          )}
                        </>
                      )}
                    />
                  </div>

                  {/* Certification Type */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Certification Type <span className="text-red-500">*</span>
                    </label>
                    <Controller
                      control={form.control}
                      name="certification_type"
                      render={({ field, fieldState }) => (
                        <>
                          <select
                            {...field}
                            disabled={isEdit}
                            className={cn(
                              'w-full px-3 py-2 text-sm border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 bg-white',
                              fieldState.error
                                ? 'border-red-300'
                                : 'border-gray-300',
                              isEdit && 'bg-gray-100 cursor-not-allowed',
                            )}
                          >
                            <option value="">Select type...</option>
                            {CERT_TYPE_OPTIONS.map((t) => (
                              <option key={t.value} value={t.value}>
                                {t.label}
                              </option>
                            ))}
                          </select>
                          {fieldState.error && (
                            <p className="mt-1 text-xs text-red-600">
                              {fieldState.error.message}
                            </p>
                          )}
                        </>
                      )}
                    />
                  </div>

                  {/* Custom name (only for OTHER) */}
                  {watchedCertType === 'OTHER' && (
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        Custom Name
                      </label>
                      <Controller
                        control={form.control}
                        name="custom_name"
                        render={({ field, fieldState }) => (
                          <>
                            <input
                              {...field}
                              type="text"
                              placeholder="e.g. Montessori Certification"
                              className={cn(
                                'w-full px-3 py-2 text-sm border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500',
                                fieldState.error
                                  ? 'border-red-300'
                                  : 'border-gray-300',
                              )}
                            />
                            {fieldState.error && (
                              <p className="mt-1 text-xs text-red-600">
                                {fieldState.error.message}
                              </p>
                            )}
                          </>
                        )}
                      />
                    </div>
                  )}

                  {/* Date row */}
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        Completed Date
                      </label>
                      <Controller
                        control={form.control}
                        name="completed_date"
                        render={({ field, fieldState }) => (
                          <>
                            <input
                              {...field}
                              type="date"
                              className={cn(
                                'w-full px-3 py-2 text-sm border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500',
                                fieldState.error
                                  ? 'border-red-300'
                                  : 'border-gray-300',
                              )}
                            />
                            {fieldState.error && (
                              <p className="mt-1 text-xs text-red-600">
                                {fieldState.error.message}
                              </p>
                            )}
                          </>
                        )}
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        Expiry Date
                      </label>
                      <Controller
                        control={form.control}
                        name="expiry_date"
                        render={({ field, fieldState }) => (
                          <>
                            <input
                              {...field}
                              type="date"
                              className={cn(
                                'w-full px-3 py-2 text-sm border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500',
                                fieldState.error
                                  ? 'border-red-300'
                                  : 'border-gray-300',
                              )}
                            />
                            {fieldState.error && (
                              <p className="mt-1 text-xs text-red-600">
                                {fieldState.error.message}
                              </p>
                            )}
                          </>
                        )}
                      />
                    </div>
                  </div>

                  {/* Provider */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Provider / Issuing Organization
                    </label>
                    <Controller
                      control={form.control}
                      name="provider"
                      render={({ field, fieldState }) => (
                        <>
                          <input
                            {...field}
                            type="text"
                            placeholder="e.g. IB Organization"
                            className={cn(
                              'w-full px-3 py-2 text-sm border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500',
                              fieldState.error
                                ? 'border-red-300'
                                : 'border-gray-300',
                            )}
                          />
                          {fieldState.error && (
                            <p className="mt-1 text-xs text-red-600">
                              {fieldState.error.message}
                            </p>
                          )}
                        </>
                      )}
                    />
                  </div>

                  {/* Certificate URL */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Certificate URL
                    </label>
                    <Controller
                      control={form.control}
                      name="certificate_url"
                      render={({ field, fieldState }) => (
                        <>
                          <input
                            {...field}
                            type="url"
                            placeholder="https://..."
                            className={cn(
                              'w-full px-3 py-2 text-sm border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500',
                              fieldState.error
                                ? 'border-red-300'
                                : 'border-gray-300',
                            )}
                          />
                          {fieldState.error && (
                            <p className="mt-1 text-xs text-red-600">
                              {fieldState.error.message}
                            </p>
                          )}
                        </>
                      )}
                    />
                  </div>

                  {/* Notes */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Notes
                    </label>
                    <Controller
                      control={form.control}
                      name="notes"
                      render={({ field, fieldState }) => (
                        <>
                          <textarea
                            {...field}
                            rows={3}
                            placeholder="Additional notes..."
                            className={cn(
                              'w-full px-3 py-2 text-sm border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none',
                              fieldState.error
                                ? 'border-red-300'
                                : 'border-gray-300',
                            )}
                          />
                          {fieldState.error && (
                            <p className="mt-1 text-xs text-red-600">
                              {fieldState.error.message}
                            </p>
                          )}
                        </>
                      )}
                    />
                  </div>
                </form>

                {/* Footer */}
                <div className="flex items-center justify-between px-6 py-4 border-t border-gray-200 bg-gray-50 rounded-b-xl">
                  {isEdit && editingCert && onDelete ? (
                    <button
                      type="button"
                      onClick={() => onDelete(editingCert.id)}
                      className="flex items-center gap-1 text-sm text-red-600 hover:text-red-700 transition-colors"
                    >
                      <Trash2 className="h-4 w-4" />
                      Delete
                    </button>
                  ) : (
                    <div />
                  )}
                  <div className="flex items-center gap-3">
                    <Button
                      variant="outline"
                      onClick={onClose}
                      disabled={isSaving}
                    >
                      Cancel
                    </Button>
                    <Button
                      onClick={form.handleSubmit(onSubmit)}
                      disabled={isSaving}
                    >
                      {isSaving ? (
                        <>
                          <Loader2 className="h-4 w-4 animate-spin mr-1" />
                          Saving...
                        </>
                      ) : isEdit ? (
                        'Update'
                      ) : (
                        'Add Certification'
                      )}
                    </Button>
                  </div>
                </div>
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition>
  );
}
