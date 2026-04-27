// src/services/assessmentService.ts
//
// Assessment API client — QuizConfig per content + teacher attempts.
// Backend contracts live in backend/apps/progress/assessment_urls.py and
// assessment_views.py (TASK-043). Admin bank/question CRUD is in
// `adminQuestionBankService.ts`.

import api from '../config/api';

// ── Shared types ─────────────────────────────────────────────────────────────

export type QuestionType = 'MCQ' | 'MULTI' | 'SHORT' | 'TRUE_FALSE' | 'ESSAY';

/** Attempt lifecycle — matches backend ATTEMPT_STATUS_CHOICES. */
export type AttemptStatus = 'IN_PROGRESS' | 'SUBMITTED' | 'EXPIRED';

/** Choice as rendered to the teacher during a live attempt (no `is_correct`). */
export interface SanitizedChoice {
  id: string;
  text: string;
  order: number;
}

/** Question as rendered to the teacher during a live attempt. */
export interface AttemptQuestion {
  id: string;
  type: QuestionType;
  prompt: string;
  points: number;
  difficulty: string;
  choices: SanitizedChoice[];
}

/** Answer shape stored client-side and sent to submit. */
export type AttemptAnswer =
  | { choice_id: string }          // MCQ / TRUE_FALSE — single choice id
  | { choice_ids: string[] }       // MULTI — list of choice ids
  | { text: string }               // SHORT / ESSAY
  | string                         // raw choice id (what backend actually reads)
  | string[];

/** Start-attempt response (created). */
export interface QuizAttemptStartResponse {
  id: string;
  attempt_number: number;
  status: AttemptStatus;
  started_at: string;
  /** 0 means unlimited. */
  time_limit_seconds: number;
  max_score: number;
  questions: AttemptQuestion[];
}

/** Submit response — includes grading and optionally correct answers. */
export interface QuizAttemptSubmitResponse {
  id: string;
  status: AttemptStatus;
  score: number;
  max_score: number;
  score_percent: number;
  passed: boolean;
  time_spent_seconds: number;
  submitted_at: string;
  /** When `show_correct_answers_after` is true the full snapshot is returned. */
  questions: AttemptQuestion[];
  answers: Record<string, unknown>;
}

export interface QuizAttemptListItem {
  id: string;
  content: string;
  attempt_number: number;
  status: AttemptStatus;
  started_at: string;
  submitted_at: string | null;
  time_spent_seconds: number;
  score: number;
  max_score: number;
  score_percent: number;
  passed: boolean;
  answers: Record<string, unknown>;
  questions_snapshot: unknown[];
}

// ── QuizConfig ───────────────────────────────────────────────────────────────

export interface QuizConfig {
  id: string;
  content: string;
  time_limit_seconds: number;
  max_attempts: number;
  pass_threshold_percent: number | string;
  shuffle_questions: boolean;
  shuffle_choices: boolean;
  show_correct_answers_after: boolean;
  random_selection_count: number | null;
  source_question_banks: string[];
  created_at: string;
  updated_at: string;
}

export interface QuizConfigPayload {
  time_limit_seconds?: number;
  max_attempts?: number;
  pass_threshold_percent?: number;
  shuffle_questions?: boolean;
  shuffle_choices?: boolean;
  show_correct_answers_after?: boolean;
  random_selection_count?: number | null;
  source_question_banks?: string[];
}

// ── API surface ──────────────────────────────────────────────────────────────

export const assessmentService = {
  // ── Admin: Quiz Config per content ─────────────────────────────────────
  async getQuizConfig(contentId: string): Promise<QuizConfig> {
    const res = await api.get(`/admin/contents/${contentId}/quiz-config/`);
    return res.data;
  },

  async updateQuizConfig(
    contentId: string,
    payload: QuizConfigPayload,
  ): Promise<QuizConfig> {
    const res = await api.patch(
      `/admin/contents/${contentId}/quiz-config/`,
      payload,
    );
    return res.data;
  },

  // ── Teacher: Attempts ──────────────────────────────────────────────────
  async startAttempt(contentId: string): Promise<QuizAttemptStartResponse> {
    const res = await api.post(`/teacher/quizzes/${contentId}/start/`);
    return res.data;
  },

  async submitAttempt(
    attemptId: string,
    answers: Record<string, unknown>,
    timeSpentSeconds?: number,
  ): Promise<QuizAttemptSubmitResponse> {
    const res = await api.post(`/teacher/quiz-attempts/${attemptId}/submit/`, {
      answers,
      ...(timeSpentSeconds !== undefined
        ? { time_spent_seconds: timeSpentSeconds }
        : {}),
    });
    return res.data;
  },

  async listMyAttempts(contentId?: string): Promise<{ results: QuizAttemptListItem[] }> {
    const res = await api.get('/teacher/quiz-attempts/', {
      params: contentId ? { content_id: contentId } : undefined,
    });
    return res.data;
  },
};
