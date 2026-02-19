import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { superAdminService } from '../../services/superAdminService';
import { usePageTitle } from '../../hooks/usePageTitle';
import {
  BuildingOffice2Icon,
  UsersIcon,
  AcademicCapIcon,
  CheckBadgeIcon,
  ClockIcon,
  ExclamationTriangleIcon,
} from '@heroicons/react/24/outline';

export const SuperAdminDashboardPage: React.FC = () => {
  usePageTitle('Platform Dashboard');
  const navigate = useNavigate();
  const { data: stats, isLoading } = useQuery({
    queryKey: ['platformStats'],
    queryFn: superAdminService.getStats,
  });

  const cards = [
    { label: 'Total Schools', value: stats?.total_tenants ?? '-', icon: BuildingOffice2Icon, color: 'bg-indigo-500' },
    { label: 'Active Schools', value: stats?.active_tenants ?? '-', icon: CheckBadgeIcon, color: 'bg-emerald-500' },
    { label: 'Trial Schools', value: stats?.trial_tenants ?? '-', icon: ClockIcon, color: 'bg-amber-500' },
    { label: 'Total Users', value: stats?.total_users ?? '-', icon: UsersIcon, color: 'bg-blue-500' },
    { label: 'Total Teachers', value: stats?.total_teachers ?? '-', icon: AcademicCapIcon, color: 'bg-purple-500' },
  ];

  const planColors: Record<string, string> = {
    FREE: 'bg-gray-100 text-gray-700',
    STARTER: 'bg-blue-100 text-blue-700',
    PRO: 'bg-indigo-100 text-indigo-700',
    ENTERPRISE: 'bg-purple-100 text-purple-700',
  };

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Platform Dashboard</h1>
          <p className="mt-1 text-gray-500">Overview of all schools on the platform</p>
        </div>
        <button
          onClick={() => navigate('/super-admin/schools?onboard=true')}
          className="px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 transition-colors"
        >
          + Onboard School
        </button>
      </div>

      {/* Stat cards */}
      {isLoading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="bg-white rounded-xl border border-gray-200 p-6 animate-pulse">
              <div className="h-4 bg-gray-200 rounded w-2/3 mb-3" />
              <div className="h-8 bg-gray-200 rounded w-1/3" />
            </div>
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
          {cards.map((card) => (
            <div key={card.label} className="bg-white rounded-xl border border-gray-200 p-6 flex items-start gap-4">
              <div className={`${card.color} p-2.5 rounded-lg`}>
                <card.icon className="h-5 w-5 text-white" />
              </div>
              <div>
                <p className="text-sm text-gray-500">{card.label}</p>
                <p className="text-2xl font-bold text-gray-900 mt-1">{card.value}</p>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Plan Distribution */}
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="font-semibold text-gray-900 mb-4">Plan Distribution</h2>
          {stats?.plan_distribution ? (
            <div className="space-y-3">
              {['FREE', 'STARTER', 'PRO', 'ENTERPRISE'].map((plan) => {
                const count = stats.plan_distribution?.[plan] ?? 0;
                const total = stats.total_tenants || 1;
                const pct = Math.round((count / total) * 100);
                return (
                  <div key={plan}>
                    <div className="flex justify-between text-sm mb-1">
                      <span className={`px-2 py-0.5 rounded text-xs font-medium ${planColors[plan] || 'bg-gray-100'}`}>{plan}</span>
                      <span className="text-gray-600">{count} school{count !== 1 ? 's' : ''}</span>
                    </div>
                    <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                      <div className="h-full bg-indigo-500 rounded-full" style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                );
              })}
            </div>
          ) : <p className="text-gray-400 text-sm">Loading...</p>}
        </div>

        {/* Recent Onboards */}
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="font-semibold text-gray-900 mb-4">Recently Onboarded</h2>
          {stats?.recent_onboards && stats.recent_onboards.length > 0 ? (
            <div className="space-y-3">
              {stats.recent_onboards.map((s: any) => (
                <button
                  key={s.id}
                  onClick={() => navigate(`/super-admin/schools/${s.id}`)}
                  className="w-full flex items-center justify-between p-3 rounded-lg hover:bg-gray-50 text-left"
                >
                  <div>
                    <p className="text-sm font-medium text-gray-900">{s.name}</p>
                    <p className="text-xs text-gray-500">{s.subdomain}.{(process.env.REACT_APP_PLATFORM_DOMAIN || 'learnpuddle.com').replace(':3000', '')}</p>
                  </div>
                  <span className="text-xs text-gray-400">{new Date(s.created_at).toLocaleDateString()}</span>
                </button>
              ))}
            </div>
          ) : <p className="text-gray-400 text-sm">No schools yet</p>}
        </div>

        {/* Schools Near Limits */}
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="font-semibold text-gray-900 mb-4">Near Limits</h2>
          {stats?.schools_near_limits && stats.schools_near_limits.length > 0 ? (
            <div className="space-y-3">
              {stats.schools_near_limits.slice(0, 5).map((s: any, i: number) => (
                <button
                  key={`${s.id}-${s.resource}-${i}`}
                  onClick={() => navigate(`/super-admin/schools/${s.id}`)}
                  className="w-full flex items-center gap-3 p-3 rounded-lg hover:bg-amber-50 text-left border border-amber-100"
                >
                  <ExclamationTriangleIcon className="h-5 w-5 text-amber-500 shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-900 truncate">{s.name}</p>
                    <p className="text-xs text-amber-600">{s.resource}: {s.used}/{s.limit}</p>
                  </div>
                </button>
              ))}
            </div>
          ) : <p className="text-gray-400 text-sm">All schools within limits</p>}
        </div>
      </div>
    </div>
  );
};
