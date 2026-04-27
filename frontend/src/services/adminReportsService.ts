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
  role?: string;
  grade_level?: string;
  section?: string;
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
  role?: string;
  grade_level?: string;
  section?: string;
}

export interface EngagementHeatmapCell {
  /** 0 = Monday .. 6 = Sunday (Python `datetime.weekday()`). */
  day: number;
  /** 0..23 in the requested timezone. */
  hour: number;
  count: number;
}

export interface EngagementHeatmapResponse {
  timezone: string;
  tz_fallback: boolean;
  start: string;
  end: string;
  total_events: number;
  max_cell: number;
  cells: EngagementHeatmapCell[];
}

export interface EngagementHeatmapParams {
  tz?: string;
  start?: string;
  end?: string;
}

export interface DeadlineAdherencePoint {
  /** Human-readable period label, e.g. "Jan 2026" */
  period: string;
  /** 0–100 percentage of teachers who met their deadline */
  adherencePercent: number;
  totalTeachers: number;
  onTime: number;
  late: number;
}

export interface ApprovalTrendsPoint {
  /** Human-readable period label, e.g. "Jan 2026" */
  period: string;
  approved: number;
  rejected: number;
  pending: number;
}

export interface CourseEffectivenessItem {
  courseId: string;
  courseName: string;
  /** 0–100 */
  completionRate: number;
  /** 0–100 */
  avgScore: number;
  enrolledCount: number;
}

export interface AnalyticsPeriodParams {
  start?: string; // ISO date, e.g. "2025-10-01"
  end?: string;   // ISO date, e.g. "2026-03-31"
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

  async courseProgress(params: { course_id: string; role?: string; status?: string; search?: string }): Promise<{ results: CourseProgressRow[] }> {
    const res = await api.get('/reports/course-progress/', { params });
    return res.data;
  },

  async assignmentStatus(params: { assignment_id: string; role?: string; status?: string; search?: string }): Promise<{ results: AssignmentStatusRow[] }> {
    const res = await api.get('/reports/assignment-status/', { params });
    return res.data;
  },

  async engagementHeatmap(
    params: EngagementHeatmapParams = {},
  ): Promise<EngagementHeatmapResponse> {
    // Strip undefined keys so we never send `?tz=undefined`.
    const clean: Record<string, string> = {};
    if (params.tz) clean.tz = params.tz;
    if (params.start) clean.start = params.start;
    if (params.end) clean.end = params.end;
    const res = await api.get<EngagementHeatmapResponse>(
      '/reports/engagement/heatmap/',
      { params: clean },
    );
    return res.data;
  },

  async deadlineAdherence(
    params: AnalyticsPeriodParams = {},
  ): Promise<DeadlineAdherencePoint[]> {
    const clean: Record<string, string> = {};
    if (params.start) clean.start = params.start;
    if (params.end) clean.end = params.end;
    const res = await api.get<DeadlineAdherencePoint[]>(
      '/reports/analytics/deadline-adherence/',
      { params: clean },
    );
    return res.data;
  },

  async approvalTrends(
    params: AnalyticsPeriodParams = {},
  ): Promise<ApprovalTrendsPoint[]> {
    const clean: Record<string, string> = {};
    if (params.start) clean.start = params.start;
    if (params.end) clean.end = params.end;
    const res = await api.get<ApprovalTrendsPoint[]>(
      '/reports/analytics/approval-trends/',
      { params: clean },
    );
    return res.data;
  },

  async courseEffectiveness(): Promise<CourseEffectivenessItem[]> {
    const res = await api.get<CourseEffectivenessItem[]>(
      '/reports/analytics/course-effectiveness/',
    );
    return res.data;
  },
};

