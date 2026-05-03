/**
 * Whiteboard — fixed 1000×562 surface that renders the WhiteboardProvider's
 * element list.
 *
 * Source: THU-MAIC/OpenMAIC main components/whiteboard/whiteboard-canvas.tsx
 *         (heavily simplified — see Phase 2 plan §"What NOT to port")
 *
 * State-driven: reads {isOpen, isClearing, elements} from the
 * WhiteboardProvider context (MAIC-210.2) — there is no prop API.
 * Mounting outside a provider throws.
 *
 * Element type → renderer mapping is here so the renderer files stay
 * isolated and per-test focused. As of MAIC-214.1 every wb_draw_*
 * element type has a real renderer; the `default` branch returns null
 * for forward-compat with future protocol additions.
 *
 * Phase 2 deferrals (signposted; do NOT remove until linked phase):
 *   - Phase 8+ — zoom / pan / clamp (upstream's InteractiveWhiteboardCanvas)
 *   - Phase 8+ — history popover / undo (useWhiteboardHistoryStore)
 *   - Phase 8+ — UI chrome: clear button, history button, element-count
 *                indicator (upstream components/whiteboard/index.tsx)
 *   - Phase 8+ — cascade-clear per-element fade animation (uses
 *                isClearing flag once CSS keyframes are wired)
 */
import {
  useWhiteboardState,
  type WhiteboardElement,
} from '../../lib/maic-v2/whiteboard-state';

import { ChartElement } from './whiteboard/ChartElement';
import { CodeElement } from './whiteboard/CodeElement';
import { LatexElement } from './whiteboard/LatexElement';
import { LineElement } from './whiteboard/LineElement';
import { ShapeElement } from './whiteboard/ShapeElement';
import { TableElement } from './whiteboard/TableElement';
import { TextElement } from './whiteboard/TextElement';


function elementKeyFor(el: WhiteboardElement): string {
  const withId = el as { elementId?: string; id: string };
  return withId.elementId ?? withId.id;
}


function renderElement(element: WhiteboardElement) {
  const key = elementKeyFor(element);
  switch (element.type) {
    case 'wb_draw_text':
      return <TextElement key={key} element={element} />;
    case 'wb_draw_shape':
      return <ShapeElement key={key} element={element} />;
    case 'wb_draw_line':
      return <LineElement key={key} element={element} />;
    case 'wb_draw_table':
      return <TableElement key={key} element={element} />;
    case 'wb_draw_latex':
      return <LatexElement key={key} element={element} />;
    case 'wb_draw_chart':
      return <ChartElement key={key} element={element} />;
    case 'wb_draw_code':
      return <CodeElement key={key} element={element} />;

    default:
      return null;
  }
}


/**
 * Whiteboard surface. Coordinate space is a fixed 1000×562 frame
 * (16:9 — matches backend protocol's wb_* coordinate bounds in
 * apps/maic/protocol/actions.py). All element renderers position
 * themselves absolutely inside this frame; the surface itself is
 * responsive via `width: 100%` + `aspect-ratio` so it scales with the
 * Stage's container width without distorting the agent's intended
 * geometry.
 */
export function Whiteboard() {
  const { isOpen, isClearing, elements } = useWhiteboardState();

  if (!isOpen) return null;

  return (
    <div
      data-testid="maic-v2-whiteboard"
      data-whiteboard-open="true"
      data-whiteboard-clearing={isClearing ? 'true' : 'false'}
      data-whiteboard-element-count={elements.length}
      className="relative w-full overflow-hidden rounded-lg border bg-white shadow-sm"
      style={{
        aspectRatio: '1000 / 562',
        opacity: isClearing ? 0.3 : 1,
        transition: 'opacity 380ms ease-out',
      }}
    >
      {/*
        Inner frame at native 1000×562 resolution. Children position
        themselves with px coordinates in this frame; the parent's
        aspectRatio + width:100% scales it visually. Absolute
        positioning (rather than CSS transforms) so children's
        getBoundingClientRect measurements work without manual viewBox
        arithmetic — critical for SpotlightOverlay (MAIC-215).
      */}
      <div
        data-testid="maic-v2-whiteboard-frame"
        className="absolute inset-0"
        style={{ width: '100%', height: '100%' }}
      >
        {elements.map(renderElement)}
      </div>
    </div>
  );
}
