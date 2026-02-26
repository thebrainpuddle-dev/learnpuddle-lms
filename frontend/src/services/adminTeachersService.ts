import api from '../config/api';

import type { User } from '../types';

export interface TeacherInvitation {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  status: 'pending' | 'accepted' | 'expired';
  created_at: string;
  expires_at: string;
  accepted_at: string | null;
  invited_by: string | null;
}

export const adminTeachersService = {
  async listTeachers(params?: { search?: string; role?: string; is_active?: boolean }): Promise<User[]> {
    const res = await api.get('/teachers/', { params });
    // Backend returns paginated response { results: [...], count, next, previous }
    return res.data.results ?? res.data;
  },

  async createTeacher(payload: {
    email: string;
    first_name: string;
    last_name: string;
    password: string;
    password_confirm: string;
    employee_id?: string;
    department?: string;
  }): Promise<User> {
    const res = await api.post('/users/auth/register-teacher/', payload);
    return res.data;
  },

  async updateTeacher(teacherId: string, data: Partial<User>): Promise<User> {
    const res = await api.patch(`/teachers/${teacherId}/`, data);
    return res.data;
  },

  async deactivateTeacher(teacherId: string): Promise<void> {
    await api.delete(`/teachers/${teacherId}/`);
  },

  async bulkImportCSV(file: File) {
    const fd = new FormData();
    fd.append('file', file);
    // Axios automatically sets Content-Type with boundary for FormData
    const res = await api.post('/teachers/bulk-import/', fd);
    return res.data as { created: number; total_rows: number; results: Array<{ row: number; email: string; status: string; message?: string }> };
  },

  async bulkAction(action: 'activate' | 'deactivate' | 'delete', teacherIds: string[]) {
    const res = await api.post('/teachers/bulk-action/', { action, teacher_ids: teacherIds });
    return res.data as { message: string; affected_count: number; requested_count: number };
  },

  async listInvitations(params?: { status?: string }): Promise<TeacherInvitation[]> {
    const res = await api.get('/teachers/invitations/', { params });
    return res.data;
  },

  async createInvitation(data: { email: string; first_name: string; last_name?: string }): Promise<TeacherInvitation> {
    const res = await api.post('/teachers/invitations/', data);
    return res.data;
  },

  async bulkInviteCSV(file: File) {
    const fd = new FormData();
    fd.append('file', file);
    const res = await api.post('/teachers/bulk-invite/', fd);
    return res.data as { created: number; total_rows: number; results: Array<{ row: number; email: string; status: string; message?: string }> };
  },

  async validateInvitation(token: string) {
    const res = await api.get(`/users/auth/invitation/${token}/`);
    return res.data as { email: string; first_name: string; last_name: string; school_name: string; expires_at: string };
  },

  async acceptInvitation(token: string, password: string) {
    const res = await api.post(`/users/auth/invitation/${token}/accept/`, { password });
    return res.data as { message: string; email: string };
  },
};
