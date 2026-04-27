// src/components/reportBuilder/RecipientChipsInput.tsx
//
// Email chip input used by the schedule form.
//
// Client-side only does syntactic email validation. The backend enforces
// tenant-internal membership and returns `EXTERNAL_RECIPIENT_NOT_ALLOWED`
// on violation — we intentionally do NOT try to enumerate tenant users
// here (privacy).

import React, { useState } from 'react';
import { XMarkIcon } from '@heroicons/react/24/outline';

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export interface RecipientChipsInputProps {
  value: string[];
  onChange: (next: string[]) => void;
  disabled?: boolean;
  /** Error text rendered below the input (e.g. server-side validation). */
  error?: string | null;
  /**
   * Machine-readable error code exposed via `data-error-code` on the alert
   * element (e.g. "EXTERNAL_RECIPIENT_NOT_ALLOWED").  Used by e2e tests.
   */
  errorCode?: string | null;
}

export const RecipientChipsInput: React.FC<RecipientChipsInputProps> = ({
  value,
  onChange,
  disabled = false,
  error = null,
  errorCode = null,
}) => {
  const [draft, setDraft] = useState('');
  const [localError, setLocalError] = useState<string | null>(null);

  const commitDraft = () => {
    const trimmed = draft.trim().replace(/,+$/, '');
    if (!trimmed) return;
    if (!EMAIL_REGEX.test(trimmed)) {
      setLocalError(`"${trimmed}" is not a valid email address.`);
      return;
    }
    if (value.includes(trimmed)) {
      setLocalError(`"${trimmed}" is already in the list.`);
      return;
    }
    onChange([...value, trimmed]);
    setDraft('');
    setLocalError(null);
  };

  const removeAt = (idx: number) => {
    onChange(value.filter((_, i) => i !== idx));
    setLocalError(null);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault();
      commitDraft();
    } else if (e.key === 'Backspace' && draft === '' && value.length > 0) {
      onChange(value.slice(0, -1));
    }
  };

  const visibleError = error ?? localError;

  return (
    <div className="space-y-1" data-testid="recipient-chips-input">
      <div
        className={`flex flex-wrap items-center gap-1 rounded-lg border bg-white p-1.5 ${
          visibleError ? 'border-red-300' : 'border-gray-300'
        } ${disabled ? 'opacity-50' : ''}`}
      >
        {value.map((email, idx) => (
          <span
            key={email}
            data-testid={`recipient-chip-${idx}`}
            className="inline-flex items-center gap-1 rounded-full bg-primary-50 px-2 py-0.5 text-xs font-medium text-primary-700"
          >
            {email}
            <button
              type="button"
              onClick={() => removeAt(idx)}
              disabled={disabled}
              aria-label={`Remove ${email}`}
              data-testid={`recipient-remove-${idx}`}
              className="rounded-full p-0.5 text-primary-500 hover:bg-primary-100 disabled:opacity-50"
            >
              <XMarkIcon className="h-3 w-3" />
            </button>
          </span>
        ))}
        <input
          type="email"
          value={draft}
          onChange={(e) => {
            setDraft(e.target.value);
            setLocalError(null);
          }}
          onKeyDown={handleKeyDown}
          onBlur={commitDraft}
          disabled={disabled}
          placeholder={value.length === 0 ? 'name@yourschool.com' : ''}
          data-testid="recipient-draft-input"
          aria-label="Add recipient email"
          className="min-w-[160px] flex-1 border-0 bg-transparent px-1 py-0.5 text-sm focus:outline-none"
        />
      </div>
      <p className="text-[11px] text-gray-500">
        Only users of this school can receive scheduled reports. External
        addresses will be rejected.
      </p>
      {visibleError && (
        <p
          className="text-xs text-red-600"
          role="alert"
          data-testid="recipient-error"
          data-error-code={errorCode ?? undefined}
        >
          {visibleError}
        </p>
      )}
    </div>
  );
};
