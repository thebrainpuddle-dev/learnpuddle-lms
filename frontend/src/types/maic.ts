// types/maic.ts — OpenMAIC AI Classroom type definitions

import type { MAICScene, AudioManifest } from './maic-scenes';

// ─── Slide Types ──────────────────────────────────────────────────────────

/** Slide transition animation mode */
export type MAICSlideTransition = 'none' | 'fade' | 'slideLeft' | 'slideRight' | 'slideUp' | 'slideDown' | 'zoom' | 'flip';

export interface MAICSlideElement {
  type: 'text' | 'image' | 'shape' | 'chart' | 'latex' | 'code' | 'table' | 'video';
  id: string;
  x: number;
  y: number;
  width: number;
  height: number;
  content: string;
  /** Image source URL — used when type is 'image' */
  src?: string;
  style?: Record<string, string | number>;
  /** Optional bag for element-level backend signals. Image elements
   *  carry `imageProviderDisabled: true` when the tenant has opted
   *  out of AI image generation — the renderer uses this to show an
   *  honest placeholder instead of falling back to random stock photos. */
  meta?: {
    imageProviderDisabled?: boolean;
    [k: string]: unknown;
  };
}

export interface MAICSlide {
  id: string;
  title: string;
  elements: MAICSlideElement[];
  background?: string;
  notes?: string;
  speakerScript?: string;
  audioUrl?: string;
  duration?: number;
  transition?: MAICSlideTransition;
}

// ─── Agent Types ──────────────────────────────────────────────────────────

export interface MAICAgent {
  id: string;
  name: string;
  role: 'professor' | 'student' | 'assistant' | 'moderator' | 'teaching_assistant' | 'student_rep';
  avatar: string;
  color: string;
  personality?: string;
  expertise?: string;
  /**
   * Azure en-IN neural voice ID (e.g. "en-IN-PrabhatNeural").
   * Optional until the wizard (Chunk 3) populates it on every new agent.
   */
  voiceId?: string;
  /** TTS provider. Only "azure" today; kept for future-proofing. */
  voiceProvider?: 'azure';
  /** 1-2 sentence description of the agent's delivery style. */
  speakingStyle?: string;
  /**
   * Backward-compat alias for voiceId. Older content may have set `voice`
   * before the wizard was added; kept optional/readable so legacy payloads
   * still parse.
   */
  voice?: string;
}

// ─── Classroom Content ─────────────────────────────────────────────────────

/**
 * The shape of the `content` JSONField on MAICClassroom. Contains the entire
 * playable classroom payload: agents, scenes, and (once the pre-gen pipeline
 * lands) an audio manifest describing the state of cached TTS clips.
 */
export interface MAICContent {
  agents: MAICAgent[];
  scenes: MAICScene[];
  /** Present only after the publish pipeline has run; optional for drafts. */
  audioManifest?: AudioManifest;
}

// ─── Outline Types ────────────────────────────────────────────────────────

export interface MAICOutlineScene {
  id: string;
  title: string;
  description: string;
  type: 'introduction' | 'lecture' | 'discussion' | 'quiz' | 'activity' | 'summary';
  estimatedMinutes: number;
  agentIds: string[];
  /** Number of slides for this scene (1 for legacy, 5-8 for multi-slide). Defaults to 1. */
  slideCount?: number;
}

export interface MAICOutline {
  topic: string;
  scenes: MAICOutlineScene[];
  agents: MAICAgent[];
  language: string;
  totalMinutes: number;
}

// ─── Chat Types ───────────────────────────────────────────────────────────

export interface MAICChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  agentId?: string;
  agentName?: string;
  content: string;
  timestamp: number;
  sceneId?: string;
}

// ─── SSE Event Types ──────────────────────────────────────────────────────

export type MAICSSEEventType =
  | 'outline'
  | 'scene_content'
  | 'chat_message'
  | 'agent_speaking'
  | 'agent_thinking'
  | 'slide_update'
  | 'generation_progress'
  | 'generation_complete'
  | 'error'
  | 'done';

export interface MAICSSEEvent {
  type: MAICSSEEventType;
  data: unknown;
  sceneId?: string;
  agentId?: string;
}

// ─── Classroom Metadata ──────────────────────────────────────────────────

export interface MAICAssignedSection {
  id: string;
  name: string;
  grade_name: string | null;
}

export interface MAICClassroomMeta {
  id: string;
  title: string;
  description: string;
  topic: string;
  status: 'DRAFT' | 'GENERATING' | 'READY' | 'FAILED' | 'ARCHIVED';
  is_public: boolean;
  scene_count: number;
  estimated_minutes: number;
  course_id: string | null;
  assigned_sections?: MAICAssignedSection[];
  error_message?: string;
  language?: string;
  config?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

// ─── Whiteboard Types ─────────────────────────────────────────────────────

export type WhiteboardToolType = 'pen' | 'highlighter' | 'eraser' | 'pointer' | 'text' | 'shape';

export interface WhiteboardPoint {
  x: number;
  y: number;
  pressure?: number;
}

export interface WhiteboardMeta {
  // Text
  text?: string;
  html?: string;
  // Shape
  shape?: 'rectangle' | 'circle' | 'triangle';
  fill?: string;
  stroke?: string;
  // Chart
  chartType?: 'bar' | 'line' | 'pie' | 'scatter' | 'area' | 'radar';
  data?: Record<string, unknown>;
  // LaTeX
  latex?: string;
  // Table
  headers?: string[];
  rows?: string[][];
  // Dimensions (shared)
  width?: number;
  height?: number;
  fontSize?: number;
  // Line markers
  startMarker?: 'arrow' | 'dot' | 'none';
  endMarker?: 'arrow' | 'dot' | 'none';
}

export interface WhiteboardAnnotation {
  id: string;
  tool: WhiteboardToolType;
  points: WhiteboardPoint[];
  color: string;
  strokeWidth: number;
  agentId?: string;
  sceneId: string;
  timestamp: number;
  meta?: WhiteboardMeta;
}

// ─── Quiz Types ───────────────────────────────────────────────────────────

export interface MAICQuizOption {
  id: string;
  text: string;
  isCorrect?: boolean;
}

export interface MAICQuizQuestion {
  id: string;
  question: string;
  options: MAICQuizOption[];
  explanation?: string;
  type: 'multiple_choice' | 'true_false';
}

// ─── Generation Config ────────────────────────────────────────────────────

export interface MAICGenerationConfig {
  topic: string;
  pdfText?: string;
  language: string;
  agentCount: number;
  sceneCount: number;
  enableTTS: boolean;
  enableImages: boolean;
  /** When true, the backend enriches the outline generation with web-search
   *  context (OpenMAIC-style grounding). Default ON in the wizard. */
  enableWebSearch?: boolean;
  courseId?: string;
}

// ─── View Mode ────────────────────────────────────────────────────────────

export type MAICViewMode = 'slides' | 'whiteboard' | 'split';
export type MAICPlayerRole = 'teacher' | 'student';
