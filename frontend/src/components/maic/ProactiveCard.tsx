// src/components/maic/ProactiveCard.tsx
//
// Floating suggestion card that appears during classroom playback to prompt
// students to engage with content. Slides up from the bottom with spring
// animation and auto-dismisses after 15 seconds if not interacted with.

import React, { useEffect, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { HelpCircle, MessagesSquare, Zap, Lightbulb, X } from 'lucide-react';
import { cn } from '../../lib/utils';

// ─── Types ──────────────────────────────────────────────────────────────────

export type ProactiveCardType = 'question' | 'discussion' | 'activity' | 'reflection';

export interface ProactiveCardProps {
  /** The suggestion text */
  suggestion: string;
  /** Type of suggestion */
  type: ProactiveCardType;
  /** Agent who is suggesting (optional) */
  agentName?: string;
  agentColor?: string;
  /** Callbacks */
  onAccept: () => void;
  onDismiss: () => void;
  /** Whether the card is visible */
  visible: boolean;
  /** Optional countdown override (ms). When provided:
   *  - a visible progress bar counts down from 100% → 0%
   *  - the card auto-dismisses when the bar reaches 0
   *  - the accept button label is replaced with "Join"
   *  Used by Sprint 1 · B.5 (discussion gate) to give the student a
   *  short, explicit window to opt into a discussion. */
  countdownMs?: number;
  /** When true, render Join/Skip labels instead of the default
   *  "Let's discuss" / X combo. Implied when countdownMs is set. */
  joinSkipMode?: boolean;
}

// ─── Config Maps ────────────────────────────────────────────────────────────

const TYPE_COLORS: Record<ProactiveCardType, string> = {
  question: '#3B82F6',
  discussion: '#8B5CF6',
  activity: '#10B981',
  reflection: '#F59E0B',
};

const TYPE_ICONS: Record<ProactiveCardType, React.FC<{ className?: string; style?: React.CSSProperties }>> = {
  question: HelpCircle,
  discussion: MessagesSquare,
  activity: Zap,
  reflection: Lightbulb,
};

const TYPE_BADGE_STYLES: Record<ProactiveCardType, string> = {
  question: 'bg-blue-100 text-blue-700',
  discussion: 'bg-violet-100 text-violet-700',
  activity: 'bg-emerald-100 text-emerald-700',
  reflection: 'bg-amber-100 text-amber-700',
};

const TYPE_LABELS: Record<ProactiveCardType, string> = {
  question: 'Question',
  discussion: 'Discussion',
  activity: 'Activity',
  reflection: 'Reflection',
};

const AUTO_DISMISS_MS = 15_000;

// ─── Component ──────────────────────────────────────────────────────────────

export const ProactiveCard: React.FC<ProactiveCardProps> = ({
  suggestion,
  type,
  agentName,
  agentColor,
  onAccept,
  onDismiss,
  visible,
  countdownMs,
  joinSkipMode,
}) => {
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hasCountdown = typeof countdownMs === 'number' && countdownMs > 0;
  const dismissMs = hasCountdown ? (countdownMs as number) : AUTO_DISMISS_MS;
  const useJoinSkip = joinSkipMode || hasCountdown;
  // Forces the countdown bar to re-mount on each fresh `visible` cycle
  // so the CSS transition restarts cleanly (the bar is driven by
  // transitioning `width` from 100% → 0% over dismissMs).
  const [mountId, setMountId] = useState(0);

  // Auto-dismiss after the configured window (5s in gate mode, 15s default)
  useEffect(() => {
    if (visible) {
      setMountId((n) => n + 1);
      timerRef.current = setTimeout(() => {
        onDismiss();
      }, dismissMs);
    }
    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [visible, onDismiss, dismissMs]);

  const Icon = TYPE_ICONS[type];
  const accentColor = TYPE_COLORS[type];

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 20, scale: 0.95 }}
          transition={{ type: 'spring', stiffness: 400, damping: 30 }}
          className="pointer-events-auto max-w-md w-full max-h-[38vh] overflow-y-auto"
        >
          <div className="relative bg-white rounded-xl shadow-lg border border-gray-200 overflow-hidden flex">
            {/* Left accent bar */}
            <div
              className="w-1.5 shrink-0"
              style={{ backgroundColor: accentColor }}
            />

            {/* Content area */}
            <div className="flex-1 px-4 py-3 min-w-0">
              {/* Header row: badge + icon + dismiss */}
              <div className="flex items-center gap-2 mb-1.5">
                <Icon className="h-4 w-4 shrink-0" style={{ color: accentColor }} />
                <span
                  className={cn(
                    'text-[10px] font-semibold uppercase tracking-wide px-1.5 py-0.5 rounded-full',
                    TYPE_BADGE_STYLES[type],
                  )}
                >
                  {TYPE_LABELS[type]}
                </span>

                {agentName && (
                  <span
                    className="text-[10px] font-medium ml-auto mr-6 truncate"
                    style={{ color: agentColor || '#6B7280' }}
                  >
                    {agentName}
                  </span>
                )}
              </div>

              {/* Suggestion text */}
              <p className="text-sm text-gray-800 leading-relaxed line-clamp-3">
                {suggestion}
              </p>

              {/* Action row */}
              <div className="mt-2.5 flex items-center gap-2">
                <button
                  onClick={onAccept}
                  className="px-4 py-1.5 text-xs font-semibold text-white rounded-lg transition-colors focus:outline-none focus:ring-2 focus:ring-offset-1"
                  style={{
                    backgroundColor: accentColor,
                    // Focus ring color matches accent
                    // @ts-expect-error -- CSS custom property
                    '--tw-ring-color': accentColor,
                  }}
                >
                  {useJoinSkip ? 'Join' : "Let's discuss"}
                </button>
                {useJoinSkip && (
                  <button
                    onClick={onDismiss}
                    className="px-3 py-1.5 text-xs font-medium text-gray-600 rounded-lg hover:bg-gray-100 transition-colors focus:outline-none"
                  >
                    Skip
                  </button>
                )}
              </div>
            </div>

            {/* Dismiss X button (top-right) */}
            <button
              onClick={onDismiss}
              className="absolute top-2 right-2 p-1 rounded-full text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors focus:outline-none"
              aria-label="Dismiss suggestion"
            >
              <X className="h-3.5 w-3.5" />
            </button>

            {/* Countdown bar — only in gate mode. A motion bar animates
                from 100% → 0% width over `dismissMs`. Keyed on
                `mountId` so reopening the card restarts the bar. */}
            {hasCountdown && (
              <div
                className="absolute bottom-0 left-0 right-0 h-1 bg-gray-100 overflow-hidden"
                aria-hidden="true"
              >
                <motion.div
                  key={mountId}
                  className="h-full"
                  style={{ backgroundColor: accentColor }}
                  initial={{ width: '100%' }}
                  animate={{ width: '0%' }}
                  transition={{ duration: dismissMs / 1000, ease: 'linear' }}
                />
              </div>
            )}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};
