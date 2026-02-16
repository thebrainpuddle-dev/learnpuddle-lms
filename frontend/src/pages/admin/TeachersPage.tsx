import React, { useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Button, Input, useToast } from '../../components/common';
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
} from '@heroicons/react/24/outline';
import type { User } from '../../types';

export const TeachersPage: React.FC = () => {
  const navigate = useNavigate();
  const toast = useToast();
  const qc = useQueryClient();
  const csvRef = useRef<HTMLInputElement>(null);
  const { usage } = useTenantStore();
  const [search, setSearch] = useState('');
  const [editingTeacher, setEditingTeacher] = useState<User | null>(null);
  const [editForm, setEditForm] = useState<Partial<User>>({});
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

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

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Teachers</h1>
          <p className="mt-1 text-sm text-gray-500">
            Create and manage teacher accounts.
            {usage && <span className="ml-2 text-gray-400">({usage.teachers.used}/{usage.teachers.limit} used)</span>}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <input ref={csvRef} type="file" accept=".csv" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) importMut.mutate(f); }} />
          <Button variant="outline" onClick={() => csvRef.current?.click()} loading={importMut.isPending}>
            <ArrowUpTrayIcon className="h-4 w-4 mr-2" />CSV Import
          </Button>
          <Button variant="primary" onClick={() => navigate('/admin/teachers/new')}>
            <UserPlusIcon className="h-4 w-4 mr-2" />Create Teacher
          </Button>
        </div>
      </div>

      <div className="card">
        <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search by name or email" leftIcon={<MagnifyingGlassIcon className="h-5 w-5" />} />
      </div>

      <div className="card overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead className="text-left text-gray-500">
            <tr>
              <th className="py-3 pr-3 w-10">
                <input
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
                          onClick={() => { if (window.confirm(`Deactivate ${t.first_name} ${t.last_name}?`)) deactivateMut.mutate(t.id); }}
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

      {/* Bulk Actions Bar */}
      <BulkActionsBar
        selectedCount={selectedIds.size}
        actions={bulkActions}
        onAction={handleBulkAction}
        onClearSelection={clearSelection}
        isLoading={bulkActionMut.isPending}
      />

      {/* Edit modal */}
      {editingTeacher && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl p-6 max-w-lg w-full mx-4 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-bold text-gray-900">Edit Teacher</h3>
              <button onClick={() => setEditingTeacher(null)} className="text-gray-400 hover:text-gray-600"><XMarkIcon className="h-6 w-6" /></button>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <Input label="First Name" value={editForm.first_name || ''} onChange={(e) => setEditForm({ ...editForm, first_name: e.target.value })} />
              <Input label="Last Name" value={editForm.last_name || ''} onChange={(e) => setEditForm({ ...editForm, last_name: e.target.value })} />
            </div>
            <Input label="Department" value={editForm.department || ''} onChange={(e) => setEditForm({ ...editForm, department: e.target.value })} />
            <Input label="Employee ID" value={editForm.employee_id || ''} onChange={(e) => setEditForm({ ...editForm, employee_id: e.target.value })} />
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Role</label>
              <select value={editForm.role || 'TEACHER'} onChange={(e) => setEditForm({ ...editForm, role: e.target.value as any })} className="w-full px-3 py-2 border border-gray-300 rounded-lg">
                <option value="TEACHER">Teacher</option>
                <option value="HOD">HOD</option>
                <option value="IB_COORDINATOR">IB Coordinator</option>
              </select>
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={editForm.is_active ?? true} onChange={(e) => setEditForm({ ...editForm, is_active: e.target.checked })} className="rounded border-gray-300 text-indigo-600" />
              Active
            </label>
            <div className="flex justify-end gap-3 pt-2">
              <Button variant="outline" onClick={() => setEditingTeacher(null)}>Cancel</Button>
              <Button variant="primary" onClick={() => updateMut.mutate({ id: editingTeacher.id, data: editForm })} loading={updateMut.isPending}>Save</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
