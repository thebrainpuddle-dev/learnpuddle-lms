/**
 * SpotlightOverlay — dim mask + cutout highlighting a target wb element.
 *
 * Source: THU-MAIC/OpenMAIC main components/slide-renderer/Editor/
 *         SpotlightOverlay.tsx (172 lines, simplified — upstream
 *         animates with motion/react; we use CSS transitions per the
 *         no-new-deps rule. Coordinates are absolute pixels relative
 *         to the Whiteboard surface, not upstream's 0-100 viewBox
 *         percentages, because our frame is fixed-pixel at 1000×562
 *         and children position with literal px coords.)
 *
 * Behavior:
 *   - On mount, measures the target element via getBoundingClientRect
 *     relative to the Whiteboard surface
 *   - Re-measures on viewport resize via ResizeObserver
 *   - SVG mask: full-frame white minus a black cutout = dim everything
 *     except the target rect
 *   - Cutout has CSS `transition: x/y/width/height 500ms cubic-bezier`
 *     so a target switch (rare in Phase 2 but possible) animates
 *   - Auto-clears at 5000 ms (mirrors upstream's EFFECT_AUTO_CLEAR_MS)
 *
 * Props:
 *   - targetId: data-element-id of the target rendered inside the
 *     Whiteboard surface
 *   - dimOpacity: 0..1 mask opacity (default 0.6 per protocol)
 *   - onClear: called when the auto-clear timer fires; Stage uses
 *     this to setActiveEffect(null)
 *
 * Mounted by Stage inside the overlay slot; the surface DOM lookup
 * is via document.querySelector('[data-testid="maic-v2-whiteboard"]')
 * since there's exactly one surface in any rendered Stage tree.
 */
import { useEffect, useLayoutEffect, useState } from 'react';


export interface SpotlightOverlayProps {
  targetId: string;
  dimOpacity?: number;
  onClear?: () => void;
}


interface MeasuredRect {
  x: number;
  y: number;
  w: number;
  h: number;
}


const AUTO_CLEAR_MS = 5000;
const DEFAULT_DIM = 0.6;
const PADDING = 6;  // px around the target so the cutout has breathing room
const TRANSITION = 'x 500ms cubic-bezier(0.22, 1, 0.36, 1), y 500ms cubic-bezier(0.22, 1, 0.36, 1), width 500ms cubic-bezier(0.22, 1, 0.36, 1), height 500ms cubic-bezier(0.22, 1, 0.36, 1)';


export function SpotlightOverlay({
  targetId,
  dimOpacity = DEFAULT_DIM,
  onClear,
}: SpotlightOverlayProps) {
  const [rect, setRect] = useState<MeasuredRect | null>(null);
  const [surfaceSize, setSurfaceSize] = useState<{ w: number; h: number } | null>(null);

  // ── Measurement ────────────────────────────────────────────────
  useLayoutEffect(() => {
    const surfaceEl = document.querySelector('[data-testid="maic-v2-whiteboard"]');
    if (!surfaceEl) {
      setRect(null);
      return;
    }
    const measure = () => {
      const target = surfaceEl.querySelector(`[data-element-id="${CSS.escape(targetId)}"]`);
      const surfaceRect = surfaceEl.getBoundingClientRect();
      setSurfaceSize({ w: surfaceRect.width, h: surfaceRect.height });
      if (!target) {
        // Target hasn't mounted yet (race against the wb_draw_* fade-in)
        // — fall back to the surface center so the overlay stays visible.
        setRect({
          x: surfaceRect.width * 0.4,
          y: surfaceRect.height * 0.4,
          w: surfaceRect.width * 0.2,
          h: surfaceRect.height * 0.2,
        });
        return;
      }
      const targetRect = target.getBoundingClientRect();
      setRect({
        x: targetRect.left - surfaceRect.left,
        y: targetRect.top - surfaceRect.top,
        w: targetRect.width,
        h: targetRect.height,
      });
    };
    measure();
    // Re-measure on surface resize (responsive viewport changes).
    const observer = new ResizeObserver(measure);
    observer.observe(surfaceEl);
    return () => observer.disconnect();
  }, [targetId]);

  // ── Auto-clear ─────────────────────────────────────────────────
  useEffect(() => {
    if (!onClear) return;
    const t = setTimeout(onClear, AUTO_CLEAR_MS);
    return () => clearTimeout(t);
  }, [onClear, targetId]);

  if (!rect || !surfaceSize) return null;

  const maskId = `maic-v2-spotlight-mask-${CSS.escape(targetId)}`;
  // Cutout extents — slightly larger than the target so the
  // highlighted area has visible breathing room.
  const cutoutX = Math.max(0, rect.x - PADDING);
  const cutoutY = Math.max(0, rect.y - PADDING);
  const cutoutW = rect.w + PADDING * 2;
  const cutoutH = rect.h + PADDING * 2;

  return (
    <div
      data-testid="maic-v2-spotlight-overlay"
      data-target-id={targetId}
      className="absolute inset-0 pointer-events-none z-30"
      style={{ overflow: 'hidden' }}
    >
      <svg
        width="100%"
        height="100%"
        viewBox={`0 0 ${surfaceSize.w} ${surfaceSize.h}`}
        preserveAspectRatio="none"
        className="absolute inset-0"
      >
        <defs>
          <mask id={maskId}>
            <rect x="0" y="0" width={surfaceSize.w} height={surfaceSize.h} fill="white" />
            <rect
              data-testid="maic-v2-spotlight-cutout"
              x={cutoutX}
              y={cutoutY}
              width={cutoutW}
              height={cutoutH}
              rx={6}
              fill="black"
              style={{ transition: TRANSITION }}
            />
          </mask>
        </defs>

        {/* Dim layer — covers the full surface; mask reveals the cutout. */}
        <rect
          width={surfaceSize.w}
          height={surfaceSize.h}
          fill={`rgba(0, 0, 0, ${dimOpacity})`}
          mask={`url(#${maskId})`}
        />

        {/* Highlight border around the cutout. */}
        <rect
          data-testid="maic-v2-spotlight-border"
          x={cutoutX}
          y={cutoutY}
          width={cutoutW}
          height={cutoutH}
          rx={6}
          fill="none"
          stroke="rgba(255, 255, 255, 0.85)"
          strokeWidth={2}
          style={{ transition: TRANSITION, vectorEffect: 'non-scaling-stroke' }}
        />
      </svg>
    </div>
  );
}
