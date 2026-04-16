// stores/maicKeyboardStore.ts — Tracks modifier key states (Ctrl, Shift, Space)
//
// Provides real-time keyboard modifier tracking for the MAIC stage.
// Ctrl/Shift detection enables multi-select and precision interactions
// on the whiteboard; Space enables pan/grab mode.

import { create } from 'zustand';

interface MAICKeyboardState {
  ctrlKeyActive: boolean;
  shiftKeyActive: boolean;
  spaceKeyActive: boolean;

  setCtrlKey: (v: boolean) => void;
  setShiftKey: (v: boolean) => void;
  setSpaceKey: (v: boolean) => void;

  /** Returns true when either Ctrl or Shift is held */
  ctrlOrShiftKeyActive: () => boolean;
}

export const useMAICKeyboardStore = create<MAICKeyboardState>((set, get) => ({
  ctrlKeyActive: false,
  shiftKeyActive: false,
  spaceKeyActive: false,

  setCtrlKey: (v) => set({ ctrlKeyActive: v }),
  setShiftKey: (v) => set({ shiftKeyActive: v }),
  setSpaceKey: (v) => set({ spaceKeyActive: v }),

  ctrlOrShiftKeyActive: () => get().ctrlKeyActive || get().shiftKeyActive,
}));

// ─── Global keyboard listener initialisation ────────────────────────────────

let _cleanupFn: (() => void) | null = null;

/**
 * Registers document-level keydown/keyup listeners that feed the keyboard
 * store. Call once on mount; returns a cleanup function for unmount.
 *
 * Safe to call multiple times — only one set of listeners is active at any
 * time (previous listeners are removed before attaching new ones).
 */
export function initKeyboardListeners(): () => void {
  // Tear down previous listeners if they exist
  _cleanupFn?.();

  const store = useMAICKeyboardStore.getState;

  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'Control' || e.key === 'Meta') {
      store().setCtrlKey(true);
    } else if (e.key === 'Shift') {
      store().setShiftKey(true);
    } else if (e.key === ' ') {
      store().setSpaceKey(true);
    }
  };

  const handleKeyUp = (e: KeyboardEvent) => {
    if (e.key === 'Control' || e.key === 'Meta') {
      store().setCtrlKey(false);
    } else if (e.key === 'Shift') {
      store().setShiftKey(false);
    } else if (e.key === ' ') {
      store().setSpaceKey(false);
    }
  };

  // Reset all keys when the window loses focus (e.g. Alt-Tab away) so we
  // don't get stuck-key artifacts when the user returns.
  const handleBlur = () => {
    store().setCtrlKey(false);
    store().setShiftKey(false);
    store().setSpaceKey(false);
  };

  document.addEventListener('keydown', handleKeyDown);
  document.addEventListener('keyup', handleKeyUp);
  window.addEventListener('blur', handleBlur);

  const cleanup = () => {
    document.removeEventListener('keydown', handleKeyDown);
    document.removeEventListener('keyup', handleKeyUp);
    window.removeEventListener('blur', handleBlur);
    _cleanupFn = null;
  };

  _cleanupFn = cleanup;
  return cleanup;
}
