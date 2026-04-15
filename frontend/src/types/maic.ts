// types/maic.ts — OpenMAIC AI Classroom type definitions

// ─── Slide Types ──────────────────────────────────────────────────────────

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
}

// ─── Agent Types ──────────────────────────────────────────────────────────

export interface MAICAgent {
  id: string;
  name: string;
  role: 'professor' | 'student' | 'assistant' | 'moderator' | 'teaching_assistant' | 'student_rep';
  avatar: string;
  color: string;
  voice?: string;
  personality?: string;
  expertise?: string;
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

export interface WhiteboardAnnotation {
  id: string;
  tool: WhiteboardToolType;
  points: WhiteboardPoint[];
  color: string;
  strokeWidth: number;
  agentId?: string;
  sceneId: string;
  timestamp: number;
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
  courseId?: string;
}

// ─── View Mode ────────────────────────────────────────────────────────────

export type MAICViewMode = 'slides' | 'whiteboard' | 'split';
export type MAICPlayerRole = 'teacher' | 'student';
