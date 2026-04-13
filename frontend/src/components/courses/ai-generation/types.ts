// src/components/courses/ai-generation/types.ts
//
// Shared types for the AI generation panel and its sub-steps.

// ── Generator State ──────────────────────────────────────────────────────────

export type GeneratorState =
  | 'idle'
  | 'parsing'
  | 'generating-outline'
  | 'outline-ready'
  | 'generating-content'
  | 'content-ready'
  | 'lesson-config'
  | 'lesson-generating'
  | 'lesson-preview';

// ── Content Type ─────────────────────────────────────────────────────────────

export type ContentType = 'lesson' | 'quiz' | 'assignment' | 'summary';

// ── Component Props ──────────────────────────────────────────────────────────

export interface AIGenerationPanelProps {
  courseId: string;
  modules: Array<{ id: string; title: string; order: number }>;
  onContentAdded: () => void;
}

// ── Outline Section ──────────────────────────────────────────────────────────

export interface OutlineSection {
  id: string;
  title: string;
  description: string;
  learningObjectives: string;
  keyPoints: string[];
  selectedTypes: Set<ContentType>;
}

// ── Generated Items ──────────────────────────────────────────────────────────

export interface GeneratedItem {
  id: string;
  sectionIndex: number;
  type: ContentType;
  title: string;
  content: string;
  questions?: GeneratedQuestion[];
  instructions?: string;
  rubric?: string;
  status: 'pending' | 'generating' | 'done' | 'failed';
  added: boolean;
  error?: string;
}

export interface GeneratedQuestion {
  prompt: string;
  options: string[];
  correctIndex: number;
  explanation?: string;
}

// ── Section Progress ─────────────────────────────────────────────────────────

export interface SectionProgress {
  sectionTitle: string;
  status: 'pending' | 'generating' | 'done' | 'failed';
}

// ── Constants ────────────────────────────────────────────────────────────────

export const ALL_CONTENT_TYPES: ContentType[] = ['lesson', 'quiz', 'assignment', 'summary'];
