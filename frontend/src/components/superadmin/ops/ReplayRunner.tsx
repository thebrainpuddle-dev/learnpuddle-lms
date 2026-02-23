import React from 'react';
import type { OpsReplayCase, OpsReplayRun, OpsReplayStep } from '../../../services/superAdminService';

interface ReplayRunnerProps {
  tenantId: string;
  portal: 'TENANT_ADMIN' | 'TEACHER';
  cases: OpsReplayCase[];
  run: OpsReplayRun | null;
  steps: OpsReplayStep[];
  running: boolean;
  onPortalChange: (portal: 'TENANT_ADMIN' | 'TEACHER') => void;
  onRun: (args: {
    tenantId: string;
    portal: 'TENANT_ADMIN' | 'TEACHER';
    caseIds: string[];
    dryRun: boolean;
    priority: 'NORMAL' | 'HIGH';
    params: Record<string, any>;
  }) => void;
}

export const ReplayRunner: React.FC<ReplayRunnerProps> = ({
  tenantId,
  portal,
  cases,
  run,
  steps,
  running,
  onPortalChange,
  onRun,
}) => {
  const [selectedCases, setSelectedCases] = React.useState<string[]>([]);
  const [dryRun, setDryRun] = React.useState(true);
  const [priority, setPriority] = React.useState<'NORMAL' | 'HIGH'>('NORMAL');
  const [paramsText, setParamsText] = React.useState('{}');
  const [paramError, setParamError] = React.useState('');

  React.useEffect(() => {
    const defaultSelection = cases.slice(0, 3).map((item) => item.case_id);
    setSelectedCases(defaultSelection);
  }, [portal, cases]);

  const toggleCase = (caseId: string) => {
    setSelectedCases((prev) => (prev.includes(caseId) ? prev.filter((id) => id !== caseId) : [...prev, caseId]));
  };

  const handleRun = () => {
    if (!selectedCases.length) return;
    try {
      const parsedParams = JSON.parse(paramsText || '{}');
      setParamError('');
      onRun({ tenantId, portal, caseIds: selectedCases, dryRun, priority, params: parsedParams });
    } catch {
      setParamError('Params must be valid JSON.');
    }
  };

  return (
    <section className="rounded-xl border border-gray-200 bg-white">
      <div className="border-b border-gray-100 px-4 py-3">
        <h3 className="text-sm font-semibold text-gray-900">Replay Runner</h3>
        <p className="mt-1 text-xs text-gray-500">Run tab-based retests with dry-run guardrails and per-run traces.</p>
      </div>

      <div className="space-y-3 p-4">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <select
            value={portal}
            onChange={(e) => onPortalChange(e.target.value as 'TENANT_ADMIN' | 'TEACHER')}
            className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm"
          >
            <option value="TENANT_ADMIN">Tenant Admin</option>
            <option value="TEACHER">Teacher</option>
          </select>
          <label className="inline-flex items-center gap-2 text-sm text-gray-700">
            <input type="checkbox" checked={dryRun} onChange={(e) => setDryRun(e.target.checked)} />
            Dry run
          </label>
          <select
            value={priority}
            onChange={(e) => setPriority(e.target.value as 'NORMAL' | 'HIGH')}
            className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm"
          >
            <option value="NORMAL">Priority: Normal</option>
            <option value="HIGH">Priority: High</option>
          </select>
          <button
            type="button"
            onClick={handleRun}
            disabled={!tenantId || !selectedCases.length || running}
            className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {running ? 'Running...' : 'Run Retest'}
          </button>
        </div>

        <div className="rounded-lg border border-gray-200 p-2">
          <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">Case Catalog</div>
          <div className="max-h-48 space-y-1 overflow-y-auto">
            {cases.map((item) => (
              <label key={item.case_id} className="flex cursor-pointer items-start gap-2 rounded px-2 py-1 hover:bg-gray-50">
                <input type="checkbox" checked={selectedCases.includes(item.case_id)} onChange={() => toggleCase(item.case_id)} />
                <span className="text-sm text-gray-800">
                  {item.label}
                  <span className="ml-2 text-xs text-gray-500">[{item.tab}] {item.method} {item.endpoint}</span>
                </span>
              </label>
            ))}
          </div>
        </div>

        <div>
          <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500">Params JSON</label>
          <textarea
            value={paramsText}
            onChange={(e) => setParamsText(e.target.value)}
            className="h-20 w-full rounded-lg border border-gray-300 px-3 py-2 font-mono text-xs"
            placeholder='{"course_id":"...","assignment_id":"..."}'
          />
          {paramError && <p className="mt-1 text-xs text-red-600">{paramError}</p>}
        </div>

        {run && (
          <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-700">
            <div className="font-semibold">Run {run.id.slice(0, 8)}</div>
            <div>Status: {run.status}</div>
            <div>
              Summary: passed {run.summary?.passed ?? 0}, failed {run.summary?.failed ?? 0}, skipped {run.summary?.skipped ?? 0}
            </div>
          </div>
        )}

        <div className="max-h-48 overflow-y-auto rounded-lg border border-gray-200">
          <table className="min-w-full text-left text-xs">
            <thead className="sticky top-0 bg-gray-50 text-gray-500">
              <tr>
                <th className="px-2 py-1">Case</th>
                <th className="px-2 py-1">Status</th>
                <th className="px-2 py-1">Latency</th>
                <th className="px-2 py-1">Endpoint</th>
              </tr>
            </thead>
            <tbody>
              {steps.length === 0 ? (
                <tr>
                  <td className="px-2 py-2 text-gray-500" colSpan={4}>
                    No replay steps yet.
                  </td>
                </tr>
              ) : (
                steps.map((step) => (
                  <tr key={step.id} className="border-t border-gray-100">
                    <td className="px-2 py-1.5">{step.case_label || step.case_id}</td>
                    <td className={`px-2 py-1.5 ${step.pass_fail ? 'text-emerald-700' : 'text-red-700'}`}>
                      {step.pass_fail ? 'PASS' : 'FAIL'}
                      {step.response_status ? ` (${step.response_status})` : ''}
                    </td>
                    <td className="px-2 py-1.5">{step.latency_ms ?? '-'}ms</td>
                    <td className="px-2 py-1.5 text-gray-600">{step.endpoint}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
};

