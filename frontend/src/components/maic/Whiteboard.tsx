// src/components/maic/Whiteboard.tsx
//
// SVG overlay for freehand drawing annotations. Supports pen, highlighter,
// eraser (click to remove), and pointer (cursor-only) tools. Reads/writes
// drawing state from maicCanvasStore.

import React, { useCallback, useRef, useState } from 'react';
import { useMAICCanvasStore } from '../../stores/maicCanvasStore';
import type { WhiteboardAnnotation, WhiteboardPoint } from '../../types/maic';

interface WhiteboardProps {
  sceneId: string;
  readonly?: boolean;
}

function pointsToPathD(points: WhiteboardPoint[]): string {
  if (points.length === 0) return '';
  if (points.length === 1) {
    const p = points[0];
    return `M ${p.x} ${p.y} L ${p.x} ${p.y}`;
  }

  let d = `M ${points[0].x} ${points[0].y}`;
  for (let i = 1; i < points.length; i++) {
    const prev = points[i - 1];
    const cur = points[i];
    // Quadratic bezier for smooth curves
    const mx = (prev.x + cur.x) / 2;
    const my = (prev.y + cur.y) / 2;
    d += ` Q ${prev.x} ${prev.y} ${mx} ${my}`;
  }
  // Close to last point
  const last = points[points.length - 1];
  d += ` L ${last.x} ${last.y}`;
  return d;
}

function getAnnotationStyle(annotation: WhiteboardAnnotation): React.CSSProperties & Record<string, string> {
  if (annotation.tool === 'highlighter') {
    return { opacity: '0.35' };
  }
  return {};
}

const cursorMap: Record<string, string> = {
  pen: 'crosshair',
  highlighter: 'crosshair',
  eraser: 'pointer',
  pointer: 'default',
  text: 'text',
  shape: 'crosshair',
};

export const Whiteboard = React.memo<WhiteboardProps>(function Whiteboard({
  sceneId,
  readonly = false,
}) {
  const {
    annotations,
    activeTool,
    activeColor,
    strokeWidth,
    isDrawing,
    setDrawing,
    addAnnotation,
    removeAnnotation,
  } = useMAICCanvasStore();

  const svgRef = useRef<SVGSVGElement>(null);
  const [currentPoints, setCurrentPoints] = useState<WhiteboardPoint[]>([]);

  const sceneAnnotations = annotations.filter((a) => a.sceneId === sceneId);

  const getSVGPoint = useCallback(
    (e: React.MouseEvent | React.TouchEvent): WhiteboardPoint | null => {
      const svg = svgRef.current;
      if (!svg) return null;

      const rect = svg.getBoundingClientRect();
      let clientX: number;
      let clientY: number;

      if ('touches' in e) {
        if (e.touches.length === 0) return null;
        clientX = e.touches[0].clientX;
        clientY = e.touches[0].clientY;
      } else {
        clientX = e.clientX;
        clientY = e.clientY;
      }

      return {
        x: clientX - rect.left,
        y: clientY - rect.top,
        pressure: 'pressure' in e ? (e as React.MouseEvent).nativeEvent instanceof PointerEvent
          ? ((e as React.MouseEvent).nativeEvent as PointerEvent).pressure
          : 0.5
          : 0.5,
      };
    },
    [],
  );

  const handlePointerDown = useCallback(
    (e: React.MouseEvent | React.TouchEvent) => {
      if (readonly) return;

      // Eraser: remove annotation on click
      if (activeTool === 'eraser') {
        const target = e.target as SVGElement;
        const annotationId = target.getAttribute('data-annotation-id');
        if (annotationId) {
          removeAnnotation(annotationId);
        }
        return;
      }

      // Pointer: no drawing
      if (activeTool === 'pointer') return;

      const point = getSVGPoint(e);
      if (!point) return;

      e.preventDefault();
      setDrawing(true);
      setCurrentPoints([point]);
    },
    [readonly, activeTool, getSVGPoint, setDrawing, removeAnnotation],
  );

  const handlePointerMove = useCallback(
    (e: React.MouseEvent | React.TouchEvent) => {
      if (!isDrawing || readonly) return;

      const point = getSVGPoint(e);
      if (!point) return;

      e.preventDefault();
      setCurrentPoints((prev) => [...prev, point]);
    },
    [isDrawing, readonly, getSVGPoint],
  );

  const handlePointerUp = useCallback(() => {
    if (!isDrawing || readonly) return;

    if (currentPoints.length > 0) {
      const annotation: WhiteboardAnnotation = {
        id: `ann-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        tool: activeTool,
        points: currentPoints,
        color: activeColor,
        strokeWidth,
        sceneId,
        timestamp: Date.now(),
      };
      addAnnotation(annotation);
    }

    setDrawing(false);
    setCurrentPoints([]);
  }, [isDrawing, readonly, currentPoints, activeTool, activeColor, strokeWidth, sceneId, addAnnotation, setDrawing]);

  return (
    <svg
      ref={svgRef}
      className="absolute inset-0 w-full h-full z-10"
      style={{ cursor: readonly ? 'default' : cursorMap[activeTool] || 'default' }}
      onMouseDown={handlePointerDown}
      onMouseMove={handlePointerMove}
      onMouseUp={handlePointerUp}
      onMouseLeave={handlePointerUp}
      onTouchStart={handlePointerDown}
      onTouchMove={handlePointerMove}
      onTouchEnd={handlePointerUp}
      aria-label="Whiteboard drawing area"
      role="img"
    >
      {/* Existing annotations */}
      {sceneAnnotations.map((ann) => (
        <path
          key={ann.id}
          d={pointsToPathD(ann.points)}
          fill="none"
          stroke={ann.color}
          strokeWidth={ann.tool === 'highlighter' ? ann.strokeWidth * 4 : ann.strokeWidth}
          strokeLinecap="round"
          strokeLinejoin="round"
          style={getAnnotationStyle(ann)}
          data-annotation-id={ann.id}
          className={activeTool === 'eraser' && !readonly ? 'cursor-pointer hover:opacity-50' : ''}
        />
      ))}

      {/* Current stroke being drawn */}
      {isDrawing && currentPoints.length > 0 && (
        <path
          d={pointsToPathD(currentPoints)}
          fill="none"
          stroke={activeColor}
          strokeWidth={activeTool === 'highlighter' ? strokeWidth * 4 : strokeWidth}
          strokeLinecap="round"
          strokeLinejoin="round"
          style={activeTool === 'highlighter' ? { opacity: 0.35 } : undefined}
        />
      )}
    </svg>
  );
});
