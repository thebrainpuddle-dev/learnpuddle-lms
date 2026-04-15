// src/components/certifications/SchoolAccreditationsTab.tsx
//
// School-level accreditation management tab. Displays all accreditations
// (IB, CBSE, Cambridge, NABET, CIS, ISO, etc.) with status tracking,
// milestone timelines, and CRUD operations.

import React, { Fragment, useMemo, useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Dialog, Transition } from '@headlessui/react';
import { z } from 'zod';
import { Controller } from 'react-hook-form';
import {
  Shield,
  ShieldCheck,
  ShieldAlert,
  ExternalLink,
  Plus,
  Pencil,
  Trash2,
  ChevronDown,
  Calendar,
  Building2,
  Award,
  Clock,
  X,
  CheckCircle,
  Circle,
  AlertCircle,
  Loader2,
} from 'lucide-react';
import api from '../../config/api';
import { cn } from '../../lib/utils';
import { useZodForm } from '../../hooks/useZodForm';
import { useToast } from '../../components/common';
import { Badge } from '../../components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Button } from '../../components/common/Button';

// -- Types -------------------------------------------------------------------

interface AccreditationMilestone {
  id: string;
  title: string;
  description: string;
  due_date: string | null;
  completed_date: string | null;
  status: 'PENDING' | 'IN_PROGRESS' | 'COMPLETED' | 'OVERDUE';
  order: number;
}

interface SchoolAccreditation {
  id: string;
  accreditation_type: string;
  display_name: string;
  custom_name: string;
  status: 'AUTHORIZED' | 'CANDIDACY' | 'CONSIDERATION' | 'PENDING' | 'EXPIRED' | 'NOT_STARTED';
  affiliation_number: string;
  valid_from: string | null;
  valid_to: string | null;
  issuing_body: string;
  external_portal_url: string;
  notes: string;
  renewal_cycle_months: number | null;
  days_remaining: number | null;
  milestones: AccreditationMilestone[];
  created_at: string;
}

// -- Constants ---------------------------------------------------------------

const ACCREDITATION_TYPES = [
  { value: 'IB_PYP', label: 'IB Primary Years Programme (PYP)' },
  { value: 'IB_MYP', label: 'IB Middle Years Programme (MYP)' },
  { value: 'IB_DP', label: 'IB Diploma Programme (DP)' },
  { value: 'IB_CP', label: 'IB Career-related Programme (CP)' },
  { value: 'CBSE', label: 'CBSE Affiliation' },
  { value: 'ICSE', label: 'ICSE Affiliation' },
  { value: 'CAMBRIDGE_IGCSE', label: 'Cambridge IGCSE' },
  { value: 'CAMBRIDGE_AL', label: 'Cambridge A Levels' },
  { value: 'NABET', label: 'NABET Accreditation' },
  { value: 'CIS', label: 'CIS Accreditation' },
  { value: 'ISO_9001', label: 'ISO 9001 Quality Management' },
  { value: 'ISO_21001', label: 'ISO 21001 Educational Organizations' },
  { value: 'GREEN_SCHOOL', label: 'IGBC Green School' },
  { value: 'OTHER', label: 'Other' },
] as const;

const STATUS_OPTIONS = [
  { value: 'NOT_STARTED', label: 'Not Started' },
  { value: 'PENDING', label: 'Pending' },
  { value: 'CONSIDERATION', label: 'Under Consideration' },
  { value: 'CANDIDACY', label: 'Candidacy' },
  { value: 'AUTHORIZED', label: 'Authorized' },
  { value: 'EXPIRED', label: 'Expired' },
] as const;

const TYPE_DEFAULTS: Record<string, { issuing_body: string; external_portal_url: string; renewal_cycle_months: number }> = {
  IB_PYP: { issuing_body: 'International Baccalaureate', external_portal_url: 'https://ibo.org', renewal_cycle_months: 60 },
  IB_MYP: { issuing_body: 'International Baccalaureate', external_portal_url: 'https://ibo.org', renewal_cycle_months: 60 },
  IB_DP: { issuing_body: 'International Baccalaureate', external_portal_url: 'https://ibo.org', renewal_cycle_months: 60 },
  IB_CP: { issuing_body: 'International Baccalaureate', external_portal_url: 'https://ibo.org', renewal_cycle_months: 60 },
  CBSE: { issuing_body: 'Central Board of Secondary Education', external_portal_url: 'https://saras.cbse.gov.in', renewal_cycle_months: 60 },
  ICSE: { issuing_body: 'CISCE', external_portal_url: 'https://eaffiliation.cisce.org', renewal_cycle_months: 0 },
  CAMBRIDGE_IGCSE: { issuing_body: 'Cambridge Assessment International Education', external_portal_url: 'https://direct.cie.org.uk', renewal_cycle_months: 0 },
  CAMBRIDGE_AL: { issuing_body: 'Cambridge Assessment International Education', external_portal_url: 'https://direct.cie.org.uk', renewal_cycle_months: 0 },
  NABET: { issuing_body: 'Quality Council of India', external_portal_url: 'https://nabet.qci.org.in/school_accreditation', renewal_cycle_months: 48 },
  CIS: { issuing_body: 'Council of International Schools', external_portal_url: 'https://www.cois.org', renewal_cycle_months: 60 },
  ISO_9001: { issuing_body: 'ISO Certification Body', external_portal_url: '', renewal_cycle_months: 36 },
  ISO_21001: { issuing_body: 'ISO Certification Body', external_portal_url: '', renewal_cycle_months: 36 },
  GREEN_SCHOOL: { issuing_body: 'Indian Green Building Council', external_portal_url: 'https://igbc.in/igbcgreenschools', renewal_cycle_months: 0 },
};

const STATUS_CONFIG: Record<SchoolAccreditation['status'], {
  color: string;
  borderColor: string;
  bgColor: string;
  badgeVariant: 'success' | 'warning' | 'default' | 'destructive' | 'secondary';
  label: string;
}> = {
  AUTHORIZED: { color: 'text-emerald-700', borderColor: 'border-l-emerald-500', bgColor: 'bg-emerald-50', badgeVariant: 'success', label: 'Authorized' },
  CANDIDACY: { color: 'text-amber-700', borderColor: 'border-l-amber-500', bgColor: 'bg-amber-50', badgeVariant: 'warning', label: 'Candidacy' },
  CONSIDERATION: { color: 'text-purple-700', borderColor: 'border-l-purple-500', bgColor: 'bg-purple-50', badgeVariant: 'default', label: 'Under Consideration' },
  PENDING: { color: 'text-blue-700', borderColor: 'border-l-blue-500', bgColor: 'bg-blue-50', badgeVariant: 'default', label: 'Pending' },
  EXPIRED: { color: 'text-red-700', borderColor: 'border-l-red-500', bgColor: 'bg-red-50', badgeVariant: 'destructive', label: 'Expired' },
  NOT_STARTED: { color: 'text-gray-500', borderColor: 'border-l-gray-300', bgColor: 'bg-gray-50', badgeVariant: 'secondary', label: 'Not Started' },
};

const DEFAULT_STATUS_CFG = { color: 'text-gray-500', borderColor: 'border-l-gray-300', bgColor: 'bg-gray-50', badgeVariant: 'secondary' as const, label: 'Unknown' };

const MILESTONE_STATUS_CONFIG: Record<AccreditationMilestone['status'], {
  icon: React.ElementType;
  color: string;
  bgColor: string;
  label: string;
}> = {
  COMPLETED: { icon: CheckCircle, color: 'text-emerald-600', bgColor: 'bg-emerald-100', label: 'Completed' },
  IN_PROGRESS: { icon: Clock, color: 'text-blue-600', bgColor: 'bg-blue-100', label: 'In Progress' },
  PENDING: { icon: Circle, color: 'text-gray-400', bgColor: 'bg-gray-100', label: 'Pending' },
  OVERDUE: { icon: AlertCircle, color: 'text-red-600', bgColor: 'bg-red-100', label: 'Overdue' },
};

// -- Helpers -----------------------------------------------------------------

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '--';
  return new Date(dateStr).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

function daysRemainingColor(days: number | null): string {
  if (days === null) return 'text-gray-500';
  if (days > 365) return 'text-emerald-600';
  if (days >= 90) return 'text-amber-600';
  return 'text-red-600';
}

function daysRemainingBg(days: number | null): string {
  if (days === null) return 'bg-gray-100';
  if (days > 365) return 'bg-emerald-50';
  if (days >= 90) return 'bg-amber-50';
  return 'bg-red-50';
}

// -- Zod Schema --------------------------------------------------------------

const AccreditationFormSchema = z.object({
  accreditation_type: z.string().min(1, 'Accreditation type is required'),
  custom_name: z.string().max(200).optional().default(''),
  status: z.string().min(1, 'Status is required'),
  affiliation_number: z.string().max(100).optional().default(''),
  valid_from: z.string().optional().default(''),
  valid_to: z.string().optional().default(''),
  issuing_body: z.string().max(200).optional().default(''),
  external_portal_url: z.string().url('Must be a valid URL').or(z.literal('')).optional().default(''),
  renewal_cycle_months: z.coerce.number().min(0).max(120).optional().nullable(),
  notes: z.string().max(2000).optional().default(''),
});

type AccreditationFormData = z.infer<typeof AccreditationFormSchema>;

const MilestoneFormSchema = z.object({
  title: z.string().min(1, 'Title is required').max(200),
  description: z.string().max(1000).optional().default(''),
  due_date: z.string().optional().default(''),
  status: z.enum(['PENDING', 'IN_PROGRESS', 'COMPLETED', 'OVERDUE']).default('PENDING'),
});

type MilestoneFormData = z.infer<typeof MilestoneFormSchema>;

// -- Skeleton ----------------------------------------------------------------

function SkeletonCard() {
  return (
    <div className="rounded-lg border border-gray-200 bg-white shadow-sm animate-pulse">
      <div className="p-5 border-l-4 border-l-gray-200">
        <div className="flex items-start justify-between mb-3">
          <div className="space-y-2 flex-1">
            <div className="h-5 bg-gray-200 rounded w-3/4" />
            <div className="h-4 bg-gray-100 rounded w-1/2" />
          </div>
          <div className="h-6 w-20 bg-gray-200 rounded-full" />
        </div>
        <div className="space-y-2 mt-4">
          <div className="h-3 bg-gray-100 rounded w-full" />
          <div className="h-3 bg-gray-100 rounded w-2/3" />
        </div>
        <div className="flex items-center gap-2 mt-4">
          <div className="h-8 w-8 bg-gray-200 rounded" />
          <div className="h-8 w-8 bg-gray-200 rounded" />
          <div className="h-8 w-8 bg-gray-200 rounded" />
        </div>
      </div>
    </div>
  );
}

function SummarySkeleton() {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {[...Array(4)].map((_, i) => (
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
  );
}

// -- Milestone Timeline ------------------------------------------------------

function MilestoneTimeline({
  accreditationId,
  milestones,
}: {
  accreditationId: string;
  milestones: AccreditationMilestone[];
}) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [showAddForm, setShowAddForm] = useState(false);

  const sortedMilestones = useMemo(
    () => [...milestones].sort((a, b) => a.order - b.order),
    [milestones],
  );

  const milestoneForm = useZodForm({
    schema: MilestoneFormSchema,
    defaultValues: { title: '', description: '', due_date: '', status: 'PENDING' },
  });

  const createMilestoneMutation = useMutation({
    mutationFn: (data: MilestoneFormData) =>
      api.post(`/tenants/accreditations/${accreditationId}/milestones/`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['accreditations'] });
      toast.success('Milestone added');
      milestoneForm.reset();
      setShowAddForm(false);
    },
    onError: () => {
      toast.error('Failed to add milestone');
    },
  });

  const updateMilestoneMutation = useMutation({
    mutationFn: ({ mid, data }: { mid: string; data: Partial<MilestoneFormData> & { completed_date?: string } }) =>
      api.patch(`/tenants/accreditations/${accreditationId}/milestones/${mid}/`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['accreditations'] });
      toast.success('Milestone updated');
    },
    onError: () => {
      toast.error('Failed to update milestone');
    },
  });

  const deleteMilestoneMutation = useMutation({
    mutationFn: (mid: string) =>
      api.delete(`/tenants/accreditations/${accreditationId}/milestones/${mid}/`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['accreditations'] });
      toast.success('Milestone removed');
    },
    onError: () => {
      toast.error('Failed to remove milestone');
    },
  });

  function handleToggleStatus(milestone: AccreditationMilestone) {
    const nextStatus: Record<string, AccreditationMilestone['status']> = {
      PENDING: 'IN_PROGRESS',
      IN_PROGRESS: 'COMPLETED',
      COMPLETED: 'PENDING',
      OVERDUE: 'IN_PROGRESS',
    };
    const newStatus = nextStatus[milestone.status];
    updateMilestoneMutation.mutate({
      mid: milestone.id,
      data: {
        status: newStatus,
        ...(newStatus === 'COMPLETED'
          ? { completed_date: new Date().toISOString().split('T')[0] }
          : {}),
      },
    });
  }

  return (
    <div className="px-5 pb-4">
      {sortedMilestones.length === 0 && !showAddForm ? (
        <p className="text-sm text-gray-400 italic py-2">No milestones defined yet.</p>
      ) : (
        <div className="relative ml-3 border-l-2 border-gray-200 space-y-4 py-2">
          {sortedMilestones.map((ms) => {
            const cfg = MILESTONE_STATUS_CONFIG[ms.status] ?? MILESTONE_STATUS_CONFIG.PENDING;
            const StatusIcon = cfg.icon;
            return (
              <div key={ms.id} className="relative pl-6 group">
                {/* Timeline dot */}
                <div className={cn(
                  'absolute -left-[9px] top-1 w-4 h-4 rounded-full flex items-center justify-center',
                  cfg.bgColor,
                )}>
                  <StatusIcon className={cn('w-3 h-3', cfg.color)} />
                </div>

                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-sm font-medium text-gray-900">{ms.title}</span>
                      <Badge
                        variant={
                          ms.status === 'COMPLETED' ? 'success'
                            : ms.status === 'IN_PROGRESS' ? 'default'
                            : ms.status === 'OVERDUE' ? 'destructive'
                            : 'secondary'
                        }
                        className="text-[10px] px-1.5 py-0"
                      >
                        {cfg.label}
                      </Badge>
                    </div>
                    {ms.description && (
                      <p className="text-xs text-gray-500 mt-0.5">{ms.description}</p>
                    )}
                    <div className="flex items-center gap-3 mt-1 text-xs text-gray-400">
                      {ms.due_date && (
                        <span className="flex items-center gap-1">
                          <Calendar className="w-3 h-3" />
                          Due: {formatDate(ms.due_date)}
                        </span>
                      )}
                      {ms.completed_date && (
                        <span className="flex items-center gap-1 text-emerald-600">
                          <CheckCircle className="w-3 h-3" />
                          Done: {formatDate(ms.completed_date)}
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                    <button
                      type="button"
                      onClick={() => handleToggleStatus(ms)}
                      className="p-1 rounded hover:bg-gray-100 text-gray-400 hover:text-gray-600"
                      title="Toggle status"
                    >
                      <CheckCircle className="w-3.5 h-3.5" />
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        if (window.confirm('Delete this milestone?')) {
                          deleteMilestoneMutation.mutate(ms.id);
                        }
                      }}
                      className="p-1 rounded hover:bg-red-50 text-gray-400 hover:text-red-500"
                      title="Delete milestone"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Add milestone form */}
      {showAddForm ? (
        <form
          onSubmit={milestoneForm.handleSubmit((data) => createMilestoneMutation.mutate(data as MilestoneFormData))}
          className="mt-3 p-3 rounded-lg bg-gray-50 border border-gray-200 space-y-3"
        >
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Title *</label>
              <input
                {...milestoneForm.register('title')}
                className="input-field text-sm"
                placeholder="e.g. Self-Study Report"
              />
              {milestoneForm.formState.errors.title && (
                <p className="mt-0.5 text-xs text-red-600">{milestoneForm.formState.errors.title.message}</p>
              )}
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Due Date</label>
              <input
                type="date"
                {...milestoneForm.register('due_date')}
                className="input-field text-sm"
              />
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Description</label>
            <input
              {...milestoneForm.register('description')}
              className="input-field text-sm"
              placeholder="Optional description"
            />
          </div>
          <div className="flex items-center gap-2">
            <button
              type="submit"
              disabled={createMilestoneMutation.isPending}
              className="px-3 py-1.5 text-xs font-medium text-white bg-primary-600 hover:bg-primary-700 rounded-lg transition-colors disabled:opacity-50"
            >
              {createMilestoneMutation.isPending ? 'Adding...' : 'Add Milestone'}
            </button>
            <button
              type="button"
              onClick={() => { setShowAddForm(false); milestoneForm.reset(); }}
              className="px-3 py-1.5 text-xs font-medium text-gray-600 bg-gray-100 hover:bg-gray-200 rounded-lg transition-colors"
            >
              Cancel
            </button>
          </div>
        </form>
      ) : (
        <button
          type="button"
          onClick={() => setShowAddForm(true)}
          className="mt-2 flex items-center gap-1 text-xs font-medium text-primary-600 hover:text-primary-700 transition-colors"
        >
          <Plus className="w-3.5 h-3.5" />
          Add Milestone
        </button>
      )}
    </div>
  );
}

// -- Accreditation Card ------------------------------------------------------

function AccreditationCard({
  accreditation,
  onEdit,
  onDelete,
}: {
  accreditation: SchoolAccreditation;
  onEdit: (a: SchoolAccreditation) => void;
  onDelete: (id: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const cfg = STATUS_CONFIG[accreditation.status] ?? DEFAULT_STATUS_CFG;

  const completedMilestones = accreditation.milestones.filter((m) => m.status === 'COMPLETED').length;
  const totalMilestones = accreditation.milestones.length;

  const displayName = accreditation.display_name || accreditation.custom_name || accreditation.accreditation_type;

  return (
    <div
      className={cn(
        'rounded-lg border border-gray-200 bg-white shadow-sm overflow-hidden border-l-4 transition-shadow hover:shadow-md',
        cfg.borderColor,
      )}
    >
      {/* Card header */}
      <div className="p-5">
        <div className="flex items-start justify-between gap-3 mb-3">
          <div className="min-w-0 flex-1">
            <h4 className="text-sm font-semibold text-gray-900 truncate">{displayName}</h4>
            {accreditation.accreditation_type !== 'OTHER' && accreditation.custom_name && (
              <p className="text-xs text-gray-500 mt-0.5">{accreditation.custom_name}</p>
            )}
          </div>
          <Badge variant={cfg.badgeVariant}>{cfg.label}</Badge>
        </div>

        {/* Status-specific body */}
        <div className="space-y-2">
          {accreditation.status === 'AUTHORIZED' && (
            <>
              <div className="flex items-center gap-2 text-sm text-gray-600">
                <Calendar className="w-4 h-4 text-gray-400 shrink-0" />
                <span>Valid until {formatDate(accreditation.valid_to)}</span>
              </div>
              {accreditation.days_remaining !== null && (
                <div className={cn(
                  'inline-flex items-center gap-1.5 text-sm font-medium px-2.5 py-1 rounded-md',
                  daysRemainingColor(accreditation.days_remaining),
                  daysRemainingBg(accreditation.days_remaining),
                )}>
                  <Clock className="w-3.5 h-3.5" />
                  {accreditation.days_remaining} days remaining
                </div>
              )}
              {accreditation.affiliation_number && (
                <div className="flex items-center gap-2 text-xs text-gray-500">
                  <Award className="w-3.5 h-3.5 text-gray-400 shrink-0" />
                  <span>Affiliation: {accreditation.affiliation_number}</span>
                </div>
              )}
            </>
          )}

          {accreditation.status === 'CANDIDACY' && (
            <>
              {totalMilestones > 0 ? (
                <div>
                  <div className="flex items-center justify-between text-xs text-gray-500 mb-1.5">
                    <span>Milestones Progress</span>
                    <span className="font-medium">{completedMilestones}/{totalMilestones}</span>
                  </div>
                  <div className="h-2 w-full rounded-full bg-gray-200">
                    <div
                      className="h-2 rounded-full bg-amber-500 transition-all"
                      style={{ width: `${totalMilestones > 0 ? (completedMilestones / totalMilestones) * 100 : 0}%` }}
                    />
                  </div>
                </div>
              ) : (
                <p className="text-sm text-amber-600">In candidacy process</p>
              )}
            </>
          )}

          {accreditation.status === 'PENDING' && (
            <p className="text-sm text-blue-600">
              {accreditation.notes || 'Application submitted'}
            </p>
          )}

          {accreditation.status === 'EXPIRED' && (
            <div className="flex items-center gap-2 text-sm font-medium text-red-600">
              <ShieldAlert className="w-4 h-4 shrink-0" />
              <span>Expired on {formatDate(accreditation.valid_to)}</span>
            </div>
          )}

          {accreditation.status === 'NOT_STARTED' && (
            <p className="text-sm text-gray-400 italic">Not yet pursued</p>
          )}
        </div>

        {/* Footer row */}
        <div className="flex items-center justify-between mt-4 pt-3 border-t border-gray-100">
          <div className="flex items-center gap-1.5 text-xs text-gray-500 min-w-0">
            <Building2 className="w-3.5 h-3.5 text-gray-400 shrink-0" />
            <span className="truncate">{accreditation.issuing_body || 'Unknown issuer'}</span>
          </div>
          <div className="flex items-center gap-1 shrink-0">
            {accreditation.external_portal_url && (
              <a
                href={accreditation.external_portal_url}
                target="_blank"
                rel="noopener noreferrer"
                className="p-1.5 rounded-md hover:bg-gray-100 text-gray-400 hover:text-primary-600 transition-colors"
                title="Open external portal"
              >
                <ExternalLink className="w-4 h-4" />
              </a>
            )}
            <button
              type="button"
              onClick={() => onEdit(accreditation)}
              className="p-1.5 rounded-md hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition-colors"
              title="Edit accreditation"
            >
              <Pencil className="w-4 h-4" />
            </button>
            <button
              type="button"
              onClick={() => onDelete(accreditation.id)}
              className="p-1.5 rounded-md hover:bg-red-50 text-gray-400 hover:text-red-500 transition-colors"
              title="Delete accreditation"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Expandable milestones */}
      <div className="border-t border-gray-100">
        <button
          type="button"
          onClick={() => setExpanded(!expanded)}
          className="w-full flex items-center justify-between px-5 py-2.5 text-xs font-medium text-gray-500 hover:text-gray-700 hover:bg-gray-50 transition-colors"
        >
          <span>
            Milestones ({totalMilestones})
            {completedMilestones > 0 && (
              <span className="text-emerald-600 ml-1">
                {completedMilestones} completed
              </span>
            )}
          </span>
          <ChevronDown className={cn(
            'w-4 h-4 transition-transform duration-200',
            expanded && 'rotate-180',
          )} />
        </button>
        {expanded && (
          <MilestoneTimeline
            accreditationId={accreditation.id}
            milestones={accreditation.milestones}
          />
        )}
      </div>
    </div>
  );
}

// -- Add/Edit Modal ----------------------------------------------------------

function AccreditationModal({
  isOpen,
  onClose,
  editingAccreditation,
}: {
  isOpen: boolean;
  onClose: () => void;
  editingAccreditation: SchoolAccreditation | null;
}) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const isEdit = !!editingAccreditation;

  const form = useZodForm({
    schema: AccreditationFormSchema,
    defaultValues: {
      accreditation_type: '',
      custom_name: '',
      status: 'NOT_STARTED',
      affiliation_number: '',
      valid_from: '',
      valid_to: '',
      issuing_body: '',
      external_portal_url: '',
      renewal_cycle_months: null,
      notes: '',
    },
  });

  const selectedType = form.watch('accreditation_type');

  // Reset form when modal opens with editing data
  useEffect(() => {
    if (isOpen && editingAccreditation) {
      form.reset({
        accreditation_type: editingAccreditation.accreditation_type,
        custom_name: editingAccreditation.custom_name || '',
        status: editingAccreditation.status,
        affiliation_number: editingAccreditation.affiliation_number || '',
        valid_from: editingAccreditation.valid_from || '',
        valid_to: editingAccreditation.valid_to || '',
        issuing_body: editingAccreditation.issuing_body || '',
        external_portal_url: editingAccreditation.external_portal_url || '',
        renewal_cycle_months: editingAccreditation.renewal_cycle_months,
        notes: editingAccreditation.notes || '',
      });
    } else if (isOpen && !editingAccreditation) {
      form.reset({
        accreditation_type: '',
        custom_name: '',
        status: 'NOT_STARTED',
        affiliation_number: '',
        valid_from: '',
        valid_to: '',
        issuing_body: '',
        external_portal_url: '',
        renewal_cycle_months: null,
        notes: '',
      });
    }
  }, [isOpen, editingAccreditation]); // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-fill defaults when type changes (only when creating, not editing)
  useEffect(() => {
    if (!isEdit && selectedType && TYPE_DEFAULTS[selectedType]) {
      const defaults = TYPE_DEFAULTS[selectedType];
      const currentIssuer = form.getValues('issuing_body');
      const currentUrl = form.getValues('external_portal_url');
      const currentCycle = form.getValues('renewal_cycle_months');

      // Only auto-fill if the field is empty or unchanged
      if (!currentIssuer) {
        form.setValue('issuing_body', defaults.issuing_body);
      }
      if (!currentUrl) {
        form.setValue('external_portal_url', defaults.external_portal_url);
      }
      if (currentCycle === null || currentCycle === 0) {
        form.setValue('renewal_cycle_months', defaults.renewal_cycle_months || null);
      }
    }
  }, [selectedType, isEdit]); // eslint-disable-line react-hooks/exhaustive-deps

  const createMutation = useMutation({
    mutationFn: (data: AccreditationFormData) =>
      api.post('/tenants/accreditations/create/', cleanPayload(data)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['accreditations'] });
      toast.success('Accreditation added successfully');
      onClose();
    },
    onError: () => {
      toast.error('Failed to add accreditation');
    },
  });

  const updateMutation = useMutation({
    mutationFn: (data: AccreditationFormData) =>
      api.patch(`/tenants/accreditations/${editingAccreditation!.id}/update/`, cleanPayload(data)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['accreditations'] });
      toast.success('Accreditation updated');
      onClose();
    },
    onError: () => {
      toast.error('Failed to update accreditation');
    },
  });

  function cleanPayload(data: AccreditationFormData) {
    return {
      ...data,
      valid_from: data.valid_from || null,
      valid_to: data.valid_to || null,
      renewal_cycle_months: data.renewal_cycle_months || null,
      external_portal_url: data.external_portal_url || '',
    };
  }

  const isSaving = createMutation.isPending || updateMutation.isPending;

  function handleSubmit(data: AccreditationFormData) {
    if (isEdit) {
      updateMutation.mutate(data);
    } else {
      createMutation.mutate(data);
    }
  }

  return (
    <Transition show={isOpen} as={Fragment}>
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
          <div className="fixed inset-0 bg-black/40" />
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
              <Dialog.Panel className="w-full max-w-lg transform overflow-hidden rounded-2xl bg-white shadow-xl transition-all">
                {/* Header */}
                <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
                  <Dialog.Title className="text-lg font-semibold text-gray-900">
                    {isEdit ? 'Edit Accreditation' : 'Add Accreditation'}
                  </Dialog.Title>
                  <button
                    type="button"
                    onClick={onClose}
                    className="p-1 rounded-md hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition-colors"
                  >
                    <X className="w-5 h-5" />
                  </button>
                </div>

                {/* Form */}
                <form onSubmit={form.handleSubmit(handleSubmit)} className="p-6 space-y-4 max-h-[70vh] overflow-y-auto">
                  {/* Accreditation Type */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Accreditation Type <span className="text-red-500">*</span>
                    </label>
                    <Controller
                      control={form.control}
                      name="accreditation_type"
                      render={({ field, fieldState }) => (
                        <div>
                          <select
                            {...field}
                            className={cn(
                              'input-field text-sm',
                              fieldState.error && 'border-red-500 focus:ring-red-500',
                            )}
                          >
                            <option value="">Select type...</option>
                            {ACCREDITATION_TYPES.map((t) => (
                              <option key={t.value} value={t.value}>{t.label}</option>
                            ))}
                          </select>
                          {fieldState.error && (
                            <p className="mt-1 text-xs text-red-600">{fieldState.error.message}</p>
                          )}
                        </div>
                      )}
                    />
                  </div>

                  {/* Custom Name (shown when type=OTHER) */}
                  {selectedType === 'OTHER' && (
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">Custom Name</label>
                      <input
                        {...form.register('custom_name')}
                        className="input-field text-sm"
                        placeholder="e.g. State Board Affiliation"
                      />
                    </div>
                  )}

                  {/* Status */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Status <span className="text-red-500">*</span>
                    </label>
                    <Controller
                      control={form.control}
                      name="status"
                      render={({ field, fieldState }) => (
                        <div>
                          <select
                            {...field}
                            className={cn(
                              'input-field text-sm',
                              fieldState.error && 'border-red-500 focus:ring-red-500',
                            )}
                          >
                            <option value="">Select status...</option>
                            {STATUS_OPTIONS.map((s) => (
                              <option key={s.value} value={s.value}>{s.label}</option>
                            ))}
                          </select>
                          {fieldState.error && (
                            <p className="mt-1 text-xs text-red-600">{fieldState.error.message}</p>
                          )}
                        </div>
                      )}
                    />
                  </div>

                  {/* Affiliation Number */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Affiliation Number</label>
                    <input
                      {...form.register('affiliation_number')}
                      className="input-field text-sm"
                      placeholder="e.g. IB-001234"
                    />
                  </div>

                  {/* Dates */}
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">Valid From</label>
                      <input
                        type="date"
                        {...form.register('valid_from')}
                        className="input-field text-sm"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">Valid To</label>
                      <input
                        type="date"
                        {...form.register('valid_to')}
                        className="input-field text-sm"
                      />
                    </div>
                  </div>

                  {/* Issuing Body */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Issuing Body</label>
                    <input
                      {...form.register('issuing_body')}
                      className="input-field text-sm"
                      placeholder="e.g. International Baccalaureate"
                    />
                  </div>

                  {/* External Portal URL */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">External Portal URL</label>
                    <input
                      type="url"
                      {...form.register('external_portal_url')}
                      className="input-field text-sm"
                      placeholder="https://..."
                    />
                    {form.formState.errors.external_portal_url && (
                      <p className="mt-1 text-xs text-red-600">
                        {form.formState.errors.external_portal_url.message}
                      </p>
                    )}
                  </div>

                  {/* Renewal Cycle */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Renewal Cycle (months)
                    </label>
                    <input
                      type="number"
                      {...form.register('renewal_cycle_months')}
                      className="input-field text-sm"
                      placeholder="e.g. 60"
                      min={0}
                      max={120}
                    />
                  </div>

                  {/* Notes */}
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Notes</label>
                    <textarea
                      {...form.register('notes')}
                      className="input-field text-sm min-h-[80px] resize-y"
                      placeholder="Internal notes about this accreditation..."
                      rows={3}
                    />
                  </div>

                  {/* Footer */}
                  <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-gray-200 bg-gray-50">
                    <button
                      type="button"
                      onClick={onClose}
                      disabled={isSaving}
                      className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={isSaving}
                      className={cn(
                        'px-4 py-2 text-sm font-medium text-white rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500',
                        isSaving
                          ? 'bg-primary-400 cursor-not-allowed'
                          : 'bg-primary-600 hover:bg-primary-700',
                      )}
                    >
                      {isSaving ? (
                        <span className="flex items-center gap-2">
                          <Loader2 className="w-4 h-4 animate-spin" />
                          Saving...
                        </span>
                      ) : isEdit ? 'Update' : 'Add Accreditation'}
                    </button>
                  </div>
                </form>
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition>
  );
}

// -- Main Component ----------------------------------------------------------

export function SchoolAccreditationsTab() {
  const queryClient = useQueryClient();
  const toast = useToast();

  const [modalOpen, setModalOpen] = useState(false);
  const [editingAccreditation, setEditingAccreditation] = useState<SchoolAccreditation | null>(null);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);

  // Fetch accreditations
  const {
    data: accreditations = [],
    isLoading,
    isError,
    error,
  } = useQuery<SchoolAccreditation[]>({
    queryKey: ['accreditations'],
    queryFn: async () => {
      const res = await api.get('/tenants/accreditations/');
      return res.data?.results ?? res.data ?? [];
    },
  });

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.delete(`/tenants/accreditations/${id}/delete/`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['accreditations'] });
      toast.success('Accreditation deleted');
      setDeleteConfirmId(null);
    },
    onError: () => {
      toast.error('Failed to delete accreditation');
      setDeleteConfirmId(null);
    },
  });

  // Computed stats
  const stats = useMemo(() => {
    const active = accreditations.filter((a) => a.status !== 'NOT_STARTED');
    return {
      total: active.length,
      authorized: accreditations.filter((a) => a.status === 'AUTHORIZED').length,
      inProgress: accreditations.filter((a) => a.status === 'CANDIDACY' || a.status === 'PENDING').length,
      expiringSoon: accreditations.filter(
        (a) => a.days_remaining !== null && a.days_remaining > 0 && a.days_remaining < 180,
      ).length,
    };
  }, [accreditations]);

  function handleEdit(accreditation: SchoolAccreditation) {
    setEditingAccreditation(accreditation);
    setModalOpen(true);
  }

  function handleCloseModal() {
    setModalOpen(false);
    setEditingAccreditation(null);
  }

  function handleDelete(id: string) {
    setDeleteConfirmId(id);
  }

  function confirmDelete() {
    if (deleteConfirmId) {
      deleteMutation.mutate(deleteConfirmId);
    }
  }

  // Loading state
  if (isLoading) {
    return (
      <div className="space-y-6">
        <SummarySkeleton />
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {[...Array(6)].map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      </div>
    );
  }

  // Error state
  if (isError) {
    return (
      <div className="text-center py-16">
        <ShieldAlert className="h-12 w-12 mx-auto mb-3 text-red-300" />
        <p className="text-lg font-medium text-gray-900">Failed to load accreditations</p>
        <p className="text-sm text-gray-500 mt-1">
          {(error as any)?.message || 'An unexpected error occurred. Please try again.'}
        </p>
        <button
          type="button"
          onClick={() => queryClient.invalidateQueries({ queryKey: ['accreditations'] })}
          className="mt-4 px-4 py-2 text-sm font-medium text-primary-600 bg-primary-50 rounded-lg hover:bg-primary-100 transition-colors"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Summary cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-gray-500">Total Accreditations</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-3">
              <Shield className="h-8 w-8 text-indigo-500" />
              <span className="text-3xl font-bold text-gray-900">{stats.total}</span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-gray-500">Active / Authorized</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-3">
              <ShieldCheck className="h-8 w-8 text-emerald-500" />
              <span className="text-3xl font-bold text-gray-900">{stats.authorized}</span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-gray-500">In Progress</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-3">
              <Clock className="h-8 w-8 text-amber-500" />
              <span className="text-3xl font-bold text-gray-900">{stats.inProgress}</span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-gray-500">Expiring Soon</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-3">
              <ShieldAlert className={cn('h-8 w-8', stats.expiringSoon > 0 ? 'text-red-500' : 'text-gray-300')} />
              <span className="text-3xl font-bold text-gray-900">{stats.expiringSoon}</span>
            </div>
            {stats.expiringSoon > 0 && (
              <p className="text-xs text-gray-500 mt-1">Within 180 days</p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Header with Add button */}
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-gray-900">
          School Accreditations
        </h3>
        <Button
          variant="primary"
          size="sm"
          leftIcon={<Plus className="w-4 h-4" />}
          onClick={() => {
            setEditingAccreditation(null);
            setModalOpen(true);
          }}
        >
          Add Accreditation
        </Button>
      </div>

      {/* Accreditation cards grid or empty state */}
      {accreditations.length === 0 ? (
        <div className="text-center py-16 border border-gray-200 rounded-lg bg-white">
          <Shield className="h-16 w-16 mx-auto mb-4 text-gray-200" />
          <p className="text-lg font-medium text-gray-900">No accreditations yet</p>
          <p className="text-sm text-gray-500 mt-1 max-w-md mx-auto">
            Track your school's accreditations and affiliations such as IB, CBSE, Cambridge, NABET, and more.
          </p>
          <button
            type="button"
            onClick={() => {
              setEditingAccreditation(null);
              setModalOpen(true);
            }}
            className="mt-5 inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-primary-600 hover:bg-primary-700 rounded-lg transition-colors"
          >
            <Plus className="w-4 h-4" />
            Add your first accreditation
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {accreditations.map((accreditation) => (
            <AccreditationCard
              key={accreditation.id}
              accreditation={accreditation}
              onEdit={handleEdit}
              onDelete={handleDelete}
            />
          ))}
        </div>
      )}

      {/* Add/Edit Modal */}
      <AccreditationModal
        isOpen={modalOpen}
        onClose={handleCloseModal}
        editingAccreditation={editingAccreditation}
      />

      {/* Delete Confirmation Dialog */}
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
              <div className="fixed inset-0 bg-black/40" />
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
                  <Dialog.Panel className="w-full max-w-md transform overflow-hidden rounded-2xl bg-white p-6 shadow-xl transition-all">
                    <div className="flex items-start gap-4">
                      <div className="flex-shrink-0 p-2 rounded-full bg-red-100">
                        <ShieldAlert className="h-6 w-6 text-red-600" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <Dialog.Title className="text-lg font-semibold text-gray-900">
                          Delete Accreditation
                        </Dialog.Title>
                        <p className="mt-2 text-sm text-gray-500">
                          Are you sure you want to delete this accreditation? This action cannot be undone.
                          All associated milestones will also be removed.
                        </p>
                      </div>
                    </div>

                    <div className="mt-6 flex justify-end gap-3">
                      <button
                        type="button"
                        onClick={() => setDeleteConfirmId(null)}
                        disabled={deleteMutation.isPending}
                        className="px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors"
                      >
                        Cancel
                      </button>
                      <button
                        type="button"
                        onClick={confirmDelete}
                        disabled={deleteMutation.isPending}
                        className={cn(
                          'px-4 py-2 text-sm font-medium text-white rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500',
                          deleteMutation.isPending
                            ? 'bg-red-400 cursor-not-allowed'
                            : 'bg-red-600 hover:bg-red-700',
                        )}
                      >
                        {deleteMutation.isPending ? 'Deleting...' : 'Delete'}
                      </button>
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
