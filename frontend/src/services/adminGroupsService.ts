import api from '../config/api';

export interface TeacherGroup {
  id: string;
  name: string;
  description: string;
  group_type: string;
  created_at: string;
  updated_at: string;
}

export interface GroupMember {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  role: string;
  is_active: boolean;
}

export const adminGroupsService = {
  async listGroups(): Promise<TeacherGroup[]> {
    const res = await api.get('/teacher-groups/');
    return res.data.results ?? res.data;
  },

  async createGroup(payload: { name: string; description?: string; group_type?: string }): Promise<TeacherGroup> {
    const res = await api.post('/teacher-groups/', payload);
    return res.data;
  },

  async deleteGroup(groupId: string): Promise<void> {
    await api.delete(`/teacher-groups/${groupId}/`);
  },

  async listMembers(groupId: string): Promise<GroupMember[]> {
    const res = await api.get(`/teacher-groups/${groupId}/members/`);
    return res.data.results ?? res.data;
  },

  async addMembers(groupId: string, teacherIds: string[]): Promise<GroupMember[]> {
    const res = await api.post(`/teacher-groups/${groupId}/members/`, { teacher_ids: teacherIds });
    return res.data;
  },

  async removeMember(groupId: string, teacherId: string): Promise<void> {
    await api.delete(`/teacher-groups/${groupId}/members/${teacherId}/`);
  },
};

