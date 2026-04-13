// src/types/chatbot.ts
// TypeScript interfaces for AI Chatbot Builder feature.

export type PersonaPreset = 'tutor' | 'reference' | 'open';

export type EmbeddingStatus = 'pending' | 'processing' | 'ready' | 'failed';

export type KnowledgeSourceType = 'pdf' | 'text' | 'url' | 'document';

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
  created_at: string;
  updated_at: string;
}

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: number;
  sources?: Array<{ title: string; page?: number | null }>;
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
  sources?: Array<{ title: string; page?: number | null }>;
  error?: string;
  conversation_id?: string;
}

export interface ChatbotAnalytics {
  total_conversations: number;
  total_messages: number;
  unique_students: number;
  flagged_count: number;
}
