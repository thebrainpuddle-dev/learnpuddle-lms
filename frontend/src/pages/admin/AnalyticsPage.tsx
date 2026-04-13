// src/pages/admin/AnalyticsPage.tsx

import React, { useMemo, useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { adminService } from '../../services/adminService';
import { adminReportsService } from '../../services/adminReportsService';
import { adminRemindersService } from '../../services/adminRemindersService';
import { Loading, useToast } from '../../components/common';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, LineChart, Line, PieChart, Pie, Cell,
  Area, AreaChart,
} from 'recharts';
import {
  ChartBarIcon,
  UserGroupIcon,
  AcademicCapIcon,
  ArrowTrendingUpIcon,
  ClipboardDocumentListIcon,
  BuildingLibraryIcon,
  ExclamationTriangleIcon,
  ChevronDownIcon,
  ChevronUpIcon,
  FunnelIcon,
  BellAlertIcon,
  TableCellsIcon,
} from '@heroicons/react/24/outline';
import { usePageTitle } from '../../hooks/usePageTitle';

/* ── New chart components ─────────────────────────────────────── */
import { DeadlineAdherenceChart } from '../../components/analytics/DeadlineAdherenceChart';
import { CertComplianceChart } from '../../components/analytics/CertComplianceChart';
import { ApprovalTrendsChart } from '../../components/analytics/ApprovalTrendsChart';
import { CourseEffectivenessChart } from '../../components/analytics/CourseEffectivenessChart';
import { ReportDrillDown } from '../../components/analytics/ReportDrillDown';

/* ── Helpers ────────────────────────────────────────────────────── */

/** Recharts PieChart shows nothing when all data values are 0.
 *  This helper detects that case so we can show a placeholder instead. */
function hasNonZero(arr: number[]): boolean {
  return arr.some(v => v > 0);
}

/** Empty state placeholder for chart panels */
const EmptyChart: React.FC<{ message: string }> = ({ message }) => (
  <div className="flex items-center justify-center h-full text-gray-400 text-sm">
    {message}
  </div>
);

/* ── Recharts custom legend for doughnut charts ─────────────────── */
const ENGAGEMENT_COLORS = ['#10b981', '#3b82f6', '#f59e0b', '#ef4444'];
const ASSIGNMENT_COLORS = ['#6366f1', '#10b981', '#f59e0b'];

type AnalyticsView = 'charts' | 'reports';

export const AnalyticsPage: React.FC = () => {
  usePageTitle('Analytics');
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const toast = useToast();
  const [courseFilter, setCourseFilter] = useState<string>('');
  const [monthsFilter, setMonthsFilter] = useState<number>(6);
  const [attentionExpanded, setAttentionExpanded] = useState(true);
  const [sentTeacherIds, setSentTeacherIds] = useState<Set<string>>(new Set());

  /* ── View toggle: Charts vs Reports drill-down ─────────────── */
  const activeView: AnalyticsView = searchParams.get('view') === 'reports' ? 'reports' : 'charts';
  const reportTab = (searchParams.get('tab') as 'COURSE' | 'ASSIGNMENT') || undefined;
  const reportCourseId = searchParams.get('course_id') || undefined;
  const reportAssignmentId = searchParams.get('assignment_id') || undefined;
  const reportStatus = searchParams.get('status') || undefined;

  const switchToReports = (params?: { tab?: string; course_id?: string; assignment_id?: string; status?: string }) => {
    const sp = new URLSearchParams();
    sp.set('view', 'reports');
    if (params?.tab) sp.set('tab', params.tab);
    if (params?.course_id) sp.set('course_id', params.course_id);
    if (params?.assignment_id) sp.set('assignment_id', params.assignment_id);
    if (params?.status) sp.set('status', params.status);
    setSearchParams(sp);
  };

  const switchToCharts = () => {
    setSearchParams({});
  };

  const reminderMutation = useMutation({
    mutationFn: (teacherIds: string[]) =>
      adminRemindersService.send({
        reminder_type: 'CUSTOM',
        teacher_ids: teacherIds,
        subject: 'Reminder: Get started with your courses',
        message: 'You have courses assigned to you that haven\'t been started yet. Please log in to the platform and begin your learning journey.',
      }),
    onSuccess: (data, teacherIds) => {
      // Resolve teacher names from stats detail for a clear confirmation
      const detail = stats?.inactive_teachers_detail ?? [];
      const names = teacherIds
        .map((id) => detail.find((t) => t.id === id)?.name)
        .filter(Boolean);
      const who = names.length > 0
        ? names.length <= 3
          ? names.join(', ')
          : `${names.slice(0, 2).join(', ')} and ${names.length - 2} more`
        : `${data.sent} teacher${data.sent !== 1 ? 's' : ''}`;
      toast.success('Reminder sent', `Sent to ${who}. They will see it in their Reminders page.`);
      setSentTeacherIds((prev) => {
        const next = new Set(prev);
        teacherIds.forEach((id) => next.add(id));
        return next;
      });
    },
    onError: () => {
      toast.error('Failed', 'Could not send reminder. Please try again.');
    },
  });

  const { data: courses } = useQuery({
    queryKey: ['reportCourses'],
    queryFn: adminReportsService.listCourses,
  });

  const { data: analytics, isLoading: analyticsLoading, error: analyticsError } = useQuery({
    queryKey: ['tenantAnalytics', courseFilter, monthsFilter],
    queryFn: () => adminService.getTenantAnalytics({
      course_id: courseFilter || undefined,
      months: monthsFilter,
    }),
    retry: 1,
  });

  const { data: stats, isLoading: statsLoading, error: statsError } = useQuery({
    queryKey: ['adminDashboardStats'],
    queryFn: adminService.getTenantStats,
    retry: 1,
  });

  const isLoading = analyticsLoading || statsLoading;

  const goToReports = (params: { tab?: string; assignment_id?: string; course_id?: string; status?: string }) => {
    switchToReports(params);
  };

  /* Safely extract with defaults (memoized for chart deps) */
  const cb = useMemo(() => analytics?.course_breakdown ?? [], [analytics?.course_breakdown]);
  const mt = useMemo(() => analytics?.monthly_trend ?? [], [analytics?.monthly_trend]);
  const ab = analytics?.assignment_breakdown ?? { total: 0, manual: 0, auto_quiz: 0, auto_reflection: 0 };
  const te = analytics?.teacher_engagement ?? { highly_active: 0, active: 0, low_activity: 0, inactive: 0 };
  const ds = useMemo(() => analytics?.department_stats ?? [], [analytics?.department_stats]);

  /* ── Recharts data (transformed from API format) ────────────── */

  const courseCompletionData = useMemo(() =>
    cb.map(c => ({
      name: c.title,
      Completed: c.completed,
      'In Progress': c.in_progress,
      'Not Started': c.not_started,
      course_id: c.course_id,
    })),
    [cb]
  );

  const monthlyTrendData = useMemo(() =>
    mt.map(m => ({
      name: m.month,
      completions: m.completions,
    })),
    [mt]
  );

  const engagementValues = [te.highly_active, te.active, te.low_activity, te.inactive];
  const engagementData = useMemo(() => [
    { name: 'Highly Active', value: te.highly_active },
    { name: 'Active', value: te.active },
    { name: 'Low Activity', value: te.low_activity },
    { name: 'Inactive', value: te.inactive },
  ], [te.highly_active, te.active, te.low_activity, te.inactive]);

  const assignmentValues = [ab.manual, ab.auto_quiz, ab.auto_reflection];
  const assignmentData = useMemo(() => [
    { name: 'Manual', value: ab.manual },
    { name: 'Auto Quiz', value: ab.auto_quiz },
    { name: 'Auto Reflection', value: ab.auto_reflection },
  ], [ab.manual, ab.auto_quiz, ab.auto_reflection]);

  const deptData = useMemo(() =>
    ds.map((d: any) => ({
      name: d.department || 'Unassigned',
      Teachers: d.count,
    })),
    [ds]
  );

  /* ── Click handler for course completion bar ─────────────────── */
  const handleCourseBarClick = (data: any) => {
    if (data?.activePayload?.[0]?.payload?.course_id) {
      const courseId = data.activePayload[0].payload.course_id;
      setCourseFilter((prev) => (prev === courseId ? '' : courseId));
    }
  };

  /* ── Error state ─────────────────────────────────────────────── */
  if (analyticsError || statsError) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Analytics</h1>
          <p className="mt-1 text-sm text-gray-500">Real-time insights across your school's LMS activity</p>
        </div>
        <div className="bg-red-50 border border-red-200 rounded-xl p-6 text-center">
          <ExclamationTriangleIcon className="h-10 w-10 mx-auto text-red-400 mb-3" />
          <p className="text-red-700 font-medium">Failed to load analytics data</p>
          <p className="text-sm text-red-500 mt-1">Please refresh the page or check your connection.</p>
        </div>
      </div>
    );
  }

  /* ── Loading state ───────────────────────────────────────────── */
  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Loading />
      </div>
    );
  }

  const summaryCards = [
    { label: 'Teachers', value: stats?.total_teachers ?? 0, icon: UserGroupIcon, color: 'text-blue-600 bg-blue-50', onClick: () => navigate('/admin/teachers') },
    { label: 'Published Courses', value: stats?.published_courses ?? 0, icon: AcademicCapIcon, color: 'text-emerald-600 bg-emerald-50', onClick: () => navigate('/admin/courses') },
    { label: 'Avg Completion', value: `${stats?.avg_completion_pct ?? 0}%`, icon: ArrowTrendingUpIcon, color: 'text-indigo-600 bg-indigo-50', onClick: () => goToReports({ tab: 'COURSE' }) },
    { label: 'Assignments', value: stats?.total_assignments ?? 0, icon: ClipboardDocumentListIcon, color: 'text-amber-600 bg-amber-50', onClick: () => goToReports({ tab: 'ASSIGNMENT' }) },
  ];

  return (
    <div className="space-y-6">
      {/* Header + View Toggle */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Analytics</h1>
          <p className="mt-1 text-sm text-gray-500">
            Real-time insights across your school's LMS activity
          </p>
        </div>
        <div className="flex rounded-lg border border-gray-200 bg-white overflow-hidden">
          <button
            type="button"
            onClick={switchToCharts}
            className={`inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium transition-colors ${
              activeView === 'charts'
                ? 'bg-primary-50 text-primary-700 border-r border-gray-200'
                : 'text-gray-600 hover:bg-gray-50 border-r border-gray-200'
            }`}
          >
            <ChartBarIcon className="h-4 w-4" />
            Charts
          </button>
          <button
            type="button"
            onClick={() => switchToReports()}
            className={`inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium transition-colors ${
              activeView === 'reports'
                ? 'bg-primary-50 text-primary-700'
                : 'text-gray-600 hover:bg-gray-50'
            }`}
          >
            <TableCellsIcon className="h-4 w-4" />
            Detailed Reports
          </button>
        </div>
      </div>

      {/* Summary Cards - clickable */}
      <div data-tour="admin-analytics-summary" className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {summaryCards.map(card => (
          <button
            key={card.label}
            type="button"
            onClick={card.onClick}
            className="bg-white rounded-xl border border-gray-200 p-4 text-left hover:border-primary-300 hover:shadow-sm transition-all focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-1"
          >
            <div className="flex items-center gap-3">
              <div className={`p-2 rounded-lg ${card.color}`}>
                <card.icon className="h-5 w-5" />
              </div>
              <div>
                <div className="text-xl font-bold text-gray-900">{card.value}</div>
                <div className="text-xs text-gray-500">{card.label}</div>
              </div>
            </div>
          </button>
        ))}
      </div>

      {/* ── Reports View (drill-down) ──────────────────────────── */}
      {activeView === 'reports' && (
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <ReportDrillDown
            defaultTab={reportTab}
            defaultCourseId={reportCourseId}
            defaultAssignmentId={reportAssignmentId}
            defaultStatus={reportStatus}
          />
        </div>
      )}

      {/* ── Charts View ────────────────────────────────────────── */}
      {activeView === 'charts' && (
        <>
          {/* Filters */}
          <div data-tour="admin-analytics-filters" className="bg-white rounded-xl border border-gray-200 p-4">
            <div className="flex flex-col gap-4 sm:flex-row sm:flex-wrap sm:items-end">
              <div className="flex items-center gap-2 text-sm font-medium text-gray-700">
                <FunnelIcon className="h-4 w-4" />
                Filters
              </div>
              <div className="flex flex-col items-stretch gap-2 sm:flex-row sm:items-end">
                <div>
                  <label className="block text-xs text-gray-500 mb-0.5">Course</label>
                  <select
                    value={courseFilter}
                    onChange={(e) => setCourseFilter(e.target.value)}
                    className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm"
                  >
                    <option value="">All courses</option>
                    {(courses ?? []).map((c) => (
                      <option key={c.id} value={c.id}>{c.title}</option>
                    ))}
                  </select>
                </div>
                {courseFilter && (
                  <button
                    type="button"
                    onClick={() => setCourseFilter('')}
                    className="text-xs text-primary-600 hover:text-primary-700 pb-1.5"
                  >
                    Clear
                  </button>
                )}
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-0.5">Trend period</label>
                <select
                  value={monthsFilter}
                  onChange={(e) => setMonthsFilter(Number(e.target.value))}
                  className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm"
                >
                  {[6, 9, 12].map((n) => (
                    <option key={n} value={n}>Last {n} months</option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          {/* Row 1: Course Completion + Monthly Trend */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="bg-white rounded-xl border border-gray-200 p-6">
              <div className="flex items-center gap-2 mb-4">
                <ChartBarIcon className="h-5 w-5 text-emerald-600" />
                <h2 className="font-semibold text-gray-900">Course Completion by Course</h2>
              </div>
              <div className="h-72">
                {cb.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={courseCompletionData} onClick={handleCourseBarClick}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} />
                      <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                      <YAxis />
                      <Tooltip />
                      <Legend iconSize={12} wrapperStyle={{ paddingTop: 8 }} />
                      <Bar dataKey="Completed" stackId="a" fill="#10b981" radius={[0, 0, 0, 0]} />
                      <Bar dataKey="In Progress" stackId="a" fill="#f59e0b" radius={[0, 0, 0, 0]} />
                      <Bar dataKey="Not Started" stackId="a" fill="#e5e7eb" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <EmptyChart message="No published courses yet" />
                )}
              </div>
            </div>

            <div className="bg-white rounded-xl border border-gray-200 p-6">
              <div className="flex items-center gap-2 mb-4">
                <ArrowTrendingUpIcon className="h-5 w-5 text-indigo-600" />
                <h2 className="font-semibold text-gray-900">Monthly Completion Trend</h2>
              </div>
              <div className="h-72">
                {mt.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={monthlyTrendData}>
                      <CartesianGrid strokeDasharray="3 3" vertical={false} />
                      <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                      <YAxis allowDecimals={false} />
                      <Tooltip />
                      <Area
                        type="monotone"
                        dataKey="completions"
                        name="Course Completions"
                        stroke="#6366f1"
                        fill="rgba(99,102,241,0.1)"
                        strokeWidth={2}
                        dot={{ fill: '#6366f1', r: 5 }}
                        activeDot={{ r: 7 }}
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                ) : (
                  <EmptyChart message="No data yet" />
                )}
              </div>
            </div>
          </div>

          {/* Row 2: Engagement + Assignments + Departments */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {/* Teacher Engagement */}
            <div className="bg-white rounded-xl border border-gray-200 p-6">
              <div className="flex items-center gap-2 mb-4">
                <UserGroupIcon className="h-5 w-5 text-blue-600" />
                <h2 className="font-semibold text-gray-900">Teacher Engagement</h2>
              </div>
              <div className="h-56">
                {hasNonZero(engagementValues) ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={engagementData}
                        cx="50%"
                        cy="50%"
                        innerRadius="55%"
                        outerRadius="80%"
                        paddingAngle={2}
                        dataKey="value"
                      >
                        {engagementData.map((_, index) => (
                          <Cell key={`cell-${index}`} fill={ENGAGEMENT_COLORS[index]} />
                        ))}
                      </Pie>
                      <Tooltip formatter={(value: number, name: string) => [value, name]} />
                    </PieChart>
                  </ResponsiveContainer>
                ) : (
                  <EmptyChart message="No teacher activity data yet" />
                )}
              </div>
              <div className="mt-4 grid grid-cols-1 gap-2 text-xs sm:grid-cols-2">
                <div className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-emerald-500" />Highly Active: {te.highly_active}</div>
                <div className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-blue-500" />Active: {te.active}</div>
                <div className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-amber-500" />Low Activity: {te.low_activity}</div>
                <div className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-red-500" />Inactive: {te.inactive}</div>
              </div>
            </div>

            {/* Assignment Types */}
            <div className="bg-white rounded-xl border border-gray-200 p-6">
              <div className="flex items-center gap-2 mb-4">
                <ClipboardDocumentListIcon className="h-5 w-5 text-amber-600" />
                <h2 className="font-semibold text-gray-900">Assignment Types</h2>
              </div>
              <div className="h-56">
                {hasNonZero(assignmentValues) ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={assignmentData}
                        cx="50%"
                        cy="50%"
                        innerRadius="55%"
                        outerRadius="80%"
                        paddingAngle={2}
                        dataKey="value"
                      >
                        {assignmentData.map((_, index) => (
                          <Cell key={`cell-${index}`} fill={ASSIGNMENT_COLORS[index]} />
                        ))}
                      </Pie>
                      <Tooltip formatter={(value: number, name: string) => [value, name]} />
                    </PieChart>
                  </ResponsiveContainer>
                ) : (
                  <EmptyChart message="No assignments yet" />
                )}
              </div>
              <div className="mt-4 text-center">
                <span className="text-2xl font-bold text-gray-900">{ab.total}</span>
                <span className="text-sm text-gray-500 ml-1">total assignments</span>
              </div>
            </div>

            {/* Department Distribution */}
            <div className="bg-white rounded-xl border border-gray-200 p-6">
              <div className="flex items-center gap-2 mb-4">
                <BuildingLibraryIcon className="h-5 w-5 text-purple-600" />
                <h2 className="font-semibold text-gray-900">Department Distribution</h2>
              </div>
              <div className="h-56">
                {ds.length > 0 ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={deptData} layout="vertical">
                      <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                      <XAxis type="number" allowDecimals={false} />
                      <YAxis dataKey="name" type="category" width={100} tick={{ fontSize: 12 }} />
                      <Tooltip />
                      <Bar dataKey="Teachers" fill="#8b5cf6" radius={[0, 6, 6, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <EmptyChart message="No department data yet" />
                )}
              </div>
            </div>
          </div>

          {/* Row 3: New Charts — Deadline Adherence + Certification Compliance */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <DeadlineAdherenceChart
              onViewDetails={() => switchToReports({ tab: 'COURSE' })}
            />
            <CertComplianceChart
              onViewDetails={() => switchToReports({ tab: 'COURSE' })}
            />
          </div>

          {/* Row 4: New Charts — Approval Trends + Course Effectiveness */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <ApprovalTrendsChart
              onViewDetails={() => switchToReports({ tab: 'ASSIGNMENT' })}
            />
            <CourseEffectivenessChart
              onViewDetails={() => switchToReports({ tab: 'COURSE' })}
            />
          </div>

          {/* Needs Attention - expandable with details */}
          {stats && stats.inactive_teachers > 0 && (
            <div className="bg-amber-50 border border-amber-200 rounded-xl overflow-hidden">
              <button
                type="button"
                onClick={() => setAttentionExpanded(!attentionExpanded)}
                className="w-full flex items-center justify-between p-6 text-left hover:bg-amber-100/50 transition-colors"
              >
                <div className="flex items-start gap-3">
                  <ExclamationTriangleIcon className="h-6 w-6 text-amber-500 flex-shrink-0 mt-0.5" />
                  <div>
                    <h2 className="font-semibold text-amber-900 mb-1">Needs Attention</h2>
                    <p className="text-sm text-amber-700">
                      <span className="font-bold">{stats.inactive_teachers}</span> teacher{stats.inactive_teachers > 1 ? 's have' : ' has'} not started any course.
                    </p>
                  </div>
                </div>
                {attentionExpanded ? <ChevronUpIcon className="h-5 w-5 text-amber-600" /> : <ChevronDownIcon className="h-5 w-5 text-amber-600" />}
              </button>
              {attentionExpanded && stats.inactive_teachers_detail && stats.inactive_teachers_detail.length > 0 && (
                <div className="border-t border-amber-200 px-6 pb-6 pt-4">
                  <div className="mb-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <h3 className="flex items-center gap-2 text-sm font-medium text-amber-900">
                      <UserGroupIcon className="h-4 w-4" />
                      Teachers not started ({stats.inactive_teachers_detail.length})
                    </h3>
                    <button
                      type="button"
                      disabled={reminderMutation.isPending || stats.inactive_teachers_detail.every((t) => sentTeacherIds.has(t.id))}
                      onClick={() => reminderMutation.mutate(stats.inactive_teachers_detail!.map((t) => t.id))}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-amber-600 text-white hover:bg-amber-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                    >
                      <BellAlertIcon className="h-3.5 w-3.5" />
                      {reminderMutation.isPending ? 'Sending...' : 'Send Reminder to All'}
                    </button>
                  </div>
                  <div className="overflow-x-auto rounded-lg border border-amber-100 bg-white">
                    <table className="min-w-full text-sm">
                      <thead className="bg-amber-50/50">
                        <tr>
                          <th className="px-4 py-2 text-left text-xs font-medium text-amber-700">Name</th>
                          <th className="px-4 py-2 text-left text-xs font-medium text-amber-700">Email</th>
                          <th className="px-4 py-2 text-right text-xs font-medium text-amber-700">Action</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-amber-50">
                        {stats.inactive_teachers_detail.map((t) => (
                          <tr key={t.id} className="hover:bg-amber-50/30">
                            <td className="px-4 py-2 font-medium text-gray-900">{t.name}</td>
                            <td className="px-4 py-2 text-gray-600">{t.email}</td>
                            <td className="px-4 py-2 text-right">
                              {sentTeacherIds.has(t.id) ? (
                                <span className="text-xs text-emerald-600 font-medium">Sent</span>
                              ) : (
                                <button
                                  type="button"
                                  disabled={reminderMutation.isPending}
                                  onClick={() => reminderMutation.mutate([t.id])}
                                  className="inline-flex items-center gap-1 text-amber-700 hover:text-amber-800 text-xs font-medium disabled:opacity-50"
                                >
                                  <BellAlertIcon className="h-3.5 w-3.5" />
                                  Send Reminder
                                </button>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
};
