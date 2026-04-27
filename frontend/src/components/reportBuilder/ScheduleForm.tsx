// src/components/reportBuilder/ScheduleForm.tsx
//
// Dialog form for creating / editing a ReportSchedule.
// Surfaces `EXTERNAL_RECIPIENT_NOT_ALLOWED` and other server-side errors
// in the recipient field.

import React, { useEffect, useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '../ui/dialog';
import { Button } from '../common/Button';
import { RecipientChipsInput } from './RecipientChipsInput';
import type {
  ReportSchedule,
  ReportScheduleCadence,
  ReportScheduleWritePayload,
} from '../../services/reportBuilderService';

const CADENCE_OPTIONS: Array<{ value: ReportScheduleCadence; label: string }> = [
  { value: 'daily', label: 'Daily' },
  { value: 'weekly', label: 'Weekly' },
  { value: 'monthly', label: 'Monthly' },
];

const DAY_OF_WEEK_LABELS = [
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
  'Sunday',
];

export interface ScheduleFormProps {
  open: boolean;
  onClose: () => void;
  /** Pre-fill mode — when set, the form is in edit mode. */
  initial?: ReportSchedule | null;
  onSubmit: (payload: ReportScheduleWritePayload) => Promise<void>;
  /** Submit-level error (e.g. server-side validation error string). */
  submitError?: string | null;
  /**
   * Machine-readable error code (e.g. "EXTERNAL_RECIPIENT_NOT_ALLOWED").
   * Attached as `data-error-code` on the alert element for e2e assertions.
   */
  submitErrorCode?: string | null;
  isSubmitting?: boolean;
}

export const ScheduleForm: React.FC<ScheduleFormProps> = ({
  open,
  onClose,
  initial = null,
  onSubmit,
  submitError = null,
  submitErrorCode = null,
  isSubmitting = false,
}) => {
  const [cadence, setCadence] = useState<ReportScheduleCadence>('daily');
  const [runAtHour, setRunAtHour] = useState<number>(6);
  const [runAtDayOfWeek, setRunAtDayOfWeek] = useState<number>(0);
  const [runAtDayOfMonth, setRunAtDayOfMonth] = useState<number>(1);
  const [recipients, setRecipients] = useState<string[]>([]);
  const [enabled, setEnabled] = useState<boolean>(true);

  // When `open` transitions to true, hydrate from `initial` (or defaults).
  useEffect(() => {
    if (!open) return;
    if (initial) {
      setCadence(initial.cadence);
      setRunAtHour(initial.run_at_hour);
      setRunAtDayOfWeek(initial.run_at_day_of_week ?? 0);
      setRunAtDayOfMonth(initial.run_at_day_of_month ?? 1);
      setRecipients(initial.recipients_json ?? []);
      setEnabled(initial.enabled);
    } else {
      setCadence('daily');
      setRunAtHour(6);
      setRunAtDayOfWeek(0);
      setRunAtDayOfMonth(1);
      setRecipients([]);
      setEnabled(true);
    }
  }, [open, initial]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const payload: ReportScheduleWritePayload = {
      cadence,
      run_at_hour: runAtHour,
      run_at_day_of_week: cadence === 'weekly' ? runAtDayOfWeek : null,
      run_at_day_of_month: cadence === 'monthly' ? runAtDayOfMonth : null,
      recipients_json: recipients,
      enabled,
    };
    await onSubmit(payload);
  };

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent
        onClose={onClose}
        className="sm:max-w-xl"
        data-testid="schedule-form"
      >
        <DialogHeader>
          <DialogTitle>
            {initial ? 'Edit schedule' : 'Create schedule'}
          </DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="mt-4 space-y-4">
          {/* Cadence */}
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-700">
              Cadence
            </label>
            <select
              value={cadence}
              onChange={(e) =>
                setCadence(e.target.value as ReportScheduleCadence)
              }
              data-testid="schedule-cadence"
              aria-label="Cadence"
              className="w-full rounded-md border border-gray-300 bg-white px-2 py-1.5 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-200"
            >
              {CADENCE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>

          <div className="grid grid-cols-2 gap-3">
            {/* Hour of day */}
            <div>
              <label className="mb-1 block text-xs font-medium text-gray-700">
                Hour (UTC, 0–23)
              </label>
              <input
                type="number"
                min={0}
                max={23}
                value={runAtHour}
                onChange={(e) => setRunAtHour(Number(e.target.value))}
                data-testid="schedule-hour"
                aria-label="Hour of day"
                className="w-full rounded-md border border-gray-300 bg-white px-2 py-1.5 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-200"
              />
            </div>

            {/* Day of week */}
            {cadence === 'weekly' && (
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-700">
                  Day of week
                </label>
                <select
                  value={runAtDayOfWeek}
                  onChange={(e) => setRunAtDayOfWeek(Number(e.target.value))}
                  data-testid="schedule-day-of-week"
                  aria-label="Day of week"
                  className="w-full rounded-md border border-gray-300 bg-white px-2 py-1.5 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-200"
                >
                  {DAY_OF_WEEK_LABELS.map((label, idx) => (
                    <option key={label} value={idx}>
                      {label}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {/* Day of month */}
            {cadence === 'monthly' && (
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-700">
                  Day of month (1–28)
                </label>
                <input
                  type="number"
                  min={1}
                  max={28}
                  value={runAtDayOfMonth}
                  onChange={(e) => setRunAtDayOfMonth(Number(e.target.value))}
                  data-testid="schedule-day-of-month"
                  aria-label="Day of month"
                  className="w-full rounded-md border border-gray-300 bg-white px-2 py-1.5 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-200"
                />
              </div>
            )}
          </div>

          {/* Recipients */}
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-700">
              Recipients
            </label>
            <RecipientChipsInput
              value={recipients}
              onChange={setRecipients}
              disabled={isSubmitting}
              error={submitError}
              errorCode={submitErrorCode}
            />
          </div>

          {/* Enabled toggle */}
          <label className="inline-flex items-center gap-2 text-sm text-gray-700">
            <input
              type="checkbox"
              checked={enabled}
              onChange={(e) => setEnabled(e.target.checked)}
              data-testid="schedule-enabled"
              className="h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500"
            />
            Enabled
          </label>

          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              onClick={onClose}
              disabled={isSubmitting}
            >
              Cancel
            </Button>
            <Button type="submit" loading={isSubmitting} data-testid="schedule-submit">
              {initial ? 'Save changes' : 'Create schedule'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
};
