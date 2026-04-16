// src/components/maic/slide-editor/SelectionBox.tsx
//
// Bounding box overlay around a selected element.

import React from 'react';
import type { ElementBounds } from './types';

interface SelectionBoxProps {
  bounds: ElementBounds;
  active: boolean;
}

export const SelectionBox: React.FC<SelectionBoxProps> = React.memo(
  function SelectionBox({ bounds, active }) {
    if (!active) return null;

    return (
      <div
        className="absolute pointer-events-none border-2 border-dashed border-blue-500 bg-blue-500/5 transition-all duration-100"
        style={{
          left: bounds.x,
          top: bounds.y,
          width: bounds.width,
          height: bounds.height,
          transform: bounds.rotation ? `rotate(${bounds.rotation}deg)` : undefined,
        }}
      />
    );
  },
);
