// src/components/maic/ai-elements/Shimmer.tsx
//
// Text shimmer loading animation using motion/react.
// Displays a gradient sweep across text to indicate loading state.

import React, { useRef, useEffect } from 'react';
import { motion } from 'motion/react';
import { cn } from '../../../lib/utils';

interface ShimmerProps {
  /** Text content to apply shimmer effect to */
  children: string;
  /** HTML element type to render */
  as?: React.ElementType;
  /** Additional CSS classes */
  className?: string;
  /** Animation duration in seconds */
  duration?: number;
  /** Gradient spread multiplier */
  spread?: number;
}

export const Shimmer = React.memo<ShimmerProps>(function Shimmer({
  children,
  as: Component = 'span',
  className,
  duration = 2,
  spread = 2,
}) {
  const MotionComponent = motion.create(Component);
  const ref = useRef<HTMLElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const animation = el.animate(
      [
        { backgroundPositionX: '100%' },
        { backgroundPositionX: '0%' },
      ],
      {
        duration: duration * 1000,
        iterations: Infinity,
        easing: 'linear',
      },
    );

    return () => animation.cancel();
  }, [duration]);

  return (
    <MotionComponent
      ref={ref}
      className={cn('inline-block', className)}
      style={{
        backgroundImage: `linear-gradient(90deg, transparent 0%, currentColor ${50 / spread}%, transparent ${100 / spread}%)`,
        backgroundSize: `${spread * 100}% 100%`,
        backgroundClip: 'text',
        WebkitBackgroundClip: 'text',
        color: 'transparent',
        WebkitTextFillColor: 'transparent',
      }}
    >
      {children}
    </MotionComponent>
  );
});
