/**
 * LaserOverlay — animated laser-pointer dot flying from the nearest
 * corner to a target wb element's center.
 *
 * Source: THU-MAIC/OpenMAIC main components/slide-renderer/Editor/
 *         LaserOverlay.tsx (84 lines, simplified — upstream uses
 *         motion/react; we use CSS transitions + keyframes per the
 *         no-new-deps rule).
 *
 * Behavior:
 *   - Mount → measure target via getBoundingClientRect inside the
 *     Whiteboard surface
 *   - Pick the nearest corner (off-screen) as the start position
 *   - On a single requestAnimationFrame tick, flip to the target
 *     center → CSS `transition: top, left 500ms cubic-bezier`
 *     animates the fly-in
 *   - Light dot 5×5 px with a continuous pulse ring via
 *     @keyframes maic-v2-laser-pulse (defined inline as a <style>
 *     because we don't have a global CSS file for one-off keyframes
 *     and Tailwind 3 in this repo doesn't have arbitrary @keyframes
 *     plugins enabled)
 *   - Auto-clears at 5000 ms (mirrors upstream's EFFECT_AUTO_CLEAR_MS)
 *
 * Race-safe fallback: if the target isn't yet in the DOM (laser
 * fires before the wb_draw_* fade-in completes), centers on the
 * surface midpoint so the overlay is still visible. The
 * ResizeObserver will lock onto the real target if/when it appears.
 *
 * Mounted by Stage in the same overlay slot as SpotlightOverlay.
 */
import { useEffect, useLayoutEffect, useState } from 'react';


export interface LaserOverlayProps {
  targetId: string;
  color?: string;
  onClear?: () => void;
}


interface MeasuredCenter {
  cx: number;
  cy: number;
  surfaceW: number;
  surfaceH: number;
}


const AUTO_CLEAR_MS = 5000;
const FLY_MS = 500;
const FADE_MS = 150;
const DEFAULT_COLOR = '#ff3b30';
const DOT_SIZE = 10;  // px


export function LaserOverlay({
  targetId,
  color = DEFAULT_COLOR,
  onClear,
}: LaserOverlayProps) {
  const [center, setCenter] = useState<MeasuredCenter | null>(null);
  const [arrived, setArrived] = useState(false);

  // ── Measurement ────────────────────────────────────────────────
  useLayoutEffect(() => {
    const surfaceEl = document.querySelector('[data-testid="maic-v2-whiteboard"]');
    if (!surfaceEl) {
      setCenter(null);
      return;
    }
    const measure = () => {
      const target = surfaceEl.querySelector(`[data-element-id="${CSS.escape(targetId)}"]`);
      const surfaceRect = surfaceEl.getBoundingClientRect();
      if (!target) {
        // Race-safe fallback: surface midpoint
        setCenter({
          cx: surfaceRect.width / 2,
          cy: surfaceRect.height / 2,
          surfaceW: surfaceRect.width,
          surfaceH: surfaceRect.height,
        });
        return;
      }
      const targetRect = target.getBoundingClientRect();
      setCenter({
        cx: targetRect.left - surfaceRect.left + targetRect.width / 2,
        cy: targetRect.top - surfaceRect.top + targetRect.height / 2,
        surfaceW: surfaceRect.width,
        surfaceH: surfaceRect.height,
      });
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(surfaceEl);
    return () => observer.disconnect();
  }, [targetId]);

  // ── Fly-in trigger ────────────────────────────────────────────
  // Render once at the start corner with `arrived=false`, then on the
  // next frame flip to `arrived=true` so CSS transition runs.
  useEffect(() => {
    if (!center) return;
    setArrived(false);
    const raf = requestAnimationFrame(() => setArrived(true));
    return () => cancelAnimationFrame(raf);
  }, [center, targetId]);

  // ── Auto-clear ─────────────────────────────────────────────────
  useEffect(() => {
    if (!onClear) return;
    const t = setTimeout(onClear, AUTO_CLEAR_MS);
    return () => clearTimeout(t);
  }, [onClear, targetId]);

  if (!center) return null;

  // Pick nearest corner (off-surface by 20px so the dot enters from
  // truly outside the visible frame).
  const startX = center.cx > center.surfaceW / 2 ? center.surfaceW + 20 : -20;
  const startY = center.cy > center.surfaceH / 2 ? center.surfaceH + 20 : -20;

  const x = arrived ? center.cx : startX;
  const y = arrived ? center.cy : startY;

  return (
    <div
      data-testid="maic-v2-laser-overlay"
      data-target-id={targetId}
      className="absolute inset-0 pointer-events-none z-30"
      style={{ overflow: 'hidden' }}
    >
      {/* Inline keyframes — Tailwind 3 in this repo doesn't expose a
          one-off @keyframes utility and adding a plugin for one
          animation feels heavy. The id is namespaced. */}
      <style>{`
        @keyframes maic-v2-laser-pulse {
          0%   { transform: scale(1);   opacity: 0.6; }
          80%  { transform: scale(2.4); opacity: 0;   }
          100% { transform: scale(2.4); opacity: 0;   }
        }
      `}</style>

      <div
        data-testid="maic-v2-laser-dot"
        style={{
          position: 'absolute',
          left: `${x}px`,
          top: `${y}px`,
          width: `${DOT_SIZE}px`,
          height: `${DOT_SIZE}px`,
          marginLeft: `-${DOT_SIZE / 2}px`,
          marginTop: `-${DOT_SIZE / 2}px`,
          opacity: arrived ? 1 : 0,
          transition: `left ${FLY_MS}ms cubic-bezier(0.22, 1, 0.36, 1), top ${FLY_MS}ms cubic-bezier(0.22, 1, 0.36, 1), opacity ${FADE_MS}ms ease-out`,
        }}
      >
        {/* Pulse ring — continuous animation via CSS keyframes. */}
        <div
          data-testid="maic-v2-laser-ring"
          style={{
            position: 'absolute',
            inset: 0,
            borderRadius: '50%',
            border: `1.5px solid ${color}`,
            animation: 'maic-v2-laser-pulse 1.5s ease-out infinite',
          }}
        />
        {/* Solid dot core. */}
        <div
          style={{
            position: 'absolute',
            inset: 0,
            borderRadius: '50%',
            backgroundColor: color,
            boxShadow: `0 0 8px 2px ${color}60`,
          }}
        />
      </div>
    </div>
  );
}
