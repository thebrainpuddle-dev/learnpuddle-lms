// src/components/maic/slide-editor/types.ts
//
// Editor type definitions for the slide editor component suite.

export interface ElementBounds {
  x: number;
  y: number;
  width: number;
  height: number;
  rotation?: number;
}

export interface ResizeHandle {
  position:
    | 'top-left'
    | 'top-center'
    | 'top-right'
    | 'middle-left'
    | 'middle-right'
    | 'bottom-left'
    | 'bottom-center'
    | 'bottom-right';
  cursor: string;
}

export interface AlignmentGuide {
  type: 'horizontal' | 'vertical';
  position: number; // pixels in design space
  label?: string;
}

export interface EditorState {
  selectedElementId: string | null;
  hoveredElementId: string | null;
  isDragging: boolean;
  isResizing: boolean;
  isRotating: boolean;
  resizeHandle: ResizeHandle['position'] | null;
  dragStart: { x: number; y: number } | null;
  snapGuides: AlignmentGuide[];
  showGrid: boolean;
  gridSize: number; // pixels
  zoom: number;
}

export type EditorAction =
  | { type: 'SELECT_ELEMENT'; elementId: string | null }
  | { type: 'HOVER_ELEMENT'; elementId: string | null }
  | { type: 'START_DRAG'; x: number; y: number }
  | { type: 'END_DRAG' }
  | { type: 'START_RESIZE'; handle: ResizeHandle['position'] }
  | { type: 'END_RESIZE' }
  | { type: 'START_ROTATE' }
  | { type: 'END_ROTATE' }
  | { type: 'TOGGLE_GRID' }
  | { type: 'SET_ZOOM'; zoom: number }
  | { type: 'SET_SNAP_GUIDES'; guides: AlignmentGuide[] };
