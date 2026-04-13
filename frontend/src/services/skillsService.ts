// src/services/skillsService.ts
//
// API service for the Skills Matrix feature -- skills CRUD, course-skill
// mappings, teacher skill matrix, and gap analysis.

import api from '../config/api';

// ── Types ───────────────────────────────────────────────────────────────

export interface Skill {
  id: string;
  name: string;
  description: string;
  category: string;
  level_required: number;
  created_at: string;
  updated_at?: string;
}

export interface SkillCreateData {
  name: string;
  description?: string;
  category: string;
  level_required: number;
}

export interface CourseSkillMapping {
  id: string;
  course: string;
  skill: string;
  level_taught: number;
  skill_name: string;
  skill_category: string;
  course_title: string;
  created_at: string;
}

export interface CourseSkillCreateData {
  course: string;
  skill: string;
  level_taught: number;
}

/** Nested teacher shape used in the matrix view. */
export interface TeacherRef {
  id: string;
  first_name: string;
  last_name: string;
  email: string;
}

/**
 * Enriched teacher-skill record used by the Teacher Matrix tab.
 * The backend returns flat fields; the service layer reshapes them
 * into nested `teacher` and `skill` objects for UI convenience.
 */
export interface TeacherSkill {
  id: string;
  teacher: TeacherRef;
  skill: Skill;
  current_level: number;
  target_level: number;
  last_assessed: string | null;
  has_gap: boolean;
  gap_size: number;
  created_at: string;
  updated_at?: string;
}

/** Raw shape returned by the backend TeacherSkillSerializer. */
interface TeacherSkillRaw {
  id: string;
  teacher: string;
  skill: string;
  current_level: number;
  target_level: number;
  last_assessed: string | null;
  skill_name: string;
  skill_category: string;
  teacher_name: string;
  teacher_email: string;
  has_gap: boolean;
  gap_size: number;
  created_at: string;
  updated_at: string;
}

export interface RecommendedCourse {
  id: string;
  title: string;
  level_taught: number;
}

/**
 * Aggregated gap analysis item (one per skill).
 * The backend returns per-teacher rows; the service aggregates them
 * so the UI can show one card per skill.
 */
export interface GapAnalysisItem {
  skill: Skill;
  avg_gap: number;
  teachers_below_target: number;
  recommended_courses: RecommendedCourse[];
}

/** Raw row returned by the backend gap-analysis endpoint. */
interface GapAnalysisRaw {
  teacher_id: string;
  teacher_name: string;
  teacher_email: string;
  skill_id: string;
  skill_name: string;
  skill_category: string;
  current_level: number;
  target_level: number;
  gap_size: number;
  recommended_courses: Array<{
    course_id: string;
    course_title: string;
    level_taught: number;
  }>;
}

// ── Helpers ─────────────────────────────────────────────────────────────

/**
 * Parse teacher name string into first/last. The backend serializer
 * returns `get_full_name()` which is "First Last" or just an email.
 */
function parseTeacherName(name: string): { first_name: string; last_name: string } {
  const parts = name.trim().split(/\s+/);
  return {
    first_name: parts[0] || '',
    last_name: parts.slice(1).join(' ') || '',
  };
}

/** Reshape a raw backend TeacherSkill record into the nested UI shape. */
function toTeacherSkill(raw: TeacherSkillRaw): TeacherSkill {
  const { first_name, last_name } = parseTeacherName(raw.teacher_name);
  return {
    id: raw.id,
    teacher: {
      id: raw.teacher,
      first_name,
      last_name,
      email: raw.teacher_email,
    },
    skill: {
      id: raw.skill,
      name: raw.skill_name,
      description: '',
      category: raw.skill_category,
      level_required: raw.target_level,
      created_at: '',
    },
    current_level: raw.current_level,
    target_level: raw.target_level,
    last_assessed: raw.last_assessed,
    has_gap: raw.has_gap,
    gap_size: raw.gap_size,
    created_at: raw.created_at,
    updated_at: raw.updated_at,
  };
}

/**
 * Aggregate flat per-teacher gap rows into one entry per skill.
 * Computes the average gap size and counts unique teachers below target.
 */
function aggregateGaps(rows: GapAnalysisRaw[]): GapAnalysisItem[] {
  const bySkill = new Map<
    string,
    {
      skill: Skill;
      gaps: number[];
      courses: Map<string, RecommendedCourse>;
    }
  >();

  for (const row of rows) {
    let entry = bySkill.get(row.skill_id);
    if (!entry) {
      entry = {
        skill: {
          id: row.skill_id,
          name: row.skill_name,
          description: '',
          category: row.skill_category,
          level_required: row.target_level,
          created_at: '',
        },
        gaps: [],
        courses: new Map(),
      };
      bySkill.set(row.skill_id, entry);
    }
    entry.gaps.push(row.gap_size);

    // Collect unique recommended courses
    for (const rc of row.recommended_courses) {
      if (!entry.courses.has(rc.course_id)) {
        entry.courses.set(rc.course_id, {
          id: rc.course_id,
          title: rc.course_title,
          level_taught: rc.level_taught,
        });
      }
    }
  }

  return Array.from(bySkill.values()).map((entry) => ({
    skill: entry.skill,
    avg_gap:
      entry.gaps.length > 0
        ? entry.gaps.reduce((a, b) => a + b, 0) / entry.gaps.length
        : 0,
    teachers_below_target: entry.gaps.length,
    recommended_courses: Array.from(entry.courses.values()),
  }));
}

// ── Service ─────────────────────────────────────────────────────────────

export const skillsService = {
  // ── Skills CRUD ─────────────────────────────────────────────────────

  /** List all skills for the current tenant. */
  list(params?: { category?: string; search?: string }) {
    return api.get('/skills/', { params });
  },

  /** Create a new skill. */
  create(data: SkillCreateData) {
    return api.post('/skills/create/', data);
  },

  /** Get a single skill by ID. */
  get(id: string) {
    return api.get(`/skills/${id}/`);
  },

  /** Update an existing skill (partial). */
  update(id: string, data: Partial<SkillCreateData>) {
    return api.patch(`/skills/${id}/update/`, data);
  },

  /** Delete a skill. */
  delete(id: string) {
    return api.delete(`/skills/${id}/delete/`);
  },

  // ── Skill Categories ────────────────────────────────────────────────

  /** List distinct skill categories for the tenant. */
  async categories() {
    const res = await api.get('/skills/categories/');
    // Backend returns { categories: string[] }
    return { data: res.data.categories ?? [] };
  },

  // ── Course-Skill Mappings ───────────────────────────────────────────

  /** List course-skill mappings. */
  listCourseMappings(params?: { course_id?: string; skill_id?: string }) {
    return api.get('/skills/course-mappings/', { params });
  },

  /** Create a course-skill mapping. */
  createCourseMapping(data: CourseSkillCreateData) {
    return api.post('/skills/course-mappings/create/', data);
  },

  /** Delete a course-skill mapping. */
  deleteCourseMapping(id: string) {
    return api.delete(`/skills/course-mappings/${id}/delete/`);
  },

  // ── Teacher Skill Matrix ────────────────────────────────────────────

  /**
   * Fetch the teacher-skill matrix.
   * Returns data reshaped into nested `teacher` / `skill` objects.
   */
  async matrix(params?: { teacher_id?: string; category?: string }) {
    const res = await api.get('/skills/matrix/', { params });
    const rawResults: TeacherSkillRaw[] = res.data?.results ?? [];
    return { data: { results: rawResults.map(toTeacherSkill) } };
  },

  /** Assign a skill to a teacher. */
  assign(data: {
    teacher: string;
    skill: string;
    current_level?: number;
    target_level?: number;
  }) {
    return api.post('/skills/assign/', data);
  },

  /** Update a teacher's skill levels. */
  updateTeacherSkill(
    teacherSkillId: string,
    data: { current_level?: number; target_level?: number },
  ) {
    return api.patch(`/skills/teacher/${teacherSkillId}/update/`, data);
  },

  /** Remove a skill assignment from a teacher. */
  deleteTeacherSkill(teacherSkillId: string) {
    return api.delete(`/skills/teacher/${teacherSkillId}/delete/`);
  },

  /**
   * Bulk update teacher skill levels.
   * Accepts an array of `{ id, current_level, target_level }`.
   */
  bulkUpdate(
    updates: Array<{ id: string; current_level: number; target_level: number }>,
  ) {
    const payload = {
      updates: updates.map((u) => ({
        teacher_skill_id: u.id,
        current_level: u.current_level,
        target_level: u.target_level,
      })),
    };
    return api.post('/skills/bulk-update/', payload);
  },

  // ── Gap Analysis ────────────────────────────────────────────────────

  /**
   * Fetch gap analysis data, aggregated per skill.
   * The backend returns per-teacher rows; this method groups them
   * by skill and computes average gap sizes.
   */
  async gapAnalysis(params?: { teacher_id?: string; category?: string }) {
    const res = await api.get('/skills/gap-analysis/', { params });
    const rawResults: GapAnalysisRaw[] = res.data?.results ?? [];
    return { data: { results: aggregateGaps(rawResults) } };
  },
};
