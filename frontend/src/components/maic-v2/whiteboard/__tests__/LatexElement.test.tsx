/**
 * Tests for src/components/maic-v2/whiteboard/LatexElement.tsx
 * (MAIC-212).
 */
import { describe, test, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { LatexElement } from '../LatexElement';
import type { Action } from '../../../../lib/maic-v2/action-types';

type L = Extract<Action, { type: 'wb_draw_latex' }>;

function make(overrides: Partial<L> = {}): L {
  return {
    id: 'a1',
    type: 'wb_draw_latex',
    latex: '\\frac{1}{2}',
    x: 0,
    y: 0,
    ...overrides,
  };
}

describe('LatexElement', () => {
  test('renders KaTeX HTML inside the inner wrapper', () => {
    const { container } = render(<LatexElement element={make()} />);
    const inner = screen.getByTestId('maic-v2-wb-latex-inner');
    // KaTeX always emits a `class="katex"` (or `katex-display`) span at
    // the top level of its HTML output.
    expect(inner.innerHTML).toMatch(/katex/);
  });

  test('renders the requested formula visibly (1/2 fraction)', () => {
    const { container } = render(<LatexElement element={make({ latex: '\\frac{1}{2}' })} />);
    // KaTeX HTML for \\frac contains numerator "1" and denominator "2"
    // wrapped in spans. Guard against KaTeX version drift by asserting
    // the digits appear in the rendered text.
    const text = container.textContent ?? '';
    expect(text).toContain('1');
    expect(text).toContain('2');
  });

  test('positions absolute at action coords', () => {
    render(<LatexElement element={make({ x: 70, y: 130 })} />);
    const el = screen.getByTestId('maic-v2-wb-latex');
    expect(el).toHaveStyle({ left: '70px', top: '130px' });
  });

  test('default 400×80 + color #000', () => {
    render(<LatexElement element={make()} />);
    const el = screen.getByTestId('maic-v2-wb-latex');
    const style = el.getAttribute('style') ?? '';
    expect(style).toContain('width: 400px');
    expect(style).toContain('height: 80px');
    expect(style).toContain('color: #000000');
  });

  test('honors caller-provided width/height/color', () => {
    render(
      <LatexElement element={make({ width: 280, height: 60, color: '#0066cc' })} />,
    );
    const el = screen.getByTestId('maic-v2-wb-latex');
    const style = el.getAttribute('style') ?? '';
    expect(style).toContain('width: 280px');
    expect(style).toContain('height: 60px');
    expect(style).toContain('color: #0066cc');
  });

  test('exposes data-element-id (elementId wins over id)', () => {
    render(<LatexElement element={make({ id: 'a1', elementId: 'L1' })} />);
    expect(screen.getByTestId('maic-v2-wb-latex')).toHaveAttribute('data-element-id', 'L1');
  });

  test('falls back to id when elementId absent', () => {
    render(<LatexElement element={make({ id: 'a1' })} />);
    expect(screen.getByTestId('maic-v2-wb-latex')).toHaveAttribute('data-element-id', 'a1');
  });

  test('throwOnError:false — malformed latex still renders without crashing', () => {
    // KaTeX returns a red-bracketed error rendering for bad input
    // when throwOnError:false. The component should survive.
    const { container } = render(
      <LatexElement element={make({ latex: '\\notarealcommand{x' })} />,
    );
    expect(screen.getByTestId('maic-v2-wb-latex-inner')).toBeInTheDocument();
    // Some KaTeX versions emit a span with class "katex-error" for
    // failed parses; either that or a red-styled span is acceptable.
    const inner = screen.getByTestId('maic-v2-wb-latex-inner');
    expect(inner.innerHTML.length).toBeGreaterThan(0);
  });

  test('inner wrapper has a transform-scale (auto-fit) style', () => {
    render(<LatexElement element={make()} />);
    const inner = screen.getByTestId('maic-v2-wb-latex-inner');
    // useLayoutEffect sets scale; in jsdom-ish env scrollWidth is 0 so
    // scale stays at the initial 1.  Either way, the transform style
    // is present.
    const style = inner.getAttribute('style') ?? '';
    expect(style).toContain('transform');
    expect(style).toContain('scale(');
  });
});
