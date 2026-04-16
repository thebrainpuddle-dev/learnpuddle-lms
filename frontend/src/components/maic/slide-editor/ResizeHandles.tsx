// src/components/maic/slide-editor/ResizeHandles.tsx
//
// 8-point resize handles around a selected element.
// Corners are 8x8 squares, edge midpoints are 6x8 or 8x6 rectangles.

import React from 'react';
import type { ElementBounds, ResizeHandle } from './types';

interface ResizeHandlesProps {
  bounds: ElementBounds;
  onResizeStart: (handle: ResizeHandle['position'], e: React.MouseEvent) => void;
  visible: boolean;
}

const HANDLE_SIZE = 8;
const HALF = HANDLE_SIZE / 2;

interface HandleDef {
  position: ResizeHandle['position'];
  cursor: string;
  getX: (b: ElementBounds) => number;
  getY: (b: ElementBounds) => number;
  width: number;
  height: number;
}

const handles: HandleDef[] = [
  // Corners (8x8)
  { position: 'top-left', cursor: 'nw-resize', getX: (b) => b.x - HALF, getY: (b) => b.y - HALF, width: HANDLE_SIZE, height: HANDLE_SIZE },
  { position: 'top-right', cursor: 'ne-resize', getX: (b) => b.x + b.width - HALF, getY: (b) => b.y - HALF, width: HANDLE_SIZE, height: HANDLE_SIZE },
  { position: 'bottom-left', cursor: 'sw-resize', getX: (b) => b.x - HALF, getY: (b) => b.y + b.height - HALF, width: HANDLE_SIZE, height: HANDLE_SIZE },
  { position: 'bottom-right', cursor: 'se-resize', getX: (b) => b.x + b.width - HALF, getY: (b) => b.y + b.height - HALF, width: HANDLE_SIZE, height: HANDLE_SIZE },
  // Edge midpoints
  { position: 'top-center', cursor: 'n-resize', getX: (b) => b.x + b.width / 2 - 4, getY: (b) => b.y - 3, width: 8, height: 6 },
  { position: 'bottom-center', cursor: 's-resize', getX: (b) => b.x + b.width / 2 - 4, getY: (b) => b.y + b.height - 3, width: 8, height: 6 },
  { position: 'middle-left', cursor: 'w-resize', getX: (b) => b.x - 3, getY: (b) => b.y + b.height / 2 - 4, width: 6, height: 8 },
  { position: 'middle-right', cursor: 'e-resize', getX: (b) => b.x + b.width - 3, getY: (b) => b.y + b.height / 2 - 4, width: 6, height: 8 },
];

export const ResizeHandles: React.FC<ResizeHandlesProps> = React.memo(
  function ResizeHandles({ bounds, onResizeStart, visible }) {
    if (!visible) return null;

    return (
      <>
        {handles.map((h) => (
          <div
            key={h.position}
            className="absolute bg-white border-2 border-blue-500 rounded-sm shadow-sm hover:border-blue-600 hover:bg-blue-50 transition-colors"
            style={{
              left: h.getX(bounds),
              top: h.getY(bounds),
              width: h.width,
              height: h.height,
              cursor: h.cursor,
              zIndex: 60,
            }}
            onMouseDown={(e) => {
              e.stopPropagation();
              e.preventDefault();
              onResizeStart(h.position, e);
            }}
          />
        ))}
      </>
    );
  },
);
