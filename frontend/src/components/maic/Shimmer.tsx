// src/components/maic/Shimmer.tsx
//
// Animated shimmer placeholder for "content is loading" states
// (Sprint 3 · C.1). A moving light streak sweeps across a muted base
// gradient — more alive than Tailwind's animate-pulse, less visually
// loud than a spinner on top of every image.
//
// Usage:
//   <Shimmer className="absolute inset-0 rounded-lg" />
// or
//   <Shimmer className="h-4 w-24 rounded-full" />
//
// The shimmer is purely decorative — it does NOT render children. Put
// it behind your content with absolute positioning, or size it as its
// own block when used as a skeleton line.

import React from 'react';
import { cn } from '../../lib/utils';

export interface ShimmerProps {
  /** Forwarded to the outer element. */
  className?: string;
  /** Muted base color. Keep subtle so the streak can read. */
  baseClassName?: string;
  /** Override the streak intensity. Defaults to a soft white. */
  streakColor?: string;
}

export const Shimmer = React.memo<ShimmerProps>(function Shimmer({
  className,
  baseClassName = 'bg-gray-100',
  streakColor = 'rgba(255, 255, 255, 0.65)',
}) {
  return (
    <div
      aria-hidden="true"
      className={cn('relative overflow-hidden', baseClassName, className)}
    >
      <div
        className="absolute inset-y-0 -left-[40%] w-[40%]"
        style={{
          background: `linear-gradient(90deg, transparent 0%, ${streakColor} 50%, transparent 100%)`,
          animation: 'maic-shimmer 1.4s ease-in-out infinite',
        }}
      />
      <style>{`
        @keyframes maic-shimmer {
          0% { transform: translateX(0%); }
          100% { transform: translateX(350%); }
        }
      `}</style>
    </div>
  );
});
