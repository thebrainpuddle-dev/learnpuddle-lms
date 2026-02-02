import api from '../config/api';

export interface ReportCourse {
  id: string;
  title: string;
  deadline: string | null;
}

export interface ReportAssignment {
  id: string;
  title: string;
  course_id: string;
  due_date: string | null;
}

export interface CourseProgressRow {
  teacher_id: string;
  teacher_name: string;
  teacher_email: string;
  course_id: string;
  course_title: string;
  deadline: string | null;
  status: string;
  completed_at: string | null;
}

export interface AssignmentStatusRow {
  teacher_id: string;
  teacher_name: string;
  teacher_email: string;
  assignment_id: string;
  assignment_title: string;
  due_date: string | null;
  status: string;
  submitted_at: string | null;
}

export const adminReportsService = {
  async listCourses(): Promise<ReportCourse[]> {
    const res = await api.get('/reports/courses/');
    return res.data;
  },

  async listAssignments(courseId?: string): Promise<ReportAssignment[]> {
    const res = await api.get('/reports/assignments/', { params: courseId ? { course_id: courseId } : undefined });
    return res.data;
  },

  async courseProgress(params: { course_id: string; status?: string; search?: string }): Promise<{ results: CourseProgressRow[] }> {
    const res = await api.get('/reports/course-progress/', { params });
    return res.data;
  },

  async assignmentStatus(params: { assignment_id: string; status?: string; search?: string }): Promise<{ results: AssignmentStatusRow[] }> {
    const res = await api.get('/reports/assignment-status/', { params });
    return res.data;
  },
};

