// stores/maicCanvasStore.ts — Whiteboard annotations, drawing tools, undo/redo

import { create } from 'zustand';
import type { WhiteboardAnnotation, WhiteboardToolType } from '../types/maic';

interface MAICCanvasState {
  annotations: WhiteboardAnnotation[];
  activeTool: WhiteboardToolType;
  activeColor: string;
  strokeWidth: number;
  isDrawing: boolean;

  // History for undo/redo
  undoStack: WhiteboardAnnotation[][];
  redoStack: WhiteboardAnnotation[][];

  setTool: (tool: WhiteboardToolType) => void;
  setColor: (color: string) => void;
  setStrokeWidth: (width: number) => void;
  setDrawing: (drawing: boolean) => void;

  addAnnotation: (annotation: WhiteboardAnnotation) => void;
  removeAnnotation: (id: string) => void;
  clearAnnotations: () => void;
  setAnnotations: (annotations: WhiteboardAnnotation[]) => void;

  undo: () => void;
  redo: () => void;
  canUndo: () => boolean;
  canRedo: () => boolean;

  reset: () => void;
}

const initialState = {
  annotations: [] as WhiteboardAnnotation[],
  activeTool: 'pen' as WhiteboardToolType,
  activeColor: '#3B82F6',
  strokeWidth: 2,
  isDrawing: false,
  undoStack: [] as WhiteboardAnnotation[][],
  redoStack: [] as WhiteboardAnnotation[][],
};

export const useMAICCanvasStore = create<MAICCanvasState>((set, get) => ({
  ...initialState,

  setTool: (tool) => set({ activeTool: tool }),
  setColor: (color) => set({ activeColor: color }),
  setStrokeWidth: (width) => set({ strokeWidth: width }),
  setDrawing: (drawing) => set({ isDrawing: drawing }),

  addAnnotation: (annotation) =>
    set((s) => ({
      annotations: [...s.annotations, annotation],
      undoStack: [...s.undoStack, s.annotations],
      redoStack: [],
    })),

  removeAnnotation: (id) =>
    set((s) => ({
      annotations: s.annotations.filter((a) => a.id !== id),
      undoStack: [...s.undoStack, s.annotations],
      redoStack: [],
    })),

  clearAnnotations: () =>
    set((s) => ({
      annotations: [],
      undoStack: [...s.undoStack, s.annotations],
      redoStack: [],
    })),

  setAnnotations: (annotations) => set({ annotations }),

  undo: () => {
    const { undoStack, annotations } = get();
    if (undoStack.length === 0) return;
    const prev = undoStack[undoStack.length - 1];
    set({
      annotations: prev,
      undoStack: undoStack.slice(0, -1),
      redoStack: [...get().redoStack, annotations],
    });
  },

  redo: () => {
    const { redoStack, annotations } = get();
    if (redoStack.length === 0) return;
    const next = redoStack[redoStack.length - 1];
    set({
      annotations: next,
      redoStack: redoStack.slice(0, -1),
      undoStack: [...get().undoStack, annotations],
    });
  },

  canUndo: () => get().undoStack.length > 0,
  canRedo: () => get().redoStack.length > 0,

  reset: () => set(initialState),
}));
