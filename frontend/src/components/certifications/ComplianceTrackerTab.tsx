// src/components/certifications/ComplianceTrackerTab.tsx
//
// Compliance tracker for Indian school regulatory requirements.
// Tracks items across Safety, Board, NEP 2020, Financial, Data & Privacy
// categories with due dates, status tracking, and overdue alerts.

import React, { Fragment, useMemo, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Dialog, Transition } from '@headlessui/react';
import { z } from 'zod';
import { Controller } from 'react-hook-form';
import {
  Shield,
  ShieldCheck,
  ShieldAlert,
  CheckCircle,
  AlertCircle,
  Clock,
  FileText,
  Users,
  Plus,
  Pencil,
  Trash2,
  ChevronDown,
  Calendar,
  Loader2,
  X,
  ListChecks,
  Building,
  GraduationCap,
  Landmark,
  Database,
  RefreshCw,
} from 'lucide-react';
import api from '../../config/api';
import { cn } from '../../lib/utils';
import { useZodForm } from '../../hooks/useZodForm';
import { useToast, ConfirmDialog } from '../common';
import { FormField } from '../common/FormField';
import { Button } from '../common/Button';

// ── Types ────────────────────────────────────────────────────────────

type ComplianceCategory = 'SAFETY' | 'BOARD' | 'NEP' | 'FINANCIAL' | 'DATA' | 'IB' | 'OTHER';
type ComplianceStatus = 'COMPLIANT' | 'IN_PROGRESS' | 'NON_COMPLIANT' | 'NOT_APPLICABLE' | 'PENDING';
type ComplianceRecurrence = 'ONE_TIME' | 'ANNUAL' | 'QUARTERLY' | 'MONTHLY';

interface ComplianceItem {
  id: string;
  name: string;
  description: string;
  category: ComplianceCategory;
  category_display: string;
  status: ComplianceStatus;
  status_display: string;
  due_date: string | null;
  completed_date: string | null;
  responsible_person: string;
  recurrence: ComplianceRecurrence;
  recurrence_display: string;
  notes: string;
  document_url: string;
  reminder_days: number;
  days_until_due: number | null;
  is_overdue: boolean;
  created_at: string;
  updated_at: string;
}

interface ComplianceSummary {
  total: number;
  compliant: number;
  in_progress: number;
  overdue: number;
  upcoming: number;
}

interface ComplianceListResponse {
  summary: ComplianceSummary;
  items: ComplianceItem[];
}

// ── Constants ────────────────────────────────────────────────────────

const CATEGORY_OPTIONS: { value: ComplianceCategory; label: string }[] = [
  { value: 'SAFETY', label: 'Safety & Infrastructure' },
  { value: 'BOARD', label: 'Board & Government' },
  { value: 'NEP', label: 'NEP 2020 Alignment' },
  { value: 'FINANCIAL', label: 'Financial & Fee Regulation' },
  { value: 'DATA', label: 'Data & Privacy' },
  { value: 'IB', label: 'IB Programme' },
  { value: 'OTHER', label: 'Other' },
];

const STATUS_OPTIONS: { value: ComplianceStatus; label: string }[] = [
  { value: 'COMPLIANT', label: 'Compliant' },
  { value: 'IN_PROGRESS', label: 'In Progress' },
  { value: 'NON_COMPLIANT', label: 'Non-Compliant' },
  { value: 'NOT_APPLICABLE', label: 'Not Applicable' },
  { value: 'PENDING', label: 'Pending Review' },
];

const RECURRENCE_OPTIONS: { value: ComplianceRecurrence; label: string }[] = [
  { value: 'ONE_TIME', label: 'One-time' },
  { value: 'ANNUAL', label: 'Annual' },
  { value: 'QUARTERLY', label: 'Quarterly' },
  { value: 'MONTHLY', label: 'Monthly' },
];

const CATEGORY_CONFIG: Record<ComplianceCategory, {
  label: string;
  icon: React.ElementType;
  color: string;
  bgColor: string;
  borderColor: string;
  badgeBg: string;
  badgeText: string;
}> = {
  SAFETY: {
    label: 'Safety & Infrastructure',
    icon: ShieldAlert,
    color: 'text-rose-700',
    bgColor: 'bg-rose-50',
    borderColor: 'border-l-rose-500',
    badgeBg: 'bg-rose-100',
    badgeText: 'text-rose-700',
  },
  BOARD: {
    label: 'Board & Government',
    icon: Building,
    color: 'text-blue-700',
    bgColor: 'bg-blue-50',
    borderColor: 'border-l-blue-500',
    badgeBg: 'bg-blue-100',
    badgeText: 'text-blue-700',
  },
  NEP: {
    label: 'NEP 2020 Alignment',
    icon: GraduationCap,
    color: 'text-purple-700',
    bgColor: 'bg-purple-50',
    borderColor: 'border-l-purple-500',
    badgeBg: 'bg-purple-100',
    badgeText: 'text-purple-700',
  },
  FINANCIAL: {
    label: 'Financial & Fee Regulation',
    icon: Landmark,
    color: 'text-amber-700',
    bgColor: 'bg-amber-50',
    borderColor: 'border-l-amber-500',
    badgeBg: 'bg-amber-100',
    badgeText: 'text-amber-700',
  },
  DATA: {
    label: 'Data & Privacy',
    icon: Database,
    color: 'text-teal-700',
    bgColor: 'bg-teal-50',
    borderColor: 'border-l-teal-500',
    badgeBg: 'bg-teal-100',
    badgeText: 'text-teal-700',
  },
  IB: {
    label: 'IB Programme',
    icon: GraduationCap,
    color: 'text-indigo-700',
    bgColor: 'bg-indigo-50',
    borderColor: 'border-l-indigo-500',
    badgeBg: 'bg-indigo-100',
    badgeText: 'text-indigo-700',
  },
  OTHER: {
    label: 'Other',
    icon: FileText,
    color: 'text-gray-700',
    bgColor: 'bg-gray-50',
    borderColor: 'border-l-gray-400',
    badgeBg: 'bg-gray-100',
    badgeText: 'text-gray-700',
  },
};

const STATUS_CONFIG: Record<ComplianceStatus, {
  color: string;
  dotColor: string;
  bgColor: string;
  label: string;
}> = {
  COMPLIANT: { color: 'text-emerald-700', dotColor: 'bg-emerald-500', bgColor: 'bg-emerald-50', label: 'Compliant' },
  IN_PROGRESS: { color: 'text-amber-700', dotColor: 'bg-amber-500', bgColor: 'bg-amber-50', label: 'In Progress' },
  NON_COMPLIANT: { color: 'text-red-700', dotColor: 'bg-red-500', bgColor: 'bg-red-50', label: 'Non-Compliant' },
  NOT_APPLICABLE: { color: 'text-gray-500', dotColor: 'bg-gray-400', bgColor: 'bg-gray-50', label: 'N/A' },
  PENDING: { color: 'text-blue-700', dotColor: 'bg-blue-500', bgColor: 'bg-blue-50', label: 'Pending' },
};

const DEFAULT_COMPLIANCE_ITEMS: {
  name: string;
  category: ComplianceCategory;
  recurrence: ComplianceRecurrence;
  description: string;
}[] = [
  // Safety & Infrastructure
  { name: 'Fire Safety NOC', category: 'SAFETY', recurrence: 'ANNUAL', description: 'Fire safety certificate from local fire department' },
  { name: 'Building Safety Certificate', category: 'SAFETY', recurrence: 'ANNUAL', description: 'Structural safety certification' },
  { name: 'POCSO Compliance Audit', category: 'SAFETY', recurrence: 'ANNUAL', description: 'Child safety audit under POCSO Act' },
  { name: 'First Aid & Medical Room', category: 'SAFETY', recurrence: 'ANNUAL', description: 'Medical facility inspection and first aid kit audit' },
  { name: 'CCTV & Security Audit', category: 'SAFETY', recurrence: 'ANNUAL', description: 'Security infrastructure review' },
  // Board & Government
  { name: 'UDISE+ Annual Submission', category: 'BOARD', recurrence: 'ANNUAL', description: 'Unified District Information System data submission' },
  { name: 'RTE 25% Quota Compliance', category: 'BOARD', recurrence: 'ANNUAL', description: 'Right to Education economically weaker section quota' },
  { name: 'CBSE Mandatory Disclosures', category: 'BOARD', recurrence: 'ANNUAL', description: 'Published on school website as per CBSE requirements' },
  { name: 'Affidavit Submission to State', category: 'BOARD', recurrence: 'ANNUAL', description: 'Annual affidavit to state education department' },
  // NEP 2020
  { name: '5+3+3+4 Structure Transition', category: 'NEP', recurrence: 'ONE_TIME', description: 'Curriculum restructuring to foundational/preparatory/middle/secondary' },
  { name: 'Competency-Based Assessment', category: 'NEP', recurrence: 'ONE_TIME', description: 'Shift from rote to competency-based evaluation' },
  { name: 'Vocational Education (Grade 6+)', category: 'NEP', recurrence: 'ONE_TIME', description: 'Integration of vocational courses from Grade 6' },
  { name: 'Multilingual Instruction', category: 'NEP', recurrence: 'ONE_TIME', description: 'Mother tongue / regional language instruction until Grade 5' },
  { name: 'Holistic Report Cards', category: 'NEP', recurrence: 'ANNUAL', description: '360-degree student progress reports beyond academics' },
  // Financial
  { name: 'Fee Regulation Filing', category: 'FINANCIAL', recurrence: 'ANNUAL', description: 'Fee structure submission to state fee regulatory committee' },
  { name: 'Annual Audit Report', category: 'FINANCIAL', recurrence: 'ANNUAL', description: 'Chartered accountant audit of school finances' },
  { name: 'Trust/Society Registration Renewal', category: 'FINANCIAL', recurrence: 'ANNUAL', description: 'Renewal of school trust or society registration' },
  // Data & Privacy
  { name: 'Student Data Privacy Policy', category: 'DATA', recurrence: 'ANNUAL', description: 'DPDPA compliance for student records and digital systems' },
  { name: 'Website Privacy & Terms', category: 'DATA', recurrence: 'ANNUAL', description: 'Updated privacy policy and terms on school website' },
  // IB Programme
  { name: 'IB Programme Evaluation', category: 'IB', recurrence: 'ANNUAL', description: 'Annual IB programme self-study and evaluation report' },
  { name: 'IB Authorization Renewal Documentation', category: 'IB', recurrence: 'ONE_TIME', description: 'Documentation for IB authorization renewal cycle' },
  { name: 'IBEN Training Requirements', category: 'IB', recurrence: 'ANNUAL', description: 'IB Educator Network training participation requirements' },
  { name: 'ATL (Approaches to Teaching & Learning) Documentation', category: 'IB', recurrence: 'ANNUAL', description: 'Documentation of ATL strategies and implementation across programmes' },
  // Safety (additional)
  { name: 'POSH Committee Formation', category: 'SAFETY', recurrence: 'ANNUAL', description: 'Prevention of Sexual Harassment committee constitution and compliance' },
];

// ── Zod Schema ───────────────────────────────────────────────────────

const ComplianceFormSchema = z.object({
  name: z.string().min(1, 'Name is required').max(300),
  description: z.string().max(2000).optional().default(''),
  category: z.string().min(1, 'Category is required'),
  status: z.string().min(1, 'Status is required'),
  due_date: z.string().optional().default(''),
  completed_date: z.string().optional().default(''),
  responsible_person: z.string().max(200).optional().default(''),
  recurrence: z.string().min(1, 'Recurrence is required'),
  reminder_days: z.coerce.number().min(0).max(365).optional().default(30),
  notes: z.string().max(2000).optional().default(''),
  document_url: z.string().url('Must be a valid URL').or(z.literal('')).optional().default(''),
});

type ComplianceFormData = z.infer<typeof ComplianceFormSchema>;

// ── Helpers ──────────────────────────────────────────────────────────

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '--';
  return new Date(dateStr).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

function dueUrgencyColor(days: number | null, isOverdue: boolean): string {
  if (isOverdue) return 'text-red-600';
  if (days === null) return 'text-gray-500';
  if (days <= 7) return 'text-red-600';
  if (days <= 30) return 'text-amber-600';
  return 'text-gray-600';
}

function dueBadgeBg(days: number | null, isOverdue: boolean): string {
  if (isOverdue) return 'bg-red-50';
  if (days === null) return 'bg-gray-50';
  if (days <= 7) return 'bg-red-50';
  if (days <= 30) return 'bg-amber-50';
  return 'bg-gray-50';
}

function daysLabel(days: number | null, isOverdue: boolean): string {
  if (days === null) return 'No due date';
  if (isOverdue) return `${Math.abs(days)}d overdue`;
  if (days === 0) return 'Due today';
  if (days === 1) return 'Due tomorrow';
  return `${days}d remaining`;
}

// ── Loading Skeleton ─────────────────────────────────────────────────

const ComplianceSkeleton: React.FC = () => (
  <div className="animate-pulse space-y-6">
    {/* Summary cards skeleton */}
    <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="h-20 bg-gray-100 rounded-xl" />
      ))}
    </div>
    {/* Filter pills skeleton */}
    <div className="flex gap-2">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="h-8 w-28 bg-gray-100 rounded-full" />
      ))}
    </div>
    {/* Items skeleton */}
    <div className="space-y-3">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="h-16 bg-gray-100 rounded-lg" />
      ))}
    </div>
  </div>
);

// ── Main Component ───────────────────────────────────────────────────

export function ComplianceTrackerTab() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [editingItem, setEditingItem] = useState<ComplianceItem | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<ComplianceItem | null>(null);
  const [categoryFilter, setCategoryFilter] = useState<ComplianceCategory | 'ALL'>('ALL');
  const [populatingDefaults, setPopulatingDefaults] = useState(false);

  // ── API Queries ──────────────────────────────────────────────────

  const {
    data: response,
    isLoading,
    isError,
    error,
  } = useQuery<ComplianceListResponse>({
    queryKey: ['compliance'],
    queryFn: () => api.get('/tenants/compliance/').then((r) => r.data),
  });

  const summary = response?.summary ?? { total: 0, compliant: 0, in_progress: 0, overdue: 0, upcoming: 0 };
  const allItems = response?.items ?? [];

  // ── Filtered & Grouped Items ───────────────────────────────────

  const filteredItems = useMemo(() => {
    if (categoryFilter === 'ALL') return allItems;
    return allItems.filter((item) => item.category === categoryFilter);
  }, [allItems, categoryFilter]);

  const groupedItems = useMemo(() => {
    const groups: Partial<Record<ComplianceCategory, ComplianceItem[]>> = {};
    for (const item of filteredItems) {
      if (!groups[item.category]) {
        groups[item.category] = [];
      }
      groups[item.category]!.push(item);
    }
    return groups;
  }, [filteredItems]);

  // Order groups by CATEGORY_OPTIONS order
  const orderedCategories = useMemo(() => {
    return CATEGORY_OPTIONS
      .map((c) => c.value)
      .filter((cat) => groupedItems[cat] && groupedItems[cat]!.length > 0);
  }, [groupedItems]);

  // ── Form ─────────────────────────────────────────────────────────

  const form = useZodForm({
    schema: ComplianceFormSchema,
    defaultValues: {
      name: '',
      description: '',
      category: '',
      status: 'PENDING',
      due_date: '',
      completed_date: '',
      responsible_person: '',
      recurrence: 'ANNUAL',
      reminder_days: 30,
      notes: '',
      document_url: '',
    },
  });

  const watchedStatus = form.watch('status');

  // ── Mutations ────────────────────────────────────────────────────

  const createMutation = useMutation({
    mutationFn: (data: Record<string, unknown>) =>
      api.post('/tenants/compliance/create/', data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['compliance'] });
      closeModal();
      toast.success('Item created', 'The compliance item has been added.');
    },
    onError: (err: any) => {
      const detail = err?.response?.data;
      if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
        Object.entries(detail).forEach(([field, messages]) => {
          if (field in ComplianceFormSchema.shape) {
            form.setError(field as keyof ComplianceFormData, {
              type: 'server',
              message: Array.isArray(messages) ? (messages as string[])[0] : String(messages),
            });
          }
        });
      }
      toast.error('Failed to create', 'Please check the details and try again.');
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Record<string, unknown> }) =>
      api.patch(`/tenants/compliance/${id}/update/`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['compliance'] });
      closeModal();
      toast.success('Item updated', 'The compliance item has been updated.');
    },
    onError: () => {
      toast.error('Failed to update', 'Please check the details and try again.');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/tenants/compliance/${id}/delete/`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['compliance'] });
      setDeleteConfirm(null);
      toast.success('Item deleted', 'The compliance item has been removed.');
    },
    onError: () => {
      toast.error('Failed to delete', 'Please try again.');
    },
  });

  // Inline status change mutation
  const statusMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      api.patch(`/tenants/compliance/${id}/update/`, { status }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['compliance'] });
    },
    onError: () => {
      toast.error('Failed to update status', 'Please try again.');
    },
  });

  // ── Populate Defaults ────────────────────────────────────────────

  const handlePopulateDefaults = async () => {
    setPopulatingDefaults(true);
    try {
      for (const item of DEFAULT_COMPLIANCE_ITEMS) {
        await api.post('/tenants/compliance/create/', {
          name: item.name,
          category: item.category,
          recurrence: item.recurrence,
          description: item.description,
          status: 'PENDING',
        });
      }
      queryClient.invalidateQueries({ queryKey: ['compliance'] });
      toast.success('Defaults added', `${DEFAULT_COMPLIANCE_ITEMS.length} compliance items have been created.`);
    } catch {
      toast.error('Failed to populate', 'Some items may not have been created. Please try again.');
    } finally {
      setPopulatingDefaults(false);
    }
  };

  // ── Modal helpers ────────────────────────────────────────────────

  const closeModal = () => {
    setModalOpen(false);
    setEditingItem(null);
    form.reset({
      name: '',
      description: '',
      category: '',
      status: 'PENDING',
      due_date: '',
      completed_date: '',
      responsible_person: '',
      recurrence: 'ANNUAL',
      reminder_days: 30,
      notes: '',
      document_url: '',
    });
  };

  const openCreateModal = () => {
    form.reset({
      name: '',
      description: '',
      category: '',
      status: 'PENDING',
      due_date: '',
      completed_date: '',
      responsible_person: '',
      recurrence: 'ANNUAL',
      reminder_days: 30,
      notes: '',
      document_url: '',
    });
    setEditingItem(null);
    setModalOpen(true);
  };

  const openEditModal = (item: ComplianceItem) => {
    form.reset({
      name: item.name,
      description: item.description || '',
      category: item.category,
      status: item.status,
      due_date: item.due_date || '',
      completed_date: item.completed_date || '',
      responsible_person: item.responsible_person || '',
      recurrence: item.recurrence,
      reminder_days: item.reminder_days,
      notes: item.notes || '',
      document_url: item.document_url || '',
    });
    setEditingItem(item);
    setModalOpen(true);
  };

  const onSubmit = form.handleSubmit((data) => {
    const payload: Record<string, unknown> = {
      name: data.name,
      description: data.description || '',
      category: data.category,
      status: data.status,
      due_date: data.due_date || null,
      completed_date: data.completed_date || null,
      responsible_person: data.responsible_person || '',
      recurrence: data.recurrence,
      reminder_days: data.reminder_days ?? 30,
      notes: data.notes || '',
      document_url: data.document_url || '',
    };

    if (editingItem) {
      updateMutation.mutate({ id: editingItem.id, data: payload });
    } else {
      createMutation.mutate(payload);
    }
  });

  // ── Render ─────────────────────────────────────────────────────────

  return (
    <div className="space-y-6">
      {/* ── Header ────────────────────────────────────────────────── */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2">
          <Shield className="h-5 w-5 text-indigo-500" />
          <h2 className="text-lg font-semibold text-gray-900">Compliance Tracker</h2>
        </div>
        <Button className="w-full sm:w-auto" variant="primary" onClick={openCreateModal}>
          <Plus className="h-5 w-5 mr-2" />
          Add Item
        </Button>
      </div>

      {isLoading ? (
        <ComplianceSkeleton />
      ) : isError ? (
        <div className="text-center py-12 text-gray-500 border border-gray-200 rounded-lg bg-white">
          <ShieldAlert className="h-12 w-12 mx-auto mb-3 text-gray-300" />
          <p className="font-medium text-red-600">Failed to load compliance data</p>
          <p className="text-sm mt-1 text-gray-500">
            {(error as any)?.message || 'An unexpected error occurred. Please try again.'}
          </p>
        </div>
      ) : (
        <>
          {/* ── Summary Cards ───────────────────────────────────────── */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4">
              <div className="flex items-center gap-2 mb-1">
                <ListChecks className="h-4 w-4 text-gray-400" />
                <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">Total</span>
              </div>
              <p className="text-2xl font-bold text-gray-900">{summary.total}</p>
            </div>
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4">
              <div className="flex items-center gap-2 mb-1">
                <CheckCircle className="h-4 w-4 text-emerald-500" />
                <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">Compliant</span>
              </div>
              <p className="text-2xl font-bold text-emerald-600">{summary.compliant}</p>
            </div>
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4">
              <div className="flex items-center gap-2 mb-1">
                <Clock className="h-4 w-4 text-amber-500" />
                <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">In Progress</span>
              </div>
              <p className="text-2xl font-bold text-amber-600">{summary.in_progress}</p>
            </div>
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4">
              <div className="flex items-center gap-2 mb-1">
                <AlertCircle className="h-4 w-4 text-red-500" />
                <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">Overdue</span>
              </div>
              <p className="text-2xl font-bold text-red-600">{summary.overdue}</p>
            </div>
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4 col-span-2 sm:col-span-1">
              <div className="flex items-center gap-2 mb-1">
                <Calendar className="h-4 w-4 text-blue-500" />
                <span className="text-xs font-medium text-gray-500 uppercase tracking-wide">Due Soon</span>
              </div>
              <p className="text-2xl font-bold text-blue-600">{summary.upcoming}</p>
            </div>
          </div>

          {/* ── Category Filter Pills ───────────────────────────────── */}
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => setCategoryFilter('ALL')}
              className={cn(
                'px-3 py-1.5 rounded-full text-sm font-medium transition-colors',
                categoryFilter === 'ALL'
                  ? 'bg-gray-900 text-white'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200',
              )}
            >
              All
            </button>
            {CATEGORY_OPTIONS.map((cat) => {
              const config = CATEGORY_CONFIG[cat.value];
              const isActive = categoryFilter === cat.value;
              return (
                <button
                  key={cat.value}
                  onClick={() => setCategoryFilter(cat.value)}
                  className={cn(
                    'px-3 py-1.5 rounded-full text-sm font-medium transition-colors',
                    isActive
                      ? `${config.badgeBg} ${config.badgeText}`
                      : 'bg-gray-100 text-gray-600 hover:bg-gray-200',
                  )}
                >
                  {cat.label}
                </button>
              );
            })}
          </div>

          {/* ── Empty State with Populate Defaults ──────────────────── */}
          {allItems.length === 0 ? (
            <div className="text-center py-12 text-gray-500 border border-gray-200 rounded-lg bg-white">
              <Shield className="h-12 w-12 mx-auto mb-3 text-gray-300" />
              <p className="font-medium">No compliance items yet.</p>
              <p className="text-sm mt-1 mb-4">
                Start tracking your school's regulatory compliance requirements.
              </p>
              <Button
                variant="outline"
                onClick={handlePopulateDefaults}
                loading={populatingDefaults}
                disabled={populatingDefaults}
              >
                <RefreshCw className={cn('h-4 w-4 mr-2', populatingDefaults && 'animate-spin')} />
                Populate Defaults
              </Button>
            </div>
          ) : filteredItems.length === 0 ? (
            <div className="text-center py-8 text-gray-500 border border-gray-200 rounded-lg bg-white">
              <Shield className="h-10 w-10 mx-auto mb-2 text-gray-300" />
              <p className="font-medium text-sm">No items in this category.</p>
            </div>
          ) : (
            /* ── Grouped Compliance Items ────────────────────────────── */
            <div className="space-y-6">
              {orderedCategories.map((cat) => {
                const config = CATEGORY_CONFIG[cat];
                const items = groupedItems[cat]!;
                const IconComponent = config.icon;

                return (
                  <section key={cat}>
                    {/* Category header */}
                    <div className={cn('flex items-center gap-2 pb-2 mb-3 border-b border-gray-200')}>
                      <IconComponent className={cn('h-4 w-4', config.color)} />
                      <h3 className="text-sm font-semibold uppercase tracking-wide text-gray-600">
                        {config.label}
                      </h3>
                      <span className={cn(
                        'ml-1 inline-flex items-center justify-center rounded-full px-2 py-0.5 text-xs font-medium',
                        config.badgeBg, config.badgeText,
                      )}>
                        {items.length}
                      </span>
                    </div>

                    {/* Desktop list */}
                    <div className="hidden md:block overflow-x-auto bg-white rounded-xl border border-gray-200 shadow-sm">
                      <table className="min-w-full divide-y divide-gray-200">
                        <thead className="bg-gray-50">
                          <tr>
                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider w-8">
                              Status
                            </th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                              Item
                            </th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                              Due Date
                            </th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                              Responsible
                            </th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                              Recurrence
                            </th>
                            <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                              Change Status
                            </th>
                            <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                              Actions
                            </th>
                          </tr>
                        </thead>
                        <tbody className="bg-white divide-y divide-gray-100">
                          {items.map((item, idx) => {
                            const statusCfg = STATUS_CONFIG[item.status];
                            return (
                              <tr
                                key={item.id}
                                className={cn(
                                  'hover:bg-gray-50 transition-colors',
                                  item.is_overdue && 'bg-red-50/50',
                                  idx % 2 === 1 && !item.is_overdue && 'bg-gray-50/30',
                                )}
                              >
                                {/* Status dot */}
                                <td className="px-4 py-3">
                                  <span
                                    className={cn('inline-block h-3 w-3 rounded-full', statusCfg.dotColor)}
                                    title={statusCfg.label}
                                  />
                                </td>
                                {/* Name */}
                                <td className="px-4 py-3">
                                  <div className="text-sm font-medium text-gray-900">{item.name}</div>
                                  {item.description && (
                                    <div className="text-xs text-gray-500 mt-0.5 line-clamp-1">{item.description}</div>
                                  )}
                                </td>
                                {/* Due date */}
                                <td className="px-4 py-3">
                                  {item.due_date ? (
                                    <div>
                                      <div className="text-sm text-gray-700">{formatDate(item.due_date)}</div>
                                      <span className={cn(
                                        'inline-block mt-0.5 text-xs font-medium px-1.5 py-0.5 rounded',
                                        dueBadgeBg(item.days_until_due, item.is_overdue),
                                        dueUrgencyColor(item.days_until_due, item.is_overdue),
                                      )}>
                                        {daysLabel(item.days_until_due, item.is_overdue)}
                                      </span>
                                    </div>
                                  ) : (
                                    <span className="text-sm text-gray-400">--</span>
                                  )}
                                </td>
                                {/* Responsible */}
                                <td className="px-4 py-3">
                                  {item.responsible_person ? (
                                    <div className="flex items-center gap-1.5">
                                      <Users className="h-3.5 w-3.5 text-gray-400" />
                                      <span className="text-sm text-gray-700">{item.responsible_person}</span>
                                    </div>
                                  ) : (
                                    <span className="text-sm text-gray-400">--</span>
                                  )}
                                </td>
                                {/* Recurrence */}
                                <td className="px-4 py-3">
                                  <span className="inline-flex items-center rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600">
                                    {item.recurrence_display}
                                  </span>
                                </td>
                                {/* Inline status change */}
                                <td className="px-4 py-3">
                                  <select
                                    value={item.status}
                                    onChange={(e) => {
                                      statusMutation.mutate({ id: item.id, status: e.target.value });
                                    }}
                                    className={cn(
                                      'text-xs font-medium rounded-lg border border-gray-200 px-2 py-1.5 bg-white',
                                      'focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500',
                                      'cursor-pointer',
                                    )}
                                  >
                                    {STATUS_OPTIONS.map((opt) => (
                                      <option key={opt.value} value={opt.value}>{opt.label}</option>
                                    ))}
                                  </select>
                                </td>
                                {/* Actions */}
                                <td className="px-4 py-3 text-right">
                                  <div className="flex items-center justify-end gap-2">
                                    {item.document_url && (
                                      <a
                                        href={item.document_url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="p-1.5 text-gray-400 hover:text-indigo-600 rounded-lg hover:bg-indigo-50 transition-colors"
                                        title="View Evidence"
                                      >
                                        <FileText className="h-4 w-4" />
                                      </a>
                                    )}
                                    <button
                                      onClick={() => openEditModal(item)}
                                      className="p-1.5 text-gray-400 hover:text-indigo-600 rounded-lg hover:bg-indigo-50 transition-colors"
                                      title="Edit"
                                    >
                                      <Pencil className="h-4 w-4" />
                                    </button>
                                    <button
                                      onClick={() => setDeleteConfirm(item)}
                                      className="p-1.5 text-gray-400 hover:text-red-600 rounded-lg hover:bg-red-50 transition-colors"
                                      title="Delete"
                                    >
                                      <Trash2 className="h-4 w-4" />
                                    </button>
                                  </div>
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>

                    {/* Mobile cards */}
                    <div className="md:hidden space-y-3">
                      {items.map((item) => {
                        const statusCfg = STATUS_CONFIG[item.status];
                        return (
                          <div
                            key={item.id}
                            className={cn(
                              'bg-white rounded-xl border shadow-sm p-4 border-l-4',
                              item.is_overdue ? 'border-l-red-500 border-red-200' : `${config.borderColor} border-gray-200`,
                            )}
                          >
                            {/* Top row: status dot + name + recurrence */}
                            <div className="flex items-start justify-between gap-3 mb-2">
                              <div className="flex items-start gap-2 min-w-0">
                                <span
                                  className={cn('mt-1.5 inline-block h-2.5 w-2.5 rounded-full flex-shrink-0', statusCfg.dotColor)}
                                />
                                <div className="min-w-0">
                                  <p className="text-sm font-semibold text-gray-900">{item.name}</p>
                                  {item.description && (
                                    <p className="text-xs text-gray-500 mt-0.5 line-clamp-2">{item.description}</p>
                                  )}
                                </div>
                              </div>
                              <span className="inline-flex items-center rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600 flex-shrink-0">
                                {item.recurrence_display}
                              </span>
                            </div>

                            {/* Info row */}
                            <div className="grid grid-cols-2 gap-2 text-xs text-gray-600 mb-3">
                              <div>
                                <span className="block font-medium text-gray-500">Due</span>
                                {item.due_date ? (
                                  <>
                                    <span className="text-gray-900">{formatDate(item.due_date)}</span>
                                    <span className={cn(
                                      'block mt-0.5 text-xs font-medium',
                                      dueUrgencyColor(item.days_until_due, item.is_overdue),
                                    )}>
                                      {daysLabel(item.days_until_due, item.is_overdue)}
                                    </span>
                                  </>
                                ) : (
                                  <span className="text-gray-400">--</span>
                                )}
                              </div>
                              <div>
                                <span className="block font-medium text-gray-500">Responsible</span>
                                <span className="text-gray-900">{item.responsible_person || '--'}</span>
                              </div>
                            </div>

                            {/* Bottom row: inline status change + actions */}
                            <div className="flex items-center justify-between pt-2 border-t border-gray-100">
                              <select
                                value={item.status}
                                onChange={(e) => {
                                  statusMutation.mutate({ id: item.id, status: e.target.value });
                                }}
                                className={cn(
                                  'text-xs font-medium rounded-lg border border-gray-200 px-2 py-1.5 bg-white',
                                  'focus:outline-none focus:ring-2 focus:ring-indigo-500',
                                  'cursor-pointer',
                                )}
                              >
                                {STATUS_OPTIONS.map((opt) => (
                                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                                ))}
                              </select>
                              <div className="flex items-center gap-2">
                                {item.document_url && (
                                  <a
                                    href={item.document_url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="p-1.5 text-gray-400 hover:text-indigo-600 rounded-lg hover:bg-indigo-50 transition-colors"
                                    title="View Evidence"
                                  >
                                    <FileText className="h-4 w-4" />
                                  </a>
                                )}
                                <button
                                  onClick={() => openEditModal(item)}
                                  className="p-1.5 text-gray-400 hover:text-indigo-600 rounded-lg hover:bg-indigo-50 transition-colors"
                                  title="Edit"
                                >
                                  <Pencil className="h-4 w-4" />
                                </button>
                                <button
                                  onClick={() => setDeleteConfirm(item)}
                                  className="p-1.5 text-gray-400 hover:text-red-600 rounded-lg hover:bg-red-50 transition-colors"
                                  title="Delete"
                                >
                                  <Trash2 className="h-4 w-4" />
                                </button>
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </section>
                );
              })}
            </div>
          )}
        </>
      )}

      {/* ── Create / Edit Modal ───────────────────────────────────── */}
      <Transition show={modalOpen} as={Fragment}>
        <Dialog as="div" className="relative z-50" onClose={closeModal}>
          <Transition.Child
            as={Fragment}
            enter="ease-out duration-200"
            enterFrom="opacity-0"
            enterTo="opacity-100"
            leave="ease-in duration-150"
            leaveFrom="opacity-100"
            leaveTo="opacity-0"
          >
            <div className="fixed inset-0 bg-black/50" />
          </Transition.Child>

          <div className="fixed inset-0 overflow-y-auto">
            <div className="flex min-h-full items-end justify-center p-0 sm:items-center sm:p-4">
              <Transition.Child
                as={Fragment}
                enter="ease-out duration-200"
                enterFrom="opacity-0 translate-y-4 sm:translate-y-0 sm:scale-95"
                enterTo="opacity-100 translate-y-0 sm:scale-100"
                leave="ease-in duration-150"
                leaveFrom="opacity-100 translate-y-0 sm:scale-100"
                leaveTo="opacity-0 translate-y-4 sm:translate-y-0 sm:scale-95"
              >
                <Dialog.Panel className="max-h-[92vh] w-full max-w-lg overflow-y-auto rounded-t-2xl bg-white p-5 pb-6 sm:rounded-xl sm:p-6">
                  <div className="flex items-center justify-between mb-4">
                    <Dialog.Title className="text-lg font-semibold text-gray-900">
                      {editingItem ? 'Edit Compliance Item' : 'Add Compliance Item'}
                    </Dialog.Title>
                    <button onClick={closeModal} className="text-gray-400 hover:text-gray-600">
                      <X className="h-6 w-6" />
                    </button>
                  </div>

                  <form onSubmit={onSubmit} noValidate className="space-y-4">
                    {/* Name */}
                    <FormField
                      control={form.control}
                      name="name"
                      label="Name *"
                      placeholder="e.g., Fire Safety NOC"
                    />

                    {/* Category & Status */}
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                          Category *
                        </label>
                        <Controller
                          control={form.control}
                          name="category"
                          render={({ field, fieldState }) => (
                            <div>
                              <select
                                {...field}
                                className={cn(
                                  'input-field w-full',
                                  fieldState.error && 'border-red-500 focus:ring-red-500',
                                )}
                              >
                                <option value="">Select...</option>
                                {CATEGORY_OPTIONS.map((opt) => (
                                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                                ))}
                              </select>
                              {fieldState.error && (
                                <p className="mt-1 text-sm text-red-600">{fieldState.error.message}</p>
                              )}
                            </div>
                          )}
                        />
                      </div>
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                          Status *
                        </label>
                        <Controller
                          control={form.control}
                          name="status"
                          render={({ field, fieldState }) => (
                            <div>
                              <select
                                {...field}
                                className={cn(
                                  'input-field w-full',
                                  fieldState.error && 'border-red-500 focus:ring-red-500',
                                )}
                              >
                                {STATUS_OPTIONS.map((opt) => (
                                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                                ))}
                              </select>
                              {fieldState.error && (
                                <p className="mt-1 text-sm text-red-600">{fieldState.error.message}</p>
                              )}
                            </div>
                          )}
                        />
                      </div>
                    </div>

                    {/* Due Date & Completed Date */}
                    <div className="grid grid-cols-2 gap-4">
                      <FormField
                        control={form.control}
                        name="due_date"
                        label="Due Date"
                        type="date"
                      />
                      {watchedStatus === 'COMPLIANT' && (
                        <FormField
                          control={form.control}
                          name="completed_date"
                          label="Completed Date"
                          type="date"
                        />
                      )}
                    </div>

                    {/* Responsible Person */}
                    <FormField
                      control={form.control}
                      name="responsible_person"
                      label="Responsible Person"
                      placeholder="e.g., Mr. Sharma"
                    />

                    {/* Recurrence & Reminder Days */}
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                          Recurrence *
                        </label>
                        <Controller
                          control={form.control}
                          name="recurrence"
                          render={({ field, fieldState }) => (
                            <div>
                              <select
                                {...field}
                                className={cn(
                                  'input-field w-full',
                                  fieldState.error && 'border-red-500 focus:ring-red-500',
                                )}
                              >
                                {RECURRENCE_OPTIONS.map((opt) => (
                                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                                ))}
                              </select>
                              {fieldState.error && (
                                <p className="mt-1 text-sm text-red-600">{fieldState.error.message}</p>
                              )}
                            </div>
                          )}
                        />
                      </div>
                      <FormField
                        control={form.control}
                        name="reminder_days"
                        label="Reminder (days)"
                        type="number"
                        min={0}
                        max={365}
                        placeholder="30"
                      />
                    </div>

                    {/* Document URL */}
                    <FormField
                      control={form.control}
                      name="document_url"
                      label="Document / Evidence URL"
                      type="url"
                      placeholder="https://..."
                    />

                    {/* Description */}
                    <div>
                      <label htmlFor="compliance-desc" className="block text-sm font-medium text-gray-700 mb-1">
                        Description
                      </label>
                      <Controller
                        control={form.control}
                        name="description"
                        render={({ field, fieldState }) => (
                          <div>
                            <textarea
                              {...field}
                              id="compliance-desc"
                              rows={2}
                              className={cn(
                                'input-field w-full resize-none',
                                fieldState.error && 'border-red-500 focus:ring-red-500',
                              )}
                              placeholder="Brief description of this compliance requirement..."
                              value={field.value ?? ''}
                            />
                            {fieldState.error && (
                              <p className="mt-1 text-sm text-red-600">{fieldState.error.message}</p>
                            )}
                          </div>
                        )}
                      />
                    </div>

                    {/* Notes */}
                    <div>
                      <label htmlFor="compliance-notes" className="block text-sm font-medium text-gray-700 mb-1">
                        Notes
                      </label>
                      <Controller
                        control={form.control}
                        name="notes"
                        render={({ field, fieldState }) => (
                          <div>
                            <textarea
                              {...field}
                              id="compliance-notes"
                              rows={2}
                              className={cn(
                                'input-field w-full resize-none',
                                fieldState.error && 'border-red-500 focus:ring-red-500',
                              )}
                              placeholder="Additional notes..."
                              value={field.value ?? ''}
                            />
                            {fieldState.error && (
                              <p className="mt-1 text-sm text-red-600">{fieldState.error.message}</p>
                            )}
                          </div>
                        )}
                      />
                    </div>

                    {/* Actions */}
                    <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:items-center sm:justify-end">
                      <Button className="w-full sm:w-auto" variant="outline" type="button" onClick={closeModal}>
                        Cancel
                      </Button>
                      <Button
                        className="w-full sm:w-auto"
                        variant="primary"
                        type="submit"
                        loading={createMutation.isPending || updateMutation.isPending}
                      >
                        {editingItem ? 'Update' : 'Add Item'}
                      </Button>
                    </div>
                  </form>
                </Dialog.Panel>
              </Transition.Child>
            </div>
          </div>
        </Dialog>
      </Transition>

      {/* ── Delete Confirmation ───────────────────────────────────── */}
      <ConfirmDialog
        isOpen={!!deleteConfirm}
        onClose={() => setDeleteConfirm(null)}
        onConfirm={() => {
          if (deleteConfirm) deleteMutation.mutate(deleteConfirm.id);
        }}
        title="Delete Compliance Item"
        message={`Are you sure you want to delete "${deleteConfirm?.name}"? This action cannot be undone.`}
        confirmLabel="Delete"
        variant="danger"
        loading={deleteMutation.isPending}
      />
    </div>
  );
}
