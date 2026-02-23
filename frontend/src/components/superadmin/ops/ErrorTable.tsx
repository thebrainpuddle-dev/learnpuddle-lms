import React from 'react';
import type { OpsRouteError } from '../../../services/superAdminService';

interface ErrorTableProps {
  errors: OpsRouteError[];
  loading?: boolean;
  lockingId?: string | null;
  onLock: (errorGroupId: string) => void;
  onReplay: (error: OpsRouteError) => void;
  onSelect: (error: OpsRouteError) => void;
}

export const ErrorTable: React.FC<ErrorTableProps> = ({
  errors,
  loading = false,
  lockingId,
  onLock,
  onReplay,
  onSelect,
}) => {
  return (
    <section className="rounded-xl border border-gray-200 bg-white">
      <div className="border-b border-gray-100 px-4 py-3">
        <h3 className="text-sm font-semibold text-gray-900">Problematic Errors (500/429)</h3>
        <p className="mt-1 text-xs text-gray-500">Shows locked and active problematic endpoint groups with tab mapping.</p>
      </div>
      <div className="max-h-[420px] overflow-auto">
        {loading ? (
          <div className="px-4 py-6 text-sm text-gray-500">Loading errors...</div>
        ) : errors.length === 0 ? (
          <div className="px-4 py-6 text-sm text-gray-500">No 500/429 errors in selected window.</div>
        ) : (
          <table className="min-w-full text-left text-sm">
            <thead className="sticky top-0 bg-gray-50 text-xs uppercase tracking-wide text-gray-500">
              <tr>
                <th className="px-3 py-2">Code</th>
                <th className="px-3 py-2">Tab</th>
                <th className="px-3 py-2">Endpoint</th>
                <th className="px-3 py-2">Count</th>
                <th className="px-3 py-2">Last Seen</th>
                <th className="px-3 py-2">Actions</th>
              </tr>
            </thead>
            <tbody>
              {errors.map((error) => (
                <tr key={error.id} className="border-t border-gray-100 align-top">
                  <td className="px-3 py-3">
                    <span
                      className={`inline-flex rounded px-2 py-0.5 text-xs font-semibold ${
                        error.status_code === 500 ? 'bg-red-100 text-red-700' : 'bg-amber-100 text-amber-700'
                      }`}
                    >
                      {error.status_code}
                    </span>
                  </td>
                  <td className="px-3 py-3 text-gray-700">{error.tab_key || '-'}</td>
                  <td className="px-3 py-3 text-xs text-gray-700">{error.method} {error.endpoint}</td>
                  <td className="px-3 py-3 text-gray-700">{error.total_count}</td>
                  <td className="px-3 py-3 text-xs text-gray-500">{new Date(error.last_seen_at).toLocaleString()}</td>
                  <td className="px-3 py-3">
                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={() => onSelect(error)}
                        className="rounded border border-gray-300 px-2 py-1 text-xs text-gray-700 hover:bg-gray-50"
                      >
                        Details
                      </button>
                      <button
                        type="button"
                        onClick={() => onReplay(error)}
                        className="rounded border border-indigo-200 px-2 py-1 text-xs text-indigo-700 hover:bg-indigo-50"
                      >
                        Replay
                      </button>
                      <button
                        type="button"
                        disabled={error.is_locked || lockingId === error.id}
                        onClick={() => onLock(error.id)}
                        className="rounded bg-slate-800 px-2 py-1 text-xs text-white hover:bg-slate-900 disabled:opacity-50"
                      >
                        {error.is_locked ? 'Locked' : lockingId === error.id ? 'Locking...' : 'Lock Incident'}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
};

