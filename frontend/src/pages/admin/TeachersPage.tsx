import React, { useMemo, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Button, Input, useToast, ConfirmDialog } from '../../components/common';
import { BulkActionsBar, BulkAction } from '../../components/common/BulkActionsBar';
import { adminTeachersService } from '../../services/adminTeachersService';
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
} from '@heroicons/react/24/outline';
import type { User } from '../../types';
import { usePageTitle } from '../../hooks/usePageTitle';

const INVITE_STATUS_COLORS: Record<string, string> = {
  pending: 'bg-yellow-100 text-yellow-700',
  accepted: 'bg-green-100 text-green-700',
  expired: 'bg-gray-100 text-gray-500',
};

export const TeachersPage: React.FC = () => {
  usePageTitle('Teachers');
  const navigate = useNavigate();
  const toast = useToast();
  const qc = useQueryClient();
  const csvRef = useRef<HTMLInputElement>(null);
  const inviteCsvRef = useRef<HTMLInputElement>(null);
  const { usage } = useTenantStore();
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = searchParams.get('tab') || 'teachers';
  const [search, setSearch] = useState('');
  const [editingTeacher, setEditingTeacher] = useState<User | null>(null);
  const [editForm, setEditForm] = useState<Partial<User>>({});
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [deactivateTarget, setDeactivateTarget] = useState<User | null>(null);
  const [showInviteForm, setShowInviteForm] = useState(false);
  const [inviteForm, setInviteForm] = useState({ email: '', first_name: '', last_name: '' });

  const { data: teachers, isLoading } = useQuery({
    queryKey: ['adminTeachers', search],
    queryFn: () => adminTeachersService.listTeachers({ search }),
  });

  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<User> }) => adminTeachersService.updateTeacher(id, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['adminTeachers'] }); setEditingTeacher(null); toast.success('Teacher updated', ''); },
    onError: () => toast.error('Failed', 'Could not update teacher.'),
  });

  const deactivateMut = useMutation({
    mutationFn: (id: string) => adminTeachersService.deactivateTeacher(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['adminTeachers'] }); toast.success('Teacher deactivated', ''); },
  });

  const importMut = useMutation({
    mutationFn: (file: File) => adminTeachersService.bulkImportCSV(file),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['adminTeachers'] });
      toast.success('Import complete', `${data.created} of ${data.total_rows} teachers created.`);
    },
    onError: () => toast.error('Import failed', 'Check CSV format.'),
  });

  const bulkActionMut = useMutation({
    mutationFn: ({ action, teacherIds }: { action: 'activate' | 'deactivate' | 'delete'; teacherIds: string[] }) =>
      adminTeachersService.bulkAction(action, teacherIds),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['adminTeachers'] });
      toast.success('Bulk action complete', data.message);
      setSelectedIds(new Set());
    },
    onError: () => toast.error('Bulk action failed', 'Please try again.'),
  });

  const { data: invitations } = useQuery({
    queryKey: ['teacherInvitations'],
    queryFn: () => adminTeachersService.listInvitations(),
    enabled: activeTab === 'invitations',
  });

  const inviteMut = useMutation({
    mutationFn: (data: { email: string; first_name: string; last_name?: string }) => adminTeachersService.createInvitation(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['teacherInvitations'] });
      toast.success('Invitation Sent', 'An invitation email has been sent.');
      setShowInviteForm(false);
      setInviteForm({ email: '', first_name: '', last_name: '' });
    },
    onError: (err: any) => toast.error('Error', err?.response?.data?.error || 'Failed to send invitation'),
  });

  const bulkInviteMut = useMutation({
    mutationFn: (file: File) => adminTeachersService.bulkInviteCSV(file),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['teacherInvitations'] });
      toast.success('Bulk Invite Complete', `${data.created} of ${data.total_rows} invitations sent.`);
    },
    onError: () => toast.error('Bulk Invite Failed', 'Check CSV format.'),
  });

  const rows = useMemo(() => teachers ?? [], [teachers]);

  // Selection helpers
  const toggleSelection = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selectedIds.size === rows.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(rows.map((t) => t.id)));
    }
  };

  const clearSelection = () => setSelectedIds(new Set());

  const handleBulkAction = (actionId: string) => {
    const teacherIds = Array.from(selectedIds);
    bulkActionMut.mutate({ action: actionId as 'activate' | 'deactivate' | 'delete', teacherIds });
  };

  const bulkActions: BulkAction[] = [
    { id: 'activate', label: 'Activate', icon: PlayIcon, variant: 'success' },
    { id: 'deactivate', label: 'Deactivate', icon: StopIcon, variant: 'default' },
    { id: 'delete', label: 'Delete', icon: TrashIcon, variant: 'danger', requiresConfirmation: true },
  ];

  const openEdit = (t: User) => {
    setEditingTeacher(t);
    setEditForm({ first_name: t.first_name, last_name: t.last_name, department: t.department, employee_id: t.employee_id, role: t.role, is_active: t.is_active });
  };

  const setTab = (tab: string) => {
    setSearchParams({ tab });
    setSearch('');
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Teachers</h1>
          <p className="mt-1 text-sm text-gray-500">
            Create and manage teacher accounts.
            {usage && <span className="ml-2 text-gray-400">({usage.teachers.used}/{usage.teachers.limit} used)</span>}
          </p>
        </div>
        {activeTab === 'teachers' && (
          <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:items-center">
            <input ref={csvRef} name="teachers_csv_import" type="file" accept=".csv" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) importMut.mutate(f); }} />
            <Button className="w-full sm:w-auto" variant="outline" onClick={() => csvRef.current?.click()} loading={importMut.isPending}>
              <ArrowUpTrayIcon className="h-4 w-4 mr-2" />CSV Import
            </Button>
            <Button className="w-full sm:w-auto" variant="primary" onClick={() => navigate('/admin/teachers/new')}>
              <UserPlusIcon className="h-4 w-4 mr-2" />Create Teacher
            </Button>
          </div>
        )}
        {activeTab === 'invitations' && (
          <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:items-center">
            <input ref={inviteCsvRef} name="teachers_csv_invite" type="file" accept=".csv" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) bulkInviteMut.mutate(f); }} />
            <Button className="w-full sm:w-auto" variant="outline" onClick={() => inviteCsvRef.current?.click()} loading={bulkInviteMut.isPending}>
              <ArrowUpTrayIcon className="h-4 w-4 mr-2" />Bulk Invite CSV
            </Button>
            <Button className="w-full sm:w-auto" variant="primary" onClick={() => setShowInviteForm(true)}>
              <EnvelopeIcon className="h-4 w-4 mr-2" />Invite Teacher
            </Button>
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200">
        <nav className="flex gap-6">
          {[
            { key: 'teachers', label: 'Teachers' },
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

      {activeTab === 'invitations' && (
        <>
          {/* Invitations Table */}
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
                  <h2 className="text-lg font-semibold">Invite Teacher</h2>
                  <button onClick={() => setShowInviteForm(false)} className="text-gray-400 hover:text-gray-600"><XMarkIcon className="h-5 w-5" /></button>
                </div>
                <div className="space-y-3">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Email *</label>
                    <input type="email" value={inviteForm.email} onChange={(e) => setInviteForm(p => ({ ...p, email: e.target.value }))} className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500" placeholder="teacher@school.com" />
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">First Name *</label>
                      <input type="text" value={inviteForm.first_name} onChange={(e) => setInviteForm(p => ({ ...p, first_name: e.target.value }))} className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500" />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">Last Name</label>
                      <input type="text" value={inviteForm.last_name} onChange={(e) => setInviteForm(p => ({ ...p, last_name: e.target.value }))} className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500" />
                    </div>
                  </div>
                  <p className="text-xs text-gray-500">An email will be sent with a link to set their password and join the platform. The invitation expires in 7 days.</p>
                </div>
                <div className="flex justify-end gap-3 mt-5">
                  <Button variant="outline" onClick={() => setShowInviteForm(false)}>Cancel</Button>
                  <Button
                    variant="primary"
                    onClick={() => {
                      if (!inviteForm.email || !inviteForm.first_name) { toast.error('Missing Fields', 'Email and first name are required.'); return; }
                      inviteMut.mutate(inviteForm);
                    }}
                    loading={inviteMut.isPending}
                  >
                    Send Invitation
                  </Button>
                </div>
              </div>
            </div>
          )}
        </>
      )}

      {activeTab === 'teachers' && (
        <>
          <div data-tour="admin-teachers-search" className="card">
            <Input
              id="teachers-search"
              name="teachers_search"
              autoComplete="off"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by name or email"
              leftIcon={<MagnifyingGlassIcon className="h-5 w-5" />}
            />
          </div>

          <div data-tour="admin-teachers-table" className="hidden md:block card overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead className="text-left text-gray-500">
            <tr>
              <th className="py-3 pr-3 w-10">
                <input
                  id="teachers-select-all"
                  name="teachers_select_all"
                  aria-label="Select all teachers"
                  type="checkbox"
                  checked={rows.length > 0 && selectedIds.size === rows.length}
                  onChange={toggleSelectAll}
                  className="rounded border-gray-300 text-emerald-600 focus:ring-emerald-500"
                />
              </th>
              <th className="py-3 pr-6">Name</th>
              <th className="py-3 pr-6">Email</th>
              <th className="py-3 pr-6">Department</th>
              <th className="py-3 pr-6">Role</th>
              <th className="py-3 pr-6">Active</th>
              <th className="py-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {isLoading ? (
              <tr><td className="py-6 text-gray-500" colSpan={7}>Loading...</td></tr>
            ) : rows.length === 0 ? (
              <tr><td className="py-6 text-gray-500" colSpan={7}>No teachers found.</td></tr>
            ) : (
              rows.map((t) => (
                <tr key={t.id} className={`text-gray-800 hover:bg-gray-50 ${selectedIds.has(t.id) ? 'bg-emerald-50' : ''}`}>
                  <td className="py-3 pr-3">
                    <input
                      id={`teacher-row-select-${t.id}`}
                      name={`teacher_row_select_${t.id}`}
                      aria-label={`Select ${t.first_name} ${t.last_name}`}
                      type="checkbox"
                      checked={selectedIds.has(t.id)}
                      onChange={() => toggleSelection(t.id)}
                      className="rounded border-gray-300 text-emerald-600 focus:ring-emerald-500"
                    />
                  </td>
                  <td className="py-3 pr-6 font-medium">{t.first_name} {t.last_name}</td>
                  <td className="py-3 pr-6">{t.email}</td>
                  <td className="py-3 pr-6">{t.department || '-'}</td>
                  <td className="py-3 pr-6">
                    <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-gray-100">{t.role}</span>
                  </td>
                  <td className="py-3 pr-6">
                    {t.is_active
                      ? <span className="inline-flex items-center gap-1 text-xs text-emerald-700"><CheckCircleIcon className="h-3.5 w-3.5" />Yes</span>
                      : <span className="inline-flex items-center gap-1 text-xs text-red-600"><XCircleIcon className="h-3.5 w-3.5" />No</span>}
                  </td>
                  <td className="py-3 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <button onClick={() => openEdit(t)} className="p-1 text-gray-400 hover:text-indigo-600 rounded"><PencilIcon className="h-4 w-4" /></button>
                      {t.is_active && (
                        <button
                          onClick={() => setDeactivateTarget(t)}
                          className="p-1 text-gray-400 hover:text-red-600 rounded"
                        ><XCircleIcon className="h-4 w-4" /></button>
                      )}
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

          <div className="md:hidden space-y-3">
        {isLoading ? (
          <div className="card text-sm text-gray-500">Loading...</div>
        ) : rows.length === 0 ? (
          <div className="card text-sm text-gray-500">No teachers found.</div>
        ) : (
          rows.map((t) => (
            <div key={t.id} className={`card ${selectedIds.has(t.id) ? 'ring-2 ring-emerald-200' : ''}`}>
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-semibold text-gray-900">{t.first_name} {t.last_name}</p>
                  <p className="text-xs text-gray-500 break-all">{t.email}</p>
                </div>
                <input
                  id={`teacher-select-${t.id}`}
                  name={`teacher_select_${t.id}`}
                  type="checkbox"
                  checked={selectedIds.has(t.id)}
                  onChange={() => toggleSelection(t.id)}
                  className="rounded border-gray-300 text-emerald-600 focus:ring-emerald-500 mt-1"
                />
              </div>
              <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-gray-600">
                <p>Department: <span className="text-gray-900">{t.department || '-'}</span></p>
                <p>Role: <span className="text-gray-900">{t.role}</span></p>
                <p>
                  Status:{' '}
                  {t.is_active ? (
                    <span className="inline-flex items-center gap-1 text-emerald-700"><CheckCircleIcon className="h-3.5 w-3.5" />Active</span>
                  ) : (
                    <span className="inline-flex items-center gap-1 text-red-600"><XCircleIcon className="h-3.5 w-3.5" />Inactive</span>
                  )}
                </p>
              </div>
              <div className="mt-3 flex items-center gap-2">
                <Button className="flex-1" variant="outline" onClick={() => openEdit(t)}>
                  <PencilIcon className="h-4 w-4 mr-2" />Edit
                </Button>
                {t.is_active && (
                  <Button className="flex-1" variant="outline" onClick={() => setDeactivateTarget(t)}>
                    <XCircleIcon className="h-4 w-4 mr-2" />Deactivate
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

      {/* Edit modal */}
      {editingTeacher && (
        <div className="fixed inset-0 bg-black/50 flex items-end sm:items-center justify-center z-50">
          <div className="bg-white rounded-t-2xl sm:rounded-xl p-6 max-w-lg w-full mx-0 sm:mx-4 space-y-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-bold text-gray-900">Edit Teacher</h3>
              <button type="button" onClick={() => setEditingTeacher(null)} className="text-gray-400 hover:text-gray-600"><XMarkIcon className="h-6 w-6" /></button>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <Input id="edit-teacher-first-name" name="first_name" label="First Name" autoComplete="given-name" value={editForm.first_name || ''} onChange={(e) => setEditForm({ ...editForm, first_name: e.target.value })} />
              <Input id="edit-teacher-last-name" name="last_name" label="Last Name" autoComplete="family-name" value={editForm.last_name || ''} onChange={(e) => setEditForm({ ...editForm, last_name: e.target.value })} />
            </div>
            <Input id="edit-teacher-department" name="department" label="Department" autoComplete="organization-title" value={editForm.department || ''} onChange={(e) => setEditForm({ ...editForm, department: e.target.value })} />
            <Input id="edit-teacher-employee-id" name="employee_id" label="Employee ID" autoComplete="off" value={editForm.employee_id || ''} onChange={(e) => setEditForm({ ...editForm, employee_id: e.target.value })} />
            <div>
              <label htmlFor="edit-teacher-role" className="block text-sm font-medium text-gray-700 mb-1">Role</label>
              <select id="edit-teacher-role" name="role" value={editForm.role || 'TEACHER'} onChange={(e) => setEditForm({ ...editForm, role: e.target.value as any })} className="w-full px-3 py-2 border border-gray-300 rounded-lg">
                <option value="TEACHER">Teacher</option>
                <option value="HOD">HOD</option>
                <option value="IB_COORDINATOR">IB Coordinator</option>
              </select>
            </div>
            <label htmlFor="edit-teacher-active" className="flex items-center gap-2 text-sm">
              <input id="edit-teacher-active" name="is_active" type="checkbox" checked={editForm.is_active ?? true} onChange={(e) => setEditForm({ ...editForm, is_active: e.target.checked })} className="rounded border-gray-300 text-indigo-600" />
              Active
            </label>
            <div className="flex justify-end gap-3 pt-2">
              <Button variant="outline" onClick={() => setEditingTeacher(null)}>Cancel</Button>
              <Button variant="primary" onClick={() => updateMut.mutate({ id: editingTeacher.id, data: editForm })} loading={updateMut.isPending}>Save</Button>
            </div>
          </div>
        </div>
      )}

      {/* Deactivate confirmation dialog */}
      <ConfirmDialog
        isOpen={!!deactivateTarget}
        onClose={() => setDeactivateTarget(null)}
        onConfirm={() => {
          if (deactivateTarget) deactivateMut.mutate(deactivateTarget.id);
        }}
        title="Deactivate Teacher"
        message={`Are you sure you want to deactivate ${deactivateTarget?.first_name} ${deactivateTarget?.last_name}? They will no longer be able to access the platform.`}
        confirmLabel="Deactivate"
        variant="warning"
      />
    </div>
  );
};
