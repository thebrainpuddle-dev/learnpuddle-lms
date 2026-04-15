// src/pages/admin/StudentsPage.tsx
//
// Admin student management — list, search, filter, create, edit,
// bulk import, bulk actions, invitations.

import React, { useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { z } from 'zod';
import { Controller } from 'react-hook-form';
import { Button, Input, useToast, ConfirmDialog } from '../../components/common';
import { FormField } from '../../components/common/FormField';
import { useZodForm } from '../../hooks/useZodForm';
import { BulkActionsBar, BulkAction } from '../../components/common/BulkActionsBar';
import { adminStudentsService } from '../../services/adminStudentsService';
import type { Student } from '../../services/adminStudentsService';
import { useTenantStore } from '../../stores/tenantStore';
import {
  MagnifyingGlassIcon,
  UserPlusIcon,
  PencilIcon,
  XMarkIcon,
  ArrowUpTrayIcon,
  CheckCircleIcon,
  XCircleIcon,
  TrashIcon,
  PlayIcon,
  StopIcon,
  EnvelopeIcon,
  ClockIcon,
  ArrowPathIcon,
  FunnelIcon,
} from '@heroicons/react/24/outline';
import { usePageTitle } from '../../hooks/usePageTitle';
import axios from 'axios';

// ── Zod Schemas ──────────────────────────────────────────────────────

const CreateStudentSchema = z
  .object({
    email: z.string().min(1, 'Email is required').email('Enter a valid email'),
    first_name: z.string().min(1, 'First name is required').max(150),
    last_name: z.string().min(1, 'Last name is required').max(150),
    password: z.string().min(8, 'Password must be at least 8 characters').max(128),
    password_confirm: z.string().min(1, 'Please confirm the password'),
    student_id: z.string().max(50).optional().or(z.literal('')),
    grade_level: z.string().optional().or(z.literal('')),
    section: z.string().optional().or(z.literal('')),
    parent_email: z.string().email('Enter a valid email').optional().or(z.literal('')),
    enrollment_date: z.string().optional().or(z.literal('')),
  })
  .refine((data) => data.password === data.password_confirm, {
    path: ['password_confirm'],
    message: 'Passwords do not match',
  });

type CreateStudentData = z.infer<typeof CreateStudentSchema>;

const EditStudentSchema = z.object({
  first_name: z.string().optional().or(z.literal('')),
  last_name: z.string().optional().or(z.literal('')),
  student_id: z.string().optional().or(z.literal('')),
  grade_level: z.string().optional().or(z.literal('')),
  section: z.string().optional().or(z.literal('')),
  parent_email: z.string().email('Enter a valid email').optional().or(z.literal('')),
  enrollment_date: z.string().optional().or(z.literal('')),
  is_active: z.boolean().default(true),
});

type EditStudentData = z.infer<typeof EditStudentSchema>;

const InviteStudentSchema = z.object({
  email: z.string().min(1, 'Email is required').email('Enter a valid email'),
  first_name: z.string().min(1, 'First name is required'),
  last_name: z.string().optional().or(z.literal('')),
});

type InviteStudentData = z.infer<typeof InviteStudentSchema>;

const INVITE_STATUS_COLORS: Record<string, string> = {
  pending: 'bg-yellow-100 text-yellow-700',
  accepted: 'bg-green-100 text-green-700',
  expired: 'bg-gray-100 text-gray-500',
};

export const StudentsPage: React.FC = () => {
  usePageTitle('Students');
  const toast = useToast();
  const qc = useQueryClient();
  const csvRef = useRef<HTMLInputElement>(null);
  const inviteCsvRef = useRef<HTMLInputElement>(null);
  const { usage } = useTenantStore();
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = searchParams.get('tab') || 'students';
  const [search, setSearch] = useState('');
  const [gradeFilter, setGradeFilter] = useState('');
  const [sectionFilter, setSectionFilter] = useState('');
  const [editingStudent, setEditingStudent] = useState<Student | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [deleteTarget, setDeleteTarget] = useState<Student | null>(null);
  const [showInviteForm, setShowInviteForm] = useState(false);
  const [showFilters, setShowFilters] = useState(false);

  const createForm = useZodForm({
    schema: CreateStudentSchema,
    defaultValues: {
      email: '', first_name: '', last_name: '', password: '', password_confirm: '',
      student_id: '', grade_level: '', section: '', parent_email: '', enrollment_date: '',
    },
  });

  const editForm = useZodForm({
    schema: EditStudentSchema,
    defaultValues: {
      first_name: '', last_name: '', student_id: '', grade_level: '',
      section: '', parent_email: '', enrollment_date: '', is_active: true,
    },
  });

  const inviteForm = useZodForm({
    schema: InviteStudentSchema,
    defaultValues: { email: '', first_name: '', last_name: '' },
  });

  // ── Queries ─────────────────────────────────────────────────────────

  const { data: studentsData, isLoading } = useQuery({
    queryKey: ['adminStudents', search, gradeFilter, sectionFilter],
    queryFn: () => adminStudentsService.listStudents({
      search: search || undefined,
      grade_level: gradeFilter || undefined,
      section: sectionFilter || undefined,
    }),
  });

  const { data: invitations } = useQuery({
    queryKey: ['studentInvitations'],
    queryFn: () => adminStudentsService.listInvitations(),
    enabled: activeTab === 'invitations',
  });

  // ── Mutations ───────────────────────────────────────────────────────

  const createMut = useMutation({
    mutationFn: (data: CreateStudentData) => adminStudentsService.createStudent(data),
    onSuccess: (_, data) => {
      qc.invalidateQueries({ queryKey: ['adminStudents'] });
      toast.success('Student created', `${data.first_name} ${data.last_name} has been added.`);
      setShowCreateForm(false);
      createForm.reset();
    },
    onError: (error) => {
      if (axios.isAxiosError(error) && error.response?.data) {
        const serverErrors = error.response.data as Record<string, string[]>;
        (Object.keys(serverErrors) as Array<keyof CreateStudentData>).forEach((field) => {
          const messages = serverErrors[field as string];
          if (Array.isArray(messages) && messages.length > 0) {
            createForm.setError(field, { type: 'server', message: messages[0] });
          }
        });
        const firstError = Object.values(serverErrors).flat()[0];
        if (firstError) toast.error('Validation error', String(firstError));
      } else {
        toast.error('Failed to create student', 'Please try again.');
      }
    },
  });

  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<Student> }) =>
      adminStudentsService.updateStudent(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['adminStudents'] });
      setEditingStudent(null);
      toast.success('Student updated', '');
    },
    onError: () => toast.error('Failed', 'Could not update student.'),
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => adminStudentsService.deleteStudent(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['adminStudents'] });
      toast.success('Student removed', '');
    },
  });

  const importMut = useMutation({
    mutationFn: (file: File) => adminStudentsService.bulkImportCSV(file),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['adminStudents'] });
      toast.success('Import complete', `${data.created} of ${data.total_rows} students created.`);
    },
    onError: () => toast.error('Import failed', 'Check CSV format.'),
  });

  const bulkActionMut = useMutation({
    mutationFn: ({ action, studentIds }: { action: 'activate' | 'deactivate' | 'delete'; studentIds: string[] }) =>
      adminStudentsService.bulkAction(action, studentIds),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['adminStudents'] });
      toast.success('Bulk action complete', data.message);
      setSelectedIds(new Set());
    },
    onError: () => toast.error('Bulk action failed', 'Please try again.'),
  });

  const inviteMut = useMutation({
    mutationFn: (data: { email: string; first_name: string; last_name?: string }) =>
      adminStudentsService.createInvitation(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['studentInvitations'] });
      toast.success('Invitation Sent', 'An invitation email has been sent.');
      setShowInviteForm(false);
      inviteForm.reset();
    },
    onError: (err: any) => {
      const detail = err?.response?.data;
      if (detail && typeof detail === 'object') {
        Object.entries(detail).forEach(([field, messages]) => {
          if (field in InviteStudentSchema.shape) {
            inviteForm.setError(field as keyof InviteStudentData, {
              type: 'server',
              message: Array.isArray(messages) ? (messages as string[])[0] : String(messages),
            });
          }
        });
      }
      toast.error('Error', err?.response?.data?.error || 'Failed to send invitation');
    },
  });

  const bulkInviteMut = useMutation({
    mutationFn: (file: File) => adminStudentsService.bulkInviteCSV(file),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['studentInvitations'] });
      toast.success('Bulk Invite Complete', `${data.created} of ${data.total_rows} invitations sent.`);
    },
    onError: () => toast.error('Bulk Invite Failed', 'Check CSV format.'),
  });

  // ── Derived state ───────────────────────────────────────────────────

  const rows = useMemo(() => studentsData?.results ?? [], [studentsData]);
  const totalCount = studentsData?.count ?? 0;

  // Unique grades and sections from current results for filter dropdowns
  const gradeOptions = useMemo(() => {
    const grades = new Set(rows.map((s) => s.grade_level).filter(Boolean));
    return Array.from(grades).sort();
  }, [rows]);

  const sectionOptions = useMemo(() => {
    const sections = new Set(rows.map((s) => s.section).filter(Boolean));
    return Array.from(sections).sort();
  }, [rows]);

  // ── Selection helpers ───────────────────────────────────────────────

  const toggleSelection = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    setSelectedIds(selectedIds.size === rows.length ? new Set() : new Set(rows.map((s) => s.id)));
  };

  const clearSelection = () => setSelectedIds(new Set());

  const handleBulkAction = (actionId: string) => {
    bulkActionMut.mutate({ action: actionId as 'activate' | 'deactivate' | 'delete', studentIds: Array.from(selectedIds) });
  };

  const bulkActions: BulkAction[] = [
    { id: 'activate', label: 'Activate', icon: PlayIcon, variant: 'success' },
    { id: 'deactivate', label: 'Deactivate', icon: StopIcon, variant: 'default' },
    { id: 'delete', label: 'Delete', icon: TrashIcon, variant: 'danger', requiresConfirmation: true },
  ];

  const openEdit = (s: Student) => {
    setEditingStudent(s);
    editForm.reset({
      first_name: s.first_name || '',
      last_name: s.last_name || '',
      student_id: s.student_id || '',
      grade_level: s.grade_level || '',
      section: s.section || '',
      parent_email: s.parent_email || '',
      enrollment_date: s.enrollment_date || '',
      is_active: s.is_active ?? true,
    });
  };

  const setTab = (tab: string) => {
    setSearchParams({ tab });
    setSearch('');
  };

  const clearFilters = () => {
    setGradeFilter('');
    setSectionFilter('');
    setSearch('');
  };

  // ── Render ──────────────────────────────────────────────────────────

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Students</h1>
          <p className="mt-1 text-sm text-gray-500">
            Manage student accounts, enroll by class, or send invitations.
            {usage && (usage as any).students && (
              <span className="ml-2 text-gray-400">
                ({(usage as any).students.used}/{(usage as any).students.limit} used)
              </span>
            )}
          </p>
        </div>
        {activeTab === 'students' && (
          <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:items-center">
            <input
              ref={csvRef}
              name="students_csv_import"
              type="file"
              accept=".csv"
              className="hidden"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) importMut.mutate(f); }}
            />
            <Button className="w-full sm:w-auto" variant="outline" onClick={() => csvRef.current?.click()} loading={importMut.isPending}>
              <ArrowUpTrayIcon className="h-4 w-4 mr-2" />CSV Import
            </Button>
            <Button className="w-full sm:w-auto" variant="primary" onClick={() => setShowCreateForm(true)}>
              <UserPlusIcon className="h-4 w-4 mr-2" />Add Student
            </Button>
          </div>
        )}
        {activeTab === 'invitations' && (
          <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:items-center">
            <input
              ref={inviteCsvRef}
              name="students_csv_invite"
              type="file"
              accept=".csv"
              className="hidden"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) bulkInviteMut.mutate(f); }}
            />
            <Button className="w-full sm:w-auto" variant="outline" onClick={() => inviteCsvRef.current?.click()} loading={bulkInviteMut.isPending}>
              <ArrowUpTrayIcon className="h-4 w-4 mr-2" />Bulk Invite CSV
            </Button>
            <Button className="w-full sm:w-auto" variant="primary" onClick={() => setShowInviteForm(true)}>
              <EnvelopeIcon className="h-4 w-4 mr-2" />Invite Student
            </Button>
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200">
        <nav className="flex gap-6">
          {[
            { key: 'students', label: 'Students' },
            { key: 'invitations', label: 'Invitations' },
          ].map((tab) => (
            <button
              key={tab.key}
              onClick={() => setTab(tab.key)}
              className={`py-2.5 text-sm font-medium border-b-2 transition ${
                activeTab === tab.key
                  ? 'border-indigo-600 text-indigo-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {/* ═══════════════════════ Invitations Tab ═══════════════════════ */}
      {activeTab === 'invitations' && (
        <>
          <div className="overflow-x-auto bg-white rounded-xl border border-gray-200 shadow-sm">
            <table className="min-w-full divide-y divide-gray-200 text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Email</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Name</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Invited By</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Expires</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {!invitations || invitations.length === 0 ? (
                  <tr><td colSpan={5} className="px-4 py-8 text-center text-gray-500">No invitations sent yet.</td></tr>
                ) : (
                  invitations.map((inv) => (
                    <tr key={inv.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3 text-gray-900">{inv.email}</td>
                      <td className="px-4 py-3 text-gray-600">{inv.first_name} {inv.last_name}</td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${INVITE_STATUS_COLORS[inv.status] || 'bg-gray-100'}`}>
                          {inv.status === 'pending' && <ClockIcon className="h-3 w-3" />}
                          {inv.status === 'accepted' && <CheckCircleIcon className="h-3 w-3" />}
                          {inv.status.charAt(0).toUpperCase() + inv.status.slice(1)}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-gray-600">{inv.invited_by || '—'}</td>
                      <td className="px-4 py-3 text-gray-600">
                        {inv.expires_at ? new Date(inv.expires_at).toLocaleDateString() : '—'}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Single Invite Modal */}
          {showInviteForm && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
              <div className="bg-white rounded-xl shadow-xl w-full max-w-md mx-4 p-6">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-lg font-semibold">Invite Student</h2>
                  <button onClick={() => setShowInviteForm(false)} className="text-gray-400 hover:text-gray-600"><XMarkIcon className="h-5 w-5" /></button>
                </div>
                <form
                  onSubmit={inviteForm.handleSubmit((data) => inviteMut.mutate(data))}
                  noValidate
                  className="space-y-3"
                >
                  <FormField control={inviteForm.control} name="email" label="Email *" type="email" placeholder="student@school.com" />
                  <div className="grid grid-cols-2 gap-3">
                    <FormField control={inviteForm.control} name="first_name" label="First Name *" />
                    <FormField control={inviteForm.control} name="last_name" label="Last Name" />
                  </div>
                  <p className="text-xs text-gray-500">An email will be sent with a link to set their password and join the platform. The invitation expires in 7 days.</p>
                  <div className="flex justify-end gap-3 mt-5">
                    <Button variant="outline" type="button" onClick={() => setShowInviteForm(false)}>Cancel</Button>
                    <Button variant="primary" type="submit" loading={inviteMut.isPending}>Send Invitation</Button>
                  </div>
                </form>
              </div>
            </div>
          )}
        </>
      )}

      {/* ═══════════════════════ Students Tab ═══════════════════════ */}
      {activeTab === 'students' && (
        <>
          {/* Search + Filters */}
          <div className="card space-y-3">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
              <div className="flex-1">
                <Input
                  id="students-search"
                  name="students_search"
                  autoComplete="off"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search by name, email, or student ID"
                  leftIcon={<MagnifyingGlassIcon className="h-5 w-5" />}
                />
              </div>
              <Button
                variant="outline"
                onClick={() => setShowFilters(!showFilters)}
                className="sm:w-auto"
              >
                <FunnelIcon className="h-4 w-4 mr-2" />
                Filters
                {(gradeFilter || sectionFilter) && (
                  <span className="ml-1.5 inline-flex items-center justify-center h-5 w-5 rounded-full bg-indigo-100 text-indigo-700 text-xs font-medium">
                    {[gradeFilter, sectionFilter].filter(Boolean).length}
                  </span>
                )}
              </Button>
            </div>

            {showFilters && (
              <div className="flex flex-col gap-3 sm:flex-row sm:items-end pt-2 border-t border-gray-100">
                <div className="flex-1">
                  <label htmlFor="grade-filter" className="block text-xs font-medium text-gray-500 mb-1">Grade Level</label>
                  <select
                    id="grade-filter"
                    value={gradeFilter}
                    onChange={(e) => setGradeFilter(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
                  >
                    <option value="">All Grades</option>
                    {gradeOptions.map((g) => <option key={g} value={g}>{g}</option>)}
                  </select>
                </div>
                <div className="flex-1">
                  <label htmlFor="section-filter" className="block text-xs font-medium text-gray-500 mb-1">Section</label>
                  <select
                    id="section-filter"
                    value={sectionFilter}
                    onChange={(e) => setSectionFilter(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
                  >
                    <option value="">All Sections</option>
                    {sectionOptions.map((s) => <option key={s} value={s}>{s}</option>)}
                  </select>
                </div>
                {(gradeFilter || sectionFilter) && (
                  <Button variant="ghost" onClick={clearFilters} className="text-gray-500">
                    <ArrowPathIcon className="h-4 w-4 mr-1" />Clear
                  </Button>
                )}
              </div>
            )}
          </div>

          {/* Result count */}
          {!isLoading && (
            <p className="text-xs text-gray-500">{totalCount} student{totalCount !== 1 ? 's' : ''} found</p>
          )}

          {/* Desktop Table */}
          <div className="hidden md:block card overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="text-left text-gray-500">
                <tr>
                  <th className="py-3 pr-3 w-10">
                    <input
                      id="students-select-all"
                      name="students_select_all"
                      aria-label="Select all students"
                      type="checkbox"
                      checked={rows.length > 0 && selectedIds.size === rows.length}
                      onChange={toggleSelectAll}
                      className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                    />
                  </th>
                  <th className="py-3 pr-6">Name</th>
                  <th className="py-3 pr-6">Email</th>
                  <th className="py-3 pr-6">Student ID</th>
                  <th className="py-3 pr-6">Grade</th>
                  <th className="py-3 pr-6">Section</th>
                  <th className="py-3 pr-6">Active</th>
                  <th className="py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {isLoading ? (
                  <tr><td className="py-6 text-gray-500" colSpan={8}>Loading...</td></tr>
                ) : rows.length === 0 ? (
                  <tr><td className="py-6 text-gray-500" colSpan={8}>No students found.</td></tr>
                ) : (
                  rows.map((s) => (
                    <tr key={s.id} className={`text-gray-800 hover:bg-gray-50 ${selectedIds.has(s.id) ? 'bg-indigo-50' : ''}`}>
                      <td className="py-3 pr-3">
                        <input
                          id={`student-row-select-${s.id}`}
                          name={`student_row_select_${s.id}`}
                          aria-label={`Select ${s.first_name} ${s.last_name}`}
                          type="checkbox"
                          checked={selectedIds.has(s.id)}
                          onChange={() => toggleSelection(s.id)}
                          className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                        />
                      </td>
                      <td className="py-3 pr-6 font-medium">{s.first_name} {s.last_name}</td>
                      <td className="py-3 pr-6">{s.email}</td>
                      <td className="py-3 pr-6">{s.student_id || '—'}</td>
                      <td className="py-3 pr-6">
                        {s.grade_level ? (
                          <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-blue-50 text-blue-700">{s.grade_level}</span>
                        ) : '—'}
                      </td>
                      <td className="py-3 pr-6">
                        {s.section ? (
                          <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-gray-100">{s.section}</span>
                        ) : '—'}
                      </td>
                      <td className="py-3 pr-6">
                        {s.is_active
                          ? <span className="inline-flex items-center gap-1 text-xs text-emerald-700"><CheckCircleIcon className="h-3.5 w-3.5" />Yes</span>
                          : <span className="inline-flex items-center gap-1 text-xs text-red-600"><XCircleIcon className="h-3.5 w-3.5" />No</span>}
                      </td>
                      <td className="py-3 text-right">
                        <div className="flex items-center justify-end gap-2">
                          <button onClick={() => openEdit(s)} className="p-1 text-gray-400 hover:text-indigo-600 rounded">
                            <PencilIcon className="h-4 w-4" />
                          </button>
                          {s.is_active && (
                            <button onClick={() => setDeleteTarget(s)} className="p-1 text-gray-400 hover:text-red-600 rounded">
                              <XCircleIcon className="h-4 w-4" />
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Mobile Cards */}
          <div className="md:hidden space-y-3">
            {isLoading ? (
              <div className="card text-sm text-gray-500">Loading...</div>
            ) : rows.length === 0 ? (
              <div className="card text-sm text-gray-500">No students found.</div>
            ) : (
              rows.map((s) => (
                <div key={s.id} className={`card ${selectedIds.has(s.id) ? 'ring-2 ring-indigo-200' : ''}`}>
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="font-semibold text-gray-900">{s.first_name} {s.last_name}</p>
                      <p className="text-xs text-gray-500 break-all">{s.email}</p>
                    </div>
                    <input
                      id={`student-select-${s.id}`}
                      name={`student_select_${s.id}`}
                      type="checkbox"
                      checked={selectedIds.has(s.id)}
                      onChange={() => toggleSelection(s.id)}
                      className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500 mt-1"
                    />
                  </div>
                  <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-gray-600">
                    <p>Student ID: <span className="text-gray-900">{s.student_id || '—'}</span></p>
                    <p>Grade: <span className="text-gray-900">{s.grade_level || '—'}</span></p>
                    <p>Section: <span className="text-gray-900">{s.section || '—'}</span></p>
                    <p>
                      Status:{' '}
                      {s.is_active ? (
                        <span className="inline-flex items-center gap-1 text-emerald-700"><CheckCircleIcon className="h-3.5 w-3.5" />Active</span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-red-600"><XCircleIcon className="h-3.5 w-3.5" />Inactive</span>
                      )}
                    </p>
                  </div>
                  <div className="mt-3 flex items-center gap-2">
                    <Button className="flex-1" variant="outline" onClick={() => openEdit(s)}>
                      <PencilIcon className="h-4 w-4 mr-2" />Edit
                    </Button>
                    {s.is_active && (
                      <Button className="flex-1" variant="outline" onClick={() => setDeleteTarget(s)}>
                        <XCircleIcon className="h-4 w-4 mr-2" />Remove
                      </Button>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>

          {/* Bulk Actions Bar */}
          <BulkActionsBar
            selectedCount={selectedIds.size}
            actions={bulkActions}
            onAction={handleBulkAction}
            onClearSelection={clearSelection}
            isLoading={bulkActionMut.isPending}
          />
        </>
      )}

      {/* ═══════════════════════ Create Student Modal ═══════════════════════ */}
      {showCreateForm && (
        <div className="fixed inset-0 bg-black/50 flex items-end sm:items-center justify-center z-50">
          <form
            onSubmit={createForm.handleSubmit((data) => createMut.mutate(data))}
            noValidate
            className="bg-white rounded-t-2xl sm:rounded-xl p-6 max-w-lg w-full mx-0 sm:mx-4 space-y-4 max-h-[90vh] overflow-y-auto"
          >
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-bold text-gray-900">Add Student</h3>
              <button type="button" onClick={() => setShowCreateForm(false)} className="text-gray-400 hover:text-gray-600">
                <XMarkIcon className="h-6 w-6" />
              </button>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <FormField control={createForm.control} name="first_name" label="First Name *" autoComplete="given-name" />
              <FormField control={createForm.control} name="last_name" label="Last Name *" autoComplete="family-name" />
            </div>
            <FormField control={createForm.control} name="email" label="Email *" type="email" placeholder="student@school.com" />
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <FormField control={createForm.control} name="password" label="Password *" type="password" autoComplete="new-password" helperText="Min 8 characters" />
              <FormField control={createForm.control} name="password_confirm" label="Confirm Password *" type="password" autoComplete="new-password" />
            </div>

            <div className="border-t border-gray-100 pt-4">
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-3">Academic Details</p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <FormField control={createForm.control} name="student_id" label="Student ID" placeholder="e.g. KIS-2024-001" />
                <FormField control={createForm.control} name="grade_level" label="Grade Level" placeholder="e.g. Grade 5" />
                <FormField control={createForm.control} name="section" label="Section" placeholder="e.g. A" />
                <FormField control={createForm.control} name="parent_email" label="Parent Email" type="email" placeholder="parent@email.com" />
              </div>
              <div className="mt-4">
                <FormField control={createForm.control} name="enrollment_date" label="Enrollment Date" type="date" />
              </div>
            </div>

            {createForm.formState.errors.root?.message && (
              <p className="text-sm text-red-600">{createForm.formState.errors.root.message}</p>
            )}

            <div className="flex justify-end gap-3 pt-2">
              <Button variant="outline" type="button" onClick={() => setShowCreateForm(false)}>Cancel</Button>
              <Button variant="primary" type="submit" loading={createMut.isPending}>Create Student</Button>
            </div>
          </form>
        </div>
      )}

      {/* ═══════════════════════ Edit Student Modal ═══════════════════════ */}
      {editingStudent && (
        <div className="fixed inset-0 bg-black/50 flex items-end sm:items-center justify-center z-50">
          <form
            onSubmit={editForm.handleSubmit((data) => updateMut.mutate({ id: editingStudent.id, data }))}
            noValidate
            className="bg-white rounded-t-2xl sm:rounded-xl p-6 max-w-lg w-full mx-0 sm:mx-4 space-y-4 max-h-[90vh] overflow-y-auto"
          >
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-bold text-gray-900">Edit Student</h3>
              <button type="button" onClick={() => setEditingStudent(null)} className="text-gray-400 hover:text-gray-600">
                <XMarkIcon className="h-6 w-6" />
              </button>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <FormField control={editForm.control} name="first_name" label="First Name" autoComplete="given-name" />
              <FormField control={editForm.control} name="last_name" label="Last Name" autoComplete="family-name" />
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <FormField control={editForm.control} name="student_id" label="Student ID" />
              <FormField control={editForm.control} name="grade_level" label="Grade Level" />
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <FormField control={editForm.control} name="section" label="Section" />
              <FormField control={editForm.control} name="parent_email" label="Parent Email" type="email" />
            </div>
            <FormField control={editForm.control} name="enrollment_date" label="Enrollment Date" type="date" />

            <Controller
              control={editForm.control}
              name="is_active"
              render={({ field }) => (
                <label htmlFor="edit-student-active" className="flex items-center gap-2 text-sm">
                  <input
                    id="edit-student-active"
                    type="checkbox"
                    checked={field.value}
                    onChange={(e) => field.onChange(e.target.checked)}
                    className="rounded border-gray-300 text-indigo-600"
                  />
                  Active
                </label>
              )}
            />

            <div className="flex justify-end gap-3 pt-2">
              <Button variant="outline" type="button" onClick={() => setEditingStudent(null)}>Cancel</Button>
              <Button variant="primary" type="submit" loading={updateMut.isPending}>Save</Button>
            </div>
          </form>
        </div>
      )}

      {/* Deactivate confirmation dialog */}
      <ConfirmDialog
        isOpen={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => { if (deleteTarget) deleteMut.mutate(deleteTarget.id); }}
        title="Remove Student"
        message={`Are you sure you want to remove ${deleteTarget?.first_name} ${deleteTarget?.last_name}? They will no longer be able to access the platform.`}
        confirmLabel="Remove"
        variant="warning"
      />
    </div>
  );
};
