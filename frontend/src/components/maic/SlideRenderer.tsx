// src/components/maic/SlideRenderer.tsx
//
// Renders a single MAICSlide by mapping each element to its visual
// representation. Elements are absolutely positioned within a viewport
// container that preserves 16:9 aspect ratio.

import React, { useRef, useState, useEffect, useCallback } from 'react';
import DOMPurify from 'dompurify';
import katex from 'katex';
import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  AreaChart, Area, RadarChart, Radar, PolarGrid, PolarAngleAxis,
  ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip,
  Legend, ResponsiveContainer,
} from 'recharts';
import type { MAICSlide, MAICSlideElement } from '../../types/maic';
import { cn } from '../../lib/utils';

// Design space the LLM generates coordinates for
const DESIGN_WIDTH = 800;
const DESIGN_HEIGHT = 450;

interface SlideRendererProps {
  slide: MAICSlide;
  /** 1-based slide number for the counter indicator */
  slideNumber?: number;
  /** Total number of slides for the counter indicator */
  totalSlides?: number;
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
      dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(html) }}
    />
  );
}

function ImageElement({ el }: { el: MAICSlideElement }) {
  const alt = el.content || 'Slide image';
  const [loaded, setLoaded] = React.useState(false);
  const [error, setError] = React.useState(false);

  // Resolve image src — use el.src if valid, otherwise generate from content keyword
  const resolvedSrc = React.useMemo(() => {
    const raw = el.src || '';
    if (raw && (raw.startsWith('http') || raw.startsWith('/') || raw.startsWith('data:'))) {
      return raw;
    }
    // No valid src — use Unsplash Source for a relevant stock photo
    const keyword = encodeURIComponent((el.content || 'education').slice(0, 80));
    return `https://source.unsplash.com/800x450/?${keyword}`;
  }, [el.src, el.content]);

  return (
    <div className="relative h-full w-full">
      {!loaded && !error && (
        <div className="absolute inset-0 flex items-center justify-center bg-gray-100 rounded-lg animate-pulse">
          <svg className="h-8 w-8 text-gray-300" fill="none" viewBox="0 0 24 24" strokeWidth={1} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="m2.25 15.75 5.159-5.159a2.25 2.25 0 0 1 3.182 0l5.159 5.159m-1.5-1.5 1.409-1.409a2.25 2.25 0 0 1 3.182 0l2.909 2.909M3.75 21h16.5a2.25 2.25 0 0 0 2.25-2.25V6.75a2.25 2.25 0 0 0-2.25-2.25H3.75A2.25 2.25 0 0 0 1.5 6.75v13.5A2.25 2.25 0 0 0 3.75 21Z" />
          </svg>
        </div>
      )}
      <img
        src={resolvedSrc}
        alt={alt}
        className={cn(
          'h-full w-full object-cover rounded-lg transition-opacity duration-300',
          loaded ? 'opacity-100' : 'opacity-0',
        )}
        loading="lazy"
        onLoad={() => setLoaded(true)}
        onError={() => setError(true)}
      />
      {error && (
        <div className="absolute inset-0 flex flex-col items-center justify-center bg-gradient-to-br from-slate-100 to-slate-200 rounded-lg p-3">
          <svg className="h-8 w-8 text-slate-400 mb-1" fill="none" viewBox="0 0 24 24" strokeWidth={1} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="m2.25 15.75 5.159-5.159a2.25 2.25 0 0 1 3.182 0l5.159 5.159m-1.5-1.5 1.409-1.409a2.25 2.25 0 0 1 3.182 0l2.909 2.909M3.75 21h16.5a2.25 2.25 0 0 0 2.25-2.25V6.75a2.25 2.25 0 0 0-2.25-2.25H3.75A2.25 2.25 0 0 0 1.5 6.75v13.5A2.25 2.25 0 0 0 3.75 21Z" />
          </svg>
          <span className="text-[10px] text-slate-400 text-center line-clamp-2">{alt}</span>
        </div>
      )}
    </div>
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
      ) : shape === 'triangle' ? (
        <polygon
          points={`${el.width / 2},${strokeWidth} ${strokeWidth},${el.height - strokeWidth} ${el.width - strokeWidth},${el.height - strokeWidth}`}
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

const CHART_COLORS = ['#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6', '#EC4899', '#06B6D4', '#F97316'];

function ChartElement({ el }: { el: MAICSlideElement }): React.ReactElement {
  let chartData: Record<string, unknown>[] = [];
  let chartType = 'bar';
  let title = '';

  try {
    const parsed = JSON.parse(el.content) as {
      type?: string;
      chartType?: string;
      data?: Record<string, unknown>[];
      title?: string;
      labels?: string[];
      values?: number[];
      datasets?: { label?: string; data?: number[] }[];
    };
    chartType = parsed.type || parsed.chartType || 'bar';
    title = parsed.title || '';

    if (parsed.data && Array.isArray(parsed.data)) {
      chartData = parsed.data;
    } else if (parsed.labels && parsed.values) {
      chartData = parsed.labels.map((label, i) => ({
        name: label,
        value: parsed.values![i] ?? 0,
      }));
    } else if (parsed.datasets && parsed.labels) {
      chartData = parsed.labels.map((label, i) => {
        const point: Record<string, unknown> = { name: label };
        parsed.datasets!.forEach((ds, di) => {
          point[ds.label || `series${di}`] = ds.data?.[i] ?? 0;
        });
        return point;
      });
    }
  } catch {
    return (
      <div className="h-full w-full flex items-center justify-center bg-gray-50 rounded text-gray-400 text-sm">
        Invalid chart data
      </div>
    );
  }

  if (chartData.length === 0) {
    return (
      <div className="h-full w-full flex items-center justify-center bg-gray-50 rounded text-gray-400 text-sm">
        No chart data
      </div>
    );
  }

  const dataKeys = Object.keys(chartData[0]).filter((k) => k !== 'name');

  return (
    <div className="h-full w-full flex flex-col">
      {title && <div className="text-xs font-semibold text-gray-700 text-center mb-1 truncate">{title}</div>}
      <div className="flex-1 min-h-0">
        <ResponsiveContainer width="100%" height="100%">
          {renderChart(chartType, chartData, dataKeys)}
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function renderChart(type: string, data: Record<string, unknown>[], dataKeys: string[]): React.ReactElement {
  switch (type) {
    case 'line':
      return (
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
          <XAxis dataKey="name" tick={{ fontSize: 10 }} />
          <YAxis tick={{ fontSize: 10 }} />
          <Tooltip />
          <Legend wrapperStyle={{ fontSize: 10 }} />
          {dataKeys.map((key, i) => (
            <Line key={key} type="monotone" dataKey={key} stroke={CHART_COLORS[i % CHART_COLORS.length]} strokeWidth={2} dot={{ r: 3 }} />
          ))}
        </LineChart>
      );
    case 'pie':
      return (
        <PieChart>
          <Pie data={data} dataKey={dataKeys[0] || 'value'} nameKey="name" cx="50%" cy="50%" outerRadius="70%" label={{ fontSize: 10 }}>
            {data.map((_, i) => (
              <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
            ))}
          </Pie>
          <Tooltip />
          <Legend wrapperStyle={{ fontSize: 10 }} />
        </PieChart>
      );
    case 'area':
      return (
        <AreaChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
          <XAxis dataKey="name" tick={{ fontSize: 10 }} />
          <YAxis tick={{ fontSize: 10 }} />
          <Tooltip />
          <Legend wrapperStyle={{ fontSize: 10 }} />
          {dataKeys.map((key, i) => (
            <Area key={key} type="monotone" dataKey={key} fill={CHART_COLORS[i % CHART_COLORS.length]} stroke={CHART_COLORS[i % CHART_COLORS.length]} fillOpacity={0.3} />
          ))}
        </AreaChart>
      );
    case 'scatter':
      return (
        <ScatterChart>
          <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
          <XAxis dataKey={dataKeys[0] || 'x'} tick={{ fontSize: 10 }} />
          <YAxis dataKey={dataKeys[1] || 'y'} tick={{ fontSize: 10 }} />
          <Tooltip />
          <Scatter data={data} fill={CHART_COLORS[0]} />
        </ScatterChart>
      );
    case 'radar':
      return (
        <RadarChart data={data} cx="50%" cy="50%" outerRadius="70%">
          <PolarGrid />
          <PolarAngleAxis dataKey="name" tick={{ fontSize: 10 }} />
          {dataKeys.map((key, i) => (
            <Radar key={key} dataKey={key} stroke={CHART_COLORS[i % CHART_COLORS.length]} fill={CHART_COLORS[i % CHART_COLORS.length]} fillOpacity={0.3} />
          ))}
          <Legend wrapperStyle={{ fontSize: 10 }} />
          <Tooltip />
        </RadarChart>
      );
    case 'bar':
    default:
      return (
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
          <XAxis dataKey="name" tick={{ fontSize: 10 }} />
          <YAxis tick={{ fontSize: 10 }} />
          <Tooltip />
          <Legend wrapperStyle={{ fontSize: 10 }} />
          {dataKeys.map((key, i) => (
            <Bar key={key} dataKey={key} fill={CHART_COLORS[i % CHART_COLORS.length]} radius={[2, 2, 0, 0]} />
          ))}
        </BarChart>
      );
  }
}

function renderLatexElement(el: MAICSlideElement): React.ReactNode {
  let html: string;
  try {
    html = katex.renderToString(el.content, {
      throwOnError: false,
      displayMode: true,
    });
  } catch {
    html = `<code>${el.content}</code>`;
  }

  return (
    <div
      className="overflow-auto"
      style={{
        fontSize: (el.style?.fontSize as string) || '18px',
        color: (el.style?.color as string) || undefined,
      }}
      dangerouslySetInnerHTML={{ __html: html }}
    />
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
  image: (el) => <ImageElement el={el} />,
  shape: renderShapeElement,
  chart: (el) => <ChartElement el={el} />,
  latex: renderLatexElement,
  code: renderCodeElement,
  table: renderTableElement,
  video: renderVideoElement,
};

// ─── SlideRenderer ──────────────────────────────────────────────────────────

export const SlideRenderer = React.memo<SlideRendererProps>(function SlideRenderer({
  slide,
  slideNumber,
  totalSlides,
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);

  // ─── Slide transition state ────────────────────────────────────────────
  const [isTransitioning, setIsTransitioning] = useState(false);
  const [displaySlide, setDisplaySlide] = useState(slide);

  useEffect(() => {
    if (displaySlide.id === slide.id) {
      // Same slide — just update content in-place without transition
      setDisplaySlide(slide);
      return;
    }
    setIsTransitioning(true);
    const timer = setTimeout(() => {
      setDisplaySlide(slide);
      setIsTransitioning(false);
    }, 300);
    return () => clearTimeout(timer);
  }, [slide]); // eslint-disable-line react-hooks/exhaustive-deps

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
      style={{ background: displaySlide.background || '#ffffff' }}
      role="region"
      aria-label={`Slide: ${displaySlide.title}`}
    >
      {/* Transition wrapper */}
      <div
        className={cn(
          'transition-opacity duration-300 ease-in-out w-full h-full',
          isTransitioning ? 'opacity-0' : 'opacity-100',
        )}
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
          {displaySlide.elements.map((el) => {
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

      {/* Slide counter indicator */}
      {slideNumber != null && totalSlides != null && totalSlides > 1 && (
        <div className="absolute bottom-3 right-4 text-[10px] text-gray-300 font-mono tabular-nums select-none">
          {slideNumber} / {totalSlides}
        </div>
      )}
    </div>
  );
});
