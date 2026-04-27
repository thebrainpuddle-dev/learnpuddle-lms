// src/pages/teacher/MasteryHistoryPage.tsx
//
// TASK-018 — Full Mastery Points ledger for the logged-in teacher.
//
// Complements the MP stat card on AchievementsPage with:
//   - paginated DataTable of every MP transaction
//   - source filter (Quiz / Assignment / Course Bonus / Admin Adjust)
//   - CSV export with spreadsheet formula-injection hardening
//     (mirrors the approach used in GradebookPage)

import React, { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { format, parseISO, isValid } from 'date-fns';
import type { ColumnDef } from '@tanstack/react-table';
import {
  ArrowDownTrayIcon,
  ArrowLeftIcon,
  SparklesIcon,
} from '@heroicons/react/24/outline';

import { DataTable, DataTableColumnHeader } from '../../components/ui/data-table';
import { Button } from '../../components/common/Button';
import { Loading } from '../../components/common';
import { usePageTitle } from '../../hooks/usePageTitle';
import {
  masteryService,
  mpToNumber,
  MASTERY_REASON_LABELS,
  type MasteryReason,
  type MasteryTransaction,
} from '../../services/masteryService';

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtDate(raw: string | null): string {
  if (!raw) return '—';
  try {
    const d = parseISO(raw);
    return isValid(d) ? format(d, 'dd MMM yyyy, HH:mm') : '—';
  } catch {
    return '—';
  }
}

const REASON_BADGE_CLASSES: Record<MasteryReason, string> = {
  quiz_mastery: 'bg-indigo-100 text-indigo-800',
  assignment_mastery: 'bg-violet-100 text-violet-800',
  course_mastery_bonus: 'bg-emerald-100 text-emerald-800',
  admin_adjust: 'bg-gray-100 text-gray-800',
};

const REASON_FILTER_OPTIONS: Array<{ value: '' | MasteryReason; label: string }> = [
  { value: '', label: 'All sources' },
  { value: 'quiz_mastery', label: 'Quiz mastery' },
  { value: 'assignment_mastery', label: 'Assignment mastery' },
  { value: 'course_mastery_bonus', label: 'Course bonus' },
  { value: 'admin_adjust', label: 'Admin adjust' },
];

// ── CSV export (formula-injection hardened) ───────────────────────────────────

/**
 * Download a list of plain-value rows as a CSV file.
 * - Escapes embedded quotes.
 * - Prefixes values starting with `=`, `+`, `-`, `@` with an apostrophe so
 *   Excel / Google Sheets don't interpret them as formulas.
 *   (Mirrors the hardening used in `GradebookPage.tsx`.)
 */
export function downloadMasteryCsv(
  rows: Record<string, unknown>[],
  filename: string,
): void {
  if (!rows.length) return;
  const headers = Object.keys(rows[0]);
  const csv = [
    headers.join(','),
    ...rows.map((row) =>
      headers
        .map((h) => {
          const v = row[h] ?? '';
          let s = String(v).replace(/"/g, '""');
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

// ── Page ──────────────────────────────────────────────────────────────────────

export const MasteryHistoryPage: React.FC = () => {
  usePageTitle('Mastery Points');

  const [page, setPage] = useState(1);
  const [source, setSource] = useState<'' | MasteryReason>('');

  const historyQ = useQuery({
    queryKey: ['teacherMasteryHistory', page, source],
    queryFn: () =>
      masteryService.getTeacherHistory({
        page,
        source: source || undefined,
      }),
  });

  const summaryQ = useQuery({
    queryKey: ['teacherMasterySummary'],
    queryFn: () => masteryService.getTeacherSummary(),
  });

  const rows = historyQ.data?.results ?? [];
  const count = historyQ.data?.count ?? 0;
  const hasNext = Boolean(historyQ.data?.next);
  const hasPrev = Boolean(historyQ.data?.previous);

  // Client-side filter-by-source mirror so the local filter works even if
  // the backend ignores the query param. Keeps UX responsive while the BE
  // catches up.
  const filteredRows = useMemo<MasteryTransaction[]>(() => {
    if (!source) return rows;
    return rows.filter((r) => r.reason === source);
  }, [rows, source]);

  const columns: ColumnDef<MasteryTransaction>[] = useMemo(
    () => [
      {
        accessorKey: 'created_at',
        header: ({ column }) => (
          <DataTableColumnHeader column={column} title="Date" />
        ),
        cell: ({ getValue }) => (
          <span
            className="text-xs text-gray-500 tabular-nums whitespace-nowrap"
            data-testid="mp-row-date"
          >
            {fmtDate(getValue() as string)}
          </span>
        ),
      },
      {
        accessorKey: 'reason',
        header: 'Source',
        cell: ({ getValue }) => {
          const r = getValue() as MasteryReason;
          const cls = REASON_BADGE_CLASSES[r] ?? 'bg-gray-100 text-gray-800';
          return (
            <span
              className={`inline-flex rounded-full px-2 py-0.5 text-[11px] font-medium ${cls}`}
              data-testid="mp-row-reason"
            >
              {MASTERY_REASON_LABELS[r] ?? r}
            </span>
          );
        },
      },
      {
        accessorKey: 'description',
        header: 'Reference',
        cell: ({ row }) => {
          const tx = row.original;
          const detail = tx.description || tx.reference_type || '—';
          return (
            <div className="min-w-0">
              <p
                className="text-sm text-gray-700 line-clamp-1"
                data-testid="mp-row-description"
              >
                {detail}
              </p>
              {tx.reference_type && (
                <p className="text-[11px] text-gray-400 truncate">
                  {tx.reference_type}
                </p>
              )}
            </div>
          );
        },
      },
      {
        accessorKey: 'amount',
        header: ({ column }) => (
          <DataTableColumnHeader column={column} title="MP" />
        ),
        cell: ({ getValue }) => {
          const n = mpToNumber(getValue() as string);
          const positive = n >= 0;
          return (
            <span
              className={`text-sm font-semibold tabular-nums ${
                positive ? 'text-emerald-600' : 'text-red-600'
              }`}
              data-testid="mp-row-amount"
            >
              {positive ? '+' : ''}
              {n.toFixed(2)}
            </span>
          );
        },
      },
    ],
    [],
  );

  const handleExport = () => {
    if (!filteredRows.length) return;
    const exportRows = filteredRows.map((tx) => ({
      Date: tx.created_at,
      Source: MASTERY_REASON_LABELS[tx.reason] ?? tx.reason,
      Description: tx.description || '',
      Reference: tx.reference_type || '',
      MP: mpToNumber(tx.amount).toFixed(2),
    }));
    const stamp = format(new Date(), 'yyyy-MM-dd');
    downloadMasteryCsv(exportRows, `mastery-points-${stamp}.csv`);
  };

  const summary = summaryQ.data;
  const totalMp = mpToNumber(summary?.total_mastery_points);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <Link
            to="/teacher/achievements"
            className="inline-flex items-center gap-1 text-xs font-medium text-primary-600 hover:text-primary-700"
            data-testid="mastery-back-to-achievements"
          >
            <ArrowLeftIcon className="h-3.5 w-3.5" />
            Back to Achievements
          </Link>
          <h1 className="text-2xl font-bold text-gray-900 mt-1">
            Mastery Points
          </h1>
          <p className="mt-1 text-sm text-gray-500">
            Every quiz, assignment and course bonus you've earned MP for.
          </p>
        </div>
        <div className="text-right">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
            Total MP
          </p>
          <p
            className="text-2xl font-bold text-gray-900 tabular-nums"
            data-testid="mastery-total-mp"
          >
            {totalMp.toFixed(2)}
          </p>
          {summary && (
            <p className="text-[11px] text-gray-400 mt-0.5">
              {mpToNumber(summary.mp_this_week).toFixed(2)} this week ·{' '}
              {mpToNumber(summary.mp_this_month).toFixed(2)} this month
            </p>
          )}
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-3 justify-between">
        <div className="flex items-center gap-3 flex-wrap">
          <label className="text-xs font-medium text-gray-500 uppercase tracking-wide">
            Source
          </label>
          <select
            value={source}
            onChange={(e) => {
              setSource(e.target.value as '' | MasteryReason);
              setPage(1);
            }}
            className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm shadow-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500 cursor-pointer"
            data-testid="mastery-source-filter"
          >
            {REASON_FILTER_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
          {source && (
            <button
              type="button"
              onClick={() => {
                setSource('');
                setPage(1);
              }}
              className="text-xs text-gray-500 hover:text-gray-700 underline cursor-pointer"
            >
              Clear
            </button>
          )}
        </div>
        <Button
          size="sm"
          variant="outline"
          leftIcon={<ArrowDownTrayIcon className="h-4 w-4" />}
          disabled={!filteredRows.length}
          onClick={handleExport}
          data-testid="mastery-export-csv"
        >
          Export CSV
        </Button>
      </div>

      {/* Table */}
      {historyQ.isLoading ? (
        <Loading />
      ) : filteredRows.length === 0 ? (
        <div className="rounded-xl border border-dashed border-gray-200 bg-white p-12 text-center">
          <SparklesIcon className="h-10 w-10 text-gray-300 mx-auto mb-3" />
          <p className="text-sm text-gray-500">
            No Mastery Point transactions yet. Earn your first MP by clearing a
            quiz or assignment at mastery level.
          </p>
        </div>
      ) : (
        <DataTable
          columns={columns}
          data={filteredRows}
          emptyMessage="No MP transactions match this filter."
        />
      )}

      {/* Pagination controls (server-side) */}
      {(hasNext || hasPrev) && (
        <div className="flex items-center justify-between">
          <p className="text-xs text-gray-500 tabular-nums">
            Showing page {page} · {count} total transaction
            {count === 1 ? '' : 's'}
          </p>
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              disabled={!hasPrev}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              data-testid="mastery-page-prev"
            >
              Previous
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={!hasNext}
              onClick={() => setPage((p) => p + 1)}
              data-testid="mastery-page-next"
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  );
};

export default MasteryHistoryPage;
