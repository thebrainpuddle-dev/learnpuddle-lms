import api from '../config/api';

import type { User } from '../types';

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
};
