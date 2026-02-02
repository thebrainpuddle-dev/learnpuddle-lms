import api from '../config/api';

export interface TeacherDashboardResponse {
  stats: {
    overall_progress: number;
    total_courses: number;
    completed_courses: number;
    pending_assignments: number;
  };
  continue_learning: null | {
    course_id: string;
    course_title: string;
    content_id: string;
    content_title: string;
    progress_percentage: number;
  };
  deadlines: Array<{
    type: 'course' | 'assignment';
    id: string;
    title: string;
    days_left: number;
  }>;
}

export interface TeacherCourseListItem {
  id: string;
  title: string;
  slug: string;
  description: string;
  thumbnail: string | null;
  is_mandatory: boolean;
  deadline: string | null;
  estimated_hours: string;
  is_published: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  progress_percentage: number;
  completed_content_count: number;
  total_content_count: number;
}

export interface TeacherCourseDetail {
  id: string;
  title: string;
  slug: string;
  description: string;
  thumbnail: string | null;
  is_mandatory: boolean;
  deadline: string | null;
  estimated_hours: string;
  is_published: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  progress: {
    completed_content_count: number;
    total_content_count: number;
    percentage: number;
  };
  modules: Array<{
    id: string;
    title: string;
    description: string;
    order: number;
    is_active: boolean;
    contents: Array<{
      id: string;
      title: string;
      content_type: 'VIDEO' | 'DOCUMENT' | 'LINK' | 'TEXT';
      order: number;
      file_url?: string;
      file_size?: number | null;
      duration?: number | null;
      text_content?: string;
      is_mandatory: boolean;
      is_active: boolean;
      status: 'NOT_STARTED' | 'IN_PROGRESS' | 'COMPLETED';
      progress_percentage: number;
      video_progress_seconds: number;
      is_completed: boolean;
    }>;
  }>;
}

export interface TeacherAssignmentListItem {
  id: string;
  course_id: string;
  course_title: string;
  title: string;
  description: string;
  instructions: string;
  due_date: string | null;
  max_score: string;
  passing_score: string;
  is_mandatory: boolean;
  is_active: boolean;
  submission_status: 'PENDING' | 'SUBMITTED' | 'GRADED';
  score: number | null;
  feedback: string;
}

export interface TeacherAssignmentSubmission {
  id: string;
  assignment_id: string;
  submission_text: string;
  file_url: string;
  status: 'PENDING' | 'SUBMITTED' | 'GRADED';
  score: string | null;
  feedback: string;
  submitted_at: string;
  updated_at: string;
}

export const teacherService = {
  async getDashboard(): Promise<TeacherDashboardResponse> {
    const res = await api.get('/teacher/dashboard/');
    return res.data;
  },

  async listCourses(): Promise<TeacherCourseListItem[]> {
    const res = await api.get('/teacher/courses/');
    return res.data;
  },

  async getCourse(courseId: string): Promise<TeacherCourseDetail> {
    const res = await api.get(`/teacher/courses/${courseId}/`);
    return res.data;
  },

  async listAssignments(status?: 'PENDING' | 'SUBMITTED' | 'GRADED'): Promise<TeacherAssignmentListItem[]> {
    const res = await api.get('/teacher/assignments/', { params: status ? { status } : undefined });
    return res.data;
  },

  async startContent(contentId: string) {
    const res = await api.post(`/teacher/progress/content/${contentId}/start/`);
    return res.data;
  },

  async updateContent(contentId: string, payload: { video_progress_seconds?: number; progress_percentage?: number }) {
    const res = await api.patch(`/teacher/progress/content/${contentId}/`, payload);
    return res.data;
  },

  async completeContent(contentId: string) {
    const res = await api.post(`/teacher/progress/content/${contentId}/complete/`);
    return res.data;
  },

  async submitAssignment(assignmentId: string, payload: { submission_text?: string; file_url?: string }) {
    const res = await api.post(`/teacher/assignments/${assignmentId}/submit/`, payload);
    return res.data as TeacherAssignmentSubmission;
  },

  async getSubmission(assignmentId: string) {
    const res = await api.get(`/teacher/assignments/${assignmentId}/submission/`);
    return res.data as TeacherAssignmentSubmission;
  },
};

