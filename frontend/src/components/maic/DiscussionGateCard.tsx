// src/components/maic/DiscussionGateCard.tsx
//
// Porting Phase 1 · P1.1 — engine-level breath before a scripted
// discussion action opens the RoundtablePanel. When the playback engine
// hits a `{type:'discussion', triggerMode:'auto'}` action it soft-pauses
// and sets `maicStageStore.discussionPending`. This component is the
// single source of the transition from "engine paused, about to open
// discussion" → "panel open" | "panel skipped, resume playback."
//
// Visual sequence (matches the OpenMAIC behavior the user flagged):
//   1. Engine pauses mid-scene and fires `discussionPending`.
//   2. We wait `BREATH_MS` in silence so the student absorbs the last
//      spoken line — no popup yet.
//   3. A small anchored card fades in near the initiating agent's avatar
//      (falling back to bottom-center when no anchor is available) with
//      "Join" and "Skip" buttons and a 5 s linear countdown bar.
//   4. Join → promote pending → discussionMode, RoundtablePanel opens.
//   5. Skip or countdown expiry → clear pending + resume playback from
//      the checkpoint the engine already saved.
//
// The old ProactiveCardManager still handles the "no engine action,
// let's suggest a discussion at a natural pause" path and pushes through
// the same pending-state pipeline so there's ONE source of UI for every
// discussion open event.

import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { MessagesSquare, X } from 'lucide-react';
import { useMAICStageStore } from '../../stores/maicStageStore';
import { cn } from '../../lib/utils';

export interface DiscussionGateCardProps {
  /** Called when the user clicks Join. Caller is expected to open the
   *  RoundtablePanel (typically by calling `setDiscussionMode(type)`). */
  onJoin: () => void;
  /** Called when the user clicks Skip OR the countdown expires. Caller
   *  must resume the playback engine from its saved checkpoint. */
  onSkip: () => void;
}

const BREATH_MS = 3000; // silence after the last speech before the card appears
const COUNTDOWN_MS = 5000; // Join/Skip window
// Card geometry for anchor math — we align the card's horizontal center
// on the avatar's center and park its BOTTOM edge `ANCHOR_GAP_PX` above
// the avatar tile's top. These are soft: if the resulting top would
// clip the viewport we fall back to centered-bottom positioning.
const ANCHOR_GAP_PX = 16;
const CARD_MAX_WIDTH_PX = 420;
const CARD_ASSUMED_HEIGHT_PX = 160;

export const DiscussionGateCard: React.FC<DiscussionGateCardProps> = ({ onJoin, onSkip }) => {
  const pending = useMAICStageStore((s) => s.discussionPending);
  const agents = useMAICStageStore((s) => s.agents);

  // Two-stage visibility: breathing (card hidden) → visible with countdown.
  const [breathDone, setBreathDone] = useState(false);
  const breathTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const dismissTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // T1.3 — anchor to the inviting agent's roundtable-strip tile. Tracks
  // position via rAF so sidebar collapses / viewport resizes don't leave
  // the card floating. Falls back to bottom-center positioning when the
  // avatar isn't in the DOM yet (card opens before the strip mounts).
  const [anchor, setAnchor] = useState<{ left: number; top: number } | null>(null);
  const anchorRafRef = useRef<number | null>(null);

  useEffect(() => {
    // Reset when a new pending event arrives (new discussion) or clears.
    if (!pending) {
      setBreathDone(false);
      if (breathTimerRef.current) clearTimeout(breathTimerRef.current);
      if (dismissTimerRef.current) clearTimeout(dismissTimerRef.current);
      breathTimerRef.current = null;
      dismissTimerRef.current = null;
      return;
    }
    setBreathDone(false);
    if (breathTimerRef.current) clearTimeout(breathTimerRef.current);
    breathTimerRef.current = setTimeout(() => setBreathDone(true), BREATH_MS);
    return () => {
      if (breathTimerRef.current) clearTimeout(breathTimerRef.current);
      breathTimerRef.current = null;
    };
  }, [pending]);

  useEffect(() => {
    if (!breathDone || !pending) return;
    if (dismissTimerRef.current) clearTimeout(dismissTimerRef.current);
    dismissTimerRef.current = setTimeout(() => onSkip(), COUNTDOWN_MS);
    return () => {
      if (dismissTimerRef.current) clearTimeout(dismissTimerRef.current);
      dismissTimerRef.current = null;
    };
  }, [breathDone, pending, onSkip]);

  const inviter = pending?.triggerAgentId
    ? agents.find((a) => a.id === pending!.triggerAgentId)
    : pending
      ? agents.find((a) => pending.agentIds.includes(a.id)) || agents[0]
      : null;

  // rAF loop: find the inviter's tile, compute a position, and keep
  // updating until the card unmounts. We use a ref (not state) inside
  // the raf tick to avoid re-rendering every frame; we setState only
  // when the computed position actually changes.
  useLayoutEffect(() => {
    if (!breathDone || !pending || !inviter) {
      setAnchor(null);
      return;
    }
    let lastLeft = -1;
    let lastTop = -1;
    let cancelled = false;
    const tick = () => {
      if (cancelled) return;
      const tile = document.querySelector<HTMLElement>(
        `[data-testid="roundtable-agent-tile"][data-agent-id="${CSS.escape(inviter.id)}"]`,
      );
      if (!tile) {
        anchorRafRef.current = requestAnimationFrame(tick);
        return;
      }
      const rect = tile.getBoundingClientRect();
      // Align card center to avatar center. Card bottom sits
      // `ANCHOR_GAP_PX` above the tile top. If that would clip the
      // top edge of the viewport, we stop overriding anchor (null) and
      // let the fallback bottom-center CSS kick in.
      const centerX = rect.left + rect.width / 2;
      const left = Math.max(
        12,
        Math.min(window.innerWidth - 12 - CARD_MAX_WIDTH_PX, centerX - CARD_MAX_WIDTH_PX / 2),
      );
      const top = rect.top - ANCHOR_GAP_PX - CARD_ASSUMED_HEIGHT_PX;
      if (top < 12) {
        if (lastLeft !== -2) {
          lastLeft = -2;
          setAnchor(null);
        }
      } else if (left !== lastLeft || top !== lastTop) {
        lastLeft = left;
        lastTop = top;
        setAnchor({ left, top });
      }
      anchorRafRef.current = requestAnimationFrame(tick);
    };
    anchorRafRef.current = requestAnimationFrame(tick);
    return () => {
      cancelled = true;
      if (anchorRafRef.current !== null) cancelAnimationFrame(anchorRafRef.current);
      anchorRafRef.current = null;
    };
  }, [breathDone, pending, inviter]);

  if (!pending || !breathDone) return null;

  const accent = inviter?.color || '#8B5CF6';

  // Anchored positioning takes precedence; `style.left/top` pins the card
  // above the inviter's avatar. Fallback (no anchor) uses the original
  // bottom-center layout so the card still shows even when the roster
  // strip isn't mounted (e.g., presentation mode variations).
  const anchoredStyle: React.CSSProperties | undefined = anchor
    ? {
        left: anchor.left,
        top: anchor.top,
        width: `min(${CARD_MAX_WIDTH_PX}px, calc(100vw - 24px))`,
      }
    : undefined;

  return (
    <AnimatePresence>
      <motion.div
        key="discussion-gate"
        className={cn(
          anchor
            ? 'fixed z-[60] flex pointer-events-none'
            : 'absolute inset-x-0 bottom-16 z-40 flex justify-center px-4 pointer-events-none',
        )}
        style={anchoredStyle}
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: 16, scale: 0.96 }}
        transition={{ duration: 0.25, ease: [0.21, 1, 0.36, 1] }}
        role="dialog"
        aria-label="Join discussion?"
      >
        <div className="pointer-events-auto relative flex max-w-md w-full overflow-hidden rounded-xl border border-gray-200 bg-white shadow-xl">
          <div className="w-1.5 shrink-0" style={{ backgroundColor: accent }} />
          <div className="flex-1 px-4 py-3 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <MessagesSquare className="h-4 w-4" style={{ color: accent }} />
              <span
                className="text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded-full"
                style={{ backgroundColor: `${accent}1A`, color: accent }}
              >
                Discussion
              </span>
              {inviter && (
                <span
                  className="ml-auto mr-6 text-[10px] font-medium truncate"
                  style={{ color: inviter.color }}
                >
                  {inviter.name}
                </span>
              )}
            </div>
            <p className="text-sm text-gray-800 leading-relaxed line-clamp-3">
              {pending.topic || "Let's pause for a short discussion."}
            </p>
            <div className="mt-2.5 flex items-center gap-2">
              <button
                type="button"
                onClick={onJoin}
                className={cn(
                  'px-4 py-1.5 text-xs font-semibold text-white rounded-lg transition-colors',
                  'focus:outline-none focus:ring-2 focus:ring-offset-1',
                )}
                style={{
                  backgroundColor: accent,
                  // @ts-expect-error -- CSS custom property
                  '--tw-ring-color': accent,
                }}
              >
                Join
              </button>
              <button
                type="button"
                onClick={onSkip}
                className="px-3 py-1.5 text-xs font-medium text-gray-600 rounded-lg hover:bg-gray-100 transition-colors focus:outline-none"
              >
                Skip
              </button>
            </div>
          </div>
          <button
            type="button"
            onClick={onSkip}
            className="absolute top-2 right-2 p-1 rounded-full text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors focus:outline-none"
            aria-label="Skip discussion"
          >
            <X className="h-3.5 w-3.5" />
          </button>
          {/* Countdown bar */}
          <div
            className="absolute bottom-0 left-0 right-0 h-1 bg-gray-100 overflow-hidden"
            aria-hidden="true"
          >
            <motion.div
              className="h-full"
              style={{ backgroundColor: accent }}
              initial={{ width: '100%' }}
              animate={{ width: '0%' }}
              transition={{ duration: COUNTDOWN_MS / 1000, ease: 'linear' }}
            />
          </div>
        </div>
      </motion.div>
    </AnimatePresence>
  );
};
