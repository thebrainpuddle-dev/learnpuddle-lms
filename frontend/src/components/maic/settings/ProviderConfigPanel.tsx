// src/components/maic/settings/ProviderConfigPanel.tsx
//
// Reusable, collapsible API provider configuration panel.
// Renders dynamic form fields and supports connection testing.

import React, { useState, useCallback } from 'react';
import {
  Zap,
  Eye,
  EyeOff,
  ChevronDown,
  ChevronRight,
  Check,
  X,
  Minus,
  Loader2,
} from 'lucide-react';
import { cn } from '../../../lib/utils';

interface ProviderField {
  key: string;
  label: string;
  type: 'text' | 'password' | 'url' | 'select';
  placeholder?: string;
  options?: Array<{ value: string; label: string }>;
  required?: boolean;
}

interface ProviderConfigPanelProps {
  className?: string;
  providerId: string;
  providerName: string;
  fields: ProviderField[];
  values: Record<string, string>;
  onChange: (key: string, value: string) => void;
  onTest?: () => Promise<boolean>;
}

type TestStatus = 'untested' | 'testing' | 'success' | 'error';

/* ------------------------------------------------------------------ */
/*  Status indicator                                                  */
/* ------------------------------------------------------------------ */

function StatusIndicator({ status }: { status: TestStatus }) {
  switch (status) {
    case 'success':
      return (
        <span className="inline-flex items-center gap-1 text-xs text-green-600">
          <Check className="h-3.5 w-3.5" />
          Verified
        </span>
      );
    case 'error':
      return (
        <span className="inline-flex items-center gap-1 text-xs text-red-600">
          <X className="h-3.5 w-3.5" />
          Failed
        </span>
      );
    case 'testing':
      return (
        <span className="inline-flex items-center gap-1 text-xs text-blue-600">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          Testing...
        </span>
      );
    default:
      return (
        <span className="inline-flex items-center gap-1 text-xs text-gray-400">
          <Minus className="h-3.5 w-3.5" />
          Untested
        </span>
      );
  }
}

/* ------------------------------------------------------------------ */
/*  Password field with toggle                                        */
/* ------------------------------------------------------------------ */

function PasswordField({
  value,
  onChange,
  placeholder,
  required,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  required?: boolean;
}) {
  const [show, setShow] = useState(false);

  return (
    <div className="relative">
      <input
        type={show ? 'text' : 'password'}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        required={required}
        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm pr-10 focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
      />
      <button
        type="button"
        onClick={() => setShow((v) => !v)}
        className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-gray-400 hover:text-gray-600"
        aria-label={show ? 'Hide value' : 'Show value'}
      >
        {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
      </button>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Main component                                                    */
/* ------------------------------------------------------------------ */

export const ProviderConfigPanel = React.memo<ProviderConfigPanelProps>(
  function ProviderConfigPanel({
    className,
    providerId,
    providerName,
    fields,
    values,
    onChange,
    onTest,
  }) {
    const [expanded, setExpanded] = useState(false);
    const [testStatus, setTestStatus] = useState<TestStatus>('untested');

    const handleTest = useCallback(async () => {
      if (!onTest) return;
      setTestStatus('testing');
      try {
        const success = await onTest();
        setTestStatus(success ? 'success' : 'error');
      } catch {
        setTestStatus('error');
      }
    }, [onTest]);

    return (
      <div
        className={cn(
          'rounded-lg border border-gray-200 overflow-hidden',
          expanded && 'ring-1 ring-gray-300',
          className,
        )}
      >
        {/* Header */}
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="w-full flex items-center justify-between gap-2 px-4 py-3 bg-gray-50 hover:bg-gray-100 transition-colors text-left focus:outline-none focus:ring-2 focus:ring-inset focus:ring-primary-500"
          aria-expanded={expanded}
        >
          <div className="flex items-center gap-2.5">
            <Zap className="h-4 w-4 text-amber-500 flex-shrink-0" aria-hidden="true" />
            <span className="text-sm font-medium text-gray-800">{providerName}</span>
          </div>
          <div className="flex items-center gap-3">
            <StatusIndicator status={testStatus} />
            {expanded ? (
              <ChevronDown className="h-4 w-4 text-gray-400" />
            ) : (
              <ChevronRight className="h-4 w-4 text-gray-400" />
            )}
          </div>
        </button>

        {/* Collapsible body */}
        {expanded && (
          <div className="px-4 py-4 space-y-4 border-t border-gray-200 bg-white">
            {fields.map((field) => (
              <div key={field.key}>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  {field.label}
                  {field.required && <span className="text-red-500 ml-0.5">*</span>}
                </label>

                {field.type === 'password' ? (
                  <PasswordField
                    value={values[field.key] ?? ''}
                    onChange={(v) => onChange(field.key, v)}
                    placeholder={field.placeholder}
                    required={field.required}
                  />
                ) : field.type === 'select' ? (
                  <div className="relative">
                    <select
                      value={values[field.key] ?? ''}
                      onChange={(e) => onChange(field.key, e.target.value)}
                      className="w-full appearance-none rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm pr-8 focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                    >
                      <option value="">Select...</option>
                      {field.options?.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
                    <ChevronDown className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
                  </div>
                ) : (
                  <input
                    type={field.type}
                    value={values[field.key] ?? ''}
                    onChange={(e) => onChange(field.key, e.target.value)}
                    placeholder={field.placeholder}
                    required={field.required}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                  />
                )}
              </div>
            ))}

            {/* Test Connection button */}
            {onTest && (
              <div className="pt-1">
                <button
                  type="button"
                  onClick={handleTest}
                  disabled={testStatus === 'testing'}
                  className={cn(
                    'inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors',
                    'focus:outline-none focus:ring-2 focus:ring-primary-500',
                    testStatus === 'testing'
                      ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                      : 'bg-primary-50 text-primary-600 hover:bg-primary-100',
                  )}
                >
                  {testStatus === 'testing' ? (
                    <>
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      Testing...
                    </>
                  ) : (
                    <>
                      <Zap className="h-3.5 w-3.5" />
                      Test Connection
                    </>
                  )}
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    );
  },
);
