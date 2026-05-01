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
  /** Estimated speech duration in ms, stamped by the backend so the
   *  playback engine can drive slide transitions and reading-fallback
   *  timers without waiting for audio metadata. */
  durationMs?: number;
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
  /** Whether the engine should auto-open the roundtable panel on this
   *  action. Defaults to 'manual' — teacher must click a Roundtable
   *  button to open. Generated classrooms from prompt v2 (Chunk 3) stamp
   *  this explicitly; legacy classrooms with the field missing are
   *  treated as manual. */
  triggerMode?: 'auto' | 'manual';
}

// ─── LLM-generated utility actions ─────────────────────────────────────────

export interface HighlightAction {
  type: 'highlight';
  elementId: string;
  color?: string;
  duration?: number;
}

/**
 * @deprecated F7 (2026-04-28, wave 3): the engine no-ops this action.
 * Kept in the union so existing classrooms with stored `{type:"pause"}`
 * actions still deserialize and match the dispatch switch (no "unknown
 * action" warnings). The backend prompt directive that emits these
 * actions is queued for removal in a follow-up; once removed and any
 * cached scenes regenerated, this type can be deleted.
 */
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

/**
 * Line-level code edit on an existing `wb_draw_code` element. Lets an
 * agent "type code live" over the course of a scene: seed an empty or
 * placeholder code block, then emit a sequence of `wb_edit_code` actions
 * that insert_after / replace_lines / delete_lines. Porting P2.2.
 */
export interface WbEditCodeAction {
  type: 'wb_edit_code';
  /** ID of the target `wb_draw_code` element (must have been drawn earlier
   *  in the same scene's action list). */
  targetId: string;
  operation: 'insert_after' | 'replace_lines' | 'delete_lines';
  /** 0-based line number. For insert_after, the new content is inserted
   *  AFTER this line. For replace_lines / delete_lines, this is the
   *  starting line (inclusive). */
  lineStart: number;
  /** Inclusive end line for replace_lines / delete_lines. Ignored for
   *  insert_after. Defaults to `lineStart` if omitted. */
  lineEnd?: number;
  /** New content for insert_after / replace_lines. Each element is one
   *  line. Ignored for delete_lines. */
  content?: string[];
}

/**
 * Code block on the whiteboard. Rendered as a monospace block with
 * syntax-highlightable lines — the target of subsequent `wb_edit_code`
 * actions. Separate from `wb_draw_text` because the code block tracks
 * individual lines for edit ops. Porting P2.2.
 */
export interface WbDrawCodeAction {
  type: 'wb_draw_code';
  id: string;
  left: number;
  top: number;
  width: number;
  height?: number;
  /** Initial lines of code. Can be empty to seed a block the agent will
   *  fill with subsequent `wb_edit_code` actions. */
  lines: string[];
  language?: string;
  fontSize?: number;
  color?: string;
}

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
  | WbDrawCodeAction
  | WbEditCodeAction
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
