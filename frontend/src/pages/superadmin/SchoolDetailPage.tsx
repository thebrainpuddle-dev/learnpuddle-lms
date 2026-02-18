import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { superAdminService, PLAN_OPTIONS, FEATURE_FLAGS } from '../../services/superAdminService';
import { Button, useToast } from '../../components/common';
import { usePageTitle } from '../../hooks/usePageTitle';
import {
  ArrowLeftIcon,
  CheckCircleIcon,
  XCircleIcon,
  ArrowTopRightOnSquareIcon,
} from '@heroicons/react/24/outline';

type Tab = 'overview' | 'plan' | 'features';

export const SchoolDetailPage: React.FC = () => {
  usePageTitle('School Details');
  const { tenantId } = useParams<{ tenantId: string }>();
  const navigate = useNavigate();
  const toast = useToast();
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>('overview');

  const { data: tenant, isLoading } = useQuery({
    queryKey: ['tenant', tenantId],
    queryFn: () => superAdminService.getTenant(tenantId!),
    enabled: !!tenantId,
  });

  const { data: usage } = useQuery({
    queryKey: ['tenantUsage', tenantId],
    queryFn: () => superAdminService.getTenantUsage(tenantId!),
    enabled: !!tenantId,
  });

  const updateMut = useMutation({
    mutationFn: (data: Record<string, any>) => superAdminService.updateTenant(tenantId!, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['tenant', tenantId] }); toast.success('Saved', ''); },
    onError: () => toast.error('Failed', 'Could not save changes.'),
  });

  const applyPlanMut = useMutation({
    mutationFn: (plan: string) => superAdminService.applyPlan(tenantId!, plan),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['tenant', tenantId] }); toast.success('Plan applied', ''); },
  });

  const resetPwMut = useMutation({
    mutationFn: () => superAdminService.resetAdminPassword(tenantId!),
    onSuccess: (d) => toast.success('Password reset', `New password emailed to ${d.email}`),
  });

  const impersonateMut = useMutation({
    mutationFn: () => superAdminService.impersonate(tenantId!),
    onSuccess: (d) => {
      const url = `http://${d.tenant_subdomain}.localhost:3000`;
      const w = window.open(url, '_blank');
      if (w) {
        setTimeout(() => {
          w.sessionStorage.setItem('access_token', d.tokens.access);
          w.sessionStorage.setItem('refresh_token', d.tokens.refresh);
          w.location.reload();
        }, 1000);
      }
      toast.success('Impersonating', d.user_email);
    },
  });

  if (isLoading || !tenant) {
    return <div className="flex items-center justify-center min-h-[60vh]"><div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600" /></div>;
  }

  const UsageBar: React.FC<{ label: string; used: number; limit: number; unit?: string }> = ({ label, used, limit, unit }) => {
    const pct = limit > 0 ? Math.min(100, Math.round((used / limit) * 100)) : 0;
    const color = pct > 80 ? 'bg-red-500' : pct > 60 ? 'bg-amber-500' : 'bg-emerald-500';
    return (
      <div>
        <div className="flex justify-between text-sm mb-1"><span className="text-gray-600">{label}</span><span className="font-medium text-gray-900">{used}{unit ? ` ${unit}` : ''} / {limit}{unit ? ` ${unit}` : ''}</span></div>
        <div className="h-2 bg-gray-100 rounded-full overflow-hidden"><div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} /></div>
      </div>
    );
  };

  const tabs: { key: Tab; label: string }[] = [
    { key: 'overview', label: 'Overview' },
    { key: 'plan', label: 'Plan & Limits' },
    { key: 'features', label: 'Features' },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <button onClick={() => navigate('/super-admin/schools')} className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg"><ArrowLeftIcon className="h-5 w-5" /></button>
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-gray-900">{tenant.name}</h1>
            {tenant.is_active
              ? <span className="inline-flex items-center gap-1 text-xs font-medium text-emerald-700 bg-emerald-50 rounded-full px-2 py-1"><CheckCircleIcon className="h-3.5 w-3.5" /> Active</span>
              : <span className="inline-flex items-center gap-1 text-xs font-medium text-red-700 bg-red-50 rounded-full px-2 py-1"><XCircleIcon className="h-3.5 w-3.5" /> Inactive</span>}
            <span className="text-xs font-medium text-indigo-700 bg-indigo-50 rounded-full px-2 py-1">{tenant.plan}</span>
          </div>
          <p className="text-sm text-gray-500 mt-0.5">{tenant.subdomain}.lms.com</p>
        </div>
        <Button variant="outline" onClick={() => impersonateMut.mutate()} loading={impersonateMut.isPending}>
          <ArrowTopRightOnSquareIcon className="h-4 w-4 mr-2" />Login as Admin
        </Button>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200">
        <nav className="-mb-px flex space-x-8">
          {tabs.map((t) => (
            <button key={t.key} onClick={() => setTab(t.key)} className={`py-3 px-1 border-b-2 text-sm font-medium transition-colors ${tab === t.key ? 'border-indigo-500 text-indigo-600' : 'border-transparent text-gray-500 hover:text-gray-700'}`}>
              {t.label}
            </button>
          ))}
        </nav>
      </div>

      {/* Overview */}
      {tab === 'overview' && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-6">
            {/* Usage */}
            <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
              <h2 className="font-semibold text-gray-900">Usage</h2>
              {usage && (
                <>
                  <UsageBar label="Teachers" used={usage.teachers.used} limit={usage.teachers.limit} />
                  <UsageBar label="Courses" used={usage.courses.used} limit={usage.courses.limit} />
                  <UsageBar label="Storage" used={usage.storage_mb.used} limit={usage.storage_mb.limit} unit="MB" />
                </>
              )}
            </div>
            {/* Notes */}
            <div className="bg-white rounded-xl border border-gray-200 p-6">
              <h2 className="font-semibold text-gray-900 mb-3">Internal Notes</h2>
              <textarea
                defaultValue={tenant.internal_notes}
                onBlur={(e) => { if (e.target.value !== tenant.internal_notes) updateMut.mutate({ internal_notes: e.target.value }); }}
                rows={4}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500"
                placeholder="Add internal notes about this school..."
              />
            </div>
          </div>
          {/* Sidebar info */}
          <div className="space-y-6">
            <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-3">
              <h2 className="font-semibold text-gray-900">School Info</h2>
              <div className="text-sm"><span className="text-gray-500">Admin:</span> <span className="text-gray-900">{tenant.admin_name || '-'}</span></div>
              <div className="text-sm"><span className="text-gray-500">Email:</span> <span className="text-gray-900">{tenant.admin_email || '-'}</span></div>
              <div className="text-sm"><span className="text-gray-500">Created:</span> <span className="text-gray-900">{new Date(tenant.created_at).toLocaleDateString()}</span></div>
              <div className="text-sm"><span className="text-gray-500">Plan:</span> <span className="text-gray-900">{tenant.plan}</span></div>
              {tenant.is_trial && <div className="text-sm"><span className="text-gray-500">Trial ends:</span> <span className="text-gray-900">{tenant.trial_end_date || 'No date set'}</span></div>}
            </div>
            <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-3">
              <h2 className="font-semibold text-gray-900">Actions</h2>
              <button onClick={() => updateMut.mutate({ is_active: !tenant.is_active })} className={`w-full text-sm font-medium px-4 py-2 rounded-lg border ${tenant.is_active ? 'border-red-200 text-red-700 hover:bg-red-50' : 'border-emerald-200 text-emerald-700 hover:bg-emerald-50'}`}>
                {tenant.is_active ? 'Deactivate School' : 'Activate School'}
              </button>
              <button onClick={() => { if (window.confirm('Reset admin password?')) resetPwMut.mutate(); }} className="w-full text-sm font-medium px-4 py-2 rounded-lg border border-gray-200 text-gray-700 hover:bg-gray-50">
                Reset Admin Password
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Plan & Limits */}
      {tab === 'plan' && (
        <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-6">
          <div>
            <h2 className="font-semibold text-gray-900 mb-3">Subscription Plan</h2>
            <div className="flex items-center gap-3">
              {PLAN_OPTIONS.map((p) => (
                <button key={p} onClick={() => applyPlanMut.mutate(p)} className={`px-4 py-2 text-sm font-medium rounded-lg border transition-colors ${tenant.plan === p ? 'bg-indigo-600 text-white border-indigo-600' : 'border-gray-200 text-gray-700 hover:border-indigo-300'}`}>
                  {p}
                </button>
              ))}
            </div>
            <p className="text-xs text-gray-500 mt-2">Clicking a plan applies its preset limits and features. You can override individual values below.</p>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Max Teachers</label>
              <input type="number" defaultValue={tenant.max_teachers} onBlur={(e) => updateMut.mutate({ max_teachers: Number(e.target.value) })} className="w-full px-3 py-2 border border-gray-300 rounded-lg" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Max Courses</label>
              <input type="number" defaultValue={tenant.max_courses} onBlur={(e) => updateMut.mutate({ max_courses: Number(e.target.value) })} className="w-full px-3 py-2 border border-gray-300 rounded-lg" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Max Storage (MB)</label>
              <input type="number" defaultValue={tenant.max_storage_mb} onBlur={(e) => updateMut.mutate({ max_storage_mb: Number(e.target.value) })} className="w-full px-3 py-2 border border-gray-300 rounded-lg" />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Max Video Duration (min)</label>
              <input type="number" defaultValue={tenant.max_video_duration_minutes} onBlur={(e) => updateMut.mutate({ max_video_duration_minutes: Number(e.target.value) })} className="w-full px-3 py-2 border border-gray-300 rounded-lg" />
            </div>
          </div>

          <div>
            <h3 className="font-medium text-gray-900 mb-2">Trial Settings</h3>
            <div className="flex items-center gap-4">
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={tenant.is_trial} onChange={(e) => updateMut.mutate({ is_trial: e.target.checked })} className="rounded border-gray-300 text-indigo-600" />
                Is Trial
              </label>
              <input type="date" defaultValue={tenant.trial_end_date || ''} onBlur={(e) => updateMut.mutate({ trial_end_date: e.target.value || null })} className="px-3 py-2 border border-gray-300 rounded-lg text-sm" />
            </div>
          </div>

          {/* Usage bars */}
          {usage && (
            <div className="space-y-3 pt-4 border-t border-gray-200">
              <h3 className="font-medium text-gray-900">Current Usage</h3>
              <UsageBar label="Teachers" used={usage.teachers.used} limit={usage.teachers.limit} />
              <UsageBar label="Courses" used={usage.courses.used} limit={usage.courses.limit} />
              <UsageBar label="Storage" used={usage.storage_mb.used} limit={usage.storage_mb.limit} unit="MB" />
            </div>
          )}
        </div>
      )}

      {/* Features */}
      {tab === 'features' && (
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="font-semibold text-gray-900 mb-4">Feature Flags</h2>
          <p className="text-sm text-gray-500 mb-6">Toggle features on/off for this school. Changes save immediately.</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {FEATURE_FLAGS.map((f) => (
              <label key={f.key} className="flex items-center justify-between p-4 border border-gray-200 rounded-lg hover:bg-gray-50 cursor-pointer">
                <span className="text-sm font-medium text-gray-900">{f.label}</span>
                <div className="relative">
                  <input
                    type="checkbox"
                    checked={(tenant as any)[f.key] ?? false}
                    onChange={(e) => updateMut.mutate({ [f.key]: e.target.checked })}
                    className="sr-only peer"
                  />
                  <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-indigo-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-indigo-600" />
                </div>
              </label>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
