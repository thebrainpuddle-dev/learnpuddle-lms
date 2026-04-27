// src/components/reportBuilder/GroupByChips.tsx
//
// Chip selector for the "Group By" section of the report builder.
//
// - Shows every whitelisted field as a toggle chip.
// - Selected chips become `group_by_json` on the definition.
// - Fully controlled.

import React from 'react';
import { cn } from '../../lib/utils';

export interface GroupByChipsProps {
  availableFields: string[];
  /** Selected field names. */
  value: string[];
  onChange: (next: string[]) => void;
  disabled?: boolean;
}

export const GroupByChips: React.FC<GroupByChipsProps> = ({
  availableFields,
  value,
  onChange,
  disabled = false,
}) => {
  if (availableFields.length === 0) {
    return (
      <p className="text-xs text-gray-500" data-testid="groupby-empty">
        Select a data source first to see groupable fields.
      </p>
    );
  }

  const toggle = (field: string) => {
    if (disabled) return;
    if (value.includes(field)) {
      onChange(value.filter((f) => f !== field));
    } else {
      onChange([...value, field]);
    }
  };

  return (
    <div className="flex flex-wrap gap-2" data-testid="groupby-chips">
      {availableFields.map((field) => {
        const selected = value.includes(field);
        return (
          <button
            key={field}
            type="button"
            onClick={() => toggle(field)}
            disabled={disabled}
            data-testid={`groupby-chip-${field}`}
            aria-pressed={selected}
            className={cn(
              'rounded-full border px-3 py-1 text-xs font-medium transition-colors',
              selected
                ? 'border-primary-500 bg-primary-50 text-primary-700'
                : 'border-gray-300 bg-white text-gray-600 hover:border-primary-400 hover:text-primary-600',
              disabled && 'cursor-not-allowed opacity-50',
            )}
          >
            {field}
          </button>
        );
      })}
    </div>
  );
};
