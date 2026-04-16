// src/components/maic/slide-editor/AlignmentGuides.tsx
//
// Visual alignment guides that appear during drag/resize operations.
// Renders horizontal and vertical guide lines at specified positions.

import React from 'react';
import type { AlignmentGuide } from './types';

interface AlignmentGuidesProps {
  guides: AlignmentGuide[];
  containerWidth: number;
  containerHeight: number;
}

export const AlignmentGuides: React.FC<AlignmentGuidesProps> = React.memo(
  function AlignmentGuides({ guides, containerWidth, containerHeight }) {
    if (guides.length === 0) return null;

    return (
      <div className="absolute inset-0 pointer-events-none" style={{ zIndex: 50 }}>
        <svg width={containerWidth} height={containerHeight} className="absolute inset-0">
          {guides.map((guide, i) => {
            if (guide.type === 'horizontal') {
              return (
                <g key={`h-${i}`}>
                  <line
                    x1={0}
                    y1={guide.position}
                    x2={containerWidth}
                    y2={guide.position}
                    stroke="#3b82f6"
                    strokeWidth={1}
                    strokeDasharray="4 3"
                  />
                  {guide.label && (
                    <text
                      x={containerWidth - 4}
                      y={guide.position - 3}
                      textAnchor="end"
                      fill="#3b82f6"
                      fontSize={9}
                      fontFamily="monospace"
                    >
                      {guide.label}
                    </text>
                  )}
                </g>
              );
            }
            return (
              <g key={`v-${i}`}>
                <line
                  x1={guide.position}
                  y1={0}
                  x2={guide.position}
                  y2={containerHeight}
                  stroke="#3b82f6"
                  strokeWidth={1}
                  strokeDasharray="4 3"
                />
                {guide.label && (
                  <text
                    x={guide.position + 3}
                    y={12}
                    fill="#3b82f6"
                    fontSize={9}
                    fontFamily="monospace"
                  >
                    {guide.label}
                  </text>
                )}
              </g>
            );
          })}
        </svg>
      </div>
    );
  },
);
