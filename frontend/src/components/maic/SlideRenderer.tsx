// src/components/maic/SlideRenderer.tsx
//
// Renders a single MAICSlide by mapping each element to its visual
// representation. Elements are absolutely positioned within a viewport
// container that preserves 16:9 aspect ratio.

import React, { useRef, useState, useEffect, useCallback } from 'react';
import type { MAICSlide, MAICSlideElement } from '../../types/maic';
import { cn } from '../../lib/utils';

// Design space the LLM generates coordinates for
const DESIGN_WIDTH = 800;
const DESIGN_HEIGHT = 450;

interface SlideRendererProps {
  slide: MAICSlide;
}

// ─── Element renderers ──────────────────────────────────────────────────────

function renderTextElement(el: MAICSlideElement): React.ReactNode {
  // Convert literal \n to <br> for proper line breaks, and sanitize
  const html = el.content
    .replace(/\\n/g, '<br>')
    .replace(/\n/g, '<br>');

  return (
    <div
      className="overflow-auto text-gray-900"
      style={{
        fontSize: (el.style?.fontSize as string) || '16px',
        color: (el.style?.color as string) || undefined,
        fontWeight: (el.style?.fontWeight as string) || undefined,
        textAlign: (el.style?.textAlign as string) as React.CSSProperties['textAlign'] || undefined,
        lineHeight: 1.5,
      }}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

function renderImageElement(el: MAICSlideElement): React.ReactNode {
  return (
    <img
      src={el.content}
      alt=""
      className="h-full w-full object-contain"
      loading="lazy"
    />
  );
}

function renderShapeElement(el: MAICSlideElement): React.ReactNode {
  const fill = (el.style?.fill as string) || '#3B82F6';
  const stroke = (el.style?.stroke as string) || 'none';
  const strokeWidth = Number(el.style?.strokeWidth) || 0;
  const shape = el.content || 'rect';

  return (
    <svg
      width="100%"
      height="100%"
      viewBox={`0 0 ${el.width} ${el.height}`}
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      {shape === 'circle' || shape === 'ellipse' ? (
        <ellipse
          cx={el.width / 2}
          cy={el.height / 2}
          rx={el.width / 2 - strokeWidth}
          ry={el.height / 2 - strokeWidth}
          fill={fill}
          stroke={stroke}
          strokeWidth={strokeWidth}
        />
      ) : (
        <rect
          x={strokeWidth / 2}
          y={strokeWidth / 2}
          width={el.width - strokeWidth}
          height={el.height - strokeWidth}
          rx={Number(el.style?.borderRadius) || 0}
          fill={fill}
          stroke={stroke}
          strokeWidth={strokeWidth}
        />
      )}
    </svg>
  );
}

function renderChartElement(el: MAICSlideElement): React.ReactNode {
  return (
    <div className="h-full w-full flex items-center justify-center bg-gray-50 rounded border border-gray-200 text-gray-400 text-sm">
      <div className="text-center">
        <svg className="mx-auto h-8 w-8 mb-1 opacity-50" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" />
        </svg>
        Chart
      </div>
    </div>
  );
}

function renderLatexElement(el: MAICSlideElement): React.ReactNode {
  return (
    <span
      className="katex-display block overflow-auto"
      style={{
        fontSize: (el.style?.fontSize as string) || '18px',
        color: (el.style?.color as string) || undefined,
      }}
    >
      {el.content}
    </span>
  );
}

function renderCodeElement(el: MAICSlideElement): React.ReactNode {
  const language = (el.style?.language as string) || '';
  return (
    <pre className="h-full w-full overflow-auto rounded bg-gray-900 p-3 text-sm leading-relaxed">
      <code className={cn('text-gray-100', language && `language-${language}`)}>
        {el.content}
      </code>
    </pre>
  );
}

function renderTableElement(el: MAICSlideElement): React.ReactNode {
  let headers: string[] = [];
  let rows: string[][] = [];
  try {
    const parsed = JSON.parse(el.content) as { headers?: string[]; rows?: string[][] };
    headers = parsed.headers ?? [];
    rows = parsed.rows ?? [];
  } catch {
    return (
      <div className="h-full w-full flex items-center justify-center text-gray-400 text-sm">
        Invalid table data
      </div>
    );
  }

  return (
    <div className="h-full w-full overflow-auto">
      <table className="w-full border-collapse text-sm">
        {headers.length > 0 && (
          <thead>
            <tr>
              {headers.map((header, i) => (
                <th
                  key={i}
                  className="border border-gray-300 dark:border-gray-600 bg-gray-100 dark:bg-gray-700 px-3 py-2 text-left font-semibold text-gray-800 dark:text-gray-200"
                >
                  {header}
                </th>
              ))}
            </tr>
          </thead>
        )}
        <tbody>
          {rows.map((row, rowIdx) => (
            <tr
              key={rowIdx}
              className={cn(
                rowIdx % 2 === 0
                  ? 'bg-white dark:bg-gray-900'
                  : 'bg-gray-50 dark:bg-gray-800',
              )}
            >
              {row.map((cell, cellIdx) => (
                <td
                  key={cellIdx}
                  className="border border-gray-300 dark:border-gray-600 px-3 py-2 text-gray-700 dark:text-gray-300"
                >
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function renderVideoElement(el: MAICSlideElement): React.ReactNode {
  return (
    <video
      src={el.content}
      className="h-full w-full object-contain"
      controls
      playsInline
    />
  );
}

const elementRenderers: Record<MAICSlideElement['type'], (el: MAICSlideElement) => React.ReactNode> = {
  text: renderTextElement,
  image: renderImageElement,
  shape: renderShapeElement,
  chart: renderChartElement,
  latex: renderLatexElement,
  code: renderCodeElement,
  table: renderTableElement,
  video: renderVideoElement,
};

// ─── SlideRenderer ──────────────────────────────────────────────────────────

export const SlideRenderer = React.memo<SlideRendererProps>(function SlideRenderer({ slide }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);

  const updateScale = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    const sx = el.clientWidth / DESIGN_WIDTH;
    const sy = el.clientHeight / DESIGN_HEIGHT;
    setScale(Math.min(sx, sy));
  }, []);

  useEffect(() => {
    updateScale();
    const observer = new ResizeObserver(updateScale);
    if (containerRef.current) observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, [updateScale]);

  return (
    <div
      ref={containerRef}
      className="relative w-full h-full overflow-hidden flex items-center justify-center"
      style={{ background: slide.background || '#ffffff' }}
      role="region"
      aria-label={`Slide: ${slide.title}`}
    >
      {/* Scaled design-space canvas */}
      <div
        className="relative"
        style={{
          width: DESIGN_WIDTH,
          height: DESIGN_HEIGHT,
          transform: `scale(${scale})`,
          transformOrigin: 'top left',
          position: 'absolute',
          top: Math.max(0, (containerRef.current?.clientHeight ?? 0) - DESIGN_HEIGHT * scale) / 2,
          left: Math.max(0, (containerRef.current?.clientWidth ?? 0) - DESIGN_WIDTH * scale) / 2,
        }}
      >
        {slide.elements.map((el) => {
          const renderer = elementRenderers[el.type];
          if (!renderer) return null;

          return (
            <div
              key={el.id}
              id={el.id}
              className="absolute"
              style={{
                left: el.x,
                top: el.y,
                width: el.width,
                height: el.height,
              }}
            >
              {renderer(el)}
            </div>
          );
        })}
      </div>
    </div>
  );
});
