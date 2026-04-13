// src/types/chatbot.ts
// TypeScript interfaces for AI Chatbot Builder feature.

export type PersonaPreset =
  | 'study_buddy'
  | 'quiz_master'
  | 'concept_explainer'
  | 'homework_helper'
  | 'revision_coach'
  | 'custom';

export type EmbeddingStatus = 'pending' | 'processing' | 'ready' | 'failed';

export type KnowledgeSourceType = 'pdf' | 'text' | 'url' | 'document';

export interface SectionBrief {
  id: string;
  name: string;
  grade_name: string;
  grade_short_code: string;
}

export interface TeacherSection extends SectionBrief {
  academic_year: string;
}

export interface AIChatbot {
  id: string;
  name: string;
  avatar_url: string;
  persona_preset: PersonaPreset;
  persona_description: string;
  custom_rules: string;
  block_off_topic: boolean;
  welcome_message: string;
  is_active: boolean;
  knowledge_count: number;
  conversation_count: number;
  sections: SectionBrief[];
  created_at: string;
  updated_at: string;
}

export interface AIChatbotCreatePayload {
  name: string;
  avatar_url?: string;
  persona_preset: PersonaPreset;
  persona_description?: string;
  custom_rules?: string;
  block_off_topic?: boolean;
  welcome_message?: string;
  section_ids?: string[];
}

export interface AIChatbotKnowledge {
  id: string;
  source_type: KnowledgeSourceType;
  title: string;
  filename: string;
  chunk_count: number;
  total_token_count: number;
  embedding_status: EmbeddingStatus;
  error_message: string;
  is_auto: boolean;
  content_source_title: string | null;
  created_at: string;
  updated_at: string;
}

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: number;
  sources?: Array<{
    title: string;
    page?: number | null;
    heading?: string;
    snippet?: string;
    is_auto?: boolean;
  }>;
}

export interface Conversation {
  id: string;
  chatbot: string;
  title: string;
  student_name?: string;
  messages: ChatMessage[];
  message_count: number;
  is_flagged: boolean;
  flag_reason?: string;
  started_at: string;
  last_message_at: string;
}

export interface ConversationListItem {
  id: string;
  title: string;
  student_name?: string;
  message_count: number;
  is_flagged: boolean;
  started_at: string;
  last_message_at: string;
}

export interface ChatSSEEvent {
  type: 'content' | 'sources' | 'done' | 'error';
  content?: string;
  sources?: Array<{
    title: string;
    page?: number | null;
    heading?: string;
    snippet?: string;
    is_auto?: boolean;
  }>;
  error?: string;
  conversation_id?: string;
}

export interface ChatbotAnalytics {
  total_conversations: number;
  total_messages: number;
  unique_students: number;
  flagged_count: number;
}
