import React, { useState, useMemo } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import {
  PaperAirplaneIcon,
  EyeIcon,
  MagnifyingGlassIcon,
  XMarkIcon,
  CalendarDaysIcon,
  ClockIcon,
} from '@heroicons/react/24/outline';
import { Button } from '../common/Button';
import { Input } from '../common/Input';
import { useToast } from '../common';
import { adminRemindersService } from '../../services/adminRemindersService';
import { adminTeachersService } from '../../services/adminTeachersService';

// ─── Types ──────────────────────────────────────────────────────────────────

type ReminderType = 'ASSIGNMENT_DUE' | 'CUSTOM';
type SendMode = 'now' | 'schedule';

// Debounce hook
function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = React.useState<T>(value);
  React.useEffect(() => {
    const handler = setTimeout(() => setDebouncedValue(value), delay);
    return () => clearTimeout(handler);
  }, [value, delay]);
  return debouncedValue;
}

// ─── Props ──────────────────────────────────────────────────────────────────

interface ManualSendSectionProps {
  onSent?: () => void;
}

// ─── Component ──────────────────────────────────────────────────────────────

export const ManualSendSection: React.FC<ManualSendSectionProps> = ({ onSent }) => {
  const toast = useToast();

  // Form state
  const [reminderType, setReminderType] = useState<ReminderType>('CUSTOM');
  const [subject, setSubject] = useState('');
  const [message, setMessage] = useState('');
  const [selectedTeacherIds, setSelectedTeacherIds] = useState<string[]>([]);
  const [teacherSearch, setTeacherSearch] = useState('');
  const [sendMode, setSendMode] = useState<SendMode>('now');
  const [scheduledDate, setScheduledDate] = useState('');

  const debouncedTeacherSearch = useDebounce(teacherSearch, 300);
  const teacherIds = selectedTeacherIds.length > 0 ? selectedTeacherIds : undefined;

  // Queries
  const { data: teachers } = useQuery({
    queryKey: ['adminTeachersManualSend', debouncedTeacherSearch],
    queryFn: () =>
      adminTeachersService.listTeachers({ search: debouncedTeacherSearch || undefined }),
  });

  const availableTeachers = useMemo(() => {
    const selected = new Set(selectedTeacherIds);
    return (teachers ?? []).filter((t) => !selected.has(t.id));
  }, [teachers, selectedTeacherIds]);

  const selectedTeachers = useMemo(() => {
    return (teachers ?? []).filter((t) => selectedTeacherIds.includes(t.id));
  }, [teachers, selectedTeacherIds]);

  // Mutations
  const previewMutation = useMutation({
    mutationFn: () =>
      adminRemindersService.preview({
        reminder_type: reminderType,
        subject: subject || undefined,
        message: message || undefined,
        teacher_ids: teacherIds,
      }),
    onSuccess: (data) => {
      toast.info('Preview ready', `${data.recipient_count} recipient(s) will receive this reminder.`);
    },
    onError: (error: any) => {
      const msg =
        error?.response?.data?.error ||
        error?.response?.data?.detail ||
        error?.message ||
        'Could not generate preview.';
      toast.error('Preview failed', msg);
    },
  });

  const sendMutation = useMutation({
    mutationFn: () =>
      adminRemindersService.send({
        reminder_type: reminderType,
        subject: subject || undefined,
        message: message || undefined,
        teacher_ids: teacherIds,
        // TODO: Pass scheduled_at to API when sendMode === 'schedule'
      }),
    onSuccess: (data) => {
      toast.success(
        'Reminders sent!',
        `Successfully sent to ${data.sent} recipient(s).${data.failed > 0 ? ` ${data.failed} failed.` : ''}`
      );
      // Reset form
      setSubject('');
      setMessage('');
      setSelectedTeacherIds([]);
      onSent?.();
    },
    onError: (error: any) => {
      const msg =
        error?.response?.data?.error ||
        error?.response?.data?.detail ||
        error?.message ||
        'Could not send reminders.';
      toast.error('Send failed', msg);
    },
  });

  const handleSend = () => {
    if (sendMode === 'schedule' && !scheduledDate) {
      toast.error('Schedule required', 'Please select a date and time to schedule.');
      return;
    }
    sendMutation.mutate();
  };

  return (
    <div data-tour="admin-reminders-composer" className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-gray-900">Manual Send</h2>
        <p className="text-sm text-gray-500 mt-0.5">
          Send a one-off reminder to specific teachers or everyone.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Composer */}
        <div className="card space-y-4">
          {/* Type */}
          <div>
            <label htmlFor="manual-reminder-type" className="block text-sm font-medium text-gray-700 mb-1">
              Type
            </label>
            <select
              id="manual-reminder-type"
              value={reminderType}
              onChange={(e) => setReminderType(e.target.value as ReminderType)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
            >
              <option value="CUSTOM">Custom message</option>
              <option value="ASSIGNMENT_DUE">Assignment due</option>
            </select>
          </div>

          {/* Subject */}
          <Input
            id="manual-subject"
            name="manual_subject"
            label="Subject"
            autoComplete="off"
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            placeholder="Enter reminder subject"
          />

          {/* Message */}
          <div>
            <label htmlFor="manual-message" className="block text-sm font-medium text-gray-700 mb-1">
              Message
            </label>
            <textarea
              id="manual-message"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              rows={4}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
              placeholder="Write your reminder message here..."
            />
          </div>

          {/* Recipients */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Recipients</label>
            <p className="text-xs text-gray-500 mb-2">
              Leave empty to target all teachers.
            </p>

            {selectedTeacherIds.length > 0 && (
              <div className="flex flex-wrap gap-2 mb-2">
                {selectedTeachers.map((t) => (
                  <span
                    key={t.id}
                    className="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium bg-primary-100 text-primary-800 rounded-full"
                  >
                    {t.first_name} {t.last_name}
                    <button
                      type="button"
                      onClick={() =>
                        setSelectedTeacherIds((prev) => prev.filter((id) => id !== t.id))
                      }
                      className="hover:text-primary-600"
                    >
                      <XMarkIcon className="h-3 w-3" />
                    </button>
                  </span>
                ))}
                <button
                  type="button"
                  onClick={() => setSelectedTeacherIds([])}
                  className="text-xs text-gray-500 hover:text-gray-700 underline"
                >
                  Clear all
                </button>
              </div>
            )}

            <Input
              id="manual-teacher-search"
              name="manual_teacher_search"
              value={teacherSearch}
              onChange={(e) => setTeacherSearch(e.target.value)}
              placeholder="Search teachers to add..."
              autoComplete="off"
              leftIcon={<MagnifyingGlassIcon className="h-5 w-5" />}
            />
            {debouncedTeacherSearch && availableTeachers.length > 0 && (
              <div className="mt-1 max-h-32 overflow-y-auto border border-gray-200 rounded-lg bg-white">
                {availableTeachers.slice(0, 10).map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => {
                      setSelectedTeacherIds((prev) => [...prev, t.id]);
                      setTeacherSearch('');
                    }}
                    className="w-full text-left px-3 py-2 hover:bg-gray-50 border-b last:border-b-0 text-sm"
                  >
                    <div className="font-medium text-gray-900">
                      {t.first_name} {t.last_name}
                    </div>
                    <div className="text-xs text-gray-500">{t.email}</div>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Schedule toggle */}
          <div className="border-t border-gray-100 pt-4">
            <div className="flex items-center gap-4">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  name="send-mode"
                  checked={sendMode === 'now'}
                  onChange={() => setSendMode('now')}
                  className="text-primary-600 focus:ring-primary-500"
                />
                <span className="text-sm text-gray-700">Send Now</span>
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  name="send-mode"
                  checked={sendMode === 'schedule'}
                  onChange={() => setSendMode('schedule')}
                  className="text-primary-600 focus:ring-primary-500"
                />
                <span className="text-sm text-gray-700">Schedule</span>
              </label>
            </div>

            {sendMode === 'schedule' && (
              <div className="mt-3">
                <label
                  htmlFor="manual-schedule-date"
                  className="block text-sm font-medium text-gray-700 mb-1"
                >
                  <CalendarDaysIcon className="h-4 w-4 inline mr-1" />
                  Schedule Date & Time
                </label>
                <input
                  id="manual-schedule-date"
                  type="datetime-local"
                  value={scheduledDate}
                  onChange={(e) => setScheduledDate(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                />
              </div>
            )}
          </div>

          {/* Actions */}
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-end border-t border-gray-100 pt-4">
            <Button
              variant="outline"
              size="sm"
              onClick={() => previewMutation.mutate()}
              loading={previewMutation.isPending}
            >
              <EyeIcon className="h-4 w-4 mr-2" />
              Preview
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={handleSend}
              loading={sendMutation.isPending}
            >
              {sendMode === 'schedule' ? (
                <ClockIcon className="h-4 w-4 mr-2" />
              ) : (
                <PaperAirplaneIcon className="h-4 w-4 mr-2" />
              )}
              {sendMode === 'schedule' ? 'Schedule' : 'Send Now'}
            </Button>
          </div>
        </div>

        {/* Preview panel */}
        <div className="card">
          <h3 className="text-sm font-semibold text-gray-900 mb-3">Preview</h3>
          {!previewMutation.data ? (
            <div className="text-sm text-gray-500 py-8 text-center">
              Click Preview to see recipients and final email content.
            </div>
          ) : (
            <div className="space-y-3 text-sm">
              <div>
                <div className="text-gray-500">Recipients</div>
                <div className="font-medium text-gray-900">{previewMutation.data.recipient_count}</div>
              </div>
              <div>
                <div className="text-gray-500">Subject</div>
                <div className="font-medium text-gray-900">{previewMutation.data.resolved_subject}</div>
              </div>
              <div>
                <div className="text-gray-500">Message</div>
                <pre className="whitespace-pre-wrap bg-gray-50 border border-gray-200 rounded-lg p-3 text-gray-800 text-xs">
                  {previewMutation.data.resolved_message}
                </pre>
              </div>
              <div>
                <div className="text-gray-500 mb-1">Sample recipients</div>
                <ul className="space-y-1">
                  {previewMutation.data.recipients_preview.map((r) => (
                    <li key={r.id} className="text-gray-800">
                      {r.name} — <span className="text-gray-500">{r.email}</span>
                    </li>
                  ))}
                  {previewMutation.data.recipients_preview.length === 0 && (
                    <li className="text-gray-500">No recipients matched.</li>
                  )}
                </ul>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
