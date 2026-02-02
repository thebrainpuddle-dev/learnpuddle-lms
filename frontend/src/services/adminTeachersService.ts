import api from '../config/api';

import type { User } from '../types';

export const adminTeachersService = {
  async listTeachers(params?: { search?: string; role?: string; is_active?: boolean }): Promise<User[]> {
    const res = await api.get('/teachers/', { params });
    return res.data;
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
};

