// src/pages/parent/ParentDashboardPage.tsx
//
// Main parent dashboard showing child overview: courses, assignments,
// attendance, study time, and recent activity.

import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  LogOut, ChevronDown, BookOpen, ClipboardList, Clock,
  Activity, Loader2, AlertCircle, User,
} from 'lucide-react';
import { useTenantStore } from '../../stores/tenantStore';
import { useParentStore } from '../../stores/parentStore';
import { parentService } from '../../services/parentService';
import { cn } from '../../lib/utils';
import type { ParentChildOverview, ParentAssignment } from '../../types/parent';

// ─── Helpers ─────────────────────────────────────────────────────────────────

function relativeTime(timestamp: string): string {
  const now = Date.now();
  const then = new Date(timestamp).getTime();
  const diffMs = now - then;
  const diffMin = Math.floor(diffMs / 60_000);
  if (diffMin < 1) return 'Just now';
  if (diffMin < 60) return `${diffMin} minute${diffMin !== 1 ? 's' : ''} ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr} hour${diffHr !== 1 ? 's' : ''} ago`;
  const diffDays = Math.floor(diffHr / 24);
  if (diffDays === 1) return 'Yesterday';
  if (diffDays < 7) return `${diffDays} days ago`;
  const diffWeeks = Math.floor(diffDays / 7);
  if (diffWeeks < 4) return `${diffWeeks} week${diffWeeks !== 1 ? 's' : ''} ago`;
  return new Date(timestamp).toLocaleDateString();
}

function progressColor(pct: number): string {
  if (pct >= 80) return 'bg-green-500';
  if (pct >= 50) return 'bg-yellow-500';
  return 'bg-red-500';
}

const STATUS_STYLES: Record<string, string> = {
  NOT_SUBMITTED: 'bg-yellow-100 text-yellow-700',
  SUBMITTED: 'bg-blue-100 text-blue-700',
  GRADED: 'bg-green-100 text-green-700',
  LATE: 'bg-red-100 text-red-700',
  NOT_STARTED: 'bg-gray-100 text-gray-500',
  IN_PROGRESS: 'bg-blue-100 text-blue-700',
  COMPLETED: 'bg-green-100 text-green-700',
};

// ─── Component ──────────────────────────────────────────────────────────────

export function ParentDashboardPage() {
  const { theme } = useTenantStore();
  const navigate = useNavigate();
  const {
    parentEmail,
    children,
    selectedChildId,
    setSelectedChild,
    clearSession,
  } = useParentStore();

  const tenantName = theme?.name || 'LearnPuddle';
  const tenantInitial = tenantName.charAt(0).toUpperCase();

  const selectedChild = children.find((c) => c.id === selectedChildId) || children[0];

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Top bar */}
      <header className="bg-white border-b border-gray-200 sticky top-0 z-30">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            {/* Left: logo + name */}
            <div className="flex items-center gap-3">
              {theme?.logo ? (
                <img
                  src={theme.logo}
                  alt={tenantName}
                  className="h-8 w-8 rounded-full object-cover"
                />
              ) : (
                <div className="h-8 w-8 rounded-full bg-gradient-to-br from-indigo-600 to-indigo-500 flex items-center justify-center shadow-sm">
                  <span className="text-white font-bold text-sm">{tenantInitial}</span>
                </div>
              )}
              <div>
                <p className="text-sm font-semibold text-gray-900">{tenantName}</p>
                <p className="text-[11px] text-gray-400">Parent Portal</p>
              </div>
            </div>

            {/* Right: child selector + email + logout */}
            <div className="flex items-center gap-4">
              {children.length > 1 && (
                <div className="relative">
                  <select
                    value={selectedChildId || ''}
                    onChange={(e) => setSelectedChild(e.target.value)}
                    className="appearance-none bg-gray-50 border border-gray-200 rounded-lg pl-3 pr-8 py-1.5 text-sm font-medium text-gray-700 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 cursor-pointer"
                  >
                    {children.map((child) => (
                      <option key={child.id} value={child.id}>
                        {child.first_name} {child.last_name}
                      </option>
                    ))}
                  </select>
                  <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400 pointer-events-none" />
                </div>
              )}
              {parentEmail && (
                <span className="hidden sm:block text-xs text-gray-400 truncate max-w-[180px]">
                  {parentEmail}
                </span>
              )}
              <button
                onClick={() => {
                  parentService.logout().catch(() => {});
                  clearSession();
                  navigate('/parent', { replace: true });
                }}
                className="p-2 rounded-lg text-gray-400 hover:text-red-500 hover:bg-red-50 transition-colors"
                title="Logout"
              >
                <LogOut className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {selectedChild ? (
          <DashboardContent childId={selectedChild.id} child={selectedChild} />
        ) : (
          <div className="text-center py-16">
            <AlertCircle className="h-8 w-8 text-gray-400 mx-auto mb-3" />
            <p className="text-sm text-gray-500">No children linked to your account.</p>
          </div>
        )}
      </main>
    </div>
  );
}

// ─── Dashboard Content ───────────────────────────────────────────────────────

function DashboardContent({
  childId,
  child,
}: {
  childId: string;
  child: { first_name: string; last_name: string; grade_level?: string; section?: string };
}) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['parent', 'child-overview', childId],
    queryFn: () => parentService.getChildOverview(childId),
    enabled: !!childId,
  });

  if (isLoading) {
    return (
      <div className="flex justify-center py-16">
        <Loader2 className="h-8 w-8 text-indigo-500 animate-spin" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="text-center py-16">
        <AlertCircle className="h-8 w-8 text-red-400 mx-auto mb-3" />
        <p className="text-sm text-gray-500">
          Failed to load data. Please try refreshing the page.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Student Info Card */}
      <StudentInfoCard
        firstName={child.first_name}
        lastName={child.last_name}
        gradeLevel={child.grade_level}
        section={child.section}
      />

      {/* Two-column grid for cards */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <CourseProgressCard courses={data.courses} />
        <AssignmentsCard assignments={data.assignments} />
        <AttendanceCard attendance={data.attendance} />
        <StudyTimeCard studyTime={data.study_time} />
      </div>

      {/* Full-width recent activity */}
      <RecentActivityCard activities={data.recent_activity} />
    </div>
  );
}

// ─── Student Info Card ──────────────────────────────────────────────────────

function StudentInfoCard({
  firstName,
  lastName,
  gradeLevel,
  section,
}: {
  firstName: string;
  lastName: string;
  gradeLevel?: string;
  section?: string;
}) {
  const initials = `${firstName.charAt(0)}${lastName.charAt(0)}`.toUpperCase();

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
      <div className="flex items-center gap-4">
        <div className="h-14 w-14 rounded-full bg-gradient-to-br from-indigo-100 to-indigo-50 flex items-center justify-center ring-2 ring-indigo-100 flex-shrink-0">
          <span className="text-indigo-600 font-bold text-lg">{initials}</span>
        </div>
        <div>
          <h2 className="text-lg font-bold text-gray-900">
            {firstName} {lastName}
          </h2>
          <div className="flex items-center gap-2 mt-0.5">
            {gradeLevel && (
              <span className="text-xs font-medium text-gray-500 bg-gray-100 px-2 py-0.5 rounded">
                {gradeLevel}
              </span>
            )}
            {section && (
              <span className="text-xs font-medium text-gray-500 bg-gray-100 px-2 py-0.5 rounded">
                Section {section}
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Course Progress Card ───────────────────────────────────────────────────

function CourseProgressCard({
  courses,
}: {
  courses: ParentChildOverview['courses'];
}) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
      <div className="flex items-center gap-2 mb-4">
        <BookOpen className="h-4 w-4 text-indigo-500" />
        <h3 className="text-sm font-semibold text-gray-900">Course Progress</h3>
      </div>
      {courses.length === 0 ? (
        <p className="text-sm text-gray-400 italic py-4">No courses enrolled.</p>
      ) : (
        <div className="space-y-3">
          {courses.map((course) => (
            <div key={course.id}>
              <div className="flex items-center justify-between mb-1">
                <p className="text-sm text-gray-700 truncate flex-1 mr-3">
                  {course.title}
                </p>
                <span className="text-xs font-medium text-gray-500 flex-shrink-0">
                  {Math.round(course.progress_percentage)}%
                </span>
              </div>
              <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                <div
                  className={cn('h-full rounded-full transition-all', progressColor(course.progress_percentage))}
                  style={{ width: `${Math.min(course.progress_percentage, 100)}%` }}
                />
              </div>
              {course.last_accessed && (
                <p className="text-[10px] text-gray-400 mt-0.5">
                  Last accessed {relativeTime(course.last_accessed)}
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── Assignments Card ───────────────────────────────────────────────────────

function AssignmentsCard({
  assignments,
}: {
  assignments: ParentAssignment[];
}) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
      <div className="flex items-center gap-2 mb-4">
        <ClipboardList className="h-4 w-4 text-indigo-500" />
        <h3 className="text-sm font-semibold text-gray-900">Assignments</h3>
      </div>
      {assignments.length === 0 ? (
        <p className="text-sm text-gray-400 italic py-4">No assignments yet.</p>
      ) : (
        <div className="overflow-x-auto -mx-5">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100">
                <th className="text-left py-2 px-5 text-xs font-medium text-gray-400">Title</th>
                <th className="text-left py-2 px-3 text-xs font-medium text-gray-400 hidden sm:table-cell">Course</th>
                <th className="text-left py-2 px-3 text-xs font-medium text-gray-400 hidden md:table-cell">Due</th>
                <th className="text-left py-2 px-3 text-xs font-medium text-gray-400">Status</th>
                <th className="text-right py-2 px-5 text-xs font-medium text-gray-400">Score</th>
              </tr>
            </thead>
            <tbody>
              {assignments.map((a) => (
                <tr key={a.id} className="border-b border-gray-50 last:border-0">
                  <td className="py-2.5 px-5 text-gray-700 truncate max-w-[160px]">
                    {a.title}
                  </td>
                  <td className="py-2.5 px-3 text-gray-500 truncate max-w-[120px] hidden sm:table-cell">
                    {a.course_title}
                  </td>
                  <td className="py-2.5 px-3 text-gray-500 hidden md:table-cell whitespace-nowrap">
                    {a.due_date
                      ? new Date(a.due_date).toLocaleDateString()
                      : '-'}
                  </td>
                  <td className="py-2.5 px-3">
                    <span
                      className={cn(
                        'inline-block text-[11px] font-medium px-2 py-0.5 rounded',
                        STATUS_STYLES[a.submission_status] || 'bg-gray-100 text-gray-500',
                      )}
                    >
                      {a.submission_status.replace('_', ' ')}
                    </span>
                  </td>
                  <td className="py-2.5 px-5 text-right text-gray-600 whitespace-nowrap">
                    {a.score != null
                      ? `${a.score}/${a.max_score}`
                      : '-'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ─── Attendance Card (SVG donut) ────────────────────────────────────────────

function AttendanceCard({
  attendance,
}: {
  attendance: ParentChildOverview['attendance'];
}) {
  const { present_days, absent_days, total_days, attendance_percentage } = attendance;

  // SVG donut parameters
  const radius = 54;
  const circumference = 2 * Math.PI * radius;

  const segments = useMemo(() => {
    if (total_days === 0) return [];
    const pPresent = present_days / total_days;
    const pAbsent = absent_days / total_days;

    let offset = 0;
    const result = [];

    if (pPresent > 0) {
      result.push({ color: '#22c55e', dasharray: `${pPresent * circumference} ${circumference}`, offset: -offset * circumference });
      offset += pPresent;
    }
    if (pAbsent > 0) {
      result.push({ color: '#ef4444', dasharray: `${pAbsent * circumference} ${circumference}`, offset: -offset * circumference });
    }

    return result;
  }, [present_days, absent_days, total_days, circumference]);

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
      <div className="flex items-center gap-2 mb-4">
        <User className="h-4 w-4 text-indigo-500" />
        <h3 className="text-sm font-semibold text-gray-900">Attendance</h3>
      </div>

      {total_days === 0 ? (
        <p className="text-sm text-gray-400 italic py-4">
          {attendance.note || 'No attendance data available.'}
        </p>
      ) : (
        <div className="flex items-center gap-6">
          {/* Donut */}
          <div className="relative flex-shrink-0">
            <svg width="130" height="130" viewBox="0 0 130 130">
              <circle cx="65" cy="65" r={radius} fill="none" stroke="#f3f4f6" strokeWidth="14" />
              {segments.map((seg, i) => (
                <circle
                  key={i}
                  cx="65"
                  cy="65"
                  r={radius}
                  fill="none"
                  stroke={seg.color}
                  strokeWidth="14"
                  strokeDasharray={seg.dasharray}
                  strokeDashoffset={seg.offset}
                  strokeLinecap="round"
                  transform="rotate(-90 65 65)"
                />
              ))}
            </svg>
            <div className="absolute inset-0 flex items-center justify-center">
              <span className="text-2xl font-bold text-gray-900">
                {Math.round(attendance_percentage)}%
              </span>
            </div>
          </div>

          {/* Legend */}
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <div className="h-2.5 w-2.5 rounded-full bg-green-500" />
              <span className="text-xs text-gray-600">Present ({present_days})</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="h-2.5 w-2.5 rounded-full bg-red-500" />
              <span className="text-xs text-gray-600">Absent ({absent_days})</span>
            </div>
            <p className="text-[10px] text-gray-400 pt-1">
              Total: {total_days} day{total_days !== 1 ? 's' : ''}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Study Time Card ────────────────────────────────────────────────────────

function StudyTimeCard({
  studyTime,
}: {
  studyTime: ParentChildOverview['study_time'];
}) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Clock className="h-4 w-4 text-indigo-500" />
          <h3 className="text-sm font-semibold text-gray-900">Study Time</h3>
        </div>
        <span className="text-xs font-medium text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded">
          {studyTime.total_video_minutes}m video time
        </span>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="bg-blue-50 rounded-lg p-4 text-center">
          <p className="text-2xl font-bold text-blue-600">
            {studyTime.courses_in_progress}
          </p>
          <p className="text-xs text-blue-500 mt-1">In Progress</p>
        </div>
        <div className="bg-green-50 rounded-lg p-4 text-center">
          <p className="text-2xl font-bold text-green-600">
            {studyTime.courses_completed}
          </p>
          <p className="text-xs text-green-500 mt-1">Completed</p>
        </div>
      </div>

      {studyTime.total_video_minutes > 0 && (
        <p className="text-xs text-gray-400 mt-3 text-center">
          {Math.floor(studyTime.total_video_minutes / 60)}h {Math.round(studyTime.total_video_minutes % 60)}m total video time
        </p>
      )}
    </div>
  );
}

// ─── Recent Activity Card ───────────────────────────────────────────────────

function RecentActivityCard({
  activities,
}: {
  activities: ParentChildOverview['recent_activity'];
}) {
  const displayActivities = activities.slice(0, 10);

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
      <div className="flex items-center gap-2 mb-4">
        <Activity className="h-4 w-4 text-indigo-500" />
        <h3 className="text-sm font-semibold text-gray-900">Recent Activity</h3>
      </div>

      {displayActivities.length === 0 ? (
        <p className="text-sm text-gray-400 italic py-4">No recent activity.</p>
      ) : (
        <div className="space-y-3">
          {displayActivities.map((act, i) => (
            <div key={i} className="flex items-start gap-3">
              <div className="mt-0.5 h-6 w-6 rounded-full bg-indigo-50 flex items-center justify-center flex-shrink-0">
                <Activity className="h-3 w-3 text-indigo-500" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm text-gray-700">
                  <span className={cn(
                    'inline-block text-[11px] font-medium px-1.5 py-0.5 rounded mr-1.5',
                    STATUS_STYLES[act.status] || 'bg-gray-100 text-gray-500',
                  )}>
                    {act.status.replace('_', ' ')}
                  </span>
                  <span className="font-medium">{act.course_title}</span>
                  {act.content_title && (
                    <span className="text-gray-500"> &mdash; {act.content_title}</span>
                  )}
                </p>
                {act.last_accessed && (
                  <p className="text-[11px] text-gray-400 mt-0.5">
                    {relativeTime(act.last_accessed)}
                  </p>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
