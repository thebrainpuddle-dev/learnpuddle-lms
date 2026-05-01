// src/lib/maicReadinessGate.ts
//
// F3 (P0) — Two-milestone classroom-ready gating.
//
// OpenMAIC's player lets users in as soon as **scene 1** is paintable;
// remaining scenes stream in afterwards. Pre-F3 our player gated on the
// classroom-level `images_pending=false` boolean — all-or-nothing across
// the whole batch. This helper implements the new two-milestone model:
//
//   - Milestone 1 (gate this file owns):  scene 0 ready → load the player.
//   - Milestone 2 (caller-owned):         whole batch done → drop the
//                                          "Fetching images…" header badge
//                                          and stop polling.
//
// The gate has two paths so legacy classrooms (generated before F2 added
// the per-element `content_image_tasks` map) keep behaving exactly as
// they did before:
//
//   - When the per-element task store is empty for the classroom, fall
//     back to `!imagesPending` — identical to the pre-F3 logic.
//
//   - When the per-element task store is populated, derive
//     `firstSceneReady` from it. Scene 0 is ready when every image
//     element it owns has a terminal status (`done` | `failed`). A scene
//     with zero image elements is considered ready (text-only scenes
//     never block).
//
// Element keys come in two shapes (the FE store treats them as opaque):
//   - plain     → `<sceneIdx>:<slideIdx>:<elementIdx>:<elementId>`
//   - walker    → `<prefix>:<sceneIdx>:<slideIdx>:<elementIdx>:<elementId>`
//
// `parseSceneIndexFromElementKey` handles both. Unparseable keys are
// ignored (defensive: never block playback on a malformed entry).

import type {
  ContentImageTasksMap,
  MediaTaskStatus,
} from '../stores/maicMediaGenerationStore';

/** Statuses that mean "this image task is done — won't change again". */
const TERMINAL_STATUSES: ReadonlySet<MediaTaskStatus> = new Set([
  'done',
  'failed',
]);

/**
 * Parse the zero-based scene index from an element key.
 *
 * Plain shape   (4 parts) → index 0 holds sceneIdx.
 * Walker shape  (5 parts) → index 1 holds sceneIdx (index 0 is the
 *                            walker namespace prefix, e.g. `meta_slides`).
 *
 * Returns `null` for any key that doesn't match either shape, or whose
 * scene index slot isn't a non-negative integer. Defensive parser:
 * unparseable entries should never accidentally block the gate.
 */
export function parseSceneIndexFromElementKey(key: string): number | null {
  if (!key) return null;
  const parts = key.split(':');
  let sceneIdxStr: string | undefined;
  if (parts.length === 4) {
    sceneIdxStr = parts[0];
  } else if (parts.length === 5) {
    sceneIdxStr = parts[1];
  } else {
    return null;
  }
  if (sceneIdxStr === undefined || sceneIdxStr === '') return null;
  // Strict integer parse — reject 'b', '1.5', '-1', '01a', etc.
  if (!/^\d+$/.test(sceneIdxStr)) return null;
  return Number.parseInt(sceneIdxStr, 10);
}

export interface ClassroomPlayableInput {
  /** Per-element media task entries keyed by element_key. Pass `{}` to opt
   *  the classroom into the legacy fallback path. */
  tasks: ContentImageTasksMap;
  /** Classroom-level `images_pending` boolean from the GET payload.
   *  Drives the legacy fallback path and the "trust the global signal"
   *  shortcut when it explicitly says everything's done. */
  imagesPending?: boolean;
}

/**
 * The F3 gate. `true` means the player should mount the Stage; `false`
 * means keep the "Finishing up — fetching slide images…" preparing panel.
 *
 * Decision order:
 *
 *   1. If `imagesPending === false` (or undefined), the server has
 *      explicitly told us the whole batch is done. Always playable —
 *      don't second-guess based on a possibly-stale local task map.
 *
 *   2. If the task map is empty (legacy / pre-F2 classroom), gate on
 *      `!imagesPending` exactly like the pre-F3 code did.
 *
 *   3. Otherwise (F3 path): scene 0 is ready when every image task
 *      assigned to scene 0 has a terminal status. Scenes with zero
 *      image tasks are ready by default.
 */
export function isClassroomPlayable(input: ClassroomPlayableInput): boolean {
  const { tasks, imagesPending } = input;

  // Rule 1: server says batch is done → always playable. Match `=== false`
  // explicitly: a missing/null/undefined `images_pending` should fall through
  // to F3 derivation (per-element scene-0 readiness) rather than be treated
  // as "definitely done".
  if (imagesPending === false) {
    return true;
  }

  const taskKeys = Object.keys(tasks);

  // Rule 2: legacy fallback — no per-element tasks hydrated.
  if (taskKeys.length === 0) {
    // imagesPending === true here, so legacy gate keeps us out.
    return false;
  }

  // Rule 3: F3 first-scene-ready derivation.
  let scene0HasAnyImages = false;
  for (const key of taskKeys) {
    const sceneIdx = parseSceneIndexFromElementKey(key);
    if (sceneIdx !== 0) continue; // ignore non-scene-0 + unparseable
    scene0HasAnyImages = true;
    const status = tasks[key]?.status;
    if (!status || !TERMINAL_STATUSES.has(status)) {
      return false;
    }
  }

  // Either every scene-0 task was terminal, OR scene 0 has no image
  // elements at all (text-only first scene). Both → playable.
  void scene0HasAnyImages; // explicit: no-images is the playable case too.
  return true;
}
