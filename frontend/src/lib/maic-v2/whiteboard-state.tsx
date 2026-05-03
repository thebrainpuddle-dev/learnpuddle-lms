/**
 * Whiteboard state — React Context + useReducer element registry.
 *
 * Source: THU-MAIC/OpenMAIC main lib/store/canvas.ts (whiteboard slice)
 *         (Zustand replaced with React Context + useReducer to keep deps
 *          unchanged — see Phase 2 plan §"Constraints")
 *
 * Used by:
 *   - frontend/src/components/maic-v2/Whiteboard.tsx (renders state.elements)
 *   - frontend/src/lib/maic-v2/action-engine.ts (mutates via controller)
 *   - frontend/src/components/maic-v2/Stage.tsx (provider wrap, MAIC-217)
 *
 * Two contexts (state + controller) so write-only consumers (the
 * ActionEngine) don't re-render when read-only state changes — and so
 * the controller's identity is stable across renders.
 *
 * Phase 2 deferrals:
 *   - Phase 8+ — undo / history snapshots (upstream useWhiteboardHistoryStore)
 *   - Phase 8+ — selection / interaction state (Phase 2 is render-only)
 */
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useReducer,
  type ReactNode,
} from 'react';

import type { Action } from './action-types';


// ── State shape ────────────────────────────────────────────────────


/**
 * A whiteboard element is the wire-format `wb_draw_*` action it came
 * from. Storing the action as-is (instead of normalising to a separate
 * shape) keeps the type system honest: renderers switch on
 * `element.type === 'wb_draw_text'` and get TS-narrowed access to the
 * action's params for free.
 */
export type WhiteboardElement = Extract<
  Action,
  {
    type:
      | 'wb_draw_text'
      | 'wb_draw_shape'
      | 'wb_draw_chart'
      | 'wb_draw_latex'
      | 'wb_draw_table'
      | 'wb_draw_line'
      | 'wb_draw_code';
  }
>;


export interface WhiteboardState {
  isOpen: boolean;
  /**
   * True during the cascade-clear animation between the moment
   * `wb_clear` fires and the elements array is actually emptied. Drives
   * the per-element exit animation in Whiteboard.tsx (Phase 2 surface
   * does CSS opacity transition on this flag).
   */
  isClearing: boolean;
  elements: WhiteboardElement[];
}


export const INITIAL_WHITEBOARD_STATE: WhiteboardState = {
  isOpen: false,
  isClearing: false,
  elements: [],
};


// ── Element key helper ─────────────────────────────────────────────


/**
 * Return the key used to look up an element in the registry. We prefer
 * `elementId` (the agent-supplied id used by `wb_delete` and
 * `wb_edit_code` to reference an element later) and fall back to
 * `action.id` (the per-emit action id) when the agent didn't bother
 * with an elementId.
 *
 * Exported so the ActionEngine and tests can compute the same key.
 */
export function getElementKey(el: WhiteboardElement): string {
  const withId = el as { elementId?: string; id: string };
  return withId.elementId ?? withId.id;
}


// ── Reducer ────────────────────────────────────────────────────────


type WhiteboardAction =
  | { type: 'set_open'; open: boolean }
  | { type: 'set_clearing'; clearing: boolean }
  | { type: 'add_element'; element: WhiteboardElement }
  | { type: 'update_element'; key: string; patch: Partial<WhiteboardElement> }
  | { type: 'delete_element'; key: string }
  | { type: 'clear' };


export function whiteboardReducer(
  state: WhiteboardState,
  action: WhiteboardAction,
): WhiteboardState {
  switch (action.type) {
    case 'set_open':
      if (state.isOpen === action.open) return state;
      return { ...state, isOpen: action.open };

    case 'set_clearing':
      if (state.isClearing === action.clearing) return state;
      return { ...state, isClearing: action.clearing };

    case 'add_element': {
      const key = getElementKey(action.element);
      // Upsert by key — re-emitting an element with the same id replaces.
      const idx = state.elements.findIndex((e) => getElementKey(e) === key);
      const next = [...state.elements];
      if (idx >= 0) next[idx] = action.element;
      else next.push(action.element);
      return { ...state, elements: next };
    }

    case 'update_element': {
      const idx = state.elements.findIndex((e) => getElementKey(e) === action.key);
      if (idx < 0) return state;  // missing key — no-op (not a crash)
      const next = [...state.elements];
      next[idx] = { ...next[idx], ...action.patch } as WhiteboardElement;
      return { ...state, elements: next };
    }

    case 'delete_element': {
      const next = state.elements.filter((e) => getElementKey(e) !== action.key);
      if (next.length === state.elements.length) return state;
      return { ...state, elements: next };
    }

    case 'clear':
      if (state.elements.length === 0) return state;
      return { ...state, elements: [] };

    default:
      return state;
  }
}


// ── Controller (write-only API exposed to ActionEngine + tests) ────


export interface WhiteboardController {
  setOpen(open: boolean): void;
  setClearing(clearing: boolean): void;
  addElement(element: WhiteboardElement): void;
  updateElement(key: string, patch: Partial<WhiteboardElement>): void;
  deleteElement(key: string): void;
  clear(): void;
}


// ── Contexts ───────────────────────────────────────────────────────


const WhiteboardStateContext = createContext<WhiteboardState | null>(null);
const WhiteboardControllerContext = createContext<WhiteboardController | null>(null);


// ── Provider ───────────────────────────────────────────────────────


export interface WhiteboardProviderProps {
  children: ReactNode;
  /** Optional initial state — useful in tests to mount with elements. */
  initialState?: WhiteboardState;
}


export function WhiteboardProvider({
  children,
  initialState = INITIAL_WHITEBOARD_STATE,
}: WhiteboardProviderProps) {
  const [state, dispatch] = useReducer(whiteboardReducer, initialState);

  const setOpen = useCallback((open: boolean) => dispatch({ type: 'set_open', open }), []);
  const setClearing = useCallback(
    (clearing: boolean) => dispatch({ type: 'set_clearing', clearing }),
    [],
  );
  const addElement = useCallback(
    (element: WhiteboardElement) => dispatch({ type: 'add_element', element }),
    [],
  );
  const updateElement = useCallback(
    (key: string, patch: Partial<WhiteboardElement>) =>
      dispatch({ type: 'update_element', key, patch }),
    [],
  );
  const deleteElement = useCallback(
    (key: string) => dispatch({ type: 'delete_element', key }),
    [],
  );
  const clear = useCallback(() => dispatch({ type: 'clear' }), []);

  const controller = useMemo<WhiteboardController>(
    () => ({ setOpen, setClearing, addElement, updateElement, deleteElement, clear }),
    [setOpen, setClearing, addElement, updateElement, deleteElement, clear],
  );

  return (
    <WhiteboardControllerContext.Provider value={controller}>
      <WhiteboardStateContext.Provider value={state}>
        {children}
      </WhiteboardStateContext.Provider>
    </WhiteboardControllerContext.Provider>
  );
}


// ── Hooks ──────────────────────────────────────────────────────────


export function useWhiteboardState(): WhiteboardState {
  const ctx = useContext(WhiteboardStateContext);
  if (!ctx) {
    throw new Error('useWhiteboardState must be used within a WhiteboardProvider');
  }
  return ctx;
}


export function useWhiteboardController(): WhiteboardController {
  const ctx = useContext(WhiteboardControllerContext);
  if (!ctx) {
    throw new Error('useWhiteboardController must be used within a WhiteboardProvider');
  }
  return ctx;
}
