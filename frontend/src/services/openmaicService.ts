// src/services/openmaicService.ts
//
// API service for OpenMAIC features: MAIC AI Classroom.

import api from '../config/api';
import type { MAICClassroomMeta, MAICOutlineScene, MAICAgent } from '../types/maic';
import type { MAICAction } from '../types/maic-actions';
import type { MAICScene } from '../types/maic-scenes';
import type { AIChatbot, AIChatbotKnowledge, AIChatbotCreatePayload, Conversation } from '../types/chatbot';

// ─── MAIC AI Classroom API (Teacher) ─────────────────────────────────────────

export const maicApi = {
  // Classroom CRUD
  listClassrooms: (params?: { status?: string; search?: string }) =>
    api.get<MAICClassroomMeta[]>('/v1/teacher/maic/classrooms/', { params }),

  createClassroom: (data: { title: string; description?: string; topic?: string; language?: string; course_id?: string; config?: Record<string, unknown> }) =>
    api.post<{ id: string; title: string; status: string; created_at: string }>('/v1/teacher/maic/classrooms/create/', data),

  getClassroom: (id: string) =>
    api.get<MAICClassroomMeta>(`/v1/teacher/maic/classrooms/${id}/`),

  updateClassroom: (id: string, data: Partial<MAICClassroomMeta>) =>
    api.patch(`/v1/teacher/maic/classrooms/${id}/update/`, data),

  deleteClassroom: (id: string) =>
    api.delete(`/v1/teacher/maic/classrooms/${id}/delete/`),

  // Generation proxies (non-SSE)
  generateSceneContent: (data: { scene: MAICOutlineScene; agents: MAICAgent[]; language: string }) =>
    api.post('/v1/teacher/maic/generate/scene-content/', data),

  generateImage: (data: { prompt: string; style?: string }) =>
    api.post('/v1/teacher/maic/generate/image/', data),

  generateClassroom: (data: Record<string, unknown>) =>
    api.post('/v1/teacher/maic/generate/classroom/', data),

  // Quiz grading
  quizGrade: (data: { question: string; answer: string; commentPrompt?: string }) =>
    api.post('/v1/teacher/maic/quiz-grade/', data),

  // Export
  exportPptx: (classroomId: string) =>
    api.post('/v1/teacher/maic/export/pptx/', { classroomId }, { responseType: 'blob' }),

  exportHtml: (classroomId: string) =>
    api.post('/v1/teacher/maic/export/html/', { classroomId }, { responseType: 'blob' }),

  // Web search
  webSearch: (query: string) =>
    api.post('/v1/teacher/maic/web-search/', { query }),

  // Generation proxies (additional)
  generateSceneActions: (data: {
    scene: { id: string; type: string; title: string; content: MAICScene['content'] };
    agents: MAICAgent[];
    language: string;
  }) =>
    api.post<{ actions: MAICAction[] }>('/v1/teacher/maic/generate/scene-actions/', data),

  generateAgentProfiles: (data: {
    topic: string;
    agentCount: number;
    language: string;
    existingAgents?: MAICAgent[];
  }) =>
    api.post<{ agents: MAICAgent[] }>('/v1/teacher/maic/generate/agent-profiles/', data),
};

// ─── MAIC AI Classroom API (Student) ─────────────────────────────────────────

export const maicStudentApi = {
  listClassrooms: (params?: { course_id?: string; search?: string }) =>
    api.get<MAICClassroomMeta[]>('/v1/student/maic/classrooms/', { params }),

  getClassroom: (id: string) =>
    api.get<MAICClassroomMeta>(`/v1/student/maic/classrooms/${id}/`),

  // Quiz grading (student)
  quizGrade: (data: { question: string; answer: string; commentPrompt?: string }) =>
    api.post('/v1/student/maic/quiz-grade/', data),
};

// ─── AI Chatbot API (Teacher) ─────────────────────────────────────────

export const chatbotApi = {
  list: () =>
    api.get<AIChatbot[]>('/v1/teacher/chatbots/'),

  create: (data: AIChatbotCreatePayload) =>
    api.post<AIChatbot>('/v1/teacher/chatbots/', data),

  detail: (id: string) =>
    api.get<AIChatbot>(`/v1/teacher/chatbots/${id}/`),

  update: (id: string, data: Partial<AIChatbotCreatePayload>) =>
    api.patch<AIChatbot>(`/v1/teacher/chatbots/${id}/`, data),

  delete: (id: string) =>
    api.delete(`/v1/teacher/chatbots/${id}/`),

  // Knowledge
  listKnowledge: (chatbotId: string) =>
    api.get<AIChatbotKnowledge[]>(`/v1/teacher/chatbots/${chatbotId}/knowledge/`),

  uploadKnowledge: (chatbotId: string, formData: FormData) =>
    api.post<AIChatbotKnowledge>(`/v1/teacher/chatbots/${chatbotId}/knowledge/`, formData),

  deleteKnowledge: (chatbotId: string, knowledgeId: string) =>
    api.delete(`/v1/teacher/chatbots/${chatbotId}/knowledge/${knowledgeId}/`),

  // Conversations
  listConversations: (chatbotId: string) =>
    api.get<Conversation[]>(`/v1/teacher/chatbots/${chatbotId}/conversations/`),

  getConversation: (chatbotId: string, convId: string) =>
    api.get<Conversation>(`/v1/teacher/chatbots/${chatbotId}/conversations/${convId}/`),

  // Analytics
  analytics: (chatbotId: string) =>
    api.get(`/v1/teacher/chatbots/${chatbotId}/analytics/`),
};

// ─── AI Chatbot API (Student) ─────────────────────────────────────────

export const chatbotStudentApi = {
  list: () =>
    api.get<AIChatbot[]>('/v1/student/chatbots/'),

  conversations: (chatbotId: string) =>
    api.get<Conversation[]>(`/v1/student/chatbots/${chatbotId}/conversations/`),

  createConversation: (chatbotId: string) =>
    api.post<Conversation>(`/v1/student/chatbots/${chatbotId}/conversations/`),

  getConversation: (chatbotId: string, convId: string) =>
    api.get<Conversation>(`/v1/student/chatbots/${chatbotId}/conversations/${convId}/`),
};
