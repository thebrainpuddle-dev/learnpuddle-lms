// src/components/maic/AgentRevealModal.tsx
//
// Porting T1.2 — blocking agent-reveal modal.
//
// When the wizard finishes generating the agent roster, the teacher
// sees this modal: full-backdrop blur, cards face-down over a violet
// gradient, then flipping one at a time (first card at 400ms, each
// subsequent card every 500ms) with a 3D `rotateY: 180 → 0` on an
// "emphasized decelerate" easing. The modal blocks until the user
// clicks Continue — matching OpenMAIC's Promise-gated handoff so the
// moment feels earned rather than incidental.
//
// After Continue, the parent unmounts the modal and lets the teacher
// edit/regenerate individual agents. The modal is strictly for the
// *reveal*.

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { Sparkles } from 'lucide-react';
import type { MAICAgent } from '../../types/maic';
import { AgentAvatar } from './AgentAvatar';
import { cn } from '../../lib/utils';

export interface AgentRevealModalProps {
  /** Full agent roster to reveal. Order is respected. */
  agents: MAICAgent[];
  /** Opens the modal. Parent controls lifecycle so regenerate flows
   *  can re-open without re-mounting the surrounding wizard step. */
  open: boolean;
  /** Fires when the user clicks Continue. Parent should close the modal
   *  and proceed with generation / editing. */
  onContinue: () => void;
}

// Timing constants tuned to match OpenMAIC's feel.
const FIRST_FLIP_DELAY_MS = 400;
const BETWEEN_FLIPS_MS = 500;
const FLIP_DURATION_MS = 600;
// Emphasized decelerate (Material/iOS cubic-bezier) — the flip settles
// crisply rather than bouncing.
const FLIP_EASE: [number, number, number, number] = [0.23, 1, 0.32, 1];

function useStaggeredReveal(count: number, open: boolean): number {
  // Returns the index of the NEXT card to flip. Cards with index < revealed
  // are face-up; the rest are face-down.
  const [revealed, setRevealed] = useState(0);
  useEffect(() => {
    if (!open) {
      setRevealed(0);
      return;
    }
    if (count === 0) return;
    const timers: ReturnType<typeof setTimeout>[] = [];
    for (let i = 0; i < count; i++) {
      const delay = FIRST_FLIP_DELAY_MS + i * BETWEEN_FLIPS_MS;
      timers.push(setTimeout(() => setRevealed((r) => Math.max(r, i + 1)), delay));
    }
    return () => {
      for (const t of timers) clearTimeout(t);
    };
  }, [open, count]);
  return revealed;
}

export const AgentRevealModal: React.FC<AgentRevealModalProps> = ({
  agents,
  open,
  onContinue,
}) => {
  const revealed = useStaggeredReveal(agents.length, open);
  const allFlipped = revealed >= agents.length && agents.length > 0;
  const continueRef = useRef<HTMLButtonElement | null>(null);

  const handleContinue = useCallback(() => {
    if (allFlipped) {
      onContinue();
    }
  }, [allFlipped, onContinue]);

  useEffect(() => {
    if (open && allFlipped) {
      continueRef.current?.focus();
    }
  }, [allFlipped, open]);

  // Progress dots at the bottom fill as cards flip.
  const dots = useMemo(
    () =>
      agents.map((_, i) => (
        <span
          key={i}
          className={cn(
            'h-1.5 w-1.5 rounded-full transition-colors duration-200',
            i < revealed ? 'bg-indigo-500' : 'bg-slate-300',
          )}
        />
      )),
    [agents, revealed],
  );

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          key="agent-reveal-modal"
          className="fixed inset-0 z-[90] flex items-center justify-center overflow-y-auto bg-black/45 px-4 py-4 backdrop-blur-md"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.25, ease: 'easeOut' }}
          role="dialog"
          aria-modal="true"
          aria-label="Meet your classroom agents"
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault();
              handleContinue();
            }
          }}
        >
          <motion.div
            className="relative flex max-h-[calc(100vh-2rem)] w-full max-w-5xl flex-col gap-6 overflow-y-auto rounded-2xl bg-white p-6 shadow-2xl"
            initial={{ scale: 0.96, y: 8 }}
            animate={{ scale: 1, y: 0 }}
            transition={{ duration: 0.28, ease: FLIP_EASE }}
          >
            <div className="text-center">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-indigo-600">
                Meet your classroom
              </p>
              <h2 className="mt-1 text-xl font-semibold text-slate-900">
                Your AI agents are ready
              </h2>
              <p className="mt-1 text-sm text-slate-500">
                Each one brings a different voice, perspective, and teaching style.
              </p>
            </div>

            {/* Cards — perspective on the grid so the 3D flip reads */}
            <div
              className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4"
              style={{ perspective: 1400 }}
            >
              {agents.map((agent, idx) => {
                const isRevealed = idx < revealed;
                return (
                  <div
                    key={agent.id}
                    className="relative aspect-[3/4]"
                    style={{ transformStyle: 'preserve-3d' }}
                  >
                    <motion.div
                      className="relative h-full w-full"
                      style={{ transformStyle: 'preserve-3d' }}
                      initial={false}
                      animate={{ rotateY: isRevealed ? 0 : 180 }}
                      transition={{
                        duration: FLIP_DURATION_MS / 1000,
                        ease: FLIP_EASE,
                      }}
                    >
                      {/* Back (face-down) — gradient with a Sparkles + ? */}
                      <div
                        className="absolute inset-0 flex flex-col items-center justify-center rounded-xl"
                        style={{
                          backfaceVisibility: 'hidden',
                          transform: 'rotateY(180deg)',
                          background:
                            'linear-gradient(160deg, #6366F1 0%, #A855F7 55%, #6366F1 100%)',
                          boxShadow:
                            '0 8px 18px -10px rgba(99,102,241,0.45), inset 0 0 0 1px rgba(255,255,255,0.18)',
                        }}
                      >
                        <Sparkles className="h-8 w-8 text-white/90" />
                        <span className="mt-2 text-3xl font-bold text-white/85">?</span>
                      </div>

                      {/* Front (face-up) — agent portrait + name + role */}
                      <div
                        className="absolute inset-0 flex flex-col items-center justify-center gap-3 rounded-xl bg-white p-4"
                        style={{
                          backfaceVisibility: 'hidden',
                          boxShadow:
                            '0 6px 16px -10px rgba(15,23,42,0.3), inset 0 0 0 2px ' + (agent.color || '#6366F1') + '33',
                        }}
                      >
                        <AgentAvatar agent={agent} size="lg" />
                        <div className="text-center">
                          <p className="text-sm font-semibold text-slate-900 line-clamp-1">
                            {agent.name}
                          </p>
                          <p
                            className="mt-0.5 text-[11px] font-medium uppercase tracking-wide line-clamp-1"
                            style={{ color: agent.color || '#6366F1' }}
                          >
                            {agent.role.replace('_', ' ')}
                          </p>
                        </div>
                        {agent.personality && (
                          <p className="text-center text-[11px] text-slate-500 line-clamp-3">
                            {agent.personality}
                          </p>
                        )}
                      </div>
                    </motion.div>
                  </div>
                );
              })}
            </div>

            {/* Progress dots */}
            <div className="flex items-center justify-center gap-1.5">{dots}</div>

            {/* Continue — disabled until every card has flipped so the
                reveal always plays fully. Skip is intentionally NOT
                offered; the Promise-gated pattern means the teacher
                always sees the full cast before proceeding. */}
            <div className="-mx-6 -mb-6 flex justify-center border-t border-slate-100 bg-white px-6 py-4">
              <button
                ref={continueRef}
                data-testid="agent-reveal-continue"
                type="button"
                onClick={handleContinue}
                onPointerUp={handleContinue}
                disabled={!allFlipped}
                aria-busy={!allFlipped}
                className={cn(
                  'inline-flex items-center gap-2 rounded-lg px-5 py-2.5 text-sm font-semibold',
                  'focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500',
                  'transition-colors',
                  allFlipped
                    ? 'bg-indigo-600 text-white hover:bg-indigo-700'
                    : 'bg-slate-100 text-slate-400 cursor-not-allowed',
                )}
              >
                Continue
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};
