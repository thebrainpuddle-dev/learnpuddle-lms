// src/services/chatbotService.ts
//
// Service layer for the RAG-backed chatbot Q&A widget (TASK-061).
// Endpoints:
//   POST /api/v1/chatbot/ask/          — single-turn question
//   GET  /api/v1/chatbot/history/      — list recent queries (max 20)
//   DELETE /api/v1/chatbot/history/:id — delete a query row

import api from '../config/api';

// ─── Shared types ─────────────────────────────────────────────────────────────

export interface ChatbotCitation {
  block: number;
  source_type: 'content' | 'transcript' | 'module' | 'course' | string;
  source_id: string;
  title: string;
  score: number;
}

export interface AskResponse {
  query_id: string;
  answer: string;
  citations: ChatbotCitation[];
  grounded: boolean;
}

export interface ChatbotHistoryItem {
  id: string;
  course_id: string | null;
  answer: string;
  citations: ChatbotCitation[];
  grounded: boolean;
  provider: string;
  model: string;
  tokens_prompt: number | null;
  tokens_completion: number | null;
  latency_ms: number | null;
  created_at: string;
}

export interface ChatbotHistoryResponse {
  results: ChatbotHistoryItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface AskRequest {
  question: string;
  course_id?: string;
  top_k?: number;
}

// ─── Service functions ────────────────────────────────────────────────────────

export const chatbotService = {
  /**
   * POST /api/v1/chatbot/ask/
   * Submits a single-turn question. Returns answer + citations.
   */
  async askQuestion(params: AskRequest): Promise<AskResponse> {
    const response = await api.post<AskResponse>('/v1/chatbot/ask/', params);
    return response.data;
  },

  /**
   * GET /api/v1/chatbot/history/
   * Returns up to 20 recent query rows for the current user.
   */
  async getHistory(pageSize = 20): Promise<ChatbotHistoryResponse> {
    const response = await api.get<ChatbotHistoryResponse>('/v1/chatbot/history/', {
      params: { page_size: pageSize, page: 1 },
    });
    return response.data;
  },

  /**
   * DELETE /api/v1/chatbot/history/:id/
   * Deletes a query row by ID.
   */
  async deleteHistoryItem(id: string): Promise<void> {
    await api.delete(`/v1/chatbot/history/${id}/`);
  },
};
