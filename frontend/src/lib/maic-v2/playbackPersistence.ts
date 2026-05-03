/**
 * Playback persistence — save + restore PlaybackSnapshot across reloads.
 *
 * Source:
 *   /Volumes/CrucialX9/OpenMAIC/lib/utils/playback-storage.ts
 *
 * Used by:
 *   - frontend/src/components/maic-v2/Stage.tsx (MAIC-412)
 *     subscribes the engine's `onProgress` callback to `save`, and
 *     calls `load` on mount before engine.start() / continuePlayback().
 *
 * Storage backend: localStorage. Key shape: `maic-v2:playback:${sessionId}`.
 * Per-session-scoped so two open tabs of two DIFFERENT sessions don't
 * trample. Two tabs of the SAME session DO trample by design — if a
 * future product decision requires per-tab isolation, switch to
 * sessionStorage in one place (the `_storage` getter).
 *
 * Failure modes:
 *   - localStorage unavailable (private mode in some browsers)
 *     → load/save are no-ops; the engine still works, just no persistence.
 *   - JSON parse failure on load (corrupted entry)
 *     → load returns null and clears the bad key.
 *   - quota exceeded on save (pathological — snapshots are ~200 bytes)
 *     → save swallows + logs; never throws.
 *   - empty sessionId
 *     → save/load no-op (don't pollute the global namespace).
 */
import type { PlaybackSnapshot } from './playback-types';


export interface PlaybackPersistence {
  save(snapshot: PlaybackSnapshot): void;
  load(): PlaybackSnapshot | null;
  clear(): void;
}


const KEY_PREFIX = 'maic-v2:playback:';


function _storage(): Storage | null {
  // localStorage can throw on access in some private-mode browsers;
  // wrap in try/catch so the call site doesn't have to.
  try {
    if (typeof window === 'undefined') return null;
    return window.localStorage;
  } catch {
    return null;
  }
}


/**
 * Build a per-session persistence handle. The returned object is a
 * thin wrapper around localStorage — no caching, no in-memory state,
 * so two handles for the same sessionId stay in sync via the storage
 * itself.
 */
export function createPlaybackPersistence(sessionId: string): PlaybackPersistence {
  const key = sessionId ? `${KEY_PREFIX}${sessionId}` : '';

  function save(snapshot: PlaybackSnapshot): void {
    if (!key) return;
    const storage = _storage();
    if (!storage) return;
    try {
      storage.setItem(key, JSON.stringify(snapshot));
    } catch (err) {
      // Quota exceeded or storage full — never block the engine.
      console.warn('[playbackPersistence] save failed', err);
    }
  }

  function load(): PlaybackSnapshot | null {
    if (!key) return null;
    const storage = _storage();
    if (!storage) return null;
    const raw = storage.getItem(key);
    if (raw === null) return null;
    try {
      const parsed = JSON.parse(raw) as PlaybackSnapshot;
      // Minimal shape validation — anything missing the indices is junk.
      if (
        typeof parsed?.sceneIndex !== 'number' ||
        typeof parsed?.actionIndex !== 'number' ||
        !Array.isArray(parsed?.consumedDiscussions)
      ) {
        storage.removeItem(key);
        return null;
      }
      return parsed;
    } catch {
      // Corrupted JSON — drop the bad key so subsequent loads don't
      // keep retrying it.
      storage.removeItem(key);
      return null;
    }
  }

  function clear(): void {
    if (!key) return;
    const storage = _storage();
    if (!storage) return;
    try {
      storage.removeItem(key);
    } catch {
      // ignore
    }
  }

  return { save, load, clear };
}
