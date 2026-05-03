/**
 * LineElement — renders a wb_draw_line element with optional arrow markers.
 *
 * Source: THU-MAIC/OpenMAIC main components/slide-renderer/components/
 *         element/LineElement/BaseLineElement.tsx (lines 1-146;
 *         simplified: no stroke-drawing animation, no shadow, no
 *         dotted style — Phase 2 protocol only ships solid + dashed).
 *
 * Wire shape (apps/maic/protocol/actions.py WbDrawLineAction):
 *   id, elementId?, startX, startY, endX, endY, color?, width?, style?,
 *   points?
 *
 * Geometry: each line gets its own absolute-positioned SVG sized to
 * the line's bounding box (max(|Δx|, 24) × max(|Δy|, 24)) so DOM
 * measurement of the wrapper matches the line's visual extent — this
 * matters for SpotlightOverlay (MAIC-215). Mirrors upstream's
 * BaseLineElement svgWidth/Height computation (lines 26-34).
 *
 * Phase 2 deferral: stroke-drawing animation (upstream lines 50-84) —
 * the agent paces the timeline via the action's wait time anyway.
 */
import type { Action } from '../../../lib/maic-v2/action-types';

type LineAction = Extract<Action, { type: 'wb_draw_line' }>;

const DEFAULT_COLOR = '#333333';
const DEFAULT_WIDTH = 2;
const MIN_AXIS_PX = 24; // upstream BaseLineElement lines 27,32

export interface LineElementProps {
  element: LineAction;
}

export function LineElement({ element }: LineElementProps) {
  const color = element.color ?? DEFAULT_COLOR;
  const width = element.width ?? DEFAULT_WIDTH;
  const style = element.style ?? 'solid';
  const points = element.points ?? ['', ''];
  const elementKey = element.elementId ?? element.id;

  const minX = Math.min(element.startX, element.endX);
  const minY = Math.min(element.startY, element.endY);
  const dx = Math.abs(element.endX - element.startX);
  const dy = Math.abs(element.endY - element.startY);
  const svgWidth = Math.max(dx, MIN_AXIS_PX);
  const svgHeight = Math.max(dy, MIN_AXIS_PX);

  // Translate the line's start/end into the local SVG coordinate space.
  const x1 = element.startX - minX;
  const y1 = element.startY - minY;
  const x2 = element.endX - minX;
  const y2 = element.endY - minY;

  // Mirrors upstream BaseLineElement lines 36-43 — proportional to
  // stroke width so dashes scale visually.
  const dashArray =
    style === 'dashed'
      ? width <= 8
        ? `${width * 5} ${width * 2.5}`
        : `${width * 5} ${width * 1.5}`
      : undefined;

  const markerStartId = `maic-v2-arrow-${elementKey}-start`;
  const markerEndId = `maic-v2-arrow-${elementKey}-end`;
  const wantStartArrow = points[0] === 'arrow';
  const wantEndArrow = points[1] === 'arrow';

  return (
    <div
      data-testid="maic-v2-wb-line"
      data-element-id={elementKey}
      className="absolute"
      style={{
        top: `${minY}px`,
        left: `${minX}px`,
        width: `${svgWidth}px`,
        height: `${svgHeight}px`,
      }}
    >
      <svg
        width={svgWidth}
        height={svgHeight}
        viewBox={`0 0 ${svgWidth} ${svgHeight}`}
        overflow="visible"
        className="block"
      >
        <defs>
          {wantStartArrow && (
            <ArrowMarker id={markerStartId} color={color} orientation="auto-start-reverse" />
          )}
          {wantEndArrow && (
            <ArrowMarker id={markerEndId} color={color} orientation="auto" />
          )}
        </defs>
        <line
          x1={x1}
          y1={y1}
          x2={x2}
          y2={y2}
          stroke={color}
          strokeWidth={width}
          strokeDasharray={dashArray}
          strokeLinecap="butt"
          markerStart={wantStartArrow ? `url(#${markerStartId})` : undefined}
          markerEnd={wantEndArrow ? `url(#${markerEndId})` : undefined}
        />
      </svg>
    </div>
  );
}

interface ArrowMarkerProps {
  id: string;
  color: string;
  orientation: 'auto' | 'auto-start-reverse';
}

/**
 * Inline arrow marker. Sized in user-space units so the arrowhead is
 * visually proportional to the line's stroke width via markerWidth /
 * markerHeight set by the parent. Default 6×6 marker viewBox; the
 * marker is positioned at the line's endpoint via refX=5.
 */
function ArrowMarker({ id, color, orientation }: ArrowMarkerProps) {
  return (
    <marker
      id={id}
      viewBox="0 0 10 10"
      refX="9"
      refY="5"
      markerWidth="6"
      markerHeight="6"
      orient={orientation}
      markerUnits="strokeWidth"
    >
      <path d="M 0 0 L 10 5 L 0 10 z" fill={color} />
    </marker>
  );
}
