// src/services/academicsService.ts
/**
 * API client for academic structure management.
 * Used by admin School View pages and teacher My Classes pages.
 */

import api from '../config/api';

// ─── Types ───────────────────────────────────────────────────────────────────

export interface GradeBand {
  id: string;
  name: string;
  short_code: string;
  order: number;
  curriculum_framework: string;
  theme_config: {
    accent_color?: string;
    bg_image?: string;
    welcome_msg?: string;
  } | null;
  grade_count: number;
  created_at: string;
  updated_at: string;
}

export interface Grade {
  id: string;
  grade_band: string;
  grade_band_name: string;
  grade_band_short_code: string;
  name: string;
  short_code: string;
  order: number;
  student_count: number;
  section_count: number;
  course_count?: number;
  created_at: string;
  updated_at: string;
}

export interface Section {
  id: string;
  grade: string;
  grade_name: string;
  grade_short_code: string;
  name: string;
  academic_year: string;
  class_teacher: string | null;
  class_teacher_name: string | null;
  student_count: number;
  created_at: string;
  updated_at: string;
}

export interface Subject {
  id: string;
  name: string;
  code: string;
  department: string;
  applicable_grade_ids: string[];
  applicable_grade_names: Array<{ id: string; name: string; short_code: string }>;
  is_elective: boolean;
  created_at: string;
  updated_at: string;
}

export interface TeachingAssignment {
  id: string;
  teacher: string;
  teacher_name: string;
  teacher_email: string;
  subject: string;
  subject_name: string;
  subject_code: string;
  section_ids: string[];
  section_details: Array<{
    id: string;
    name: string;
    grade_name: string;
    grade_short_code: string;
    academic_year: string;
  }>;
  academic_year: string;
  is_class_teacher: boolean;
  created_at: string;
  updated_at: string;
}

export interface SchoolOverviewResponse {
  academic_year: string;
  school_name: string;
  grade_bands: Array<GradeBand & { grades: Grade[] }>;
}

export interface SectionStudentsResponse {
  section: Section;
  students: Array<{
    id: string;
    email: string;
    first_name: string;
    last_name: string;
    student_id: string;
    is_active: boolean;
    last_login: string | null;
    role: string;
  }>;
  total: number;
}

export interface SectionTeachersResponse {
  section: Section;
  teachers: TeachingAssignment[];
}

export interface SectionCoursesResponse {
  section: Section;
  courses: Array<{
    id: string;
    title: string;
    slug: string;
    is_published: boolean;
    is_active: boolean;
    created_at: string;
    student_count?: number;
  }>;
}

export interface CSVImportResult {
  created: number;
  skipped: number;
  errors: Array<{ row: number; error: string }>;
  total_rows: number;
}

export interface PromotionPreview {
  current_academic_year: string;
  grades: Array<{
    grade_id: string;
    grade_name: string;
    grade_short_code: string;
    student_count: number;
    next_grade_id: string | null;
    next_grade_name: string;
    is_final_grade: boolean;
  }>;
  total_students: number;
}

export interface PromotionResult {
  promoted: number;
  graduated: number;
  new_academic_year: string;
}

// Teacher My Classes types
export interface MyClassesSection {
  id: string;
  name: string;
  grade_name: string;
  grade_short_code: string;
  grade_band_name: string;
  academic_year: string;
  student_count: number;
  course_count: number;
  class_teacher_name: string | null;
  is_class_teacher: boolean;
}

export interface MyClassesAssignment {
  assignment_id: string;
  subject: {
    id: string;
    name: string;
    code: string;
    department: string;
  };
  academic_year: string;
  is_class_teacher: boolean;
  sections: MyClassesSection[];
}

export interface MyClassesResponse {
  academic_year: string;
  assignments: MyClassesAssignment[];
  total_sections: number;
}

export interface SectionDashboardResponse {
  section: {
    id: string;
    name: string;
    grade_name: string;
    grade_short_code: string;
    grade_band_name: string;
    academic_year: string;
  };
  tab: string;
  students?: Array<{
    id: string;
    first_name: string;
    last_name: string;
    email: string;
    student_id: string;
    is_active: boolean;
    last_login: string | null;
  }>;
  courses?: Array<{
    id: string;
    title: string;
    slug: string;
    is_published: boolean;
    is_active: boolean;
    created_at: string;
    student_count: number;
  }>;
  stats?: {
    total_students: number;
    active_students_7d: number;
    inactive_students: number;
    total_courses: number;
  };
  assignments?: Array<{
    id: string;
    title: string;
    course_id: string;
    due_date: string | null;
    max_score: string;
    is_quiz: boolean;
  }>;
  total?: number;
}

// ─── Service ─────────────────────────────────────────────────────────────────

export const academicsService = {
  // ─── School Overview ─────────────────────────────────────────
  async getSchoolOverview(): Promise<SchoolOverviewResponse> {
    const res = await api.get('/v1/academics/school-overview/');
    return res.data;
  },

  // ─── GradeBands ──────────────────────────────────────────────
  async getGradeBands(): Promise<GradeBand[]> {
    const res = await api.get('/v1/academics/grade-bands/');
    return res.data.data;
  },

  async createGradeBand(data: Partial<GradeBand>): Promise<GradeBand> {
    const res = await api.post('/v1/academics/grade-bands/', data);
    return res.data;
  },

  async updateGradeBand(id: string, data: Partial<GradeBand>): Promise<GradeBand> {
    const res = await api.patch(`/v1/academics/grade-bands/${id}/`, data);
    return res.data;
  },

  async deleteGradeBand(id: string): Promise<void> {
    await api.delete(`/v1/academics/grade-bands/${id}/`);
  },

  // ─── Grades ──────────────────────────────────────────────────
  async getGrades(gradeBandId?: string): Promise<Grade[]> {
    const res = await api.get('/v1/academics/grades/', {
      params: gradeBandId ? { grade_band: gradeBandId } : undefined,
    });
    return res.data.data;
  },

  async createGrade(data: { grade_band: string; name: string; short_code: string; order: number }): Promise<Grade> {
    const res = await api.post('/v1/academics/grades/', data);
    return res.data;
  },

  async updateGrade(id: string, data: Partial<Grade>): Promise<Grade> {
    const res = await api.patch(`/v1/academics/grades/${id}/`, data);
    return res.data;
  },

  async deleteGrade(id: string): Promise<void> {
    await api.delete(`/v1/academics/grades/${id}/`);
  },

  // ─── Sections ────────────────────────────────────────────────
  async getSections(gradeId?: string, academicYear?: string): Promise<Section[]> {
    const params: Record<string, string> = {};
    if (gradeId) params.grade = gradeId;
    if (academicYear) params.academic_year = academicYear;
    const res = await api.get('/v1/academics/sections/', { params });
    return res.data.data;
  },

  async createSection(data: { grade: string; name: string; academic_year: string; class_teacher?: string }): Promise<Section> {
    const res = await api.post('/v1/academics/sections/', data);
    return res.data;
  },

  async updateSection(id: string, data: Partial<Section>): Promise<Section> {
    const res = await api.patch(`/v1/academics/sections/${id}/`, data);
    return res.data;
  },

  async deleteSection(id: string): Promise<void> {
    await api.delete(`/v1/academics/sections/${id}/`);
  },

  // ─── Section Detail Views ────────────────────────────────────
  async getSectionStudents(sectionId: string, search?: string): Promise<SectionStudentsResponse> {
    const res = await api.get(`/v1/academics/sections/${sectionId}/students/`, {
      params: search ? { search } : undefined,
    });
    return res.data;
  },

  async getSectionTeachers(sectionId: string): Promise<SectionTeachersResponse> {
    const res = await api.get(`/v1/academics/sections/${sectionId}/teachers/`);
    return res.data;
  },

  async getSectionCourses(sectionId: string): Promise<SectionCoursesResponse> {
    const res = await api.get(`/v1/academics/sections/${sectionId}/courses/`);
    return res.data;
  },

  // ─── Section Actions ─────────────────────────────────────────
  async importStudents(sectionId: string, file: File): Promise<CSVImportResult> {
    const form = new FormData();
    form.append('file', file);
    const res = await api.post(
      `/v1/academics/sections/${sectionId}/import-students/`,
      form,
      { headers: { 'Content-Type': 'multipart/form-data' } },
    );
    return res.data;
  },

  async addStudent(sectionId: string, data: {
    email: string;
    first_name: string;
    last_name: string;
    parent_email?: string;
  }): Promise<any> {
    const res = await api.post(`/v1/academics/sections/${sectionId}/add-student/`, data);
    return res.data;
  },

  async transferStudent(studentId: string, sectionId: string): Promise<any> {
    const res = await api.post(`/v1/academics/students/${studentId}/transfer/`, {
      section_id: sectionId,
    });
    return res.data;
  },

  // ─── Subjects ────────────────────────────────────────────────
  async getSubjects(department?: string): Promise<Subject[]> {
    const res = await api.get('/v1/academics/subjects/', {
      params: department ? { department } : undefined,
    });
    return res.data.data;
  },

  async createSubject(data: Partial<Subject>): Promise<Subject> {
    const res = await api.post('/v1/academics/subjects/', data);
    return res.data;
  },

  async updateSubject(id: string, data: Partial<Subject>): Promise<Subject> {
    const res = await api.patch(`/v1/academics/subjects/${id}/`, data);
    return res.data;
  },

  async deleteSubject(id: string): Promise<void> {
    await api.delete(`/v1/academics/subjects/${id}/`);
  },

  // ─── Teaching Assignments ────────────────────────────────────
  async getTeachingAssignments(params?: {
    teacher?: string;
    academic_year?: string;
    subject?: string;
  }): Promise<TeachingAssignment[]> {
    const res = await api.get('/v1/academics/teaching-assignments/', { params });
    return res.data.data;
  },

  async createTeachingAssignment(data: {
    teacher: string;
    subject: string;
    section_ids: string[];
    academic_year: string;
    is_class_teacher?: boolean;
  }): Promise<TeachingAssignment> {
    const res = await api.post('/v1/academics/teaching-assignments/', data);
    return res.data;
  },

  async updateTeachingAssignment(id: string, data: Partial<TeachingAssignment>): Promise<TeachingAssignment> {
    const res = await api.patch(`/v1/academics/teaching-assignments/${id}/`, data);
    return res.data;
  },

  async deleteTeachingAssignment(id: string): Promise<void> {
    await api.delete(`/v1/academics/teaching-assignments/${id}/`);
  },

  // ─── Promotion ───────────────────────────────────────────────
  async getPromotionPreview(): Promise<PromotionPreview> {
    const res = await api.get('/v1/academics/promotion/preview/');
    return res.data;
  },

  async executePromotion(data: {
    new_academic_year: string;
    excluded_student_ids?: string[];
    graduated_student_ids?: string[];
  }): Promise<PromotionResult> {
    const res = await api.post('/v1/academics/promotion/execute/', data);
    return res.data;
  },

  // ─── Course Clone ────────────────────────────────────────────
  async cloneCourse(courseId: string, title?: string): Promise<any> {
    const res = await api.post(`/v1/academics/courses/${courseId}/clone/`, {
      title,
    });
    return res.data;
  },

  // ─── Teacher: My Classes ────────────────────────────────────
  async getMyClasses(): Promise<MyClassesResponse> {
    const res = await api.get('/v1/teacher/academics/my-classes/');
    return res.data;
  },

  async getSectionDashboard(sectionId: string, tab: string, search?: string): Promise<SectionDashboardResponse> {
    const params: Record<string, string> = { tab };
    if (search) params.search = search;
    const res = await api.get(`/v1/teacher/academics/sections/${sectionId}/dashboard/`, {
      params,
    });
    return res.data;
  },
};
