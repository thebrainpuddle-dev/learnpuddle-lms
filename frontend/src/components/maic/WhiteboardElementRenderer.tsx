// src/components/maic/WhiteboardElementRenderer.tsx
//
// Renders structured whiteboard annotations (meta-driven) as SVG elements.
// Text, charts, LaTeX, and tables use <foreignObject>; shapes and lines use native SVG.

import React from 'react';
import katex from 'katex';
import type { WhiteboardAnnotation } from '../../types/maic';

interface Props {
  annotation: WhiteboardAnnotation;
}

export const WhiteboardElementRenderer = React.memo<Props>(function WhiteboardElementRenderer({ annotation }) {
  const meta = annotation.meta;
  if (!meta) return null;

  const [p0, p1] = annotation.points;
  if (!p0 || !p1) return null;

  const x = Math.min(p0.x, p1.x);
  const y = Math.min(p0.y, p1.y);
  const w = Math.abs(p1.x - p0.x);
  const h = Math.abs(p1.y - p0.y);

  // ── Shape (rectangle, circle, triangle) ──
  if (meta.shape) {
    return renderShape(meta.shape, x, y, w, h, meta.fill, meta.stroke ?? annotation.color, annotation.strokeWidth);
  }

  // ── Line with markers ──
  if (meta.startMarker !== undefined || meta.endMarker !== undefined) {
    return renderLine(p0.x, p0.y, p1.x, p1.y, annotation.color, annotation.strokeWidth, meta.startMarker, meta.endMarker, annotation.id);
  }

  // ── LaTeX ──
  if (meta.latex) {
    return (
      <foreignObject x={x} y={y} width={w} height={h || 60}>
        <div
          style={{ fontSize: meta.fontSize ?? 16, color: annotation.color, overflow: 'hidden' }}
          dangerouslySetInnerHTML={{ __html: renderLatexToHtml(meta.latex) }}
        />
      </foreignObject>
    );
  }

  // ── Table ──
  if (meta.headers && meta.rows) {
    return (
      <foreignObject x={x} y={y} width={w} height={h || (meta.rows.length + 1) * 32}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, color: annotation.color }}>
          <thead>
            <tr>
              {meta.headers.map((hdr, i) => (
                <th key={i} style={{ border: '1px solid #d1d5db', padding: '4px 8px', background: '#f3f4f6', fontWeight: 600, textAlign: 'left' }}>
                  {hdr}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {meta.rows.map((row, ri) => (
              <tr key={ri}>
                {row.map((cell, ci) => (
                  <td key={ci} style={{ border: '1px solid #d1d5db', padding: '4px 8px' }}>
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </foreignObject>
    );
  }

  // ── Chart (placeholder — full Recharts rendering deferred to Phase 2) ──
  if (meta.chartType && meta.data) {
    return (
      <foreignObject x={x} y={y} width={w} height={h}>
        <div style={{ width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 12, color: '#6b7280' }}>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>{meta.chartType.toUpperCase()} Chart</div>
            <div style={{ fontSize: 11, opacity: 0.7 }}>(Interactive charts coming soon)</div>
          </div>
        </div>
      </foreignObject>
    );
  }

  // ── Text / HTML ──
  if (meta.text || meta.html) {
    return (
      <foreignObject x={x} y={y} width={w} height={h || 40}>
        {meta.html ? (
          <div
            style={{ fontSize: meta.fontSize ?? 16, color: annotation.color, overflow: 'hidden' }}
            dangerouslySetInnerHTML={{ __html: meta.html }}
          />
        ) : (
          <div style={{ fontSize: meta.fontSize ?? 16, color: annotation.color, overflow: 'hidden', whiteSpace: 'pre-wrap' }}>
            {meta.text}
          </div>
        )}
      </foreignObject>
    );
  }

  return null;
});

// ─── SVG Shape Rendering ────────────────────────────────────────────────

function renderShape(
  shape: string,
  x: number, y: number, w: number, h: number,
  fill?: string, stroke?: string, strokeWidth?: number,
) {
  const sw = strokeWidth ?? 2;
  const f = fill ?? 'transparent';
  const s = stroke ?? '#3B82F6';

  switch (shape) {
    case 'rectangle':
      return <rect x={x} y={y} width={w} height={h} fill={f} stroke={s} strokeWidth={sw} rx={4} />;
    case 'circle':
      return <ellipse cx={x + w / 2} cy={y + h / 2} rx={w / 2} ry={h / 2} fill={f} stroke={s} strokeWidth={sw} />;
    case 'triangle': {
      const pts = `${x + w / 2},${y} ${x},${y + h} ${x + w},${y + h}`;
      return <polygon points={pts} fill={f} stroke={s} strokeWidth={sw} />;
    }
    default:
      return <rect x={x} y={y} width={w} height={h} fill={f} stroke={s} strokeWidth={sw} />;
  }
}

// ─── SVG Line with Markers ──────────────────────────────────────────────

function renderLine(
  x1: number, y1: number, x2: number, y2: number,
  color: string, strokeWidth: number,
  startMarker?: string, endMarker?: string,
  id?: string,
) {
  const markerId = id ?? `line-${x1}-${y1}`;

  return (
    <g>
      <defs>
        {(endMarker === 'arrow' || startMarker === 'arrow') && (
          <marker id={`arrow-${markerId}`} markerWidth="10" markerHeight="7" refX="10" refY="3.5" orient="auto">
            <polygon points="0 0, 10 3.5, 0 7" fill={color} />
          </marker>
        )}
        {(endMarker === 'dot' || startMarker === 'dot') && (
          <marker id={`dot-${markerId}`} markerWidth="8" markerHeight="8" refX="4" refY="4" orient="auto">
            <circle cx="4" cy="4" r="3" fill={color} />
          </marker>
        )}
      </defs>
      <line
        x1={x1} y1={y1} x2={x2} y2={y2}
        stroke={color}
        strokeWidth={strokeWidth}
        markerStart={
          startMarker === 'arrow' ? `url(#arrow-${markerId})`
            : startMarker === 'dot' ? `url(#dot-${markerId})`
            : undefined
        }
        markerEnd={
          endMarker === 'arrow' ? `url(#arrow-${markerId})`
            : endMarker === 'dot' ? `url(#dot-${markerId})`
            : undefined
        }
      />
    </g>
  );
}

// ─── LaTeX → HTML ───────────────────────────────────────────────────────

function renderLatexToHtml(latex: string): string {
  try {
    return katex.renderToString(latex, { throwOnError: false, displayMode: true });
  } catch {
    return `<code style="font-family: monospace; font-size: 14px; background: #f5f5f5; padding: 4px 8px; border-radius: 4px;">${latex}</code>`;
  }
}
