/**
 * Tests for src/components/maic-v2/whiteboard/LineElement.tsx
 * (MAIC-211.2).
 */
import { describe, test, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { LineElement } from '../LineElement';
import type { Action } from '../../../../lib/maic-v2/action-types';

type L = Extract<Action, { type: 'wb_draw_line' }>;

function make(overrides: Partial<L> = {}): L {
  return {
    id: 'a1',
    type: 'wb_draw_line',
    startX: 100,
    startY: 100,
    endX: 200,
    endY: 200,
    ...overrides,
  };
}

describe('LineElement', () => {
  test('positions wrapper at min(start, end) corner', () => {
    render(<LineElement element={make({ startX: 200, startY: 300, endX: 100, endY: 200 })} />);
    const wrapper = screen.getByTestId('maic-v2-wb-line');
    expect(wrapper).toHaveStyle({ left: '100px', top: '200px' });
  });

  test('SVG dimensions track the line bounding box', () => {
    const { container } = render(
      <LineElement element={make({ startX: 0, startY: 0, endX: 80, endY: 60 })} />,
    );
    const svg = container.querySelector('svg');
    expect(svg!.getAttribute('width')).toBe('80');
    expect(svg!.getAttribute('height')).toBe('60');
  });

  test('SVG enforces a min axis of 24px so very short lines stay clickable', () => {
    const { container } = render(
      <LineElement element={make({ startX: 0, startY: 0, endX: 5, endY: 5 })} />,
    );
    const svg = container.querySelector('svg');
    expect(svg!.getAttribute('width')).toBe('24');
    expect(svg!.getAttribute('height')).toBe('24');
  });

  test('default color #333 + width 2 + solid style', () => {
    const { container } = render(<LineElement element={make()} />);
    const line = container.querySelector('line');
    expect(line!.getAttribute('stroke')).toBe('#333333');
    expect(line!.getAttribute('stroke-width')).toBe('2');
    expect(line!.getAttribute('stroke-dasharray')).toBeNull();
  });

  test('dashed style emits a stroke-dasharray', () => {
    const { container } = render(<LineElement element={make({ style: 'dashed', width: 4 })} />);
    const line = container.querySelector('line');
    const dash = line!.getAttribute('stroke-dasharray');
    expect(dash).toBeTruthy();
    // upstream formula for width<=8: `${w*5} ${w*2.5}` → "20 10"
    expect(dash).toBe('20 10');
  });

  test('end arrow marker emitted when points[1]===arrow', () => {
    const { container } = render(
      <LineElement element={make({ id: 'aL', points: ['', 'arrow'] })} />,
    );
    const markers = container.querySelectorAll('marker');
    expect(markers).toHaveLength(1);
    const line = container.querySelector('line');
    expect(line!.getAttribute('marker-end')).toContain('aL-end');
    expect(line!.getAttribute('marker-start')).toBeNull();
  });

  test('start arrow marker emitted when points[0]===arrow', () => {
    const { container } = render(
      <LineElement element={make({ id: 'aL', points: ['arrow', ''] })} />,
    );
    const markers = container.querySelectorAll('marker');
    expect(markers).toHaveLength(1);
    const line = container.querySelector('line');
    expect(line!.getAttribute('marker-start')).toContain('aL-start');
    expect(line!.getAttribute('marker-end')).toBeNull();
  });

  test('two-arrow connector', () => {
    const { container } = render(
      <LineElement element={make({ id: 'aL', points: ['arrow', 'arrow'] })} />,
    );
    expect(container.querySelectorAll('marker')).toHaveLength(2);
  });
});
