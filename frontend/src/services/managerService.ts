import api from '../config/api';

// ---------------------------------------------------------------------------
// Response types — aligned with backend apps/reports/manager_views.py
// ---------------------------------------------------------------------------

export interface TeamProgressTeacher {
  teacher_id: string;
  teacher_name: string;
  teacher_email: string;
  department: string | null;
  assigned_courses: number;
  completed_courses: number;
  progress_percentage: number;
}

export interface TeamProgressSummary {
  total_teachers: number;
  average_progress: number;
  fully_completed_teachers: number;
}

export interface TeamProgressResponse {
  results: TeamProgressTeacher[];
  summary: TeamProgressSummary;
}

export interface OverdueAssignment {
  teacher_id: string;
  teacher_name: string;
  teacher_email: string;
  department: string | null;
  course_id: string;
  course_title: string;
  deadline: string;
  days_overdue: number;
  status: string;
}

export interface OverdueResponse {
  results: OverdueAssignment[];
  total_overdue: number;
}

export interface ComplianceTeacher {
  teacher_id: string;
  teacher_name: string;
  teacher_email: string;
  department: string | null;
  is_compliant: boolean;
  certifications_held: number;
  certifications_required: number;
  missing_certifications: string[];
}

export interface ComplianceExpiring {
  teacher_name: string;
  teacher_email: string;
  certification_name: string;
  expires_at: string;
  days_until_expiry: number;
}

export interface ComplianceSummary {
  total_teachers: number;
  fully_compliant: number;
  non_compliant: number;
  expiring_within_30_days: number;
}

export interface ComplianceResponse {
  results: ComplianceTeacher[];
  expiring_soon: ComplianceExpiring[];
  summary: ComplianceSummary;
}

export interface SkillTeacherDetail {
  teacher_id: string;
  teacher_name: string;
  current_level: number;
  target_level: number;
  has_gap: boolean;
}

export interface SkillOverviewItem {
  skill_id: string;
  skill_name: string;
  skill_category: string;
  level_required: number;
  teachers_assessed: number;
  avg_current_level: number;
  avg_target_level: number;
  at_or_above_target: number;
  below_target: number;
  teacher_details: SkillTeacherDetail[];
}

export interface SkillsOverviewSummary {
  total_skills_tracked: number;
  total_teacher_skill_gaps: number;
  total_teachers: number;
}

export interface SkillsOverviewResponse {
  results: SkillOverviewItem[];
  summary: SkillsOverviewSummary;
}

// ---------------------------------------------------------------------------
// Service
// ---------------------------------------------------------------------------

export const managerService = {
  async getTeamProgress(params?: { department?: string }): Promise<TeamProgressResponse> {
    const res = await api.get('/v1/reports/manager/team-progress/', { params });
    return res.data;
  },

  async getOverdueAssignments(params?: { department?: string }): Promise<OverdueResponse> {
    const res = await api.get('/v1/reports/manager/overdue/', { params });
    return res.data;
  },

  async getComplianceOverview(params?: { department?: string }): Promise<ComplianceResponse> {
    const res = await api.get('/v1/reports/manager/compliance/', { params });
    return res.data;
  },

  async getTeamSkillsOverview(params?: { department?: string; category?: string }): Promise<SkillsOverviewResponse> {
    const res = await api.get('/v1/reports/manager/skills-overview/', { params });
    return res.data;
  },
};
