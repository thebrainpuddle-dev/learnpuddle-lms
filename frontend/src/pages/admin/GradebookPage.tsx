// src/pages/admin/GradebookPage.tsx
//
// Centralized Gradebook — admin view of course progress and assignment scores
// for all teachers and students.  Uses TanStack Table (via DataTable) with
// client-side sort/filter/paginate, plus server-driven course/assignment
// selectors and role/status filters.

import React, { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { format, parseISO, isValid } from 'date-fns';
import { type ColumnDef } from '@tanstack/react-table';
import { DataTable, DataTableColumnHeader } from '../../components/ui/data-table';
import { Badge } from '../../components/ui/badge';
import { Button } from '../../components/common/Button';
import { Loading } from '../../components/common';
import { adminReportsService } from '../../services/adminReportsService';
import type {
  CourseProgressRow,
  AssignmentStatusRow,
} from '../../services/adminReportsService';
import {
  TableCellsIcon,
  FunnelIcon,
  ArrowDownTrayIcon,
  ClipboardDocumentListIcon,
  AcademicCapIcon,
  UserGroupIcon,
  UsersIcon,
} from '@heroicons/react/24/outline';
import { usePageTitle } from '../../hooks/usePageTitle';
import { useModeLabels } from '../../hooks/useModeLabels';
import type { ModeLabelKey } from '../../stores/tenantStore';

// ── Types & helpers ──────────────────────────────────────────────────────────

type GradebookTab = 'course' | 'assignment';
type RoleFilter = 'all' | 'teachers' | 'students';

const STATUS_COURSE: Record<string, { label: string; variant: 'success' | 'default' | 'secondary' | 'warning' }> = {
  COMPLETED:   { label: 'Completed',   variant: 'success' },
  IN_PROGRESS: { label: 'In Progress', variant: 'warning' },
  NOT_STARTED: { label: 'Not Started', variant: 'secondary' },
};

const STATUS_ASSIGNMENT: Record<string, { label: string; variant: 'success' | 'default' | 'secondary' | 'warning' }> = {
  GRADED:        { label: 'Graded',       variant: 'success' },
  SUBMITTED:     { label: 'Submitted',    variant: 'warning' },
  NOT_SUBMITTED: { label: 'Not Submitted', variant: 'secondary' },
};

function fmtDate(raw: string | null): string {
  if (!raw) return '—';
  try {
    const d = parseISO(raw);
    return isValid(d) ? format(d, 'dd MMM yyyy') : '—';
  } catch {
    return '—';
  }
}

/** Download an array of objects as a CSV file. */
function downloadCsv(rows: Record<string, unknown>[], filename: string) {
  if (!rows.length) return;
  const headers = Object.keys(rows[0]);
  const csv = [
    headers.join(','),
    ...rows.map((row) =>
      headers
        .map((h) => {
          const v = row[h] ?? '';
          let s = String(v).replace(/"/g, '""');
          // Prefix formula-injection characters so spreadsheet apps don't
          // interpret cell contents as formulas.
          if (/^[=+\-@]/.test(s)) s = `'${s}`;
          return /[",\n]/.test(s) ? `"${s}"` : s;
        })
        .join(','),
    ),
  ].join('\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// ── Column definitions ────────────────────────────────────────────────────────
// Factory functions so callers can inject mode-aware labels via `useModeLabels`.

export function makeCourseColumns(
  lbl: (k: ModeLabelKey) => string,
): ColumnDef<CourseProgressRow>[] {
  return [
    {
      accessorKey: 'teacher_name',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Name" />,
      cell: ({ row }) => (
        <div>
          <p className="font-medium text-slate-900">{row.original.teacher_name}</p>
          <p className="text-xs text-slate-500">{row.original.teacher_email}</p>
        </div>
      ),
    },
    {
      accessorKey: 'role',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Role" />,
      cell: ({ getValue }) => {
        const v = (getValue() as string | undefined) ?? '';
        return (
          <span className="capitalize text-sm text-slate-600">
            {v.replace(/_/g, ' ').toLowerCase() || '—'}
          </span>
        );
      },
    },
    {
      accessorKey: 'grade_level',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Grade / Section" />,
      cell: ({ row }) => {
        const grade = row.original.grade_level;
        const section = row.original.section;
        if (!grade && !section) return <span className="text-slate-400">—</span>;
        return (
          <span className="text-sm text-slate-600">
            {[grade, section].filter(Boolean).join(' · ')}
          </span>
        );
      },
    },
    {
      accessorKey: 'course_title',
      header: ({ column }) => <DataTableColumnHeader column={column} title={lbl('course')} />,
      cell: ({ getValue }) => (
        <span className="text-sm text-slate-700 font-medium">{getValue() as string}</span>
      ),
    },
    {
      accessorKey: 'status',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Status" />,
      cell: ({ getValue }) => {
        const s = getValue() as string;
        const cfg = STATUS_COURSE[s] ?? { label: s, variant: 'secondary' as const };
        return <Badge variant={cfg.variant}>{cfg.label}</Badge>;
      },
    },
    {
      accessorKey: 'deadline',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Deadline" />,
      cell: ({ getValue }) => (
        <span className="text-sm text-slate-600">{fmtDate(getValue() as string | null)}</span>
      ),
    },
    {
      accessorKey: 'completed_at',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Completed" />,
      cell: ({ getValue }) => (
        <span className="text-sm text-slate-600">{fmtDate(getValue() as string | null)}</span>
      ),
    },
  ];
}

export function makeAssignmentColumns(
  lbl: (k: ModeLabelKey) => string,
): ColumnDef<AssignmentStatusRow>[] {
  return [
    {
      accessorKey: 'teacher_name',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Name" />,
      cell: ({ row }) => (
        <div>
          <p className="font-medium text-slate-900">{row.original.teacher_name}</p>
          <p className="text-xs text-slate-500">{row.original.teacher_email}</p>
        </div>
      ),
    },
    {
      accessorKey: 'role',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Role" />,
      cell: ({ getValue }) => {
        const v = (getValue() as string | undefined) ?? '';
        return (
          <span className="capitalize text-sm text-slate-600">
            {v.replace(/_/g, ' ').toLowerCase() || '—'}
          </span>
        );
      },
    },
    {
      accessorKey: 'grade_level',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Grade / Section" />,
      cell: ({ row }) => {
        const grade = row.original.grade_level;
        const section = row.original.section;
        if (!grade && !section) return <span className="text-slate-400">—</span>;
        return (
          <span className="text-sm text-slate-600">
            {[grade, section].filter(Boolean).join(' · ')}
          </span>
        );
      },
    },
    {
      accessorKey: 'assignment_title',
      header: ({ column }) => <DataTableColumnHeader column={column} title={lbl('assignment')} />,
      cell: ({ getValue }) => (
        <span className="text-sm text-slate-700 font-medium">{getValue() as string}</span>
      ),
    },
    {
      accessorKey: 'status',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Status" />,
      cell: ({ getValue }) => {
        const s = getValue() as string;
        const cfg = STATUS_ASSIGNMENT[s] ?? { label: s, variant: 'secondary' as const };
        return <Badge variant={cfg.variant}>{cfg.label}</Badge>;
      },
    },
    {
      accessorKey: 'due_date',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Due Date" />,
      cell: ({ getValue }) => (
        <span className="text-sm text-slate-600">{fmtDate(getValue() as string | null)}</span>
      ),
    },
    {
      accessorKey: 'submitted_at',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Submitted" />,
      cell: ({ getValue }) => (
        <span className="text-sm text-slate-600">{fmtDate(getValue() as string | null)}</span>
      ),
    },
  ];
}

// ── Summary stats bar ─────────────────────────────────────────────────────────

function CourseSummary({ rows }: { rows: CourseProgressRow[] }) {
  const total     = rows.length;
  const completed = rows.filter((r) => r.status === 'COMPLETED').length;
  const inProg    = rows.filter((r) => r.status === 'IN_PROGRESS').length;
  const notStart  = rows.filter((r) => r.status === 'NOT_STARTED').length;
  const pct       = total > 0 ? Math.round((completed / total) * 100) : 0;

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      {[
        { label: 'Total',       value: total,     color: 'text-slate-900' },
        { label: 'Completed',   value: completed,  color: 'text-emerald-700' },
        { label: 'In Progress', value: inProg,     color: 'text-amber-700' },
        { label: 'Not Started', value: notStart,   color: 'text-slate-500' },
      ].map(({ label, value, color }) => (
        <div key={label} className="rounded-xl border border-slate-200/80 bg-white p-4 text-center shadow-sm">
          <p className={`text-2xl font-bold ${color}`}>{value}</p>
          <p className="mt-0.5 text-xs text-slate-500">{label}</p>
        </div>
      ))}
      {total > 0 && (
        <div className="sm:col-span-4 rounded-xl border border-slate-200/80 bg-white p-4 shadow-sm">
          <div className="flex items-center justify-between mb-2">
            <p className="text-xs font-medium text-slate-500">Overall Completion</p>
            <p className="text-sm font-bold text-slate-900">{pct}%</p>
          </div>
          <div className="h-2 rounded-full bg-slate-100">
            <div
              className="h-2 rounded-full bg-emerald-500 transition-all duration-500"
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>
      )}
    </div>
  );
}

function AssignmentSummary({ rows }: { rows: AssignmentStatusRow[] }) {
  const total     = rows.length;
  const graded    = rows.filter((r) => r.status === 'GRADED').length;
  const submitted = rows.filter((r) => r.status === 'SUBMITTED').length;
  const pending   = rows.filter((r) => r.status === 'NOT_SUBMITTED').length;
  const pct       = total > 0 ? Math.round(((graded + submitted) / total) * 100) : 0;

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      {[
        { label: 'Total',         value: total,     color: 'text-slate-900' },
        { label: 'Graded',        value: graded,    color: 'text-emerald-700' },
        { label: 'Submitted',     value: submitted, color: 'text-amber-700' },
        { label: 'Not Submitted', value: pending,   color: 'text-slate-500' },
      ].map(({ label, value, color }) => (
        <div key={label} className="rounded-xl border border-slate-200/80 bg-white p-4 text-center shadow-sm">
          <p className={`text-2xl font-bold ${color}`}>{value}</p>
          <p className="mt-0.5 text-xs text-slate-500">{label}</p>
        </div>
      ))}
      {total > 0 && (
        <div className="sm:col-span-4 rounded-xl border border-slate-200/80 bg-white p-4 shadow-sm">
          <div className="flex items-center justify-between mb-2">
            <p className="text-xs font-medium text-slate-500">Response Rate (Submitted + Graded)</p>
            <p className="text-sm font-bold text-slate-900">{pct}%</p>
          </div>
          <div className="h-2 rounded-full bg-slate-100">
            <div
              className="h-2 rounded-full bg-blue-500 transition-all duration-500"
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export const GradebookPage: React.FC = () => {
  usePageTitle('Gradebook');

  const [activeTab, setActiveTab]       = useState<GradebookTab>('course');
  const [roleFilter, setRoleFilter]     = useState<RoleFilter>('all');
  const [courseId, setCourseId]         = useState('');
  const [courseStatus, setCourseStatus] = useState('');
  const [assignmentId, setAssignmentId] = useState('');
  const [asnStatus, setAsnStatus]       = useState('');

  const { label } = useModeLabels();
  const courseColumns    = useMemo(() => makeCourseColumns(label),    [label]);
  const assignmentColumns = useMemo(() => makeAssignmentColumns(label), [label]);

  // ── Reference data ────────────────────────────────────────────────────
  const { data: courses = [] } = useQuery({
    queryKey: ['gradebookCourses'],
    queryFn: adminReportsService.listCourses,
  });

  const { data: assignments = [] } = useQuery({
    queryKey: ['gradebookAssignments'],
    queryFn: () => adminReportsService.listAssignments(),
  });

  // ── Course-progress report ───────────────────────────────────────────
  const {
    data: courseReport,
    isLoading: courseLoading,
    isFetching: courseFetching,
  } = useQuery({
    queryKey: ['gradebookCourseProgress', courseId, courseStatus, roleFilter],
    queryFn: () =>
      adminReportsService.courseProgress({
        course_id: courseId,
        status: courseStatus || undefined,
        role: roleFilter === 'all' ? undefined : roleFilter,
      }),
    enabled: activeTab === 'course' && !!courseId,
  });

  // ── Assignment-status report ─────────────────────────────────────────
  const {
    data: asnReport,
    isLoading: asnLoading,
    isFetching: asnFetching,
  } = useQuery({
    queryKey: ['gradebookAssignmentStatus', assignmentId, asnStatus, roleFilter],
    queryFn: () =>
      adminReportsService.assignmentStatus({
        assignment_id: assignmentId,
        status: asnStatus || undefined,
        role: roleFilter === 'all' ? undefined : roleFilter,
      }),
    enabled: activeTab === 'assignment' && !!assignmentId,
  });

  // ── Derived data ──────────────────────────────────────────────────────
  const courseRows   = useMemo(() => courseReport?.results ?? [], [courseReport]);
  const asnRows      = useMemo(() => asnReport?.results ?? [], [asnReport]);
  const isLoading    = activeTab === 'course' ? courseLoading : asnLoading;
  const isFetching   = activeTab === 'course' ? courseFetching : asnFetching;
  const hasData      = activeTab === 'course' ? courseRows.length > 0 : asnRows.length > 0;
  const needsSelect  = activeTab === 'course' ? !courseId : !assignmentId;

  // ── Export ─────────────────────────────────────────────────────────────
  const handleExport = () => {
    if (activeTab === 'course') {
      const courseName = courses.find((c) => c.id === courseId)?.title ?? 'course';
      downloadCsv(
        courseRows.map((r) => ({
          Name:        r.teacher_name,
          Email:       r.teacher_email,
          Role:        r.role ?? '',
          Grade:       r.grade_level ?? '',
          Section:     r.section ?? '',
          Course:      r.course_title,
          Status:      r.status,
          Deadline:    r.deadline ?? '',
          'Completed At': r.completed_at ?? '',
        })),
        `gradebook-${courseName.replace(/\s+/g, '-')}.csv`,
      );
    } else {
      const asnName = assignments.find((a) => a.id === assignmentId)?.title ?? 'assignment';
      downloadCsv(
        asnRows.map((r) => ({
          Name:         r.teacher_name,
          Email:        r.teacher_email,
          Role:         r.role ?? '',
          Grade:        r.grade_level ?? '',
          Section:      r.section ?? '',
          Assignment:   r.assignment_title,
          Status:       r.status,
          'Due Date':   r.due_date ?? '',
          'Submitted At': r.submitted_at ?? '',
        })),
        `gradebook-${asnName.replace(/\s+/g, '-')}.csv`,
      );
    }
  };

  // ── Render ─────────────────────────────────────────────────────────────
  return (
    <div className="space-y-6">
      {/* ── Header ── */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-[22px] font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <TableCellsIcon className="h-6 w-6 text-primary-600" />
            Gradebook
          </h1>
          <p className="mt-1 text-[13px] text-slate-500">
            Track course progress and assignment completion across all teachers and students.
          </p>
        </div>

        {hasData && (
          <Button
            variant="outline"
            onClick={handleExport}
            className="flex items-center gap-2 shrink-0"
          >
            <ArrowDownTrayIcon className="h-4 w-4" />
            Export CSV
          </Button>
        )}
      </div>

      {/* ── Tab switcher ── */}
      <div className="flex items-center gap-1 rounded-xl bg-slate-100 p-1 w-fit">
        {(
          [
            { id: 'course' as const,     label: 'Course Progress', Icon: AcademicCapIcon },
            { id: 'assignment' as const, label: 'Assignments',     Icon: ClipboardDocumentListIcon },
          ] as const
        ).map(({ id, label, Icon }) => (
          <button
            key={id}
            type="button"
            onClick={() => setActiveTab(id)}
            className={`flex items-center gap-1.5 rounded-lg px-4 py-2 text-[13px] font-medium transition-colors cursor-pointer ${
              activeTab === id
                ? 'bg-white text-slate-900 shadow-sm'
                : 'text-slate-500 hover:text-slate-700'
            }`}
          >
            <Icon className="h-4 w-4" />
            {label}
          </button>
        ))}
      </div>

      {/* ── Filter row ── */}
      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-200/80 bg-white p-4 shadow-sm">
        <FunnelIcon className="h-4 w-4 text-slate-400 shrink-0" />

        {/* Course / Assignment picker */}
        {activeTab === 'course' ? (
          <select
            value={courseId}
            onChange={(e) => setCourseId(e.target.value)}
            className="rounded-lg border border-slate-200 px-3 py-2 text-[13px] text-slate-700 focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-200 cursor-pointer min-w-[200px]"
          >
            <option value="">— Select a course —</option>
            {courses.map((c) => (
              <option key={c.id} value={c.id}>{c.title}</option>
            ))}
          </select>
        ) : (
          <select
            value={assignmentId}
            onChange={(e) => setAssignmentId(e.target.value)}
            className="rounded-lg border border-slate-200 px-3 py-2 text-[13px] text-slate-700 focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-200 cursor-pointer min-w-[200px]"
          >
            <option value="">— Select an assignment —</option>
            {assignments.map((a) => (
              <option key={a.id} value={a.id}>{a.title}</option>
            ))}
          </select>
        )}

        {/* Role filter */}
        <div className="flex items-center gap-1 rounded-lg border border-slate-200 p-1">
          {(
            [
              { id: 'all' as const,      label: 'All',      Icon: null },
              { id: 'teachers' as const, label: 'Teachers', Icon: UserGroupIcon },
              { id: 'students' as const, label: 'Students', Icon: UsersIcon },
            ] as const
          ).map(({ id, label, Icon }) => (
            <button
              key={id}
              type="button"
              onClick={() => setRoleFilter(id)}
              className={`flex items-center gap-1 rounded px-3 py-1.5 text-[12px] font-medium transition-colors cursor-pointer ${
                roleFilter === id
                  ? 'bg-primary-600 text-white'
                  : 'text-slate-600 hover:bg-slate-100'
              }`}
            >
              {Icon && <Icon className="h-3.5 w-3.5" />}
              {label}
            </button>
          ))}
        </div>

        {/* Status filter */}
        {activeTab === 'course' ? (
          <select
            value={courseStatus}
            onChange={(e) => setCourseStatus(e.target.value)}
            className="rounded-lg border border-slate-200 px-3 py-2 text-[13px] text-slate-700 focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-200 cursor-pointer"
          >
            <option value="">All Statuses</option>
            <option value="COMPLETED">Completed</option>
            <option value="IN_PROGRESS">In Progress</option>
            <option value="NOT_STARTED">Not Started</option>
          </select>
        ) : (
          <select
            value={asnStatus}
            onChange={(e) => setAsnStatus(e.target.value)}
            className="rounded-lg border border-slate-200 px-3 py-2 text-[13px] text-slate-700 focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-200 cursor-pointer"
          >
            <option value="">All Statuses</option>
            <option value="GRADED">Graded</option>
            <option value="SUBMITTED">Submitted</option>
            <option value="NOT_SUBMITTED">Not Submitted</option>
          </select>
        )}

        {isFetching && (
          <span className="text-xs text-slate-400 ml-auto">Refreshing…</span>
        )}
      </div>

      {/* ── Content area ── */}
      {needsSelect ? (
        <div className="rounded-xl border-2 border-dashed border-slate-200 bg-white p-12 text-center">
          {activeTab === 'course' ? (
            <AcademicCapIcon className="mx-auto h-12 w-12 text-slate-300" />
          ) : (
            <ClipboardDocumentListIcon className="mx-auto h-12 w-12 text-slate-300" />
          )}
          <p className="mt-3 text-sm font-medium text-slate-600">
            Select a {activeTab === 'course' ? 'course' : 'assignment'} to view gradebook data
          </p>
          <p className="mt-1 text-xs text-slate-400">
            Use the filter above to choose a {activeTab === 'course' ? 'course' : 'assignment'}.
          </p>
        </div>
      ) : isLoading ? (
        <div className="flex justify-center py-16">
          <Loading />
        </div>
      ) : (
        <div className="space-y-4">
          {/* Summary stats */}
          {activeTab === 'course' && courseRows.length > 0 && (
            <CourseSummary rows={courseRows} />
          )}
          {activeTab === 'assignment' && asnRows.length > 0 && (
            <AssignmentSummary rows={asnRows} />
          )}

          {/* DataTable */}
          <div className="rounded-xl border border-slate-200/80 bg-white shadow-sm p-4">
            {activeTab === 'course' ? (
              <DataTable
                columns={courseColumns}
                data={courseRows}
                filterColumn="teacher_name"
                filterPlaceholder="Search by name…"
                pageSize={15}
                emptyMessage="No records found for the selected filters."
              />
            ) : (
              <DataTable
                columns={assignmentColumns}
                data={asnRows}
                filterColumn="teacher_name"
                filterPlaceholder="Search by name…"
                pageSize={15}
                emptyMessage="No records found for the selected filters."
              />
            )}
          </div>
        </div>
      )}
    </div>
  );
};
