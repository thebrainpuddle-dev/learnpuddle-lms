// src/pages/teacher/DashboardPage.tsx
//
// Teacher Overview dashboard — real API data, no mocks.

import React, { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  Play,
  ArrowRight,
  BookOpen,
  CheckCircle2,
  Award,
  Clock,
  ClipboardList,
  Megaphone,
  ChevronLeft,
  ChevronRight,
  CalendarDays,
  TrendingUp,
} from 'lucide-react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { cn } from '../../design-system/theme/cn';
import { useAuthStore } from '../../stores/authStore';
import {
  teacherService,
  TeacherCalendarDay,
  TeacherCalendarEvent,
} from '../../services/teacherService';
import { notificationService } from '../../services/notificationService';
import { usePageTitle } from '../../hooks/usePageTitle';
import {
  format,
  startOfMonth,
  endOfMonth,
  startOfWeek,
  endOfWeek,
  eachDayOfInterval,
  isSameMonth,
  isToday,
  addMonths,
  subMonths,
  isSameDay,
  parseISO,
} from 'date-fns';
import { formatDistanceToNow } from 'date-fns';

// ─── Helpers ──────────────────────────────────────────────────────────────────

function getGreeting(): string {
  const h = new Date().getHours();
  if (h < 12) return 'Good morning';
  if (h < 17) return 'Good afternoon';
  return 'Good evening';
}

// ─── Study Calendar ───────────────────────────────────────────────────────────

const WEEKDAYS = ['S', 'M', 'T', 'W', 'T', 'F', 'S'];

function StudyCalendar({
  calendarDays,
  events,
  currentMonth,
  onMonthChange,
  isLoading,
}: {
  calendarDays: TeacherCalendarDay[];
  events: TeacherCalendarEvent[];
  currentMonth: Date;
  onMonthChange: (month: Date) => void;
  isLoading: boolean;
}) {
  const monthStart = startOfMonth(currentMonth);
  const monthEnd = endOfMonth(currentMonth);
  const calStart = startOfWeek(monthStart);
  const calEnd = endOfWeek(monthEnd);
  const days = eachDayOfInterval({ start: calStart, end: calEnd });

  // Build lookup maps from API data
  const dayMap = useMemo(() => {
    const m = new Map<string, TeacherCalendarDay>();
    calendarDays.forEach((d) => m.set(d.date, d));
    return m;
  }, [calendarDays]);

  const eventsByDate = useMemo(() => {
    const m = new Map<string, TeacherCalendarEvent[]>();
    events.forEach((e) => {
      const existing = m.get(e.date) || [];
      existing.push(e);
      m.set(e.date, existing);
    });
    return m;
  }, [events]);

  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
      <div className="flex items-center justify-between px-5 py-3.5 border-b border-gray-50">
        <div className="flex items-center gap-2">
          <CalendarDays className="h-4 w-4 text-tp-accent" />
          <h3 className="text-[13px] font-semibold text-tp-text">Study Calendar</h3>
        </div>
        <div className="flex items-center gap-0.5">
          <button
            onClick={() => onMonthChange(subMonths(currentMonth, 1))}
            className="p-1 rounded-md hover:bg-gray-100 text-gray-400 hover:text-tp-text transition-colors"
          >
            <ChevronLeft className="h-3.5 w-3.5" />
          </button>
          <span className="text-[11px] font-medium text-tp-text-secondary px-1.5 min-w-[88px] text-center">
            {format(currentMonth, 'MMM yyyy')}
          </span>
          <button
            onClick={() => onMonthChange(addMonths(currentMonth, 1))}
            className="p-1 rounded-md hover:bg-gray-100 text-gray-400 hover:text-tp-text transition-colors"
          >
            <ChevronRight className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      <div className="px-4 pt-3 pb-2">
        {isLoading ? (
          <div className="h-[180px] tp-skeleton rounded-lg" />
        ) : (
          <>
            <div className="grid grid-cols-7 mb-1">
              {WEEKDAYS.map((d, i) => (
                <div
                  key={i}
                  className="text-center text-[10px] font-semibold text-gray-300 uppercase tracking-widest py-1"
                >
                  {d}
                </div>
              ))}
            </div>

            <div className="grid grid-cols-7">
              {days.map((day, i) => {
                const inMonth = isSameMonth(day, currentMonth);
                const today = isToday(day);
                const dateStr = format(day, 'yyyy-MM-dd');
                const calDay = dayMap.get(dateStr);
                const dayEvents = eventsByDate.get(dateStr) || [];

                const studied = inMonth && calDay != null && calDay.total_minutes > 0;
                const hasAssessment =
                  inMonth && dayEvents.some((e) => e.type === 'assignment_due');

                return (
                  <div
                    key={i}
                    className={cn(
                      'relative flex flex-col items-center py-[5px] rounded-lg',
                      !inMonth && 'opacity-20',
                      today && 'bg-orange-50',
                    )}
                  >
                    <span
                      className={cn(
                        'text-[11px] leading-none tabular-nums',
                        today
                          ? 'text-tp-accent font-bold'
                          : inMonth
                            ? 'text-tp-text-secondary'
                            : 'text-gray-300',
                      )}
                    >
                      {format(day, 'd')}
                    </span>
                    {inMonth && (studied || hasAssessment) && (
                      <div className="flex items-center gap-[3px] mt-[3px]">
                        {studied && (
                          <span className="w-[4px] h-[4px] rounded-full bg-emerald-400" />
                        )}
                        {hasAssessment && (
                          <span className="w-[4px] h-[4px] rounded-full bg-tp-accent" />
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </>
        )}
      </div>

      <div className="flex items-center gap-4 px-5 py-2.5 border-t border-gray-50 bg-gray-50/50">
        <div className="flex items-center gap-1.5">
          <span className="w-[5px] h-[5px] rounded-full bg-emerald-400" />
          <span className="text-[10px] text-gray-400 font-medium">Studied</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-[5px] h-[5px] rounded-full bg-tp-accent" />
          <span className="text-[10px] text-gray-400 font-medium">Assessment</span>
        </div>
      </div>
    </div>
  );
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

// ─── Chart Tooltip ────────────────────────────────────────────────────────────

function ChartTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-gray-900 rounded-lg px-3 py-2 shadow-xl border border-gray-800">
      <p className="text-[10px] text-gray-400 uppercase tracking-wider font-medium">
        {label}
      </p>
      <p className="text-sm font-semibold text-white mt-0.5">
        {payload[0].value}h{' '}
        <span className="text-gray-400 font-normal">studied</span>
      </p>
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────

export const DashboardPage: React.FC = () => {
  usePageTitle('Overview');
  const navigate = useNavigate();
  const { user } = useAuthStore();
  const [calMonth, setCalMonth] = useState(new Date());
  const [chartView, setChartView] = useState<'week' | 'month'>('week');

  // ─── Data queries ─────────────────────────────────────────────

  const { data: dashboard, isLoading } = useQuery({
    queryKey: ['teacherDashboard'],
    queryFn: teacherService.getDashboard,
  });

  const { data: courses = [] } = useQuery({
    queryKey: ['teacherCourses'],
    queryFn: teacherService.listCourses,
  });

  const { data: gamification, isLoading: gamLoading } = useQuery({
    queryKey: ['teacherGamification'],
    queryFn: teacherService.getGamificationSummary,
  });

  const { data: assignments = [] } = useQuery({
    queryKey: ['teacherAssignmentsAll'],
    queryFn: () => teacherService.listAssignments(),
  });

  const { data: announcements = [] } = useQuery({
    queryKey: ['dashboardAnnouncements'],
    queryFn: () => notificationService.getNotifications({ limit: 3 }),
  });

  // Calendar data — real API, keyed by month
  const calMonthStart = format(startOfMonth(calMonth), 'yyyy-MM-dd');
  const { data: calendarData, isLoading: calLoading } = useQuery({
    queryKey: ['teacherCalendar', calMonthStart],
    queryFn: () => teacherService.getCalendar(35, calMonthStart),
  });

  // Weekly data for study chart — current week
  const weekStartStr = format(startOfWeek(new Date()), 'yyyy-MM-dd');
  const { data: weekData } = useQuery({
    queryKey: ['teacherCalendarWeek', weekStartStr],
    queryFn: () => teacherService.getCalendar(7, weekStartStr),
  });

  // Monthly data for study chart — current month
  const monthStartStr = format(startOfMonth(new Date()), 'yyyy-MM-dd');
  const { data: monthData } = useQuery({
    queryKey: ['teacherCalendarMonth', monthStartStr],
    queryFn: () => teacherService.getCalendar(30, monthStartStr),
    enabled: chartView === 'month',
  });

  // ─── Derived data ────────────────────────────────────────────

  const continueCourse = dashboard?.continue_learning;
  const pendingAssessments = assignments
    .filter((a) => a.submission_status === 'PENDING')
    .slice(0, 4);

  const completedCourses = dashboard?.stats.completed_courses ?? 0;
  const inProgressCourses = courses.filter(
    (c) =>
      Number(c.progress_percentage) > 0 && Number(c.progress_percentage) < 100,
  ).length;

  const classroomCourses = courses.slice(0, 5);

  // Chart data from real API — week or month view
  const chartData = useMemo(() => {
    if (chartView === 'month') {
      if (!monthData?.days?.length) return [];
      // Group by week for month view
      const weeks: Record<string, number> = {};
      monthData.days.forEach((d) => {
        const weekNum = `W${Math.ceil(new Date(d.date).getDate() / 7)}`;
        weeks[weekNum] = (weeks[weekNum] || 0) + d.total_minutes;
      });
      return Object.entries(weeks).map(([week, mins]) => ({
        day: week,
        hours: Math.round((mins / 60) * 10) / 10,
      }));
    }
    if (!weekData?.days?.length) return [];
    return weekData.days.map((d) => ({
      day: d.short_weekday,
      hours: Math.round((d.total_minutes / 60) * 10) / 10,
    }));
  }, [weekData, monthData, chartView]);

  const totalWeeklyHours = useMemo(
    () => chartData.reduce((sum, d) => sum + d.hours, 0),
    [chartData],
  );

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
            {pendingAssessments.length > 0 && (
              <span className="text-tp-accent font-medium">
                {' '}
                · {pendingAssessments.length} assessment
                {pendingAssessments.length !== 1 ? 's' : ''} pending
              </span>
            )}
          </p>
        </div>
      </div>

      {/* ─── Stat Cards ────────────────────────────────────────── */}
      <div data-tour="teacher-dashboard-stats" className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <StatCard
          icon={TrendingUp}
          iconBg="bg-orange-50"
          iconColor="text-tp-accent"
          value={`${dashboard?.stats.overall_progress ?? 0}%`}
          label="Overall Progress"
          loading={isLoading}
        />
        <StatCard
          icon={CheckCircle2}
          iconBg="bg-emerald-50"
          iconColor="text-emerald-500"
          value={completedCourses}
          label="Completed"
          loading={isLoading}
        />
        <StatCard
          icon={Award}
          iconBg="bg-amber-50"
          iconColor="text-amber-500"
          value={
            gamLoading
              ? '—'
              : (gamification?.badges.filter((b) => b.unlocked).length ?? 0)
          }
          label="Certificates"
        />
        <StatCard
          icon={BookOpen}
          iconBg="bg-blue-50"
          iconColor="text-blue-500"
          value={inProgressCourses}
          label="In Progress"
          loading={isLoading}
        />
      </div>

      {/* ─── Main Grid ─────────────────────────────────────────── */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">
        {/* Left column */}
        <div className="xl:col-span-2 space-y-5">
          {/* Study Statistics — real weekly data */}
          <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
            <div className="flex items-center justify-between px-5 py-3.5 border-b border-gray-50">
              <div>
                <h2 className="text-[13px] font-semibold text-tp-text">
                  Study Statistics
                </h2>
                <p className="text-[11px] text-gray-400 mt-0.5">
                  <span className="text-tp-text font-semibold">
                    {totalWeeklyHours}h
                  </span>{' '}
                  this week
                </p>
              </div>
              <div className="flex rounded-lg overflow-hidden border border-gray-200">
                <button
                  onClick={() => setChartView('week')}
                  className={cn(
                    'px-3 py-1.5 text-[11px] font-semibold transition-colors',
                    chartView === 'week'
                      ? 'bg-tp-accent text-white'
                      : 'text-gray-400 hover:text-tp-text hover:bg-gray-50',
                  )}
                >
                  Week
                </button>
                <button
                  onClick={() => setChartView('month')}
                  className={cn(
                    'px-3 py-1.5 text-[11px] font-semibold transition-colors',
                    chartView === 'month'
                      ? 'bg-tp-accent text-white'
                      : 'text-gray-400 hover:text-tp-text hover:bg-gray-50',
                  )}
                >
                  Month
                </button>
              </div>
            </div>

            <div className="px-5 pt-4 pb-5">
              {chartData.length === 0 ? (
                <div className="h-[180px] flex items-center justify-center">
                  <p className="text-[13px] text-gray-400">
                    No study data this week
                  </p>
                </div>
              ) : (
                <div className="h-[180px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={chartData} barSize={28} barGap={4}>
                      <defs>
                        <linearGradient
                          id="barGradient"
                          x1="0"
                          y1="0"
                          x2="0"
                          y2="1"
                        >
                          <stop
                            offset="0%"
                            stopColor="#F97316"
                            stopOpacity={1}
                          />
                          <stop
                            offset="100%"
                            stopColor="#FDBA74"
                            stopOpacity={0.7}
                          />
                        </linearGradient>
                      </defs>
                      <XAxis
                        dataKey="day"
                        axisLine={false}
                        tickLine={false}
                        tick={{ fill: '#9CA3AF', fontSize: 11, fontWeight: 500 }}
                        dy={8}
                      />
                      <YAxis
                        axisLine={false}
                        tickLine={false}
                        tick={{ fill: '#D1D5DB', fontSize: 10 }}
                        tickFormatter={(v) => `${v}h`}
                        width={32}
                      />
                      <Tooltip
                        content={<ChartTooltip />}
                        cursor={{
                          fill: 'rgba(249, 115, 22, 0.04)',
                          radius: 8,
                        }}
                      />
                      <Bar
                        dataKey="hours"
                        fill="url(#barGradient)"
                        radius={[6, 6, 2, 2]}
                      />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              )}
            </div>
          </div>

          {/* Classroom Table */}
          <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
            <div className="flex items-center justify-between px-5 py-3.5 border-b border-gray-50">
              <h2 className="text-[13px] font-semibold text-tp-text">
                My Classroom
              </h2>
              <button
                onClick={() => navigate('/teacher/courses')}
                className="text-[11px] text-tp-accent hover:text-tp-accent-dark font-medium flex items-center gap-1 transition-colors"
              >
                View All <ArrowRight className="h-3 w-3" />
              </button>
            </div>

            {isLoading ? (
              <div className="p-4 space-y-2">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="h-14 tp-skeleton rounded-xl" />
                ))}
              </div>
            ) : classroomCourses.length === 0 ? (
              <div className="py-12 text-center">
                <BookOpen className="h-8 w-8 mx-auto text-gray-200 mb-2" />
                <p className="text-[13px] text-gray-400">
                  No courses assigned yet
                </p>
              </div>
            ) : (
              <>
                <div className="hidden sm:grid grid-cols-12 gap-4 px-5 py-2.5 bg-gray-50/80 text-[10px] uppercase tracking-wider font-semibold text-gray-400 border-b border-gray-50">
                  <div className="col-span-5">Course</div>
                  <div className="col-span-3">Progress</div>
                  <div className="col-span-2">Status</div>
                  <div className="col-span-2 text-right">Action</div>
                </div>

                <div className="divide-y divide-gray-50">
                  {classroomCourses.map((course) => {
                    const progress = Number(course.progress_percentage || 0);
                    const status =
                      progress >= 100
                        ? 'Completed'
                        : progress > 0
                          ? 'Active'
                          : 'Not Started';
                    const statusStyle =
                      status === 'Completed'
                        ? 'bg-emerald-50 text-emerald-600'
                        : status === 'Active'
                          ? 'bg-orange-50 text-tp-accent'
                          : 'bg-gray-50 text-gray-500';

                    return (
                      <div
                        key={course.id}
                        className="grid grid-cols-1 sm:grid-cols-12 gap-2 sm:gap-4 px-5 py-3 hover:bg-gray-50/50 transition-colors items-center"
                      >
                        <div className="sm:col-span-5 flex items-center gap-3 min-w-0">
                          <div className="h-9 w-9 rounded-lg bg-gray-50 flex items-center justify-center flex-shrink-0 border border-gray-100 overflow-hidden">
                            {course.thumbnail ? (
                              <img
                                src={course.thumbnail}
                                alt=""
                                className="h-9 w-9 object-cover"
                              />
                            ) : (
                              <BookOpen className="h-4 w-4 text-gray-300" />
                            )}
                          </div>
                          <div className="min-w-0">
                            <p className="text-[13px] font-medium text-tp-text truncate leading-tight">
                              {course.title}
                            </p>
                            <p className="text-[11px] text-gray-400 mt-0.5">
                              {course.total_content_count} lessons
                            </p>
                          </div>
                        </div>

                        <div className="sm:col-span-3 flex items-center gap-2.5">
                          <div className="flex-1 h-[6px] bg-gray-100 rounded-full overflow-hidden">
                            <div
                              className="h-full bg-gradient-to-r from-tp-accent to-amber-400 rounded-full transition-all duration-700"
                              style={{
                                width: `${Math.min(100, progress)}%`,
                              }}
                            />
                          </div>
                          <span className="text-[11px] text-tp-text-secondary font-semibold tabular-nums w-8 text-right">
                            {Math.round(progress)}%
                          </span>
                        </div>

                        <div className="sm:col-span-2">
                          <span
                            className={cn(
                              'inline-flex px-2 py-[3px] rounded-md text-[10px] font-semibold uppercase tracking-wide leading-none',
                              statusStyle,
                            )}
                          >
                            {status}
                          </span>
                        </div>

                        <div className="sm:col-span-2 text-right">
                          <button
                            onClick={() =>
                              navigate(`/teacher/courses/${course.id}`)
                            }
                            className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-[11px] font-medium bg-orange-50 text-tp-accent hover:bg-orange-100 transition-colors"
                          >
                            {progress > 0 && progress < 100
                              ? 'Continue'
                              : progress >= 100
                                ? 'Review'
                                : 'Start'}
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </>
            )}
          </div>
        </div>

        {/* Right column */}
        <div className="space-y-5">
          {/* Study Calendar — real API data */}
          <StudyCalendar
            calendarDays={calendarData?.days ?? []}
            events={calendarData?.events ?? []}
            currentMonth={calMonth}
            onMonthChange={setCalMonth}
            isLoading={calLoading}
          />

          {/* Continue Learning */}
          {continueCourse && (
            <button
              data-tour="teacher-dashboard-continue"
              onClick={() =>
                navigate(`/teacher/courses/${continueCourse.course_id}`)
              }
              className="w-full text-left bg-gradient-to-br from-tp-accent via-orange-500 to-amber-500 rounded-2xl p-5 group transition-all hover:shadow-lg hover:shadow-orange-200/50"
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

          {/* Upcoming Assessments */}
          <div data-tour="teacher-dashboard-deadlines" className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
            <div className="flex items-center justify-between px-5 py-3.5 border-b border-gray-50">
              <div className="flex items-center gap-2">
                <ClipboardList className="h-4 w-4 text-tp-accent" />
                <h3 className="text-[13px] font-semibold text-tp-text">
                  Upcoming
                </h3>
              </div>
              <button
                onClick={() => navigate('/teacher/assignments')}
                className="text-[11px] text-tp-accent hover:text-tp-accent-dark font-medium flex items-center gap-1 transition-colors"
              >
                All <ArrowRight className="h-3 w-3" />
              </button>
            </div>

            {pendingAssessments.length === 0 ? (
              <div className="py-10 text-center">
                <CheckCircle2 className="h-7 w-7 mx-auto text-emerald-200 mb-2" />
                <p className="text-[13px] text-gray-400 font-medium">
                  All caught up
                </p>
              </div>
            ) : (
              <div className="divide-y divide-gray-50">
                {pendingAssessments.map((a) => (
                  <button
                    key={a.id}
                    onClick={() =>
                      a.is_quiz
                        ? navigate(`/teacher/quizzes/${a.id}`)
                        : navigate('/teacher/assignments')
                    }
                    className="w-full text-left px-5 py-3 hover:bg-gray-50/50 transition-colors group/item"
                  >
                    <p className="text-[13px] font-medium text-tp-text truncate group-hover/item:text-tp-accent transition-colors">
                      {a.title}
                    </p>
                    <div className="flex items-center gap-2 mt-1">
                      <span className="text-[11px] text-gray-400 truncate">
                        {a.course_title}
                      </span>
                      {a.due_date && (
                        <>
                          <span className="text-gray-200">·</span>
                          <span className="text-[11px] text-amber-500 flex items-center gap-1 font-medium">
                            <Clock className="h-3 w-3" />
                            {new Date(a.due_date).toLocaleDateString('en-US', {
                              month: 'short',
                              day: 'numeric',
                            })}
                          </span>
                        </>
                      )}
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Announcements */}
          <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
            <div className="flex items-center justify-between px-5 py-3.5 border-b border-gray-50">
              <div className="flex items-center gap-2">
                <Megaphone className="h-4 w-4 text-tp-accent" />
                <h3 className="text-[13px] font-semibold text-tp-text">
                  Announcements
                </h3>
              </div>
              <button
                onClick={() => navigate('/teacher/reminders')}
                className="text-[11px] text-tp-accent hover:text-tp-accent-dark font-medium flex items-center gap-1 transition-colors"
              >
                All <ArrowRight className="h-3 w-3" />
              </button>
            </div>

            {announcements.length === 0 ? (
              <div className="py-10 text-center">
                <Megaphone className="h-7 w-7 mx-auto text-gray-200 mb-2" />
                <p className="text-[13px] text-gray-400 font-medium">
                  No announcements
                </p>
              </div>
            ) : (
              <div className="divide-y divide-gray-50">
                {announcements.map((n) => (
                  <div key={n.id} className="px-5 py-3">
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-[13px] font-medium text-tp-text truncate">
                        {n.title}
                      </p>
                      {!n.is_read && (
                        <span className="w-[6px] h-[6px] rounded-full bg-tp-accent flex-shrink-0 mt-1.5" />
                      )}
                    </div>
                    <p className="text-[11px] text-gray-400 mt-0.5 line-clamp-1">
                      {n.message}
                    </p>
                    <p className="text-[10px] text-gray-300 mt-1 font-medium">
                      {formatDistanceToNow(new Date(n.created_at), {
                        addSuffix: true,
                      })}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
