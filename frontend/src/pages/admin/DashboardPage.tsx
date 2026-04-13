// src/pages/admin/DashboardPage.tsx
//
// Warm cream/golden dashboard matching Behance reference design.
// Redesigned: deadlines calendar, compact plan badge, real top performers, tooltips.

import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  Users,
  BookOpen,
  TrendingUp,
  AlertCircle,
  Trophy,
  Plus,
  Sparkles,
  BarChart3,
  Zap,
  FileText,
  UserCheck,
  UserX,
  GraduationCap,
  ClipboardCheck,
} from 'lucide-react';
import { Card, Badge, Button, cn } from '../../design-system';
import { adminService } from '../../services/adminService';
import { useTenantStore } from '../../stores/tenantStore';
import { useAuthStore } from '../../stores/authStore';
import { usePageTitle } from '../../hooks/usePageTitle';
import { DeadlinesCalendar } from '../../components/dashboard/DeadlinesCalendar';
import { PlanBadge } from '../../components/dashboard/PlanBadge';

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** Calculate a performance score from submission rate + completion rate */
function calcPerformanceScore(
  completedCourses: number,
  totalCourses: number,
  submissions: number,
  totalAssignments: number,
): number {
  const completionRate = totalCourses > 0 ? completedCourses / totalCourses : 0;
  const submissionRate = totalAssignments > 0 ? submissions / totalAssignments : 0;
  // Weighted: 50% completion + 50% submission
  return Math.round((completionRate * 50 + submissionRate * 50));
}

export const DashboardPage: React.FC = () => {
  usePageTitle('Dashboard');
  const navigate = useNavigate();
  const { theme } = useTenantStore();
  const { user } = useAuthStore();

  const { data: stats, isLoading } = useQuery({
    queryKey: ['adminDashboardStats'],
    queryFn: adminService.getTenantStats,
    refetchInterval: 30000,
  });

  const firstName = user?.first_name || 'Admin';

  // Derive top performer scores from available stats
  const topPerformers = React.useMemo(() => {
    if (!stats?.top_teachers?.length) return [];

    const totalCourses = stats.total_courses || 1;
    const totalAssignments = stats.total_assignments || 1;

    return stats.top_teachers.map((t) => ({
      name: t.name,
      completedCourses: t.completed_courses,
      score: calcPerformanceScore(
        t.completed_courses,
        totalCourses,
        // Approximate per-teacher submission count from completed courses ratio
        Math.round((t.completed_courses / totalCourses) * (stats.total_submissions || 0)),
        totalAssignments,
      ),
    }));
  }, [stats]);

  return (
    <div className="space-y-6 pb-12">
      {/* ─── Hero Header + Plan Badge ───────────────────────────────── */}
      <div data-tour="admin-dashboard-hero" className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-3 flex-wrap">
            <h1 className="text-2xl font-bold text-content">
              Welcome back, {firstName}
            </h1>
            <PlanBadge />
          </div>
          <p className="mt-1 text-sm text-content-secondary">
            Here's what's happening at {theme.name} today
          </p>
        </div>
        <Button
          variant="primary"
          onClick={() => navigate('/admin/courses/new')}
          icon={<Plus className="h-4 w-4" />}
          title="Create a new course from scratch"
        >
          New Course
        </Button>
      </div>

      {/* ─── Big Number Stats ─────────────────────────────────────── */}
      <div data-tour="admin-dashboard-stats" className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card
          className="text-center py-8"
          title="Total number of teachers registered at your school"
        >
          <p className="text-4xl font-bold text-content tracking-tight">
            {isLoading ? '—' : stats?.total_teachers || 0}
          </p>
          <p className="mt-1 text-sm text-content-secondary">Total Teachers</p>
          <div className="mt-3 flex items-center justify-center gap-4 text-xs text-content-muted">
            <span className="flex items-center gap-1" title="Teachers who have logged in recently">
              <UserCheck className="h-3.5 w-3.5 text-success" />
              {stats?.active_teachers ?? 0} active
            </span>
            <span className="flex items-center gap-1" title="Teachers with no recent activity">
              <UserX className="h-3.5 w-3.5 text-content-muted" />
              {stats?.inactive_teachers ?? 0} inactive
            </span>
          </div>
        </Card>

        <Card
          className="text-center py-8"
          title="Number of courses currently published and available"
        >
          <p className="text-4xl font-bold text-content tracking-tight">
            {isLoading ? '—' : stats?.published_courses || 0}
          </p>
          <p className="mt-1 text-sm text-content-secondary">Published Courses</p>
          <div className="mt-3 flex items-center justify-center gap-4 text-xs text-content-muted">
            <span className="flex items-center gap-1" title="Courses with at least one teacher in progress">
              <Zap className="h-3.5 w-3.5 text-warning" />
              {stats?.courses_in_progress ?? 0} in progress
            </span>
            <span className="flex items-center gap-1" title="Total course completions across all teachers">
              <GraduationCap className="h-3.5 w-3.5 text-success" />
              {stats?.course_completions ?? 0} done
            </span>
          </div>
        </Card>

        <Card
          className="text-center py-8"
          title="Average course completion percentage across all teachers"
        >
          <p className="text-4xl font-bold text-accent tracking-tight">
            {isLoading ? '—' : `${stats?.avg_completion_pct || 0}%`}
          </p>
          <p className="mt-1 text-sm text-content-secondary">Avg Completion</p>
          <div className="mt-3">
            <div className="mx-auto max-w-[180px] h-2 bg-surface rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-accent to-accent-light rounded-full transition-all duration-700"
                style={{ width: `${stats?.avg_completion_pct || 0}%` }}
              />
            </div>
          </div>
        </Card>
      </div>

      {/* ─── Secondary Metrics Row ────────────────────────────────── */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          { label: 'Assignments', value: stats?.total_assignments, icon: FileText, color: 'text-accent', tooltip: 'Total assignments created across all courses' },
          { label: 'Submissions', value: stats?.total_submissions, icon: ClipboardCheck, color: 'text-success', tooltip: 'Total submissions received from teachers' },
          { label: 'Pending Review', value: stats?.pending_review, icon: AlertCircle, color: 'text-danger', tooltip: 'Submissions awaiting grading or review' },
          { label: 'Graded', value: stats?.graded_submissions, icon: TrendingUp, color: 'text-info', tooltip: 'Submissions that have been graded' },
        ].map((item) => (
          <Card key={item.label} padding="sm" hoverable title={item.tooltip}>
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-xl bg-surface flex items-center justify-center flex-shrink-0">
                <item.icon className={cn('h-5 w-5', item.color)} />
              </div>
              <div>
                <p className="text-xl font-bold text-content leading-tight">
                  {isLoading ? '—' : (item.value ?? 0)}
                </p>
                <p className="text-xs text-content-muted">{item.label}</p>
              </div>
            </div>
          </Card>
        ))}
      </div>

      {/* ─── Quick Actions ────────────────────────────────────────── */}
      <div data-tour="admin-dashboard-quick-actions" className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          { label: 'New Course', icon: BookOpen, bg: 'bg-accent-50', color: 'text-accent', href: '/admin/courses/new', tooltip: 'Create a new course from scratch' },
          { label: 'Add Teacher', icon: Users, bg: 'bg-success-bg', color: 'text-success', href: '/admin/teachers/new', tooltip: 'Add a new teacher to your school' },
          { label: 'Analytics', icon: BarChart3, bg: 'bg-info-bg', color: 'text-info', href: '/admin/analytics', tooltip: 'View detailed analytics and reports' },
          { label: 'AI Generator', icon: Sparkles, bg: 'bg-warning-bg', color: 'text-warning', href: '/admin/courses/new', tooltip: 'Use AI to generate assignments and course questions' },
        ].map((action) => (
          <button
            key={action.label}
            onClick={() => navigate(action.href)}
            className="group flex flex-col items-center justify-center rounded-2xl border border-surface-border bg-white p-5 transition-all hover:-translate-y-0.5 hover:shadow-card-hover"
            title={action.tooltip}
          >
            <div className={cn('h-11 w-11 rounded-xl flex items-center justify-center mb-2.5', action.bg)}>
              <action.icon className={cn('h-5 w-5', action.color)} />
            </div>
            <span className="text-sm font-semibold text-content">{action.label}</span>
          </button>
        ))}
      </div>

      {/* ─── Calendar + Top Performers ────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Deadlines Calendar (~60%) */}
        <div className="lg:col-span-7">
          <DeadlinesCalendar />
        </div>

        {/* Top Performers (~40%) */}
        <div className="lg:col-span-5">
          <Card padding="none" className="h-full">
            <div className="px-5 py-3.5 border-b border-surface-border">
              <div className="flex items-center gap-2">
                <Trophy className="h-4 w-4 text-accent" />
                <h3 className="text-sm font-semibold text-content">Top Performers</h3>
              </div>
              <p className="text-[10px] text-content-muted mt-0.5">
                Based on submission &amp; completion rates
              </p>
            </div>

            <div className="p-2">
              {isLoading ? (
                <div className="p-4 space-y-3">
                  {[1, 2, 3].map(i => <div key={i} className="h-10 skeleton rounded-lg" />)}
                </div>
              ) : topPerformers.length === 0 ? (
                <div className="text-center py-8">
                  <Trophy className="h-8 w-8 mx-auto mb-2 text-content-muted" />
                  <p className="text-sm text-content-secondary">No champions yet</p>
                </div>
              ) : (
                <div className="space-y-0.5">
                  {topPerformers.map((t, i) => (
                    <div
                      key={t.name}
                      className="flex items-center justify-between p-3 rounded-xl hover:bg-surface transition-colors"
                      title={`${t.completedCourses} courses completed, ${t.score}% performance score`}
                    >
                      <div className="flex items-center gap-3">
                        <div className={cn(
                          'w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold',
                          i === 0 && 'bg-gradient-to-br from-accent to-accent-dark text-white',
                          i === 1 && 'bg-surface-card-hover text-content-secondary',
                          i === 2 && 'bg-accent-50 text-accent-dark',
                          i > 2 && 'bg-surface text-content-muted',
                        )}>
                          {i + 1}
                        </div>
                        <div>
                          <p className="text-sm font-semibold text-content">{t.name}</p>
                          <p className="text-[10px] text-content-muted uppercase tracking-wide">
                            {t.completedCourses} courses &middot; {t.score}% score
                          </p>
                        </div>
                      </div>
                      {i === 0 && <Badge variant="warning" size="sm">Top</Badge>}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
};
