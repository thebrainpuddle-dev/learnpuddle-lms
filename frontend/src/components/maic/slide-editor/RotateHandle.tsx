// src/components/maic/slide-editor/RotateHandle.tsx
//
// Rotation knob above the selected element, connected by a thin line.

import React, { useState } from 'react';
import { RotateCw } from 'lucide-react';
import type { ElementBounds } from './types';

interface RotateHandleProps {
  bounds: ElementBounds;
  onRotateStart: (e: React.MouseEvent) => void;
  visible: boolean;
  currentAngle?: number;
}

const HANDLE_OFFSET = 30;
const HANDLE_RADIUS = 12;

export const RotateHandle: React.FC<RotateHandleProps> = React.memo(
  function RotateHandle({ bounds, onRotateStart, visible, currentAngle = 0 }) {
    const [showTooltip, setShowTooltip] = useState(false);

    if (!visible) return null;

    const centerX = bounds.x + bounds.width / 2;
    const topY = bounds.y;
    const handleY = topY - HANDLE_OFFSET;

    return (
      <>
        {/* Connecting line from top-center to handle */}
        <svg
          className="absolute pointer-events-none"
          style={{ left: 0, top: 0, width: '100%', height: '100%', zIndex: 59 }}
        >
          <line
            x1={centerX}
            y1={topY}
            x2={centerX}
            y2={handleY + HANDLE_RADIUS}
            stroke="#3b82f6"
            strokeWidth={1}
          />
        </svg>

        {/* Handle circle */}
        <div
          className="absolute flex items-center justify-center rounded-full bg-white border-2 border-blue-500 shadow-sm hover:border-blue-600 hover:bg-blue-50 transition-colors cursor-grab active:cursor-grabbing"
          style={{
            left: centerX - HANDLE_RADIUS,
            top: handleY - HANDLE_RADIUS,
            width: HANDLE_RADIUS * 2,
            height: HANDLE_RADIUS * 2,
            zIndex: 60,
          }}
          onMouseDown={(e) => {
            e.stopPropagation();
            e.preventDefault();
            setShowTooltip(true);
            onRotateStart(e);
          }}
          onMouseUp={() => setShowTooltip(false)}
          onMouseEnter={() => setShowTooltip(true)}
          onMouseLeave={() => setShowTooltip(false)}
        >
          <RotateCw className="w-3 h-3 text-blue-500" />
        </div>

        {/* Angle tooltip */}
        {showTooltip && currentAngle !== 0 && (
          <div
            className="absolute bg-gray-900 text-white text-[10px] px-1.5 py-0.5 rounded pointer-events-none whitespace-nowrap"
            style={{
              left: centerX + HANDLE_RADIUS + 6,
              top: handleY - 8,
              zIndex: 61,
            }}
          >
            {Math.round(currentAngle)}°
          </div>
        )}
      </>
    );
  },
);
