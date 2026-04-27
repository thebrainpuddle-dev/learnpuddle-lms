// src/components/reportBuilder/AggregateBuilder.tsx
//
// Dynamic row editor for aggregate entries in the report builder.
//
// Each row = { fn, field, alias? }. `fn` is picked from AGGREGATE_FN_MAP,
// `field` from the data source whitelist (defaults to "id"),
// `alias` is an optional output column name.

import React from 'react';
import { PlusIcon, TrashIcon } from '@heroicons/react/24/outline';
import type {
  AggregateEntry,
  ReportAggregateFn,
} from '../../services/reportBuilderService';

const FN_LABELS: Record<ReportAggregateFn, string> = {
  count: 'Count',
  distinct_count: 'Count (distinct)',
  sum: 'Sum',
  avg: 'Average',
};

export interface AggregateBuilderProps {
  availableFields: string[];
  availableFns: ReportAggregateFn[];
  value: AggregateEntry[];
  onChange: (next: AggregateEntry[]) => void;
  disabled?: boolean;
}

export const AggregateBuilder: React.FC<AggregateBuilderProps> = ({
  availableFields,
  availableFns,
  value,
  onChange,
  disabled = false,
}) => {
  // Always allow "id" as an aggregate field (matches backend default).
  const fieldOptions = React.useMemo(() => {
    const fields = new Set<string>(['id', ...availableFields]);
    return Array.from(fields);
  }, [availableFields]);

  const updateRow = (idx: number, patch: Partial<AggregateEntry>) => {
    const next = value.map((row, i) => (i === idx ? { ...row, ...patch } : row));
    onChange(next);
  };

  const removeRow = (idx: number) => {
    onChange(value.filter((_, i) => i !== idx));
  };

  const addRow = () => {
    const firstFn: ReportAggregateFn = availableFns[0] ?? 'count';
    onChange([...value, { fn: firstFn, field: 'id', alias: '' }]);
  };

  return (
    <div className="space-y-2" data-testid="aggregate-builder">
      {value.length === 0 ? (
        <p className="text-xs text-gray-500" data-testid="aggregate-empty">
          No aggregates yet — click "Add aggregate" to count / sum / average
          results.
        </p>
      ) : (
        <div className="space-y-2">
          {value.map((row, idx) => (
            <div
              key={idx}
              className="flex items-center gap-2 rounded-lg border border-gray-200 bg-white p-2"
              data-testid={`aggregate-row-${idx}`}
            >
              <select
                value={row.fn}
                onChange={(e) =>
                  updateRow(idx, { fn: e.target.value as ReportAggregateFn })
                }
                disabled={disabled}
                data-testid={`aggregate-fn-${idx}`}
                aria-label={`Aggregate ${idx + 1} function`}
                className="rounded-md border border-gray-300 bg-white px-2 py-1.5 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-200"
              >
                {availableFns.map((fn) => (
                  <option key={fn} value={fn}>
                    {FN_LABELS[fn] ?? fn}
                  </option>
                ))}
              </select>

              <select
                value={row.field}
                onChange={(e) => updateRow(idx, { field: e.target.value })}
                disabled={disabled}
                data-testid={`aggregate-field-${idx}`}
                aria-label={`Aggregate ${idx + 1} field`}
                className="flex-1 rounded-md border border-gray-300 bg-white px-2 py-1.5 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-200"
              >
                {fieldOptions.map((f) => (
                  <option key={f} value={f}>
                    {f}
                  </option>
                ))}
              </select>

              <input
                type="text"
                value={row.alias ?? ''}
                onChange={(e) => updateRow(idx, { alias: e.target.value })}
                disabled={disabled}
                placeholder="alias (optional)"
                data-testid={`aggregate-alias-${idx}`}
                aria-label={`Aggregate ${idx + 1} alias`}
                className="flex-1 rounded-md border border-gray-300 bg-white px-2 py-1.5 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-200"
              />

              <button
                type="button"
                onClick={() => removeRow(idx)}
                disabled={disabled}
                data-testid={`aggregate-remove-${idx}`}
                aria-label={`Remove aggregate ${idx + 1}`}
                className="rounded-md p-1.5 text-red-500 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <TrashIcon className="h-4 w-4" />
              </button>
            </div>
          ))}
        </div>
      )}

      <button
        type="button"
        onClick={addRow}
        disabled={disabled}
        data-testid="aggregate-add"
        className="inline-flex items-center gap-1 rounded-md border border-dashed border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-600 hover:border-primary-400 hover:text-primary-600 disabled:cursor-not-allowed disabled:opacity-50"
      >
        <PlusIcon className="h-3.5 w-3.5" />
        Add aggregate
      </button>
    </div>
  );
};
