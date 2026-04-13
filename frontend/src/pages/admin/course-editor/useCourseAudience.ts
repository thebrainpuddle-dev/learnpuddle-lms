// course-editor/useCourseAudience.ts
//
// Sub-hook: teacher assignment, group management, assign-to-all toggle,
// inline group creation.

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '../../../config/api';
import * as courseApi from './api';
import type { Teacher, TeacherGroup, CreateGroupForm } from './types';

export interface UseCourseAudienceParams {
  canManageAssignments: boolean;
}

export function useCourseAudience({
  canManageAssignments,
}: UseCourseAudienceParams) {
  const queryClient = useQueryClient();

  // ── Queries ─────────────────────────────────────────────────────────
  const { data: teachers } = useQuery({
    queryKey: ['adminTeachers'],
    queryFn: courseApi.fetchTeachers,
    enabled: canManageAssignments,
  });

  const { data: groups } = useQuery({
    queryKey: ['adminGroups'],
    queryFn: courseApi.fetchGroups,
    enabled: canManageAssignments,
  });

  // ── Inline group creation ───────────────────────────────────────────
  const [createGroupOpen, setCreateGroupOpen] = useState(false);
  const [createGroupForm, setCreateGroupForm] = useState<CreateGroupForm>({
    name: '',
    description: '',
    group_type: 'CUSTOM',
  });

  const createGroupMutation = useMutation({
    mutationFn: (payload: {
      name: string;
      description?: string;
      group_type?: string;
    }) => api.post('/teacher-groups/', payload).then((r) => r.data),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['adminGroups'] });
      setCreateGroupForm({ name: '', description: '', group_type: 'CUSTOM' });
      setCreateGroupOpen(false);
    },
  });

  return {
    teachers: teachers as Teacher[] | undefined,
    groups: groups as TeacherGroup[] | undefined,
    createGroupOpen,
    setCreateGroupOpen,
    createGroupForm,
    setCreateGroupForm,
    createGroupMutation,
  };
}
