// src/components/analytics/ReportDrillDown.tsx
//
// Extracted from ReportsPage.tsx — reusable report table with
// course completion and assignment status views.
// Embeddable in AnalyticsPage as a drill-down component.
// Keeps: tabular data, filtering, search, export functionality (CSV/PDF).

import React, { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Button } from '../../components/common/Button';
import { Input } from '../../components/common/Input';
import { useToast } from '../../components/common';
import { adminReportsService } from '../../services/adminReportsService';
import { adminRemindersService } from '../../services/adminRemindersService';
import {
  PaperAirplaneIcon,
  FunnelIcon,
  MagnifyingGlassIcon,
  LockClosedIcon,
  ArrowDownTrayIcon,
  UserGroupIcon,
  AcademicCapIcon,
} from '@heroicons/react/24/outline';

type Tab = 'COURSE' | 'ASSIGNMENT';
type RoleFilter = 'teachers' | 'students';

interface ReportDrillDownProps {
  /** Optional: pre-select a tab */
  defaultTab?: Tab;
  /** Optional: pre-select a course */
  defaultCourseId?: string;
  /** Optional: pre-select an assignment */
  defaultAssignmentId?: string;
  /** Optional: pre-select a status filter */
  defaultStatus?: string;
  /** Optional: pre-select role filter */
  defaultRole?: RoleFilter;
}

export const ReportDrillDown: React.FC<ReportDrillDownProps> = ({
  defaultTab = 'COURSE',
  defaultCourseId = '',
  defaultAssignmentId = '',
  defaultStatus = '',
  defaultRole = 'teachers',
}) => {
  const toast = useToast();

  const [tab, setTab] = useState<Tab>(defaultTab);
  const [role, setRole] = useState<RoleFilter>(defaultRole);
  const [courseId, setCourseId] = useState<string>(defaultCourseId);
  const [courseStatus, setCourseStatus] = useState<string>(defaultStatus);
  const [courseSearch, setCourseSearch] = useState<string>('');
  const [selectedTeacherIds, setSelectedTeacherIds] = useState<string[]>([]);

  const [assignmentId, setAssignmentId] = useState<string>(defaultAssignmentId);
  const [assignmentStatus, setAssignmentStatus] = useState<string>(defaultStatus);
  const [assignmentSearch, setAssignmentSearch] = useState<string>('');
  const [selectedAssignmentTeacherIds, setSelectedAssignmentTeacherIds] = useState<string[]>([]);

  const isStudents = role === 'students';
  const personLabel = isStudents ? 'Student' : 'Teacher';
  const searchPlaceholder = isStudents ? 'Search student name/email/ID...' : 'Search teacher name/email...';

  const { data: courses } = useQuery({
    queryKey: ['reportCourses'],
    queryFn: adminReportsService.listCourses,
  });

  const { data: assignments } = useQuery({
    queryKey: ['reportAssignments'],
    queryFn: () => adminReportsService.listAssignments(),
  });

  const { data: courseReport, isLoading: courseLoading } = useQuery({
    queryKey: ['courseProgressReport', courseId, courseStatus, courseSearch, role],
    queryFn: () =>
      adminReportsService.courseProgress({
        course_id: courseId,
        role,
        status: courseStatus || undefined,
        search: courseSearch || undefined,
      }),
    enabled: tab === 'COURSE' && !!courseId,
    refetchInterval: 30000,
  });

  const { data: assignmentReport, isLoading: assignmentLoading } = useQuery({
    queryKey: ['assignmentStatusReport', assignmentId, assignmentStatus, assignmentSearch, role],
    queryFn: () =>
      adminReportsService.assignmentStatus({
        assignment_id: assignmentId,
        role,
        status: assignmentStatus || undefined,
        search: assignmentSearch || undefined,
      }),
    enabled: tab === 'ASSIGNMENT' && !!assignmentId,
    refetchInterval: 30000,
  });

  const courseRows = courseReport?.results ?? [];
  const assignmentRows = assignmentReport?.results ?? [];

  const sendReminderMutation = useMutation({
    mutationFn: (payload: any) => adminRemindersService.send(payload),
    onSuccess: (data) => {
      toast.success(
        'Reminders sent!',
        `Successfully sent to ${data.sent} recipient(s).${data.failed > 0 ? ` ${data.failed} failed.` : ''}`
      );
      setSelectedTeacherIds([]);
      setSelectedAssignmentTeacherIds([]);
    },
    onError: (error: any) => {
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

  const canSendAssignmentReminder = !!assignmentId && selectedAssignmentTeacherIds.length > 0;

  const courseAllSelected = useMemo(
    () => courseRows.length > 0 && selectedTeacherIds.length === courseRows.length,
    [courseRows.length, selectedTeacherIds.length]
  );
  const assignmentAllSelected = useMemo(
    () => assignmentRows.length > 0 && selectedAssignmentTeacherIds.length === assignmentRows.length,
    [assignmentRows.length, selectedAssignmentTeacherIds.length]
  );

  // Clear selections when switching role
  useEffect(() => {
    setSelectedTeacherIds([]);
    setSelectedAssignmentTeacherIds([]);
  }, [role]);

  // CSV export helper
  const handleExportCSV = () => {
    const rows = tab === 'COURSE' ? courseRows : assignmentRows;
    if (rows.length === 0) return;

    const headers =
      tab === 'COURSE'
        ? isStudents
          ? [personLabel, 'Email', 'Grade', 'Section', 'Status', 'Completed At']
          : [personLabel, 'Email', 'Status', 'Completed At']
        : isStudents
          ? [personLabel, 'Email', 'Grade', 'Section', 'Status', 'Submitted At']
          : [personLabel, 'Email', 'Status', 'Submitted At'];

    const csvContent = [
      headers.join(','),
      ...rows.map((r: any) => {
        const base = [
          `"${r.teacher_name}"`,
          `"${r.teacher_email}"`,
        ];
        if (isStudents) {
          base.push(`"${r.grade_level || ''}"`, `"${r.section || ''}"`);
        }
        base.push(r.status, r.completed_at || r.submitted_at || '');
        return base.join(',');
      }),
    ].join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `report-${tab.toLowerCase()}-${role}-${new Date().toISOString().slice(0, 10)}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6">
      {/* Tab navigation + Role toggle */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-b border-gray-200 pb-0">
        <nav className="-mb-px flex gap-4 overflow-x-auto whitespace-nowrap">
          <button
            className={`py-4 px-1 border-b-2 font-medium text-sm ${
              tab === 'COURSE'
                ? 'border-primary-500 text-primary-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
            onClick={() => setTab('COURSE')}
          >
            Course Completion
          </button>
          <button
            className={`py-4 px-1 border-b-2 font-medium text-sm ${
              tab === 'ASSIGNMENT'
                ? 'border-primary-500 text-primary-600'
                : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
            }`}
            onClick={() => setTab('ASSIGNMENT')}
          >
            Assignments
          </button>
        </nav>

        {/* Role toggle */}
        <div className="flex rounded-lg border border-gray-200 bg-white overflow-hidden mb-px">
          <button
            type="button"
            onClick={() => setRole('teachers')}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium transition-colors border-r border-gray-200 ${
              role === 'teachers' ? 'bg-primary-50 text-primary-700' : 'text-gray-600 hover:bg-gray-50'
            }`}
          >
            <UserGroupIcon className="h-3.5 w-3.5" />
            Teachers
          </button>
          <button
            type="button"
            onClick={() => setRole('students')}
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium transition-colors ${
              role === 'students' ? 'bg-primary-50 text-primary-700' : 'text-gray-600 hover:bg-gray-50'
            }`}
          >
            <AcademicCapIcon className="h-3.5 w-3.5" />
            Students
          </button>
        </div>
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
                  <option value="">Select a course...</option>
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
                  placeholder={searchPlaceholder}
                  leftIcon={<MagnifyingGlassIcon className="h-5 w-5" />}
                />
              </div>
            </div>
          </div>

          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="text-sm text-gray-600">
              Selected: <span className="font-medium">{selectedTeacherIds.length}</span>
            </div>
            <div className="flex items-center gap-2">
              {courseRows.length > 0 && (
                <button
                  onClick={handleExportCSV}
                  className="inline-flex items-center gap-1 px-3 py-2 text-xs font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
                >
                  <ArrowDownTrayIcon className="h-4 w-4" />
                  Export CSV
                </button>
              )}
              <div className="inline-flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                <LockClosedIcon className="h-4 w-4" />
                Course deadline reminders are automated (manual send locked).
              </div>
            </div>
          </div>

          <div className="card overflow-x-auto">
            {!courseId ? (
              <div className="p-8 text-sm text-gray-500">Pick a course to view assigned {role}.</div>
            ) : courseLoading ? (
              <div className="p-8 text-sm text-gray-500">Loading...</div>
            ) : courseRows.length === 0 ? (
              <div className="p-8 text-sm text-gray-500">No assigned {role} found for this course.</div>
            ) : (
              <>
                {/* Mobile */}
                <div className="space-y-3 md:hidden">
                  <label className="flex items-center gap-2 text-xs font-medium text-gray-600">
                    <input
                      type="checkbox"
                      checked={courseAllSelected}
                      onChange={(e) =>
                        setSelectedTeacherIds(e.target.checked ? courseRows.map((r) => r.teacher_id) : [])
                      }
                    />
                    Select all
                  </label>
                  {courseRows.map((r) => (
                    <div key={r.teacher_id} className="rounded-lg border border-gray-200 p-3">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="text-sm font-semibold text-gray-900">{r.teacher_name}</p>
                          <p className="break-all text-xs text-gray-500">{r.teacher_email}</p>
                          {isStudents && (r.grade_level || r.section) && (
                            <p className="text-xs text-gray-400 mt-0.5">
                              {r.grade_level}{r.grade_level && r.section ? ' · ' : ''}{r.section}
                            </p>
                          )}
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
                        <p>
                          Status: <span className="font-medium text-gray-900">{r.status}</span>
                        </p>
                        <p>
                          Completed:{' '}
                          <span className="font-medium text-gray-900">
                            {r.completed_at ? new Date(r.completed_at).toLocaleString() : '-'}
                          </span>
                        </p>
                      </div>
                    </div>
                  ))}
                </div>

                {/* Desktop */}
                <table className="hidden min-w-full text-sm md:table">
                  <thead className="text-left text-gray-500">
                    <tr>
                      <th className="py-3 pr-6">
                        <input
                          type="checkbox"
                          checked={courseAllSelected}
                          onChange={(e) =>
                            setSelectedTeacherIds(e.target.checked ? courseRows.map((r) => r.teacher_id) : [])
                          }
                        />
                      </th>
                      <th className="py-3 pr-6">{personLabel}</th>
                      <th className="py-3 pr-6">Email</th>
                      {isStudents && <th className="py-3 pr-6">Grade</th>}
                      {isStudents && <th className="py-3 pr-6">Section</th>}
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
                                e.target.checked
                                  ? [...prev, r.teacher_id]
                                  : prev.filter((id) => id !== r.teacher_id)
                              )
                            }
                          />
                        </td>
                        <td className="py-3 pr-6 font-medium">{r.teacher_name}</td>
                        <td className="py-3 pr-6">{r.teacher_email}</td>
                        {isStudents && <td className="py-3 pr-6">{r.grade_level || '-'}</td>}
                        {isStudents && <td className="py-3 pr-6">{r.section || '-'}</td>}
                        <td className="py-3 pr-6">
                          <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                            r.status === 'COMPLETED' ? 'bg-emerald-50 text-emerald-700' :
                            r.status === 'IN_PROGRESS' ? 'bg-blue-50 text-blue-700' :
                            'bg-gray-100 text-gray-600'
                          }`}>
                            {r.status === 'NOT_STARTED' ? 'Not Started' : r.status === 'IN_PROGRESS' ? 'In Progress' : 'Completed'}
                          </span>
                        </td>
                        <td className="py-3 pr-6">
                          {r.completed_at ? new Date(r.completed_at).toLocaleString() : '-'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>

                {/* Summary bar */}
                <div className="mt-4 flex flex-wrap gap-4 text-xs text-gray-500 border-t border-gray-100 pt-3">
                  <span>Total: <strong className="text-gray-700">{courseRows.length}</strong></span>
                  <span>Completed: <strong className="text-emerald-600">{courseRows.filter(r => r.status === 'COMPLETED').length}</strong></span>
                  <span>In Progress: <strong className="text-blue-600">{courseRows.filter(r => r.status === 'IN_PROGRESS').length}</strong></span>
                  <span>Not Started: <strong className="text-gray-600">{courseRows.filter(r => r.status === 'NOT_STARTED').length}</strong></span>
                </div>
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
                  <option value="">Select an assignment...</option>
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
                  placeholder={searchPlaceholder}
                  leftIcon={<MagnifyingGlassIcon className="h-5 w-5" />}
                />
              </div>
            </div>
          </div>

          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="text-sm text-gray-600">
              Selected: <span className="font-medium">{selectedAssignmentTeacherIds.length}</span>
            </div>
            <div className="flex items-center gap-2">
              {assignmentRows.length > 0 && (
                <button
                  onClick={handleExportCSV}
                  className="inline-flex items-center gap-1 px-3 py-2 text-xs font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
                >
                  <ArrowDownTrayIcon className="h-4 w-4" />
                  Export CSV
                </button>
              )}
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
          </div>

          <div className="card overflow-x-auto">
            {!assignmentId ? (
              <div className="p-8 text-sm text-gray-500">Pick an assignment to view {role} statuses.</div>
            ) : assignmentLoading ? (
              <div className="p-8 text-sm text-gray-500">Loading...</div>
            ) : assignmentRows.length === 0 ? (
              <div className="p-8 text-sm text-gray-500">No records found for this assignment.</div>
            ) : (
              <>
                {/* Mobile */}
                <div className="space-y-3 md:hidden">
                  <label className="flex items-center gap-2 text-xs font-medium text-gray-600">
                    <input
                      type="checkbox"
                      checked={assignmentAllSelected}
                      onChange={(e) =>
                        setSelectedAssignmentTeacherIds(
                          e.target.checked ? assignmentRows.map((r) => r.teacher_id) : []
                        )
                      }
                    />
                    Select all
                  </label>
                  {assignmentRows.map((r) => (
                    <div key={r.teacher_id} className="rounded-lg border border-gray-200 p-3">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="text-sm font-semibold text-gray-900">{r.teacher_name}</p>
                          <p className="break-all text-xs text-gray-500">{r.teacher_email}</p>
                          {isStudents && (r.grade_level || r.section) && (
                            <p className="text-xs text-gray-400 mt-0.5">
                              {r.grade_level}{r.grade_level && r.section ? ' · ' : ''}{r.section}
                            </p>
                          )}
                        </div>
                        <input
                          type="checkbox"
                          checked={selectedAssignmentTeacherIds.includes(r.teacher_id)}
                          onChange={(e) =>
                            setSelectedAssignmentTeacherIds((prev) =>
                              e.target.checked
                                ? [...prev, r.teacher_id]
                                : prev.filter((id) => id !== r.teacher_id)
                            )
                          }
                        />
                      </div>
                      <div className="mt-2 grid grid-cols-1 gap-1 text-xs text-gray-600">
                        <p>
                          Status: <span className="font-medium text-gray-900">{r.status}</span>
                        </p>
                        <p>
                          Submitted:{' '}
                          <span className="font-medium text-gray-900">
                            {r.submitted_at ? new Date(r.submitted_at).toLocaleString() : '-'}
                          </span>
                        </p>
                      </div>
                    </div>
                  ))}
                </div>

                {/* Desktop */}
                <table className="hidden min-w-full text-sm md:table">
                  <thead className="text-left text-gray-500">
                    <tr>
                      <th className="py-3 pr-6">
                        <input
                          type="checkbox"
                          checked={assignmentAllSelected}
                          onChange={(e) =>
                            setSelectedAssignmentTeacherIds(
                              e.target.checked ? assignmentRows.map((r) => r.teacher_id) : []
                            )
                          }
                        />
                      </th>
                      <th className="py-3 pr-6">{personLabel}</th>
                      <th className="py-3 pr-6">Email</th>
                      {isStudents && <th className="py-3 pr-6">Grade</th>}
                      {isStudents && <th className="py-3 pr-6">Section</th>}
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
                                e.target.checked
                                  ? [...prev, r.teacher_id]
                                  : prev.filter((id) => id !== r.teacher_id)
                              )
                            }
                          />
                        </td>
                        <td className="py-3 pr-6 font-medium">{r.teacher_name}</td>
                        <td className="py-3 pr-6">{r.teacher_email}</td>
                        {isStudents && <td className="py-3 pr-6">{r.grade_level || '-'}</td>}
                        {isStudents && <td className="py-3 pr-6">{r.section || '-'}</td>}
                        <td className="py-3 pr-6">
                          <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                            r.status === 'GRADED' ? 'bg-emerald-50 text-emerald-700' :
                            r.status === 'SUBMITTED' ? 'bg-blue-50 text-blue-700' :
                            'bg-amber-50 text-amber-700'
                          }`}>
                            {r.status}
                          </span>
                        </td>
                        <td className="py-3 pr-6">
                          {r.submitted_at ? new Date(r.submitted_at).toLocaleString() : '-'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>

                {/* Summary bar */}
                <div className="mt-4 flex flex-wrap gap-4 text-xs text-gray-500 border-t border-gray-100 pt-3">
                  <span>Total: <strong className="text-gray-700">{assignmentRows.length}</strong></span>
                  <span>Graded: <strong className="text-emerald-600">{assignmentRows.filter(r => r.status === 'GRADED').length}</strong></span>
                  <span>Submitted: <strong className="text-blue-600">{assignmentRows.filter(r => r.status === 'SUBMITTED').length}</strong></span>
                  <span>Pending: <strong className="text-amber-600">{assignmentRows.filter(r => r.status === 'PENDING').length}</strong></span>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
