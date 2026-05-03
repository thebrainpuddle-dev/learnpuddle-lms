/**
 * Action types — frontend mirror of the backend Pydantic action protocol.
 *
 * Source (truth):
 *   /Volumes/CrucialX9/OpenMAIC/lib/types/action.ts (286 lines)
 *   backend/apps/maic/protocol/actions.py (our port)
 *
 * Hand-mirrored discriminated-union shapes — tested for shape against
 * a backend-emitted JSON sample in __tests__/action-types.test.ts.
 * Phase 4 generation pipeline may swap this for a JSON-Schema-codegen
 * artifact derived from `apps.maic.protocol.export_json_schema()`; for
 * Phase 1 hand-mirror is simpler and the shapes are stable.
 *
 * Whiteboard coordinate space is 1000 × 562 (16:9). Same constraint
 * as backend.
 */


// ── Common base ───────────────────────────────────────────────────


interface ActionBase {
  /** Unique action ID within the scene. */
  id: string;
  title?: string;
  description?: string;
}


// ── Fire-and-forget overlays (slide-only) ─────────────────────────


export interface SpotlightAction extends ActionBase {
  type: 'spotlight';
  elementId: string;
  /** 0..1 dim opacity for non-target elements. Default 0.5. */
  dimOpacity?: number;
}

export interface LaserAction extends ActionBase {
  type: 'laser';
  elementId: string;
  /** CSS color string. Default '#ff0000'. */
  color?: string;
}


// ── Speech ────────────────────────────────────────────────────────


export interface SpeechAction extends ActionBase {
  type: 'speech';
  text: string;
  audioId?: string;
  /** Server-generated TTS audio URL (Phase 5+ may populate this). */
  audioUrl?: string;
  voice?: string;
  /** Default 1.0. */
  speed?: number;
}


// ── Whiteboard (Phase 2 renders these) ────────────────────────────


export interface WbOpenAction extends ActionBase {
  type: 'wb_open';
}

export interface WbCloseAction extends ActionBase {
  type: 'wb_close';
}

export interface WbClearAction extends ActionBase {
  type: 'wb_clear';
}

export interface WbDeleteAction extends ActionBase {
  type: 'wb_delete';
  elementId: string;
}

export interface WbDrawTextAction extends ActionBase {
  type: 'wb_draw_text';
  elementId?: string;
  /** HTML or plain text. */
  content: string;
  x: number;
  y: number;
  width?: number;
  height?: number;
  fontSize?: number;
  color?: string;
}

export interface WbDrawShapeAction extends ActionBase {
  type: 'wb_draw_shape';
  elementId?: string;
  shape: 'rectangle' | 'circle' | 'triangle';
  x: number;
  y: number;
  width: number;
  height: number;
  fillColor?: string;
}

export interface WbDrawChartAction extends ActionBase {
  type: 'wb_draw_chart';
  elementId?: string;
  chartType: 'bar' | 'column' | 'line' | 'pie' | 'ring' | 'area' | 'radar' | 'scatter';
  x: number;
  y: number;
  width: number;
  height: number;
  data: {
    labels: string[];
    legends: string[];
    series: number[][];
  };
  themeColors?: string[];
}

export interface WbDrawLatexAction extends ActionBase {
  type: 'wb_draw_latex';
  elementId?: string;
  latex: string;
  x: number;
  y: number;
  width?: number;
  height?: number;
  color?: string;
}

export interface WbDrawTableAction extends ActionBase {
  type: 'wb_draw_table';
  elementId?: string;
  x: number;
  y: number;
  width: number;
  height: number;
  /** 2D string array; first row is the header. */
  data: string[][];
  outline?: { width: number; style: string; color: string };
  theme?: { color: string };
}

export interface WbDrawLineAction extends ActionBase {
  type: 'wb_draw_line';
  elementId?: string;
  /** 0..1000 (16:9 frame). */
  startX: number;
  /** 0..562 (16:9 frame). */
  startY: number;
  endX: number;
  endY: number;
  /** Default '#333333'. */
  color?: string;
  /** Line width; default 2. */
  width?: number;
  /** Default 'solid'. */
  style?: 'solid' | 'dashed';
  /** Endpoint markers; default ['', '']. */
  points?: ['' | 'arrow', '' | 'arrow'];
}

export interface WbDrawCodeAction extends ActionBase {
  type: 'wb_draw_code';
  elementId?: string;
  /** lowlight language id. */
  language: string;
  /** Source code; lines separated by `\n`. */
  code: string;
  x: number;
  y: number;
  width?: number;
  height?: number;
  fileName?: string;
}

export interface WbEditCodeAction extends ActionBase {
  type: 'wb_edit_code';
  elementId: string;
  operation: 'insert_after' | 'insert_before' | 'delete_lines' | 'replace_lines';
  lineId?: string;
  lineIds?: string[];
  content?: string;
}


// ── Media ─────────────────────────────────────────────────────────


export interface PlayVideoAction extends ActionBase {
  type: 'play_video';
  elementId: string;
}


// ── Discussion ────────────────────────────────────────────────────


export interface DiscussionAction extends ActionBase {
  type: 'discussion';
  topic: string;
  prompt?: string;
  agentId?: string;
}


// ── Widget interaction (Phase 6 renders these) ────────────────────


export interface WidgetHighlightAction extends ActionBase {
  type: 'widget_highlight';
  /** CSS selector or element ID inside the widget iframe. */
  target: string;
  /** Speech text to accompany the highlight. */
  content?: string;
}

export interface WidgetSetStateAction extends ActionBase {
  type: 'widget_setState';
  state: Record<string, unknown>;
  content?: string;
}

export interface WidgetAnnotationAction extends ActionBase {
  type: 'widget_annotation';
  target: string;
  content?: string;
}

export interface WidgetRevealAction extends ActionBase {
  type: 'widget_reveal';
  target: string;
  content?: string;
}


// ── Discriminated union ───────────────────────────────────────────


export type Action =
  | SpotlightAction
  | LaserAction
  | SpeechAction
  | WbOpenAction
  | WbCloseAction
  | WbClearAction
  | WbDeleteAction
  | WbDrawTextAction
  | WbDrawShapeAction
  | WbDrawChartAction
  | WbDrawLatexAction
  | WbDrawTableAction
  | WbDrawLineAction
  | WbDrawCodeAction
  | WbEditCodeAction
  | PlayVideoAction
  | DiscussionAction
  | WidgetHighlightAction
  | WidgetSetStateAction
  | WidgetAnnotationAction
  | WidgetRevealAction;

export type ActionType = Action['type'];


// ── Categorization (mirror of backend ALL_ACTION_TYPES) ──────────


/** All 21 action types. Sync'd with apps/maic/protocol/actions.py. */
export const ALL_ACTION_TYPES: readonly ActionType[] = [
  'spotlight', 'laser', 'speech',
  'wb_open', 'wb_close', 'wb_clear', 'wb_delete',
  'wb_draw_text', 'wb_draw_shape', 'wb_draw_chart',
  'wb_draw_latex', 'wb_draw_table', 'wb_draw_line',
  'wb_draw_code', 'wb_edit_code',
  'play_video', 'discussion',
  'widget_highlight', 'widget_setState', 'widget_annotation', 'widget_reveal',
] as const;

/** Action types that fire immediately without blocking. */
export const FIRE_AND_FORGET_ACTIONS: readonly ActionType[] = [
  'spotlight', 'laser',
] as const;

/** Action types that only render on slide scenes. */
export const SLIDE_ONLY_ACTIONS: readonly ActionType[] = [
  'spotlight', 'laser',
] as const;
