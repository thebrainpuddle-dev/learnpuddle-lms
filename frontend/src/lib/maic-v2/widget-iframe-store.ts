/**
 * Widget iframe messaging store — Zustand singleton.
 *
 * Source: THU-MAIC/OpenMAIC lib/store/widget-iframe.ts (lifted under
 *         ADR-001a). Local edits: import path uses `zustand` directly
 *         (no Next.js layout assumption).
 *
 * Tracks per-scene postMessage callbacks so the playback engine can
 * dispatch teacher actions (widget_highlight / widget_setState /
 * widget_annotation / widget_reveal) into the correct iframe even
 * when scenes switch mid-classroom. The store is keyed by sceneId
 * so the post-target stays unambiguous when multiple interactive
 * scenes are mounted simultaneously (rare; more common pattern is
 * one active scene + a "preloading next" iframe).
 */
import { create } from 'zustand';

interface WidgetIframeState {
  /** Callbacks keyed by sceneId for targeted postMessage communication */
  sendMessageByScene: Record<
    string,
    (type: string, payload: Record<string, unknown>) => void
  >;
  /** Currently active scene ID (used for fallback/legacy support) */
  activeSceneId: string | null;
  /** Register an iframe callback for a specific scene */
  registerIframe: (
    sceneId: string,
    callback: ((type: string, payload: Record<string, unknown>) => void) | null,
  ) => void;
  /** Set the active scene ID */
  setActiveScene: (sceneId: string | null) => void;
  /** Get sendMessage callback for a specific scene (or current active scene) */
  getSendMessage: (
    sceneId?: string,
  ) => ((type: string, payload: Record<string, unknown>) => void) | null;
}

export const useWidgetIframeStore = create<WidgetIframeState>((set, get) => ({
  sendMessageByScene: {},
  activeSceneId: null,
  registerIframe: (sceneId, callback) =>
    set((state) => {
      if (callback === null) {
        // Unregister: remove from map
        const updated = { ...state.sendMessageByScene };
        delete updated[sceneId];
        return { sendMessageByScene: updated };
      }
      // Register: add to map
      return {
        sendMessageByScene: { ...state.sendMessageByScene, [sceneId]: callback },
      };
    }),
  setActiveScene: (sceneId) => set({ activeSceneId: sceneId }),
  getSendMessage: (sceneId) => {
    const state = get();
    const targetId = sceneId ?? state.activeSceneId;
    if (!targetId) return null;
    return state.sendMessageByScene[targetId] ?? null;
  },
}));
