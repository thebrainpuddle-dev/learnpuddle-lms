// src/components/reportBuilder/PreviewTable.tsx
//
// Lightweight tabular renderer for the JSON rows returned by POST /definitions/{id}/run/.
//
// Scope note (per spec): backend returns rows as a list of dicts — we do not
// reconstruct types, we just stringify each cell. Client-side pagination kicks
// in for > PAGE_SIZE rows to keep the DOM small without pulling in a
// virtualised-list dependency.

import React, { useMemo, useState } from 'react';

const PAGE_SIZE = 50;

export interface PreviewTableProps {
  rows: Array<Record<string, unknown>>;
  rowCount?: number;
  /** Optional inline error message, e.g. "ROW_CAP_EXCEEDED". */
  errorMessage?: string | null;
}

function cellToString(value: unknown): string {
  if (value === null || value === undefined) return '';
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  }
  return String(value);
}

export const PreviewTable: React.FC<PreviewTableProps> = ({
  rows,
  rowCount,
  errorMessage = null,
}) => {
  const [page, setPage] = useState(0);

  // Derive column headers from the first row. Keys from later rows are ignored
  // for the header set but still rendered if present (defensive against
  // heterogeneous dicts in the response).
  const columns = useMemo<string[]>(() => {
    if (rows.length === 0) return [];
    return Object.keys(rows[0] ?? {});
  }, [rows]);

  const totalPages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  const pageStart = page * PAGE_SIZE;
  const pageEnd = Math.min(pageStart + PAGE_SIZE, rows.length);
  const visible = rows.slice(pageStart, pageEnd);

  if (errorMessage) {
    return (
      <div
        className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700"
        data-testid="preview-error"
        role="alert"
      >
        {errorMessage}
      </div>
    );
  }

  if (rows.length === 0) {
    return (
      <div
        className="rounded-lg border border-dashed border-gray-300 p-8 text-center text-sm text-gray-500"
        data-testid="preview-empty"
      >
        No rows returned.
      </div>
    );
  }

  return (
    <div className="space-y-2" data-testid="preview-table">
      <div className="flex items-center justify-between text-xs text-gray-500">
        <span>
          Showing {pageStart + 1}–{pageEnd} of {rowCount ?? rows.length} rows
        </span>
        {totalPages > 1 && (
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              data-testid="preview-prev"
              className="rounded-md border border-gray-300 px-2 py-1 disabled:opacity-50"
            >
              Previous
            </button>
            <span>
              Page {page + 1} / {totalPages}
            </span>
            <button
              type="button"
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              disabled={page >= totalPages - 1}
              data-testid="preview-next"
              className="rounded-md border border-gray-300 px-2 py-1 disabled:opacity-50"
            >
              Next
            </button>
          </div>
        )}
      </div>

      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="min-w-full divide-y divide-gray-200 text-sm">
          <thead className="bg-gray-50">
            <tr>
              {columns.map((col) => (
                <th
                  key={col}
                  scope="col"
                  className="px-3 py-2 text-left font-medium text-gray-700 whitespace-nowrap"
                >
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 bg-white">
            {visible.map((row, i) => (
              <tr key={pageStart + i} data-testid={`preview-row-${pageStart + i}`}>
                {columns.map((col) => (
                  <td
                    key={col}
                    className="px-3 py-2 text-gray-700 whitespace-nowrap"
                  >
                    {cellToString(row[col])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
