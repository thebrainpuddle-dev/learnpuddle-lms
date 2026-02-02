import React, { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Button } from '../../components/common/Button';
import { Input } from '../../components/common/Input';
import { useToast } from '../../components/common';
import { adminGroupsService, TeacherGroup } from '../../services/adminGroupsService';
import { adminTeachersService } from '../../services/adminTeachersService';
import {
  PlusIcon,
  TrashIcon,
  UserPlusIcon,
  UsersIcon,
  MagnifyingGlassIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';

// Debounce hook
function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);
  useEffect(() => {
    const handler = setTimeout(() => setDebouncedValue(value), delay);
    return () => clearTimeout(handler);
  }, [value, delay]);
  return debouncedValue;
}

export const GroupsPage: React.FC = () => {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [selectedGroupId, setSelectedGroupId] = useState<string | null>(null);
  const [groupSearch, setGroupSearch] = useState('');

  const [createOpen, setCreateOpen] = useState(false);
  const [createForm, setCreateForm] = useState({
    name: '',
    description: '',
    group_type: 'CUSTOM',
  });

  const [teacherSearch, setTeacherSearch] = useState('');
  const debouncedTeacherSearch = useDebounce(teacherSearch, 300);
  const [selectedTeacherIds, setSelectedTeacherIds] = useState<string[]>([]);

  const { data: groups, isLoading: groupsLoading } = useQuery({
    queryKey: ['adminGroups'],
    queryFn: adminGroupsService.listGroups,
  });

  const filteredGroups = useMemo(() => {
    const list = groups ?? [];
    const q = groupSearch.trim().toLowerCase();
    if (!q) return list;
    return list.filter((g) => g.name.toLowerCase().includes(q));
  }, [groups, groupSearch]);

  const selectedGroup: TeacherGroup | undefined = useMemo(() => {
    if (!selectedGroupId) return undefined;
    return (groups ?? []).find((g) => g.id === selectedGroupId);
  }, [groups, selectedGroupId]);

  const { data: members, isLoading: membersLoading } = useQuery({
    queryKey: ['adminGroupMembers', selectedGroupId],
    queryFn: () => adminGroupsService.listMembers(selectedGroupId!),
    enabled: !!selectedGroupId,
  });

  const { data: teachers } = useQuery({
    queryKey: ['adminTeachers', debouncedTeacherSearch],
    queryFn: () => adminTeachersService.listTeachers({ search: debouncedTeacherSearch || undefined }),
  });

  const createMutation = useMutation({
    mutationFn: () => adminGroupsService.createGroup(createForm),
    onSuccess: async (g) => {
      await queryClient.invalidateQueries({ queryKey: ['adminGroups'] });
      setCreateOpen(false);
      setCreateForm({ name: '', description: '', group_type: 'CUSTOM' });
      setSelectedGroupId(g.id);
      toast.success('Group created', `"${g.name}" has been created successfully.`);
    },
    onError: () => {
      toast.error('Failed to create group', 'Please check the details and try again.');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (groupId: string) => adminGroupsService.deleteGroup(groupId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['adminGroups'] });
      setSelectedGroupId(null);
      toast.success('Group deleted', 'The group has been removed.');
    },
    onError: () => {
      toast.error('Failed to delete group', 'Please try again.');
    },
  });

  const addMembersMutation = useMutation({
    mutationFn: (teacherIds: string[]) => adminGroupsService.addMembers(selectedGroupId!, teacherIds),
    onSuccess: async (members) => {
      await queryClient.invalidateQueries({ queryKey: ['adminGroupMembers', selectedGroupId] });
      setSelectedTeacherIds([]);
      toast.success('Members added', `${members.length} teacher(s) now in this group.`);
    },
    onError: () => {
      toast.error('Failed to add members', 'Please try again.');
    },
  });

  const removeMemberMutation = useMutation({
    mutationFn: (teacherId: string) => adminGroupsService.removeMember(selectedGroupId!, teacherId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['adminGroupMembers', selectedGroupId] });
      toast.success('Member removed', 'Teacher has been removed from the group.');
    },
    onError: () => {
      toast.error('Failed to remove member', 'Please try again.');
    },
  });

  const memberIds = useMemo(() => new Set((members ?? []).map((m) => m.id)), [members]);
  const availableTeachers = useMemo(() => {
    return (teachers ?? []).filter((t) => !memberIds.has(t.id));
  }, [teachers, memberIds]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Groups</h1>
          <p className="mt-1 text-sm text-gray-500">Create teacher groups and manage memberships.</p>
        </div>
        <Button variant="primary" onClick={() => setCreateOpen(true)}>
          <PlusIcon className="h-5 w-5 mr-2" />
          Create Group
        </Button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Groups list */}
        <div className="card lg:col-span-1">
          <div className="flex items-center mb-3">
            <Input
              value={groupSearch}
              onChange={(e) => setGroupSearch(e.target.value)}
              placeholder="Search groups…"
              leftIcon={<MagnifyingGlassIcon className="h-5 w-5" />}
            />
          </div>
          <div className="space-y-2">
            {groupsLoading ? (
              <div className="text-sm text-gray-500">Loading…</div>
            ) : filteredGroups.length === 0 ? (
              <div className="text-sm text-gray-500">No groups yet.</div>
            ) : (
              filteredGroups.map((g) => (
                <button
                  key={g.id}
                  onClick={() => setSelectedGroupId(g.id)}
                  className={`w-full text-left p-3 rounded-lg border transition-colors ${
                    selectedGroupId === g.id ? 'border-primary-500 bg-primary-50' : 'border-gray-200 hover:bg-gray-50'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="font-medium text-gray-900">{g.name}</div>
                      <div className="text-xs text-gray-500">{g.group_type}</div>
                    </div>
                    <UsersIcon className="h-5 w-5 text-gray-400" />
                  </div>
                </button>
              ))
            )}
          </div>
        </div>

        {/* Members */}
        <div className="card lg:col-span-2">
          {!selectedGroup ? (
            <div className="text-center py-12 text-gray-500">
              <UsersIcon className="h-12 w-12 mx-auto mb-3 text-gray-300" />
              Select a group to manage members.
            </div>
          ) : (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-semibold text-gray-900">{selectedGroup.name}</h2>
                  <p className="text-sm text-gray-500">{selectedGroup.description || 'No description'}</p>
                </div>
                <Button
                  variant="outline"
                  className="text-red-600 border-red-200 hover:bg-red-50"
                  onClick={() => {
                    if (window.confirm('Delete this group?')) {
                      deleteMutation.mutate(selectedGroup.id);
                    }
                  }}
                  loading={deleteMutation.isPending}
                >
                  <TrashIcon className="h-4 w-4 mr-2" />
                  Delete
                </Button>
              </div>

              {/* Add members */}
              <div className="bg-gray-50 rounded-lg p-4 border border-gray-100">
                <div className="flex items-center justify-between mb-3">
                  <div className="font-medium text-gray-900 flex items-center">
                    <UserPlusIcon className="h-5 w-5 mr-2 text-gray-500" />
                    Add teachers
                  </div>
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={() => addMembersMutation.mutate(selectedTeacherIds)}
                    disabled={selectedTeacherIds.length === 0}
                    loading={addMembersMutation.isPending}
                  >
                    Add selected ({selectedTeacherIds.length})
                  </Button>
                </div>

                <Input
                  value={teacherSearch}
                  onChange={(e) => setTeacherSearch(e.target.value)}
                  placeholder="Search teachers…"
                  leftIcon={<MagnifyingGlassIcon className="h-5 w-5" />}
                />

                <div className="mt-3 max-h-44 overflow-y-auto border border-gray-200 rounded-lg bg-white">
                  {availableTeachers.length === 0 ? (
                    <div className="p-3 text-sm text-gray-500">No teachers to add.</div>
                  ) : (
                    availableTeachers.slice(0, 50).map((t) => (
                      <label key={t.id} className="flex items-center gap-3 p-3 border-b last:border-b-0">
                        <input
                          type="checkbox"
                          checked={selectedTeacherIds.includes(t.id)}
                          onChange={(e) => {
                            setSelectedTeacherIds((prev) =>
                              e.target.checked ? [...prev, t.id] : prev.filter((id) => id !== t.id)
                            );
                          }}
                          className="h-4 w-4 rounded border-gray-300"
                        />
                        <div className="min-w-0">
                          <div className="text-sm font-medium text-gray-900 truncate">
                            {t.first_name} {t.last_name}
                          </div>
                          <div className="text-xs text-gray-500 truncate">{t.email}</div>
                        </div>
                      </label>
                    ))
                  )}
                </div>
              </div>

              {/* Members table */}
              <div className="border border-gray-200 rounded-lg overflow-hidden">
                <div className="px-4 py-3 bg-white border-b border-gray-200 font-medium text-gray-900">
                  Members ({members?.length || 0})
                </div>
                {membersLoading ? (
                  <div className="p-4 text-sm text-gray-500">Loading…</div>
                ) : (members?.length || 0) === 0 ? (
                  <div className="p-6 text-sm text-gray-500">No members in this group yet.</div>
                ) : (
                  <div className="divide-y divide-gray-100">
                    {members?.map((m) => (
                      <div key={m.id} className="flex items-center justify-between p-4 bg-white">
                        <div className="min-w-0">
                          <div className="text-sm font-medium text-gray-900 truncate">
                            {m.first_name} {m.last_name}
                          </div>
                          <div className="text-xs text-gray-500 truncate">{m.email}</div>
                        </div>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => removeMemberMutation.mutate(m.id)}
                          loading={removeMemberMutation.isPending}
                        >
                          Remove
                        </Button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Create group modal */}
      {createOpen && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl p-6 max-w-lg w-full mx-4">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-gray-900">Create Group</h3>
              <button onClick={() => setCreateOpen(false)} className="text-gray-400 hover:text-gray-600">
                <XMarkIcon className="h-6 w-6" />
              </button>
            </div>

            <div className="space-y-4">
              <Input
                label="Group name"
                value={createForm.name}
                onChange={(e) => setCreateForm({ ...createForm, name: e.target.value })}
                placeholder="e.g., Grade 9, Math Teachers"
              />
              <Input
                label="Description"
                value={createForm.description}
                onChange={(e) => setCreateForm({ ...createForm, description: e.target.value })}
                placeholder="Optional"
              />
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Type</label>
                <select
                  value={createForm.group_type}
                  onChange={(e) => setCreateForm({ ...createForm, group_type: e.target.value })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                >
                  <option value="CUSTOM">Custom</option>
                  <option value="SUBJECT">Subject</option>
                  <option value="GRADE">Grade</option>
                  <option value="DEPARTMENT">Department</option>
                </select>
              </div>
            </div>

            <div className="flex items-center justify-end gap-3 mt-6">
              <Button variant="outline" onClick={() => setCreateOpen(false)}>
                Cancel
              </Button>
              <Button
                variant="primary"
                onClick={() => createMutation.mutate()}
                disabled={!createForm.name.trim()}
                loading={createMutation.isPending}
              >
                Create
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

