// src/components/maic/slide-editor/EditorToolbar.tsx
//
// Floating toolbar for slide editing actions: add elements, grid/zoom,
// and selection actions (duplicate, delete, layer ordering).

import React, { useState, useCallback } from 'react';
import {
  Grid3X3,
  ZoomIn,
  ZoomOut,
  Copy,
  Trash2,
  Type,
  Image,
  Square,
  Triangle,
  Circle,
  Code2,
  Table2,
  ArrowUpToLine,
  ArrowDownToLine,
} from 'lucide-react';
import type { MAICSlideElement } from '../../../types/maic';
import { cn } from '../../../lib/utils';

interface EditorToolbarProps {
  onToggleGrid: () => void;
  showGrid: boolean;
  zoom: number;
  onZoomChange: (zoom: number) => void;
  onAddElement: (type: MAICSlideElement['type'], shapeContent?: string) => void;
  onDeleteSelected: () => void;
  onDuplicate: () => void;
  onBringToFront: () => void;
  onSendToBack: () => void;
  hasSelection: boolean;
  className?: string;
}

function ToolButton({
  onClick,
  title,
  active,
  disabled,
  children,
}: {
  onClick: () => void;
  title: string;
  active?: boolean;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      title={title}
      disabled={disabled}
      className={cn(
        'p-1.5 rounded-md transition-colors disabled:opacity-40 disabled:cursor-not-allowed',
        active
          ? 'bg-blue-600 text-white hover:bg-blue-700'
          : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900',
      )}
    >
      {children}
    </button>
  );
}

function Divider() {
  return <div className="w-px h-6 bg-gray-200 mx-1" />;
}

export const EditorToolbar: React.FC<EditorToolbarProps> = React.memo(
  function EditorToolbar({
    onToggleGrid,
    showGrid,
    zoom,
    onZoomChange,
    onAddElement,
    onDeleteSelected,
    onDuplicate,
    onBringToFront,
    onSendToBack,
    hasSelection,
    className,
  }) {
    const [showShapes, setShowShapes] = useState(false);

    const handleZoomIn = useCallback(() => {
      onZoomChange(Math.min(2, Math.round((zoom + 0.1) * 10) / 10));
    }, [zoom, onZoomChange]);

    const handleZoomOut = useCallback(() => {
      onZoomChange(Math.max(0.5, Math.round((zoom - 0.1) * 10) / 10));
    }, [zoom, onZoomChange]);

    const handleAddShape = useCallback(
      (shape: string) => {
        onAddElement('shape', shape);
        setShowShapes(false);
      },
      [onAddElement],
    );

    return (
      <div
        className={cn(
          'flex items-center gap-0.5 px-2 py-1 bg-white border border-gray-200 rounded-lg shadow-sm',
          className,
        )}
      >
        {/* Add elements */}
        <ToolButton onClick={() => onAddElement('text')} title="Add text">
          <Type className="w-4 h-4" />
        </ToolButton>
        <ToolButton onClick={() => onAddElement('image')} title="Add image">
          <Image className="w-4 h-4" />
        </ToolButton>

        {/* Shapes dropdown */}
        <div className="relative">
          <ToolButton
            onClick={() => setShowShapes(!showShapes)}
            title="Add shape"
            active={showShapes}
          >
            <Square className="w-4 h-4" />
          </ToolButton>
          {showShapes && (
            <div className="absolute top-full left-0 mt-1 flex gap-1 bg-white border border-gray-200 rounded-lg shadow-lg p-1 z-50">
              <ToolButton onClick={() => handleAddShape('rect')} title="Rectangle">
                <Square className="w-4 h-4" />
              </ToolButton>
              <ToolButton onClick={() => handleAddShape('circle')} title="Circle">
                <Circle className="w-4 h-4" />
              </ToolButton>
              <ToolButton onClick={() => handleAddShape('triangle')} title="Triangle">
                <Triangle className="w-4 h-4" />
              </ToolButton>
            </div>
          )}
        </div>

        <ToolButton onClick={() => onAddElement('code')} title="Add code block">
          <Code2 className="w-4 h-4" />
        </ToolButton>
        <ToolButton onClick={() => onAddElement('table')} title="Add table">
          <Table2 className="w-4 h-4" />
        </ToolButton>

        <Divider />

        {/* Grid & Zoom */}
        <ToolButton onClick={onToggleGrid} title="Toggle grid" active={showGrid}>
          <Grid3X3 className="w-4 h-4" />
        </ToolButton>
        <ToolButton onClick={handleZoomOut} title="Zoom out">
          <ZoomOut className="w-4 h-4" />
        </ToolButton>
        <span className="text-xs text-gray-500 font-mono tabular-nums w-10 text-center select-none">
          {Math.round(zoom * 100)}%
        </span>
        <ToolButton onClick={handleZoomIn} title="Zoom in">
          <ZoomIn className="w-4 h-4" />
        </ToolButton>

        {/* Selection actions */}
        {hasSelection && (
          <>
            <Divider />
            <ToolButton onClick={onDuplicate} title="Duplicate (Ctrl+D)">
              <Copy className="w-4 h-4" />
            </ToolButton>
            <ToolButton onClick={onDeleteSelected} title="Delete (Del)">
              <Trash2 className="w-4 h-4" />
            </ToolButton>
            <ToolButton onClick={onBringToFront} title="Bring to front">
              <ArrowUpToLine className="w-4 h-4" />
            </ToolButton>
            <ToolButton onClick={onSendToBack} title="Send to back">
              <ArrowDownToLine className="w-4 h-4" />
            </ToolButton>
          </>
        )}
      </div>
    );
  },
);
