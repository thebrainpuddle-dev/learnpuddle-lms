import api from '../config/api';
import type { StudySummaryListItem, StudySummaryDetail } from '../types/studySummary';

// ─── Dashboard ────────────────────────────────────────────────────────────────

export interface StudentDashboardResponse {
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

// ─── Courses ──────────────────────────────────────────────────────────────────

export interface StudentCourseListItem {
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

export interface StudentCourseDetail {
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
    completed_content_count: number;
    total_content_count: number;
    completion_percentage: number;
    is_completed: boolean;
    is_locked: boolean;
    lock_reason: string;
    contents: Array<{
      id: string;
      title: string;
      content_type: 'VIDEO' | 'DOCUMENT' | 'LINK' | 'TEXT' | 'AI_CLASSROOM' | 'CHATBOT';
      order: number;
      file_url?: string;
      hls_url?: string;
      thumbnail_url?: string;
      file_size?: number | null;
      duration?: number | null;
      text_content?: string;
      is_mandatory: boolean;
      is_active: boolean;
      status: 'NOT_STARTED' | 'IN_PROGRESS' | 'COMPLETED';
      progress_percentage: number;
      video_progress_seconds: number;
      is_completed: boolean;
      is_locked: boolean;
      lock_reason: string;
      has_transcript?: boolean;
      transcript_vtt_url?: string;
    }>;
  }>;
}

// ─── Assignments ──────────────────────────────────────────────────────────────

export interface StudentAssignmentListItem {
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
  is_quiz: boolean;
}

export interface StudentAssignmentSubmission {
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

// ─── Gamification ─────────────────────────────────────────────────────────────

export interface StudentGamificationSummary {
  points_total: number;
  points_breakdown: {
    content_completion: number;
    course_completion: number;
    assignment_submission: number;
    streak_bonus: number;
    quest_bonus: number;
  };
  streak: {
    current_days: number;
    target_days: number;
  };
  badges: Array<{
    level: number;
    key: string;
    name: string;
    min_points: number;
    max_points: number | null;
    color: string;
    unlocked: boolean;
    progress_percentage: number;
  }>;
}

// ─── Service ──────────────────────────────────────────────────────────────────

export const studentService = {
  // Dashboard
  async getStudentDashboard(): Promise<StudentDashboardResponse> {
    const res = await api.get('/v1/student/dashboard/');
    return res.data;
  },

  // Courses
  async getStudentCourses(): Promise<StudentCourseListItem[]> {
    const res = await api.get('/v1/student/courses/');
    return res.data;
  },

  async getStudentCourseDetail(courseId: string): Promise<StudentCourseDetail> {
    const res = await api.get(`/v1/student/courses/${courseId}/`);
    return res.data;
  },

  // Content Progress
  async startContentProgress(contentId: string) {
    const res = await api.post(`/v1/student/progress/content/${contentId}/start/`);
    return res.data;
  },

  async updateContentProgress(contentId: string, data: { video_progress_seconds?: number; progress_percentage?: number }) {
    const res = await api.patch(`/v1/student/progress/content/${contentId}/`, data);
    return res.data;
  },

  async completeContent(contentId: string) {
    const res = await api.post(`/v1/student/progress/content/${contentId}/complete/`);
    return res.data;
  },

  // Assignments
  async getStudentAssignments(status?: 'PENDING' | 'SUBMITTED' | 'GRADED'): Promise<StudentAssignmentListItem[]> {
    const res = await api.get('/v1/student/assignments/', { params: status ? { status } : undefined });
    return res.data;
  },

  async submitAssignment(assignmentId: string, data: { submission_text?: string; file_url?: string }) {
    const res = await api.post(`/v1/student/assignments/${assignmentId}/submit/`, data);
    return res.data as StudentAssignmentSubmission;
  },

  // Quizzes
  async getQuizDetail(assignmentId: string) {
    const res = await api.get(`/v1/student/quizzes/${assignmentId}/`);
    return res.data as {
      assignment_id: string;
      quiz_id: string;
      schema_version: number;
      questions: Array<{
        id: string;
        order: number;
        question_type: 'MCQ' | 'SHORT_ANSWER' | 'TRUE_FALSE';
        selection_mode: 'SINGLE' | 'MULTIPLE';
        prompt: string;
        options: string[];
        points: number;
      }>;
      submission: null | {
        answers: Record<string, any>;
        score: number | null;
        graded_at: string | null;
        submitted_at: string;
      };
    };
  },

  async submitQuiz(assignmentId: string, answers: Record<string, any>) {
    const res = await api.post(`/v1/student/quizzes/${assignmentId}/submit/`, { answers });
    return res.data as {
      quiz_id: string;
      assignment_id: string;
      score: number | null;
      graded_at: string | null;
    };
  },

  // Gamification
  async getGamificationSummary(): Promise<StudentGamificationSummary> {
    const res = await api.get('/v1/student/gamification/summary/');
    return res.data;
  },

  // Search
  async searchStudentContent(query: string) {
    const res = await api.get('/v1/student/search/', { params: { q: query } });
    return res.data;
  },

  // Video Transcript
  async getVideoTranscript(contentId: string) {
    const res = await api.get(`/v1/student/videos/${contentId}/transcript/`);
    return res.data;
  },

  // Assignment Submission Detail
  async getAssignmentSubmission(assignmentId: string) {
    const res = await api.get(`/v1/student/assignments/${assignmentId}/submission/`);
    return res.data as StudentAssignmentSubmission;
  },

  // Study Summaries
  async getStudySummaries(courseId?: string): Promise<StudySummaryListItem[]> {
    const res = await api.get('/v1/student/study-summaries/', { params: courseId ? { course_id: courseId } : undefined });
    return res.data;
  },

  async getStudySummaryDetail(summaryId: string): Promise<StudySummaryDetail> {
    const res = await api.get(`/v1/student/study-summaries/${summaryId}/`);
    return res.data;
  },

  async getStudySummaryForContent(contentId: string): Promise<StudySummaryDetail | null> {
    try {
      const summaries = await api.get('/v1/student/study-summaries/', { params: { content_id: contentId } });
      const match = (summaries.data as StudySummaryListItem[]).find((s) => s.content_id === contentId && s.status === 'READY');
      if (match) {
        const detail = await api.get(`/v1/student/study-summaries/${match.id}/`);
        return detail.data;
      }
    } catch {
      // No summaries found
    }
    return null;
  },

  async deleteStudySummary(summaryId: string): Promise<void> {
    await api.delete(`/v1/student/study-summaries/${summaryId}/delete/`);
  },
};
