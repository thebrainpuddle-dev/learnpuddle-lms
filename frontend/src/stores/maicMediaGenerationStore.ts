// stores/maicMediaGenerationStore.ts
//
// F2 (P0) — Per-element media-task store.
//
// Ports OpenMAIC's `useMediaGenerationStore` shape (research/OpenMAIC/lib/
// store/media-generation.ts) into our Zustand convention. Tracks a single
// media-task per element keyed by `element_key`
// (`<scene_idx>:<slide_idx>:<element_idx>:<element_id>`) so the SlideRenderer
// can show per-image shimmer/done/failed independent of the legacy global
// `imagesPending` boolean (which still drives F3 "all images done" gating).
//
// Hydration paths:
//   1. classroom-detail GET → `content_image_tasks` map → hydrateFromMap()
//   2. ws/maic/classrooms/<id>/ → `maic.image.task` events → applyEvent()
//
// IndexedDB durability is INTENTIONALLY OMITTED for the first cut. The
// server already persists the generated image URL (the GET hydration path
// rebuilds the task map on every page load). A follow-up may add local
// blob caching for offline/replay scenarios — see TODO below.

import { create } from 'zustand';

// ─── Types ──────────────────────────────────────────────────────────────────

export type MediaTaskStatus = 'pending' | 'generating' | 'done' | 'failed';

/** A single per-element media task. The `classroomId` field lets clearStage
 *  scope cleanup to the classroom the user just left without nuking tasks
 *  for other classrooms still mounted (e.g. a sidebar preview). */
export interface MediaTask {
  classroomId: string;
  elementKey: string;
  status: MediaTaskStatus;
  /** Generated image URL — present once status becomes 'done'. */
  src?: string;
  /** Structured error code from the backend — present when status='failed'.
   *  Examples: 'PROVIDER_DISABLED', 'CONTENT_SENSITIVE', 'TIMEOUT'. */
  errorCode?: string;
  /** Server-stamped ISO timestamp; useful for debugging out-of-order WS events. */
  updatedAt?: string;
}

/** Backend's serialised event shape — matches the contract in F2 spec. */
export interface MaicImageTaskEvent {
  type: 'maic.image.task';
  classroom_id: string;
  element_key: string;
  status: MediaTaskStatus;
  src?: string;
  error_code?: string;
  updated_at?: string;
}

/** Hydration map shape returned by classroom-detail GET. */
export type ContentImageTasksMap = Record<
  string,
  {
    status: MediaTaskStatus;
    src?: string;
    error_code?: string;
    updated_at?: string;
  }
>;

interface MaicMediaGenerationState {
  /** All tracked tasks keyed by element_key. */
  tasks: Record<string, MediaTask>;

  /** Hydrate the store from the classroom-detail GET response. Replaces
   *  any existing tasks for that classroom (server is the source of
   *  truth at hydration time). */
  hydrateFromMap: (classroomId: string, map: ContentImageTasksMap) => void;

  /** Apply an incoming `maic.image.task` WS event. Late-arriving stale
   *  events (older `updated_at` than what we already have) are ignored. */
  applyEvent: (event: MaicImageTaskEvent) => void;

  /** Convenience accessor — returns undefined when no task is tracked. */
  getTask: (elementKey: string) => MediaTask | undefined;

  /** Drop every task for the given classroom (e.g. on unmount). The
   *  server keeps the durable copy, so this is purely a memory hygiene
   *  step; we don't persist anything locally yet. */
  clearStage: (classroomId: string) => void;

  /** Reset the entire store. Test helper / global cleanup. */
  resetAll: () => void;
}

// Note: a `revokeObjectUrls` method was intentionally removed (WAVE-F2-F5).
// The F2 store stashes server-issued https URLs directly into `task.src` —
// it never calls `URL.createObjectURL()`, so there is nothing to revoke.
// If/when IndexedDB blob durability lands, reintroduce the method (and a
// matching call site in MAICPlayerPage's unmount effect) at that time.

// ─── Store ──────────────────────────────────────────────────────────────────

export const useMaicMediaGenerationStore = create<MaicMediaGenerationState>()(
  (set, get) => ({
    tasks: {},

    hydrateFromMap: (classroomId, map) => {
      // Replace tasks for this classroom only — leave any other classroom's
      // tasks alone in case the user has multiple players mounted (rare).
      const next: Record<string, MediaTask> = {};
      for (const [elementKey, task] of Object.entries(get().tasks)) {
        if (task.classroomId !== classroomId) {
          next[elementKey] = task;
        }
      }
      for (const [elementKey, payload] of Object.entries(map)) {
        next[elementKey] = {
          classroomId,
          elementKey,
          status: payload.status,
          src: payload.src,
          errorCode: payload.error_code,
          updatedAt: payload.updated_at,
        };
      }
      set({ tasks: next });
    },

    applyEvent: (event) => {
      if (event.type !== 'maic.image.task') return;
      const { classroom_id, element_key, status, src, error_code, updated_at } =
        event;
      const existing = get().tasks[element_key];

      // Stale-event guard: if we already have an entry with an updated_at
      // greater-than-or-equal-to the incoming event, ignore the incoming
      // event. WS delivery is generally in order but reconnects can replay
      // buffered events out of sequence; we also drop exact-equal timestamps
      // (clock granularity is ~1ms) to make idempotent replays a no-op.
      if (
        existing &&
        existing.updatedAt &&
        updated_at &&
        new Date(updated_at).getTime() <= new Date(existing.updatedAt).getTime()
      ) {
        return;
      }

      const nextTask: MediaTask = {
        classroomId: classroom_id,
        elementKey: element_key,
        status,
        src: status === 'done' ? src ?? existing?.src : existing?.src,
        errorCode:
          status === 'failed' ? error_code ?? existing?.errorCode : undefined,
        updatedAt: updated_at ?? existing?.updatedAt,
      };

      set((s) => ({ tasks: { ...s.tasks, [element_key]: nextTask } }));
    },

    getTask: (elementKey) => get().tasks[elementKey],

    clearStage: (classroomId) => {
      const next: Record<string, MediaTask> = {};
      for (const [elementKey, task] of Object.entries(get().tasks)) {
        if (task.classroomId !== classroomId) {
          next[elementKey] = task;
        }
      }
      set({ tasks: next });
    },

    resetAll: () => set({ tasks: {} }),
  }),
);

// ─── Selector helpers ───────────────────────────────────────────────────────

/** React-friendly selector — subscribe to one element's task without
 *  re-rendering on unrelated task updates. */
export function useMediaTask(elementKey: string | undefined): MediaTask | undefined {
  return useMaicMediaGenerationStore((s) =>
    elementKey ? s.tasks[elementKey] : undefined,
  );
}
