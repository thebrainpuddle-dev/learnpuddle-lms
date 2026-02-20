// src/pages/admin/DashboardPage.tsx

import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { StatsCard } from '../../components/admin/StatsCard';
import { adminService, RecentActivityItem } from '../../services/adminService';
import { useTenantStore } from '../../stores/tenantStore';
import {
  AcademicCapIcon,
  UserGroupIcon,
  ChartBarIcon,
  ClockIcon,
  DocumentCheckIcon,
  TrophyIcon,
  ExclamationTriangleIcon,
  ArrowTrendingUpIcon,
  BookOpenIcon,
  SparklesIcon,
  MegaphoneIcon,
  CalendarDaysIcon,
} from '@heroicons/react/24/outline';
import { useNavigate } from 'react-router-dom';
import { usePageTitle } from '../../hooks/usePageTitle';

function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSeconds = Math.floor(diffMs / 1000);
  const diffMinutes = Math.floor(diffSeconds / 60);
  const diffHours = Math.floor(diffMinutes / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffSeconds < 60) return 'just now';
  if (diffMinutes < 60) return `${diffMinutes}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays === 1) return 'yesterday';
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}

export const DashboardPage: React.FC = () => {
  usePageTitle('Command Center');
  const navigate = useNavigate();
  const { plan, usage, limits, theme } = useTenantStore();

  const { data: stats, isLoading } = useQuery({
    queryKey: ['adminDashboardStats'],
    queryFn: adminService.getTenantStats,
    refetchInterval: 30000, // Auto-refresh every 30 seconds for real-time progress
  });

  const recentActivity: RecentActivityItem[] = stats?.recent_activity || [];

  const UsageBar: React.FC<{ label: string; used: number; limit: number; unit?: string; color: string }> = ({ label, used, limit, unit, color }) => {
    const pct = limit > 0 ? Math.min(100, Math.round((used / limit) * 100)) : 0;
    return (
      <div>
        <div className="flex justify-between text-xs font-medium mb-1.5 opacity-80">
          <span>{label}</span>
          <span>{used}{unit ? ` ${unit}` : ''} / {limit}</span>
        </div>
        <div className="h-2.5 bg-black/5 rounded-full overflow-hidden">
          <div className={`h-full rounded-full transition-all duration-500 ${color}`} style={{ width: `${pct}%` }} />
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-8 max-w-7xl mx-auto pb-12">
      {/* ─── Hero Header ──────────────────────────────────────────────── */}
      <div data-tour="admin-dashboard-hero" className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-indigo-600 via-purple-600 to-indigo-800 text-white p-8 shadow-xl shadow-indigo-200/50">
        <div className="absolute top-0 right-0 p-12 opacity-10 transform translate-x-1/4 -translate-y-1/4">
          <SparklesIcon className="w-64 h-64" />
        </div>
        <div className="relative z-10 flex flex-col md:flex-row md:items-end justify-between gap-6">
          <div>
            <div className="inline-flex items-center gap-2 bg-white/10 backdrop-blur-md rounded-full px-3 py-1 text-xs font-medium text-indigo-100 mb-3 border border-white/20">
              <MegaphoneIcon className="w-3 h-3" />
              <span>Welcome to the Command Center</span>
            </div>
            <h1 className="text-3xl md:text-4xl font-bold tracking-tight mb-2">
              Hello, Admin! 👋
            </h1>
            <p className="text-indigo-100 text-lg max-w-xl leading-relaxed">
              Here's what's happening at <span className="font-semibold text-white">{theme.name}</span> today. 
              You have <span className="font-bold text-white underline decoration-amber-400 decoration-2 underline-offset-2">{stats?.pending_review || 0} items</span> pending review.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <button 
              onClick={() => navigate('/admin/courses/new')}
              className="group flex items-center gap-2 bg-white text-indigo-600 px-5 py-3 rounded-xl font-bold shadow-lg shadow-black/10 hover:shadow-xl hover:scale-105 transition-all active:scale-95"
            >
              <BookOpenIcon className="w-5 h-5 group-hover:rotate-12 transition-transform" />
              <span>Create Course</span>
            </button>
          </div>
        </div>
      </div>

      {/* ─── Primary Stats Grid ───────────────────────────────────────── */}
      <div data-tour="admin-dashboard-stats" className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
        <StatsCard
          title="Total Teachers"
          value={stats?.total_teachers || 0}
          icon={<UserGroupIcon />}
          loading={isLoading}
          variant="indigo"
          description="Active educators"
        />
        <StatsCard
          title="Published Courses"
          value={stats?.published_courses || 0}
          icon={<AcademicCapIcon />}
          loading={isLoading}
          variant="emerald"
          description="Live for students"
        />
        <StatsCard
          title="Avg Completion"
          value={`${stats?.avg_completion_pct || 0}%`}
          icon={<ArrowTrendingUpIcon />}
          loading={isLoading}
          variant="amber"
          description="Across all courses"
        />
        <StatsCard
          title="Pending Review"
          value={stats?.pending_review || 0}
          icon={<ExclamationTriangleIcon />}
          loading={isLoading}
          variant="rose"
          description="Needs attention"
        />
      </div>

      {/* ─── Secondary "Sticker" Stats ────────────────────────────────── */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
        {[
          { label: 'Active', value: stats?.active_teachers, icon: '👩‍🏫', color: 'bg-blue-50 border-blue-100 text-blue-700' },
          { label: 'Inactive', value: stats?.inactive_teachers, icon: '😴', color: 'bg-slate-50 border-slate-100 text-slate-600' },
          { label: 'Completions', value: stats?.course_completions, icon: '🎓', color: 'bg-purple-50 border-purple-100 text-purple-700' },
          { label: 'In Progress', value: stats?.courses_in_progress, icon: '📖', color: 'bg-amber-50 border-amber-100 text-amber-700' },
          { label: 'Assignments', value: stats?.total_assignments, icon: '📝', color: 'bg-rose-50 border-rose-100 text-rose-700' },
          { label: 'Submissions', value: stats?.total_submissions, icon: '✅', color: 'bg-emerald-50 border-emerald-100 text-emerald-700' },
        ].map((item) => (
          <div key={item.label} className={`flex flex-col items-center justify-center p-4 rounded-2xl border-2 border-dashed ${item.color} transition-transform hover:scale-105 hover:rotate-1`}>
            <div className="text-2xl mb-1 filter drop-shadow-sm">{item.icon}</div>
            <div className="text-xl font-black">{isLoading ? '-' : (item.value ?? 0)}</div>
            <div className="text-[10px] uppercase tracking-wider font-bold opacity-70">{item.label}</div>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        {/* ─── Left Column (8/12) ─────────────────────────────────────── */}
        <div className="lg:col-span-8 space-y-8">
          
          {/* Recent Activity "Notebook" */}
          <div data-tour="admin-dashboard-activity" className="bg-white rounded-3xl border border-gray-200 shadow-sm overflow-hidden">
            <div className="bg-slate-50 px-6 py-4 border-b border-gray-200 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="p-2 bg-white rounded-lg shadow-sm">
                  <ClockIcon className="w-5 h-5 text-slate-600" />
                </div>
                <h2 className="font-bold text-slate-800">Class Log</h2>
              </div>
              <span className="text-xs font-medium px-2.5 py-1 bg-white border border-slate-200 rounded-full text-slate-500">
                Recent Activity
              </span>
            </div>
            
            <div className="p-6">
              {isLoading ? (
                <div className="space-y-4 animate-pulse">
                  {[1, 2, 3].map(i => <div key={i} className="h-16 bg-slate-50 rounded-xl" />)}
                </div>
              ) : recentActivity.length === 0 ? (
                <div className="text-center py-12 bg-slate-50 rounded-2xl border-2 border-dashed border-slate-200">
                  <div className="text-4xl mb-3">📭</div>
                  <p className="text-slate-500 font-medium">No activity recorded yet</p>
                </div>
              ) : (
                <div className="relative border-l-2 border-slate-100 ml-3 space-y-8 py-2">
                  {recentActivity.slice(0, 6).map((a, i) => (
                    <div key={i} className="relative pl-8 group">
                      {/* Timeline dot */}
                      <div className="absolute -left-[9px] top-1 h-4 w-4 rounded-full bg-white border-4 border-indigo-200 group-hover:border-indigo-500 transition-colors shadow-sm" />
                      
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 p-3 -mt-3 -ml-3 rounded-xl hover:bg-slate-50 transition-colors">
                        <div>
                          <p className="text-sm text-slate-900">
                            <span className="font-bold text-indigo-700">{a.teacher_name}</span>
                            <span className="text-slate-500"> completed </span>
                            <span className="font-semibold text-slate-700">{a.content_title || a.course_title}</span>
                          </p>
                          <div className="flex items-center gap-2 mt-1">
                            <span className="inline-flex items-center text-[10px] font-bold px-1.5 py-0.5 rounded text-indigo-600 bg-indigo-50 border border-indigo-100 uppercase tracking-wide">
                              Completion
                            </span>
                          </div>
                        </div>
                        <span className="text-xs font-medium text-slate-400 whitespace-nowrap bg-white px-2 py-1 rounded-lg border border-slate-100 shadow-sm">
                          {formatRelativeTime(a.completed_at)}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Quick Actions Grid */}
          <div data-tour="admin-dashboard-quick-actions" className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <button onClick={() => navigate('/admin/courses/new')} className="flex flex-col items-center justify-center p-6 bg-white border border-gray-200 rounded-2xl hover:border-indigo-300 hover:shadow-md hover:-translate-y-1 transition-all group">
              <div className="w-12 h-12 bg-indigo-50 rounded-2xl flex items-center justify-center mb-3 group-hover:bg-indigo-100 transition-colors">
                <BookOpenIcon className="w-6 h-6 text-indigo-600" />
              </div>
              <span className="font-bold text-slate-700 group-hover:text-indigo-700">New Course</span>
            </button>
            <button onClick={() => navigate('/admin/teachers/new')} className="flex flex-col items-center justify-center p-6 bg-white border border-gray-200 rounded-2xl hover:border-emerald-300 hover:shadow-md hover:-translate-y-1 transition-all group">
              <div className="w-12 h-12 bg-emerald-50 rounded-2xl flex items-center justify-center mb-3 group-hover:bg-emerald-100 transition-colors">
                <UserGroupIcon className="w-6 h-6 text-emerald-600" />
              </div>
              <span className="font-bold text-slate-700 group-hover:text-emerald-700">Add Teacher</span>
            </button>
            <button onClick={() => navigate('/admin/analytics')} className="flex flex-col items-center justify-center p-6 bg-white border border-gray-200 rounded-2xl hover:border-amber-300 hover:shadow-md hover:-translate-y-1 transition-all group">
              <div className="w-12 h-12 bg-amber-50 rounded-2xl flex items-center justify-center mb-3 group-hover:bg-amber-100 transition-colors">
                <ChartBarIcon className="w-6 h-6 text-amber-600" />
              </div>
              <span className="font-bold text-slate-700 group-hover:text-amber-700">Analytics</span>
            </button>
            <button onClick={() => navigate('/admin/reminders')} className="flex flex-col items-center justify-center p-6 bg-white border border-gray-200 rounded-2xl hover:border-rose-300 hover:shadow-md hover:-translate-y-1 transition-all group">
              <div className="w-12 h-12 bg-rose-50 rounded-2xl flex items-center justify-center mb-3 group-hover:bg-rose-100 transition-colors">
                <DocumentCheckIcon className="w-6 h-6 text-rose-600" />
              </div>
              <span className="font-bold text-slate-700 group-hover:text-rose-700">Reminders</span>
            </button>
          </div>

        </div>

        {/* ─── Right Column (4/12) ────────────────────────────────────── */}
        <div className="lg:col-span-4 space-y-8">
          
          {/* Plan "ID Card" */}
          {usage && limits && (
            <div className="relative overflow-hidden bg-slate-900 text-white rounded-3xl p-6 shadow-xl">
              {/* Card decoration */}
              <div className="absolute top-0 right-0 w-32 h-32 bg-white/5 rounded-full blur-2xl -mr-10 -mt-10" />
              
              <div className="relative z-10">
                <div className="flex justify-between items-start mb-6">
                  <div>
                    <p className="text-slate-400 text-xs font-bold uppercase tracking-wider mb-1">Current Plan</p>
                    <h3 className="text-2xl font-black bg-clip-text text-transparent bg-gradient-to-r from-white to-slate-400">{plan}</h3>
                  </div>
                  <div className="p-2 bg-white/10 rounded-lg backdrop-blur-sm border border-white/10">
                    <CalendarDaysIcon className="w-6 h-6 text-white" />
                  </div>
                </div>

                <div className="space-y-5">
                  <UsageBar label="Teachers" used={usage.teachers.used} limit={usage.teachers.limit} color="bg-indigo-500" />
                  <UsageBar label="Courses" used={usage.courses.used} limit={usage.courses.limit} color="bg-emerald-500" />
                  <UsageBar label="Storage" used={usage.storage_mb.used} limit={usage.storage_mb.limit} unit="MB" color="bg-amber-500" />
                </div>

                <button className="w-full mt-6 py-3 rounded-xl bg-white text-slate-900 font-bold text-sm hover:bg-indigo-50 transition-colors">
                  Upgrade Plan
                </button>
              </div>
            </div>
          )}

          {/* Top Performers "Honor Roll" */}
          <div className="bg-white rounded-3xl border border-gray-200 shadow-sm overflow-hidden">
            <div className="bg-amber-50/50 px-6 py-4 border-b border-amber-100 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <TrophyIcon className="w-5 h-5 text-amber-500" />
                <h2 className="font-bold text-amber-900">Honor Roll</h2>
              </div>
            </div>
            
            <div className="p-2">
              {isLoading ? (
                <div className="p-4 space-y-3 animate-pulse">
                  {[1, 2, 3].map(i => <div key={i} className="h-10 bg-slate-50 rounded-lg" />)}
                </div>
              ) : (stats?.top_teachers?.length || 0) === 0 ? (
                <div className="text-center py-8 px-4">
                  <p className="text-sm text-slate-400">No champions yet!</p>
                </div>
              ) : (
                <div className="space-y-1">
                  {stats?.top_teachers?.map((t, i) => (
                    <div key={i} className="flex items-center justify-between p-3 rounded-xl hover:bg-amber-50/30 transition-colors">
                      <div className="flex items-center gap-3">
                        <div className={`w-8 h-8 rounded-full flex items-center justify-center font-black text-sm shadow-sm ${
                          i === 0 ? 'bg-amber-400 text-white ring-2 ring-amber-200' : 
                          i === 1 ? 'bg-slate-300 text-white' : 
                          i === 2 ? 'bg-orange-300 text-white' : 'bg-slate-100 text-slate-500'
                        }`}>
                          {i + 1}
                        </div>
                        <div>
                          <p className="font-bold text-slate-800 text-sm">{t.name}</p>
                          <p className="text-[10px] text-slate-400 font-medium uppercase tracking-wide">
                            {t.completed_courses} Courses
                          </p>
                        </div>
                      </div>
                      {i === 0 && <span className="text-xl">👑</span>}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

        </div>
      </div>
    </div>
  );
};
