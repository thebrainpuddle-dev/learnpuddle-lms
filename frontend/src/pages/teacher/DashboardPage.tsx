// src/pages/teacher/DashboardPage.tsx

import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuthStore } from '../../stores/authStore';
import { Button } from '../../components/common/Button';
import { teacherService } from '../../services/teacherService';
import { notificationService, Notification } from '../../services/notificationService';
import { TeacherCalendarFiveDay } from '../../components/teacher/dashboard/TeacherCalendarFiveDay';
import {
  AcademicCapIcon,
  CheckCircleIcon,
  ClockIcon,
  ArrowRightIcon,
  BellAlertIcon,
  CheckIcon,
  MegaphoneIcon,
  SparklesIcon,
  PlayCircleIcon,
} from '@heroicons/react/24/outline';
import { PlayIcon } from '@heroicons/react/24/solid';
import { formatDistanceToNow } from 'date-fns';
import { usePageTitle } from '../../hooks/usePageTitle';

const NotifIcon: React.FC<{ type: Notification['notification_type'] }> = ({ type }) => {
  switch (type) {
    case 'COURSE_ASSIGNED':
      return <AcademicCapIcon className="h-5 w-5 text-blue-500" />;
    case 'ASSIGNMENT_DUE':
      return <ClockIcon className="h-5 w-5 text-amber-500" />;
    case 'REMINDER':
      return <BellAlertIcon className="h-5 w-5 text-red-500" />;
    case 'ANNOUNCEMENT':
      return <MegaphoneIcon className="h-5 w-5 text-purple-500" />;
    default:
      return <BellAlertIcon className="h-5 w-5 text-gray-500" />;
  }
};

export const DashboardPage: React.FC = () => {
  usePageTitle('Dashboard');
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user } = useAuthStore();

  const { data: dashboard } = useQuery({
    queryKey: ['teacherDashboard'],
    queryFn: teacherService.getDashboard,
  });

  const { data: calendar, isLoading: calendarLoading } = useQuery({
    queryKey: ['teacherCalendar', 5],
    queryFn: () => teacherService.getCalendar(5),
  });

  const { data: gamification, isLoading: gamificationLoading } = useQuery({
    queryKey: ['teacherGamification'],
    queryFn: teacherService.getGamificationSummary,
  });

  const { data: todoItems = [] } = useQuery({
    queryKey: ['dashboardTodos'],
    queryFn: () => notificationService.getNotifications({ unread_only: true, actionable_only: true, limit: 10 }),
  });

  const invalidateNotifQueries = () => {
    queryClient.invalidateQueries({ queryKey: ['dashboardTodos'] });
    queryClient.invalidateQueries({ queryKey: ['notificationUnreadCount'] });
    queryClient.invalidateQueries({ queryKey: ['notifications'] });
  };

  const markReadMutation = useMutation({
    mutationFn: notificationService.markAsRead,
    onSuccess: invalidateNotifQueries,
  });

  const continueCourse = dashboard?.continue_learning;
  const currentLevel = gamification?.badge_current;
  const currentLevelProgress = gamification?.badges.find(
    (badge) => badge.level === currentLevel?.level,
  )?.progress_percentage ?? 0;

  const handleNotifClick = (notification: Notification) => {
    if (!notification.is_read) markReadMutation.mutate(notification.id);
    if (notification.course) {
      navigate(`/teacher/courses/${notification.course}`);
      return;
    }
    if (notification.assignment) {
      navigate('/teacher/assignments');
      return;
    }
    navigate('/teacher/reminders');
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Welcome back, {user?.first_name}!</h1>
          <p className="mt-1 text-gray-500">Your learning space is ready. Pick one task and move forward.</p>
        </div>

        {continueCourse && (
          <Button
            variant="primary"
            className="bg-emerald-600 hover:bg-emerald-700"
            onClick={() => navigate(`/teacher/courses/${continueCourse.course_id}`)}
          >
            <PlayIcon className="h-4 w-4 mr-2" />
            Continue Learning
          </Button>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Current State</p>
              <h2 className="mt-1 text-xl font-bold text-slate-900">
                {gamificationLoading ? 'Syncing progress...' : `${gamification?.points_total || 0} points synced`}
              </h2>
              <p className="text-sm text-slate-500">Your fish journey updates from this score automatically.</p>
            </div>
            <div className="rounded-xl bg-indigo-50 p-2 text-indigo-600">
              <SparklesIcon className="h-5 w-5" />
            </div>
          </div>

          <div className="mt-4">
            <div className="mb-1 flex items-center justify-between text-xs font-medium text-slate-500">
              <span>Milestone progress</span>
              <span>{Math.round(currentLevelProgress)}%</span>
            </div>
            <div className="h-2 rounded-full bg-slate-100 overflow-hidden">
              <div
                className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 transition-all"
                style={{ width: `${Math.min(100, Math.max(0, currentLevelProgress))}%` }}
              />
            </div>
            <p className="mt-2 text-xs text-slate-500">Keep completing items to grow your journey state.</p>
          </div>
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Momentum</p>
          <h2 className="mt-1 text-xl font-bold text-slate-900">
            {gamificationLoading ? 'Loading streak...' : `${gamification?.streak.current_days || 0}-day streak`}
          </h2>
          <p className="text-sm text-slate-500">Small daily steps beat big rushed days.</p>

          <div className="mt-4 grid grid-cols-3 gap-3 text-center">
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
              <p className="text-lg font-bold text-slate-900">{dashboard?.stats.pending_assignments || 0}</p>
              <p className="text-xs text-slate-500">Pending work</p>
            </div>
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
              <p className="text-lg font-bold text-slate-900">{todoItems.length}</p>
              <p className="text-xs text-slate-500">Actionable tasks</p>
            </div>
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
              <p className="text-lg font-bold text-slate-900">{dashboard?.stats.completed_courses || 0}</p>
              <p className="text-xs text-slate-500">Courses done</p>
            </div>
          </div>
        </section>
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <div className="xl:col-span-2">
          {calendarLoading ? (
            <div className="h-[22rem] rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
              <div className="h-full animate-pulse rounded-xl bg-slate-100" />
            </div>
          ) : (
            <TeacherCalendarFiveDay
              days={calendar?.days || []}
              events={calendar?.events || []}
              onOpenEvent={(event) => navigate(event.route)}
            />
          )}
        </div>

        <div>
          <section className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
            <div className="flex items-center justify-between px-5 py-3 border-b border-gray-100 bg-emerald-50/60">
              <div className="flex items-center gap-2">
                <CheckCircleIcon className="h-5 w-5 text-emerald-600" />
                <h2 className="text-sm font-semibold text-gray-900">
                  To Do
                  {todoItems.length > 0 && (
                    <span className="ml-2 inline-flex items-center justify-center h-5 min-w-[20px] px-1.5 rounded-full bg-emerald-100 text-emerald-700 text-xs font-bold">
                      {todoItems.length}
                    </span>
                  )}
                </h2>
              </div>
              {todoItems.length > 0 && (
                <button
                  type="button"
                  onClick={() => navigate('/teacher/reminders')}
                  className="text-xs text-emerald-600 hover:text-emerald-700 flex items-center gap-1"
                >
                  View all
                  <ArrowRightIcon className="h-3 w-3" />
                </button>
              )}
            </div>

            {todoItems.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-8 text-gray-400">
                <CheckCircleIcon className="h-10 w-10 mb-2 text-emerald-300" />
                <p className="text-sm font-medium text-gray-500">All caught up</p>
                <p className="text-xs text-gray-400 mt-0.5">Nothing urgent right now.</p>
              </div>
            ) : (
              <div className="divide-y divide-gray-50">
                {todoItems.map((item) => (
                  <div
                    key={item.id}
                    className="flex items-start gap-3 px-5 py-3 hover:bg-gray-50 transition-colors"
                  >
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        markReadMutation.mutate(item.id);
                      }}
                      className="flex-shrink-0 mt-0.5 h-5 w-5 rounded-md border-2 border-gray-300 hover:border-emerald-500 hover:bg-emerald-50 flex items-center justify-center transition-colors"
                      title="Mark as done"
                    >
                      <CheckIcon className="h-3 w-3 text-transparent hover:text-emerald-500" />
                    </button>
                    <button
                      type="button"
                      onClick={() => handleNotifClick(item)}
                      className="flex-1 min-w-0 text-left"
                    >
                      <div className="flex items-center gap-2">
                        <NotifIcon type={item.notification_type} />
                        <p className="text-sm font-medium text-gray-900 truncate">{item.title}</p>
                      </div>
                      <p className="text-xs text-gray-500 mt-0.5 line-clamp-1 ml-7">{item.message}</p>
                      <p className="text-xs text-gray-400 mt-1 ml-7">
                        {formatDistanceToNow(new Date(item.created_at), { addSuffix: true })}
                      </p>
                    </button>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      </div>

      <section className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900">Continue Learning</h2>
          <button
            onClick={() => navigate('/teacher/courses')}
            className="text-sm text-emerald-600 hover:text-emerald-700 flex items-center"
          >
            Open courses
            <ArrowRightIcon className="h-4 w-4 ml-1" />
          </button>
        </div>

        {continueCourse ? (
          <button
            type="button"
            className="w-full text-left relative bg-gradient-to-r from-slate-800 to-slate-900 rounded-xl p-6 group overflow-hidden"
            onClick={() => navigate(`/teacher/courses/${continueCourse.course_id}`)}
          >
            <div className="absolute inset-0 opacity-10">
              <div className="absolute inset-0 bg-[radial-gradient(circle_at_30%_50%,white_1px,transparent_1px)] bg-[size:20px_20px]" />
            </div>

            <div className="relative flex items-center">
              <div className="flex-shrink-0 mr-6">
                <div className="h-20 w-20 bg-emerald-500/20 rounded-xl flex items-center justify-center group-hover:bg-emerald-500/30 transition-colors">
                  <PlayCircleIcon className="h-10 w-10 text-emerald-400" />
                </div>
              </div>

              <div className="flex-1 min-w-0">
                <h3 className="text-xl font-semibold text-white mb-1">{continueCourse.course_title}</h3>
                <p className="text-slate-400 text-sm mb-3 line-clamp-1">{continueCourse.content_title}</p>

                <div className="flex items-center space-x-4">
                  <div className="flex-1 max-w-xs">
                    <div className="flex justify-between text-xs text-slate-400 mb-1">
                      <span>Lesson progress</span>
                      <span>{continueCourse.progress_percentage}%</span>
                    </div>
                    <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-emerald-500 rounded-full transition-all"
                        style={{ width: `${continueCourse.progress_percentage}%` }}
                      />
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </button>
        ) : (
          <div className="text-center py-8 text-gray-500">
            <AcademicCapIcon className="h-12 w-12 mx-auto mb-3 text-gray-400" />
            <p>No active course session yet</p>
            <button
              onClick={() => navigate('/teacher/courses')}
              className="mt-2 text-emerald-600 hover:text-emerald-700"
            >
              Browse courses
            </button>
          </div>
        )}
      </section>
    </div>
  );
};
