// src/services/adminRubricService.ts
//
// Admin API client for Rubric CRUD + evaluation (TASK-044 backend).
//
// Endpoints (all admin-only + tenant-scoped):
//   GET  /admin/rubrics/                       → paginated list
//   POST /admin/rubrics/                       → create
//   GET  /admin/rubrics/:id/                   → detail
//   PATCH /admin/rubrics/:id/                  → update
//   DELETE /admin/rubrics/:id/                 → delete
//   POST /admin/rubrics/:id/clone/             → deep-copy
//   GET  /admin/assignments/:id/attach-rubric/ → get current attachment
//   POST /admin/assignments/:id/attach-rubric/ → attach / detach
//   POST /admin/submissions/:id/evaluate/      → grade a submission
//   GET  /teacher/submissions/:id/evaluation/  → teacher views own evaluation

import api from '../config/api';

// ── Types ────────────────────────────────────────────────────────────────────

export interface RubricLevel {
  id: string;
  title: string;
  description: string;
  points: number;
  order: number;
}

export interface RubricCriterion {
  id: string;
  title: string;
  description: string;
  max_points: number;
  order: number;
  levels: RubricLevel[];
}

export interface Rubric {
  id: string;
  title: string;
  description: string;
  total_points: number;
  is_active: boolean;
  criteria: RubricCriterion[];
  created_at: string;
  updated_at: string;
}

export interface RubricListResponse {
  count: number;
  next: string | null;
  previous: string | null;
  results: Rubric[];
}

// Write payload types (mirrors RubricWriteSerializer)
export interface RubricLevelPayload {
  title: string;
  description?: string;
  points: number;
  order?: number;
}

export interface RubricCriterionPayload {
  title: string;
  description?: string;
  max_points: number;
  order?: number;
  levels?: RubricLevelPayload[];
}

export interface RubricWritePayload {
  title: string;
  description?: string;
  is_active?: boolean;
  criteria?: RubricCriterionPayload[];
}

// Evaluation types
export interface RubricScoreEntry {
  criterion_id: string;
  level_id?: string | null;
  points?: number;
  comment?: string;
}

export interface RubricEvaluatePayload {
  scores: RubricScoreEntry[];
  feedback?: string;
}

export interface RubricEvaluation {
  id: string;
  submission: string;
  rubric: string;
  rubric_title: string;
  evaluator: string;
  evaluator_email: string;
  scores: Record<
    string,
    { level_id: string | null; points: string; comment: string }
  >;
  total_score: string;
  feedback: string;
  created_at: string;
  updated_at: string;
}

// ── API surface ──────────────────────────────────────────────────────────────

export const adminRubricService = {
  // ── Rubric CRUD ──────────────────────────────────────────────────────

  async listRubrics(params?: {
    search?: string;
    is_active?: boolean;
    page?: number;
  }): Promise<RubricListResponse> {
    const res = await api.get('/admin/rubrics/', { params });
    // Backend paginates; fall back to wrapping plain arrays for robustness.
    if (Array.isArray(res.data)) {
      return { count: res.data.length, next: null, previous: null, results: res.data };
    }
    return res.data;
  },

  async getRubric(rubricId: string): Promise<Rubric> {
    const res = await api.get(`/admin/rubrics/${rubricId}/`);
    return res.data;
  },

  async createRubric(payload: RubricWritePayload): Promise<Rubric> {
    const res = await api.post('/admin/rubrics/', payload);
    return res.data;
  },

  async updateRubric(
    rubricId: string,
    payload: Partial<RubricWritePayload>,
  ): Promise<Rubric> {
    const res = await api.patch(`/admin/rubrics/${rubricId}/`, payload);
    return res.data;
  },

  async deleteRubric(rubricId: string): Promise<void> {
    await api.delete(`/admin/rubrics/${rubricId}/`);
  },

  async cloneRubric(rubricId: string, title?: string): Promise<Rubric> {
    const res = await api.post(`/admin/rubrics/${rubricId}/clone/`, title ? { title } : {});
    return res.data;
  },

  // ── Assignment-rubric attachment ─────────────────────────────────────

  async getAssignmentRubric(
    assignmentId: string,
  ): Promise<{ assignment_id: string; rubric: Rubric | null }> {
    const res = await api.get(`/admin/assignments/${assignmentId}/attach-rubric/`);
    return res.data;
  },

  async attachRubric(
    assignmentId: string,
    rubricId: string | null,
  ): Promise<{ assignment_id: string; rubric: Rubric | null }> {
    const res = await api.post(`/admin/assignments/${assignmentId}/attach-rubric/`, {
      rubric_id: rubricId,
    });
    return res.data;
  },

  // ── Evaluation ───────────────────────────────────────────────────────

  /** Admin grades a submission using the rubric attached to its assignment. */
  async evaluateSubmission(
    submissionId: string,
    payload: RubricEvaluatePayload,
  ): Promise<RubricEvaluation> {
    const res = await api.post(`/admin/submissions/${submissionId}/evaluate/`, payload);
    return res.data;
  },

  /** Teacher retrieves their own evaluation result. */
  async getMyEvaluation(submissionId: string): Promise<RubricEvaluation> {
    const res = await api.get(`/teacher/submissions/${submissionId}/evaluation/`);
    return res.data;
  },
};
