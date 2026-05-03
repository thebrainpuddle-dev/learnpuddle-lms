/**
 * LatexElement — renders a wb_draw_latex element via KaTeX.
 *
 * Source: THU-MAIC/OpenMAIC main lib/action/engine.ts:423-457
 *         (executeWbDrawLatex — katex.renderToString call) +
 *         components/slide-renderer/components/element/LatexElement/
 *         BaseLatexElement.tsx (KatexContent auto-scale logic, lines
 *         70-120; simplified — no rotation, no SVG fallback path).
 *
 * Wire shape (apps/maic/protocol/actions.py WbDrawLatexAction):
 *   id, elementId?, latex, x, y, width?, height?, color?
 *
 * Architectural divergence from upstream:
 *   Upstream pre-renders KaTeX HTML in the action engine and stores it
 *   on the element. We render in the React component on each render
 *   (memoised on the latex string) so the element registry stores the
 *   wire-format action verbatim — no synthetic html field. KaTeX's
 *   renderToString is fast (<1ms for typical formulae) and the latex
 *   string is stable, so re-render cost is negligible.
 *
 * Phase 2 deferrals:
 *   - rotation (upstream BaseLatexElement supports it; protocol doesn't)
 *   - legacy SVG path fallback (upstream supports MathML→SVG; we only
 *     ship KaTeX HTML output. KaTeX's `throwOnError:false` returns the
 *     malformed source wrapped in a red box so failures stay visible
 *     without crashing the surface.)
 */
import { useLayoutEffect, useMemo, useRef, useState } from 'react';
import katex from 'katex';
import 'katex/dist/katex.min.css';

import type { Action } from '../../../lib/maic-v2/action-types';

type LatexAction = Extract<Action, { type: 'wb_draw_latex' }>;

const DEFAULT_WIDTH = 400;
const DEFAULT_HEIGHT = 80;
const DEFAULT_COLOR = '#000000';

export interface LatexElementProps {
  element: LatexAction;
}

export function LatexElement({ element }: LatexElementProps) {
  const width = element.width ?? DEFAULT_WIDTH;
  const height = element.height ?? DEFAULT_HEIGHT;
  const color = element.color ?? DEFAULT_COLOR;
  const elementKey = element.elementId ?? element.id;

  // Render once per latex change. KaTeX is sync and fast; useMemo
  // avoids re-running on unrelated re-renders (parent state, layout
  // measurement, etc.).
  const html = useMemo(() => {
    try {
      return katex.renderToString(element.latex, {
        throwOnError: false,
        displayMode: true,
        output: 'html',
      });
    } catch (err) {
      // throwOnError:false should swallow most issues, but guard
      // against any unexpected KaTeX init failure.
      // eslint-disable-next-line no-console
      console.warn(
        '[LatexElement] katex.renderToString failed; falling back to raw text',
        err,
      );
      return `<span style="color:#cc0000;font-family:monospace;">${escapeHtml(element.latex)}</span>`;
    }
  }, [element.latex]);

  // Auto-scale the rendered KaTeX content to fit the element box —
  // KaTeX's natural width/height depends on font metrics, which we
  // can't predict from the latex source alone. Mirrors upstream
  // KatexContent (BaseLatexElement.tsx:84-91).
  const innerRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);

  useLayoutEffect(() => {
    if (!innerRef.current) return;
    const naturalW = innerRef.current.scrollWidth;
    const naturalH = innerRef.current.scrollHeight;
    if (naturalW > 0 && naturalH > 0) {
      const next = Math.min(width / naturalW, height / naturalH, 1);
      setScale(next);
    }
  }, [html, width, height]);

  return (
    <div
      data-testid="maic-v2-wb-latex"
      data-element-id={elementKey}
      className="absolute overflow-hidden flex items-center justify-center"
      style={{
        top: `${element.y}px`,
        left: `${element.x}px`,
        width: `${width}px`,
        height: `${height}px`,
        color,
      }}
    >
      <div
        ref={innerRef}
        data-testid="maic-v2-wb-latex-inner"
        style={{
          transformOrigin: 'center center',
          transform: `scale(${scale})`,
          whiteSpace: 'nowrap',
        }}
        dangerouslySetInnerHTML={{ __html: html }}
      />
    </div>
  );
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
