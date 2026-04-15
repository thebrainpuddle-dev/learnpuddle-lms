// src/pages/student/DashboardPage.tsx
//
// Student dashboard — stats, continue learning, upcoming deadlines.

import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  Play,
  ArrowRight,
  BookOpen,
  CheckCircle2,
  Clock,
  ClipboardList,
  TrendingUp,
  Trophy,
} from 'lucide-react';
import { format } from 'date-fns';
import { cn } from '../../design-system/theme/cn';
import { useAuthStore } from '../../stores/authStore';
import { useTenantStore } from '../../stores/tenantStore';
import { studentService, type StudentCourseListItem } from '../../services/studentService';
import { usePageTitle } from '../../hooks/usePageTitle';

// ─── Helpers ──────────────────────────────────────────────────────────────────

function getGreeting(): string {
  const h = new Date().getHours();
  if (h < 12) return 'Good morning';
  if (h < 17) return 'Good afternoon';
  return 'Good evening';
}

// ─── Stat Card ────────────────────────────────────────────────────────────────

function StatCard({
  icon: Icon,
  iconBg,
  iconColor,
  value,
  label,
  loading,
}: {
  icon: React.ElementType;
  iconBg: string;
  iconColor: string;
  value: string | number;
  label: string;
  loading?: boolean;
}) {
  return (
    <div className="bg-white rounded-2xl border border-gray-100 p-4 flex items-center gap-3.5 shadow-sm hover:shadow-md transition-shadow group">
      <div
        className={cn(
          'h-11 w-11 rounded-xl flex items-center justify-center flex-shrink-0 transition-transform group-hover:scale-105',
          iconBg,
        )}
      >
        <Icon className={cn('h-[18px] w-[18px]', iconColor)} />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-[20px] font-bold text-tp-text leading-tight tracking-tight">
          {loading ? (
            <span className="inline-block w-12 h-5 tp-skeleton rounded" />
          ) : (
            value
          )}
        </p>
        <p className="text-[11px] text-gray-400 mt-0.5 font-medium">{label}</p>
      </div>
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────

export const DashboardPage: React.FC = () => {
  usePageTitle('Dashboard');
  const navigate = useNavigate();
  const { user } = useAuthStore();
  const { theme } = useTenantStore();

  const { data: dashboard, isLoading } = useQuery({
    queryKey: ['studentDashboard'],
    queryFn: studentService.getStudentDashboard,
  });

  const { data: courses = [], isLoading: coursesLoading } = useQuery({
    queryKey: ['studentCourses'],
    queryFn: studentService.getStudentCourses,
  });

  const continueCourse = dashboard?.continue_learning;
  const deadlines = dashboard?.deadlines ?? [];

  // Show up to 4 courses on the dashboard, sorted by in-progress first, then by progress descending
  const dashboardCourses = [...courses]
    .sort((a, b) => {
      const pa = Number(a.progress_percentage || 0);
      const pb = Number(b.progress_percentage || 0);
      // In-progress courses first (0 < p < 100), then not started, then completed
      const rankA = pa > 0 && pa < 100 ? 0 : pa === 0 ? 1 : 2;
      const rankB = pb > 0 && pb < 100 ? 0 : pb === 0 ? 1 : 2;
      if (rankA !== rankB) return rankA - rankB;
      return pb - pa;
    })
    .slice(0, 4);

  return (
    <div className="space-y-6">
      {/* ─── Greeting ──────────────────────────────────────────── */}
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-[22px] font-bold text-tp-text tracking-tight">
            {getGreeting()}, {user?.first_name}
          </h1>
          <p className="mt-0.5 text-[13px] text-gray-400">
            {format(new Date(), 'EEEE, MMMM d')}
            {(user?.grade_name || user?.section_name) && (
              <span className="text-gray-400">
                {' · '}
                {[user.grade_name, user.section_name && `Section ${user.section_name}`].filter(Boolean).join(', ')}
              </span>
            )}
            {(dashboard?.stats.pending_assignments ?? 0) > 0 && (
              <span className="text-indigo-600 font-medium">
                {' '}
                · {dashboard!.stats.pending_assignments} assignment
                {dashboard!.stats.pending_assignments !== 1 ? 's' : ''} pending
              </span>
            )}
          </p>
          {theme?.welcomeMessage && (
            <p className="mt-1 text-[12px] text-indigo-500/70 font-medium italic">
              {theme.welcomeMessage}
            </p>
          )}
        </div>
      </div>

      {/* ─── Stat Cards ────────────────────────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard
          icon={TrendingUp}
          iconBg="bg-indigo-50"
          iconColor="text-indigo-600"
          value={`${dashboard?.stats.overall_progress ?? 0}%`}
          label="Overall Progress"
          loading={isLoading}
        />
        <StatCard
          icon={BookOpen}
          iconBg="bg-blue-50"
          iconColor="text-blue-500"
          value={dashboard?.stats.total_courses ?? 0}
          label="Total Courses"
          loading={isLoading}
        />
        <StatCard
          icon={CheckCircle2}
          iconBg="bg-emerald-50"
          iconColor="text-emerald-500"
          value={dashboard?.stats.completed_courses ?? 0}
          label="Completed"
          loading={isLoading}
        />
        <StatCard
          icon={ClipboardList}
          iconBg="bg-amber-50"
          iconColor="text-amber-500"
          value={dashboard?.stats.pending_assignments ?? 0}
          label="Pending Assignments"
          loading={isLoading}
        />
      </div>

      {/* ─── Main Grid ─────────────────────────────────────────── */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">
        {/* Left column */}
        <div className="xl:col-span-2 space-y-5">
          {/* Continue Learning */}
          {continueCourse && (
            <button
              onClick={() => navigate(`/student/courses/${continueCourse.course_id}`)}
              className="w-full text-left bg-gradient-to-br from-indigo-500 via-indigo-600 to-violet-600 rounded-2xl p-5 group transition-all hover:shadow-lg hover:shadow-indigo-200/50"
            >
              <div className="flex items-center gap-3 mb-3">
                <div className="h-10 w-10 rounded-xl bg-white/20 flex items-center justify-center backdrop-blur-sm">
                  <Play className="h-5 w-5 text-white" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-[10px] uppercase tracking-widest text-white/60 font-semibold">
                    Continue Learning
                  </p>
                  <p className="text-[13px] font-semibold text-white truncate mt-0.5">
                    {continueCourse.course_title}
                  </p>
                </div>
              </div>
              <p className="text-[12px] text-white/80 mb-2 truncate">
                Up next: {continueCourse.content_title}
              </p>
              <div className="h-1.5 bg-white/20 rounded-full overflow-hidden">
                <div
                  className="h-full bg-white rounded-full transition-all duration-500"
                  style={{ width: `${continueCourse.progress_percentage}%` }}
                />
              </div>
              <p className="text-[10px] text-white/60 mt-2 font-medium">
                {continueCourse.progress_percentage}% complete
              </p>
            </button>
          )}

          {/* My Courses */}
          <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
            <div className="flex items-center justify-between px-5 py-3.5 border-b border-gray-50">
              <h2 className="text-[13px] font-semibold text-tp-text">My Courses</h2>
              <button
                onClick={() => navigate('/student/courses')}
                className="text-[11px] text-indigo-600 hover:text-indigo-700 font-medium flex items-center gap-1 transition-colors"
              >
                View All <ArrowRight className="h-3 w-3" />
              </button>
            </div>

            {coursesLoading ? (
              <div className="p-4 space-y-2">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="h-14 tp-skeleton rounded-xl" />
                ))}
              </div>
            ) : dashboardCourses.length === 0 ? (
              <div className="py-10 text-center">
                <BookOpen className="h-8 w-8 mx-auto text-gray-200 mb-2" />
                <p className="text-[13px] text-gray-400">
                  No courses assigned yet
                </p>
                <button
                  onClick={() => navigate('/student/courses')}
                  className="mt-3 inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-[12px] font-medium bg-indigo-50 text-indigo-600 hover:bg-indigo-100 transition-colors"
                >
                  <BookOpen className="h-3.5 w-3.5" />
                  Browse Courses
                </button>
              </div>
            ) : (
              <div className="divide-y divide-gray-50">
                {dashboardCourses.map((course) => {
                  const progress = Math.min(100, Number(course.progress_percentage || 0));
                  const isCompleted = progress >= 100;
                  const isInProgress = progress > 0 && progress < 100;
                  return (
                    <button
                      key={course.id}
                      onClick={() => navigate(`/student/courses/${course.id}`)}
                      className="w-full text-left flex items-center gap-3.5 px-5 py-3.5 hover:bg-gray-50/60 transition-colors group"
                    >
                      {/* Thumbnail */}
                      <div className="h-10 w-10 rounded-lg bg-gray-50 border border-gray-100 flex items-center justify-center flex-shrink-0 overflow-hidden">
                        {course.thumbnail ? (
                          <img
                            src={course.thumbnail}
                            alt=""
                            className="h-10 w-10 object-cover"
                          />
                        ) : (
                          <BookOpen className="h-4 w-4 text-gray-300" />
                        )}
                      </div>

                      {/* Info */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <p className="text-[13px] font-medium text-tp-text truncate leading-tight">
                            {course.title}
                          </p>
                          {isCompleted && (
                            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 flex-shrink-0" />
                          )}
                        </div>

                        {/* Progress bar */}
                        <div className="flex items-center gap-2.5">
                          <div className="flex-1 h-[5px] bg-gray-100 rounded-full overflow-hidden">
                            <div
                              className={cn(
                                'h-full rounded-full transition-all duration-700',
                                isCompleted
                                  ? 'bg-emerald-500'
                                  : 'bg-gradient-to-r from-indigo-500 to-violet-400',
                              )}
                              style={{ width: `${progress}%` }}
                            />
                          </div>
                          <span className="text-[11px] font-semibold tabular-nums text-tp-text-secondary w-8 text-right">
                            {Math.round(progress)}%
                          </span>
                        </div>

                        {/* Meta */}
                        <div className="flex items-center gap-3 mt-1 text-[10px] text-gray-400">
                          <span>
                            {course.completed_content_count}/{course.total_content_count} lessons
                          </span>
                          {course.deadline && (
                            <span className="flex items-center gap-0.5 text-amber-500">
                              <Clock className="h-2.5 w-2.5" />
                              {new Date(course.deadline).toLocaleDateString('en-US', {
                                month: 'short',
                                day: 'numeric',
                              })}
                            </span>
                          )}
                          {isInProgress && (
                            <span className="flex items-center gap-0.5 text-indigo-500 font-medium">
                              <Play className="h-2.5 w-2.5" />
                              In Progress
                            </span>
                          )}
                        </div>
                      </div>

                      {/* Arrow */}
                      <ArrowRight className="h-3.5 w-3.5 text-gray-300 group-hover:text-indigo-500 transition-colors flex-shrink-0" />
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {/* Right column */}
        <div className="space-y-5">
          {/* Upcoming Deadlines */}
          <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
            <div className="flex items-center justify-between px-5 py-3.5 border-b border-gray-50">
              <div className="flex items-center gap-2">
                <Clock className="h-4 w-4 text-indigo-600" />
                <h3 className="text-[13px] font-semibold text-tp-text">
                  Upcoming Deadlines
                </h3>
              </div>
              <button
                onClick={() => navigate('/student/assignments')}
                className="text-[11px] text-indigo-600 hover:text-indigo-700 font-medium flex items-center gap-1 transition-colors"
              >
                All <ArrowRight className="h-3 w-3" />
              </button>
            </div>

            {isLoading ? (
              <div className="p-4 space-y-2">
                {[1, 2].map((i) => (
                  <div key={i} className="h-12 tp-skeleton rounded-xl" />
                ))}
              </div>
            ) : deadlines.length === 0 ? (
              <div className="py-10 text-center">
                <CheckCircle2 className="h-7 w-7 mx-auto text-emerald-200 mb-2" />
                <p className="text-[13px] text-gray-400 font-medium">
                  No upcoming deadlines
                </p>
              </div>
            ) : (
              <div className="divide-y divide-gray-50">
                {deadlines.slice(0, 5).map((d) => (
                  <div
                    key={d.id}
                    className="px-5 py-3 hover:bg-gray-50/50 transition-colors"
                  >
                    <p className="text-[13px] font-medium text-tp-text truncate">
                      {d.title}
                    </p>
                    <div className="flex items-center gap-2 mt-1">
                      <span
                        className={cn(
                          'inline-flex px-2 py-[2px] rounded-md text-[10px] font-semibold uppercase tracking-wide leading-none',
                          d.type === 'assignment'
                            ? 'bg-amber-50 text-amber-600'
                            : 'bg-indigo-50 text-indigo-600',
                        )}
                      >
                        {d.type}
                      </span>
                      <span className="text-[11px] text-gray-400 flex items-center gap-1 font-medium">
                        <Clock className="h-3 w-3" />
                        {d.days_left === 0
                          ? 'Due today'
                          : d.days_left === 1
                            ? 'Due tomorrow'
                            : `${d.days_left} days left`}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Achievements Teaser */}
          <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
            <div className="flex items-center justify-between px-5 py-3.5 border-b border-gray-50">
              <div className="flex items-center gap-2">
                <Trophy className="h-4 w-4 text-amber-500" />
                <h3 className="text-[13px] font-semibold text-tp-text">
                  Achievements
                </h3>
              </div>
              <button
                onClick={() => navigate('/student/achievements')}
                className="text-[11px] text-indigo-600 hover:text-indigo-700 font-medium flex items-center gap-1 transition-colors"
              >
                View All <ArrowRight className="h-3 w-3" />
              </button>
            </div>

            <div className="py-10 text-center">
              <Trophy className="h-7 w-7 mx-auto text-amber-200 mb-2" />
              <p className="text-[13px] text-gray-400 font-medium">
                Complete courses to earn badges
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
