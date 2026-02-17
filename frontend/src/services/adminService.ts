import api from '../config/api';

export interface RecentActivityItem {
  teacher_name: string;
  course_title: string;
  content_title: string | null;
  completed_at: string;
}

export interface TopTeacher {
  name: string;
  completed_courses: number;
}

export interface InactiveTeacherDetail {
  id: string;
  name: string;
  email: string;
}

export interface PendingReviewDetail {
  submission_id: string;
  teacher_id: string;
  teacher_name: string;
  teacher_email: string;
  assignment_id: string;
  assignment_title: string;
  course_id: string;
  course_title: string;
  submitted_at: string | null;
  is_quiz: boolean;
}

export interface TenantStats {
  total_teachers: number;
  active_teachers: number;
  inactive_teachers: number;
  total_admins: number;
  total_courses: number;
  published_courses: number;
  total_content_items: number;
  avg_completion_pct: number;
  course_completions: number;
  courses_in_progress: number;
  content_completions: number;
  total_assignments: number;
  total_submissions: number;
  graded_submissions: number;
  pending_review: number;
  inactive_teachers_detail?: InactiveTeacherDetail[];
  pending_review_detail?: PendingReviewDetail[];
  top_teachers: TopTeacher[];
  recent_activity: RecentActivityItem[];
}

export interface CourseBreakdown {
  course_id: string;
  title: string;
  assigned: number;
  completed: number;
  in_progress: number;
  not_started: number;
}

export interface TenantAnalytics {
  course_breakdown: CourseBreakdown[];
  monthly_trend: Array<{ month: string; completions: number }>;
  assignment_breakdown: { total: number; manual: number; auto_quiz: number; auto_reflection: number };
  teacher_engagement: { highly_active: number; active: number; low_activity: number; inactive: number };
  department_stats: Array<{ department: string; count: number }>;
}

export interface VideoStatusResponse {
  content: any;
  video_asset: {
    id: string;
    status: 'UPLOADED' | 'PROCESSING' | 'READY' | 'FAILED';
    error_message: string;
    duration_seconds: number | null;
    hls_master_url: string;
    thumbnail_url: string;
    source_url: string;
  } | null;
  transcript: { language: string; full_text_preview: string; vtt_url: string; generated_at: string | null } | null;
  assignments: Array<{ id: string; title: string }>;
}

// Skip-request types (course skip by teacher, reviewed by admin)
export interface SkipRequestItem {
  id: string;
  teacher_name: string;
  teacher_email: string;
  course_title: string;
  status: 'PENDING' | 'APPROVED' | 'REJECTED';
  certificate_url: string | null;
  comments: string;
  created_at: string;
  reviewed_by_name: string | null;
}

export const adminService = {
  async getTenantStats(): Promise<TenantStats> {
    const res = await api.get('/tenants/stats/');
    return res.data;
  },

  async getTenantAnalytics(params?: { course_id?: string; months?: number }): Promise<TenantAnalytics> {
    const res = await api.get('/tenants/analytics/', { params });
    return res.data;
  },

  async getVideoStatus(courseId: string, moduleId: string, contentId: string): Promise<VideoStatusResponse> {
    const res = await api.get(`/courses/${courseId}/modules/${moduleId}/contents/${contentId}/video-status/`);
    return res.data;
  },

  async listSkipRequests(params?: { status?: string; search?: string; page?: number }) {
    const res = await api.get('/teacher/skip-requests/', { params });
    return res.data as { count: number; results: SkipRequestItem[] };
  },

  async reviewSkipRequest(id: string, data: { action: 'approve' | 'reject'; admin_notes?: string }) {
    const res = await api.post(`/teacher/skip-requests/${id}/review/`, data);
    return res.data;
  },
};
