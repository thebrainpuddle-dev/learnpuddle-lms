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
  CheckCircleIcon,
  DocumentCheckIcon,
  TrophyIcon,
  ExclamationTriangleIcon,
  ArrowTrendingUpIcon,
  BookOpenIcon,
} from '@heroicons/react/24/outline';
import { Button } from '../../components/common/Button';
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
  usePageTitle('Dashboard');
  const navigate = useNavigate();
  const { plan, usage, limits } = useTenantStore();

  const { data: stats, isLoading } = useQuery({
    queryKey: ['adminDashboardStats'],
    queryFn: adminService.getTenantStats,
  });

  const recentActivity: RecentActivityItem[] = stats?.recent_activity || [];

  const UsageBar: React.FC<{ label: string; used: number; limit: number; unit?: string }> = ({ label, used, limit, unit }) => {
    const pct = limit > 0 ? Math.min(100, Math.round((used / limit) * 100)) : 0;
    const color = pct > 80 ? 'bg-red-500' : pct > 60 ? 'bg-amber-500' : 'bg-emerald-500';
    return (
      <div>
        <div className="flex justify-between text-sm mb-1">
          <span className="text-gray-600">{label}</span>
          <span className="font-medium text-gray-900">{used}{unit ? ` ${unit}` : ''} / {limit}{unit ? ` ${unit}` : ''}</span>
        </div>
        <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
          <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
          <p className="mt-1 text-sm text-gray-500">
            Welcome back! Here's what's happening with your school.
          </p>
        </div>
        <Button variant="primary" onClick={() => navigate('/admin/courses/new')}>
          Create Course
        </Button>
      </div>

      {/* Primary Stats */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatsCard
          title="Total Teachers"
          value={stats?.total_teachers || 0}
          icon={<UserGroupIcon className="h-6 w-6" />}
          loading={isLoading}
        />
        <StatsCard
          title="Published Courses"
          value={stats?.published_courses || 0}
          icon={<AcademicCapIcon className="h-6 w-6" />}
          loading={isLoading}
        />
        <StatsCard
          title="Avg Completion"
          value={`${stats?.avg_completion_pct || 0}%`}
          icon={<ArrowTrendingUpIcon className="h-6 w-6" />}
          loading={isLoading}
        />
        <StatsCard
          title="Pending Review"
          value={stats?.pending_review || 0}
          icon={<ExclamationTriangleIcon className="h-6 w-6" />}
          loading={isLoading}
        />
      </div>

      {/* Secondary Stats Row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-4">
        {[
          { label: 'Active Teachers', value: stats?.active_teachers, icon: '👩‍🏫' },
          { label: 'Inactive', value: stats?.inactive_teachers, icon: '😴' },
          { label: 'Course Completions', value: stats?.course_completions, icon: '🎓' },
          { label: 'In Progress', value: stats?.courses_in_progress, icon: '📖' },
          { label: 'Assignments', value: stats?.total_assignments, icon: '📝' },
          { label: 'Submissions', value: stats?.total_submissions, icon: '✅' },
        ].map((item) => (
          <div key={item.label} className="bg-white rounded-xl border border-gray-200 p-4 text-center">
            <div className="text-2xl mb-1">{item.icon}</div>
            <div className="text-xl font-bold text-gray-900">{isLoading ? '-' : (item.value ?? 0)}</div>
            <div className="text-xs text-gray-500 mt-0.5">{item.label}</div>
          </div>
        ))}
      </div>

      {/* Plan & Usage */}
      {usage && limits && (
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-gray-900">Your Plan</h2>
            <span className="px-3 py-1 text-xs font-semibold rounded-full bg-indigo-100 text-indigo-700">{plan}</span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <UsageBar label="Teachers" used={usage.teachers.used} limit={usage.teachers.limit} />
            <UsageBar label="Courses" used={usage.courses.used} limit={usage.courses.limit} />
            <UsageBar label="Storage" used={usage.storage_mb.used} limit={usage.storage_mb.limit} unit="MB" />
          </div>
        </div>
      )}

      {/* Bottom Grid */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Top Teachers */}
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <div className="flex items-center gap-2 mb-4">
            <TrophyIcon className="h-5 w-5 text-amber-500" />
            <h2 className="text-lg font-semibold text-gray-900">Top Performers</h2>
          </div>
          {isLoading ? (
            <div className="animate-pulse space-y-3">
              {[1, 2, 3].map(i => <div key={i} className="h-8 bg-gray-100 rounded" />)}
            </div>
          ) : (stats?.top_teachers?.length || 0) === 0 ? (
            <p className="text-sm text-gray-400 text-center py-6">No completions yet</p>
          ) : (
            <div className="space-y-3">
              {stats?.top_teachers?.map((t, i) => (
                <div key={i} className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <span className={`flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
                      i === 0 ? 'bg-amber-100 text-amber-700' : i === 1 ? 'bg-gray-100 text-gray-600' : 'bg-orange-50 text-orange-600'
                    }`}>{i + 1}</span>
                    <span className="text-sm font-medium text-gray-900">{t.name}</span>
                  </div>
                  <span className="text-sm text-gray-500">{t.completed_courses} courses</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Recent Activity */}
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <div className="flex items-center gap-2 mb-4">
            <ClockIcon className="h-5 w-5 text-gray-400" />
            <h2 className="text-lg font-semibold text-gray-900">Recent Activity</h2>
          </div>
          {isLoading ? (
            <div className="animate-pulse space-y-3">
              {[1, 2, 3].map(i => <div key={i} className="h-10 bg-gray-100 rounded" />)}
            </div>
          ) : recentActivity.length === 0 ? (
            <div className="text-center py-6">
              <CheckCircleIcon className="h-10 w-10 mx-auto text-gray-300 mb-2" />
              <p className="text-sm text-gray-400">No activity yet</p>
            </div>
          ) : (
            <div className="space-y-3">
              {recentActivity.slice(0, 6).map((a, i) => (
                <div key={i} className="flex items-start gap-2">
                  <div className="flex-shrink-0 mt-0.5 h-6 w-6 rounded-full bg-green-100 flex items-center justify-center">
                    <CheckCircleIcon className="h-3.5 w-3.5 text-green-600" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm text-gray-900 truncate">
                      <span className="font-medium">{a.teacher_name}</span> completed{' '}
                      <span className="font-medium">{a.content_title || a.course_title}</span>
                    </p>
                    <p className="text-xs text-gray-400">{formatRelativeTime(a.completed_at)}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Quick Actions */}
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Quick Actions</h2>
          <div className="space-y-3">
            <Button variant="outline" fullWidth onClick={() => navigate('/admin/courses/new')}>
              <BookOpenIcon className="h-4 w-4 mr-2" /> Create New Course
            </Button>
            <Button variant="outline" fullWidth onClick={() => navigate('/admin/teachers/new')}>
              <UserGroupIcon className="h-4 w-4 mr-2" /> Add Teacher
            </Button>
            <Button variant="outline" fullWidth onClick={() => navigate('/admin/analytics')}>
              <ChartBarIcon className="h-4 w-4 mr-2" /> View Analytics
            </Button>
            <Button variant="outline" fullWidth onClick={() => navigate('/admin/reminders')}>
              <DocumentCheckIcon className="h-4 w-4 mr-2" /> Send Reminders
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
};
