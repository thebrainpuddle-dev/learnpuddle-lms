// src/services/aiService.ts
//
// API service for AI-powered course generation and chat features.

import api from '../config/api';

// ─── Course Generation Types ────────────────────────────────────────────────

export interface GenerateOutlineRequest {
  topic: string;
  description: string;
  target_audience: string;
  num_modules: number;
  material_context?: string;
}

export interface OutlineModule {
  id?: string;
  title: string;
  description: string;
  content_items: OutlineContent[];
  learning_objectives?: string[];
  key_points?: string[];
  bloom_level?: string;
  suggested_types?: string[];
}

export interface OutlineContent {
  title: string;
  content_type: 'TEXT' | 'VIDEO' | 'DOCUMENT' | 'LINK';
  description: string;
}

export interface CourseOutline {
  title: string;
  description: string;
  target_audience: string;
  estimated_hours: number;
  modules: OutlineModule[];
}

export interface GenerateContentRequest {
  module_title: string;
  module_description: string;
  content_type: string;
  material_context?: string;
}

// ─── Chat Types ─────────────────────────────────────────────────────────────

export interface ChatSession {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ChatSource {
  source_type: string;
  content_id: string | null;
  score: number;
  excerpt: string;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: ChatSource[];
  created_at: string;
}

// ─── Service ────────────────────────────────────────────────────────────────

export const aiService = {
  // Course generation
  generateOutline: (data: GenerateOutlineRequest) =>
    api.post<{ outline: CourseOutline }>('/v1/courses/ai/generate-outline/', data).then(r => r.data.outline),

  createFromOutline: (outline: CourseOutline) =>
    api.post('/v1/courses/ai/create-from-outline/', { outline }),

  generateContent: (data: GenerateContentRequest) =>
    api.post('/v1/courses/ai/generate-content/', data),

  summarize: (data: { text: string; max_length?: number }) =>
    api.post('/v1/courses/ai/summarize/', data),

  parseMaterial: (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post<{ text: string; metadata: Record<string, unknown> }>('/v1/courses/ai/parse-material/', formData)
      .then(r => r.data);
  },

  generateAssignment: (data: { topic: string; description: string; material_context?: string; difficulty?: string }) =>
    api.post('/v1/courses/ai/generate-assignment/', data).then(r => r.data),

  // Chat sessions
  chatSessions: {
    list: (courseId: string) =>
      api.get<ChatSession[]>(`/v1/courses/${courseId}/chat/sessions/`),

    create: (courseId: string) =>
      api.post<ChatSession>(`/v1/courses/${courseId}/chat/sessions/`),

    delete: (courseId: string, sessionId: string) =>
      api.delete(`/v1/courses/${courseId}/chat/sessions/${sessionId}/`),

    messages: (courseId: string, sessionId: string) =>
      api.get<ChatMessage[]>(`/v1/courses/${courseId}/chat/sessions/${sessionId}/messages/`),

    sendMessage: (courseId: string, sessionId: string, content: string, context?: Record<string, unknown>) =>
      api.post<ChatMessage>(`/v1/courses/${courseId}/chat/sessions/${sessionId}/messages/`, {
        message: content,
        ...(context ? { context } : {}),
      }),
  },

  // AI Studio — Admin
  studio: {
    generateAudio: (lessonId: string, voice?: string) =>
      api.post<{ task_id: string; status: string }>(`/v1/courses/ai-studio/generate-audio/${lessonId}/`, {
        ...(voice ? { voice } : {}),
      }).then(r => r.data),

    getStatus: (itemId: string) =>
      api.get<{
        type: 'lesson' | 'scenario';
        id: string;
        title: string;
        status: string;
        scene_count?: number;
        node_count?: number;
        has_audio?: boolean;
        difficulty?: string;
        created_at: string;
        scenes?: unknown[];
      }>(`/v1/courses/ai-studio/status/${itemId}/`).then(r => r.data),
  },
};
