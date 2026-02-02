// src/pages/admin/DashboardPage.tsx

import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { StatsCard } from '../../components/admin/StatsCard';
import { adminService, RecentActivityItem } from '../../services/adminService';
import {
  AcademicCapIcon,
  UserGroupIcon,
  ChartBarIcon,
  ClockIcon,
  CheckCircleIcon,
} from '@heroicons/react/24/outline';
import { Button } from '../../components/common/Button';
import { useNavigate } from 'react-router-dom';

// Helper to format relative time
function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSeconds = Math.floor(diffMs / 1000);
  const diffMinutes = Math.floor(diffSeconds / 60);
  const diffHours = Math.floor(diffMinutes / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffSeconds < 60) return 'just now';
  if (diffMinutes < 60) return `${diffMinutes} minute${diffMinutes > 1 ? 's' : ''} ago`;
  if (diffHours < 24) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`;
  if (diffDays === 1) return 'yesterday';
  if (diffDays < 7) return `${diffDays} days ago`;
  return date.toLocaleDateString();
}

export const DashboardPage: React.FC = () => {
  const navigate = useNavigate();
  
  // Fetch dashboard stats
  const { data: stats, isLoading } = useQuery({
    queryKey: ['dashboardStats'],
    queryFn: adminService.getTenantStats,
  });

  const recentActivity: RecentActivityItem[] = stats?.recent_activity || [];
  
  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
          <p className="mt-1 text-sm text-gray-500">
            Welcome back! Here's what's happening with your school.
          </p>
        </div>
        
        <Button
          variant="primary"
          onClick={() => navigate('/admin/courses/new')}
        >
          Create Course
        </Button>
      </div>
      
      {/* Stats Grid */}
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
        <StatsCard
          title="Total Courses"
          value={stats?.total_courses || 0}
          icon={<AcademicCapIcon className="h-6 w-6" />}
          loading={isLoading}
        />
        
        <StatsCard
          title="Total Teachers"
          value={stats?.total_teachers || 0}
          icon={<UserGroupIcon className="h-6 w-6" />}
          loading={isLoading}
        />
        
        <StatsCard
          title="Published Courses"
          value={stats?.published_courses || 0}
          icon={<ChartBarIcon className="h-6 w-6" />}
          loading={isLoading}
        />
        
        <StatsCard
          title="Total Admins"
          value={stats?.total_admins || 0}
          icon={<ClockIcon className="h-6 w-6" />}
          loading={isLoading}
        />
      </div>
      
      {/* Content Grid */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Recent Activity */}
        <div className="card">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">
            Recent Activity
          </h2>
          {isLoading ? (
            <div className="space-y-4">
              {[1, 2, 3].map((i) => (
                <div key={i} className="flex items-start animate-pulse">
                  <div className="h-8 w-8 rounded-full bg-gray-200" />
                  <div className="ml-3 flex-1 space-y-2">
                    <div className="h-4 bg-gray-200 rounded w-3/4" />
                    <div className="h-3 bg-gray-200 rounded w-1/4" />
                  </div>
                </div>
              ))}
            </div>
          ) : recentActivity.length === 0 ? (
            <div className="text-center py-8">
              <CheckCircleIcon className="h-12 w-12 mx-auto text-gray-300 mb-3" />
              <p className="text-gray-500 text-sm">No recent activity yet</p>
              <p className="text-gray-400 text-xs mt-1">
                Activity will appear here when teachers complete courses
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              {recentActivity.map((activity, i) => (
                <div key={i} className="flex items-start">
                  <div className="flex-shrink-0">
                    <div className="h-8 w-8 rounded-full bg-green-100 flex items-center justify-center">
                      <CheckCircleIcon className="h-4 w-4 text-green-600" />
                    </div>
                  </div>
                  <div className="ml-3 flex-1">
                    <p className="text-sm text-gray-900">
                      <span className="font-medium">{activity.teacher_name}</span> completed{' '}
                      <span className="font-medium">
                        {activity.content_title || activity.course_title}
                      </span>
                    </p>
                    <p className="text-xs text-gray-500 mt-1">
                      {formatRelativeTime(activity.completed_at)}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
        
        {/* Quick Actions */}
        <div className="card">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">
            Quick Actions
          </h2>
          <div className="space-y-3">
            <Button
              variant="outline"
              fullWidth
              onClick={() => navigate('/admin/courses/new')}
            >
              Create New Course
            </Button>
            <Button
              variant="outline"
              fullWidth
              onClick={() => navigate('/admin/teachers/new')}
            >
              Add Teacher
            </Button>
            <Button
              variant="outline"
              fullWidth
              onClick={() => navigate('/admin/analytics')}
            >
              View Reports
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
};
