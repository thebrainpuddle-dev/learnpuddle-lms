import api from '../config/api';

export interface RecentActivityItem {
  teacher_name: string;
  course_title: string;
  content_title: string | null;
  completed_at: string;
}

export interface TenantStats {
  total_teachers: number;
  total_admins: number;
  total_courses: number;
  published_courses: number;
  recent_activity: RecentActivityItem[];
}

export const adminService = {
  async getTenantStats(): Promise<TenantStats> {
    const res = await api.get('/tenants/stats/');
    return res.data;
  },
};

