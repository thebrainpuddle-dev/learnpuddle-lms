import api from '../config/api';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface Student {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  student_id: string;
  grade_level: string;
  section: string;
  parent_email: string;
  enrollment_date: string;
  is_active: boolean;
  last_login: string | null;
  created_at: string;
}

export interface StudentListResponse {
  results: Student[];
  count: number;
  next: string | null;
  previous: string | null;
}

export interface CreateStudentData {
  email: string;
  first_name: string;
  last_name: string;
  password: string;
  password_confirm: string;
  student_id?: string;
  grade_level?: string;
  section?: string;
  parent_email?: string;
  enrollment_date?: string;
}

export interface UpdateStudentData {
  first_name?: string;
  last_name?: string;
  student_id?: string;
  grade_level?: string;
  section?: string;
  parent_email?: string;
  enrollment_date?: string;
  is_active?: boolean;
}

export interface StudentInvitation {
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

export interface BulkImportResult {
  created: number;
  total_rows: number;
  results: Array<{ row: number; email: string; status: string; message?: string }>;
}

export interface BulkActionResult {
  message: string;
  affected_count: number;
  requested_count: number;
}

// ---------------------------------------------------------------------------
// Service
// ---------------------------------------------------------------------------

export const adminStudentsService = {
  async listStudents(params?: {
    search?: string;
    grade_level?: string;
    section?: string;
    is_active?: boolean;
    page?: number;
    page_size?: number;
  }): Promise<StudentListResponse> {
    const res = await api.get('/students/', { params });
    // Backend returns paginated response { results: [...], count, next, previous }
    return res.data;
  },

  async getStudent(studentId: string): Promise<Student> {
    const res = await api.get(`/students/${studentId}/`);
    return res.data;
  },

  async createStudent(payload: CreateStudentData): Promise<Student> {
    const res = await api.post('/students/register/', payload);
    return res.data;
  },

  async updateStudent(studentId: string, data: UpdateStudentData): Promise<Student> {
    const res = await api.patch(`/students/${studentId}/`, data);
    return res.data;
  },

  async deleteStudent(studentId: string): Promise<void> {
    await api.delete(`/students/${studentId}/`);
  },

  async listDeletedStudents(params?: {
    search?: string;
    page?: number;
    page_size?: number;
  }): Promise<StudentListResponse> {
    const res = await api.get('/students/deleted/', { params });
    return res.data;
  },

  async restoreStudent(studentId: string): Promise<void> {
    await api.post(`/students/${studentId}/restore/`);
  },

  async bulkImportCSV(file: File): Promise<BulkImportResult> {
    const fd = new FormData();
    fd.append('file', file);
    // Axios automatically sets Content-Type with boundary for FormData
    const res = await api.post('/students/bulk-import/', fd);
    return res.data;
  },

  async bulkAction(action: 'activate' | 'deactivate' | 'delete', studentIds: string[]): Promise<BulkActionResult> {
    const res = await api.post('/students/bulk-action/', { action, student_ids: studentIds });
    return res.data;
  },

  async listInvitations(params?: { status?: string }): Promise<StudentInvitation[]> {
    const res = await api.get('/students/invitations/', { params });
    return res.data;
  },

  async createInvitation(data: { email: string; first_name: string; last_name?: string }): Promise<StudentInvitation> {
    const res = await api.post('/students/invitations/', data);
    return res.data;
  },

  async bulkInviteCSV(file: File): Promise<BulkImportResult> {
    const fd = new FormData();
    fd.append('file', file);
    const res = await api.post('/students/bulk-invite/', fd);
    return res.data;
  },
};
