// src/services/openmaicService.ts
//
// API service for OpenMAIC features: MAIC AI Classroom.

import api from '../config/api';
import type { MAICClassroomMeta, MAICOutlineScene, MAICAgent, MAICSlide } from '../types/maic';
import type { MAICAction } from '../types/maic-actions';
import type { MAICScene, SceneSlideBounds, AudioManifest } from '../types/maic-scenes';
import type { AIChatbot, AIChatbotKnowledge, AIChatbotCreatePayload, ChatbotAnalytics, Conversation, TeacherSection } from '../types/chatbot';

// ─── Shared MAIC types ──────────────────────────────────────────────────────

export interface MAICRoleSlot {
  role: string;
  count: number;
}

export interface GenerateAgentProfilesRequest {
  topic: string;
  language: string;
  /** Preferred: role slot map. The server may also accept an `agentCount` body from older callers. */
  roleSlots?: MAICRoleSlot[];
  /** Legacy single-count request. Kept for callers that don't yet pass `roleSlots`. */
  agentCount?: number;
  existingAgents?: MAICAgent[];
}

export interface GenerateAgentProfilesResponse {
  agents: MAICAgent[];
}

export interface RegenerateAgentRequest {
  topic: string;
  existingAgents: MAICAgent[];
  targetAgentId: string;
  lockedFields: string[];
}

export interface MAICVoice {
  id: string;
  gender: string;
  tone: string;
  age: string;
  suits: string[];
}

export interface MAICGenerationContextPayload {
  grade_level?: string;
  subject?: string;
  syllabus_board?: string;
  audience_role?: 'teacher' | 'student';
  class_guide?: string;
}

export interface MAICV2GenerationRequest {
  topic: string;
  contentTitle?: string;
  agentCount?: number;
  sceneCount?: number;
  language?: string;
  level?: string;
  specifications?: string;
  courseId?: string;
  moduleId?: string;
  isPublic?: boolean;
  gradeLevel?: string;
  subject?: string;
  syllabusBoard?: string;
  classGuide?: string;
  /**
   * Chunk 3a typed pedagogy targets — see backend
   * apps/maic/views_generation.py `_optional_string_list` / `_optional_text`
   * for validation caps. Each field is optional; absent → request behaves
   * identically to origin/main.
   */
  learningObjective?: string;
  misconceptions?: string[];
  successCriteria?: string[];
  pblBrief?: string;
  pdfText?: string;
  researchContext?: string;
  agents?: MAICAgent[];
  enablePBL?: boolean;
  enableImageGeneration?: boolean;
  enableVideoGeneration?: boolean;
}

export interface MAICV2GenerationCreateResponse {
  job_id: string;
  ws_url: string;
  tenant_id: string | number;
}

export interface MAICV2GenerationJobResponse {
  job_id: string;
  status: 'pending' | 'in_progress' | 'succeeded' | 'failed';
  step?: number;
  progress?: {
    stage?: number;
    completed?: number;
    total?: number;
    message?: string;
  };
  message?: string;
  scenesGenerated?: number;
  totalScenes?: number;
  result?: {
    classroomId?: string;
    classroom_id?: string;
    contentId?: string | null;
    content_id?: string | null;
    url?: string;
    scenesCount?: number;
    artifact?: {
      classroomId?: string;
      classroom_id?: string;
      url?: string;
    };
    [key: string]: unknown;
  };
  error?: string | null;
  done: boolean;
  created_at: string;
  updated_at: string;
  completed_at?: string | null;
}

// ─── MAIC AI Classroom API (Teacher) ─────────────────────────────────────────

export const maicApi = {
  // Classroom CRUD
  listClassrooms: (params?: { status?: string; search?: string }) =>
    api.get<MAICClassroomMeta[]>('/v1/teacher/maic/classrooms/', { params }),

  createClassroom: (data: { title: string; description?: string; topic?: string; language?: string; course_id?: string; config?: Record<string, unknown> }) =>
    api.post<{ id: string; title: string; status: string; created_at: string }>('/v1/teacher/maic/classrooms/create/', data),

  getClassroom: (id: string) =>
    api.get<MAICClassroomMeta>(`/v1/teacher/maic/classrooms/${id}/`),

  updateClassroom: (id: string, data: Partial<MAICClassroomMeta> & { assigned_section_ids?: string[]; content?: Record<string, unknown> }) =>
    api.patch(`/v1/teacher/maic/classrooms/${id}/update/`, data),

  deleteClassroom: (id: string) =>
    api.delete(`/v1/teacher/maic/classrooms/${id}/delete/`),

  // Generation proxies (non-SSE)
  // CG-P0-9: classroomId + sceneIdx are passed so the backend image_service
  // has tenant/lesson/scene context — without them `_save_image_to_storage`
  // runs `can_save=False` and Imagen returns a base64 `data:` URL which the
  // frontend's `scrubSlideDataUrls` strips to empty → broken images. Both
  // fields are optional for back-compat with student/preview callers.
  generateSceneContent: (data: {
    scene: MAICOutlineScene;
    agents: MAICAgent[];
    language: string;
    classroomId?: string;
    sceneIdx?: number;
  } & MAICGenerationContextPayload) => api.post('/v1/teacher/maic/generate/scene-content/', data),

  generateImage: (data: { prompt: string; style?: string }) =>
    api.post('/v1/teacher/maic/generate/image/', data),

  generateClassroom: (data: Record<string, unknown>) =>
    api.post('/v1/teacher/maic/generate/classroom/', data),

  generateV2Classroom: (data: MAICV2GenerationRequest) =>
    api.post<MAICV2GenerationCreateResponse>('/maic/v2/generate/', data),

  getV2GenerationJob: (jobId: string, opts?: { full?: boolean }) =>
    api.get<MAICV2GenerationJobResponse>(`/maic/v2/generate/${jobId}/`, {
      params: opts?.full ? { full: '1' } : undefined,
    }),

  // Quiz grading
  quizGrade: (data: { question: string; answer: string; commentPrompt?: string }) =>
    api.post('/v1/teacher/maic/quiz-grade/', data),

  // Export
  exportPptx: (classroomId: string) =>
    api.post('/v1/teacher/maic/export/pptx/', { classroomId }, { responseType: 'blob' }),

  exportHtml: (classroomId: string) =>
    api.post('/v1/teacher/maic/export/html/', { classroomId }, { responseType: 'blob' }),

  // Web search
  webSearch: (query: string, maxResults?: number) =>
    api.post('/v1/teacher/maic/web-search/', { query, max_results: maxResults }),

  // Generation proxies (additional)
  generateSceneActions: (data: {
    scene: { id: string; type: string; title: string; content: MAICScene['content'] };
    agents: MAICAgent[];
    language: string;
    classroomId?: string;
  } & MAICGenerationContextPayload) =>
    api.post<{ actions: MAICAction[] }>('/v1/teacher/maic/generate/scene-actions/', data),

  generateAgentProfiles: (data: GenerateAgentProfilesRequest) =>
    api.post<GenerateAgentProfilesResponse>('/v1/teacher/maic/generate/agent-profiles/', data),

  regenerateAgent: (data: RegenerateAgentRequest) =>
    api.post<{ agent: MAICAgent }>('/v1/teacher/maic/agents/regenerate-one/', data),

  ttsPreview: (data: { voiceId: string; text: string }) =>
    api.post('/v1/teacher/maic/tts/preview/', data, { responseType: 'blob' }),

  listVoices: () =>
    // Backend mounts this under the courses router: apps/courses/urls.py →
    // /api/v1/courses/maic/voices/  (not /api/v1/maic/voices/).
    api.get<{ voices: MAICVoice[] }>('/v1/courses/maic/voices/'),

  publishClassroom: (id: string) =>
    api.post<{ audioManifest: AudioManifest }>(`/v1/teacher/maic/classrooms/${id}/publish/`, {}),

  /** CG-P0-8 — recover a stalled classroom by flipping GENERATING → READY
   *  with whatever scenes were saved by per-scene persistPartial. Used by
   *  the stall-panel "Use what's saved" button on MAICPlayerPage. */
  finalizePartialClassroom: (id: string) =>
    api.post<{
      ok: boolean;
      status: string;
      scenes_ready: number;
      scene_count: number;
      noop?: boolean;
      error?: string;
    }>(`/v1/teacher/maic/classrooms/${id}/finalize-partial/`, {}),

  /** Fire-and-forget progress ping. Server stamps last_progress_at +
   *  optional phase/phase_scene_index/scenes_ready. Callers should
   *  .catch(() => {}) so a failed ping doesn't break generation. */
  pingClassroomProgress: (
    id: string,
    patch: {
      phase?: 'outline' | 'content' | 'actions' | 'saving' | 'complete';
      phase_scene_index?: number;
      scenes_ready?: number;
    },
  ) =>
    api.post<{
      phase: string;
      phase_scene_index: number;
      scenes_ready: number;
      started_at: string | null;
      last_progress_at: string;
    }>(`/v1/teacher/maic/classrooms/${id}/progress/`, patch),

  /** Push full classroom content to backend for student access */
  syncContent: (classroomId: string, content: {
    slides: MAICSlide[];
    scenes: MAICScene[];
    sceneSlideBounds: SceneSlideBounds[];
  }) =>
    api.patch(`/v1/teacher/maic/classrooms/${classroomId}/update/`, { content }),

  /** Chat/orchestration — send message to agent for streaming response */
  chat: (data: {
    classroomId?: string;
    agentId: string;
    messages: Array<{ role: string; content: string }>;
    systemPrompt: string;
    discussionContext?: { topic: string; prompt?: string };
  }) =>
    api.post('/v1/teacher/maic/chat/', data),

  /** Generate TTS audio via the backend proxy */
  generateTTS: (data: {
    text: string;
    providerId: string;
    voice: string;
    speed?: number;
    modelId?: string;
    format?: string;
  }) =>
    api.post('/v1/teacher/maic/generate/tts/', data, { responseType: 'arraybuffer' }),

  /** Transcribe audio via the backend proxy */
  transcribe: (formData: FormData) =>
    api.post('/v1/teacher/maic/transcribe/', formData),

  /** Parse a PDF for text extraction */
  parsePdf: (formData: FormData) =>
    api.post('/v1/teacher/maic/parse-pdf/', formData),
};

// ─── MAIC AI Classroom API (Student) ─────────────────────────────────────────

export const maicStudentApi = {
  // Browse teacher-created public classrooms
  listClassrooms: (params?: { course_id?: string; search?: string }) =>
    api.get<MAICClassroomMeta[]>('/v1/student/maic/classrooms/', { params }),

  getClassroom: (id: string) =>
    api.get<MAICClassroomMeta>(`/v1/student/maic/classrooms/${id}/`),

  // Student's own classrooms
  myClassrooms: () =>
    api.get<MAICClassroomMeta[]>('/v1/student/maic/my-classrooms/'),

  createClassroom: (data: { title: string; description?: string; topic?: string; language?: string; config?: Record<string, unknown> }) =>
    api.post<{ id: string; title: string; status: string; created_at: string }>('/v1/student/maic/classrooms/create/', data),

  updateClassroom: (id: string, data: Partial<MAICClassroomMeta> & { content?: Record<string, unknown> }) =>
    api.patch(`/v1/student/maic/classrooms/${id}/update/`, data),

  deleteClassroom: (id: string) =>
    api.delete(`/v1/student/maic/classrooms/${id}/delete/`),

  // Topic validation (guardrail check)
  validateTopic: (data: { topic?: string; pdfText?: string }) =>
    api.post<{ allowed: boolean; is_educational: boolean; subject_area: string; confidence: number; reason: string }>('/v1/student/maic/validate-topic/', data),

  generateV2Classroom: (data: MAICV2GenerationRequest) =>
    api.post<MAICV2GenerationCreateResponse>('/maic/v2/generate/', data),

  getV2GenerationJob: (jobId: string, opts?: { full?: boolean }) =>
    api.get<MAICV2GenerationJobResponse>(`/maic/v2/generate/${jobId}/`, {
      params: opts?.full ? { full: '1' } : undefined,
    }),

  // Generation proxies (with guardrails)
  generateSceneContent: (data: { scene: MAICOutlineScene; agents: MAICAgent[]; language: string }) =>
    api.post('/v1/student/maic/generate/scene-content/', data),

  generateSceneActions: (data: {
    scene: { id: string; type: string; title: string; content: MAICScene['content'] };
    agents: MAICAgent[];
    language: string;
  }) =>
    api.post<{ actions: MAICAction[] }>('/v1/student/maic/generate/scene-actions/', data),

  generateAgentProfiles: (data: GenerateAgentProfilesRequest) =>
    api.post<GenerateAgentProfilesResponse>('/v1/student/maic/generate/agent-profiles/', data),

  regenerateAgent: (data: RegenerateAgentRequest) =>
    api.post<{ agent: MAICAgent }>('/v1/student/maic/agents/regenerate-one/', data),

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

  clone: (id: string) =>
    api.post<AIChatbot>(`/v1/teacher/chatbots/${id}/clone/`),

  refreshSources: (id: string) =>
    api.post(`/v1/teacher/chatbots/${id}/refresh-sources/`),

  // Sections
  mySections: () =>
    api.get<TeacherSection[]>('/v1/teacher/chatbots/my-sections/'),

  // Knowledge
  listKnowledge: (chatbotId: string) =>
    api.get<AIChatbotKnowledge[]>(`/v1/teacher/chatbots/${chatbotId}/knowledge/`),

  uploadKnowledge: (chatbotId: string, formData: FormData) =>
    api.post<AIChatbotKnowledge>(`/v1/teacher/chatbots/${chatbotId}/knowledge/`, formData),

  addKnowledgeUrl: (chatbotId: string, data: { source_type: 'url'; url: string; title: string }) =>
    api.post<AIChatbotKnowledge>(`/v1/teacher/chatbots/${chatbotId}/knowledge/`, data),

  deleteKnowledge: (chatbotId: string, knowledgeId: string) =>
    api.delete(`/v1/teacher/chatbots/${chatbotId}/knowledge/${knowledgeId}/`),

  // Conversations
  listConversations: (chatbotId: string) =>
    api.get<Conversation[]>(`/v1/teacher/chatbots/${chatbotId}/conversations/`),

  getConversation: (chatbotId: string, convId: string) =>
    api.get<Conversation>(`/v1/teacher/chatbots/${chatbotId}/conversations/${convId}/`),

  // Analytics
  analytics: (chatbotId: string) =>
    api.get<ChatbotAnalytics>(`/v1/teacher/chatbots/${chatbotId}/analytics/`),
};

// ─── AI Chatbot API (Student) ─────────────────────────────────────────

export const chatbotStudentApi = {
  list: () =>
    api.get<AIChatbot[]>('/v1/student/chatbots/'),

  detail: (chatbotId: string) =>
    api.get<AIChatbot>(`/v1/student/chatbots/${chatbotId}/`),

  conversations: (chatbotId: string) =>
    api.get<Conversation[]>(`/v1/student/chatbots/${chatbotId}/conversations/`),

  createConversation: (chatbotId: string) =>
    api.post<Conversation>(`/v1/student/chatbots/${chatbotId}/conversations/`),

  getConversation: (chatbotId: string, convId: string) =>
    api.get<Conversation>(`/v1/student/chatbots/${chatbotId}/conversations/${convId}/`),
};
