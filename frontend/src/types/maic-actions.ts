// types/maic-actions.ts — Action types that drive MAIC classroom playback

// ─── Fire-and-Forget Visual Effects ─────────────────────────────────────────

export interface SpotlightAction {
  type: 'spotlight';
  elementId: string;
  duration?: number;
  radius?: number;
  dimness?: number;
}

export interface LaserAction {
  type: 'laser';
  /** Target element ID — used for element-based laser pointer */
  elementId: string;
  /** Absolute x coordinate for free-position laser (0-100 percentage) */
  x?: number;
  /** Absolute y coordinate for free-position laser (0-100 percentage) */
  y?: number;
  color?: string;
  duration?: number;
}

// ─── Speech ─────────────────────────────────────────────────────────────────

export interface SpeechAction {
  type: 'speech';
  agentId: string;
  text: string;
  ssml?: string;
  // Stamped at publish time by the pre-gen pipeline (Chunk 4). All optional
  // until the backend starts emitting them; the playback engine falls back
  // to live TTS when these are absent.
  audioId?: string;
  audioUrl?: string;
  voiceId?: string;
}

// ─── Video ──────────────────────────────────────────────────────────────────

export interface PlayVideoAction {
  type: 'play_video';
  elementId: string;
}

// ─── Whiteboard Actions ─────────────────────────────────────────────────────

export interface WbOpenAction {
  type: 'wb_open';
}

export interface WbCloseAction {
  type: 'wb_close';
}

export interface WbClearAction {
  type: 'wb_clear';
}

export interface WbDrawTextAction {
  type: 'wb_draw_text';
  id: string;
  text: string;
  html?: string;
  left: number;
  top: number;
  width: number;
  height?: number;
  fontSize?: number;
  color?: string;
}

export interface WbDrawShapeAction {
  type: 'wb_draw_shape';
  id: string;
  shape: 'rectangle' | 'circle' | 'triangle';
  left: number;
  top: number;
  width: number;
  height: number;
  fill?: string;
  stroke?: string;
  strokeWidth?: number;
}

export interface WbDrawChartAction {
  type: 'wb_draw_chart';
  id: string;
  chartType: 'bar' | 'line' | 'pie' | 'scatter' | 'area' | 'radar';
  data: Record<string, unknown>;
  left: number;
  top: number;
  width: number;
  height: number;
}

export interface WbDrawLatexAction {
  type: 'wb_draw_latex';
  id: string;
  latex: string;
  left: number;
  top: number;
  width: number;
  height?: number;
  fontSize?: number;
}

export interface WbDrawTableAction {
  type: 'wb_draw_table';
  id: string;
  headers: string[];
  rows: string[][];
  left: number;
  top: number;
  width: number;
  height?: number;
}

export interface WbDrawLineAction {
  type: 'wb_draw_line';
  id: string;
  start: [number, number];
  end: [number, number];
  color?: string;
  width?: number;
  startMarker?: 'arrow' | 'dot' | 'none';
  endMarker?: 'arrow' | 'dot' | 'none';
}

export interface WbDeleteAction {
  type: 'wb_delete';
  elementId: string;
}

// ─── Discussion ─────────────────────────────────────────────────────────────

export interface DiscussionAction {
  type: 'discussion';
  sessionType: 'qa' | 'roundtable' | 'classroom';
  topic: string;
  agentIds: string[];
}

// ─── LLM-generated utility actions ─────────────────────────────────────────

export interface HighlightAction {
  type: 'highlight';
  elementId: string;
  color?: string;
  duration?: number;
}

export interface PauseAction {
  type: 'pause';
  duration: number;
}

export interface TransitionAction {
  type: 'transition';
  effect?: 'fade' | 'slide';
  duration?: number;
  /** Target slide index within the current scene (0-based). Used for multi-slide navigation. */
  slideIndex?: number;
}

// ─── Union Type ─────────────────────────────────────────────────────────────

export type MAICAction =
  | SpotlightAction
  | LaserAction
  | SpeechAction
  | PlayVideoAction
  | WbOpenAction
  | WbCloseAction
  | WbClearAction
  | WbDrawTextAction
  | WbDrawShapeAction
  | WbDrawChartAction
  | WbDrawLatexAction
  | WbDrawTableAction
  | WbDrawLineAction
  | WbDeleteAction
  | DiscussionAction
  | HighlightAction
  | PauseAction
  | TransitionAction;

// ─── Type Guards ────────────────────────────────────────────────────────────

export function isWhiteboardAction(action: MAICAction): boolean {
  return action.type.startsWith('wb_');
}

export function isFireAndForget(action: MAICAction): boolean {
  return action.type === 'spotlight' || action.type === 'laser' || action.type === 'highlight';
}
