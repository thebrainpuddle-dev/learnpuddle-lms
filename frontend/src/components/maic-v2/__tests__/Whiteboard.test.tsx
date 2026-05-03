/**
 * Tests for src/components/maic-v2/Whiteboard.tsx (MAIC-210.1 +
 * MAIC-211.2 — surface scaffold + element-list rendering).
 *
 * Whiteboard is now state-driven: it consumes WhiteboardProvider
 * context and renders the elements list via switch on type. Tests
 * mount it inside a provider with a hand-crafted initial state so
 * we can assert each renderer dispatches correctly.
 */
import { describe, test, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { Whiteboard } from '../Whiteboard';
import {
  WhiteboardProvider,
  type WhiteboardState,
  type WhiteboardElement,
} from '../../../lib/maic-v2/whiteboard-state';


function mount(initial: Partial<WhiteboardState> = {}) {
  const state: WhiteboardState = {
    isOpen: true,
    isClearing: false,
    elements: [],
    ...initial,
  };
  return render(
    <WhiteboardProvider initialState={state}>
      <Whiteboard />
    </WhiteboardProvider>,
  );
}


describe('Whiteboard surface — visibility', () => {
  test('renders nothing when state.isOpen=false', () => {
    const { container } = mount({ isOpen: false });
    expect(container.firstChild).toBeNull();
  });

  test('renders the surface when state.isOpen=true', () => {
    mount({ isOpen: true });
    expect(screen.getByTestId('maic-v2-whiteboard')).toBeInTheDocument();
    expect(screen.getByTestId('maic-v2-whiteboard-frame')).toBeInTheDocument();
  });

  test('exposes data-whiteboard-open attribute when open', () => {
    mount({ isOpen: true });
    expect(screen.getByTestId('maic-v2-whiteboard')).toHaveAttribute(
      'data-whiteboard-open',
      'true',
    );
  });

  test('uses 1000×562 aspect ratio for responsive scaling', () => {
    mount({ isOpen: true });
    const surface = screen.getByTestId('maic-v2-whiteboard');
    expect(surface).toHaveStyle({ aspectRatio: '1000 / 562' });
  });

  test('exposes element count + clearing flag as data attrs', () => {
    mount({
      isOpen: true,
      isClearing: true,
      elements: [
        { id: 'e1', type: 'wb_draw_text', content: 'a', x: 0, y: 0 },
        { id: 'e2', type: 'wb_draw_shape', shape: 'circle', x: 10, y: 10, width: 50, height: 50 },
      ],
    });
    const surface = screen.getByTestId('maic-v2-whiteboard');
    expect(surface).toHaveAttribute('data-whiteboard-element-count', '2');
    expect(surface).toHaveAttribute('data-whiteboard-clearing', 'true');
  });
});


describe('Whiteboard — element-list rendering', () => {
  test('routes wb_draw_text to TextElement', () => {
    mount({
      elements: [{ id: 'e1', type: 'wb_draw_text', content: 'hello', x: 0, y: 0 }],
    });
    expect(screen.getByTestId('maic-v2-wb-text')).toBeInTheDocument();
  });

  test('routes wb_draw_shape to ShapeElement', () => {
    mount({
      elements: [
        { id: 'e1', type: 'wb_draw_shape', shape: 'rectangle', x: 0, y: 0, width: 100, height: 50 },
      ],
    });
    expect(screen.getByTestId('maic-v2-wb-shape')).toBeInTheDocument();
  });

  test('routes wb_draw_line to LineElement', () => {
    mount({
      elements: [
        { id: 'e1', type: 'wb_draw_line', startX: 0, startY: 0, endX: 100, endY: 100 },
      ],
    });
    expect(screen.getByTestId('maic-v2-wb-line')).toBeInTheDocument();
  });

  test('routes wb_draw_table to TableElement', () => {
    mount({
      elements: [
        {
          id: 'e1',
          type: 'wb_draw_table',
          x: 0, y: 0, width: 200, height: 100,
          data: [['A', 'B'], ['1', '2']],
        },
      ],
    });
    expect(screen.getByTestId('maic-v2-wb-table')).toBeInTheDocument();
  });

  test('routes wb_draw_latex to LatexElement (MAIC-212)', () => {
    mount({
      elements: [{ id: 'l1', type: 'wb_draw_latex', latex: '\\frac{1}{2}', x: 0, y: 0 }],
    });
    expect(screen.getByTestId('maic-v2-wb-latex')).toBeInTheDocument();
  });

  test('routes wb_draw_chart to ChartElement (MAIC-213)', () => {
    mount({
      elements: [
        {
          id: 'c1',
          type: 'wb_draw_chart',
          chartType: 'bar',
          x: 0, y: 0, width: 200, height: 100,
          data: { labels: ['a'], legends: ['x'], series: [[1]] },
        },
      ],
    });
    expect(screen.getByTestId('maic-v2-wb-chart')).toBeInTheDocument();
  });

  test('routes wb_draw_code to placeholder until renderer ships', () => {
    const elements: WhiteboardElement[] = [
      { id: 'co1', type: 'wb_draw_code', language: 'js', code: 'x', x: 100, y: 0 },
    ];
    mount({ elements });
    expect(screen.getAllByTestId('maic-v2-wb-placeholder')).toHaveLength(1);
  });

  test('renders multiple elements in registry order', () => {
    mount({
      elements: [
        { id: 'a', type: 'wb_draw_text', content: 'one', x: 0, y: 0 },
        { id: 'b', type: 'wb_draw_text', content: 'two', x: 0, y: 50 },
        { id: 'c', type: 'wb_draw_shape', shape: 'circle', x: 0, y: 100, width: 50, height: 50 },
      ],
    });
    const texts = screen.getAllByTestId('maic-v2-wb-text');
    expect(texts).toHaveLength(2);
    const shapes = screen.getAllByTestId('maic-v2-wb-shape');
    expect(shapes).toHaveLength(1);
  });

  test('uses elementId as the React key when present (stable across re-render)', () => {
    // Re-render with the same elementId but different action id —
    // the registry upsert in 210.2 keeps a single element, the
    // surface's switch keys on elementKeyFor which prefers
    // elementId, so the rendered TextElement keeps its DOM identity.
    const { rerender } = render(
      <WhiteboardProvider
        initialState={{
          isOpen: true,
          isClearing: false,
          elements: [
            { id: 'action-1', elementId: 't1', type: 'wb_draw_text', content: 'first', x: 0, y: 0 },
          ],
        }}
      >
        <Whiteboard />
      </WhiteboardProvider>,
    );
    const first = screen.getByTestId('maic-v2-wb-text');
    expect(first).toHaveAttribute('data-element-id', 't1');

    // Re-render with a different action id but same elementId
    rerender(
      <WhiteboardProvider
        initialState={{
          isOpen: true,
          isClearing: false,
          elements: [
            { id: 'action-2', elementId: 't1', type: 'wb_draw_text', content: 'second', x: 0, y: 0 },
          ],
        }}
      >
        <Whiteboard />
      </WhiteboardProvider>,
    );
    expect(screen.getByTestId('maic-v2-wb-text')).toHaveAttribute('data-element-id', 't1');
  });
});
