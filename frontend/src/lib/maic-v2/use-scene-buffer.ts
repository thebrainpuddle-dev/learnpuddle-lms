/**
 * useSceneBuffer — React hook that wraps `reduceEvents` in a useMemo
 * over an events[] array (typically the one returned by
 * useMaicClassroomChannelV2).
 *
 * Used by:
 *   - frontend/src/components/maic-v2/Stage.tsx (MAIC-403.7)
 *
 * Why it's its own file (and its own hook):
 *   - Keeps the Stage component free of the useMemo identity-tracking
 *     boilerplate.
 *   - Makes it trivial to memoize on the events[] array reference,
 *     which the channel hook produces with a fresh reference exactly
 *     when a new event arrives. Recomputation cost is O(events.length)
 *     per new event — acceptable for Phase 1's 10-100 events per turn.
 *     If profiling later shows pressure, swap to incremental
 *     accumulation (lastIndex + applyEvent) without changing this
 *     hook's signature.
 */
import { useMemo } from 'react';

import { reduceEvents } from './scene-buffer';
import type { SceneBuffer } from './scene-buffer';
import type { MaicEvent } from '../../hooks/useMaicClassroomChannelV2';


/**
 * Reduce a MaicEvent[] prefix into the latest SceneBuffer.
 *
 * Stable identity: returns the same object instance across renders
 * unless `events` reference changes.
 */
export function useSceneBuffer(events: MaicEvent[]): SceneBuffer {
  return useMemo(() => reduceEvents(events), [events]);
}
