// src/components/maic/ThinkingDots.tsx
//
// Three-dot "thinking" indicator shown in the speech bubble while a
// TTS fetch is in flight and no text has arrived yet (Sprint 1 · B.3).
// Keeps the overlay visible so the audience sees the speaker bubble is
// *about* to say something, rather than the overlay popping in late.
//
// Pure CSS animation via motion — no timers, no cleanup.

import React from 'react';
import { motion } from 'motion/react';

export interface ThinkingDotsProps {
  /** Optional accent color — defaults to neutral gray. */
  color?: string;
  /** Optional className forwarded to wrapper. */
  className?: string;
}

const DOT_TRANSITION = {
  duration: 0.9,
  repeat: Infinity,
  ease: 'easeInOut' as const,
};

export const ThinkingDots = React.memo<ThinkingDotsProps>(function ThinkingDots({
  color,
  className,
}) {
  const dotColor = color || 'rgba(209, 213, 219, 0.9)';
  return (
    <div
      className={className}
      role="status"
      aria-label="Preparing speech"
      style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}
    >
      {[0, 0.15, 0.3].map((delay, idx) => (
        <motion.span
          key={idx}
          initial={{ opacity: 0.3, y: 0 }}
          animate={{ opacity: [0.3, 1, 0.3], y: [0, -2, 0] }}
          transition={{ ...DOT_TRANSITION, delay }}
          style={{
            display: 'inline-block',
            width: 5,
            height: 5,
            borderRadius: 9999,
            background: dotColor,
          }}
        />
      ))}
    </div>
  );
});
