// src/pages/admin/DashboardPage.tsx
//
// Admin dashboard with deep-linked metrics → analytics drill-down.
// Row 1: 4 stat cards + enrollment trend + completion stats
// Row 2: Weekly activity chart + side-by-side teacher/student engagement donuts
// Row 3: Student performance snapshot
// Row 4: Recent activity + top performers
// Row 5: Courses table

import React, { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  Users,
  BookOpen,
  GraduationCap,
  Award,
  ArrowUpRight,
  ArrowDownRight,
  MoreHorizontal,
  Plus,
  ChevronRight,
  BarChart3,
  Target,
  CheckCircle2,
  Clock,
} from 'lucide-react';
import { cn } from '../../design-system';
import { adminService } from '../../services/adminService';
import type { TenantStats, TenantAnalytics } from '../../services/adminService';
import { useTenantStore } from '../../stores/tenantStore';
import { useAuthStore } from '../../stores/authStore';
import { usePageTitle } from '../../hooks/usePageTitle';
import { PlanBadge } from '../../components/dashboard/PlanBadge';

// ── Helpers ──────────────────────────────────────────────────────────

/** Navigate to analytics with deep-link params */
function analyticsLink(params: Record<string, string>): string {
  const sp = new URLSearchParams(params);
  return `/admin/analytics?${sp.toString()}`;
}

// ── Count-up animation hook ──────────────────────────────────────────

function useCountUp(target: number, duration = 800): number {
  const [count, setCount] = useState(0);
  const prev = useRef(0);

  useEffect(() => {
    if (target === prev.current) return;
    const start = prev.current;
    const diff = target - start;
    const startTime = performance.now();

    function animate(now: number) {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setCount(Math.round(start + diff * eased));
      if (progress < 1) requestAnimationFrame(animate);
    }

    requestAnimationFrame(animate);
    prev.current = target;
  }, [target, duration]);

  return count;
}

// ── Shimmer Skeleton ─────────────────────────────────────────────────

function Shimmer({ className }: { className: string }) {
  return <div className={cn('animate-pulse bg-gray-200 rounded-lg', className)} />;
}

function DashboardSkeleton() {
  return (
    <div className="space-y-6 pb-12">
      <div className="flex justify-between items-end">
        <div><Shimmer className="h-8 w-64 mb-2" /><Shimmer className="h-4 w-40" /></div>
        <Shimmer className="h-10 w-32 rounded-lg" />
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[1,2,3,4].map(i => <Shimmer key={i} className="h-28 rounded-2xl" />)}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Shimmer className="h-56 rounded-2xl" /><Shimmer className="h-56 rounded-2xl" />
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Shimmer className="lg:col-span-2 h-72 rounded-2xl" /><Shimmer className="h-72 rounded-2xl" />
      </div>
      <Shimmer className="h-80 rounded-2xl" />
    </div>
  );
}

// ── Mini Bar Chart ───────────────────────────────────────────────────

function MiniBarChart({ data, color }: { data: number[]; color: string }) {
  const max = Math.max(...data, 1);
  return (
    <div className="flex items-end gap-[3px] h-16">
      {data.map((v, i) => {
        const pct = (v / max) * 100;
        return (
          <div
            key={i}
            className="flex-1 rounded-sm transition-all duration-500"
            style={{ height: `${Math.max(pct, 6)}%`, backgroundColor: color, opacity: 0.6 + (i / data.length) * 0.4 }}
          />
        );
      })}
    </div>
  );
}

// ── Area Chart (SVG) ─────────────────────────────────────────────────

function AreaChart({ data, labels, color, height = 200 }: {
  data: number[];
  labels: string[];
  color: string;
  height?: number;
}) {
  if (data.length < 2) return null;

  const width = 600;
  const padT = 20, padB = 30, padL = 40, padR = 20;
  const chartW = width - padL - padR;
  const chartH = height - padT - padB;
  const max = Math.max(...data, 1);
  const gridLines = 4;

  const points = data.map((v, i) => ({
    x: padL + (i / (data.length - 1)) * chartW,
    y: padT + chartH - (v / max) * chartH,
  }));

  const linePath = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ');
  const areaPath = `${linePath} L${points[points.length-1].x},${padT + chartH} L${points[0].x},${padT + chartH} Z`;

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full" preserveAspectRatio="xMidYMid meet">
      <defs>
        <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.25" />
          <stop offset="100%" stopColor={color} stopOpacity="0.02" />
        </linearGradient>
      </defs>
      {Array.from({ length: gridLines + 1 }).map((_, i) => {
        const y = padT + (i / gridLines) * chartH;
        const val = Math.round(max - (i / gridLines) * max);
        return (
          <g key={i}>
            <line x1={padL} y1={y} x2={padL + chartW} y2={y} stroke="#f1f5f9" strokeWidth="1" />
            <text x={padL - 8} y={y + 4} textAnchor="end" className="fill-gray-400" fontSize="10">{val}</text>
          </g>
        );
      })}
      <path d={areaPath} fill="url(#areaGrad)" />
      <path d={linePath} fill="none" stroke={color} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
      {points.map((p, i) => (
        <circle key={i} cx={p.x} cy={p.y} r="3.5" fill="white" stroke={color} strokeWidth="2" />
      ))}
      {labels.map((label, i) => {
        const x = padL + (i / (labels.length - 1)) * chartW;
        return (
          <text key={i} x={x} y={height - 6} textAnchor="middle" className="fill-gray-400" fontSize="10">{label}</text>
        );
      })}
    </svg>
  );
}

// ── Donut Chart (SVG) ────────────────────────────────────────────────

function DonutChart({ segments, size = 150, label }: {
  segments: Array<{ label: string; value: number; color: string }>;
  size?: number;
  label?: string;
}) {
  const total = segments.reduce((s, seg) => s + seg.value, 0) || 1;
  const radius = (size - 20) / 2;
  const cx = size / 2;
  const cy = size / 2;
  const circumference = 2 * Math.PI * radius;
  let accumulated = 0;

  return (
    <div className="flex flex-col items-center gap-3">
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} className="rotate-[-90deg]">
          {segments.map((seg, i) => {
            const pct = seg.value / total;
            const dashLen = pct * circumference;
            const dashGap = circumference - dashLen;
            const offset = accumulated * circumference;
            accumulated += pct;
            return (
              <circle
                key={i} cx={cx} cy={cy} r={radius} fill="none"
                stroke={seg.color} strokeWidth="18"
                strokeDasharray={`${dashLen} ${dashGap}`}
                strokeDashoffset={-offset}
                className="transition-all duration-700"
              />
            );
          })}
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-xl font-bold text-gray-900">{total}</span>
          {label && <span className="text-[10px] text-gray-500">{label}</span>}
        </div>
      </div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
        {segments.map((seg, i) => (
          <div key={i} className="flex items-center gap-1.5">
            <div className="h-2 w-2 rounded-full flex-shrink-0" style={{ backgroundColor: seg.color }} />
            <span className="text-[11px] text-gray-600">{seg.label}</span>
            <span className="text-[11px] font-semibold text-gray-900 ml-auto">{seg.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Stacked Bar Comparison ───────────────────────────────────────────

function CompletionComparison({ completionPct, inProgressPct }: { completionPct: number; inProgressPct: number }) {
  return (
    <div className="space-y-3">
      <div>
        <div className="flex items-center justify-between mb-1">
          <span className="text-xs text-gray-600">Completed</span>
          <span className="text-xs font-bold text-gray-900">{completionPct}%</span>
        </div>
        <div className="h-2.5 bg-gray-100 rounded-full overflow-hidden">
          <div className="h-full bg-emerald-500 rounded-full transition-all duration-700" style={{ width: `${completionPct}%` }} />
        </div>
      </div>
      <div>
        <div className="flex items-center justify-between mb-1">
          <span className="text-xs text-gray-600">In Progress</span>
          <span className="text-xs font-bold text-gray-900">{inProgressPct}%</span>
        </div>
        <div className="h-2.5 bg-gray-100 rounded-full overflow-hidden">
          <div className="h-full bg-blue-500 rounded-full transition-all duration-700" style={{ width: `${inProgressPct}%` }} />
        </div>
      </div>
    </div>
  );
}

// ── Progress Bar ─────────────────────────────────────────────────────

function ProgressBar({ value }: { value: number }) {
  const color = value >= 80 ? 'bg-emerald-500' : value >= 50 ? 'bg-blue-500' : value >= 25 ? 'bg-amber-500' : 'bg-gray-300';
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
        <div className={cn('h-full rounded-full transition-all duration-500', color)} style={{ width: `${value}%` }} />
      </div>
      <span className="text-xs font-medium text-gray-600 w-8 text-right">{value}%</span>
    </div>
  );
}

// ── Avatar Stack ─────────────────────────────────────────────────────

function AvatarStack({ count, max = 4 }: { count: number; max?: number }) {
  const COLORS = ['bg-blue-500', 'bg-emerald-500', 'bg-violet-500', 'bg-amber-500', 'bg-rose-500'];
  const shown = Math.min(count, max);
  const extra = count - shown;
  return (
    <div className="flex items-center -space-x-2">
      {Array.from({ length: shown }).map((_, i) => (
        <div key={i} className={cn('h-7 w-7 rounded-full border-2 border-white flex items-center justify-center text-[10px] font-bold text-white', COLORS[i % COLORS.length])}>
          {String.fromCharCode(65 + i)}
        </div>
      ))}
      {extra > 0 && (
        <div className="h-7 w-7 rounded-full border-2 border-white bg-gray-200 flex items-center justify-center text-[10px] font-medium text-gray-600">
          +{extra}
        </div>
      )}
    </div>
  );
}

// ── Metric Pill (for student snapshot row) ────────────────────────────

function MetricPill({ icon: Icon, label, value, sub, color, onClick }: {
  icon: React.ElementType;
  label: string;
  value: string | number;
  sub?: string;
  color: string;
  onClick?: () => void;
}) {
  return (
    <div
      onClick={onClick}
      className={cn(
        'bg-white rounded-xl border border-gray-200 p-4 flex items-center gap-3 transition-all',
        onClick && 'cursor-pointer hover:shadow-md hover:-translate-y-0.5',
      )}
    >
      <div className={cn('h-10 w-10 rounded-lg flex items-center justify-center flex-shrink-0', color)}>
        <Icon className="h-5 w-5 text-white" />
      </div>
      <div>
        <p className="text-lg font-bold text-gray-900 leading-tight">{value}</p>
        <p className="text-xs text-gray-500">{label}</p>
        {sub && <p className="text-[10px] text-gray-400">{sub}</p>}
      </div>
    </div>
  );
}

// ── Main Component ────────────────────────────────────────────────────

export const DashboardPage: React.FC = () => {
  usePageTitle('Dashboard');
  const navigate = useNavigate();
  const { theme } = useTenantStore();
  const { user } = useAuthStore();

  const { data: stats, isLoading: statsLoading } = useQuery<TenantStats>({
    queryKey: ['adminDashboardStats'],
    queryFn: adminService.getTenantStats,
    refetchInterval: 30000,
  });

  const { data: analytics, isLoading: analyticsLoading } = useQuery<TenantAnalytics>({
    queryKey: ['adminDashboardAnalytics'],
    queryFn: () => adminService.getTenantAnalytics({ months: 6 }),
    refetchInterval: 60000,
  });

  const isLoading = statsLoading || analyticsLoading;
  const firstName = user?.first_name || 'Admin';

  // Animated counters
  const teacherCount = useCountUp(stats?.total_teachers ?? 0);
  const courseCount = useCountUp(stats?.published_courses ?? 0);
  const studentCount = useCountUp(stats?.total_students ?? 0);
  const certCount = useCountUp(stats?.cert_compliance?.fully_compliant ?? 0);

  // Weekly trend
  const weeklyData = (stats?.weekly_trend ?? []).map(w => w.completions);
  const totalWeeklyCompletions = weeklyData.reduce((s, v) => s + v, 0);

  // Completion %
  const totalEnrolled = (stats?.course_completions ?? 0) + (stats?.courses_in_progress ?? 0) + 1;
  const completionPct = stats?.avg_completion_pct ?? 0;
  const inProgressPct = totalEnrolled > 0
    ? Math.round(((stats?.courses_in_progress ?? 0) / totalEnrolled) * 100)
    : 0;

  // Area chart
  const areaData = (stats?.weekly_trend ?? []).map(w => w.completions);
  const areaLabels = (stats?.weekly_trend ?? []).map(w => w.week);

  // Engagement donuts
  const te = analytics?.teacher_engagement;
  const teacherDonut = te ? [
    { label: 'Highly Active', value: te.highly_active, color: '#10b981' },
    { label: 'Active', value: te.active, color: '#3b82f6' },
    { label: 'Low Activity', value: te.low_activity, color: '#f59e0b' },
    { label: 'Inactive', value: te.inactive, color: '#ef4444' },
  ] : [];

  const se = analytics?.student_engagement;
  const studentDonut = se ? [
    { label: 'Highly Active', value: se.highly_active, color: '#10b981' },
    { label: 'Active', value: se.active, color: '#3b82f6' },
    { label: 'Low Activity', value: se.low_activity, color: '#f59e0b' },
    { label: 'Inactive', value: se.inactive, color: '#ef4444' },
  ] : [];

  // Student data
  const sp = analytics?.student_course_progress;
  const sPerf = analytics?.student_performance;
  const sOverview = analytics?.student_overview;

  // Course breakdown
  const courses = analytics?.course_breakdown ?? [];

  if (isLoading) return <DashboardSkeleton />;

  return (
    <div className="space-y-6 pb-12">
      {/* ─── Header ─────────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-3 flex-wrap">
            <h1 className="text-2xl font-bold text-gray-900">Welcome back, {firstName}</h1>
            <PlanBadge />
          </div>
          <p className="mt-1 text-sm text-gray-500">Here's what's happening at {theme.name} today</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => navigate('/admin/courses/new')}
            className="inline-flex items-center gap-2 px-4 py-2.5 bg-gray-900 text-white text-sm font-medium rounded-xl hover:bg-gray-800 transition-colors shadow-sm"
          >
            <Plus className="h-4 w-4" /> New Course
          </button>
        </div>
      </div>

      {/* ─── Row 1: Stat Cards + Trend + Completion ─────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
        <div className="lg:col-span-6 grid grid-cols-2 gap-4">
          <StatCard
            label="Total Teachers" value={teacherCount} icon={Users}
            iconBg="bg-rose-100" iconColor="text-rose-600"
            trend={stats?.active_teachers ? `${stats.active_teachers} active` : undefined}
            trendUp={true}
            onClick={() => navigate(analyticsLink({ view: 'charts', focus: 'teachers' }))}
          />
          <StatCard
            label="Active Courses" value={courseCount} icon={BookOpen}
            iconBg="bg-blue-100" iconColor="text-blue-600"
            trend={`${stats?.courses_in_progress ?? 0} in progress`}
            trendUp={true}
            onClick={() => navigate(analyticsLink({ view: 'reports', tab: 'COURSE' }))}
          />
          <StatCard
            label="Total Students" value={studentCount} icon={GraduationCap}
            iconBg="bg-emerald-100" iconColor="text-emerald-600"
            trend={sOverview ? `${sOverview.active_30d} active (30d)` : 'enrolled'}
            trendUp={true}
            onClick={() => navigate(analyticsLink({ view: 'charts', focus: 'students' }))}
          />
          <StatCard
            label="Certifications" value={certCount} icon={Award}
            iconBg="bg-amber-100" iconColor="text-amber-600"
            trend={`${stats?.cert_compliance?.compliance_pct ?? 0}% compliant`}
            trendUp={(stats?.cert_compliance?.compliance_pct ?? 0) >= 50}
            onClick={() => navigate('/admin/certifications')}
          />
        </div>

        {/* Course Enrollment Trend — deep link */}
        <div className="lg:col-span-3">
          <div
            className="h-full bg-white rounded-2xl border border-gray-200 p-5 flex flex-col cursor-pointer hover:shadow-md transition-shadow"
            onClick={() => navigate(analyticsLink({ view: 'charts' }))}
          >
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">Enrollment Trend</p>
            <div className="flex items-baseline gap-2 mt-2">
              <span className="text-2xl font-bold text-gray-900">{totalWeeklyCompletions}</span>
              <span className="text-xs font-medium text-emerald-600 flex items-center gap-0.5">
                <ArrowUpRight className="h-3 w-3" /> Last 8 weeks
              </span>
            </div>
            <div className="mt-auto pt-3">
              <MiniBarChart data={weeklyData.length > 0 ? weeklyData : [0]} color="#6366f1" />
            </div>
          </div>
        </div>

        {/* Course Completion Stats — deep link */}
        <div className="lg:col-span-3">
          <div
            className="h-full bg-white rounded-2xl border border-gray-200 p-5 flex flex-col cursor-pointer hover:shadow-md transition-shadow"
            onClick={() => navigate(analyticsLink({ view: 'reports', tab: 'COURSE' }))}
          >
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">Completion Stats</p>
            <div className="flex items-baseline gap-2 mt-2">
              <span className="text-2xl font-bold text-gray-900">{completionPct}%</span>
              <span className="text-xs text-gray-500">avg completion</span>
            </div>
            <div className="mt-auto pt-3">
              <CompletionComparison completionPct={completionPct} inProgressPct={inProgressPct} />
            </div>
          </div>
        </div>
      </div>

      {/* ─── Row 2: Area Chart + Dual Engagement Donuts ─────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="lg:col-span-6 bg-white rounded-2xl border border-gray-200 p-6">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="text-base font-semibold text-gray-900">Weekly Activity</h3>
              <p className="text-xs text-gray-500 mt-0.5">Content completions over the last 8 weeks</p>
            </div>
            <button
              onClick={() => navigate(analyticsLink({ view: 'charts' }))}
              className="text-xs font-medium text-indigo-600 hover:text-indigo-800 flex items-center gap-1"
            >
              Details <ChevronRight className="h-3 w-3" />
            </button>
          </div>
          {areaData.length >= 2 ? (
            <AreaChart data={areaData} labels={areaLabels} color="#6366f1" height={200} />
          ) : (
            <div className="h-48 flex items-center justify-center text-sm text-gray-400">Not enough data</div>
          )}
        </div>

        {/* Teacher Engagement — deep link */}
        <div
          className="lg:col-span-3 bg-white rounded-2xl border border-gray-200 p-5 cursor-pointer hover:shadow-md transition-shadow"
          onClick={() => navigate(analyticsLink({ view: 'charts', focus: 'teachers' }))}
        >
          <h3 className="text-sm font-semibold text-gray-900 mb-1">Teacher Engagement</h3>
          <p className="text-[11px] text-gray-500 mb-3">Activity distribution</p>
          {teacherDonut.length > 0 ? (
            <DonutChart segments={teacherDonut} size={140} label="Teachers" />
          ) : (
            <div className="h-40 flex items-center justify-center text-sm text-gray-400">No data</div>
          )}
        </div>

        {/* Student Engagement — deep link */}
        <div
          className="lg:col-span-3 bg-white rounded-2xl border border-gray-200 p-5 cursor-pointer hover:shadow-md transition-shadow"
          onClick={() => navigate(analyticsLink({ view: 'charts', focus: 'students' }))}
        >
          <h3 className="text-sm font-semibold text-gray-900 mb-1">Student Engagement</h3>
          <p className="text-[11px] text-gray-500 mb-3">Activity distribution</p>
          {studentDonut.length > 0 ? (
            <DonutChart segments={studentDonut} size={140} label="Students" />
          ) : (
            <div className="h-40 flex items-center justify-center text-sm text-gray-400">No data</div>
          )}
        </div>
      </div>

      {/* ─── Row 3: Student Performance Snapshot ────────────────── */}
      {sOverview && sOverview.total > 0 && (
        <div>
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-base font-semibold text-gray-900">Student Performance</h3>
            <button
              onClick={() => navigate(analyticsLink({ view: 'charts', focus: 'students' }))}
              className="text-xs font-medium text-indigo-600 hover:text-indigo-800 flex items-center gap-1"
            >
              Full Analytics <ChevronRight className="h-3 w-3" />
            </button>
          </div>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <MetricPill
              icon={BookOpen} label="Course Completion" color="bg-emerald-500"
              value={`${sp?.avg_completion_pct ?? 0}%`}
              sub={`${sp?.completed ?? 0} of ${sp?.total_enrollments ?? 0} completed`}
              onClick={() => navigate(analyticsLink({ view: 'reports', tab: 'COURSE', role: 'students' }))}
            />
            <MetricPill
              icon={BarChart3} label="Avg Score" color="bg-blue-500"
              value={`${sPerf?.avg_score_pct ?? 0}%`}
              sub={`${sPerf?.graded ?? 0} graded`}
              onClick={() => navigate(analyticsLink({ view: 'reports', tab: 'ASSIGNMENT', role: 'students' }))}
            />
            <MetricPill
              icon={Target} label="Pass Rate" color="bg-violet-500"
              value={`${sPerf?.pass_rate_pct ?? 0}%`}
              sub={`${sPerf?.total_submissions ?? 0} submissions`}
              onClick={() => navigate(analyticsLink({ view: 'reports', tab: 'ASSIGNMENT', role: 'students' }))}
            />
            <MetricPill
              icon={Clock} label="Inactive Students" color={(sOverview?.inactive ?? 0) > 0 ? 'bg-red-500' : 'bg-gray-400'}
              value={sOverview?.inactive ?? 0}
              sub="No login in 30 days"
              onClick={() => navigate('/admin/students')}
            />
          </div>
        </div>
      )}

      {/* ─── Row 4: Recent Activity + Top Performers ────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent Activity */}
        <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
            <h3 className="text-base font-semibold text-gray-900">Recent Activity</h3>
            <button onClick={() => navigate(analyticsLink({ view: 'charts' }))} className="text-xs font-medium text-indigo-600 hover:text-indigo-800">
              View All
            </button>
          </div>
          <div className="divide-y divide-gray-50 max-h-72 overflow-y-auto">
            {!stats?.recent_activity?.length ? (
              <div className="p-10 text-center text-sm text-gray-400">No recent activity</div>
            ) : (
              stats.recent_activity.slice(0, 6).map((item, i) => (
                <div key={i} className="px-6 py-3.5 flex items-center gap-3 hover:bg-gray-50/50 transition-colors">
                  <div className="h-9 w-9 rounded-full bg-gradient-to-br from-indigo-500 to-violet-500 flex items-center justify-center text-white text-xs font-bold flex-shrink-0">
                    {item.teacher_name.split(' ').map(n => n[0]).join('').slice(0, 2)}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-gray-800 truncate">{item.teacher_name}</p>
                    <p className="text-xs text-gray-500 truncate">Completed {item.content_title || item.course_title}</p>
                  </div>
                  <span className="text-[11px] text-gray-400 flex-shrink-0">{formatRelativeTime(item.completed_at)}</span>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Top Performers */}
        <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
            <h3 className="text-base font-semibold text-gray-900">Top Performers</h3>
            <button onClick={() => navigate(analyticsLink({ view: 'charts', focus: 'teachers' }))} className="text-xs font-medium text-indigo-600 hover:text-indigo-800">
              View All
            </button>
          </div>
          <div className="divide-y divide-gray-50 max-h-72 overflow-y-auto">
            {!stats?.top_teachers?.length ? (
              <div className="p-10 text-center text-sm text-gray-400">No data yet</div>
            ) : (
              stats.top_teachers.map((t, i) => {
                const totalCourses = stats.total_courses || 1;
                const pct = Math.round((t.completed_courses / totalCourses) * 100);
                return (
                  <div key={t.name} className="px-6 py-3.5 flex items-center gap-3 hover:bg-gray-50/50 transition-colors">
                    <div className={cn(
                      'w-9 h-9 rounded-full flex items-center justify-center text-sm font-bold flex-shrink-0',
                      i === 0 ? 'bg-gradient-to-br from-amber-400 to-amber-600 text-white' :
                      i === 1 ? 'bg-gray-200 text-gray-600' :
                      i === 2 ? 'bg-amber-100 text-amber-700' :
                      'bg-gray-100 text-gray-500',
                    )}>
                      {i + 1}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-gray-800 truncate">{t.name}</p>
                      <p className="text-xs text-gray-500">{t.completed_courses} courses completed</p>
                    </div>
                    <div className="flex-shrink-0 w-20">
                      <ProgressBar value={Math.min(pct, 100)} />
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>

      {/* ─── Row 5: Courses Table ───────────────────────────────── */}
      {courses.length > 0 && (
        <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
            <h3 className="text-base font-semibold text-gray-900">Courses Overview</h3>
            <button
              onClick={() => navigate(analyticsLink({ view: 'reports', tab: 'COURSE' }))}
              className="text-xs font-medium text-indigo-600 hover:text-indigo-800 flex items-center gap-1"
            >
              Detailed Reports <ChevronRight className="h-3 w-3" />
            </button>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100">
                  <th className="text-left text-xs font-medium text-gray-500 uppercase tracking-wider px-6 py-3">Course</th>
                  <th className="text-left text-xs font-medium text-gray-500 uppercase tracking-wider px-4 py-3">Enrolled</th>
                  <th className="text-left text-xs font-medium text-gray-500 uppercase tracking-wider px-4 py-3 w-44">Completion</th>
                  <th className="text-center text-xs font-medium text-gray-500 uppercase tracking-wider px-4 py-3">Status</th>
                  <th className="text-center text-xs font-medium text-gray-500 uppercase tracking-wider px-4 py-3 w-16"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {courses.slice(0, 8).map((course) => {
                  const total = course.assigned || 1;
                  const compPct = Math.round((course.completed / total) * 100);
                  const hasActivity = course.completed > 0 || course.in_progress > 0;
                  return (
                    <tr
                      key={course.course_id}
                      className="hover:bg-gray-50/50 transition-colors cursor-pointer"
                      onClick={() => navigate(analyticsLink({ view: 'reports', tab: 'COURSE', course_id: course.course_id }))}
                    >
                      <td className="px-6 py-3.5">
                        <div className="flex items-center gap-3">
                          <div className="h-9 w-9 rounded-lg bg-indigo-50 flex items-center justify-center flex-shrink-0">
                            <BookOpen className="h-4 w-4 text-indigo-600" />
                          </div>
                          <span className="font-medium text-gray-800 truncate max-w-[280px]">{course.title}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3.5">
                        <div className="flex items-center gap-2">
                          <AvatarStack count={course.assigned} max={3} />
                          <span className="text-xs text-gray-500">{course.assigned}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3.5"><ProgressBar value={compPct} /></td>
                      <td className="px-4 py-3.5 text-center">
                        <span className={cn(
                          'inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium',
                          hasActivity ? 'bg-emerald-50 text-emerald-700' : 'bg-gray-100 text-gray-600',
                        )}>
                          {hasActivity ? 'Active' : 'No Activity'}
                        </span>
                      </td>
                      <td className="px-4 py-3.5 text-center">
                        <button
                          onClick={(e) => { e.stopPropagation(); navigate(`/admin/courses/${course.course_id}`); }}
                          className="p-1.5 rounded-lg hover:bg-gray-100 transition-colors text-gray-400 hover:text-gray-600"
                        >
                          <MoreHorizontal className="h-4 w-4" />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          {courses.length > 8 && (
            <div className="px-6 py-3 border-t border-gray-100 text-center">
              <button onClick={() => navigate(analyticsLink({ view: 'reports', tab: 'COURSE' }))} className="text-xs font-medium text-indigo-600 hover:text-indigo-800">
                View all {courses.length} courses
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

// ── Stat Card ─────────────────────────────────────────────────────────

function StatCard({ label, value, icon: Icon, iconBg, iconColor, trend, trendUp, onClick }: {
  label: string;
  value: number | string;
  icon: React.ElementType;
  iconBg: string;
  iconColor: string;
  trend?: string;
  trendUp?: boolean;
  onClick?: () => void;
}) {
  return (
    <div
      onClick={onClick}
      className={cn(
        'bg-white rounded-2xl border border-gray-200 p-5 transition-all',
        onClick && 'cursor-pointer hover:shadow-md hover:-translate-y-0.5',
      )}
    >
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">{label}</p>
          <p className="text-2xl font-bold text-gray-900 mt-1">{typeof value === 'number' ? value.toLocaleString() : value}</p>
        </div>
        <div className={cn('h-12 w-12 rounded-full flex items-center justify-center', iconBg)}>
          <Icon className={cn('h-6 w-6', iconColor)} />
        </div>
      </div>
      {trend && (
        <div className="mt-3 flex items-center gap-1">
          {trendUp ? <ArrowUpRight className="h-3.5 w-3.5 text-emerald-500" /> : <ArrowDownRight className="h-3.5 w-3.5 text-red-500" />}
          <span className={cn('text-xs font-medium', trendUp ? 'text-emerald-600' : 'text-red-600')}>{trend}</span>
        </div>
      )}
    </div>
  );
}

// ── Relative Time Formatter ───────────────────────────────────────────

function formatRelativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'Just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
}
