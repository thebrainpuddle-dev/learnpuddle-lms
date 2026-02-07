import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { superAdminService, OnboardPayload, TenantListItem } from '../../services/superAdminService';
import { Button, Input, useToast } from '../../components/common';
import {
  BuildingOffice2Icon,
  MagnifyingGlassIcon,
  XMarkIcon,
  CheckCircleIcon,
  XCircleIcon,
} from '@heroicons/react/24/outline';

export const SchoolsPage: React.FC = () => {
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

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Schools</h1>
          <p className="mt-1 text-gray-500">Manage all schools on the platform</p>
        </div>
        <button
          onClick={() => setShowOnboard(true)}
          className="px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 transition-colors"
        >
          + Onboard School
        </button>
      </div>

      {/* Search */}
      <div className="relative max-w-md">
        <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-400" />
        <input
          type="text"
          placeholder="Search schools..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
        />
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <table className="min-w-full divide-y divide-gray-200">
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
                <tr key={t.id} className="hover:bg-gray-50 cursor-pointer" onClick={() => nav(`/super-admin/schools/${t.id}`)}>
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
                      onClick={() => toggleMutation.mutate({ id: t.id, is_active: !t.is_active })}
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

      {/* Onboard modal */}
      {showOnboard && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl p-6 max-w-lg w-full mx-4 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-bold text-gray-900">Onboard New School</h3>
              <button onClick={() => setShowOnboard(false)} className="text-gray-400 hover:text-gray-600">
                <XMarkIcon className="h-6 w-6" />
              </button>
            </div>

            <Input
              label="School Name"
              value={onboardForm.school_name}
              onChange={(e) => setOnboardForm({ ...onboardForm, school_name: e.target.value })}
              placeholder="ABC International School"
              required
            />
            <div className="grid grid-cols-2 gap-4">
              <Input
                label="Admin First Name"
                value={onboardForm.admin_first_name}
                onChange={(e) => setOnboardForm({ ...onboardForm, admin_first_name: e.target.value })}
                required
              />
              <Input
                label="Admin Last Name"
                value={onboardForm.admin_last_name}
                onChange={(e) => setOnboardForm({ ...onboardForm, admin_last_name: e.target.value })}
                required
              />
            </div>
            <Input
              label="Admin Email"
              type="email"
              value={onboardForm.admin_email}
              onChange={(e) => setOnboardForm({ ...onboardForm, admin_email: e.target.value })}
              placeholder="principal@school.com"
              required
            />
            <Input
              label="Initial Password"
              type="password"
              value={onboardForm.admin_password}
              onChange={(e) => setOnboardForm({ ...onboardForm, admin_password: e.target.value })}
              placeholder="Minimum 8 characters"
              required
            />
            <Input
              label="Subdomain (optional, auto-generated if blank)"
              value={onboardForm.subdomain || ''}
              onChange={(e) => setOnboardForm({ ...onboardForm, subdomain: e.target.value })}
              placeholder="abcschool"
            />

            <div className="flex justify-end gap-3 pt-2">
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
      )}
    </div>
  );
};
