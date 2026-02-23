import React from 'react';
import type { OpsRouteError } from '../../../services/superAdminService';

interface IncidentDrawerProps {
  open: boolean;
  loading: boolean;
  onClose: () => void;
  detail: {
    error_group: OpsRouteError;
    recent_replay_steps: Array<{
      id: string;
      run_id: string;
      run_status: string;
      case_id: string;
      response_status: number | null;
      created_at: string;
    }>;
  } | null;
}

export const IncidentDrawer: React.FC<IncidentDrawerProps> = ({ open, loading, onClose, detail }) => {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/30">
      <div className="h-full w-full max-w-lg overflow-y-auto bg-white shadow-2xl">
        <div className="sticky top-0 flex items-center justify-between border-b border-gray-200 bg-white px-4 py-3">
          <h3 className="text-sm font-semibold text-gray-900">Error Group Details</h3>
          <button type="button" onClick={onClose} className="rounded border border-gray-300 px-2 py-1 text-xs text-gray-700">
            Close
          </button>
        </div>
        <div className="space-y-3 p-4 text-sm">
          {loading ? (
            <p className="text-gray-500">Loading details...</p>
          ) : !detail ? (
            <p className="text-gray-500">No detail loaded.</p>
          ) : (
            <>
              <div className="rounded-lg border border-gray-200 bg-gray-50 p-3">
                <div className="text-xs uppercase tracking-wide text-gray-500">Endpoint</div>
                <div className="mt-1 break-all font-medium text-gray-900">
                  {detail.error_group.method} {detail.error_group.endpoint}
                </div>
                <div className="mt-2 text-xs text-gray-600">
                  tab={detail.error_group.tab_key || '-'} | portal={detail.error_group.portal}
                </div>
                <div className="mt-1 text-xs text-gray-600">
                  request_id={detail.error_group.last_request_id || '-'}
                </div>
              </div>

              <div>
                <div className="mb-2 text-xs uppercase tracking-wide text-gray-500">Sample Response Excerpt</div>
                <pre className="max-h-44 overflow-auto rounded-lg border border-gray-200 bg-white p-2 text-xs text-gray-700">
                  {detail.error_group.sample_response_excerpt || 'N/A'}
                </pre>
              </div>

              <div>
                <div className="mb-2 text-xs uppercase tracking-wide text-gray-500">Recent Replay Steps</div>
                <div className="space-y-2">
                  {detail.recent_replay_steps.length === 0 ? (
                    <p className="text-xs text-gray-500">No linked replay steps.</p>
                  ) : (
                    detail.recent_replay_steps.map((step) => (
                      <div key={step.id} className="rounded border border-gray-200 px-3 py-2 text-xs text-gray-700">
                        <div className="font-medium">{step.case_id}</div>
                        <div className="mt-1 text-gray-500">
                          run={step.run_id.slice(0, 8)} ({step.run_status}) | status={step.response_status ?? '-'}
                        </div>
                        <div className="mt-1 text-gray-500">{new Date(step.created_at).toLocaleString()}</div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

