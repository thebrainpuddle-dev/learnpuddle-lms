import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { superAdminService, OnboardPayload, TenantListItem } from '../../services/superAdminService';
import { Button, Input, useToast } from '../../components/common';
import { usePageTitle } from '../../hooks/usePageTitle';
import {
  BuildingOffice2Icon,
  MagnifyingGlassIcon,
  XMarkIcon,
  CheckCircleIcon,
  XCircleIcon,
} from '@heroicons/react/24/outline';

export const SchoolsPage: React.FC = () => {
  usePageTitle('Schools');
  const toast = useToast();
  const queryClient = useQueryClient();
  const nav = useNavigate();
  const [searchParams] = useSearchParams();
  const [search, setSearch] = useState('');
  const [showOnboard, setShowOnboard] = useState(searchParams.get('onboard') === 'true');
  const [onboardForm, setOnboardForm] = useState<OnboardPayload>({
    school_name: '',
    admin_email: '',
    admin_first_name: '',
    admin_last_name: '',
    admin_password: '',
    subdomain: '',
  });

  const { data, isLoading } = useQuery({
    queryKey: ['tenants', search],
    queryFn: () => superAdminService.listTenants({ search: search || undefined }),
  });

  const onboardMutation = useMutation({
    mutationFn: superAdminService.onboardSchool,
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['tenants'] });
      queryClient.invalidateQueries({ queryKey: ['platformStats'] });
      setShowOnboard(false);
      setOnboardForm({ school_name: '', admin_email: '', admin_first_name: '', admin_last_name: '', admin_password: '', subdomain: '' });
      toast.success('School onboarded!', `Subdomain: ${result.subdomain} — Admin: ${result.admin_email}`);
    },
    onError: (err: any) => {
      const detail = err?.response?.data;
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

  const tenants: TenantListItem[] = data?.results ?? [];
  const platformDomain = (process.env.REACT_APP_PLATFORM_DOMAIN || 'learnpuddle.com').replace(':3000', '');

  return (
    <div className="space-y-5 sm:space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 sm:text-3xl">Schools</h1>
          <p className="mt-1 text-gray-500">Manage all schools on the platform</p>
        </div>
        <button
          data-tour="superadmin-schools-onboard"
          onClick={() => setShowOnboard(true)}
          className="w-full rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-700 sm:w-auto"
        >
          + Onboard School
        </button>
      </div>

      {/* Search */}
      <div className="relative w-full max-w-md">
        <label htmlFor="superadmin-school-search" className="sr-only">
          Search schools
        </label>
        <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-400" />
        <input
          id="superadmin-school-search"
          name="school_search"
          data-tour="superadmin-schools-search"
          type="search"
          autoComplete="off"
          placeholder="Search schools..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
        />
      </div>

      {/* Table / Cards */}
      <div data-tour="superadmin-schools-table" className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <div className="md:hidden">
          {isLoading ? (
            <div className="space-y-3 p-4">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="rounded-lg border border-gray-200 p-4 animate-pulse">
                  <div className="h-4 w-1/2 rounded bg-gray-100 mb-2" />
                  <div className="h-3 w-1/3 rounded bg-gray-100 mb-3" />
                  <div className="h-8 rounded bg-gray-100" />
                </div>
              ))}
            </div>
          ) : tenants.length === 0 ? (
            <div className="px-6 py-12 text-center">
              <BuildingOffice2Icon className="h-10 w-10 mx-auto text-gray-300 mb-3" />
              <p className="text-gray-500">No schools found</p>
            </div>
          ) : (
            <div className="space-y-3 p-3">
              {tenants.map((t) => (
                <div
                  key={t.id}
                  data-tour="superadmin-school-row"
                  data-tenant-id={t.id}
                  className="rounded-lg border border-gray-200 p-4 cursor-pointer hover:bg-gray-50"
                  onClick={() => nav(`/super-admin/schools/${t.id}`)}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="font-semibold text-gray-900 truncate">{t.name}</p>
                      <p className="text-xs text-gray-500 truncate">{t.subdomain}.{platformDomain}</p>
                    </div>
                    {t.is_active ? (
                      <span className="inline-flex items-center gap-1 text-[11px] font-medium text-emerald-700 bg-emerald-50 rounded-full px-2 py-1 shrink-0">
                        <CheckCircleIcon className="h-3.5 w-3.5" /> Active
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-[11px] font-medium text-red-700 bg-red-50 rounded-full px-2 py-1 shrink-0">
                        <XCircleIcon className="h-3.5 w-3.5" /> Inactive
                      </span>
                    )}
                  </div>
                  <div className="mt-3 grid grid-cols-2 gap-3 text-xs text-gray-600">
                    <p>Teachers: <span className="font-medium text-gray-900">{t.teacher_count}</span></p>
                    <p>Courses: <span className="font-medium text-gray-900">{t.course_count}</span></p>
                    <p>Plan: <span className="font-medium text-gray-900">{t.is_trial ? 'Trial' : 'Active'}</span></p>
                  </div>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      toggleMutation.mutate({ id: t.id, is_active: !t.is_active });
                    }}
                    className={`mt-3 w-full text-xs font-medium px-3 py-2 rounded-lg border ${
                      t.is_active
                        ? 'border-red-200 text-red-700 hover:bg-red-50'
                        : 'border-emerald-200 text-emerald-700 hover:bg-emerald-50'
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
          <table className="min-w-[760px] divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">School</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Subdomain</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Teachers</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Courses</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Plan</th>
                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {isLoading ? (
                Array.from({ length: 4 }).map((_, i) => (
                  <tr key={i}><td colSpan={7} className="px-6 py-4"><div className="h-4 bg-gray-100 rounded animate-pulse" /></td></tr>
                ))
              ) : tenants.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-6 py-12 text-center">
                    <BuildingOffice2Icon className="h-10 w-10 mx-auto text-gray-300 mb-3" />
                    <p className="text-gray-500">No schools found</p>
                  </td>
                </tr>
              ) : (
                tenants.map((t) => (
                  <tr
                    key={t.id}
                    data-tour="superadmin-school-row"
                    data-tenant-id={t.id}
                    className="hover:bg-gray-50 cursor-pointer"
                    onClick={() => nav(`/super-admin/schools/${t.id}`)}
                  >
                    <td className="px-6 py-4 font-medium text-gray-900">{t.name}</td>
                    <td className="px-6 py-4 text-sm text-gray-600">{t.subdomain}</td>
                    <td className="px-6 py-4 text-sm text-gray-600">{t.teacher_count}</td>
                    <td className="px-6 py-4 text-sm text-gray-600">{t.course_count}</td>
                    <td className="px-6 py-4">
                      {t.is_active ? (
                        <span className="inline-flex items-center gap-1 text-xs font-medium text-emerald-700 bg-emerald-50 rounded-full px-2 py-1">
                          <CheckCircleIcon className="h-3.5 w-3.5" /> Active
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-xs font-medium text-red-700 bg-red-50 rounded-full px-2 py-1">
                          <XCircleIcon className="h-3.5 w-3.5" /> Inactive
                        </span>
                      )}
                    </td>
                    <td className="px-6 py-4 text-sm">
                      {t.is_trial ? (
                        <span className="text-amber-600 font-medium">Trial</span>
                      ) : (
                        <span className="text-indigo-600 font-medium">Active</span>
                      )}
                    </td>
                    <td className="px-6 py-4 text-right">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          toggleMutation.mutate({ id: t.id, is_active: !t.is_active });
                        }}
                        className={`text-xs font-medium px-3 py-1 rounded-lg border ${
                          t.is_active
                            ? 'border-red-200 text-red-700 hover:bg-red-50'
                            : 'border-emerald-200 text-emerald-700 hover:bg-emerald-50'
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

      {/* Onboard modal */}
      {showOnboard && (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/50 p-0 sm:items-center sm:p-4">
          <div className="max-h-[92vh] w-full max-w-lg space-y-4 overflow-y-auto rounded-t-2xl bg-white p-4 pb-6 sm:rounded-xl sm:p-6">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-bold text-gray-900">Onboard New School</h3>
              <button type="button" onClick={() => setShowOnboard(false)} className="text-gray-400 hover:text-gray-600">
                <XMarkIcon className="h-6 w-6" />
              </button>
            </div>

            <Input
              id="school-name"
              name="school_name"
              label="School Name"
              autoComplete="organization"
              value={onboardForm.school_name}
              onChange={(e) => setOnboardForm({ ...onboardForm, school_name: e.target.value })}
              placeholder="ABC International School"
              required
            />
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Input
                id="admin-first-name"
                name="admin_first_name"
                label="Admin First Name"
                autoComplete="given-name"
                value={onboardForm.admin_first_name}
                onChange={(e) => setOnboardForm({ ...onboardForm, admin_first_name: e.target.value })}
                required
              />
              <Input
                id="admin-last-name"
                name="admin_last_name"
                label="Admin Last Name"
                autoComplete="family-name"
                value={onboardForm.admin_last_name}
                onChange={(e) => setOnboardForm({ ...onboardForm, admin_last_name: e.target.value })}
                required
              />
            </div>
            <Input
              id="admin-email"
              name="admin_email"
              label="Admin Email"
              type="email"
              autoComplete="email"
              value={onboardForm.admin_email}
              onChange={(e) => setOnboardForm({ ...onboardForm, admin_email: e.target.value })}
              placeholder="principal@school.com"
              required
            />
            <Input
              id="admin-password"
              name="admin_password"
              label="Initial Password"
              type="password"
              autoComplete="new-password"
              value={onboardForm.admin_password}
              onChange={(e) => setOnboardForm({ ...onboardForm, admin_password: e.target.value })}
              placeholder="Minimum 8 characters"
              required
            />
            <Input
              id="school-subdomain"
              name="subdomain"
              label="Subdomain (optional, auto-generated if blank)"
              autoComplete="off"
              value={onboardForm.subdomain || ''}
              onChange={(e) => setOnboardForm({ ...onboardForm, subdomain: e.target.value })}
              placeholder="abcschool"
            />

            <div className="sticky bottom-0 -mx-4 bg-white px-4 pt-3 sm:static sm:mx-0 sm:px-0">
              <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
                <Button variant="outline" onClick={() => setShowOnboard(false)}>Cancel</Button>
                <Button
                  variant="primary"
                  onClick={() => onboardMutation.mutate(onboardForm)}
                  loading={onboardMutation.isPending}
                  disabled={!onboardForm.school_name || !onboardForm.admin_email || !onboardForm.admin_password}
                >
                  Onboard School
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
