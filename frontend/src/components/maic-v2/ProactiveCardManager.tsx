/**
 * ProactiveCardManager — thin filter + renderer between Stage's
 * `trigger` state and the ProactiveCard component.
 *
 * Single critical invariant (MAIC-411.2 risk register):
 *   The manager NEVER caches its own "shown" set. It defers entirely
 *   to `engine.getSnapshot().consumedDiscussions` on every render.
 *
 * Why: a snapshot/restore (MAIC-412) can re-fire the engine's
 * `_dispatchDiscussion` for a discussion that was already consumed.
 * The engine's own filter (`if consumedDiscussions.has(action.id)
 * return processNext()`) catches this at the engine layer, but the
 * manager adds a second-line check so a future engine refactor can't
 * accidentally surface a duplicate ProactiveCard.
 *
 * The `trigger` prop is controlled by Stage from the engine's
 * `onProactiveShow` / `onProactiveHide` callbacks. The manager is
 * stateless — no useState, no useEffect. Pure render.
 */
import type { PlaybackEngine } from '../../lib/maic-v2/playback-engine';
import type { TriggerEvent } from '../../lib/maic-v2/playback-types';

import { ProactiveCard } from './ProactiveCard';


export interface ProactiveCardManagerProps {
  /** The engine instance — read for `getSnapshot().consumedDiscussions`. */
  engine: PlaybackEngine;
  /** Current trigger from Stage's `onProactiveShow` state, or null. */
  trigger: TriggerEvent | null;
  onJoin: () => void;
  onSkip: () => void;
}


export function ProactiveCardManager({
  engine,
  trigger,
  onJoin,
  onSkip,
}: ProactiveCardManagerProps) {
  if (!trigger) return null;

  // Dedup: never re-render a card for an already-consumed discussion.
  // Reads engine state synchronously on every render — no subscription,
  // no caching. If the engine's consumed-set drifts during the render
  // (it shouldn't), the next render reconciles.
  const consumed = engine.getSnapshot().consumedDiscussions;
  if (consumed.includes(trigger.id)) {
    return null;
  }

  return (
    <ProactiveCard
      trigger={trigger}
      onJoin={onJoin}
      onSkip={onSkip}
    />
  );
}
