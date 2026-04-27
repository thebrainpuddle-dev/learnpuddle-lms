// src/components/maic/RoundtableStrip.tsx
//
// Persistent agent dock rendered inside the stage viewport during
// playback. Shows the full roster as a horizontal strip of avatar
// tiles. The currently speaking agent is enlarged + emphasized with a
// ring of their color; the others are dimmed but remain visible so the
// audience keeps a sense of the full classroom cast.
//
// Pair to `PresentationSpeechOverlay` (the old single-agent floating
// card). Both can render simultaneously — RoundtableStrip covers
// "who's on stage," PresentationSpeechOverlay covers "what the active
// speaker is saying right now." Sprint 2+ may fold the overlay into
// the strip; for now they're complementary.
//
// Gated by `SPRINT1_FLAGS.roundtableStrip` — toggle off from DevTools
// via `localStorage.setItem('maic.sprint1.roundtableStrip', 'off')` to
// fall back to the pre-sprint UI.
//
// Design anchors (own implementation; patterns inspired by what feels
// polished in similar multi-agent UIs):
//   - Strip sits at bottom-center of the 16:9 viewport, above the
//     ProactiveCardManager overlay so suggestion cards can still fly
//     over without occluding the agent roster.
//   - Active speaker: ring pulse keyed to agent.color, avatar size 'lg'.
//   - Inactive: size 'sm', opacity 0.55, no ring emphasis.
//   - Small name label under each avatar — truncated at 10 chars.
//   - pointer-events-none on the wrapper so the strip never blocks
//     clicks on the slide content below it.

import React, { useMemo } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import type { MAICAgent } from '../../types/maic';
import { AgentAvatar } from './AgentAvatar';
import { cn } from '../../lib/utils';

export interface RoundtableStripProps {
  /** Full agent roster — typically from stageStore.agents. */
  agents: readonly MAICAgent[];
  /** Currently speaking agent id, or null when idle. */
  speakingAgentId: string | null;
  /** Whether the class is actively playing. When false, the strip
   *  renders in a muted "rehearsal" state. */
  isPlaying: boolean;
  /** Hide the strip entirely. Caller uses this to suppress when the
   *  discussion panel or a modal is covering the stage. */
  hidden?: boolean;
}

/** Truncate long names so the strip stays balanced at any roster size. */
function truncateName(name: string, max = 14): string {
  if (!name) return '';
  if (name.length <= max) return name;
  return `${name.slice(0, max - 1).trimEnd()}\u2026`;
}

export const RoundtableStrip = React.memo<RoundtableStripProps>(function RoundtableStrip({
  agents,
  speakingAgentId,
  isPlaying,
  hidden = false,
}) {
  // Stable key derived from roster composition so AnimatePresence can
  // re-trigger entry animations when the classroom swaps rosters
  // (e.g., post-regenerate).
  const rosterKey = useMemo(
    () => agents.map((a) => a.id).join('|'),
    [agents],
  );

  if (hidden || agents.length === 0) return null;

  return (
    <div
      className={cn(
        'absolute inset-x-0 bottom-2 z-10 flex justify-center px-4',
        'pointer-events-none select-none',
      )}
      aria-label="Classroom agent roster"
      role="group"
    >
      <AnimatePresence mode="popLayout">
        <motion.div
          key={rosterKey}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: isPlaying ? 1 : 0.75, y: 0 }}
          exit={{ opacity: 0, y: 8 }}
          transition={{ duration: 0.28, ease: [0.21, 1, 0.36, 1] }}
          className={cn(
            'flex items-end gap-3 px-4 py-2',
            'rounded-2xl border border-white/10 bg-black/55 backdrop-blur-md',
            'shadow-lg shadow-black/20',
          )}
        >
          {agents.map((agent) => {
            const isActive = agent.id === speakingAgentId;
            return (
              <motion.div
                key={agent.id}
                layout
                initial={false}
                animate={{
                  scale: isActive ? 1.08 : 0.92,
                  opacity: isActive ? 1 : 0.55,
                }}
                transition={{ type: 'spring', stiffness: 280, damping: 26, mass: 0.7 }}
                className="flex flex-col items-center gap-1 min-w-[48px]"
                data-active={isActive ? 'true' : 'false'}
                data-testid="roundtable-agent-tile"
                data-agent-id={agent.id}
              >
                <AgentAvatar
                  agent={agent}
                  isSpeaking={isActive}
                  size={isActive ? 'md' : 'sm'}
                />
                <span
                  className={cn(
                    'text-[10px] leading-none tabular-nums truncate max-w-[72px]',
                    isActive ? 'text-white font-medium' : 'text-white/55',
                  )}
                  title={agent.name}
                >
                  {truncateName(agent.name, isActive ? 16 : 10)}
                </span>
              </motion.div>
            );
          })}
        </motion.div>
      </AnimatePresence>
    </div>
  );
});
