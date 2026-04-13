import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { z } from 'zod';
import { Controller } from 'react-hook-form';
import { superAdminService, OnboardPayload, TenantListItem } from '../../services/superAdminService';
import { Button, useToast } from '../../components/common';
import { FormField } from '../../components/common/FormField';
import { useZodForm } from '../../hooks/useZodForm';
import { usePageTitle } from '../../hooks/usePageTitle';
import {
  BuildingOffice2Icon,
  MagnifyingGlassIcon,
  XMarkIcon,
  CheckCircleIcon,
  XCircleIcon,
  EnvelopeIcon,
} from '@heroicons/react/24/outline';

// ── Zod Schemas ──────────────────────────────────────────────────────

const OnboardSchema = z.object({
  school_name: z.string().min(1, 'School name is required'),
  admin_email: z.string().min(1, 'Admin email is required').email('Enter a valid email'),
  admin_first_name: z.string().min(1, 'First name is required'),
  admin_last_name: z.string().min(1, 'Last name is required'),
  admin_password: z.string().min(8, 'Password must be at least 8 characters'),
  subdomain: z.string().optional().or(z.literal('')),
});

type OnboardData = z.infer<typeof OnboardSchema>;

const BulkEmailSchema = z.object({
  subject: z.string().min(1, 'Subject is required'),
  body: z.string().min(1, 'Body is required'),
});

type BulkEmailData = z.infer<typeof BulkEmailSchema>;

export const SchoolsPage: React.FC = () => {
  usePageTitle('Schools');
  const toast = useToast();
  const queryClient = useQueryClient();
  const nav = useNavigate();
  const [searchParams] = useSearchParams();
  const [search, setSearch] = useState('');
  const [showOnboard, setShowOnboard] = useState(searchParams.get('onboard') === 'true');
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [showBulkEmail, setShowBulkEmail] = useState(false);
  const [page, setPage] = useState(1);

  const onboardForm = useZodForm({
    schema: OnboardSchema,
    defaultValues: {
      school_name: '',
      admin_email: '',
      admin_first_name: '',
      admin_last_name: '',
      admin_password: '',
      subdomain: '',
    },
  });

  const bulkEmailForm = useZodForm({
    schema: BulkEmailSchema,
    defaultValues: { subject: '', body: '' },
  });

  const { data, isLoading } = useQuery({
    queryKey: ['tenants', search, page],
    queryFn: () => superAdminService.listTenants({ search: search || undefined, page }),
  });

  // Reset page when search changes
  React.useEffect(() => { setPage(1); }, [search]);

  const onboardMutation = useMutation({
    mutationFn: superAdminService.onboardSchool,
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['tenants'] });
      queryClient.invalidateQueries({ queryKey: ['platformStats'] });
      setShowOnboard(false);
      onboardForm.reset();
      toast.success('School onboarded!', `Subdomain: ${result.subdomain} — Admin: ${result.admin_email}`);
    },
    onError: (err: any) => {
      const detail = err?.response?.data;
      if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
        Object.entries(detail).forEach(([field, messages]) => {
          if (field in OnboardSchema.shape) {
            onboardForm.setError(field as keyof OnboardData, {
              type: 'server',
              message: Array.isArray(messages) ? (messages as string[])[0] : String(messages),
            });
          }
        });
      }
      const msg = typeof detail === 'object' ? JSON.stringify(detail) : String(detail || 'Unknown error');
      toast.error('Onboarding failed', msg);
    },
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) =>
      superAdminService.updateTenant(id, { is_active } as any),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tenants'] });
      toast.success('Updated', 'School status changed.');
    },
  });

  const bulkEmailMut = useMutation({
    mutationFn: (data: { tenant_ids: string[]; subject: string; body: string }) => superAdminService.bulkSendEmail(data),
    onSuccess: (result) => {
      toast.success('Bulk Email Sent', `Queued ${result.queued} emails.`);
      setShowBulkEmail(false);
      bulkEmailForm.reset();
      setSelectedIds(new Set());
    },
    onError: (err: any) => toast.error('Error', err?.response?.data?.error || 'Failed to send bulk email'),
  });

  const tenants: TenantListItem[] = data?.results ?? [];
  const platformDomain = (process.env.REACT_APP_PLATFORM_DOMAIN || 'learnpuddle.com').replace(':3000', '');

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };
  const toggleSelectAll = () => {
    if (selectedIds.size === tenants.length) setSelectedIds(new Set());
    else setSelectedIds(new Set(tenants.map((t) => t.id)));
  };

  return (
    <div className="space-y-5 sm:space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-[22px] font-bold text-slate-900 tracking-tight">Schools</h1>
          <p className="mt-0.5 text-[13px] text-slate-500">Manage all schools on the platform</p>
        </div>
        <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:items-center">
          {selectedIds.size > 0 && (
            <button
              onClick={() => setShowBulkEmail(true)}
              className="w-full rounded-lg border border-indigo-200 bg-indigo-50 px-4 py-2 text-[13px] font-semibold text-indigo-700 transition-colors hover:bg-indigo-100 sm:w-auto inline-flex items-center gap-2 justify-center"
            >
              <EnvelopeIcon className="h-4 w-4" />
              Email Selected ({selectedIds.size})
            </button>
          )}
          <button
            data-tour="superadmin-schools-onboard"
            onClick={() => setShowOnboard(true)}
            className="w-full rounded-lg bg-indigo-600 px-4 py-2 text-[13px] font-semibold text-white transition-colors hover:bg-indigo-700 shadow-sm sm:w-auto"
          >
            + Onboard School
          </button>
        </div>
      </div>

      {/* Search */}
      <div className="relative w-full max-w-md">
        <label htmlFor="superadmin-school-search" className="sr-only">
          Search schools
        </label>
        <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
        <input
          id="superadmin-school-search"
          name="school_search"
          data-tour="superadmin-schools-search"
          type="search"
          autoComplete="off"
          placeholder="Search schools..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full pl-9 pr-4 py-2 text-[13px] border border-slate-200/80 rounded-xl bg-white focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 transition-shadow placeholder:text-slate-400"
        />
      </div>

      {/* Table / Cards */}
      <div data-tour="superadmin-schools-table" className="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
        <div className="md:hidden">
          {isLoading ? (
            <div className="space-y-2.5 p-3">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="rounded-xl border border-slate-200/80 p-4 animate-pulse">
                  <div className="h-4 w-1/2 rounded bg-slate-100 mb-2" />
                  <div className="h-3 w-1/3 rounded bg-slate-100 mb-3" />
                  <div className="h-8 rounded bg-slate-100" />
                </div>
              ))}
            </div>
          ) : tenants.length === 0 ? (
            <div className="px-6 py-12 text-center">
              <BuildingOffice2Icon className="h-8 w-8 mx-auto text-slate-200 mb-2" />
              <p className="text-[13px] text-slate-400">No schools found</p>
            </div>
          ) : (
            <div className="space-y-2 p-2.5">
              {tenants.map((t) => (
                <div
                  key={t.id}
                  data-tour="superadmin-school-row"
                  data-tenant-id={t.id}
                  className="rounded-xl border border-slate-200/80 p-3.5 cursor-pointer hover:bg-slate-50 transition-colors"
                  onClick={() => nav(`/super-admin/schools/${t.id}`)}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-[13px] font-semibold text-slate-900 truncate">{t.name}</p>
                      <p className="text-[11px] text-slate-400 mt-0.5 truncate">{t.subdomain}.{platformDomain}</p>
                    </div>
                    {t.is_active ? (
                      <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-emerald-700 bg-emerald-50 rounded-full px-2 py-0.5 shrink-0">
                        <CheckCircleIcon className="h-3 w-3" /> Active
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-red-700 bg-red-50 rounded-full px-2 py-0.5 shrink-0">
                        <XCircleIcon className="h-3 w-3" /> Inactive
                      </span>
                    )}
                  </div>
                  <div className="mt-2.5 grid grid-cols-3 gap-2 text-[11px] text-slate-500">
                    <p>Teachers: <span className="font-semibold text-slate-900 tabular-nums">{t.teacher_count}</span></p>
                    <p>Courses: <span className="font-semibold text-slate-900 tabular-nums">{t.course_count}</span></p>
                    <p>Plan: <span className="font-semibold text-slate-900">{t.is_trial ? 'Trial' : 'Active'}</span></p>
                  </div>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      toggleMutation.mutate({ id: t.id, is_active: !t.is_active });
                    }}
                    className={`mt-3 w-full text-[11px] font-semibold px-3 py-1.5 rounded-lg border transition-colors ${
                      t.is_active
                        ? 'border-red-200 text-red-600 hover:bg-red-50'
                        : 'border-emerald-200 text-emerald-600 hover:bg-emerald-50'
                    }`}
                  >
                    {t.is_active ? 'Deactivate' : 'Activate'}
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="hidden md:block overflow-x-auto">
          <table className="min-w-[760px] w-full">
            <thead>
              <tr className="border-b border-slate-100">
                <th className="pl-4 pr-2 py-3 w-10">
                  <input
                    type="checkbox"
                    checked={tenants.length > 0 && selectedIds.size === tenants.length}
                    onChange={toggleSelectAll}
                    className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500/20"
                    aria-label="Select all schools"
                  />
                </th>
                <th className="px-4 py-3 text-left text-[11px] font-semibold text-slate-400 uppercase tracking-wide">School</th>
                <th className="px-4 py-3 text-left text-[11px] font-semibold text-slate-400 uppercase tracking-wide">Subdomain</th>
                <th className="px-4 py-3 text-left text-[11px] font-semibold text-slate-400 uppercase tracking-wide">Teachers</th>
                <th className="px-4 py-3 text-left text-[11px] font-semibold text-slate-400 uppercase tracking-wide">Courses</th>
                <th className="px-4 py-3 text-left text-[11px] font-semibold text-slate-400 uppercase tracking-wide">Status</th>
                <th className="px-4 py-3 text-left text-[11px] font-semibold text-slate-400 uppercase tracking-wide">Plan</th>
                <th className="px-4 py-3 text-right text-[11px] font-semibold text-slate-400 uppercase tracking-wide">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100/80">
              {isLoading ? (
                Array.from({ length: 4 }).map((_, i) => (
                  <tr key={i}><td colSpan={8} className="px-4 py-3.5"><div className="h-4 bg-slate-100 rounded animate-pulse" /></td></tr>
                ))
              ) : tenants.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-6 py-12 text-center">
                    <BuildingOffice2Icon className="h-8 w-8 mx-auto text-slate-200 mb-2" />
                    <p className="text-[13px] text-slate-400">No schools found</p>
                  </td>
                </tr>
              ) : (
                tenants.map((t) => (
                  <tr
                    key={t.id}
                    data-tour="superadmin-school-row"
                    data-tenant-id={t.id}
                    className={`hover:bg-slate-50/60 cursor-pointer transition-colors ${selectedIds.has(t.id) ? 'bg-indigo-50/50' : ''}`}
                    onClick={() => nav(`/super-admin/schools/${t.id}`)}
                  >
                    <td className="pl-4 pr-2 py-3.5" onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={selectedIds.has(t.id)}
                        onChange={() => toggleSelect(t.id)}
                        className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500/20"
                        aria-label={`Select ${t.name}`}
                      />
                    </td>
                    <td className="px-4 py-3.5 text-[13px] font-medium text-slate-900">{t.name}</td>
                    <td className="px-4 py-3.5 text-[13px] text-slate-500">{t.subdomain}</td>
                    <td className="px-4 py-3.5 text-[13px] text-slate-500 tabular-nums">{t.teacher_count}</td>
                    <td className="px-4 py-3.5 text-[13px] text-slate-500 tabular-nums">{t.course_count}</td>
                    <td className="px-4 py-3.5">
                      {t.is_active ? (
                        <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-emerald-700 bg-emerald-50 rounded-full px-2 py-0.5">
                          <CheckCircleIcon className="h-3 w-3" /> Active
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-red-600 bg-red-50 rounded-full px-2 py-0.5">
                          <XCircleIcon className="h-3 w-3" /> Inactive
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3.5 text-[13px]">
                      {t.is_trial ? (
                        <span className="text-amber-600 font-semibold">Trial</span>
                      ) : (
                        <span className="text-indigo-600 font-semibold">Active</span>
                      )}
                    </td>
                    <td className="px-4 py-3.5 text-right">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          toggleMutation.mutate({ id: t.id, is_active: !t.is_active });
                        }}
                        className={`text-[11px] font-semibold px-2.5 py-1 rounded-lg border transition-colors ${
                          t.is_active
                            ? 'border-red-200 text-red-600 hover:bg-red-50'
                            : 'border-emerald-200 text-emerald-600 hover:bg-emerald-50'
                        }`}
                      >
                        {t.is_active ? 'Deactivate' : 'Activate'}
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Pagination */}
      {data && data.count > 20 && (
        <div className="flex items-center justify-between px-1">
          <p className="text-[12px] text-slate-400">
            {data.count} school{data.count !== 1 ? 's' : ''} total
          </p>
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              className="rounded-lg border border-slate-200 px-3 py-1.5 text-[12px] font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              Previous
            </button>
            <span className="text-[12px] text-slate-500">
              Page {page} of {Math.ceil(data.count / 20)}
            </span>
            <button
              type="button"
              disabled={page >= Math.ceil(data.count / 20)}
              onClick={() => setPage((p) => p + 1)}
              className="rounded-lg border border-slate-200 px-3 py-1.5 text-[12px] font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              Next
            </button>
          </div>
        </div>
      )}

      {/* Onboard modal */}
      {showOnboard && (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-slate-900/50 backdrop-blur-[2px] p-0 sm:items-center sm:p-4">
          <form
            onSubmit={onboardForm.handleSubmit((data: OnboardData) => onboardMutation.mutate(data as OnboardPayload))}
            noValidate
            className="max-h-[92vh] w-full max-w-lg space-y-4 overflow-y-auto rounded-t-2xl bg-white p-5 pb-6 sm:rounded-2xl sm:p-6 shadow-xl"
          >
            <div className="flex items-center justify-between">
              <h3 className="text-[15px] font-bold text-slate-900">Onboard New School</h3>
              <button type="button" onClick={() => setShowOnboard(false)} className="text-slate-400 hover:text-slate-600 transition-colors">
                <XMarkIcon className="h-5 w-5" />
              </button>
            </div>

            <FormField
              control={onboardForm.control}
              name="school_name"
              label="School Name"
              autoComplete="organization"
              placeholder="ABC International School"
              id="school-name"
            />
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <FormField
                control={onboardForm.control}
                name="admin_first_name"
                label="Admin First Name"
                autoComplete="given-name"
                id="admin-first-name"
              />
              <FormField
                control={onboardForm.control}
                name="admin_last_name"
                label="Admin Last Name"
                autoComplete="family-name"
                id="admin-last-name"
              />
            </div>
            <FormField
              control={onboardForm.control}
              name="admin_email"
              label="Admin Email"
              type="email"
              autoComplete="email"
              placeholder="principal@school.com"
              id="admin-email"
            />
            <FormField
              control={onboardForm.control}
              name="admin_password"
              label="Initial Password"
              type="password"
              autoComplete="new-password"
              placeholder="Minimum 8 characters"
              id="admin-password"
            />
            <FormField
              control={onboardForm.control}
              name="subdomain"
              label="Subdomain (optional, auto-generated if blank)"
              autoComplete="off"
              placeholder="abcschool"
              id="school-subdomain"
            />

            <div className="sticky bottom-0 -mx-4 bg-white px-4 pt-3 sm:static sm:mx-0 sm:px-0">
              <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
                <Button variant="outline" type="button" onClick={() => setShowOnboard(false)}>Cancel</Button>
                <Button
                  variant="primary"
                  type="submit"
                  loading={onboardMutation.isPending}
                >
                  Onboard School
                </Button>
              </div>
            </div>
          </form>
        </div>
      )}

      {/* Bulk Email Modal */}
      {showBulkEmail && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-[2px]">
          <form
            onSubmit={bulkEmailForm.handleSubmit((data: BulkEmailData) =>
              bulkEmailMut.mutate({ tenant_ids: Array.from(selectedIds), ...data })
            )}
            noValidate
            className="bg-white rounded-2xl shadow-xl w-full max-w-md mx-4 p-6"
          >
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-[15px] font-bold text-slate-900">Email {selectedIds.size} School{selectedIds.size !== 1 ? 's' : ''}</h2>
              <button type="button" onClick={() => setShowBulkEmail(false)} className="text-slate-400 hover:text-slate-600 transition-colors"><XMarkIcon className="h-5 w-5" /></button>
            </div>
            <p className="text-[13px] text-slate-500 mb-4">
              This email will be sent to the school admin of each selected school.
            </p>
            <div className="space-y-3">
              <FormField
                control={bulkEmailForm.control}
                name="subject"
                label="Subject *"
                placeholder="Important update..."
              />
              <Controller
                control={bulkEmailForm.control}
                name="body"
                render={({ field, fieldState }: { field: any; fieldState: any }) => (
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Body *</label>
                    <textarea
                      rows={5}
                      value={field.value}
                      onChange={field.onChange}
                      onBlur={field.onBlur}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500"
                      placeholder="Dear School Administrator,..."
                    />
                    {fieldState.error && (
                      <p className="mt-1 text-sm text-red-600">{fieldState.error.message}</p>
                    )}
                  </div>
                )}
              />
            </div>
            <div className="flex justify-end gap-3 mt-5">
              <Button variant="outline" type="button" onClick={() => setShowBulkEmail(false)}>Cancel</Button>
              <Button
                variant="primary"
                type="submit"
                loading={bulkEmailMut.isPending}
              >
                Send to {selectedIds.size} School{selectedIds.size !== 1 ? 's' : ''}
              </Button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
};
