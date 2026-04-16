// src/components/maic/ai-elements/Loader.tsx
//
// Animated spinning loader with 8-spoke SVG pattern.
// Spokes have decreasing opacity for a smooth rotation effect.

import React from 'react';
import { cn } from '../../../lib/utils';

interface LoaderProps {
  /** Size preset or custom pixel value */
  size?: 'sm' | 'md' | 'lg' | number;
  className?: string;
}

const SIZE_MAP: Record<string, number> = {
  sm: 16,
  md: 24,
  lg: 32,
};

/** Calculate spoke endpoints for a given angle (degrees). */
function spokePoints(
  angle: number,
  cx: number,
  cy: number,
  innerR: number,
  outerR: number,
): { x1: number; y1: number; x2: number; y2: number } {
  const rad = (angle * Math.PI) / 180;
  return {
    x1: cx + innerR * Math.cos(rad),
    y1: cy + innerR * Math.sin(rad),
    x2: cx + outerR * Math.cos(rad),
    y2: cy + outerR * Math.sin(rad),
  };
}

const SPOKE_COUNT = 8;
const SPOKES = Array.from({ length: SPOKE_COUNT }, (_, i) => {
  const angle = i * (360 / SPOKE_COUNT) - 90; // Start from top
  const opacity = 1 - i * (0.9 / SPOKE_COUNT); // 1.0 -> ~0.1
  const points = spokePoints(angle, 12, 12, 4, 10);
  return { ...points, opacity };
});

export const Loader = React.memo<LoaderProps>(function Loader({
  size = 'md',
  className,
}) {
  const px = typeof size === 'number' ? size : (SIZE_MAP[size] ?? 24);

  return (
    <div
      className={cn('inline-flex items-center justify-center', className)}
      role="status"
      aria-label="Loading"
    >
      <svg
        width={px}
        height={px}
        viewBox="0 0 24 24"
        fill="none"
        className="loader-spin"
      >
        {SPOKES.map((spoke, i) => (
          <line
            key={i}
            x1={spoke.x1}
            y1={spoke.y1}
            x2={spoke.x2}
            y2={spoke.y2}
            stroke="currentColor"
            strokeWidth={2}
            strokeLinecap="round"
            opacity={spoke.opacity}
          />
        ))}
      </svg>
      <style>{LOADER_STYLES}</style>
    </div>
  );
});

const LOADER_STYLES = `
@keyframes loaderSpin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
.loader-spin {
  animation: loaderSpin 0.8s steps(${SPOKE_COUNT}) infinite;
}
`;
