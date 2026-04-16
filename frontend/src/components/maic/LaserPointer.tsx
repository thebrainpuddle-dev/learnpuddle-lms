// src/components/maic/LaserPointer.tsx
//
// Laser pointer effect for presentations. Renders a small colored dot
// that follows the mouse cursor with a glowing trail effect using
// spring-animated motion.div.

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { motion, AnimatePresence } from 'motion/react';

// ─── Types ───────────────────────────────────────────────────────────────────

interface TrailPoint {
  x: number;
  y: number;
  id: number;
}

export interface LaserPointerProps {
  active: boolean;
  color?: string;  // default: '#ef4444' (red)
  size?: number;   // default: 12
}

// ─── Component ───────────────────────────────────────────────────────────────

export const LaserPointer = React.memo<LaserPointerProps>(
  function LaserPointer({ active, color = '#ef4444', size = 12 }) {
    const [position, setPosition] = useState({ x: 0, y: 0 });
    const [trail, setTrail] = useState<TrailPoint[]>([]);
    const idRef = useRef(0);
    const rafRef = useRef<number | null>(null);
    const trailRef = useRef<TrailPoint[]>([]);

    // ─── Mouse tracking ──────────────────────────────────────────────────
    const handleMouseMove = useCallback((e: MouseEvent) => {
      setPosition({ x: e.clientX, y: e.clientY });
      idRef.current += 1;
      const point: TrailPoint = { x: e.clientX, y: e.clientY, id: idRef.current };
      trailRef.current = [...trailRef.current.slice(-7), point];
      setTrail([...trailRef.current]);
    }, []);

    useEffect(() => {
      if (!active) {
        trailRef.current = [];
        setTrail([]);
        return;
      }

      window.addEventListener('mousemove', handleMouseMove);
      return () => {
        window.removeEventListener('mousemove', handleMouseMove);
        if (rafRef.current !== null) {
          cancelAnimationFrame(rafRef.current);
        }
      };
    }, [active, handleMouseMove]);

    if (!active) return null;

    const halfSize = size / 2;

    return (
      <div
        className="fixed inset-0 z-[60] pointer-events-none"
        aria-hidden="true"
      >
        {/* Trail dots */}
        {trail.slice(0, -1).map((point, idx) => {
          const age = 1 - idx / trail.length;
          const dotSize = size * Math.max(0.2, age * 0.5);
          return (
            <div
              key={point.id}
              className="absolute rounded-full"
              style={{
                left: point.x - dotSize / 2,
                top: point.y - dotSize / 2,
                width: dotSize,
                height: dotSize,
                backgroundColor: color,
                opacity: age * 0.3,
              }}
            />
          );
        })}

        {/* Main laser dot with spring physics */}
        <AnimatePresence>
          <motion.div
            className="absolute rounded-full"
            animate={{
              left: position.x - halfSize,
              top: position.y - halfSize,
            }}
            transition={{
              type: 'spring',
              stiffness: 500,
              damping: 30,
              mass: 0.5,
            }}
            style={{
              width: size,
              height: size,
              backgroundColor: color,
              boxShadow: `0 0 ${size}px ${size / 3}px ${color}80, 0 0 ${size * 2}px ${size / 2}px ${color}40`,
            }}
          />
        </AnimatePresence>
      </div>
    );
  },
);
