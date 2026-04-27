// src/components/maic/SlideRenderer.tsx
//
// Renders a single MAICSlide by mapping each element to its visual
// representation. Elements are absolutely positioned within a viewport
// container that preserves 16:9 aspect ratio.

import React, { useRef, useState, useEffect, useCallback } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import DOMPurify from 'dompurify';
import katex from 'katex';
import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  AreaChart, Area, RadarChart, Radar, PolarGrid, PolarAngleAxis,
  ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip,
  Legend, ResponsiveContainer,
} from 'recharts';
import type { MAICSlide, MAICSlideElement, MAICSlideTransition } from '../../types/maic';
import { useMAICSettingsStore } from '../../stores/maicSettingsStore';
import { Shimmer } from './Shimmer';
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
  /**
   * CG-P0-3: When true the Celery image-fill task is still running.
   * Image elements with an empty src should show a "fetching image…"
   * skeleton rather than immediately falling back to a random Unsplash
   * photo (which would be replaced anyway once the task completes).
   */
  imagesPending?: boolean;
}

// ─── Element renderers ──────────────────────────────────────────────────────

function renderTextElement(el: MAICSlideElement): React.ReactNode {
  // Convert literal \n to <br> for proper line breaks, and sanitize
  const html = el.content
    .replace(/\\n/g, '<br>')
    .replace(/\n/g, '<br>');

  // textShadow gives a subtle white halo so text remains readable when the
  // LLM's generated layout accidentally puts an image rect underneath it.
  // Cheap defense — combined with the z-index layering above, text always
  // sits on top and stays legible.
  const hasExplicitBg = !!(el.style?.background || el.style?.backgroundColor);

  return (
    <div
      className="overflow-auto text-gray-900"
      style={{
        fontSize: (el.style?.fontSize as string) || '16px',
        color: (el.style?.color as string) || undefined,
        fontWeight: (el.style?.fontWeight as string) || undefined,
        textAlign: (el.style?.textAlign as string) as React.CSSProperties['textAlign'] || undefined,
        lineHeight: 1.5,
        textShadow: hasExplicitBg
          ? undefined
          : '0 0 6px rgba(255,255,255,0.9), 0 0 12px rgba(255,255,255,0.7)',
      }}
      dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(html) }}
    />
  );
}

function ImageElement({ el, imagesPending }: { el: MAICSlideElement; imagesPending?: boolean }) {
  const alt = el.content || 'Slide image';
  const [loaded, setLoaded] = React.useState(false);
  const [error, setError] = React.useState(false);

  const providerDisabled = !!el.meta?.imageProviderDisabled;

  // Resolve image src — use el.src if valid; otherwise fall back only when
  // the tenant has image generation enabled. Random Unsplash photos behind
  // the user's back is bad UX for schools that deliberately opt out.
  //
  // SEC-P0-4 (2026-04-23): `data:` URLs are NOT accepted. An LLM-controlled
  // `data:text/html;base64,...` or `data:image/svg+xml;base64,...<script>`
  // would execute in the slide renderer. Only allow:
  //   - http(s) URLs to the image providers we fetch from
  //   - site-relative paths starting with `/` (our own backend/static)
  //
  // CG-P0-3: When el.src is empty AND imagesPending is true, the Celery
  // image-fill task hasn't yet run. Return '' to render the "fetching
  // image…" skeleton rather than a random Unsplash fallback (which would
  // be replaced anyway once the task completes).
  const resolvedSrc = React.useMemo(() => {
    const raw = (el.src || '').trim();
    if (raw) {
      if (raw.startsWith('https://') || raw.startsWith('http://') || raw.startsWith('/')) {
        return raw;
      }
      // Anything else (data:, javascript:, vbscript:, file:, blob: from
      // an external origin, etc.) is rejected. Fall through to placeholder.
    }
    if (providerDisabled) return '';  // render placeholder instead
    // CG-P0-3: images still filling — hold off on Unsplash fallback.
    if (imagesPending) return '';
    const keyword = encodeURIComponent((el.content || 'education').slice(0, 80));
    return `https://source.unsplash.com/800x450/?${keyword}`;
  }, [el.src, el.content, providerDisabled, imagesPending]);

  // "Provider disabled" placeholder — honest about why there's no image.
  if (providerDisabled && !resolvedSrc) {
    return (
      <div className="relative h-full w-full">
        <div className="absolute inset-0 flex flex-col items-center justify-center bg-gradient-to-br from-slate-100 to-slate-200 rounded-lg p-3 text-center">
          <svg className="h-8 w-8 text-slate-400 mb-2" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="m2.25 15.75 5.159-5.159a2.25 2.25 0 0 1 3.182 0l5.159 5.159m-1.5-1.5 1.409-1.409a2.25 2.25 0 0 1 3.182 0l2.909 2.909M3.75 21h16.5a2.25 2.25 0 0 0 2.25-2.25V6.75a2.25 2.25 0 0 0-2.25-2.25H3.75A2.25 2.25 0 0 0 1.5 6.75v13.5A2.25 2.25 0 0 0 3.75 21Z" />
          </svg>
          <span className="text-[10px] font-medium text-slate-500 mb-0.5">
            AI images disabled
          </span>
          <span className="text-[9px] text-slate-400 line-clamp-2">
            Ask your admin to enable image generation in classroom settings.
          </span>
        </div>
      </div>
    );
  }

  // CG-P0-3: "Fetching image…" skeleton — shown when el.src is empty and
  // the Celery fill task is still in progress. Uses the existing Shimmer
  // component so it visually matches the normal image-loading skeleton,
  // but adds a small caption so the teacher/student knows it's transient.
  if (!resolvedSrc && imagesPending) {
    return (
      <div className="relative h-full w-full" data-testid="image-fetching-skeleton">
        <Shimmer
          className="absolute inset-0 rounded-lg"
          baseClassName="bg-gray-100"
        />
        <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
          <svg
            className="h-7 w-7 text-gray-300 mb-1.5 animate-pulse"
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth={1}
            stroke="currentColor"
            aria-hidden="true"
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="m2.25 15.75 5.159-5.159a2.25 2.25 0 0 1 3.182 0l5.159 5.159m-1.5-1.5 1.409-1.409a2.25 2.25 0 0 1 3.182 0l2.909 2.909M3.75 21h16.5a2.25 2.25 0 0 0 2.25-2.25V6.75a2.25 2.25 0 0 0-2.25-2.25H3.75A2.25 2.25 0 0 0 1.5 6.75v13.5A2.25 2.25 0 0 0 3.75 21Z" />
          </svg>
          <span className="text-[9px] text-gray-400 font-medium select-none">
            Fetching image…
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="relative h-full w-full">
      {!loaded && !error && (
        <>
          <Shimmer
            className="absolute inset-0 rounded-lg"
            baseClassName="bg-gray-100"
          />
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
            <svg className="h-8 w-8 text-gray-300" fill="none" viewBox="0 0 24 24" strokeWidth={1} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="m2.25 15.75 5.159-5.159a2.25 2.25 0 0 1 3.182 0l5.159 5.159m-1.5-1.5 1.409-1.409a2.25 2.25 0 0 1 3.182 0l2.909 2.909M3.75 21h16.5a2.25 2.25 0 0 0 2.25-2.25V6.75a2.25 2.25 0 0 0-2.25-2.25H3.75A2.25 2.25 0 0 0 1.5 6.75v13.5A2.25 2.25 0 0 0 3.75 21Z" />
            </svg>
          </div>
        </>
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

// Escape user/LLM input for safe interpolation into an HTML string.
// Used by the LaTeX fallback path to avoid interpolating raw content
// (which the LLM controls) directly into the DOM.
function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function renderLatexElement(el: MAICSlideElement): React.ReactNode {
  let html: string;
  try {
    // KaTeX with trust:false (default) blocks javascript: URIs, but we still
    // pass output through DOMPurify below for defense-in-depth — LLM-supplied
    // LaTeX source + any future KaTeX regression should never reach the DOM
    // unsanitized.
    html = katex.renderToString(el.content, {
      throwOnError: false,
      displayMode: true,
      trust: false,
      strict: 'ignore',
    });
  } catch {
    // Fallback: the raw LLM content is interpolated into an HTML string. We
    // MUST escape it — without the escape, any `</code><img src=x onerror=...>`
    // in el.content would execute. (SEC-P0-2 from 2026-04-23 ultrareview.)
    html = `<code>${escapeHtml(el.content)}</code>`;
  }

  return (
    <div
      className="overflow-auto"
      style={{
        fontSize: (el.style?.fontSize as string) || '18px',
        color: (el.style?.color as string) || undefined,
      }}
      dangerouslySetInnerHTML={{
        __html: DOMPurify.sanitize(html, {
          // KaTeX emits MathML + annotated spans — allow its footprint.
          ADD_TAGS: ['math', 'mrow', 'mi', 'mo', 'mn', 'msup', 'msub', 'mfrac',
                     'msqrt', 'mroot', 'munderover', 'munder', 'mover',
                     'annotation', 'semantics', 'mspace', 'mtext'],
          ADD_ATTR: ['mathvariant', 'mathsize', 'xmlns', 'encoding'],
          FORBID_ATTR: ['onerror', 'onload', 'onclick', 'onmouseover'],
        }),
      }}
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

// ─── Transition variants ────────────────────────────────────────────────────

function getTransitionVariants(transition: MAICSlideTransition, direction: 'next' | 'prev') {
  const sign = direction === 'next' ? 1 : -1;

  switch (transition) {
    case 'none':
      return { initial: {}, animate: {}, exit: {} };
    case 'fade':
      return {
        initial: { opacity: 0 },
        animate: { opacity: 1 },
        exit: { opacity: 0 },
      };
    case 'slideLeft':
      return {
        initial: { x: `${100 * sign}%`, opacity: 0 },
        animate: { x: 0, opacity: 1 },
        exit: { x: `${-100 * sign}%`, opacity: 0 },
      };
    case 'slideRight':
      return {
        initial: { x: `${-100 * sign}%`, opacity: 0 },
        animate: { x: 0, opacity: 1 },
        exit: { x: `${100 * sign}%`, opacity: 0 },
      };
    case 'slideUp':
      return {
        initial: { y: `${100 * sign}%`, opacity: 0 },
        animate: { y: 0, opacity: 1 },
        exit: { y: `${-100 * sign}%`, opacity: 0 },
      };
    case 'slideDown':
      return {
        initial: { y: `${-100 * sign}%`, opacity: 0 },
        animate: { y: 0, opacity: 1 },
        exit: { y: `${100 * sign}%`, opacity: 0 },
      };
    case 'zoom':
      return {
        initial: { scale: 0.8, opacity: 0 },
        animate: { scale: 1, opacity: 1 },
        exit: { scale: 1.2, opacity: 0 },
      };
    case 'flip':
      return {
        initial: { rotateY: 90, opacity: 0 },
        animate: { rotateY: 0, opacity: 1 },
        exit: { rotateY: -90, opacity: 0 },
      };
  }
}

// ─── SlideRenderer ──────────────────────────────────────────────────────────

export const SlideRenderer = React.memo<SlideRendererProps>(function SlideRenderer({
  slide,
  slideNumber,
  totalSlides,
  imagesPending,
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);

  // ─── Transition direction tracking ─────────────────────────────────────
  const slideTransition = useMAICSettingsStore((s) => s.slideTransition);
  const prevSlideIdRef = useRef(slide.id);
  const slideIndexRef = useRef(slideNumber ?? 0);
  const [direction, setDirection] = useState<'next' | 'prev'>('next');

  useEffect(() => {
    if (slide.id !== prevSlideIdRef.current) {
      const currentIndex = slideNumber ?? 0;
      setDirection(currentIndex >= slideIndexRef.current ? 'next' : 'prev');
      prevSlideIdRef.current = slide.id;
      slideIndexRef.current = currentIndex;
    }
  }, [slide.id, slideNumber]);

  const variants = getTransitionVariants(slideTransition, direction);

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
      style={{
        background: slide.background || '#ffffff',
        perspective: slideTransition === 'flip' ? 1000 : undefined,
      }}
      role="region"
      aria-label={`Slide: ${slide.title}`}
    >
      {/* Animated transition wrapper */}
      <AnimatePresence mode="wait">
        <motion.div
          key={slide.id}
          variants={variants}
          initial="initial"
          animate="animate"
          exit="exit"
          transition={{ duration: 0.3, ease: 'easeInOut' }}
          className="w-full h-full"
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
              // Layer order: images & shapes behind; charts/videos middle;
              // text/latex/code/table on top. Prevents the common LLM-
              // output failure where an image rect overlaps the title rect
              // and occludes the text. Text also gets a subtle white
              // backdrop shadow for legibility if it does overlap an image.
              const zIndex =
                el.type === 'image' || el.type === 'shape' ? 1 :
                el.type === 'chart' || el.type === 'video' ? 5 :
                10;

              // For image elements, pass imagesPending so the renderer can
              // show the "fetching image…" skeleton (CG-P0-3) rather than
              // immediately falling back to a random Unsplash photo.
              const renderer = el.type === 'image'
                ? () => <ImageElement el={el} imagesPending={imagesPending} />
                : elementRenderers[el.type];
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
                    zIndex,
                  }}
                >
                  {renderer(el)}
                </div>
              );
            })}
          </div>
        </motion.div>
      </AnimatePresence>

      {/* Slide counter indicator */}
      {slideNumber != null && totalSlides != null && totalSlides > 1 && (
        <div className="absolute bottom-3 right-4 text-[10px] text-gray-300 font-mono tabular-nums select-none">
          {slideNumber} / {totalSlides}
        </div>
      )}
    </div>
  );
});
