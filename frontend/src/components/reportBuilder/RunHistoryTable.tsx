// src/components/reportBuilder/RunHistoryTable.tsx
//
// Shows the run history for one report definition.
// Columns: status badge | started | finished | row count | actions.

import React from 'react';
import { ArrowDownTrayIcon, ArrowPathIcon } from '@heroicons/react/24/outline';
import { Badge } from '../ui/badge';
import type {
  ReportRunRecord,
  ReportRunStatus,
} from '../../services/reportBuilderService';

export interface RunHistoryTableProps {
  runs: ReportRunRecord[];
  isLoading?: boolean;
  /** Called when the user clicks the download link of a successful run. */
  onDownload: (runId: string) => void;
  /** Whether a download lookup is in flight. */
  downloadingRunId?: string | null;
}

function statusVariant(status: ReportRunStatus): 'success' | 'destructive' | 'warning' | 'secondary' {
  switch (status) {
    case 'success':
      return 'success';
    case 'error':
      return 'destructive';
    case 'running':
      return 'warning';
    default:
      return 'secondary';
  }
}

function formatDate(value: string | null | undefined): string {
  if (!value) return '—';
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

export const RunHistoryTable: React.FC<RunHistoryTableProps> = ({
  runs,
  isLoading = false,
  onDownload,
  downloadingRunId = null,
}) => {
  if (isLoading && runs.length === 0) {
    return (
      <div
        className="flex items-center justify-center rounded-lg border border-gray-200 p-8 text-sm text-gray-500"
        data-testid="run-history-loading"
      >
        <ArrowPathIcon className="mr-2 h-4 w-4 animate-spin" />
        Loading run history…
      </div>
    );
  }

  if (runs.length === 0) {
    return (
      <div
        className="rounded-lg border border-dashed border-gray-300 p-8 text-center text-sm text-gray-500"
        data-testid="run-history-empty"
      >
        No runs yet. Run the report or export to CSV to see history here.
      </div>
    );
  }

  return (
    <div
      className="overflow-x-auto rounded-lg border border-gray-200"
      data-testid="run-history-table"
    >
      <table className="min-w-full divide-y divide-gray-200 text-sm">
        <thead className="bg-gray-50">
          <tr>
            <th scope="col" className="px-3 py-2 text-left font-medium text-gray-700">
              Status
            </th>
            <th scope="col" className="px-3 py-2 text-left font-medium text-gray-700">
              Started
            </th>
            <th scope="col" className="px-3 py-2 text-left font-medium text-gray-700">
              Finished
            </th>
            <th scope="col" className="px-3 py-2 text-right font-medium text-gray-700">
              Rows
            </th>
            <th scope="col" className="px-3 py-2 text-right font-medium text-gray-700">
              Actions
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100 bg-white">
          {runs.map((run) => (
            <tr key={run.id} data-testid={`run-row-${run.id}`}>
              <td className="px-3 py-2">
                <Badge variant={statusVariant(run.status)}>{run.status}</Badge>
              </td>
              <td className="px-3 py-2 text-gray-700 whitespace-nowrap">
                {formatDate(run.started_at)}
              </td>
              <td className="px-3 py-2 text-gray-700 whitespace-nowrap">
                {formatDate(run.finished_at)}
              </td>
              <td className="px-3 py-2 text-right text-gray-700">{run.row_count}</td>
              <td className="px-3 py-2 text-right">
                {run.status === 'success' && run.artifact_path ? (
                  <button
                    type="button"
                    onClick={() => onDownload(run.id)}
                    disabled={downloadingRunId === run.id}
                    data-testid={`run-download-${run.id}`}
                    className="inline-flex items-center gap-1 rounded-md border border-gray-300 bg-white px-2 py-1 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                  >
                    <ArrowDownTrayIcon className="h-3.5 w-3.5" />
                    {downloadingRunId === run.id ? 'Preparing…' : 'Download CSV'}
                  </button>
                ) : (
                  <span className="text-xs text-gray-400">—</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};
