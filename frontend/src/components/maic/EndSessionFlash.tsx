// src/components/maic/EndSessionFlash.tsx
//
// T7.c — transient "session ended" card that flashes over the stage
// for ~1800ms when a discussion or QA closes. Replaces the toast-only
// close feedback with a more grounded, centered confirmation that
// matches OpenMAIC's end-flash pattern (`stage.tsx:~440`).
//
// Usage: a single always-mounted instance inside the stage viewport.
// The parent (Stage.tsx) calls `useEndSessionFlash().show('discussion')`
// whenever a discussion panel closes; hook handles timing + auto-exit.

import React, { useCallback, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { MessagesSquare, CheckCircle2 } from 'lucide-react';
import { cn } from '../../lib/utils';

export type EndSessionKind = 'discussion' | 'qa' | 'roundtable' | 'classroom';

const FLASH_DURATION_MS = 1800;

const KIND_COPY: Record<EndSessionKind, { title: string; sub: string }> = {
  discussion: { title: 'Discussion ended', sub: 'Back to the lecture' },
  qa: { title: 'Q&A complete', sub: 'Back to the lecture' },
  roundtable: { title: 'Roundtable ended', sub: 'Back to the lecture' },
  classroom: { title: 'Class ended', sub: "That's a wrap" },
};

export function useEndSessionFlash() {
  const [kind, setKind] = useState<EndSessionKind | null>(null);
  const show = useCallback((k: EndSessionKind) => {
    setKind(k);
    window.setTimeout(() => setKind((current) => (current === k ? null : current)), FLASH_DURATION_MS);
  }, []);
  return { kind, show };
}

export interface EndSessionFlashProps {
  kind: EndSessionKind | null;
}

export const EndSessionFlash: React.FC<EndSessionFlashProps> = ({ kind }) => {
  const copy = kind ? KIND_COPY[kind] : null;
  return (
    <AnimatePresence>
      {copy && (
        <motion.div
          key="end-session-flash"
          className={cn(
            'absolute inset-0 z-[55] flex items-center justify-center',
            'pointer-events-none',
          )}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.25, ease: 'easeOut' }}
          role="status"
          aria-live="polite"
        >
          <motion.div
            className="flex items-center gap-3 rounded-2xl bg-white/95 backdrop-blur-md border border-white/30 px-5 py-3 shadow-2xl"
            initial={{ y: 12, scale: 0.96 }}
            animate={{ y: 0, scale: 1 }}
            exit={{ y: -6, scale: 0.98 }}
            transition={{ duration: 0.3, ease: [0.21, 1, 0.36, 1] }}
          >
            <span className="relative flex h-9 w-9 items-center justify-center rounded-full bg-indigo-50">
              <span className="absolute inset-0 rounded-full bg-indigo-200/70 animate-ping" />
              {kind === 'classroom' ? (
                <CheckCircle2 className="relative h-5 w-5 text-indigo-600" />
              ) : (
                <MessagesSquare className="relative h-5 w-5 text-indigo-600" />
              )}
            </span>
            <div className="min-w-0">
              <p className="text-sm font-semibold text-gray-900 leading-tight">{copy.title}</p>
              <p className="text-xs text-gray-500 leading-tight mt-0.5">{copy.sub}</p>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};
