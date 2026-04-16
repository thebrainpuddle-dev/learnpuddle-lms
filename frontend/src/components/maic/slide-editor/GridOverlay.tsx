// src/components/maic/slide-editor/GridOverlay.tsx
//
// SVG pattern-based grid overlay for the slide canvas.
// Renders dashed lines with bolder center cross lines.

import React from 'react';
import { AnimatePresence, motion } from 'motion/react';

interface GridOverlayProps {
  visible: boolean;
  gridSize?: number;
  color?: string;
  containerWidth: number;
  containerHeight: number;
}

export const GridOverlay: React.FC<GridOverlayProps> = React.memo(function GridOverlay({
  visible,
  gridSize = 50,
  color = '#e5e7eb',
  containerWidth,
  containerHeight,
}) {
  const patternId = 'editor-grid-pattern';
  const centerX = containerWidth / 2;
  const centerY = containerHeight / 2;

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          className="absolute inset-0 pointer-events-none"
          style={{ zIndex: 1 }}
        >
          <svg
            width={containerWidth}
            height={containerHeight}
            className="absolute inset-0"
          >
            <defs>
              <pattern
                id={patternId}
                width={gridSize}
                height={gridSize}
                patternUnits="userSpaceOnUse"
              >
                {/* Vertical grid line */}
                <line
                  x1={gridSize}
                  y1={0}
                  x2={gridSize}
                  y2={gridSize}
                  stroke={color}
                  strokeWidth={0.5}
                  strokeDasharray="4 4"
                />
                {/* Horizontal grid line */}
                <line
                  x1={0}
                  y1={gridSize}
                  x2={gridSize}
                  y2={gridSize}
                  stroke={color}
                  strokeWidth={0.5}
                  strokeDasharray="4 4"
                />
              </pattern>
            </defs>

            {/* Grid pattern fill */}
            <rect width={containerWidth} height={containerHeight} fill={`url(#${patternId})`} />

            {/* Center horizontal line (bolder) */}
            <line
              x1={0}
              y1={centerY}
              x2={containerWidth}
              y2={centerY}
              stroke={color}
              strokeWidth={1}
              strokeDasharray="6 4"
              opacity={0.7}
            />

            {/* Center vertical line (bolder) */}
            <line
              x1={centerX}
              y1={0}
              x2={centerX}
              y2={containerHeight}
              stroke={color}
              strokeWidth={1}
              strokeDasharray="6 4"
              opacity={0.7}
            />
          </svg>
        </motion.div>
      )}
    </AnimatePresence>
  );
});
