// src/components/maic/slide-editor/useEditorState.ts
//
// React hook managing slide editor state via useReducer.

import { useReducer, useCallback } from 'react';
import type { EditorState, EditorAction, ResizeHandle, AlignmentGuide } from './types';

const initialEditorState: EditorState = {
  selectedElementId: null,
  hoveredElementId: null,
  isDragging: false,
  isResizing: false,
  isRotating: false,
  resizeHandle: null,
  dragStart: null,
  snapGuides: [],
  showGrid: false,
  gridSize: 50,
  zoom: 1,
};

function editorReducer(state: EditorState, action: EditorAction): EditorState {
  switch (action.type) {
    case 'SELECT_ELEMENT':
      return { ...state, selectedElementId: action.elementId };
    case 'HOVER_ELEMENT':
      return { ...state, hoveredElementId: action.elementId };
    case 'START_DRAG':
      return { ...state, isDragging: true, dragStart: { x: action.x, y: action.y } };
    case 'END_DRAG':
      return { ...state, isDragging: false, dragStart: null };
    case 'START_RESIZE':
      return { ...state, isResizing: true, resizeHandle: action.handle };
    case 'END_RESIZE':
      return { ...state, isResizing: false, resizeHandle: null };
    case 'START_ROTATE':
      return { ...state, isRotating: true };
    case 'END_ROTATE':
      return { ...state, isRotating: false };
    case 'TOGGLE_GRID':
      return { ...state, showGrid: !state.showGrid };
    case 'SET_ZOOM':
      return { ...state, zoom: Math.max(0.5, Math.min(2, action.zoom)) };
    case 'SET_SNAP_GUIDES':
      return { ...state, snapGuides: action.guides };
    default:
      return state;
  }
}

export function useEditorState() {
  const [state, dispatch] = useReducer(editorReducer, initialEditorState);

  const selectElement = useCallback(
    (id: string | null) => dispatch({ type: 'SELECT_ELEMENT', elementId: id }),
    [],
  );
  const hoverElement = useCallback(
    (id: string | null) => dispatch({ type: 'HOVER_ELEMENT', elementId: id }),
    [],
  );
  const startDrag = useCallback(
    (x: number, y: number) => dispatch({ type: 'START_DRAG', x, y }),
    [],
  );
  const endDrag = useCallback(() => dispatch({ type: 'END_DRAG' }), []);
  const startResize = useCallback(
    (handle: ResizeHandle['position']) => dispatch({ type: 'START_RESIZE', handle }),
    [],
  );
  const endResize = useCallback(() => dispatch({ type: 'END_RESIZE' }), []);
  const startRotate = useCallback(() => dispatch({ type: 'START_ROTATE' }), []);
  const endRotate = useCallback(() => dispatch({ type: 'END_ROTATE' }), []);
  const toggleGrid = useCallback(() => dispatch({ type: 'TOGGLE_GRID' }), []);
  const setZoom = useCallback(
    (zoom: number) => dispatch({ type: 'SET_ZOOM', zoom }),
    [],
  );
  const setSnapGuides = useCallback(
    (guides: AlignmentGuide[]) => dispatch({ type: 'SET_SNAP_GUIDES', guides }),
    [],
  );

  return {
    ...state,
    dispatch,
    selectElement,
    hoverElement,
    startDrag,
    endDrag,
    startResize,
    endResize,
    startRotate,
    endRotate,
    toggleGrid,
    setZoom,
    setSnapGuides,
  };
}
