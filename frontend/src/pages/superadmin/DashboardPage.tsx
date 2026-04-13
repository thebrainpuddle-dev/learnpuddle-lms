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
    { label: 'Total Schools', value: stats?.total_tenants ?? '—', icon: BuildingOffice2Icon, color: 'bg-indigo-500', lightBg: 'bg-indigo-50' },
    { label: 'Active Schools', value: stats?.active_tenants ?? '—', icon: CheckBadgeIcon, color: 'bg-emerald-500', lightBg: 'bg-emerald-50' },
    { label: 'Trial Schools', value: stats?.trial_tenants ?? '—', icon: ClockIcon, color: 'bg-amber-500', lightBg: 'bg-amber-50' },
    { label: 'Total Users', value: stats?.total_users ?? '—', icon: UsersIcon, color: 'bg-blue-500', lightBg: 'bg-blue-50' },
    { label: 'Total Teachers', value: stats?.total_teachers ?? '—', icon: AcademicCapIcon, color: 'bg-violet-500', lightBg: 'bg-violet-50' },
  ];

  const planColors: Record<string, string> = {
    FREE: 'bg-gray-100 text-gray-600',
    STARTER: 'bg-blue-50 text-blue-600',
    PRO: 'bg-indigo-50 text-indigo-600',
    ENTERPRISE: 'bg-violet-50 text-violet-600',
  };

  const planBarColors: Record<string, string> = {
    FREE: 'bg-gray-400',
    STARTER: 'bg-blue-500',
    PRO: 'bg-indigo-500',
    ENTERPRISE: 'bg-violet-500',
  };

  return (
    <div className="space-y-6" data-tour="superadmin-dashboard-page">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-[22px] font-bold text-slate-900 tracking-tight">
            Platform Dashboard
          </h1>
          <p className="mt-0.5 text-[13px] text-slate-500">
            Overview of all schools on the platform
          </p>
        </div>
        <button
          data-tour="superadmin-dashboard-onboard"
          onClick={() => navigate('/super-admin/schools?onboard=true')}
          className="w-full rounded-lg bg-indigo-600 px-4 py-2 text-[13px] font-semibold text-white transition-colors hover:bg-indigo-700 shadow-sm sm:w-auto"
        >
          + Onboard School
        </button>
      </div>

      {/* Stat cards */}
      {isLoading ? (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-[88px] rounded-2xl bg-white border border-slate-200/80 animate-pulse" />
          ))}
        </div>
      ) : (
        <div
          data-tour="superadmin-dashboard-stats"
          className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3"
        >
          {cards.map((card) => (
            <div
              key={card.label}
              className="flex items-center gap-3 rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm hover:shadow-md transition-shadow"
            >
              <div className={`${card.color} h-10 w-10 rounded-xl flex items-center justify-center flex-shrink-0`}>
                <card.icon className="h-[18px] w-[18px] text-white" />
              </div>
              <div>
                <p className="text-[20px] font-bold text-slate-900 leading-tight tabular-nums">
                  {card.value}
                </p>
                <p className="text-[11px] text-slate-400 mt-0.5 font-medium">
                  {card.label}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* Plan Distribution */}
        <div
          data-tour="superadmin-dashboard-plan-distribution"
          className="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden"
        >
          <div className="px-5 py-3.5 border-b border-slate-100">
            <h2 className="text-[13px] font-semibold text-slate-900">
              Plan Distribution
            </h2>
          </div>
          <div className="p-5">
            {stats?.plan_distribution ? (
              <div className="space-y-3.5">
                {['FREE', 'STARTER', 'PRO', 'ENTERPRISE'].map((plan) => {
                  const count = stats.plan_distribution?.[plan] ?? 0;
                  const total = stats.total_tenants || 1;
                  const pct = Math.round((count / total) * 100);
                  return (
                    <div key={plan}>
                      <div className="flex justify-between items-center mb-1.5">
                        <span
                          className={`px-2 py-[2px] rounded-md text-[10px] font-semibold uppercase tracking-wide ${planColors[plan] || 'bg-gray-100'}`}
                        >
                          {plan}
                        </span>
                        <span className="text-[11px] text-slate-500 font-medium tabular-nums">
                          {count} school{count !== 1 ? 's' : ''}
                        </span>
                      </div>
                      <div className="h-[5px] bg-slate-100 rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all duration-500 ${planBarColors[plan] || 'bg-slate-400'}`}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="text-slate-400 text-[13px]">Loading...</p>
            )}
          </div>
        </div>

        {/* Recent Onboards */}
        <div
          data-tour="superadmin-dashboard-recent-onboards"
          className="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden"
        >
          <div className="px-5 py-3.5 border-b border-slate-100">
            <h2 className="text-[13px] font-semibold text-slate-900">
              Recently Onboarded
            </h2>
          </div>
          <div className="p-2">
            {stats?.recent_onboards && stats.recent_onboards.length > 0 ? (
              <div className="space-y-0.5">
                {stats.recent_onboards.map((s: any) => (
                  <button
                    key={s.id}
                    onClick={() => navigate(`/super-admin/schools/${s.id}`)}
                    className="flex w-full items-center justify-between rounded-xl p-3 text-left hover:bg-slate-50 transition-colors"
                  >
                    <div>
                      <p className="text-[13px] font-medium text-slate-900">
                        {s.name}
                      </p>
                      <p className="text-[11px] text-slate-400 mt-0.5">
                        {s.subdomain}.
                        {(
                          process.env.REACT_APP_PLATFORM_DOMAIN ||
                          'learnpuddle.com'
                        ).replace(':3000', '')}
                      </p>
                    </div>
                    <span className="text-[10px] text-slate-400 font-medium tabular-nums">
                      {new Date(s.created_at).toLocaleDateString('en-US', {
                        month: 'short',
                        day: 'numeric',
                      })}
                    </span>
                  </button>
                ))}
              </div>
            ) : (
              <div className="py-8 text-center">
                <BuildingOffice2Icon className="h-7 w-7 mx-auto text-slate-200 mb-2" />
                <p className="text-[13px] text-slate-400">No schools yet</p>
              </div>
            )}
          </div>
        </div>

        {/* Schools Near Limits */}
        <div
          data-tour="superadmin-dashboard-near-limits"
          className="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden"
        >
          <div className="px-5 py-3.5 border-b border-slate-100">
            <h2 className="text-[13px] font-semibold text-slate-900">
              Near Limits
            </h2>
          </div>
          <div className="p-2">
            {stats?.schools_near_limits && stats.schools_near_limits.length > 0 ? (
              <div className="space-y-1">
                {stats.schools_near_limits.slice(0, 5).map((s: any, i: number) => (
                  <button
                    key={`${s.id}-${s.resource}-${i}`}
                    onClick={() => navigate(`/super-admin/schools/${s.id}`)}
                    className="w-full flex items-center gap-2.5 p-3 rounded-xl hover:bg-amber-50/50 text-left transition-colors"
                  >
                    <div className="h-8 w-8 rounded-lg bg-amber-50 flex items-center justify-center flex-shrink-0">
                      <ExclamationTriangleIcon className="h-4 w-4 text-amber-500" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-[13px] font-medium text-slate-900 truncate">
                        {s.name}
                      </p>
                      <p className="text-[11px] text-amber-600 font-medium">
                        {s.resource}: {s.used}/{s.limit}
                      </p>
                    </div>
                  </button>
                ))}
              </div>
            ) : (
              <div className="py-8 text-center">
                <CheckBadgeIcon className="h-7 w-7 mx-auto text-emerald-200 mb-2" />
                <p className="text-[13px] text-slate-400">
                  All schools within limits
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
