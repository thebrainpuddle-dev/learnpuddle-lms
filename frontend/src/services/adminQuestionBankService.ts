// src/services/adminQuestionBankService.ts
//
// Admin question-bank + question CRUD.
// Backend: apps/progress/assessment_urls.py

import api from '../config/api';

// ── Types ─────────────────────────────────────────────────────────────────────

export type QuestionType = 'MCQ' | 'MULTI' | 'SHORT' | 'TRUE_FALSE' | 'ESSAY';
export type Difficulty   = 'EASY' | 'MEDIUM' | 'HARD';

export interface QuestionChoice {
  id?:       string;
  text:      string;
  is_correct: boolean;
  order:     number;
}

export interface Question {
  id:            string;
  bank:          string;
  question_type: QuestionType;
  prompt:        string;
  points:        number;
  difficulty:    Difficulty;
  explanation:   string;
  metadata:      Record<string, unknown>;
  order:         number;
  choices:       QuestionChoice[];
  created_at:    string;
  updated_at:    string;
}

export interface QuestionBank {
  id:             string;
  title:          string;
  description:    string;
  tags:           string[];
  is_active:      boolean;
  question_count: number;
  created_at:     string;
  updated_at:     string;
}

export interface QuestionBankPayload {
  title:       string;
  description?: string;
  tags?:        string[];
  is_active?:   boolean;
}

export interface QuestionPayload {
  bank:          string;
  question_type: QuestionType;
  prompt:        string;
  points?:       number;
  difficulty?:   Difficulty;
  explanation?:  string;
  order?:        number;
  choices?:      Omit<QuestionChoice, 'id'>[];
}

// ── Service ───────────────────────────────────────────────────────────────────

export const adminQuestionBankService = {
  /** List all question banks for the current tenant. */
  async listBanks(search?: string): Promise<{ results: QuestionBank[] }> {
    const res = await api.get('/admin/question-banks/', {
      params: search ? { search } : undefined,
    });
    return res.data;
  },

  /** Create a new question bank. */
  async createBank(payload: QuestionBankPayload): Promise<QuestionBank> {
    const res = await api.post('/admin/question-banks/', payload);
    return res.data;
  },

  /** Update an existing question bank. */
  async updateBank(bankId: string, payload: Partial<QuestionBankPayload>): Promise<QuestionBank> {
    const res = await api.patch(`/admin/question-banks/${bankId}/`, payload);
    return res.data;
  },

  /** Delete a question bank (and all its questions). */
  async deleteBank(bankId: string): Promise<void> {
    await api.delete(`/admin/question-banks/${bankId}/`);
  },

  /** List questions in a bank. */
  async listQuestions(bankId: string, type?: QuestionType): Promise<{ results: Question[] }> {
    const res = await api.get(`/admin/question-banks/${bankId}/questions/`, {
      params: type ? { type } : undefined,
    });
    return res.data;
  },

  /** Create a question in a bank. */
  async createQuestion(bankId: string, payload: Omit<QuestionPayload, 'bank'>): Promise<Question> {
    const res = await api.post(`/admin/question-banks/${bankId}/questions/`, {
      ...payload,
      bank: bankId,
    });
    return res.data;
  },

  /** Update a question. */
  async updateQuestion(questionId: string, payload: Partial<QuestionPayload>): Promise<Question> {
    const res = await api.patch(`/admin/questions/${questionId}/`, payload);
    return res.data;
  },

  /** Delete a question. */
  async deleteQuestion(questionId: string): Promise<void> {
    await api.delete(`/admin/questions/${questionId}/`);
  },
};
