// src/pages/admin/translation/components/LocalePicker.tsx
// Multi-select locale picker for translation target languages.

import React from 'react';
import { SUPPORTED_LOCALES } from '../../../../services/translationService';

interface LocalePickerProps {
  selected: string[];
  onChange: (selected: string[]) => void;
  disabled?: boolean;
}

export const LocalePicker: React.FC<LocalePickerProps> = ({
  selected,
  onChange,
  disabled = false,
}) => {
  const toggle = (code: string) => {
    if (disabled) return;
    if (selected.includes(code)) {
      onChange(selected.filter((c) => c !== code));
    } else {
      onChange([...selected, code]);
    }
  };

  return (
    <div data-testid="locale-picker">
      <p className="text-sm text-gray-500 mb-3">
        Select one or more target languages. English (source) is always included.
      </p>
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2">
        {SUPPORTED_LOCALES.map((locale) => {
          const isSelected = selected.includes(locale.code);
          return (
            <button
              key={locale.code}
              type="button"
              data-testid={`locale-btn-${locale.code}`}
              onClick={() => toggle(locale.code)}
              disabled={disabled}
              className={`cursor-pointer rounded-lg border px-3 py-2 text-sm font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-1 disabled:opacity-50 disabled:cursor-not-allowed ${
                isSelected
                  ? 'border-primary-500 bg-primary-50 text-primary-700'
                  : 'border-gray-200 bg-white text-gray-700 hover:border-gray-300 hover:bg-gray-50'
              }`}
              aria-pressed={isSelected}
            >
              {locale.label}
            </button>
          );
        })}
      </div>
      {selected.length > 0 && (
        <p
          data-testid="selected-count"
          className="mt-2 text-xs text-gray-400"
        >
          {selected.length} language{selected.length > 1 ? 's' : ''} selected
        </p>
      )}
    </div>
  );
};
