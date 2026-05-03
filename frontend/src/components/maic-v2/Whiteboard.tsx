/**
 * Whiteboard — fixed 1000×562 surface that hosts wb_* element renderers.
 *
 * Source: THU-MAIC/OpenMAIC main components/whiteboard/whiteboard-canvas.tsx
 *         (heavily simplified — see Phase 2 plan §"What NOT to port")
 *
 * Phase 2 scope: a static framed surface. The element registry + the
 * draw/edit/clear/delete state machine live in
 * lib/maic-v2/whiteboard-state.ts (MAIC-210.2). This file is the
 * presentation layer only.
 *
 * Phase 2 deferrals (signposted; do NOT remove until linked phase):
 *   - Phase 8+ — zoom / pan / clamp (upstream's InteractiveWhiteboardCanvas)
 *   - Phase 8+ — history popover / undo (useWhiteboardHistoryStore)
 *   - Phase 8+ — UI chrome: clear button, history button, element-count
 *                indicator (upstream components/whiteboard/index.tsx)
 *
 * Used by:
 *   - frontend/src/components/maic-v2/Stage.tsx (MAIC-217 wires this in)
 */
import type { ReactNode } from 'react';


export interface WhiteboardProps {
  /**
   * When false the surface is removed from the DOM (rather than hidden
   * via CSS) so the AgentOverlay/Transcript stack reflows without a
   * 562px gap above it. Mirrors upstream's `whiteboardOpen` state.
   */
  isOpen: boolean;

  /**
   * Element renderers; one per active wb_draw_* element. Phase 2 fills
   * this from the WhiteboardProvider's element list (MAIC-210.2).
   */
  children?: ReactNode;
}


/**
 * Whiteboard surface. The coordinate space is a fixed 1000×562 frame
 * (16:9 — matches backend protocol's wb_* coordinate bounds in
 * apps/maic/protocol/actions.py). All element renderers position
 * themselves absolutely inside this frame; the surface itself is
 * responsive via `width: 100%` + `aspect-ratio` so it scales with the
 * Stage's container width without distorting the agent's intended
 * geometry.
 */
export function Whiteboard({ isOpen, children }: WhiteboardProps) {
  if (!isOpen) return null;

  return (
    <div
      data-testid="maic-v2-whiteboard"
      data-whiteboard-open="true"
      className="relative w-full overflow-hidden rounded-lg border bg-white shadow-sm"
      style={{ aspectRatio: '1000 / 562' }}
    >
      {/*
        Inner frame at native 1000×562 resolution. Children position
        themselves with px coordinates in this frame; the parent's
        aspectRatio + width:100% scales it visually. We use absolute
        positioning rather than CSS transforms so children's
        bounding-rect measurements (used by SpotlightOverlay in
        MAIC-215) are correct without manual viewBox arithmetic.
      */}
      <div
        data-testid="maic-v2-whiteboard-frame"
        className="absolute inset-0"
        style={{
          width: '100%',
          height: '100%',
        }}
      >
        {children}
      </div>
    </div>
  );
}
