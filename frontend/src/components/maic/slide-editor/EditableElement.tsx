// src/components/maic/slide-editor/EditableElement.tsx
//
// Wrapper that makes a slide element interactive: draggable, selectable,
// resizable, and rotatable. Converts mouse pixel deltas to design-space
// coordinates using the container's scale factor.

import React, { useCallback, useRef, useEffect, useState } from 'react';
import type { MAICSlideElement } from '../../../types/maic';
import type { ResizeHandle } from './types';
import { ResizeHandles } from './ResizeHandles';
import { RotateHandle } from './RotateHandle';
import { cn } from '../../../lib/utils';

interface EditableElementProps {
  element: MAICSlideElement;
  selected: boolean;
  hovered: boolean;
  onSelect: () => void;
  onDeselect: () => void;
  onHover: (hovered: boolean) => void;
  onMove: (dx: number, dy: number) => void;
  onMoveEnd: () => void;
  onResize: (handle: ResizeHandle['position'], dx: number, dy: number) => void;
  onResizeEnd: () => void;
  onRotate: (angle: number) => void;
  onRotateEnd: () => void;
  children: React.ReactNode;
  scale: number;
  snapToGrid?: boolean;
  gridSize?: number;
}

export const EditableElement: React.FC<EditableElementProps> = React.memo(
  function EditableElement({
    element,
    selected,
    hovered,
    onSelect,
    onDeselect,
    onHover,
    onMove,
    onMoveEnd,
    onResize,
    onResizeEnd,
    onRotate,
    onRotateEnd,
    children,
    scale,
    snapToGrid,
    gridSize = 50,
  }) {
    const elRef = useRef<HTMLDivElement>(null);
    const isDraggingRef = useRef(false);
    const isResizingRef = useRef(false);
    const isRotatingRef = useRef(false);
    const dragStartRef = useRef({ x: 0, y: 0 });
    const resizeHandleRef = useRef<ResizeHandle['position'] | null>(null);
    const rotateCenterRef = useRef({ x: 0, y: 0 });
    const rotateStartAngleRef = useRef(0);

    const [currentRotation, setCurrentRotation] = useState(0);

    // Snap value to grid if enabled
    const snap = useCallback(
      (v: number) => (snapToGrid ? Math.round(v / gridSize) * gridSize : v),
      [snapToGrid, gridSize],
    );

    // ─── Drag handlers ──────────────────────────────────────────────
    const handleMouseDown = useCallback(
      (e: React.MouseEvent) => {
        if (e.button !== 0) return;
        e.stopPropagation();
        onSelect();
        isDraggingRef.current = true;
        dragStartRef.current = { x: e.clientX, y: e.clientY };
      },
      [onSelect],
    );

    // ─── Resize handlers ────────────────────────────────────────────
    const handleResizeStart = useCallback(
      (handle: ResizeHandle['position'], e: React.MouseEvent) => {
        isResizingRef.current = true;
        resizeHandleRef.current = handle;
        dragStartRef.current = { x: e.clientX, y: e.clientY };
      },
      [],
    );

    // ─── Rotate handlers ────────────────────────────────────────────
    const handleRotateStart = useCallback(
      (e: React.MouseEvent) => {
        isRotatingRef.current = true;
        const rect = elRef.current?.getBoundingClientRect();
        if (rect) {
          rotateCenterRef.current = {
            x: rect.left + rect.width / 2,
            y: rect.top + rect.height / 2,
          };
        }
        const angle = Math.atan2(
          e.clientY - rotateCenterRef.current.y,
          e.clientX - rotateCenterRef.current.x,
        );
        rotateStartAngleRef.current = angle;
      },
      [],
    );

    // ─── Global mouse move/up ───────────────────────────────────────
    useEffect(() => {
      const handleGlobalMouseMove = (e: MouseEvent) => {
        if (isDraggingRef.current) {
          const rawDx = (e.clientX - dragStartRef.current.x) / scale;
          const rawDy = (e.clientY - dragStartRef.current.y) / scale;
          const dx = snap(rawDx);
          const dy = snap(rawDy);
          if (dx !== 0 || dy !== 0) {
            onMove(dx, dy);
            dragStartRef.current = {
              x: dragStartRef.current.x + dx * scale,
              y: dragStartRef.current.y + dy * scale,
            };
          }
        } else if (isResizingRef.current && resizeHandleRef.current) {
          const rawDx = (e.clientX - dragStartRef.current.x) / scale;
          const rawDy = (e.clientY - dragStartRef.current.y) / scale;
          const dx = snap(rawDx);
          const dy = snap(rawDy);
          if (dx !== 0 || dy !== 0) {
            onResize(resizeHandleRef.current, dx, dy);
            dragStartRef.current = {
              x: dragStartRef.current.x + dx * scale,
              y: dragStartRef.current.y + dy * scale,
            };
          }
        } else if (isRotatingRef.current) {
          const angle = Math.atan2(
            e.clientY - rotateCenterRef.current.y,
            e.clientX - rotateCenterRef.current.x,
          );
          const delta = ((angle - rotateStartAngleRef.current) * 180) / Math.PI;
          setCurrentRotation(delta);
          onRotate(delta);
          rotateStartAngleRef.current = angle;
        }
      };

      const handleGlobalMouseUp = () => {
        if (isDraggingRef.current) {
          isDraggingRef.current = false;
          onMoveEnd();
        }
        if (isResizingRef.current) {
          isResizingRef.current = false;
          resizeHandleRef.current = null;
          onResizeEnd();
        }
        if (isRotatingRef.current) {
          isRotatingRef.current = false;
          setCurrentRotation(0);
          onRotateEnd();
        }
      };

      document.addEventListener('mousemove', handleGlobalMouseMove);
      document.addEventListener('mouseup', handleGlobalMouseUp);
      return () => {
        document.removeEventListener('mousemove', handleGlobalMouseMove);
        document.removeEventListener('mouseup', handleGlobalMouseUp);
      };
    }, [scale, snap, onMove, onMoveEnd, onResize, onResizeEnd, onRotate, onRotateEnd]);

    const bounds = {
      x: element.x,
      y: element.y,
      width: element.width,
      height: element.height,
    };

    return (
      <>
        <div
          ref={elRef}
          className={cn(
            'absolute cursor-move transition-shadow duration-100',
            selected && 'ring-2 ring-blue-500 ring-offset-1',
            !selected && hovered && 'ring-1 ring-dashed ring-gray-300',
          )}
          style={{
            left: element.x,
            top: element.y,
            width: element.width,
            height: element.height,
            zIndex: selected ? 40 : 10,
          }}
          onMouseDown={handleMouseDown}
          onMouseEnter={() => onHover(true)}
          onMouseLeave={() => onHover(false)}
        >
          {children}
        </div>

        {/* Resize handles */}
        {selected && (
          <ResizeHandles
            bounds={bounds}
            onResizeStart={handleResizeStart}
            visible={selected}
          />
        )}

        {/* Rotate handle */}
        {selected && (
          <RotateHandle
            bounds={bounds}
            onRotateStart={handleRotateStart}
            visible={selected}
            currentAngle={currentRotation}
          />
        )}
      </>
    );
  },
);
