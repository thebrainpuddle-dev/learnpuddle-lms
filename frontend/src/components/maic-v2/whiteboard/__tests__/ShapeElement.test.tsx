/**
 * Tests for src/components/maic-v2/whiteboard/ShapeElement.tsx
 * (MAIC-211.2).
 */
import { describe, test, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { ShapeElement } from '../ShapeElement';
import type { Action } from '../../../../lib/maic-v2/action-types';

type S = Extract<Action, { type: 'wb_draw_shape' }>;

function make(overrides: Partial<S> = {}): S {
  return {
    id: 'a1',
    type: 'wb_draw_shape',
    shape: 'rectangle',
    x: 0,
    y: 0,
    width: 100,
    height: 50,
    ...overrides,
  };
}

describe('ShapeElement', () => {
  test.each<['rectangle' | 'circle' | 'triangle']>([['rectangle'], ['circle'], ['triangle']])(
    'renders shape=%s with the matching SHAPE_PATHS path',
    (shape) => {
      const { container } = render(<ShapeElement element={make({ shape })} />);
      const el = screen.getByTestId('maic-v2-wb-shape');
      expect(el).toHaveAttribute('data-shape', shape);
      const path = container.querySelector('path');
      expect(path).not.toBeNull();
      expect(path!.getAttribute('d')).toBeTruthy();
    },
  );

  test('uses 1000×1000 viewBox so the path scales to width/height', () => {
    const { container } = render(<ShapeElement element={make({ width: 200, height: 80 })} />);
    const svg = container.querySelector('svg');
    expect(svg).not.toBeNull();
    expect(svg!.getAttribute('viewBox')).toBe('0 0 1000 1000');
    expect(svg!.getAttribute('width')).toBe('200');
    expect(svg!.getAttribute('height')).toBe('80');
  });

  test('default fill is upstream blue #5b9bd5 when fillColor omitted', () => {
    const { container } = render(<ShapeElement element={make()} />);
    expect(container.querySelector('path')!.getAttribute('fill')).toBe('#5b9bd5');
  });

  test('honors fillColor when provided', () => {
    const { container } = render(<ShapeElement element={make({ fillColor: '#00ff00' })} />);
    expect(container.querySelector('path')!.getAttribute('fill')).toBe('#00ff00');
  });

  test('positions absolute at action coords', () => {
    render(<ShapeElement element={make({ x: 30, y: 40 })} />);
    const el = screen.getByTestId('maic-v2-wb-shape');
    expect(el).toHaveStyle({ left: '30px', top: '40px' });
  });

  test('exposes data-element-id (elementId wins over id)', () => {
    render(<ShapeElement element={make({ id: 'a1', elementId: 's1' })} />);
    expect(screen.getByTestId('maic-v2-wb-shape')).toHaveAttribute('data-element-id', 's1');
  });
});
