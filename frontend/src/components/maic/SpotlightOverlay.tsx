// src/components/maic/SpotlightOverlay.tsx
//
// Visual spotlight effect that dims everything except a circular area
// following the mouse/touch cursor. Uses CSS radial-gradient masking
// for the effect. Also supports a laser pointer mode that renders a
// small colored dot with a trailing tail.

import React, { useState, useCallback, useRef, useEffect } from 'react';

interface SpotlightOverlayProps {
  active: boolean;
  onToggle: () => void;
  laserActive?: boolean;
  laserColor?: string;
}

const SPOTLIGHT_RADIUS = 120;
const LASER_SIZE = 10;
const LASER_TRAIL_LENGTH = 8;

interface TrailPoint {
  x: number;
  y: number;
  t: number;
}

export const SpotlightOverlay = React.memo<SpotlightOverlayProps>(function SpotlightOverlay({
  active,
  onToggle,
  laserActive = false,
  laserColor = '#EF4444',
}) {
  const overlayRef = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const trailRef = useRef<TrailPoint[]>([]);
  const [trail, setTrail] = useState<TrailPoint[]>([]);
  const rafRef = useRef<number | null>(null);

  const handleMove = useCallback((e: React.MouseEvent | React.TouchEvent) => {
    const el = overlayRef.current;
    if (!el) return;

    const rect = el.getBoundingClientRect();
    let clientX: number;
    let clientY: number;

    if ('touches' in e) {
      if (e.touches.length === 0) return;
      clientX = e.touches[0].clientX;
      clientY = e.touches[0].clientY;
    } else {
      clientX = e.clientX;
      clientY = e.clientY;
    }

    const x = clientX - rect.left;
    const y = clientY - rect.top;

    setPosition({ x, y });

    if (laserActive) {
      const now = Date.now();
      trailRef.current = [
        ...trailRef.current.filter((p) => now - p.t < 300).slice(-LASER_TRAIL_LENGTH),
        { x, y, t: now },
      ];
      setTrail([...trailRef.current]);
    }
  }, [laserActive]);

  // Clean up old trail points on an animation frame loop when laser is active
  useEffect(() => {
    if (!laserActive || !active) {
      trailRef.current = [];
      setTrail([]);
      return;
    }

    let running = true;
    const tick = () => {
      if (!running) return;
      const now = Date.now();
      const filtered = trailRef.current.filter((p) => now - p.t < 300);
      if (filtered.length !== trailRef.current.length) {
        trailRef.current = filtered;
        setTrail([...filtered]);
      }
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);

    return () => {
      running = false;
      if (rafRef.current !== null) {
        cancelAnimationFrame(rafRef.current);
      }
    };
  }, [laserActive, active]);

  if (!active && !laserActive) return null;

  // Laser pointer mode
  if (laserActive) {
    return (
      <div
        ref={overlayRef}
        className="absolute inset-0 z-30 cursor-none"
        onMouseMove={handleMove}
        onTouchMove={handleMove}
        onClick={onToggle}
        role="presentation"
        aria-hidden="true"
      >
        {/* Trail dots */}
        {trail.map((point, i) => {
          const age = (Date.now() - point.t) / 300; // 0..1
          const opacity = Math.max(0, 1 - age) * 0.5;
          const size = LASER_SIZE * Math.max(0.3, 1 - age * 0.7);
          return (
            <div
              key={`${point.t}-${i}`}
              className="absolute rounded-full pointer-events-none"
              style={{
                left: point.x - size / 2,
                top: point.y - size / 2,
                width: size,
                height: size,
                backgroundColor: laserColor,
                opacity,
                transition: 'opacity 0.1s ease-out',
              }}
            />
          );
        })}
        {/* Main laser dot */}
        <div
          className="absolute rounded-full pointer-events-none"
          style={{
            left: position.x - LASER_SIZE / 2,
            top: position.y - LASER_SIZE / 2,
            width: LASER_SIZE,
            height: LASER_SIZE,
            backgroundColor: laserColor,
            boxShadow: `0 0 8px 2px ${laserColor}80, 0 0 16px 4px ${laserColor}40`,
          }}
        />
      </div>
    );
  }

  // Spotlight mode
  return (
    <div
      ref={overlayRef}
      className="absolute inset-0 z-30 cursor-none"
      onMouseMove={handleMove}
      onTouchMove={handleMove}
      onClick={onToggle}
      role="presentation"
      aria-hidden="true"
      style={{
        background: `radial-gradient(circle ${SPOTLIGHT_RADIUS}px at ${position.x}px ${position.y}px, transparent 0%, transparent 100%), rgba(0, 0, 0, 0.7)`,
        maskImage: `radial-gradient(circle ${SPOTLIGHT_RADIUS}px at ${position.x}px ${position.y}px, transparent 80%, black 100%)`,
        WebkitMaskImage: `radial-gradient(circle ${SPOTLIGHT_RADIUS}px at ${position.x}px ${position.y}px, transparent 80%, black 100%)`,
        mixBlendMode: 'multiply',
      }}
    />
  );
});
