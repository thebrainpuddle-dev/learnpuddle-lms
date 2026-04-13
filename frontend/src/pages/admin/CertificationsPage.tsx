// src/pages/admin/CertificationsPage.tsx
//
// Admin page for managing certification types, issued certifications,
// monitoring upcoming expirations, approving skip requests, and
// viewing IB compliance dashboard.
//
// Top-level tabs: Certifications | Approvals | IB Dashboard
// The Certifications tab contains the original 3 sub-tabs:
//   Certification Types | Issued Certifications | Expiry Dashboard

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { z } from 'zod';
import { Controller } from 'react-hook-form';
import { Button } from '../../components/common/Button';
import { Input } from '../../components/common/Input';
import { FormField } from '../../components/common/FormField';
import { useToast, ConfirmDialog } from '../../components/common';
import { useZodForm } from '../../hooks/useZodForm';
import { usePageTitle } from '../../hooks/usePageTitle';
import { Badge } from '../../components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Tabs, TabsList, TabsTrigger, TabsContent, TabsPanels } from '../../components/ui/tabs';
import {
  certificationsService,
  type CertificationType,
  type TeacherCertification,
  type ExpiryCheckItem,
} from '../../services/certificationsService';
import { adminTeachersService } from '../../services/adminTeachersService';
import { ApprovalsTab } from '../../components/certifications/ApprovalsTab';
import { IBDashboard } from '../../components/certifications/IBDashboard';
import {
  PlusIcon,
  PencilSquareIcon,
  TrashIcon,
  XMarkIcon,
  MagnifyingGlassIcon,
  ArrowPathIcon,
  ShieldCheckIcon,
  ClockIcon,
  ExclamationTriangleIcon,
  NoSymbolIcon,
} from '@heroicons/react/24/outline';

// ── Zod Schemas ──────────────────────────────────────────────────────

const CertificationTypeSchema = z.object({
  name: z.string().min(1, 'Name is required').max(200),
  description: z.string().max(1000).optional().or(z.literal('')),
  validity_months: z.coerce.number().min(1, 'Must be at least 1 month').max(120, 'Max 120 months'),
  auto_renew: z.boolean().default(false),
});

type CertificationTypeFormData = z.infer<typeof CertificationTypeSchema>;

const IssueCertificationSchema = z.object({
  teacher_id: z.string().min(1, 'Please select a teacher'),
  certification_type_id: z.string().min(1, 'Please select a certification type'),
});

type IssueCertificationFormData = z.infer<typeof IssueCertificationSchema>;

// ── Debounce hook ────────────────────────────────────────────────────

function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);
  useEffect(() => {
    const handler = setTimeout(() => setDebouncedValue(value), delay);
    return () => clearTimeout(handler);
  }, [value, delay]);
  return debouncedValue;
}

// ── Status helpers ───────────────────────────────────────────────────

const STATUS_BADGE_VARIANTS: Record<string, 'success' | 'warning' | 'destructive' | 'secondary'> = {
  active: 'success',
  pending_renewal: 'warning',
  expired: 'destructive',
  revoked: 'secondary',
};

const STATUS_LABELS: Record<string, string> = {
  active: 'Active',
  pending_renewal: 'Pending Renewal',
  expired: 'Expired',
  revoked: 'Revoked',
};

function formatDate(dateStr: string) {
  return new Date(dateStr).toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

function daysUntil(dateStr: string) {
  const now = new Date();
  const target = new Date(dateStr);
  return Math.ceil((target.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));
}

// ── Loading skeleton ─────────────────────────────────────────────────

const TableSkeleton: React.FC<{ rows?: number; cols?: number }> = ({ rows = 3, cols = 5 }) => (
  <div className="animate-pulse space-y-3">
    {Array.from({ length: rows }).map((_, i) => (
      <div key={i} className="flex gap-4">
        {Array.from({ length: cols }).map((_, j) => (
          <div key={j} className="h-10 bg-gray-100 rounded-lg flex-1" />
        ))}
      </div>
    ))}
  </div>
);

// ── Tab 1: Certification Types ───────────────────────────────────────

const CertificationTypesTab: React.FC = () => {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [editingType, setEditingType] = useState<CertificationType | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<CertificationType | null>(null);

  const { data: certTypes, isLoading } = useQuery({
    queryKey: ['certificationTypes'],
    queryFn: () => certificationsService.types.list(),
  });

  const form = useZodForm({
    schema: CertificationTypeSchema,
    defaultValues: {
      name: '',
      description: '',
      validity_months: 12,
      auto_renew: false,
    },
  });

  const createMutation = useMutation({
    mutationFn: (data: CertificationTypeFormData) =>
      certificationsService.types.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['certificationTypes'] });
      closeModal();
      toast.success('Type created', 'Certification type has been created.');
    },
    onError: (err: any) => {
      const detail = err?.response?.data;
      if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
        Object.entries(detail).forEach(([field, messages]) => {
          if (field in CertificationTypeSchema.shape) {
            form.setError(field as keyof CertificationTypeFormData, {
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
    mutationFn: ({ id, data }: { id: string; data: CertificationTypeFormData }) =>
      certificationsService.types.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['certificationTypes'] });
      closeModal();
      toast.success('Type updated', 'Certification type has been updated.');
    },
    onError: () => {
      toast.error('Failed to update', 'Please check the details and try again.');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => certificationsService.types.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['certificationTypes'] });
      setDeleteConfirm(null);
      toast.success('Type deleted', 'Certification type has been removed.');
    },
    onError: () => {
      toast.error('Failed to delete', 'Please try again.');
    },
  });

  const closeModal = () => {
    setModalOpen(false);
    setEditingType(null);
    form.reset({ name: '', description: '', validity_months: 12, auto_renew: false });
  };

  const openCreateModal = () => {
    form.reset({ name: '', description: '', validity_months: 12, auto_renew: false });
    setEditingType(null);
    setModalOpen(true);
  };

  const openEditModal = (certType: CertificationType) => {
    form.reset({
      name: certType.name,
      description: certType.description || '',
      validity_months: certType.validity_months,
      auto_renew: certType.auto_renew,
    });
    setEditingType(certType);
    setModalOpen(true);
  };

  const onSubmit = form.handleSubmit((data) => {
    if (editingType) {
      updateMutation.mutate({ id: editingType.id, data });
    } else {
      createMutation.mutate(data);
    }
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-gray-500">
          Define certification types that can be issued to teachers.
        </p>
        <Button className="w-full sm:w-auto" variant="primary" onClick={openCreateModal}>
          <PlusIcon className="h-5 w-5 mr-2" />
          New Type
        </Button>
      </div>

      {isLoading ? (
        <TableSkeleton rows={3} cols={5} />
      ) : !certTypes || certTypes.length === 0 ? (
        <div className="text-center py-12 text-gray-500">
          <ShieldCheckIcon className="h-12 w-12 mx-auto mb-3 text-gray-300" />
          <p className="font-medium">No certification types defined yet.</p>
          <p className="text-sm mt-1">Create one to start issuing certifications.</p>
        </div>
      ) : (
        <div className="overflow-x-auto bg-white rounded-xl border border-gray-200 shadow-sm">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Name</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Validity</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Auto-Renew</th>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider hidden lg:table-cell">Req. Courses</th>
                <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-100">
              {certTypes.map((ct) => (
                <tr key={ct.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3">
                    <div className="text-sm font-medium text-gray-900">{ct.name}</div>
                    {ct.description && (
                      <div className="text-xs text-gray-500 truncate max-w-xs">{ct.description}</div>
                    )}
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-700">
                    {ct.validity_months} {ct.validity_months === 1 ? 'month' : 'months'}
                  </td>
                  <td className="px-4 py-3">
                    <Badge variant={ct.auto_renew ? 'success' : 'secondary'}>
                      {ct.auto_renew ? 'Yes' : 'No'}
                    </Badge>
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-700 hidden lg:table-cell">
                    {ct.required_course_ids?.length || 0}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <button
                        onClick={() => openEditModal(ct)}
                        className="p-1.5 text-gray-400 hover:text-indigo-600 rounded-lg hover:bg-indigo-50 transition-colors"
                        title="Edit"
                      >
                        <PencilSquareIcon className="h-4 w-4" />
                      </button>
                      <button
                        onClick={() => setDeleteConfirm(ct)}
                        className="p-1.5 text-gray-400 hover:text-red-600 rounded-lg hover:bg-red-50 transition-colors"
                        title="Delete"
                      >
                        <TrashIcon className="h-4 w-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Create / Edit modal */}
      {modalOpen && (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/50 p-0 sm:items-center sm:p-4">
          <div className="max-h-[92vh] w-full max-w-lg overflow-y-auto rounded-t-2xl bg-white p-5 pb-6 sm:rounded-xl sm:p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-gray-900">
                {editingType ? 'Edit Certification Type' : 'Create Certification Type'}
              </h3>
              <button onClick={closeModal} className="text-gray-400 hover:text-gray-600">
                <XMarkIcon className="h-6 w-6" />
              </button>
            </div>

            <form onSubmit={onSubmit} noValidate className="space-y-4">
              <FormField
                control={form.control}
                name="name"
                label="Name *"
                placeholder="e.g., IB Teaching Certificate"
              />
              <FormField
                control={form.control}
                name="description"
                label="Description"
                placeholder="Optional description"
              />
              <FormField
                control={form.control}
                name="validity_months"
                label="Validity (months) *"
                type="number"
                min={1}
                max={120}
                placeholder="12"
              />
              <Controller
                control={form.control}
                name="auto_renew"
                render={({ field }) => (
                  <label htmlFor="cert-type-auto-renew" className="flex items-center gap-3">
                    <input
                      type="checkbox"
                      id="cert-type-auto-renew"
                      checked={field.value}
                      onChange={(e) => field.onChange(e.target.checked)}
                      className="h-4 w-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                    />
                    <span className="text-sm font-medium text-gray-700">
                      Auto-renew when expired
                    </span>
                  </label>
                )}
              />

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
                  {editingType ? 'Update' : 'Create'}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Delete confirmation */}
      <ConfirmDialog
        isOpen={!!deleteConfirm}
        onClose={() => setDeleteConfirm(null)}
        onConfirm={() => {
          if (deleteConfirm) deleteMutation.mutate(deleteConfirm.id);
        }}
        title="Delete Certification Type"
        message={`Are you sure you want to delete "${deleteConfirm?.name}"? This action cannot be undone.`}
        confirmLabel="Delete"
        variant="danger"
      />
    </div>
  );
};

// ── Tab 2: Issued Certifications ─────────────────────────────────────

const IssuedCertificationsTab: React.FC = () => {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState('');
  const debouncedSearch = useDebounce(search, 300);
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [issueModalOpen, setIssueModalOpen] = useState(false);
  const [revokeTarget, setRevokeTarget] = useState<TeacherCertification | null>(null);

  const { data: certifications, isLoading } = useQuery({
    queryKey: ['issuedCertifications'],
    queryFn: () => certificationsService.list(),
  });

  const { data: certTypes } = useQuery({
    queryKey: ['certificationTypes'],
    queryFn: () => certificationsService.types.list(),
  });

  const { data: teachers } = useQuery({
    queryKey: ['adminTeachers'],
    queryFn: () => adminTeachersService.listTeachers(),
  });

  const issueForm = useZodForm({
    schema: IssueCertificationSchema,
    defaultValues: { teacher_id: '', certification_type_id: '' },
  });

  const issueMutation = useMutation({
    mutationFn: (data: IssueCertificationFormData) => certificationsService.issue(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['issuedCertifications'] });
      setIssueModalOpen(false);
      issueForm.reset();
      toast.success('Certification issued', 'The certification has been issued successfully.');
    },
    onError: (err: any) => {
      const msg = err?.response?.data?.error || err?.response?.data?.detail || 'Please check the details and try again.';
      toast.error('Failed to issue', msg);
    },
  });

  const revokeMutation = useMutation({
    mutationFn: (id: string) => certificationsService.revoke(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['issuedCertifications'] });
      setRevokeTarget(null);
      toast.success('Certification revoked', 'The certification has been revoked.');
    },
    onError: () => {
      toast.error('Failed to revoke', 'Please try again.');
    },
  });

  const renewMutation = useMutation({
    mutationFn: (id: string) => certificationsService.renew(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['issuedCertifications'] });
      toast.success('Certification renewed', 'The certification has been renewed.');
    },
    onError: (err: any) => {
      const msg = err?.response?.data?.error || err?.response?.data?.detail || 'Please try again.';
      toast.error('Failed to renew', msg);
    },
  });

  const filtered = useMemo(() => {
    let list = certifications ?? [];
    if (statusFilter !== 'all') {
      list = list.filter((c) => c.status === statusFilter);
    }
    if (debouncedSearch.trim()) {
      const q = debouncedSearch.toLowerCase();
      list = list.filter(
        (c) =>
          c.teacher_name.toLowerCase().includes(q) ||
          c.teacher_email.toLowerCase().includes(q) ||
          c.certification_name.toLowerCase().includes(q)
      );
    }
    return list;
  }, [certifications, statusFilter, debouncedSearch]);

  const openIssueModal = () => {
    issueForm.reset({ teacher_id: '', certification_type_id: '' });
    setIssueModalOpen(true);
  };

  const onIssueSubmit = issueForm.handleSubmit((data) => {
    issueMutation.mutate(data);
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center flex-1">
          <Input
            id="cert-search"
            name="cert_search"
            autoComplete="off"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by teacher or certification..."
            leftIcon={<MagnifyingGlassIcon className="h-5 w-5" />}
            className="sm:max-w-xs"
          />
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
          >
            <option value="all">All Statuses</option>
            <option value="active">Active</option>
            <option value="pending_renewal">Pending Renewal</option>
            <option value="expired">Expired</option>
            <option value="revoked">Revoked</option>
          </select>
        </div>
        <Button className="w-full sm:w-auto" variant="primary" onClick={openIssueModal}>
          <PlusIcon className="h-5 w-5 mr-2" />
          Issue New
        </Button>
      </div>

      {isLoading ? (
        <TableSkeleton rows={4} cols={6} />
      ) : filtered.length === 0 ? (
        <div className="text-center py-12 text-gray-500">
          <ShieldCheckIcon className="h-12 w-12 mx-auto mb-3 text-gray-300" />
          <p className="font-medium">No certifications found.</p>
          {(certifications ?? []).length > 0 && (
            <p className="text-sm mt-1">Try adjusting your filters.</p>
          )}
        </div>
      ) : (
        <>
          {/* Desktop table */}
          <div className="hidden md:block overflow-x-auto bg-white rounded-xl border border-gray-200 shadow-sm">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Teacher</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Certification</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Issued</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Expires</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-100">
                {filtered.map((cert) => {
                  const days = daysUntil(cert.expires_at);
                  const isExpiringSoon = cert.status === 'active' && days <= 30 && days > 0;
                  return (
                    <tr key={cert.id} className={`hover:bg-gray-50 ${isExpiringSoon ? 'bg-amber-50/50' : ''}`}>
                      <td className="px-4 py-3">
                        <div className="text-sm font-medium text-gray-900">{cert.teacher_name}</div>
                        <div className="text-xs text-gray-500">{cert.teacher_email}</div>
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-700">
                        {cert.certification_name}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-700">
                        {formatDate(cert.issued_at)}
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-700">
                        <div>{formatDate(cert.expires_at)}</div>
                        {isExpiringSoon && (
                          <div className="text-xs text-amber-600 font-medium">
                            {days} day{days !== 1 ? 's' : ''} left
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <Badge variant={STATUS_BADGE_VARIANTS[cert.status] || 'secondary'}>
                          {STATUS_LABELS[cert.status] || cert.status}
                        </Badge>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <div className="flex items-center justify-end gap-2">
                          {(cert.status === 'active' || cert.status === 'expired' || cert.status === 'pending_renewal') && (
                            <button
                              onClick={() => renewMutation.mutate(cert.id)}
                              disabled={renewMutation.isPending}
                              className="p-1.5 text-gray-400 hover:text-emerald-600 rounded-lg hover:bg-emerald-50 transition-colors disabled:opacity-50"
                              title="Renew"
                            >
                              <ArrowPathIcon className="h-4 w-4" />
                            </button>
                          )}
                          {cert.status === 'active' && (
                            <button
                              onClick={() => setRevokeTarget(cert)}
                              className="p-1.5 text-gray-400 hover:text-red-600 rounded-lg hover:bg-red-50 transition-colors"
                              title="Revoke"
                            >
                              <NoSymbolIcon className="h-4 w-4" />
                            </button>
                          )}
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
            {filtered.map((cert) => {
              const days = daysUntil(cert.expires_at);
              const isExpiringSoon = cert.status === 'active' && days <= 30 && days > 0;
              return (
                <div key={cert.id} className={`card ${isExpiringSoon ? 'ring-1 ring-amber-200' : ''}`}>
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="font-semibold text-gray-900">{cert.teacher_name}</p>
                      <p className="text-xs text-gray-500 break-all">{cert.teacher_email}</p>
                    </div>
                    <Badge variant={STATUS_BADGE_VARIANTS[cert.status] || 'secondary'}>
                      {STATUS_LABELS[cert.status] || cert.status}
                    </Badge>
                  </div>
                  <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-gray-600">
                    <p>Certification: <span className="text-gray-900">{cert.certification_name}</span></p>
                    <p>Issued: <span className="text-gray-900">{formatDate(cert.issued_at)}</span></p>
                    <p>
                      Expires: <span className="text-gray-900">{formatDate(cert.expires_at)}</span>
                      {isExpiringSoon && (
                        <span className="ml-1 text-amber-600 font-medium">({days}d left)</span>
                      )}
                    </p>
                    <p>Renewals: <span className="text-gray-900">{cert.renewal_count}</span></p>
                  </div>
                  <div className="mt-3 flex items-center gap-2">
                    {(cert.status === 'active' || cert.status === 'expired' || cert.status === 'pending_renewal') && (
                      <Button
                        className="flex-1"
                        variant="outline"
                        size="sm"
                        onClick={() => renewMutation.mutate(cert.id)}
                        loading={renewMutation.isPending}
                      >
                        <ArrowPathIcon className="h-4 w-4 mr-1" />Renew
                      </Button>
                    )}
                    {cert.status === 'active' && (
                      <Button
                        className="flex-1"
                        variant="outline"
                        size="sm"
                        onClick={() => setRevokeTarget(cert)}
                      >
                        <NoSymbolIcon className="h-4 w-4 mr-1" />Revoke
                      </Button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}

      {/* Issue certification modal */}
      {issueModalOpen && (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/50 p-0 sm:items-center sm:p-4">
          <div className="max-h-[92vh] w-full max-w-lg overflow-y-auto rounded-t-2xl bg-white p-5 pb-6 sm:rounded-xl sm:p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-gray-900">Issue Certification</h3>
              <button onClick={() => setIssueModalOpen(false)} className="text-gray-400 hover:text-gray-600">
                <XMarkIcon className="h-6 w-6" />
              </button>
            </div>

            <form onSubmit={onIssueSubmit} noValidate className="space-y-4">
              <Controller
                control={issueForm.control}
                name="teacher_id"
                render={({ field, fieldState }) => (
                  <div>
                    <label htmlFor="issue-teacher" className="block text-sm font-medium text-gray-700 mb-1">Teacher *</label>
                    <select
                      id="issue-teacher"
                      value={field.value}
                      onChange={(e) => field.onChange(e.target.value)}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                    >
                      <option value="">Select a teacher...</option>
                      {(teachers ?? []).map((t) => (
                        <option key={t.id} value={t.id}>
                          {t.first_name} {t.last_name} ({t.email})
                        </option>
                      ))}
                    </select>
                    {fieldState.error?.message && (
                      <p className="mt-1 text-sm text-red-600">{fieldState.error.message}</p>
                    )}
                  </div>
                )}
              />

              <Controller
                control={issueForm.control}
                name="certification_type_id"
                render={({ field, fieldState }) => (
                  <div>
                    <label htmlFor="issue-cert-type" className="block text-sm font-medium text-gray-700 mb-1">Certification Type *</label>
                    <select
                      id="issue-cert-type"
                      value={field.value}
                      onChange={(e) => field.onChange(e.target.value)}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                    >
                      <option value="">Select a type...</option>
                      {(certTypes ?? []).map((ct) => (
                        <option key={ct.id} value={ct.id}>
                          {ct.name} ({ct.validity_months} months)
                        </option>
                      ))}
                    </select>
                    {fieldState.error?.message && (
                      <p className="mt-1 text-sm text-red-600">{fieldState.error.message}</p>
                    )}
                  </div>
                )}
              />

              <p className="text-xs text-gray-500">
                The expiry date will be calculated automatically based on the certification type's validity period.
              </p>

              <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:items-center sm:justify-end">
                <Button className="w-full sm:w-auto" variant="outline" type="button" onClick={() => setIssueModalOpen(false)}>
                  Cancel
                </Button>
                <Button
                  className="w-full sm:w-auto"
                  variant="primary"
                  type="submit"
                  loading={issueMutation.isPending}
                >
                  Issue Certification
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Revoke confirmation */}
      <ConfirmDialog
        isOpen={!!revokeTarget}
        onClose={() => setRevokeTarget(null)}
        onConfirm={() => {
          if (revokeTarget) revokeMutation.mutate(revokeTarget.id);
        }}
        title="Revoke Certification"
        message={`Are you sure you want to revoke the "${revokeTarget?.certification_name}" certification for ${revokeTarget?.teacher_name}? This cannot be undone.`}
        confirmLabel="Revoke"
        variant="danger"
      />
    </div>
  );
};

// ── Tab 3: Expiry Dashboard ──────────────────────────────────────────

const ExpiryDashboardTab: React.FC = () => {
  const toast = useToast();
  const queryClient = useQueryClient();

  // Fetch with 90-day window to populate all summary cards
  const { data: expiryData, isLoading } = useQuery({
    queryKey: ['certificationExpiryCheck'],
    queryFn: () => certificationsService.expiryCheck(90),
  });

  const renewMutation = useMutation({
    mutationFn: (id: string) => certificationsService.renew(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['certificationExpiryCheck'] });
      queryClient.invalidateQueries({ queryKey: ['issuedCertifications'] });
      toast.success('Certification renewed', 'The certification has been renewed.');
    },
    onError: (err: any) => {
      const msg = err?.response?.data?.error || err?.response?.data?.detail || 'Please try again.';
      toast.error('Failed to renew', msg);
    },
  });

  const expiringSoon = expiryData?.expiring_soon ?? [];
  const alreadyExpired = expiryData?.already_expired ?? [];

  const expiringIn30 = expiringSoon.filter((c) => (c.days_until_expiry ?? daysUntil(c.expires_at)) <= 30);
  const expiringIn60 = expiringSoon.filter((c) => {
    const d = c.days_until_expiry ?? daysUntil(c.expires_at);
    return d > 30 && d <= 60;
  });
  const expiringIn90 = expiringSoon.filter((c) => {
    const d = c.days_until_expiry ?? daysUntil(c.expires_at);
    return d > 60 && d <= 90;
  });

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-28 bg-gray-100 rounded-lg animate-pulse" />
          ))}
        </div>
        <TableSkeleton rows={3} cols={4} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Summary cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-gray-500">Expiring in 30 Days</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              <ExclamationTriangleIcon className="h-8 w-8 text-red-500" />
              <span className="text-3xl font-bold text-gray-900">{expiringIn30.length}</span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-gray-500">Expiring in 60 Days</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              <ClockIcon className="h-8 w-8 text-amber-500" />
              <span className="text-3xl font-bold text-gray-900">{expiringIn60.length}</span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-gray-500">Expiring in 90 Days</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              <ClockIcon className="h-8 w-8 text-blue-400" />
              <span className="text-3xl font-bold text-gray-900">{expiringIn90.length}</span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-gray-500">Already Expired</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              <NoSymbolIcon className="h-8 w-8 text-gray-400" />
              <span className="text-3xl font-bold text-gray-900">{alreadyExpired.length}</span>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Upcoming expirations list */}
      <div>
        <h3 className="text-lg font-semibold text-gray-900 mb-3">Upcoming Expirations</h3>
        {expiringSoon.length === 0 ? (
          <div className="text-center py-8 text-gray-500 border border-gray-200 rounded-lg bg-white">
            <ShieldCheckIcon className="h-10 w-10 mx-auto mb-2 text-gray-300" />
            <p className="font-medium">All clear</p>
            <p className="text-sm mt-1">No certifications expiring within 90 days.</p>
          </div>
        ) : (
          <div className="bg-white border border-gray-200 rounded-lg overflow-hidden divide-y divide-gray-100">
            {expiringSoon.map((item) => {
              const days = item.days_until_expiry ?? daysUntil(item.expires_at);
              const isUrgent = days <= 14;
              const isWarning = days > 14 && days <= 30;
              return (
                <div
                  key={item.id}
                  className={`flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between ${
                    isUrgent ? 'bg-red-50' : isWarning ? 'bg-amber-50' : 'bg-white'
                  }`}
                >
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-gray-900">
                      {item.teacher_name}
                    </div>
                    <div className="text-xs text-gray-500">
                      {item.certification_name}
                      <span className="mx-1">--</span>
                      {item.teacher_email}
                    </div>
                    <div className={`text-xs mt-1 font-medium ${
                      isUrgent ? 'text-red-600' : isWarning ? 'text-amber-600' : 'text-blue-600'
                    }`}>
                      {days <= 0
                        ? 'Expired'
                        : `Expires in ${days} day${days !== 1 ? 's' : ''}`}{' '}
                      ({formatDate(item.expires_at)})
                    </div>
                  </div>
                  <Button
                    variant="primary"
                    size="sm"
                    className="w-full sm:w-auto"
                    onClick={() => renewMutation.mutate(item.id)}
                    loading={renewMutation.isPending}
                  >
                    <ArrowPathIcon className="h-4 w-4 mr-1" />
                    Renew
                  </Button>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Already expired list */}
      {alreadyExpired.length > 0 && (
        <div>
          <h3 className="text-lg font-semibold text-gray-900 mb-3">Recently Expired</h3>
          <div className="bg-white border border-gray-200 rounded-lg overflow-hidden divide-y divide-gray-100">
            {alreadyExpired.map((item) => (
              <div
                key={item.id}
                className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between bg-gray-50"
              >
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-gray-900">{item.teacher_name}</div>
                  <div className="text-xs text-gray-500">
                    {item.certification_name}
                    <span className="mx-1">--</span>
                    {item.teacher_email}
                  </div>
                  <div className="text-xs mt-1 text-red-600 font-medium">
                    Expired {item.days_since_expiry} day{item.days_since_expiry !== 1 ? 's' : ''} ago ({formatDate(item.expires_at)})
                  </div>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  className="w-full sm:w-auto"
                  onClick={() => renewMutation.mutate(item.id)}
                  loading={renewMutation.isPending}
                >
                  <ArrowPathIcon className="h-4 w-4 mr-1" />
                  Renew
                </Button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

// ── Certifications sub-tabs (original content) ──────────────────────

const CertificationsContent: React.FC = () => (
  <Tabs>
    <TabsList>
      <TabsTrigger>Certification Types</TabsTrigger>
      <TabsTrigger>Issued Certifications</TabsTrigger>
      <TabsTrigger>Expiry Dashboard</TabsTrigger>
    </TabsList>
    <TabsPanels>
      <TabsContent>
        <CertificationTypesTab />
      </TabsContent>
      <TabsContent>
        <IssuedCertificationsTab />
      </TabsContent>
      <TabsContent>
        <ExpiryDashboardTab />
      </TabsContent>
    </TabsPanels>
  </Tabs>
);

// ── Top-level tab config ─────────────────────────────────────────────

const TOP_TABS = ['certifications', 'approvals', 'ib-dashboard'] as const;
type TopTab = typeof TOP_TABS[number];

const TOP_TAB_LABELS: Record<TopTab, string> = {
  certifications: 'Certifications',
  approvals: 'Approvals',
  'ib-dashboard': 'IB Dashboard',
};

// ── Main Page ────────────────────────────────────────────────────────

export const CertificationsPage: React.FC = () => {
  usePageTitle('Certifications');

  const [searchParams, setSearchParams] = useSearchParams();
  const tabParam = searchParams.get('tab') as TopTab | null;
  const activeTab = tabParam && TOP_TABS.includes(tabParam) ? tabParam : 'certifications';

  const selectedIndex = TOP_TABS.indexOf(activeTab);

  const handleTabChange = useCallback(
    (index: number) => {
      const tab = TOP_TABS[index];
      if (tab === 'certifications') {
        // Default tab — remove param for clean URL
        setSearchParams((prev) => {
          const next = new URLSearchParams(prev);
          next.delete('tab');
          return next;
        });
      } else {
        setSearchParams((prev) => {
          const next = new URLSearchParams(prev);
          next.set('tab', tab);
          return next;
        });
      }
    },
    [setSearchParams],
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Certifications</h1>
        <p className="mt-1 text-sm text-gray-500">
          Manage certification types, issue certifications to teachers, and monitor expirations.
        </p>
      </div>

      <Tabs selectedIndex={selectedIndex} onChange={handleTabChange}>
        <TabsList>
          {TOP_TABS.map((tab) => (
            <TabsTrigger key={tab}>{TOP_TAB_LABELS[tab]}</TabsTrigger>
          ))}
        </TabsList>
        <TabsPanels>
          <TabsContent>
            <CertificationsContent />
          </TabsContent>
          <TabsContent>
            <ApprovalsTab />
          </TabsContent>
          <TabsContent>
            <IBDashboard />
          </TabsContent>
        </TabsPanels>
      </Tabs>
    </div>
  );
};
