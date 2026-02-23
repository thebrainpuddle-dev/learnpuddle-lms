import React from 'react';
import type { OpsActionCatalogItem } from '../../../services/superAdminService';

interface ActionCenterProps {
  tenantId: string;
  actions: OpsActionCatalogItem[];
  executing: boolean;
  onExecute: (args: {
    tenantId: string;
    actionKey: string;
    dryRun: boolean;
    reason: string;
    target: Record<string, any>;
  }) => void;
  lastResult?: Record<string, any> | null;
}

export const ActionCenter: React.FC<ActionCenterProps> = ({
  tenantId,
  actions,
  executing,
  onExecute,
  lastResult,
}) => {
  const [actionKey, setActionKey] = React.useState('');
  const [targetText, setTargetText] = React.useState('{}');
  const [reason, setReason] = React.useState('');
  const [dryRun, setDryRun] = React.useState(true);
  const [targetError, setTargetError] = React.useState('');

  React.useEffect(() => {
    if (!actionKey && actions.length > 0) {
      setActionKey(actions[0].key);
    }
  }, [actionKey, actions]);

  const selectedAction = actions.find((item) => item.key === actionKey);

  const handleExecute = () => {
    if (!tenantId || !actionKey) return;
    try {
      const target = JSON.parse(targetText || '{}');
      setTargetError('');
      onExecute({ tenantId, actionKey, dryRun, reason, target });
    } catch {
      setTargetError('Target must be valid JSON.');
    }
  };

  return (
    <section className="rounded-xl border border-gray-200 bg-white">
      <div className="border-b border-gray-100 px-4 py-3">
        <h3 className="text-sm font-semibold text-gray-900">Action Center</h3>
        <p className="mt-1 text-xs text-gray-500">Guarded unblock actions with dry-run by default and approval gating.</p>
      </div>

      <div className="space-y-3 p-4">
        <select
          value={actionKey}
          onChange={(e) => setActionKey(e.target.value)}
          className="w-full rounded-lg border border-gray-300 px-3 py-1.5 text-sm"
        >
          {actions.map((action) => (
            <option key={action.key} value={action.key}>
              {action.label}
            </option>
          ))}
        </select>
        {selectedAction && (
          <div className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-xs text-gray-600">
            <div className="font-semibold text-gray-800">{selectedAction.description}</div>
            <div className="mt-1">
              Risk: <span className="uppercase">{selectedAction.risk}</span> | Requires approval:{' '}
              {selectedAction.requires_approval ? 'Yes' : 'No'}
            </div>
            <div className="mt-1">
              Target keys: {selectedAction.required_target_keys?.length ? selectedAction.required_target_keys.join(', ') : 'None'}
            </div>
          </div>
        )}
        <div>
          <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500">Target JSON</label>
          <textarea
            value={targetText}
            onChange={(e) => setTargetText(e.target.value)}
            className="h-20 w-full rounded-lg border border-gray-300 px-3 py-2 font-mono text-xs"
            placeholder='{"content_id":"...","course_id":"..."}'
          />
          {targetError && <p className="mt-1 text-xs text-red-600">{targetError}</p>}
        </div>
        <div>
          <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-500">Reason</label>
          <input
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            className="w-full rounded-lg border border-gray-300 px-3 py-1.5 text-sm"
            placeholder="Operator note for audit trail"
          />
        </div>
        <label className="inline-flex items-center gap-2 text-sm text-gray-700">
          <input type="checkbox" checked={dryRun} onChange={(e) => setDryRun(e.target.checked)} />
          Dry run
        </label>
        <button
          type="button"
          onClick={handleExecute}
          disabled={!tenantId || !actionKey || executing}
          className="rounded-md bg-slate-800 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-900 disabled:opacity-50"
        >
          {executing ? 'Executing...' : 'Execute Action'}
        </button>
        {lastResult && (
          <pre className="overflow-auto rounded-lg border border-gray-200 bg-gray-50 p-2 text-xs text-gray-700">
            {JSON.stringify(lastResult, null, 2)}
          </pre>
        )}
      </div>
    </section>
  );
};

