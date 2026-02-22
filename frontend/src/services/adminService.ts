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

export type AdminAssignmentScopeType = 'COURSE' | 'MODULE';
export type AdminAssignmentType = 'QUIZ' | 'WRITTEN';
export type AdminQuizQuestionType = 'MCQ' | 'SHORT_ANSWER' | 'TRUE_FALSE';
export type AdminQuizSelectionMode = 'SINGLE' | 'MULTIPLE';

export interface AdminQuizQuestion {
  id?: string;
  order: number;
  question_type: AdminQuizQuestionType;
  selection_mode: AdminQuizSelectionMode;
  prompt: string;
  options: string[];
  correct_answer: Record<string, any>;
  explanation: string;
  points: number;
}

export interface AdminAssignment {
  id: string;
  title: string;
  description: string;
  instructions: string;
  due_date: string | null;
  max_score: string;
  passing_score: string;
  is_mandatory: boolean;
  is_active: boolean;
  scope_type: AdminAssignmentScopeType;
  module_id: string | null;
  module_title: string | null;
  assignment_type: AdminAssignmentType;
  generation_source: 'MANUAL' | 'VIDEO_AUTO';
  generation_metadata: Record<string, any>;
  questions: AdminQuizQuestion[];
  created_at: string;
  updated_at: string;
}

export interface AdminAssignmentPayload {
  title: string;
  description: string;
  instructions: string;
  due_date?: string | null;
  max_score: number | string;
  passing_score: number | string;
  is_mandatory: boolean;
  is_active: boolean;
  scope_type: AdminAssignmentScopeType;
  module_id?: string | null;
  assignment_type: AdminAssignmentType;
  questions?: AdminQuizQuestion[];
}

export interface AiGenerateRequest {
  scope_type: AdminAssignmentScopeType;
  module_id?: string | null;
  question_count?: number;
  include_short_answer?: boolean;
  title_hint?: string;
}

export interface AiGenerateResponse extends AdminAssignment {}

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

  async listCourseAssignments(courseId: string, params?: { scope?: 'ALL' | 'COURSE' | 'MODULE'; module_id?: string }) {
    const res = await api.get(`/courses/${courseId}/assignments/`, { params });
    return res.data as AdminAssignment[];
  },

  async getCourseAssignment(courseId: string, assignmentId: string) {
    const res = await api.get(`/courses/${courseId}/assignments/${assignmentId}/`);
    return res.data as AdminAssignment;
  },

  async createCourseAssignment(courseId: string, payload: AdminAssignmentPayload) {
    const res = await api.post(`/courses/${courseId}/assignments/`, payload);
    return res.data as AdminAssignment;
  },

  async updateCourseAssignment(courseId: string, assignmentId: string, payload: Partial<AdminAssignmentPayload>) {
    const res = await api.patch(`/courses/${courseId}/assignments/${assignmentId}/`, payload);
    return res.data as AdminAssignment;
  },

  async deleteCourseAssignment(courseId: string, assignmentId: string) {
    await api.delete(`/courses/${courseId}/assignments/${assignmentId}/`);
  },

  async aiGenerateCourseAssignment(courseId: string, payload: AiGenerateRequest) {
    const res = await api.post(`/courses/${courseId}/assignments/ai-generate/`, payload);
    return res.data as AiGenerateResponse;
  },

  async listSkipRequests(params?: { status?: string; search?: string; page?: number }) {
    const res = await api.get('/teacher/skip-requests/', { params });
    return res.data as { count: number; next: string | null; previous: string | null; results: SkipRequestItem[] };
  },

  async reviewSkipRequest(id: string, data: { action: 'approve' | 'reject'; admin_notes?: string }) {
    const res = await api.post(`/teacher/skip-requests/${id}/review/`, data);
    return res.data;
  },
};
