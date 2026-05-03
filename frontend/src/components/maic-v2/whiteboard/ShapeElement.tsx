/**
 * ShapeElement — renders a wb_draw_shape element (rectangle/circle/triangle).
 *
 * Source: THU-MAIC/OpenMAIC main lib/action/engine.ts:47-51 (SHAPE_PATHS
 *         constants) + components/slide-renderer/components/element/
 *         ShapeElement/BaseShapeElement.tsx (simplified: no gradient,
 *         no pattern, no outline, no shadow, no flip — Phase 2 protocol
 *         only ships shape + fillColor).
 *
 * Wire shape (apps/maic/protocol/actions.py WbDrawShapeAction):
 *   id, elementId?, shape, x, y, width, height, fillColor?
 *
 * Geometry: SVG paths are authored in a 1000×1000 viewBox; we scale to
 * the element's actual width/height via a group transform (matches
 * upstream engine.ts:382-386 transform-scale pattern).
 */
import type { Action } from '../../../lib/maic-v2/action-types';

type ShapeAction = Extract<Action, { type: 'wb_draw_shape' }>;

/** SHAPE_PATHS verbatim from OpenMAIC lib/action/engine.ts:47-51. */
const SHAPE_PATHS: Record<ShapeAction['shape'], string> = {
  rectangle: 'M 0 0 L 1000 0 L 1000 1000 L 0 1000 Z',
  circle: 'M 500 0 A 500 500 0 1 1 499 0 Z',
  triangle: 'M 500 0 L 1000 1000 L 0 1000 Z',
};

const DEFAULT_FILL = '#5b9bd5';

export interface ShapeElementProps {
  element: ShapeAction;
}

export function ShapeElement({ element }: ShapeElementProps) {
  const fill = element.fillColor ?? DEFAULT_FILL;
  const elementKey = element.elementId ?? element.id;
  const path = SHAPE_PATHS[element.shape] ?? SHAPE_PATHS.rectangle;

  return (
    <div
      data-testid="maic-v2-wb-shape"
      data-element-id={elementKey}
      data-shape={element.shape}
      className="absolute"
      style={{
        top: `${element.y}px`,
        left: `${element.x}px`,
        width: `${element.width}px`,
        height: `${element.height}px`,
      }}
    >
      <svg
        width={element.width}
        height={element.height}
        viewBox="0 0 1000 1000"
        preserveAspectRatio="none"
        className="block"
      >
        <path d={path} fill={fill} />
      </svg>
    </div>
  );
}
