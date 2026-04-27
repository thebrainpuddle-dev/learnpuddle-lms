// src/pages/admin/AssessmentGradebookPage.tsx
//
// Assessment-centric gradebook powered by the TASK-043 backend:
//   GET /api/v1/admin/gradebook/courses/:course_id/
//
// One row per teacher × course with quiz stats, assignment stats and overall
// progress %. Filters are applied client-side by the service (status, score
// range). CSV export is also client-side (see gradebookService.downloadCsv).

import React, { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  TableCellsIcon,
  ArrowDownTrayIcon,
  FunnelIcon,
  AcademicCapIcon,
} from '@heroicons/react/24/outline';
import type { ColumnDef } from '@tanstack/react-table';
import { DataTable, DataTableColumnHeader } from '../../components/ui/data-table';
import { Badge } from '../../components/ui/badge';
import { Button, Loading, useToast } from '../../components/common';
import { usePageTitle } from '../../hooks/usePageTitle';
import {
  gradebookService,
  type GradebookRow,
  type GradebookStatusFilter,
} from '../../services/gradebookService';
import { adminReportsService } from '../../services/adminReportsService';
import { useModeLabels } from '../../hooks/useModeLabels';
import type { ModeLabelKey } from '../../stores/tenantStore';

// ── Columns ─────────────────────────────────────────────────────────────────
// Factory so the component can inject mode-aware labels via `useModeLabels`.

export function makeColumns(lbl: (k: ModeLabelKey) => string): ColumnDef<GradebookRow>[] {
  return [
  {
    accessorKey: 'teacher_name',
    header: ({ column }) => <DataTableColumnHeader column={column} title={lbl('learner')} />,
    cell: ({ row }) => (
      <div>
        <p className="font-medium text-slate-900">{row.original.teacher_name}</p>
        <p className="text-xs text-slate-500">{row.original.teacher_email}</p>
      </div>
    ),
  },
  {
    accessorKey: 'quiz_attempts',
    header: ({ column }) => <DataTableColumnHeader column={column} title="Attempts" />,
    cell: ({ getValue }) => (
      <span className="text-sm text-slate-700 tabular-nums">
        {getValue() as number}
      </span>
    ),
  },
  {
    accessorKey: 'quiz_best_score_percent',
    header: ({ column }) => <DataTableColumnHeader column={column} title="Best Score" />,
    cell: ({ row }) => {
      const pct = Number(row.original.quiz_best_score_percent) || 0;
      const variant =
        row.original.quiz_attempts === 0
          ? 'secondary'
          : pct >= 70
          ? 'success'
          : pct >= 50
          ? 'warning'
          : 'destructive';
      return (
        <Badge variant={variant}>
          {row.original.quiz_attempts === 0 ? 'Not attempted' : `${pct.toFixed(0)}%`}
        </Badge>
      );
    },
  },
  {
    accessorKey: 'quiz_passed',
    header: ({ column }) => <DataTableColumnHeader column={column} title="Passed" />,
    cell: ({ getValue }) => (
      <span className="text-sm text-slate-700 tabular-nums">
        {getValue() as number}
      </span>
    ),
  },
  {
    accessorKey: 'assignments_submitted',
    header: ({ column }) => <DataTableColumnHeader column={column} title="Assignments" />,
    cell: ({ row }) => (
      <span className="text-sm text-slate-600 tabular-nums">
        {row.original.assignments_graded} graded / {row.original.assignments_submitted} submitted
      </span>
    ),
  },
  {
    accessorKey: 'assignments_avg_score',
    header: ({ column }) => <DataTableColumnHeader column={column} title="Avg Score" />,
    cell: ({ getValue }) => (
      <span className="text-sm text-slate-700 tabular-nums">
        {Number(getValue() as number).toFixed(1)}
      </span>
    ),
  },
  {
    accessorKey: 'progress_percent',
    header: ({ column }) => <DataTableColumnHeader column={column} title="Progress" />,
    cell: ({ getValue }) => {
      const pct = Number(getValue() as number) || 0;
      return (
        <div className="flex items-center gap-2 min-w-[120px]">
          <div className="flex-1 h-2 rounded-full bg-slate-100">
            <div
              className="h-2 rounded-full bg-primary-500"
              style={{ width: `${Math.min(100, Math.max(0, pct))}%` }}
            />
          </div>
          <span className="text-xs font-medium text-slate-700 tabular-nums">
            {pct.toFixed(0)}%
          </span>
        </div>
      );
    },
  },
  ];
}

// ── Page ────────────────────────────────────────────────────────────────────

export const AssessmentGradebookPage: React.FC = () => {
  usePageTitle('Assessment Gradebook');
  const toast = useToast();

  const { label } = useModeLabels();
  const columns = useMemo(() => makeColumns(label), [label]);

  const [courseId, setCourseId] = useState('');
  const [statusFilter, setStatusFilter] =
    useState<GradebookStatusFilter>('all');
  const [minScore, setMinScore] = useState(0);
  const [maxScore, setMaxScore] = useState(100);

  const { data: courses = [] } = useQuery({
    queryKey: ['gradebookCourses'],
    queryFn: adminReportsService.listCourses,
  });

  const {
    data,
    isLoading,
    isFetching,
  } = useQuery({
    queryKey: ['assessmentGradebook', courseId],
    queryFn: () => gradebookService.getCourseGradebook(courseId),
    enabled: !!courseId,
  });

  const rawRows = useMemo(() => data?.results ?? [], [data]);
  const rows = useMemo(
    () =>
      gradebookService.applyFilters(rawRows, {
        statusFilter,
        minScorePercent: minScore,
        maxScorePercent: maxScore,
      }),
    [rawRows, statusFilter, minScore, maxScore],
  );

  const handleExport = () => {
    if (rows.length === 0) {
      toast.warning('Nothing to export', 'No rows match the current filters.');
      return;
    }
    const name =
      courses.find((c) => c.id === courseId)?.title?.replace(/\s+/g, '-') ??
      'course';
    gradebookService.downloadCsv(rows, `gradebook-${name}.csv`);
    toast.success('CSV ready', `Exported ${rows.length} rows.`);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-[22px] font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <TableCellsIcon className="h-6 w-6 text-primary-600" />
            Assessment Gradebook
          </h1>
          <p className="mt-1 text-[13px] text-slate-500">
            Quiz and assignment performance per teacher, aggregated per course.
          </p>
        </div>

        {rows.length > 0 && (
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

      {/* Filter row */}
      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-200/80 bg-white p-4 shadow-sm">
        <FunnelIcon className="h-4 w-4 text-slate-400 shrink-0" />

        <select
          value={courseId}
          onChange={(e) => setCourseId(e.target.value)}
          className="rounded-lg border border-slate-200 px-3 py-2 text-[13px] text-slate-700 focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-200 cursor-pointer min-w-[220px]"
        >
          <option value="">— Select a course —</option>
          {courses.map((c) => (
            <option key={c.id} value={c.id}>{c.title}</option>
          ))}
        </select>

        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as GradebookStatusFilter)}
          className="rounded-lg border border-slate-200 px-3 py-2 text-[13px] text-slate-700 focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-200 cursor-pointer"
        >
          <option value="all">All Statuses</option>
          <option value="passed">Passed at least one</option>
          <option value="failed">Attempted, none passed</option>
          <option value="not_attempted">Not attempted</option>
        </select>

        <div className="flex items-center gap-2">
          <label className="text-[12px] text-slate-500">Score %:</label>
          <input
            type="number"
            min={0}
            max={100}
            value={minScore}
            onChange={(e) =>
              setMinScore(Math.max(0, Math.min(100, Number(e.target.value) || 0)))
            }
            className="w-20 rounded-lg border border-slate-200 px-2 py-1.5 text-[13px] focus:border-primary-400 focus:ring-2 focus:ring-primary-200 focus:outline-none"
            aria-label="Min score"
          />
          <span className="text-slate-400">–</span>
          <input
            type="number"
            min={0}
            max={100}
            value={maxScore}
            onChange={(e) =>
              setMaxScore(Math.max(0, Math.min(100, Number(e.target.value) || 0)))
            }
            className="w-20 rounded-lg border border-slate-200 px-2 py-1.5 text-[13px] focus:border-primary-400 focus:ring-2 focus:ring-primary-200 focus:outline-none"
            aria-label="Max score"
          />
        </div>

        {isFetching && (
          <span className="text-xs text-slate-400 ml-auto">Refreshing…</span>
        )}
      </div>

      {/* Body */}
      {!courseId ? (
        <div className="rounded-xl border-2 border-dashed border-slate-200 bg-white p-12 text-center">
          <AcademicCapIcon className="mx-auto h-12 w-12 text-slate-300" />
          <p className="mt-3 text-sm font-medium text-slate-600">
            Select a course to view assessment data
          </p>
          <p className="mt-1 text-xs text-slate-400">
            Use the filter above to choose a course.
          </p>
        </div>
      ) : isLoading ? (
        <div className="flex justify-center py-16">
          <Loading />
        </div>
      ) : (
        <div className="rounded-xl border border-slate-200/80 bg-white shadow-sm p-4">
          <DataTable
            columns={columns}
            data={rows}
            filterColumn="teacher_name"
            filterPlaceholder="Search teacher…"
            pageSize={15}
            emptyMessage={
              rawRows.length === 0
                ? 'No teachers enrolled in this course yet.'
                : 'No teachers match the current filters.'
            }
          />
        </div>
      )}
    </div>
  );
};

export default AssessmentGradebookPage;
