// src/lib/playbackPersistence.ts
//
// Tiny localStorage-backed persistence for classroom playback position
// (Sprint 3 · B.9). Stores the last-seen {sceneIndex, slideIndex} per
// classroom so the student can pick up where they left off after a
// refresh or accidental close.
//
// Keys: `maic.playback.<classroomId>`. Values: JSON
// `{sceneIndex, slideIndex, updatedAt}` where updatedAt is ms epoch —
// used to expire stale positions (default 14 days) so a classroom the
// user clearly abandoned doesn't keep prompting for resume.

const KEY_PREFIX = 'maic.playback.';
const STALE_AFTER_MS = 14 * 24 * 60 * 60 * 1000; // 14 days

export interface PlaybackPosition {
  sceneIndex: number;
  slideIndex: number;
  updatedAt: number;
}

function key(classroomId: string): string {
  return `${KEY_PREFIX}${classroomId}`;
}

export function readPosition(classroomId: string): PlaybackPosition | null {
  if (typeof window === 'undefined' || !classroomId) return null;
  try {
    const raw = window.localStorage.getItem(key(classroomId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<PlaybackPosition>;
    if (
      typeof parsed.sceneIndex !== 'number' ||
      typeof parsed.slideIndex !== 'number' ||
      typeof parsed.updatedAt !== 'number'
    ) {
      return null;
    }
    if (Date.now() - parsed.updatedAt > STALE_AFTER_MS) {
      // Expired — proactively clean up so the key doesn't linger forever.
      window.localStorage.removeItem(key(classroomId));
      return null;
    }
    return parsed as PlaybackPosition;
  } catch {
    return null;
  }
}

export function savePosition(
  classroomId: string,
  sceneIndex: number,
  slideIndex: number,
): void {
  if (typeof window === 'undefined' || !classroomId) return;
  try {
    const payload: PlaybackPosition = {
      sceneIndex,
      slideIndex,
      updatedAt: Date.now(),
    };
    window.localStorage.setItem(key(classroomId), JSON.stringify(payload));
  } catch {
    /* quota / privacy — silent no-op */
  }
}

export function clearPosition(classroomId: string): void {
  if (typeof window === 'undefined' || !classroomId) return;
  try {
    window.localStorage.removeItem(key(classroomId));
  } catch {
    /* silent */
  }
}
