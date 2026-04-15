// src/pages/teacher/SectionDashboardPage.tsx
//
// Teacher Section Dashboard — tabbed view for managing a single section.
// Tabs: Students, Courses, Analytics, Assignments.
// Active tab is persisted in URL search params (?tab=students).

import React, { useState, useMemo } from 'react';
import { useParams, useNavigate, useSearchParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  ArrowLeft,
  Users,
  BookOpen,
  BarChart3,
  ClipboardList,
  CalendarDays,
  Search,
  CheckCircle,
  XCircle,
  AlertCircle,
  Clock,
  Plus,
  ChevronLeft,
  ChevronRight,
  Download,
} from 'lucide-react';
import { cn } from '../../design-system/theme/cn';
import { usePageTitle } from '../../hooks/usePageTitle';
import {
  academicsService,
  type SectionDashboardResponse,
} from '../../services/academicsService';
import { AttendanceCard } from '../../components/attendance/AttendanceCard';
import { AttendanceLoader } from '../../components/attendance/AttendanceLoader';
import { ExportAttendanceModal } from '../../components/attendance/ExportAttendanceModal';
import api from '../../config/api';

// ─── Constants ───────────────────────────────────────────────────────────────

type TabKey = 'students' | 'courses' | 'analytics' | 'assignments' | 'attendance';

interface TabDefinition {
  key: TabKey;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}

const TABS: TabDefinition[] = [
  { key: 'students', label: 'Students', icon: Users },
  { key: 'courses', label: 'Courses', icon: BookOpen },
  { key: 'analytics', label: 'Analytics', icon: BarChart3 },
  { key: 'assignments', label: 'Assignments', icon: ClipboardList },
  { key: 'attendance', label: 'Attendance', icon: CalendarDays },
];

// ─── Helpers ─────────────────────────────────────────────────────────────────

function formatDate(dateStr: string | null): string {
  if (!dateStr) return 'Never';
  const date = new Date(dateStr);
  if (isNaN(date.getTime())) return 'Never';
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

function formatDueDate(dateStr: string | null): string {
  if (!dateStr) return 'No due date';
  const date = new Date(dateStr);
  if (isNaN(date.getTime())) return 'No due date';
  const now = new Date();
  const diffMs = date.getTime() - now.getTime();
  const diffDays = Math.ceil(diffMs / (1000 * 60 * 60 * 24));

  const formatted = date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });

  if (diffDays < 0) return `Overdue (${formatted})`;
  if (diffDays === 0) return 'Due today';
  if (diffDays === 1) return 'Due tomorrow';
  if (diffDays <= 7) return `Due in ${diffDays} days`;
  return formatted;
}

function getBadgeCount(
  data: SectionDashboardResponse | undefined,
  tab: TabKey,
): number | null {
  if (!data) return null;
  switch (tab) {
    case 'students':
      return data.students?.length ?? data.total ?? null;
    case 'courses':
      return data.courses?.length ?? null;
    case 'analytics':
      return null;
    case 'assignments':
      return data.assignments?.length ?? null;
    case 'attendance':
      return null;
    default:
      return null;
  }
}

// ─── Empty State ─────────────────────────────────────────────────────────────

function EmptyState({
  icon: Icon,
  title,
  description,
  action,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-dashed border-gray-200 bg-white p-12 text-center">
      <Icon className="mx-auto h-12 w-12 text-gray-200" />
      <h3 className="mt-4 text-[15px] font-semibold text-tp-text">{title}</h3>
      <p className="mt-1.5 text-[13px] text-gray-400 max-w-sm mx-auto">
        {description}
      </p>
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

// ─── Students Tab ────────────────────────────────────────────────────────────

function StudentsTab({ data }: { data: SectionDashboardResponse }) {
  const [search, setSearch] = useState('');
  const students = data.students ?? [];

  const filtered = useMemo(() => {
    if (!search.trim()) return students;
    const q = search.toLowerCase();
    return students.filter(
      (s) =>
        s.first_name.toLowerCase().includes(q) ||
        s.last_name.toLowerCase().includes(q) ||
        s.email.toLowerCase().includes(q) ||
        s.student_id.toLowerCase().includes(q),
    );
  }, [students, search]);

  if (students.length === 0) {
    return (
      <EmptyState
        icon={Users}
        title="No students in this section"
        description="There are no students assigned to this section yet. Students can be added from the admin panel."
      />
    );
  }

  return (
    <div className="space-y-4">
      {/* Search */}
      <div className="relative max-w-sm">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
        <input
          type="text"
          placeholder="Search by name, ID, or email..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full pl-10 pr-4 py-2 rounded-lg text-[13px] bg-white border border-gray-200 text-tp-text placeholder:text-gray-400 focus:border-tp-accent focus:ring-2 focus:ring-orange-100 focus:outline-none transition-all"
        />
      </div>

      {/* Results count */}
      <p className="text-[12px] text-gray-400">
        {filtered.length === students.length
          ? `${students.length} student${students.length !== 1 ? 's' : ''}`
          : `${filtered.length} of ${students.length} student${students.length !== 1 ? 's' : ''}`}
      </p>

      {/* Table */}
      {filtered.length === 0 ? (
        <div className="rounded-xl border border-gray-200 bg-white p-8 text-center">
          <Search className="mx-auto h-8 w-8 text-gray-200" />
          <p className="mt-2 text-[13px] text-gray-500">
            No students match &ldquo;{search}&rdquo;
          </p>
        </div>
      ) : (
        <div className="rounded-xl border border-gray-100 bg-white overflow-hidden shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-gray-100 bg-gray-50/60">
                  <th className="px-5 py-3 text-[11px] font-semibold text-gray-500 uppercase tracking-wider">
                    Name
                  </th>
                  <th className="px-5 py-3 text-[11px] font-semibold text-gray-500 uppercase tracking-wider">
                    Student ID
                  </th>
                  <th className="px-5 py-3 text-[11px] font-semibold text-gray-500 uppercase tracking-wider">
                    Email
                  </th>
                  <th className="px-5 py-3 text-[11px] font-semibold text-gray-500 uppercase tracking-wider">
                    Status
                  </th>
                  <th className="px-5 py-3 text-[11px] font-semibold text-gray-500 uppercase tracking-wider">
                    Last Login
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {filtered.map((student) => (
                  <tr
                    key={student.id}
                    className="hover:bg-orange-50/30 transition-colors"
                  >
                    <td className="px-5 py-3.5">
                      <div className="flex items-center gap-3">
                        <div className="h-8 w-8 rounded-full bg-orange-50 flex items-center justify-center text-[12px] font-semibold text-tp-accent flex-shrink-0">
                          {student.first_name.charAt(0)}
                          {student.last_name.charAt(0)}
                        </div>
                        <span className="text-[13px] font-medium text-tp-text">
                          {student.first_name} {student.last_name}
                        </span>
                      </div>
                    </td>
                    <td className="px-5 py-3.5">
                      <span className="text-[13px] text-tp-text-secondary font-mono">
                        {student.student_id}
                      </span>
                    </td>
                    <td className="px-5 py-3.5">
                      <span className="text-[13px] text-tp-text-secondary">
                        {student.email}
                      </span>
                    </td>
                    <td className="px-5 py-3.5">
                      {student.is_active ? (
                        <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-0.5 text-[11px] font-semibold text-emerald-700">
                          <CheckCircle className="h-3 w-3" />
                          Active
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1.5 rounded-full bg-red-50 px-2.5 py-0.5 text-[11px] font-semibold text-red-600">
                          <XCircle className="h-3 w-3" />
                          Inactive
                        </span>
                      )}
                    </td>
                    <td className="px-5 py-3.5">
                      <span className="text-[13px] text-tp-text-muted">
                        {formatDate(student.last_login)}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Courses Tab ─────────────────────────────────────────────────────────────

function CoursesTab({
  data,
  sectionId,
}: {
  data: SectionDashboardResponse;
  sectionId: string;
}) {
  const navigate = useNavigate();
  const courses = data.courses ?? [];

  if (courses.length === 0) {
    return (
      <EmptyState
        icon={BookOpen}
        title="No courses targeting this section"
        description="Create a course and assign it to this section to get started."
        action={
          <button
            onClick={() =>
              navigate(`/teacher/authoring/new?sectionId=${sectionId}`)
            }
            className="inline-flex items-center gap-2 rounded-lg bg-tp-accent px-4 py-2.5 text-sm font-semibold text-white hover:bg-tp-accent-dark transition-colors shadow-sm"
          >
            <Plus className="h-4 w-4" />
            Create Course
          </button>
        }
      />
    );
  }

  return (
    <div className="space-y-4">
      {/* Header row */}
      <div className="flex items-center justify-between">
        <p className="text-[12px] text-gray-400">
          {courses.length} course{courses.length !== 1 ? 's' : ''}
        </p>
      </div>

      {/* Course cards grid */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {courses.map((course) => (
          <Link
            key={course.id}
            to={`/teacher/courses/${course.id}`}
            className="group rounded-2xl border border-gray-100 bg-white p-5 hover:shadow-md hover:border-orange-200 transition-all shadow-sm"
          >
            {/* Status badges */}
            <div className="flex items-center gap-2 mb-3">
              {course.is_published ? (
                <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2.5 py-0.5 text-[11px] font-semibold text-emerald-700">
                  <CheckCircle className="h-3 w-3" />
                  Published
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 rounded-full bg-gray-100 px-2.5 py-0.5 text-[11px] font-semibold text-gray-500">
                  <Clock className="h-3 w-3" />
                  Draft
                </span>
              )}
              {course.is_active ? (
                <span className="inline-flex items-center rounded-full bg-blue-50 px-2.5 py-0.5 text-[11px] font-semibold text-blue-600">
                  Active
                </span>
              ) : (
                <span className="inline-flex items-center rounded-full bg-gray-100 px-2.5 py-0.5 text-[11px] font-semibold text-gray-400">
                  Inactive
                </span>
              )}
            </div>

            {/* Title */}
            <h3 className="text-[15px] font-semibold text-tp-text group-hover:text-tp-accent transition-colors line-clamp-2">
              {course.title}
            </h3>

            {/* Meta */}
            <div className="mt-3 flex items-center gap-4 text-[12px] text-tp-text-muted">
              <span className="flex items-center gap-1">
                <Users className="h-3.5 w-3.5" />
                {course.student_count} student
                {course.student_count !== 1 ? 's' : ''}
              </span>
              <span className="flex items-center gap-1">
                <Clock className="h-3.5 w-3.5" />
                {formatDate(course.created_at)}
              </span>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}

// ─── Analytics Tab ───────────────────────────────────────────────────────────

function AnalyticsTab({ data }: { data: SectionDashboardResponse }) {
  const stats = data.stats;

  if (!stats) {
    return (
      <EmptyState
        icon={BarChart3}
        title="No analytics available"
        description="Analytics data will appear here once students are enrolled and begin engaging with courses."
      />
    );
  }

  const cards = [
    {
      label: 'Total Students',
      value: stats.total_students,
      icon: Users,
      iconColor: 'text-tp-accent',
      iconBg: 'bg-orange-50',
    },
    {
      label: 'Active (7d)',
      value: stats.active_students_7d,
      icon: CheckCircle,
      iconColor: 'text-emerald-600',
      iconBg: 'bg-emerald-50',
    },
    {
      label: 'Inactive',
      value: stats.inactive_students,
      icon: AlertCircle,
      iconColor: 'text-amber-600',
      iconBg: 'bg-amber-50',
    },
    {
      label: 'Total Courses',
      value: stats.total_courses,
      icon: BookOpen,
      iconColor: 'text-blue-600',
      iconBg: 'bg-blue-50',
    },
  ];

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-2">
      {cards.map((card) => {
        const Icon = card.icon;
        return (
          <div
            key={card.label}
            className="rounded-2xl border border-gray-100 bg-white p-5 transition-shadow hover:shadow-md shadow-sm"
          >
            <div className="flex items-center justify-between">
              <div>
                <p className="text-[12px] font-medium text-tp-text-muted uppercase tracking-wide">
                  {card.label}
                </p>
                <p className="mt-1.5 text-[28px] font-bold text-tp-text leading-none tabular-nums">
                  {card.value}
                </p>
              </div>
              <div className={cn('rounded-xl p-2.5', card.iconBg)}>
                <Icon className={cn('h-5 w-5', card.iconColor)} />
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ─── Assignments Tab ─────────────────────────────────────────────────────────

function AssignmentsTab({ data }: { data: SectionDashboardResponse }) {
  const assignments = data.assignments ?? [];

  if (assignments.length === 0) {
    return (
      <EmptyState
        icon={ClipboardList}
        title="No assignments for this section"
        description="Assignments will appear here once they are created within courses for this section."
      />
    );
  }

  return (
    <div className="space-y-3">
      <p className="text-[12px] text-gray-400">
        {assignments.length} assignment{assignments.length !== 1 ? 's' : ''}
      </p>

      <div className="rounded-2xl border border-gray-100 bg-white overflow-hidden shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-gray-100 bg-gray-50/60">
                <th className="px-5 py-3 text-[11px] font-semibold text-gray-500 uppercase tracking-wider">
                  Title
                </th>
                <th className="px-5 py-3 text-[11px] font-semibold text-gray-500 uppercase tracking-wider">
                  Due Date
                </th>
                <th className="px-5 py-3 text-[11px] font-semibold text-gray-500 uppercase tracking-wider">
                  Max Score
                </th>
                <th className="px-5 py-3 text-[11px] font-semibold text-gray-500 uppercase tracking-wider">
                  Type
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {assignments.map((assignment) => {
                const dueDateStr = formatDueDate(assignment.due_date);
                const isOverdue = dueDateStr.startsWith('Overdue');

                return (
                  <tr
                    key={assignment.id}
                    className="hover:bg-orange-50/30 transition-colors"
                  >
                    <td className="px-5 py-3.5">
                      <div className="flex items-center gap-3">
                        <div
                          className={cn(
                            'rounded-lg p-2 flex-shrink-0',
                            assignment.is_quiz ? 'bg-purple-50' : 'bg-orange-50',
                          )}
                        >
                          <ClipboardList
                            className={cn(
                              'h-4 w-4',
                              assignment.is_quiz
                                ? 'text-purple-600'
                                : 'text-tp-accent',
                            )}
                          />
                        </div>
                        <span className="text-[13px] font-medium text-tp-text truncate">
                          {assignment.title}
                        </span>
                      </div>
                    </td>
                    <td className="px-5 py-3.5">
                      <span
                        className={cn(
                          'text-[13px] font-medium',
                          isOverdue ? 'text-red-600' : 'text-tp-text-secondary',
                        )}
                      >
                        {dueDateStr}
                      </span>
                    </td>
                    <td className="px-5 py-3.5">
                      <span className="text-[13px] text-tp-text-secondary tabular-nums">
                        {assignment.max_score}
                      </span>
                    </td>
                    <td className="px-5 py-3.5">
                      {assignment.is_quiz ? (
                        <span className="inline-flex items-center rounded-full bg-purple-100 px-2.5 py-0.5 text-[11px] font-semibold text-purple-700">
                          Quiz
                        </span>
                      ) : (
                        <span className="inline-flex items-center rounded-full bg-gray-100 px-2.5 py-0.5 text-[11px] font-semibold text-gray-600">
                          Assignment
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

// ─── Attendance Tab ─────────────────────────────────────────────────────────

interface AttendanceStudent {
  id: string;
  first_name: string;
  last_name: string;
  student_id: string;
  status: string;
  remarks: string;
}

interface AttendanceResponse {
  section_id: string;
  date: string;
  summary: {
    total: number;
    present: number;
    late: number;
    absent: number;
    excused: number;
    attendance_rate: number;
    on_time_pct: number;
    late_pct: number;
    absent_pct: number;
  };
  bars: { status: string }[];
  students: AttendanceStudent[];
}

const STATUS_BADGE: Record<string, { bg: string; text: string; label: string }> = {
  PRESENT: { bg: 'bg-blue-50', text: 'text-blue-700', label: 'Present' },
  LATE: { bg: 'bg-amber-50', text: 'text-amber-700', label: 'Late' },
  ABSENT: { bg: 'bg-red-50', text: 'text-red-600', label: 'Absent' },
  EXCUSED: { bg: 'bg-slate-100', text: 'text-slate-600', label: 'Excused' },
};

function AttendanceTab({ sectionId }: { sectionId: string }) {
  const today = new Date();
  const [selectedDate, setSelectedDate] = useState(
    today.toISOString().split('T')[0],
  );

  const { data, isLoading } = useQuery<AttendanceResponse>({
    queryKey: ['sectionAttendance', sectionId, selectedDate],
    queryFn: async () => {
      const res = await api.get(
        `/v1/teacher/academics/sections/${sectionId}/attendance/`,
        { params: { date: selectedDate } },
      );
      return res.data;
    },
    enabled: !!sectionId,
    staleTime: 30_000,
  });

  const goToPrev = () => {
    const d = new Date(selectedDate);
    d.setDate(d.getDate() - 1);
    setSelectedDate(d.toISOString().split('T')[0]);
  };

  const goToNext = () => {
    const d = new Date(selectedDate);
    d.setDate(d.getDate() + 1);
    const todayStr = today.toISOString().split('T')[0];
    if (d.toISOString().split('T')[0] <= todayStr) {
      setSelectedDate(d.toISOString().split('T')[0]);
    }
  };

  const isToday = selectedDate === today.toISOString().split('T')[0];
  const [exportOpen, setExportOpen] = useState(false);

  if (isLoading) {
    return <AttendanceLoader />;
  }

  if (!data || data.summary.total === 0) {
    return (
      <div className="space-y-4">
        {/* Date nav */}
        <div className="flex items-center gap-3">
          <button onClick={goToPrev} className="p-1.5 rounded-lg hover:bg-gray-100 transition-colors">
            <ChevronLeft className="h-4 w-4 text-gray-500" />
          </button>
          <span className="text-sm font-semibold text-tp-text">
            {new Date(selectedDate + 'T12:00:00').toLocaleDateString('en-US', {
              weekday: 'long', month: 'long', day: 'numeric', year: 'numeric',
            })}
          </span>
          <button
            onClick={goToNext}
            disabled={isToday}
            className="p-1.5 rounded-lg hover:bg-gray-100 transition-colors disabled:opacity-30"
          >
            <ChevronRight className="h-4 w-4 text-gray-500" />
          </button>
        </div>

        <EmptyState
          icon={CalendarDays}
          title="No attendance data for this date"
          description="Attendance data will appear here once imported by the school administrator."
        />
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Date nav + export */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button onClick={goToPrev} className="p-1.5 rounded-lg hover:bg-gray-100 transition-colors">
            <ChevronLeft className="h-4 w-4 text-gray-500" />
          </button>
          <span className="text-sm font-semibold text-tp-text">
            {new Date(selectedDate + 'T12:00:00').toLocaleDateString('en-US', {
              weekday: 'long', month: 'long', day: 'numeric', year: 'numeric',
            })}
          </span>
          <button
            onClick={goToNext}
            disabled={isToday}
            className="p-1.5 rounded-lg hover:bg-gray-100 transition-colors disabled:opacity-30"
          >
            <ChevronRight className="h-4 w-4 text-gray-500" />
          </button>
        </div>
        <button
          onClick={() => setExportOpen(true)}
          className="inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-[13px] font-medium text-gray-600 hover:bg-gray-50 transition-colors"
        >
          <Download className="h-3.5 w-3.5" />
          Export
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Attendance Card */}
        <AttendanceCard
          title="Section Attendance"
          summary={data.summary}
          bars={data.bars}
        />

        {/* Student list */}
        <div className="lg:col-span-2 rounded-2xl border border-gray-100 bg-white overflow-hidden shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-gray-100 bg-gray-50/60">
                  <th className="px-5 py-3 text-[11px] font-semibold text-gray-500 uppercase tracking-wider">
                    Student
                  </th>
                  <th className="px-5 py-3 text-[11px] font-semibold text-gray-500 uppercase tracking-wider">
                    ID
                  </th>
                  <th className="px-5 py-3 text-[11px] font-semibold text-gray-500 uppercase tracking-wider">
                    Status
                  </th>
                  <th className="px-5 py-3 text-[11px] font-semibold text-gray-500 uppercase tracking-wider">
                    Remarks
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {data.students.map((student) => {
                  const badge = STATUS_BADGE[student.status] || STATUS_BADGE.PRESENT;
                  return (
                    <tr key={student.id} className="hover:bg-orange-50/30 transition-colors">
                      <td className="px-5 py-3.5">
                        <div className="flex items-center gap-3">
                          <div className="h-8 w-8 rounded-full bg-orange-50 flex items-center justify-center text-[12px] font-semibold text-tp-accent flex-shrink-0">
                            {student.first_name.charAt(0)}{student.last_name.charAt(0)}
                          </div>
                          <span className="text-[13px] font-medium text-tp-text">
                            {student.first_name} {student.last_name}
                          </span>
                        </div>
                      </td>
                      <td className="px-5 py-3.5">
                        <span className="text-[13px] text-tp-text-secondary font-mono">
                          {student.student_id}
                        </span>
                      </td>
                      <td className="px-5 py-3.5">
                        <span className={cn(
                          'inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-semibold',
                          badge.bg, badge.text,
                        )}>
                          {badge.label}
                        </span>
                      </td>
                      <td className="px-5 py-3.5">
                        <span className="text-[13px] text-tp-text-muted">
                          {student.remarks || '—'}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>
      <ExportAttendanceModal
        open={exportOpen}
        onClose={() => setExportOpen(false)}
        portal="teacher"
        sectionId={sectionId}
      />
    </div>
  );
}

// ─── Main Page Component ─────────────────────────────────────────────────────

export const SectionDashboardPage: React.FC = () => {
  const { sectionId } = useParams<{ sectionId: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const activeTab = (searchParams.get('tab') as TabKey) || 'students';

  // Validate tab key and fall back to 'students'
  const validTab = TABS.some((t) => t.key === activeTab) ? activeTab : 'students';

  usePageTitle('Section Dashboard');

  // ─── Tab-specific queries (only enabled when that tab is active) ─────────

  const {
    data: studentsData,
    isLoading: studentsLoading,
    isError: studentsError,
    error: studentsErr,
  } = useQuery<SectionDashboardResponse>({
    queryKey: ['sectionDashboard', sectionId, 'students'],
    queryFn: () => academicsService.getSectionDashboard(sectionId!, 'students'),
    enabled: !!sectionId && validTab === 'students',
    staleTime: 30_000,
  });

  const {
    data: coursesData,
    isLoading: coursesLoading,
    isError: coursesError,
    error: coursesErr,
  } = useQuery<SectionDashboardResponse>({
    queryKey: ['sectionDashboard', sectionId, 'courses'],
    queryFn: () => academicsService.getSectionDashboard(sectionId!, 'courses'),
    enabled: !!sectionId && validTab === 'courses',
    staleTime: 30_000,
  });

  const {
    data: analyticsData,
    isLoading: analyticsLoading,
    isError: analyticsError,
    error: analyticsErr,
  } = useQuery<SectionDashboardResponse>({
    queryKey: ['sectionDashboard', sectionId, 'analytics'],
    queryFn: () => academicsService.getSectionDashboard(sectionId!, 'analytics'),
    enabled: !!sectionId && validTab === 'analytics',
    staleTime: 30_000,
  });

  const {
    data: assignmentsData,
    isLoading: assignmentsLoading,
    isError: assignmentsError,
    error: assignmentsErr,
  } = useQuery<SectionDashboardResponse>({
    queryKey: ['sectionDashboard', sectionId, 'assignments'],
    queryFn: () => academicsService.getSectionDashboard(sectionId!, 'assignments'),
    enabled: !!sectionId && validTab === 'assignments',
    staleTime: 30_000,
  });

  // ─── Resolve active tab data ─────────────────────────────────────────────

  // Attendance tab has its own query within the AttendanceTab component,
  // so we use a dummy SectionDashboardResponse to satisfy the tab framework.
  const attendanceDummy: SectionDashboardResponse | undefined =
    validTab === 'attendance' ? ({} as SectionDashboardResponse) : undefined;

  const tabDataMap: Record<TabKey, SectionDashboardResponse | undefined> = {
    students: studentsData,
    courses: coursesData,
    analytics: analyticsData,
    assignments: assignmentsData,
    attendance: attendanceDummy,
  };

  const tabLoadingMap: Record<TabKey, boolean> = {
    students: studentsLoading,
    courses: coursesLoading,
    analytics: analyticsLoading,
    assignments: assignmentsLoading,
    attendance: false,
  };

  const tabErrorMap: Record<TabKey, boolean> = {
    students: studentsError,
    courses: coursesError,
    analytics: analyticsError,
    assignments: assignmentsError,
    attendance: false,
  };

  const tabErrorMsgMap: Record<TabKey, unknown> = {
    students: studentsErr,
    courses: coursesErr,
    analytics: analyticsErr,
    assignments: assignmentsErr,
    attendance: null,
  };

  const activeData = tabDataMap[validTab];
  const isLoading = tabLoadingMap[validTab];
  const isError = tabErrorMap[validTab];
  const error = tabErrorMsgMap[validTab];

  const handleTabChange = (tab: TabKey) => {
    setSearchParams({ tab }, { replace: true });
  };

  // Section info from whichever response we have
  const section =
    activeData?.section ??
    studentsData?.section ??
    coursesData?.section ??
    analyticsData?.section ??
    assignmentsData?.section ??
    null;

  const sectionTitle = section
    ? `${section.grade_name} - ${section.name}`
    : null;

  // Resolve badge counts
  const resolveBadge = (tab: TabKey): number | null => {
    return getBadgeCount(tabDataMap[tab], tab);
  };

  return (
    <div className="space-y-5">
      {/* ── Header ────────────────────────────────────────────────────────── */}
      <div>
        <div className="flex items-start gap-3">
          <button
            onClick={() => navigate('/teacher/my-classes')}
            className="mt-0.5 rounded-lg p-1.5 text-gray-400 hover:bg-orange-50 hover:text-tp-accent transition-colors flex-shrink-0"
            aria-label="Back to My Classes"
          >
            <ArrowLeft className="h-5 w-5" />
          </button>

          <div className="min-w-0">
            {isLoading && !section ? (
              <div className="space-y-2">
                <div className="h-7 w-64 tp-skeleton rounded-lg" />
                <div className="h-4 w-40 tp-skeleton rounded" />
              </div>
            ) : (
              <>
                <div className="flex items-center gap-3 flex-wrap">
                  <h1 className="text-[22px] font-bold text-tp-text tracking-tight">
                    {sectionTitle ?? 'Section Dashboard'}
                  </h1>
                  {section?.academic_year && (
                    <span className="inline-flex items-center rounded-full bg-orange-50 px-2.5 py-0.5 text-[11px] font-semibold text-tp-accent">
                      {section.academic_year}
                    </span>
                  )}
                </div>
                {section?.grade_band_name && (
                  <p className="mt-0.5 text-[13px] text-gray-400">
                    {section.grade_band_name}
                  </p>
                )}
              </>
            )}
          </div>
        </div>
      </div>

      {/* ── Tab Bar ───────────────────────────────────────────────────────── */}
      <div className="flex items-center gap-1 overflow-x-auto" role="tablist">
        {TABS.map((tab) => {
          const isActive = validTab === tab.key;
          const Icon = tab.icon;
          const badge = resolveBadge(tab.key);

          return (
            <button
              key={tab.key}
              role="tab"
              aria-selected={isActive}
              aria-controls={`panel-${tab.key}`}
              onClick={() => handleTabChange(tab.key)}
              className={cn(
                'inline-flex items-center gap-2 whitespace-nowrap rounded-lg px-4 py-2 text-[13px] font-medium transition-colors',
                isActive
                  ? 'bg-orange-50 text-tp-accent'
                  : 'text-gray-500 hover:bg-gray-50',
              )}
            >
              <Icon className="h-4 w-4 flex-shrink-0" />
              {tab.label}
              {badge !== null && (
                <span
                  className={cn(
                    'inline-flex items-center justify-center rounded-md px-1.5 py-[2px] text-[10px] font-semibold leading-none min-w-[20px] tabular-nums',
                    isActive
                      ? 'bg-orange-100 text-tp-accent'
                      : 'bg-gray-100 text-gray-400',
                  )}
                >
                  {badge}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* ── Tab Content ───────────────────────────────────────────────────── */}
      <div id={`panel-${validTab}`} role="tabpanel">
        {isLoading ? (
          <div className="space-y-3">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="h-14 tp-skeleton rounded-xl" />
            ))}
          </div>
        ) : isError ? (
          <div className="rounded-2xl border border-red-200 bg-red-50 p-8 text-center">
            <AlertCircle className="mx-auto h-10 w-10 text-red-400" />
            <h3 className="mt-3 text-[15px] font-semibold text-red-700">
              Failed to load data
            </h3>
            <p className="mt-1 text-[13px] text-red-500">
              {error instanceof Error
                ? error.message
                : 'An unexpected error occurred.'}
            </p>
            <button
              onClick={() => navigate('/teacher/my-classes')}
              className="mt-4 inline-flex items-center gap-1.5 rounded-lg border border-red-200 px-4 py-2 text-[13px] font-medium text-red-700 hover:bg-red-100 transition-colors"
            >
              <ArrowLeft className="h-4 w-4" />
              Back to My Classes
            </button>
          </div>
        ) : activeData ? (
          <>
            {validTab === 'students' && <StudentsTab data={activeData} />}
            {validTab === 'courses' && (
              <CoursesTab data={activeData} sectionId={sectionId!} />
            )}
            {validTab === 'analytics' && <AnalyticsTab data={activeData} />}
            {validTab === 'assignments' && <AssignmentsTab data={activeData} />}
            {validTab === 'attendance' && <AttendanceTab sectionId={sectionId!} />}
          </>
        ) : null}
      </div>
    </div>
  );
};
