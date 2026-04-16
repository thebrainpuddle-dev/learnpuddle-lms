// src/components/maic/slide-editor/SlideEditor.tsx
//
// Main slide editor container. Composes EditorToolbar, GridOverlay,
// AlignmentGuides, EditableElement, and SelectionBox into a unified
// interactive editing canvas for a single MAICSlide.

import React, { useCallback, useRef, useEffect, useState } from 'react';
import DOMPurify from 'dompurify';
import type { MAICSlide, MAICSlideElement } from '../../../types/maic';
import type { ResizeHandle } from './types';
import { useEditorState } from './useEditorState';
import { GridOverlay } from './GridOverlay';
import { AlignmentGuides } from './AlignmentGuides';
import { EditableElement } from './EditableElement';
import { EditorToolbar } from './EditorToolbar';
import { cn } from '../../../lib/utils';

// Design space matching SlideRenderer
const DESIGN_WIDTH = 800;
const DESIGN_HEIGHT = 450;

interface SlideEditorProps {
  slide: MAICSlide;
  onSlideUpdate: (slide: MAICSlide) => void;
  readonly?: boolean;
  className?: string;
}

// Generate a unique element ID
function genId(): string {
  return `el-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
}

// Default new elements by type
function createDefaultElement(
  type: MAICSlideElement['type'],
  shapeContent?: string,
): MAICSlideElement {
  const base = {
    id: genId(),
    x: DESIGN_WIDTH / 2 - 75,
    y: DESIGN_HEIGHT / 2 - 30,
    width: 150,
    height: 60,
  };

  switch (type) {
    case 'text':
      return { ...base, type: 'text', content: 'Double-click to edit', style: { fontSize: '16px' } };
    case 'image':
      return { ...base, type: 'image', width: 200, height: 150, x: DESIGN_WIDTH / 2 - 100, y: DESIGN_HEIGHT / 2 - 75, content: 'placeholder', src: '' };
    case 'shape':
      return { ...base, type: 'shape', width: 100, height: 100, x: DESIGN_WIDTH / 2 - 50, y: DESIGN_HEIGHT / 2 - 50, content: shapeContent || 'rect', style: { fill: '#3B82F6' } };
    case 'code':
      return { ...base, type: 'code', width: 250, height: 120, x: DESIGN_WIDTH / 2 - 125, y: DESIGN_HEIGHT / 2 - 60, content: '// Your code here\nconsole.log("Hello!");' };
    case 'table':
      return { ...base, type: 'table', width: 250, height: 120, x: DESIGN_WIDTH / 2 - 125, y: DESIGN_HEIGHT / 2 - 60, content: JSON.stringify({ headers: ['Column 1', 'Column 2'], rows: [['A', 'B'], ['C', 'D']] }) };
    case 'chart':
      return { ...base, type: 'chart', width: 250, height: 180, x: DESIGN_WIDTH / 2 - 125, y: DESIGN_HEIGHT / 2 - 90, content: JSON.stringify({ type: 'bar', data: [{ name: 'A', value: 10 }, { name: 'B', value: 20 }] }) };
    case 'latex':
      return { ...base, type: 'latex', content: 'E = mc^2' };
    case 'video':
      return { ...base, type: 'video', width: 320, height: 180, x: DESIGN_WIDTH / 2 - 160, y: DESIGN_HEIGHT / 2 - 90, content: '' };
    default:
      return { ...base, type: 'text', content: 'New element' };
  }
}

// ─── Simple inline element renderers (mirrors SlideRenderer) ────────────────

function renderElementContent(el: MAICSlideElement): React.ReactNode {
  switch (el.type) {
    case 'text': {
      const html = el.content.replace(/\\n/g, '<br>').replace(/\n/g, '<br>');
      return (
        <div
          className="overflow-auto text-gray-900 w-full h-full"
          style={{
            fontSize: (el.style?.fontSize as string) || '16px',
            color: (el.style?.color as string) || undefined,
            fontWeight: (el.style?.fontWeight as string) || undefined,
            textAlign: (el.style?.textAlign as string) as React.CSSProperties['textAlign'] || undefined,
            lineHeight: 1.5,
          }}
          dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(html) }}
        />
      );
    }
    case 'image':
      return (
        <div className="w-full h-full bg-gray-100 flex items-center justify-center rounded overflow-hidden">
          {el.src ? (
            <img src={el.src} alt={el.content || 'Image'} className="w-full h-full object-cover" />
          ) : (
            <span className="text-xs text-gray-400">Image placeholder</span>
          )}
        </div>
      );
    case 'shape': {
      const fill = (el.style?.fill as string) || '#3B82F6';
      const shape = el.content || 'rect';
      return (
        <svg width="100%" height="100%" viewBox={`0 0 ${el.width} ${el.height}`} preserveAspectRatio="none">
          {shape === 'circle' || shape === 'ellipse' ? (
            <ellipse cx={el.width / 2} cy={el.height / 2} rx={el.width / 2} ry={el.height / 2} fill={fill} />
          ) : shape === 'triangle' ? (
            <polygon points={`${el.width / 2},0 0,${el.height} ${el.width},${el.height}`} fill={fill} />
          ) : (
            <rect width={el.width} height={el.height} rx={Number(el.style?.borderRadius) || 0} fill={fill} />
          )}
        </svg>
      );
    }
    case 'code':
      return (
        <pre className="h-full w-full overflow-auto rounded bg-gray-900 p-2 text-xs leading-relaxed">
          <code className="text-gray-100">{el.content}</code>
        </pre>
      );
    case 'table':
      return (
        <div className="h-full w-full overflow-auto bg-white rounded text-xs p-1">
          <span className="text-gray-400">Table</span>
        </div>
      );
    default:
      return (
        <div className="h-full w-full flex items-center justify-center bg-gray-50 rounded text-gray-400 text-xs">
          {el.type}
        </div>
      );
  }
}

// ─── SlideEditor ────────────────────────────────────────────────────────────

export const SlideEditor: React.FC<SlideEditorProps> = React.memo(function SlideEditor({
  slide,
  onSlideUpdate,
  readonly = false,
  className,
}) {
  const canvasContainerRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  const [editingTextId, setEditingTextId] = useState<string | null>(null);

  const editor = useEditorState();

  // ─── Scale calculation ──────────────────────────────────────────
  const updateScale = useCallback(() => {
    const el = canvasContainerRef.current;
    if (!el) return;
    const sx = el.clientWidth / DESIGN_WIDTH;
    const sy = el.clientHeight / DESIGN_HEIGHT;
    setScale(Math.min(sx, sy));
  }, []);

  useEffect(() => {
    updateScale();
    const observer = new ResizeObserver(updateScale);
    if (canvasContainerRef.current) observer.observe(canvasContainerRef.current);
    return () => observer.disconnect();
  }, [updateScale]);

  // ─── Element update helper ────────────────────────────────────
  const updateElement = useCallback(
    (elementId: string, patch: Partial<MAICSlideElement>) => {
      const newElements = slide.elements.map((el) =>
        el.id === elementId ? { ...el, ...patch } : el,
      );
      onSlideUpdate({ ...slide, elements: newElements });
    },
    [slide, onSlideUpdate],
  );

  // ─── Element CRUD ─────────────────────────────────────────────
  const handleAddElement = useCallback(
    (type: MAICSlideElement['type'], shapeContent?: string) => {
      if (readonly) return;
      const newEl = createDefaultElement(type, shapeContent);
      onSlideUpdate({ ...slide, elements: [...slide.elements, newEl] });
      editor.selectElement(newEl.id);
    },
    [slide, onSlideUpdate, readonly, editor],
  );

  const handleDeleteSelected = useCallback(() => {
    if (readonly || !editor.selectedElementId) return;
    const newElements = slide.elements.filter((el) => el.id !== editor.selectedElementId);
    onSlideUpdate({ ...slide, elements: newElements });
    editor.selectElement(null);
  }, [slide, onSlideUpdate, readonly, editor]);

  const handleDuplicate = useCallback(() => {
    if (readonly || !editor.selectedElementId) return;
    const source = slide.elements.find((el) => el.id === editor.selectedElementId);
    if (!source) return;
    const copy: MAICSlideElement = {
      ...source,
      id: genId(),
      x: source.x + 20,
      y: source.y + 20,
    };
    onSlideUpdate({ ...slide, elements: [...slide.elements, copy] });
    editor.selectElement(copy.id);
  }, [slide, onSlideUpdate, readonly, editor]);

  const handleBringToFront = useCallback(() => {
    if (!editor.selectedElementId) return;
    const idx = slide.elements.findIndex((el) => el.id === editor.selectedElementId);
    if (idx < 0 || idx === slide.elements.length - 1) return;
    const newElements = [...slide.elements];
    const [moved] = newElements.splice(idx, 1);
    newElements.push(moved);
    onSlideUpdate({ ...slide, elements: newElements });
  }, [slide, onSlideUpdate, editor]);

  const handleSendToBack = useCallback(() => {
    if (!editor.selectedElementId) return;
    const idx = slide.elements.findIndex((el) => el.id === editor.selectedElementId);
    if (idx <= 0) return;
    const newElements = [...slide.elements];
    const [moved] = newElements.splice(idx, 1);
    newElements.unshift(moved);
    onSlideUpdate({ ...slide, elements: newElements });
  }, [slide, onSlideUpdate, editor]);

  // ─── Move / Resize / Rotate handlers ─────────────────────────
  const handleMove = useCallback(
    (elementId: string, dx: number, dy: number) => {
      if (readonly) return;
      const el = slide.elements.find((e) => e.id === elementId);
      if (!el) return;
      updateElement(elementId, { x: el.x + dx, y: el.y + dy });
    },
    [slide.elements, updateElement, readonly],
  );

  const handleResize = useCallback(
    (elementId: string, handle: ResizeHandle['position'], dx: number, dy: number) => {
      if (readonly) return;
      const el = slide.elements.find((e) => e.id === elementId);
      if (!el) return;

      let { x, y, width, height } = el;
      const MIN_SIZE = 20;

      switch (handle) {
        case 'top-left':
          x += dx; y += dy; width -= dx; height -= dy; break;
        case 'top-center':
          y += dy; height -= dy; break;
        case 'top-right':
          y += dy; width += dx; height -= dy; break;
        case 'middle-left':
          x += dx; width -= dx; break;
        case 'middle-right':
          width += dx; break;
        case 'bottom-left':
          x += dx; width -= dx; height += dy; break;
        case 'bottom-center':
          height += dy; break;
        case 'bottom-right':
          width += dx; height += dy; break;
      }

      // Enforce minimum size
      if (width < MIN_SIZE) { width = MIN_SIZE; x = el.x; }
      if (height < MIN_SIZE) { height = MIN_SIZE; y = el.y; }

      updateElement(elementId, { x, y, width, height });
    },
    [slide.elements, updateElement, readonly],
  );

  const handleRotate = useCallback(
    (_elementId: string, _angle: number) => {
      // Rotation is tracked visually but not persisted to MAICSlideElement
      // since the type doesn't have a rotation field. This is a visual-only
      // feature for now.
    },
    [],
  );

  // ─── Canvas click (deselect) ──────────────────────────────────
  const handleCanvasClick = useCallback(
    (e: React.MouseEvent) => {
      if (e.target === e.currentTarget) {
        editor.selectElement(null);
        setEditingTextId(null);
      }
    },
    [editor],
  );

  // ─── Double-click for inline text editing ─────────────────────
  const handleDoubleClick = useCallback(
    (elementId: string) => {
      if (readonly) return;
      const el = slide.elements.find((e) => e.id === elementId);
      if (el?.type === 'text') {
        setEditingTextId(elementId);
      }
    },
    [slide.elements, readonly],
  );

  const handleTextChange = useCallback(
    (elementId: string, newContent: string) => {
      updateElement(elementId, { content: newContent });
    },
    [updateElement],
  );

  // ─── Keyboard shortcuts ───────────────────────────────────────
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (readonly) return;
      // Don't capture when typing in an input or contenteditable
      const target = e.target as HTMLElement;
      if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable) {
        if (e.key === 'Escape') {
          setEditingTextId(null);
          editor.selectElement(null);
        }
        return;
      }

      if (e.key === 'Delete' || e.key === 'Backspace') {
        handleDeleteSelected();
      } else if (e.key === 'd' && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        handleDuplicate();
      } else if (e.key === 'g' && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        editor.toggleGrid();
      } else if (e.key === 'Escape') {
        editor.selectElement(null);
        setEditingTextId(null);
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [readonly, handleDeleteSelected, handleDuplicate, editor]);

  // ─── Alignment guide computation ─────────────────────────────
  // Generate snap guides for the selected element against others
  useEffect(() => {
    if (!editor.selectedElementId || !editor.isDragging) {
      if (editor.snapGuides.length > 0) {
        editor.setSnapGuides([]);
      }
      return;
    }

    const selected = slide.elements.find((el) => el.id === editor.selectedElementId);
    if (!selected) return;

    const guides = [];
    const SNAP_THRESHOLD = 5;
    const selCenterX = selected.x + selected.width / 2;
    const selCenterY = selected.y + selected.height / 2;

    // Center guides
    if (Math.abs(selCenterX - DESIGN_WIDTH / 2) < SNAP_THRESHOLD) {
      guides.push({ type: 'vertical' as const, position: DESIGN_WIDTH / 2, label: 'center' });
    }
    if (Math.abs(selCenterY - DESIGN_HEIGHT / 2) < SNAP_THRESHOLD) {
      guides.push({ type: 'horizontal' as const, position: DESIGN_HEIGHT / 2, label: 'center' });
    }

    // Alignment with other elements
    for (const other of slide.elements) {
      if (other.id === editor.selectedElementId) continue;
      const otherCenterX = other.x + other.width / 2;
      const otherCenterY = other.y + other.height / 2;

      if (Math.abs(selCenterX - otherCenterX) < SNAP_THRESHOLD) {
        guides.push({ type: 'vertical' as const, position: otherCenterX });
      }
      if (Math.abs(selCenterY - otherCenterY) < SNAP_THRESHOLD) {
        guides.push({ type: 'horizontal' as const, position: otherCenterY });
      }
      if (Math.abs(selected.x - other.x) < SNAP_THRESHOLD) {
        guides.push({ type: 'vertical' as const, position: other.x, label: 'left' });
      }
      if (Math.abs(selected.x + selected.width - other.x - other.width) < SNAP_THRESHOLD) {
        guides.push({ type: 'vertical' as const, position: other.x + other.width, label: 'right' });
      }
    }

    editor.setSnapGuides(guides);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editor.selectedElementId, editor.isDragging, slide.elements]);

  return (
    <div className={cn('flex flex-col h-full w-full', className)}>
      {/* Toolbar */}
      {!readonly && (
        <div className="flex justify-center py-2 px-3">
          <EditorToolbar
            onToggleGrid={editor.toggleGrid}
            showGrid={editor.showGrid}
            zoom={editor.zoom}
            onZoomChange={editor.setZoom}
            onAddElement={handleAddElement}
            onDeleteSelected={handleDeleteSelected}
            onDuplicate={handleDuplicate}
            onBringToFront={handleBringToFront}
            onSendToBack={handleSendToBack}
            hasSelection={!!editor.selectedElementId}
          />
        </div>
      )}

      {/* Canvas area */}
      <div
        ref={canvasContainerRef}
        className="flex-1 relative flex items-center justify-center bg-gray-900/50 overflow-hidden"
      >
        {/* Scaled design-space canvas */}
        <div
          className="relative bg-white rounded shadow-lg overflow-visible"
          style={{
            width: DESIGN_WIDTH,
            height: DESIGN_HEIGHT,
            transform: `scale(${scale * editor.zoom})`,
            transformOrigin: 'center center',
          }}
          onClick={handleCanvasClick}
        >
          {/* Background */}
          {slide.background && (
            <div
              className="absolute inset-0"
              style={{ background: slide.background }}
            />
          )}

          {/* Grid overlay */}
          <GridOverlay
            visible={editor.showGrid}
            gridSize={editor.gridSize}
            containerWidth={DESIGN_WIDTH}
            containerHeight={DESIGN_HEIGHT}
          />

          {/* Slide elements */}
          {slide.elements.map((el) => {
            const isSelected = editor.selectedElementId === el.id;
            const isHovered = editor.hoveredElementId === el.id;
            const isEditingText = editingTextId === el.id;

            return (
              <EditableElement
                key={el.id}
                element={el}
                selected={isSelected}
                hovered={isHovered}
                onSelect={() => editor.selectElement(el.id)}
                onDeselect={() => editor.selectElement(null)}
                onHover={(h) => editor.hoverElement(h ? el.id : null)}
                onMove={(dx, dy) => handleMove(el.id, dx, dy)}
                onMoveEnd={() => {}}
                onResize={(handle, dx, dy) => handleResize(el.id, handle, dx, dy)}
                onResizeEnd={() => {}}
                onRotate={(angle) => handleRotate(el.id, angle)}
                onRotateEnd={() => {}}
                scale={scale * editor.zoom}
                snapToGrid={editor.showGrid}
                gridSize={editor.gridSize}
              >
                {isEditingText && el.type === 'text' ? (
                  <div
                    contentEditable
                    suppressContentEditableWarning
                    className="w-full h-full outline-none text-gray-900"
                    style={{
                      fontSize: (el.style?.fontSize as string) || '16px',
                      color: (el.style?.color as string) || undefined,
                      fontWeight: (el.style?.fontWeight as string) || undefined,
                      textAlign: (el.style?.textAlign as string) as React.CSSProperties['textAlign'] || undefined,
                      lineHeight: 1.5,
                    }}
                    onBlur={(e) => {
                      handleTextChange(el.id, e.currentTarget.textContent || '');
                      setEditingTextId(null);
                    }}
                    onDoubleClick={(e) => e.stopPropagation()}
                    dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(el.content) }}
                  />
                ) : (
                  <div
                    className="w-full h-full"
                    onDoubleClick={(e) => {
                      e.stopPropagation();
                      handleDoubleClick(el.id);
                    }}
                  >
                    {renderElementContent(el)}
                  </div>
                )}
              </EditableElement>
            );
          })}

          {/* Alignment guides */}
          <AlignmentGuides
            guides={editor.snapGuides}
            containerWidth={DESIGN_WIDTH}
            containerHeight={DESIGN_HEIGHT}
          />
        </div>
      </div>
    </div>
  );
});
