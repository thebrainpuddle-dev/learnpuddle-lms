import React, { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Button } from '../../components/common/Button';
import { Input } from '../../components/common/Input';
import { useToast } from '../../components/common';
import { adminReportsService } from '../../services/adminReportsService';
import { adminRemindersService } from '../../services/adminRemindersService';
import { adminTeachersService } from '../../services/adminTeachersService';
import { PaperAirplaneIcon, EyeIcon, ClockIcon, MagnifyingGlassIcon, XMarkIcon } from '@heroicons/react/24/outline';
import { usePageTitle } from '../../hooks/usePageTitle';

// Debounce hook
function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);
  useEffect(() => {
    const handler = setTimeout(() => setDebouncedValue(value), delay);
    return () => clearTimeout(handler);
  }, [value, delay]);
  return debouncedValue;
}

type ReminderType = 'COURSE_DEADLINE' | 'ASSIGNMENT_DUE' | 'CUSTOM';

export const RemindersPage: React.FC = () => {
  usePageTitle('Reminders');
  const toast = useToast();
  const [reminderType, setReminderType] = useState<ReminderType>('COURSE_DEADLINE');
  const [courseId, setCourseId] = useState('');
  const [assignmentId, setAssignmentId] = useState('');
  const [deadlineOverride, setDeadlineOverride] = useState('');
  const [subject, setSubject] = useState('');
  const [message, setMessage] = useState('');
  const [selectedTeacherIds, setSelectedTeacherIds] = useState<string[]>([]);
  const [teacherSearch, setTeacherSearch] = useState('');
  const debouncedTeacherSearch = useDebounce(teacherSearch, 300);

  const teacherIds = selectedTeacherIds.length > 0 ? selectedTeacherIds : undefined;

  const { data: courses } = useQuery({
    queryKey: ['reportCourses'],
    queryFn: adminReportsService.listCourses,
  });

  const { data: assignments } = useQuery({
    queryKey: ['reportAssignments'],
    queryFn: () => adminReportsService.listAssignments(),
  });

  const { data: teachers } = useQuery({
    queryKey: ['adminTeachersReminders', debouncedTeacherSearch],
    queryFn: () => adminTeachersService.listTeachers({ search: debouncedTeacherSearch || undefined }),
  });

  const availableTeachers = useMemo(() => {
    const selected = new Set(selectedTeacherIds);
    return (teachers ?? []).filter((t) => !selected.has(t.id));
  }, [teachers, selectedTeacherIds]);

  const selectedTeachers = useMemo(() => {
    return (teachers ?? []).filter((t) => selectedTeacherIds.includes(t.id));
  }, [teachers, selectedTeacherIds]);

  const previewMutation = useMutation({
    mutationFn: () =>
      adminRemindersService.preview({
        reminder_type: reminderType,
        course_id: reminderType === 'COURSE_DEADLINE' ? courseId : undefined,
        assignment_id: reminderType === 'ASSIGNMENT_DUE' ? assignmentId : undefined,
        deadline_override: deadlineOverride || undefined,
        subject: subject || undefined,
        message: message || undefined,
        teacher_ids: teacherIds,
      }),
    onSuccess: (data) => {
      toast.info('Preview ready', `${data.recipient_count} recipient(s) will receive this reminder.`);
    },
    onError: (error: any) => {
      console.error('Preview error:', error);
      let message = 'Could not generate preview. Please try again.';
      if (error?.response?.data?.error) {
        message = error.response.data.error;
      } else if (error?.response?.data?.detail) {
        message = error.response.data.detail;
      } else if (error?.message) {
        message = error.message;
      }
      toast.error('Preview failed', message);
    },
  });

  const sendMutation = useMutation({
    mutationFn: () =>
      adminRemindersService.send({
        reminder_type: reminderType,
        course_id: reminderType === 'COURSE_DEADLINE' ? courseId : undefined,
        assignment_id: reminderType === 'ASSIGNMENT_DUE' ? assignmentId : undefined,
        deadline_override: deadlineOverride || undefined,
        subject: subject || undefined,
        message: message || undefined,
        teacher_ids: teacherIds,
      }),
    onSuccess: (data) => {
      toast.success(
        'Reminders sent!',
        `Successfully sent to ${data.sent} recipient(s).${data.failed > 0 ? ` ${data.failed} failed.` : ''}`
      );
      // refresh history
      historyQuery.refetch();
    },
    onError: (error: any) => {
      console.error('Reminder send error:', error);
      let message = 'Could not send reminders. Please try again.';
      if (error?.response?.data?.error) {
        message = error.response.data.error;
      } else if (error?.response?.data?.detail) {
        message = error.response.data.detail;
      } else if (error?.message) {
        message = error.message;
      }
      toast.error('Send failed', message);
    },
  });

  const historyQuery = useQuery({
    queryKey: ['remindersHistory'],
    queryFn: adminRemindersService.history,
  });

  const canPreview =
    reminderType === 'CUSTOM' ||
    (reminderType === 'COURSE_DEADLINE' && !!courseId) ||
    (reminderType === 'ASSIGNMENT_DUE' && !!assignmentId);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Reminders</h1>
        <p className="mt-1 text-sm text-gray-500">Send bulk or targeted email reminders and track history.</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Composer */}
        <div className="card space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Type</label>
              <select
                value={reminderType}
                onChange={(e) => setReminderType(e.target.value as ReminderType)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg"
              >
                <option value="COURSE_DEADLINE">Course deadline</option>
                <option value="ASSIGNMENT_DUE">Assignment due</option>
                <option value="CUSTOM">Custom</option>
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                <ClockIcon className="h-4 w-4 inline mr-1" />
                Deadline override (optional)
              </label>
              <input
                type="datetime-local"
                value={deadlineOverride}
                onChange={(e) => setDeadlineOverride(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg"
              />
            </div>
          </div>

          {reminderType === 'COURSE_DEADLINE' && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Course</label>
              <select
                value={courseId}
                onChange={(e) => setCourseId(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg"
              >
                <option value="">Select a course…</option>
                {(courses ?? []).map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.title}
                  </option>
                ))}
              </select>
            </div>
          )}

          {reminderType === 'ASSIGNMENT_DUE' && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Assignment</label>
              <select
                value={assignmentId}
                onChange={(e) => setAssignmentId(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg"
              >
                <option value="">Select an assignment…</option>
                {(assignments ?? []).map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.title}
                  </option>
                ))}
              </select>
            </div>
          )}

          <Input label="Subject (optional)" value={subject} onChange={(e) => setSubject(e.target.value)} />
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Message (optional)</label>
            <textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              rows={4}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg"
              placeholder="Add a custom note. The system will prepend the core reminder text."
            />
          </div>

          {/* Target specific teachers (optional) */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Target specific teachers (optional)
            </label>
            <p className="text-xs text-gray-500 mb-2">
              Leave empty to target all relevant teachers (e.g., not completed / not submitted).
            </p>

            {/* Selected teachers */}
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
                      onClick={() => setSelectedTeacherIds((prev) => prev.filter((id) => id !== t.id))}
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

            {/* Search and add teachers */}
            <Input
              value={teacherSearch}
              onChange={(e) => setTeacherSearch(e.target.value)}
              placeholder="Search teachers to add…"
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

          <div className="flex items-center justify-end gap-3">
            <Button
              variant="outline"
              onClick={() => previewMutation.mutate()}
              disabled={!canPreview}
              loading={previewMutation.isPending}
            >
              <EyeIcon className="h-4 w-4 mr-2" />
              Preview
            </Button>
            <Button
              variant="primary"
              onClick={() => sendMutation.mutate()}
              disabled={!canPreview}
              loading={sendMutation.isPending}
            >
              <PaperAirplaneIcon className="h-4 w-4 mr-2" />
              Send
            </Button>
          </div>
        </div>

        {/* Preview + History */}
        <div className="space-y-6">
          <div className="card">
            <h2 className="text-lg font-semibold text-gray-900 mb-3">Preview</h2>
            {!previewMutation.data ? (
              <div className="text-sm text-gray-500">Click Preview to see recipients and final email content.</div>
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
                  <pre className="whitespace-pre-wrap bg-gray-50 border border-gray-200 rounded-lg p-3 text-gray-800">
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

          <div className="card">
            <h2 className="text-lg font-semibold text-gray-900 mb-3">History</h2>
            {historyQuery.isLoading ? (
              <div className="text-sm text-gray-500">Loading…</div>
            ) : (historyQuery.data?.results.length || 0) === 0 ? (
              <div className="text-sm text-gray-500">No reminders sent yet.</div>
            ) : (
              <div className="space-y-3">
                {historyQuery.data?.results.slice(0, 10).map((c) => (
                  <div key={c.id} className="border border-gray-200 rounded-lg p-3">
                    <div className="flex items-center justify-between">
                      <div className="font-medium text-gray-900">{c.subject}</div>
                      <div className="text-xs text-gray-500">{new Date(c.created_at).toLocaleString()}</div>
                    </div>
                    <div className="text-xs text-gray-600 mt-1">
                      {c.reminder_type} • sent: {c.sent_count} • failed: {c.failed_count}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

