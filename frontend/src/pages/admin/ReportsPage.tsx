import React, { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { Button } from '../../components/common/Button';
import { Input } from '../../components/common/Input';
import { useToast } from '../../components/common';
import { adminReportsService } from '../../services/adminReportsService';
import { adminRemindersService } from '../../services/adminRemindersService';
import { usePageTitle } from '../../hooks/usePageTitle';
import {
  PaperAirplaneIcon,
  ClipboardDocumentCheckIcon,
  FunnelIcon,
  MagnifyingGlassIcon,
  LockClosedIcon,
} from '@heroicons/react/24/outline';

type Tab = 'COURSE' | 'ASSIGNMENT';

export const ReportsPage: React.FC = () => {
  usePageTitle('Reports');
  const toast = useToast();
  const [searchParams] = useSearchParams();
  const tabParam = searchParams.get('tab');
  const assignmentIdParam = searchParams.get('assignment_id');
  const statusParam = searchParams.get('status');
  const courseIdParam = searchParams.get('course_id');

  const [tab, setTab] = useState<Tab>(tabParam === 'ASSIGNMENT' ? 'ASSIGNMENT' : 'COURSE');
  const [courseId, setCourseId] = useState<string>(courseIdParam || '');
  const [courseStatus, setCourseStatus] = useState<string>(statusParam || '');
  const [courseSearch, setCourseSearch] = useState<string>('');
  const [selectedTeacherIds, setSelectedTeacherIds] = useState<string[]>([]);

  const [assignmentId, setAssignmentId] = useState<string>(assignmentIdParam || '');
  const [assignmentStatus, setAssignmentStatus] = useState<string>(statusParam || '');
  const [assignmentSearch, setAssignmentSearch] = useState<string>('');
  const [selectedAssignmentTeacherIds, setSelectedAssignmentTeacherIds] = useState<string[]>([]);

  useEffect(() => {
    if (tabParam === 'ASSIGNMENT' && assignmentIdParam) {
      setTab('ASSIGNMENT');
      setAssignmentId(assignmentIdParam);
      if (statusParam) setAssignmentStatus(statusParam);
    } else if (tabParam === 'COURSE' && courseIdParam) {
      setTab('COURSE');
      setCourseId(courseIdParam);
      if (statusParam) setCourseStatus(statusParam);
    }
  }, [tabParam, assignmentIdParam, statusParam, courseIdParam]);

  const { data: courses } = useQuery({
    queryKey: ['reportCourses'],
    queryFn: adminReportsService.listCourses,
  });

  const { data: assignments } = useQuery({
    queryKey: ['reportAssignments'],
    queryFn: () => adminReportsService.listAssignments(),
  });

  const { data: courseReport, isLoading: courseLoading } = useQuery({
    queryKey: ['courseProgressReport', courseId, courseStatus, courseSearch],
    queryFn: () => adminReportsService.courseProgress({ course_id: courseId, status: courseStatus || undefined, search: courseSearch || undefined }),
    enabled: tab === 'COURSE' && !!courseId,
    refetchInterval: 30000, // Auto-refresh every 30 seconds for real-time progress
  });

  const { data: assignmentReport, isLoading: assignmentLoading } = useQuery({
    queryKey: ['assignmentStatusReport', assignmentId, assignmentStatus, assignmentSearch],
    queryFn: () => adminReportsService.assignmentStatus({ assignment_id: assignmentId, status: assignmentStatus || undefined, search: assignmentSearch || undefined }),
    enabled: tab === 'ASSIGNMENT' && !!assignmentId,
    refetchInterval: 30000, // Auto-refresh every 30 seconds for real-time progress
  });

  const courseRows = courseReport?.results ?? [];
  const assignmentRows = assignmentReport?.results ?? [];

  const sendReminderMutation = useMutation({
    mutationFn: (payload: any) => adminRemindersService.send(payload),
    onSuccess: (data) => {
      toast.success('Reminders sent!', `Successfully sent to ${data.sent} recipient(s).${data.failed > 0 ? ` ${data.failed} failed.` : ''}`);
      setSelectedTeacherIds([]);
      setSelectedAssignmentTeacherIds([]);
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

  const courseSelectedCount = selectedTeacherIds.length;
  const assignmentSelectedCount = selectedAssignmentTeacherIds.length;

  const canSendAssignmentReminder = !!assignmentId && assignmentSelectedCount > 0;

  const courseAllSelected = useMemo(() => courseRows.length > 0 && courseSelectedCount === courseRows.length, [courseRows.length, courseSelectedCount]);
  const assignmentAllSelected = useMemo(() => assignmentRows.length > 0 && assignmentSelectedCount === assignmentRows.length, [assignmentRows.length, assignmentSelectedCount]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Reports</h1>
        <p className="mt-1 text-sm text-gray-500">
          Track progress and send reminders to teachers (single or bulk).
        </p>
      </div>

      <div className="border-b border-gray-200">
        <nav className="-mb-px flex gap-4 overflow-x-auto whitespace-nowrap">
          <button
            className={`py-4 px-1 border-b-2 font-medium text-sm ${tab === 'COURSE' ? 'border-primary-500 text-primary-600' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'}`}
            onClick={() => setTab('COURSE')}
          >
            Course Completion
          </button>
          <button
            className={`py-4 px-1 border-b-2 font-medium text-sm ${tab === 'ASSIGNMENT' ? 'border-primary-500 text-primary-600' : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'}`}
            onClick={() => setTab('ASSIGNMENT')}
          >
            Assignments
          </button>
        </nav>
      </div>

      {/* Course report */}
      {tab === 'COURSE' && (
        <div className="space-y-4">
          <div className="card">
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Course</label>
                <select
                  value={courseId}
                  onChange={(e) => {
                    setCourseId(e.target.value);
                    setSelectedTeacherIds([]);
                  }}
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
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  <FunnelIcon className="h-4 w-4 inline mr-1" />
                  Status
                </label>
                <select
                  value={courseStatus}
                  onChange={(e) => setCourseStatus(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                >
                  <option value="">All</option>
                  <option value="NOT_STARTED">Not started</option>
                  <option value="IN_PROGRESS">In progress</option>
                  <option value="COMPLETED">Completed</option>
                </select>
              </div>
              <div>
                <Input
                  value={courseSearch}
                  onChange={(e) => setCourseSearch(e.target.value)}
                  placeholder="Search teacher name/email…"
                  leftIcon={<MagnifyingGlassIcon className="h-5 w-5" />}
                />
              </div>
            </div>
          </div>

          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="text-sm text-gray-600">
              Selected: <span className="font-medium">{courseSelectedCount}</span>
            </div>
            <div className="inline-flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
              <LockClosedIcon className="h-4 w-4" />
              Course deadline reminders are automated (manual send locked).
            </div>
          </div>

          <div className="card overflow-x-auto">
            {!courseId ? (
              <div className="p-8 text-sm text-gray-500">Pick a course to view assigned teachers.</div>
            ) : courseLoading ? (
              <div className="p-8 text-sm text-gray-500">Loading…</div>
            ) : courseRows.length === 0 ? (
              <div className="p-8 text-sm text-gray-500">No assigned teachers found for this course.</div>
            ) : (
              <>
                <div className="space-y-3 md:hidden">
                  <label className="flex items-center gap-2 text-xs font-medium text-gray-600">
                    <input
                      type="checkbox"
                      checked={courseAllSelected}
                      onChange={(e) => setSelectedTeacherIds(e.target.checked ? courseRows.map((r) => r.teacher_id) : [])}
                    />
                    Select all
                  </label>
                  {courseRows.map((r) => (
                    <div key={r.teacher_id} className="rounded-lg border border-gray-200 p-3">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="text-sm font-semibold text-gray-900">{r.teacher_name}</p>
                          <p className="break-all text-xs text-gray-500">{r.teacher_email}</p>
                        </div>
                        <input
                          type="checkbox"
                          checked={selectedTeacherIds.includes(r.teacher_id)}
                          onChange={(e) =>
                            setSelectedTeacherIds((prev) =>
                              e.target.checked ? [...prev, r.teacher_id] : prev.filter((id) => id !== r.teacher_id)
                            )
                          }
                        />
                      </div>
                      <div className="mt-2 grid grid-cols-1 gap-1 text-xs text-gray-600">
                        <p>Status: <span className="font-medium text-gray-900">{r.status}</span></p>
                        <p>Completed: <span className="font-medium text-gray-900">{r.completed_at ? new Date(r.completed_at).toLocaleString() : '-'}</span></p>
                      </div>
                    </div>
                  ))}
                </div>

                <table className="hidden min-w-full text-sm md:table">
                  <thead className="text-left text-gray-500">
                    <tr>
                      <th className="py-3 pr-6">
                        <input
                          type="checkbox"
                          checked={courseAllSelected}
                          onChange={(e) => setSelectedTeacherIds(e.target.checked ? courseRows.map((r) => r.teacher_id) : [])}
                        />
                      </th>
                      <th className="py-3 pr-6">Teacher</th>
                      <th className="py-3 pr-6">Email</th>
                      <th className="py-3 pr-6">Status</th>
                      <th className="py-3 pr-6">Completed</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {courseRows.map((r) => (
                      <tr key={r.teacher_id} className="text-gray-800">
                        <td className="py-3 pr-6">
                          <input
                            type="checkbox"
                            checked={selectedTeacherIds.includes(r.teacher_id)}
                            onChange={(e) =>
                              setSelectedTeacherIds((prev) =>
                                e.target.checked ? [...prev, r.teacher_id] : prev.filter((id) => id !== r.teacher_id)
                              )
                            }
                          />
                        </td>
                        <td className="py-3 pr-6 font-medium">{r.teacher_name}</td>
                        <td className="py-3 pr-6">{r.teacher_email}</td>
                        <td className="py-3 pr-6">{r.status}</td>
                        <td className="py-3 pr-6">{r.completed_at ? new Date(r.completed_at).toLocaleString() : '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}
          </div>
        </div>
      )}

      {/* Assignment report */}
      {tab === 'ASSIGNMENT' && (
        <div className="space-y-4">
          <div className="card">
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Assignment</label>
                <select
                  value={assignmentId}
                  onChange={(e) => {
                    setAssignmentId(e.target.value);
                    setSelectedAssignmentTeacherIds([]);
                  }}
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
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  <FunnelIcon className="h-4 w-4 inline mr-1" />
                  Status
                </label>
                <select
                  value={assignmentStatus}
                  onChange={(e) => setAssignmentStatus(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                >
                  <option value="">All</option>
                  <option value="PENDING">Pending</option>
                  <option value="SUBMITTED">Submitted</option>
                  <option value="GRADED">Graded</option>
                </select>
              </div>
              <div>
                <Input
                  value={assignmentSearch}
                  onChange={(e) => setAssignmentSearch(e.target.value)}
                  placeholder="Search teacher name/email…"
                  leftIcon={<MagnifyingGlassIcon className="h-5 w-5" />}
                />
              </div>
            </div>
          </div>

          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="text-sm text-gray-600">
              Selected: <span className="font-medium">{assignmentSelectedCount}</span>
            </div>
            <Button
              variant="primary"
              disabled={!canSendAssignmentReminder}
              loading={sendReminderMutation.isPending}
              onClick={() =>
                sendReminderMutation.mutate({
                  reminder_type: 'ASSIGNMENT_DUE',
                  assignment_id: assignmentId,
                  teacher_ids: selectedAssignmentTeacherIds,
                })
              }
            >
              <PaperAirplaneIcon className="h-4 w-4 mr-2" />
              Send reminder
            </Button>
          </div>

          <div className="card overflow-x-auto">
            {!assignmentId ? (
              <div className="p-8 text-sm text-gray-500">Pick an assignment to view teacher statuses.</div>
            ) : assignmentLoading ? (
              <div className="p-8 text-sm text-gray-500">Loading…</div>
            ) : assignmentRows.length === 0 ? (
              <div className="p-8 text-sm text-gray-500">No records found for this assignment.</div>
            ) : (
              <>
                <div className="space-y-3 md:hidden">
                  <label className="flex items-center gap-2 text-xs font-medium text-gray-600">
                    <input
                      type="checkbox"
                      checked={assignmentAllSelected}
                      onChange={(e) => setSelectedAssignmentTeacherIds(e.target.checked ? assignmentRows.map((r) => r.teacher_id) : [])}
                    />
                    Select all
                  </label>
                  {assignmentRows.map((r) => (
                    <div key={r.teacher_id} className="rounded-lg border border-gray-200 p-3">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="text-sm font-semibold text-gray-900">{r.teacher_name}</p>
                          <p className="break-all text-xs text-gray-500">{r.teacher_email}</p>
                        </div>
                        <input
                          type="checkbox"
                          checked={selectedAssignmentTeacherIds.includes(r.teacher_id)}
                          onChange={(e) =>
                            setSelectedAssignmentTeacherIds((prev) =>
                              e.target.checked ? [...prev, r.teacher_id] : prev.filter((id) => id !== r.teacher_id)
                            )
                          }
                        />
                      </div>
                      <div className="mt-2 grid grid-cols-1 gap-1 text-xs text-gray-600">
                        <p>Status: <span className="font-medium text-gray-900">{r.status}</span></p>
                        <p>Submitted: <span className="font-medium text-gray-900">{r.submitted_at ? new Date(r.submitted_at).toLocaleString() : '-'}</span></p>
                      </div>
                    </div>
                  ))}
                </div>
                <table className="hidden min-w-full text-sm md:table">
                  <thead className="text-left text-gray-500">
                    <tr>
                      <th className="py-3 pr-6">
                        <input
                          type="checkbox"
                          checked={assignmentAllSelected}
                          onChange={(e) => setSelectedAssignmentTeacherIds(e.target.checked ? assignmentRows.map((r) => r.teacher_id) : [])}
                        />
                      </th>
                      <th className="py-3 pr-6">Teacher</th>
                      <th className="py-3 pr-6">Email</th>
                      <th className="py-3 pr-6">Status</th>
                      <th className="py-3 pr-6">Submitted</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {assignmentRows.map((r) => (
                      <tr key={r.teacher_id} className="text-gray-800">
                        <td className="py-3 pr-6">
                          <input
                            type="checkbox"
                            checked={selectedAssignmentTeacherIds.includes(r.teacher_id)}
                            onChange={(e) =>
                              setSelectedAssignmentTeacherIds((prev) =>
                                e.target.checked ? [...prev, r.teacher_id] : prev.filter((id) => id !== r.teacher_id)
                              )
                            }
                          />
                        </td>
                        <td className="py-3 pr-6 font-medium">{r.teacher_name}</td>
                        <td className="py-3 pr-6">{r.teacher_email}</td>
                        <td className="py-3 pr-6">{r.status}</td>
                        <td className="py-3 pr-6">{r.submitted_at ? new Date(r.submitted_at).toLocaleString() : '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}
          </div>

          <div className="text-xs text-gray-500 flex items-center">
            <ClipboardDocumentCheckIcon className="h-4 w-4 mr-1" />
            Tip: Filter to PENDING to target only teachers who haven’t submitted.
          </div>
        </div>
      )}
    </div>
  );
};
