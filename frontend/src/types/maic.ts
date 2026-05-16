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
   *  honest placeholder. */
  meta?: {
    imageProviderDisabled?: boolean;
    [k: string]: unknown;
  };
}

// ─── F4 (P0): Typed slide schema with role discriminator ──────────────────
//
// The frontend renderer accepts an OPTIONAL `template` discriminator + a
// matching `slots` payload as a forward-compatible alternative to the
// legacy free-form `elements[]` layout. Backward compatibility is the
// safety net: slides emitted WITHOUT `template`/`slots` continue to render
// via the free-form absolute-positioned `elements[]` path UNCHANGED.
//
// Renderer rule (see SlideRenderer.tsx):
//   - if `slide.template === 'body-image-right'` AND `slide.slots` is
//     populated, render via the slot-aware CSS-grid template.
//   - otherwise fall through to the existing `elements[]` renderer.
//
// Backend mirror: `apps/courses/maic_generation_service.py` validator
// accepts the same OPTIONAL fields; LLM prompts may emit the new shape
// but are never required to. Today only `body-image-right` is shipped.

/** Identifier for the slide layout template. `free-form` is implicit and
 *  represented by the absence of `template` (legacy `elements[]` path). */
export type SlideTemplateId = 'body-image-right' | 'free-form';

/** Structured content slots used by template-aware layouts. Each slot is
 *  optional — a template renderer simply omits the corresponding grid row
 *  when its slot is absent. */
export interface SlideSlots {
  /** Top-row title slot. */
  title?: { text: string };
  /** Body slot — short paragraph, bullets, or both. */
  body?: { text?: string; bullets?: string[] };
  /** Image slot — `src` may be empty while the Celery image-fill task is
   *  still running (CG-P0-3); renderer shows the fetching skeleton in that
   *  case and an unavailable placeholder when not pending. */
  image?: { src?: string; alt?: string; meta?: Record<string, unknown> };
  /** Bottom-row footer caption. */
  footer?: { text: string };
}

export interface MAICSlide {
  id: string;
  title: string;
  /** Legacy/free-form rendering canvas. Always present; rendered when no
   *  `template` is set OR when the chosen template doesn't apply. */
  elements: MAICSlideElement[];
  background?: string;
  notes?: string;
  speakerScript?: string;
  audioUrl?: string;
  duration?: number;
  transition?: MAICSlideTransition;
  /** Optional generation-space metadata. V2/OpenMAIC scenes commonly
   *  generate coordinates on a 1000 x 562.5 canvas, while legacy scenes
   *  use 800 x 450. The renderer uses these fields to scale without
   *  clipping content. */
  canvasWidth?: number;
  canvasHeight?: number;
  viewportSize?: number;
  viewportRatio?: number;
  /** F4 (P0): optional layout discriminator. When set to a known template
   *  id AND `slots` is populated, the renderer uses the slot-aware path
   *  instead of `elements[]`. Absent on legacy slides. */
  template?: SlideTemplateId;
  /** F4 (P0): structured content for template-aware layouts. Ignored when
   *  `template` is missing or unknown. */
  slots?: SlideSlots;
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
  type: 'introduction' | 'lecture' | 'discussion' | 'quiz' | 'activity' | 'interactive' | 'summary';
  estimatedMinutes: number;
  agentIds: string[];
  /** Number of slides for this scene (1 for legacy, 5-8 for multi-slide). Defaults to 1. */
  slideCount?: number;
  /** Number of quiz questions for type='quiz' scenes. */
  questionCount?: number;
  /** CG-P0-7: measurable Bloom's-taxonomy objective. The slide-content
   *  LLM uses this to anchor the scene to a committed lesson goal. */
  teachingObjective?: string;
  /** CG-P0-7: 3-5 substantive points the scene MUST cover, committed at
   *  outline time. The slide-content LLM expands these into slides
   *  instead of re-deriving the topic from `title`/`description`. */
  keyPoints?: string[];
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
  /**
   * Set to `true` by the backend when `fill_classroom_images` Celery task
   * has been enqueued but not yet completed (CG-P0-3 async image fill).
   * Flips back to `false` once the task finishes filling all scene image
   * elements.  The FE uses this to:
   *   1. Keep polling even when status is READY (images still loading).
   *   2. Show a "fetching image…" skeleton on slides with empty image src.
   */
  images_pending?: boolean;
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
  // Code block (Porting P2.2 — live code typing)
  code?: boolean;
  codeLines?: string[];
  language?: string;
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
  /** Curated web-search context from the teacher wizard. V2 sends this as
   *  researchContext so the backend keeps it separate from uploaded PDFs. */
  webSearchContext?: string;
  courseId?: string;
  /**
   * FULL-1 — Grade / subject / syllabus board metadata feeding the
   * grade-aware prompt builder in `_extract_generation_context` on the
   * backend (apps/courses/maic_views.py:84-113). All optional; backend
   * falls back to safe defaults (Generic syllabus, no grade hint) when
   * omitted. Sent to the API as snake_case `grade_level`, `subject`,
   * `syllabus_board` — conversion happens at the network boundary.
   */
  gradeLevel?: string;
  subject?: string;
  syllabusBoard?: string;
  /**
   * Teacher-authored preparation guide from Step 2 of the wizard. This is
   * threaded through outline, scene-content, and action prompts so the class
   * plan, misconceptions, checks, PBL/activity moments, and agent handovers
   * stay consistent across the whole generated classroom.
   */
  classGuide?: string;
  /**
   * Chunk 3a typed pedagogy targets — structured equivalents of the things
   * the backend's _teacher_planning_contract already names. These render as
   * a labeled `## Pedagogy Targets` block in the teacher context that feeds
   * outline / scene / PBL prompts, so the LLM honors them concretely rather
   * than only when the teacher happens to restate them in the free-form
   * classGuide blob. All four are optional.
   *
   * Caps mirror the backend: learningObjective ≤500 chars; misconceptions
   * and successCriteria ≤5 items × ≤200 chars each; pblBrief ≤1000.
   */
  learningObjective?: string;
  misconceptions?: string[];
  successCriteria?: string[];
  pblBrief?: string;
}

// ─── View Mode ────────────────────────────────────────────────────────────

export type MAICViewMode = 'slides' | 'whiteboard' | 'split';
export type MAICPlayerRole = 'teacher' | 'student';
