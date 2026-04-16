// src/components/maic/Reasoning.tsx
//
// Collapsible component showing AI agent thinking/reasoning process.
// Auto-opens during thinking, displays elapsed time, and auto-closes
// after the agent finishes reasoning.

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { ChevronRight } from 'lucide-react';
import { cn } from '../../lib/utils';

interface ReasoningProps {
  thinking: boolean;
  text?: string;
  duration?: number; // final duration in seconds, provided when thinking ends
  agentName?: string;
  agentColor?: string;
}

export const Reasoning = React.memo<ReasoningProps>(function Reasoning({
  thinking,
  text,
  duration,
  agentName,
  agentColor = '#6b7280',
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const autoCloseRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ─── Timer management ──────────────────────────────────────────────

  const clearTimer = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const clearAutoClose = useCallback(() => {
    if (autoCloseRef.current) {
      clearTimeout(autoCloseRef.current);
      autoCloseRef.current = null;
    }
  }, []);

  // Auto-open when thinking starts, auto-close when it stops
  useEffect(() => {
    if (thinking) {
      setIsOpen(true);
      setElapsed(0);
      clearAutoClose();

      // Start elapsed timer (updates every 100ms)
      clearTimer();
      const start = Date.now();
      timerRef.current = setInterval(() => {
        setElapsed((Date.now() - start) / 1000);
      }, 100);
    } else {
      clearTimer();

      // Auto-close after 1 second delay when thinking finishes
      if (isOpen) {
        autoCloseRef.current = setTimeout(() => {
          setIsOpen(false);
        }, 1000);
      }
    }

    return () => {
      clearTimer();
      clearAutoClose();
    };
    // Intentionally excluding isOpen to avoid re-triggering on toggle
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [thinking]);

  // ─── Display values ────────────────────────────────────────────────

  const displayDuration = thinking ? elapsed : (duration ?? elapsed);
  const formattedTime = displayDuration.toFixed(1);

  const triggerLabel = thinking
    ? `${agentName ? `${agentName} is thinking` : 'Thinking'}...`
    : `${agentName ? `${agentName} t` : 'T'}hought for ${formattedTime}s`;

  const toggleOpen = useCallback(() => {
    setIsOpen((prev) => !prev);
  }, []);

  return (
    <div className="rounded-lg border border-gray-200 bg-gray-50/80 overflow-hidden text-sm">
      {/* Collapsible trigger */}
      <button
        type="button"
        onClick={toggleOpen}
        className={cn(
          'flex items-center gap-1.5 w-full px-3 py-1.5 text-left',
          'text-xs font-medium text-gray-500 hover:text-gray-700 hover:bg-gray-100/60',
          'transition-colors',
        )}
        aria-expanded={isOpen}
      >
        <ChevronRight
          className={cn(
            'h-3 w-3 shrink-0 transition-transform duration-200',
            isOpen && 'rotate-90',
          )}
          style={{ color: agentColor }}
        />
        <span className="flex items-center gap-1.5">
          {thinking && (
            <span
              className="inline-block h-1.5 w-1.5 rounded-full animate-pulse"
              style={{ backgroundColor: agentColor }}
            />
          )}
          {triggerLabel}
        </span>
      </button>

      {/* Collapsible content */}
      <AnimatePresence initial={false}>
        {isOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: 'easeInOut' }}
            className="overflow-hidden"
          >
            <div className="relative px-3 py-2 border-t border-gray-100">
              {/* Reasoning text */}
              <div
                className={cn(
                  'font-mono text-xs leading-relaxed text-gray-600 whitespace-pre-wrap',
                  'bg-gray-100 rounded-md px-3 py-2 max-h-40 overflow-y-auto',
                )}
              >
                {text || (thinking ? 'Processing...' : 'No reasoning text available.')}
              </div>

              {/* Shimmer overlay while thinking */}
              {thinking && (
                <div
                  className="absolute inset-0 pointer-events-none rounded-md overflow-hidden"
                  aria-hidden="true"
                >
                  <div className="shimmer-reasoning absolute inset-0" />
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Shimmer animation */}
      {thinking && (
        <style>{`
          @keyframes shimmerReasoning {
            0% { transform: translateX(-100%); }
            100% { transform: translateX(100%); }
          }
          .shimmer-reasoning {
            background: linear-gradient(
              90deg,
              transparent 0%,
              rgba(255, 255, 255, 0.3) 50%,
              transparent 100%
            );
            animation: shimmerReasoning 2s ease-in-out infinite;
          }
        `}</style>
      )}
    </div>
  );
});
