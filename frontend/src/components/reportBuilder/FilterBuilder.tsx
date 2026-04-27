// src/components/reportBuilder/FilterBuilder.tsx
//
// Dynamic filter row editor for the Custom Report Builder.
//
// Each filter row has:
//   - field   : a select bound to the current data source's whitelist
//   - op      : a select bound to SUPPORTED_OPS
//   - value   : a free-text input; serialised into the underlying JSON value
//               depending on the operator (in / between → split by comma).
//
// The component is fully controlled — parent owns `value` state.

import React, { useState } from 'react';
import { PlusIcon, TrashIcon } from '@heroicons/react/24/outline';
import type {
  FilterEntry,
  ReportFilterOp,
} from '../../services/reportBuilderService';

const OP_LABELS: Record<ReportFilterOp, string> = {
  eq: 'equals',
  ne: 'not equals',
  gt: 'greater than',
  gte: 'greater than or equal',
  lt: 'less than',
  lte: 'less than or equal',
  in: 'in list',
  contains: 'contains',
  between: 'between',
};

/** Declared field types, keyed by field name. */
export type FieldTypeMap = Record<string, 'number' | 'boolean' | 'date' | 'string'>;

export interface FilterBuilderProps {
  /** Fields allowed for the currently-selected data source. */
  availableFields: string[];
  /** Operators allowed by the backend (SUPPORTED_OPS). */
  availableOperators: ReportFilterOp[];
  /** Current filters. */
  value: FilterEntry[];
  /** Called whenever the filter list changes. */
  onChange: (next: FilterEntry[]) => void;
  /** Disabled state (e.g. while the form is submitting). */
  disabled?: boolean;
  /**
   * Optional map of field name → declared type.
   * When provided, scalar filter values are coerced to the declared type
   * before being passed to onChange.  'in' / 'between' list items are also
   * individually coerced.  If coercion fails (NaN for number), a per-row
   * validation error is displayed and the parent onChange is NOT called.
   */
  fieldTypes?: FieldTypeMap;
}

/** Coerce a single string token to the declared type.  Returns the coerced
 *  value, or `null` to signal a coercion failure. */
function coerceToken(
  token: string,
  type: 'number' | 'boolean' | 'date' | 'string',
): unknown | null {
  if (type === 'number') {
    const n = Number(token);
    if (isNaN(n)) return null;
    return n;
  }
  if (type === 'boolean') {
    return token === 'true';
  }
  // 'date' and 'string' stay as-is
  return token;
}

/** Serialise a user-facing value string into the FilterEntry.value field.
 *  Returns { value, error } — error is non-null when coercion fails. */
function parseValue(
  raw: string,
  op: ReportFilterOp,
  fieldType?: 'number' | 'boolean' | 'date' | 'string',
): { value: unknown; error: string | null } {
  const trimmed = raw.trim();
  if (op === 'in' || op === 'between') {
    if (!trimmed) return { value: [], error: null };
    const tokens = trimmed
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);
    if (fieldType && fieldType !== 'string' && fieldType !== 'date') {
      const coerced: unknown[] = [];
      for (const token of tokens) {
        const result = coerceToken(token, fieldType);
        if (result === null) {
          return {
            value: tokens,
            error: `"${token}" is not a valid ${fieldType}.`,
          };
        }
        coerced.push(result);
      }
      return { value: coerced, error: null };
    }
    return { value: tokens, error: null };
  }
  if (fieldType && fieldType !== 'string' && fieldType !== 'date') {
    if (!trimmed) return { value: trimmed, error: null };
    const result = coerceToken(trimmed, fieldType);
    if (result === null) {
      return {
        value: trimmed,
        error: `"${trimmed}" is not a valid ${fieldType}.`,
      };
    }
    return { value: result, error: null };
  }
  return { value: trimmed, error: null };
}

/** De-serialise FilterEntry.value back to a string for the <input>. */
function stringifyValue(value: unknown): string {
  if (Array.isArray(value)) return value.join(', ');
  if (value === null || value === undefined) return '';
  return String(value);
}

export const FilterBuilder: React.FC<FilterBuilderProps> = ({
  availableFields,
  availableOperators,
  value,
  onChange,
  disabled = false,
  fieldTypes,
}) => {
  // Per-row coercion error messages (index → message | null).
  const [rowErrors, setRowErrors] = useState<Record<number, string | null>>({});

  const updateRow = (idx: number, patch: Partial<FilterEntry>) => {
    const currentRow = value[idx];
    const nextRow = { ...currentRow, ...patch };

    // If the value was updated, run coercion if fieldTypes is provided.
    if ('value' in patch && fieldTypes) {
      const fieldType = fieldTypes[nextRow.field];
      if (fieldType) {
        const raw = String(patch.value ?? '');
        const { value: coerced, error } = parseValue(raw, nextRow.op, fieldType);
        setRowErrors((prev) => ({ ...prev, [idx]: error }));
        if (error) {
          // Still update the raw display string so the user sees what they typed,
          // but do NOT call the parent onChange (block the invalid value).
          return;
        }
        const next = value.map((row, i) =>
          i === idx ? { ...nextRow, value: coerced } : row,
        );
        onChange(next);
        return;
      }
    }

    setRowErrors((prev) => ({ ...prev, [idx]: null }));
    // When no fieldTypes coercion applies, still split 'in'/'between' strings
    // into arrays so the backend receives the correct JSON type.
    let finalRow = nextRow;
    if ('value' in patch && typeof patch.value === 'string') {
      const { value: parsed } = parseValue(patch.value, nextRow.op, undefined);
      finalRow = { ...nextRow, value: parsed };
    }
    const next = value.map((row, i) => (i === idx ? finalRow : row));
    onChange(next);
  };

  const removeRow = (idx: number) => {
    setRowErrors((prev) => {
      const next = { ...prev };
      delete next[idx];
      return next;
    });
    onChange(value.filter((_, i) => i !== idx));
  };

  const addRow = () => {
    const firstField = availableFields[0] ?? '';
    const firstOp: ReportFilterOp = availableOperators[0] ?? 'eq';
    onChange([...value, { field: firstField, op: firstOp, value: '' }]);
  };

  return (
    <div className="space-y-2" data-testid="filter-builder">
      {value.length === 0 ? (
        <p className="text-xs text-gray-500" data-testid="filter-empty">
          No filters yet — click "Add filter" to narrow down results.
        </p>
      ) : (
        <div className="space-y-2">
          {value.map((row, idx) => (
            <div key={idx} data-testid={`filter-row-${idx}`}>
              <div
                className="flex items-center gap-2 rounded-lg border border-gray-200 bg-white p-2"
              >
                <select
                  value={row.field}
                  onChange={(e) => updateRow(idx, { field: e.target.value })}
                  disabled={disabled || availableFields.length === 0}
                  data-testid={`filter-field-${idx}`}
                  aria-label={`Filter ${idx + 1} field`}
                  className="flex-1 rounded-md border border-gray-300 bg-white px-2 py-1.5 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-200"
                >
                  {availableFields.map((f) => (
                    <option key={f} value={f}>
                      {f}
                    </option>
                  ))}
                </select>

                <select
                  value={row.op}
                  onChange={(e) =>
                    updateRow(idx, { op: e.target.value as ReportFilterOp })
                  }
                  disabled={disabled}
                  data-testid={`filter-op-${idx}`}
                  aria-label={`Filter ${idx + 1} operator`}
                  className="rounded-md border border-gray-300 bg-white px-2 py-1.5 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-200"
                >
                  {availableOperators.map((op) => (
                    <option key={op} value={op}>
                      {OP_LABELS[op] ?? op}
                    </option>
                  ))}
                </select>

                <input
                  type="text"
                  value={stringifyValue(row.value)}
                  onChange={(e) =>
                    updateRow(idx, { value: e.target.value })
                  }
                  disabled={disabled}
                  placeholder={
                    row.op === 'in'
                      ? 'value1, value2, …'
                      : row.op === 'between'
                        ? 'min, max'
                        : 'value'
                  }
                  data-testid={`filter-value-${idx}`}
                  aria-label={`Filter ${idx + 1} value`}
                  className={`flex-1 rounded-md border bg-white px-2 py-1.5 text-sm focus:outline-none focus:ring-1 ${
                    rowErrors[idx]
                      ? 'border-red-400 focus:border-red-400 focus:ring-red-200'
                      : 'border-gray-300 focus:border-primary-500 focus:ring-primary-200'
                  }`}
                />

                <button
                  type="button"
                  onClick={() => removeRow(idx)}
                  disabled={disabled}
                  data-testid={`filter-remove-${idx}`}
                  aria-label={`Remove filter ${idx + 1}`}
                  className="rounded-md p-1.5 text-red-500 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <TrashIcon className="h-4 w-4" />
                </button>
              </div>
              {rowErrors[idx] && (
                <p
                  className="mt-0.5 text-xs text-red-600"
                  role="alert"
                  data-testid={`filter-coerce-error-${idx}`}
                >
                  {rowErrors[idx]}
                </p>
              )}
            </div>
          ))}
        </div>
      )}

      <button
        type="button"
        onClick={addRow}
        disabled={disabled || availableFields.length === 0}
        data-testid="filter-add"
        className="inline-flex items-center gap-1 rounded-md border border-dashed border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-600 hover:border-primary-400 hover:text-primary-600 disabled:cursor-not-allowed disabled:opacity-50"
      >
        <PlusIcon className="h-3.5 w-3.5" />
        Add filter
      </button>
    </div>
  );
};
