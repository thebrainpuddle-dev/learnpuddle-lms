// src/pages/teacher/DashboardPage.tsx

import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuthStore } from '../../stores/authStore';
import { ProgressCard, CourseCard } from '../../components/teacher';
import { Button } from '../../components/common/Button';
import { teacherService } from '../../services/teacherService';
import { notificationService, Notification } from '../../services/notificationService';
import { BadgeShowcase } from '../../components/teacher/dashboard/BadgeShowcase';
import { CompletionRing } from '../../components/teacher/dashboard/CompletionRing';
import { ConfettiBurst } from '../../components/teacher/dashboard/ConfettiBurst';
import { DailyQuestCard } from '../../components/teacher/dashboard/DailyQuestCard';
import { DeadlinePressureBar } from '../../components/teacher/dashboard/DeadlinePressureBar';
import { TeacherCalendarFiveDay } from '../../components/teacher/dashboard/TeacherCalendarFiveDay';
import {
  AcademicCapIcon,
  BookOpenIcon,
  CheckCircleIcon,
  ClockIcon,
  ArrowRightIcon,
  CalendarDaysIcon,
  BellAlertIcon,
  CheckIcon,
  MegaphoneIcon,
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
  const [showConfetti, setShowConfetti] = React.useState(false);
  
  const { data: dashboard, isLoading: statsLoading } = useQuery({
    queryKey: ['teacherDashboard'],
    queryFn: teacherService.getDashboard,
  });
  
  const { data: courses, isLoading: coursesLoading } = useQuery({
    queryKey: ['teacherCourses'],
    queryFn: teacherService.listCourses,
  });

  const { data: calendar, isLoading: calendarLoading } = useQuery({
    queryKey: ['teacherCalendar', 5],
    queryFn: () => teacherService.getCalendar(5),
  });

  const { data: gamification, isLoading: gamificationLoading } = useQuery({
    queryKey: ['teacherGamification'],
    queryFn: teacherService.getGamificationSummary,
  });

  // Unread notifications for the dashboard banner
  const { data: unreadNotifications = [] } = useQuery({
    queryKey: ['dashboardNotifications'],
    queryFn: () => notificationService.getNotifications({ unread_only: true, limit: 5 }),
  });

  const markReadMutation = useMutation({
    mutationFn: notificationService.markAsRead,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dashboardNotifications'] });
      queryClient.invalidateQueries({ queryKey: ['notificationUnreadCount'] });
      queryClient.invalidateQueries({ queryKey: ['notifications'] });
    },
  });

  const markAllReadMutation = useMutation({
    mutationFn: notificationService.markAllAsRead,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dashboardNotifications'] });
      queryClient.invalidateQueries({ queryKey: ['notificationUnreadCount'] });
      queryClient.invalidateQueries({ queryKey: ['notifications'] });
    },
  });

  const claimQuestMutation = useMutation({
    mutationFn: (questKey: string) => teacherService.claimQuestReward(questKey),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['teacherGamification'] });
      queryClient.invalidateQueries({ queryKey: ['teacherDashboard'] });
      setShowConfetti(true);
      window.setTimeout(() => setShowConfetti(false), 1500);
    },
  });

  const handleNotifClick = (n: Notification) => {
    if (!n.is_read) markReadMutation.mutate(n.id);
    if (n.course) navigate(`/teacher/courses/${n.course}`);
    else if (n.assignment) navigate('/teacher/assignments');
    else if (n.notification_type === 'REMINDER') navigate('/teacher/reminders');
  };
  
  const deadlines = dashboard?.deadlines ?? [];
  const continueCourse = dashboard?.continue_learning;
  const overdueDeadlines = deadlines.filter((item) => item.days_left < 0).length;
  const upcomingDeadlines = deadlines.filter((item) => item.days_left >= 0 && item.days_left <= 7).length;
  const streakProgress = gamification
    ? Math.round((gamification.streak.current_days / Math.max(1, gamification.streak.target_days)) * 100)
    : 0;

  const toCourseCard = (c: any) => {
    const total = Number(c.total_content_count || 0);
    const completed = Number(c.completed_content_count || 0);
    const progress = Number(c.progress_percentage || 0);
    const status =
      progress >= 100 ? 'COMPLETED' : progress > 0 ? 'IN_PROGRESS' : 'NOT_STARTED';
    return {
      id: c.id,
      title: c.title,
      description: c.description,
      thumbnail: c.thumbnail_url || c.thumbnail || undefined,
      progress,
      totalModules: total,
      completedModules: completed,
      estimatedHours: Number(c.estimated_hours || 0),
      deadline: c.deadline || undefined,
      status,
    } as const;
  };
  
  return (
    <div className="space-y-8">
      <ConfettiBurst active={showConfetti} />
      {/* Welcome Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">
            Welcome back, {user?.first_name}!
          </h1>
          <p className="mt-1 text-gray-500">
            Track your progress and continue learning
          </p>
        </div>
        
        {continueCourse && (
          <Button
            variant="primary"
            className="mt-4 sm:mt-0 bg-emerald-600 hover:bg-emerald-700"
            onClick={() => navigate(`/teacher/courses/${continueCourse.course_id}`)}
          >
            <PlayIcon className="h-4 w-4 mr-2" />
            Continue Learning
          </Button>
        )}
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <p className="text-sm font-semibold text-slate-700">Learning Momentum</p>
          <div className="mt-3 flex items-center gap-4">
            <CompletionRing value={dashboard?.stats.overall_progress || 0} label={`${Math.round(dashboard?.stats.overall_progress || 0)}%`} tone="emerald" />
            <div>
              <p className="text-sm font-semibold text-slate-900">Overall completion</p>
              <p className="text-xs text-slate-500">
                {dashboard?.stats.completed_courses || 0} / {dashboard?.stats.total_courses || 0} courses finished
              </p>
            </div>
          </div>
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <p className="text-sm font-semibold text-slate-700">Streak Power</p>
          <div className="mt-3 flex items-center gap-4">
            <CompletionRing value={streakProgress} label={`${gamification?.streak.current_days || 0}d`} tone="blue" />
            <div>
              <p className="text-sm font-semibold text-slate-900">
                {gamification?.streak.current_days || 0} day streak
              </p>
              <p className="text-xs text-slate-500">
                Target: {gamification?.streak.target_days || 5} consecutive days
              </p>
            </div>
          </div>
        </div>
        <DeadlinePressureBar
          overallProgress={dashboard?.stats.overall_progress || 0}
          upcomingDeadlines={upcomingDeadlines}
          overdueDeadlines={overdueDeadlines}
        />
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
          {gamification ? (
            <DailyQuestCard
              quest={gamification.quest}
              claiming={claimQuestMutation.isPending}
              onClaim={() => claimQuestMutation.mutate(gamification.quest.key)}
            />
          ) : (
            <div className="h-48 animate-pulse rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
              <div className="h-full rounded-xl bg-slate-100" />
            </div>
          )}
        </div>
      </div>

      {!gamificationLoading && gamification && (
        <BadgeShowcase
          badges={gamification.badges}
          currentLevel={gamification.badge_current.level}
        />
      )}
      
      {/* Unread Notifications / Reminders */}
      {unreadNotifications.length > 0 && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
          <div className="flex items-center justify-between px-5 py-3 border-b border-gray-100 bg-red-50/60">
            <div className="flex items-center gap-2">
              <BellAlertIcon className="h-5 w-5 text-red-500" />
              <h2 className="text-sm font-semibold text-gray-900">
                {unreadNotifications.length} new notification{unreadNotifications.length !== 1 ? 's' : ''}
              </h2>
            </div>
            <div className="flex items-center gap-3">
              {unreadNotifications.length > 1 && (
                <button
                  type="button"
                  onClick={() => markAllReadMutation.mutate()}
                  disabled={markAllReadMutation.isPending}
                  className="text-xs text-emerald-600 hover:text-emerald-700 flex items-center gap-1"
                >
                  <CheckIcon className="h-3.5 w-3.5" />
                  Mark all read
                </button>
              )}
              <button
                type="button"
                onClick={() => navigate('/teacher/reminders')}
                className="text-xs text-emerald-600 hover:text-emerald-700 flex items-center gap-1"
              >
                View all
                <ArrowRightIcon className="h-3 w-3" />
              </button>
            </div>
          </div>
          <div className="divide-y divide-gray-50">
            {unreadNotifications.map((n) => (
              <button
                key={n.id}
                type="button"
                onClick={() => handleNotifClick(n)}
                className="w-full flex items-start gap-3 px-5 py-3 text-left hover:bg-gray-50 transition-colors"
              >
                <div className="flex-shrink-0 mt-0.5">
                  <NotifIcon type={n.notification_type} />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-900">{n.title}</p>
                  <p className="text-xs text-gray-500 mt-0.5 line-clamp-2">{n.message}</p>
                  <p className="text-xs text-gray-400 mt-1">
                    {formatDistanceToNow(new Date(n.created_at), { addSuffix: true })}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); markReadMutation.mutate(n.id); }}
                  className="flex-shrink-0 text-xs text-gray-400 hover:text-emerald-600 mt-1"
                  title="Dismiss"
                >
                  <CheckIcon className="h-4 w-4" />
                </button>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Stats Grid */}
      <div data-tour="teacher-dashboard-stats" className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <ProgressCard
          title="Overall Progress"
          value={`${dashboard?.stats.overall_progress || 0}%`}
          subtitle="Keep it up!"
          icon={<AcademicCapIcon className="h-6 w-6" />}
          progress={dashboard?.stats.overall_progress}
          color="emerald"
          loading={statsLoading}
        />
        
        <ProgressCard
          title="Total Courses"
          value={dashboard?.stats.total_courses || 0}
          subtitle="Assigned to you"
          icon={<BookOpenIcon className="h-6 w-6" />}
          color="blue"
          loading={statsLoading}
        />
        
        <ProgressCard
          title="Completed"
          value={dashboard?.stats.completed_courses || 0}
          subtitle="Courses finished"
          icon={<CheckCircleIcon className="h-6 w-6" />}
          color="purple"
          loading={statsLoading}
        />
        
        <ProgressCard
          title="Pending"
          value={dashboard?.stats.pending_assignments || 0}
          subtitle="Assignments due"
          icon={<ClockIcon className="h-6 w-6" />}
          color="amber"
          loading={statsLoading}
        />
      </div>
      
      {/* Continue Learning + Deadlines */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Continue Learning */}
        <div data-tour="teacher-dashboard-continue" className="lg:col-span-2">
          <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-gray-900">Continue Learning</h2>
              <button 
                onClick={() => navigate('/teacher/courses')}
                className="text-sm text-emerald-600 hover:text-emerald-700 flex items-center"
              >
                View All
                <ArrowRightIcon className="h-4 w-4 ml-1" />
              </button>
            </div>
            
            {continueCourse ? (
              <div 
                className="relative bg-gradient-to-r from-slate-800 to-slate-900 rounded-xl p-6 cursor-pointer group overflow-hidden"
                onClick={() => navigate(`/teacher/courses/${continueCourse.course_id}`)}
              >
                {/* Background pattern */}
                <div className="absolute inset-0 opacity-10">
                  <div className="absolute inset-0 bg-[radial-gradient(circle_at_30%_50%,white_1px,transparent_1px)] bg-[size:20px_20px]" />
                </div>
                
                <div className="relative flex items-center">
                  <div className="flex-shrink-0 mr-6">
                    <div className="h-20 w-20 bg-emerald-500/20 rounded-xl flex items-center justify-center group-hover:bg-emerald-500/30 transition-colors">
                      <PlayIcon className="h-10 w-10 text-emerald-400" />
                    </div>
                  </div>
                  
                  <div className="flex-1 min-w-0">
                    <h3 className="text-xl font-semibold text-white mb-1">
                      {continueCourse.course_title}
                    </h3>
                    <p className="text-slate-400 text-sm mb-3 line-clamp-1">
                      {continueCourse.content_title}
                    </p>
                    
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
              </div>
            ) : (
              <div className="text-center py-8 text-gray-500">
                <BookOpenIcon className="h-12 w-12 mx-auto mb-3 text-gray-400" />
                <p>No courses in progress</p>
                <button 
                  onClick={() => navigate('/teacher/courses')}
                  className="mt-2 text-emerald-600 hover:text-emerald-700"
                >
                  Browse courses
                </button>
              </div>
            )}
          </div>
        </div>
        
        {/* Upcoming Deadlines */}
        <div data-tour="teacher-dashboard-deadlines" className="lg:col-span-1">
          <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100 h-full">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-gray-900">Upcoming Deadlines</h2>
              <CalendarDaysIcon className="h-5 w-5 text-gray-400" />
            </div>
            
            <div className="space-y-3">
              {deadlines?.map((item) => (
                <div 
                  key={item.id}
                  className="flex items-center p-3 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors cursor-pointer"
                  onClick={() =>
                    navigate(item.type === 'course' ? `/teacher/courses/${item.id}` : `/teacher/assignments`)
                  }
                >
                  <div className={`p-2 rounded-lg mr-3 ${
                    item.type === 'course' ? 'bg-blue-100' : 'bg-amber-100'
                  }`}>
                    {item.type === 'course' ? (
                      <BookOpenIcon className="h-4 w-4 text-blue-600" />
                    ) : (
                      <ClockIcon className="h-4 w-4 text-amber-600" />
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-900 truncate">{item.title}</p>
                    <p className={`text-xs ${
                      item.days_left <= 3 ? 'text-red-500' : 'text-gray-500'
                    }`}>
                      {item.days_left === 0 ? 'Due today' : `${item.days_left} days left`}
                    </p>
                  </div>
                </div>
              ))}
              
              {(!deadlines || deadlines.length === 0) && (
                <p className="text-center text-gray-500 py-4">No upcoming deadlines</p>
              )}
            </div>
          </div>
        </div>
      </div>
      
      {/* Recent Courses */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900">My Courses</h2>
          <button 
            onClick={() => navigate('/teacher/courses')}
            className="text-sm text-emerald-600 hover:text-emerald-700 flex items-center"
          >
            View All
            <ArrowRightIcon className="h-4 w-4 ml-1" />
          </button>
        </div>
        
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {coursesLoading ? (
            Array.from({ length: 4 }).map((_, i) => (
              <CourseCard key={i} loading id="" title="" description="" progress={0} totalModules={0} completedModules={0} estimatedHours={0} status="NOT_STARTED" />
            ))
          ) : (
            (courses ?? []).slice(0, 4).map((course) => (
              <CourseCard
                key={course.id}
                {...toCourseCard(course)}
              />
            ))
          )}
        </div>
      </div>

    </div>
  );
};
