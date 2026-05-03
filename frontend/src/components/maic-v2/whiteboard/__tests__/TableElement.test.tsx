/**
 * Tests for src/components/maic-v2/whiteboard/TableElement.tsx
 * (MAIC-211.2).
 */
import { describe, test, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { TableElement } from '../TableElement';
import type { Action } from '../../../../lib/maic-v2/action-types';

type T = Extract<Action, { type: 'wb_draw_table' }>;

function make(overrides: Partial<T> = {}): T {
  return {
    id: 'a1',
    type: 'wb_draw_table',
    x: 0,
    y: 0,
    width: 300,
    height: 100,
    data: [['A', 'B'], ['1', '2']],
    ...overrides,
  };
}

describe('TableElement', () => {
  test('renders one <td> per cell across all rows', () => {
    const { container } = render(
      <TableElement element={make({ data: [['A', 'B', 'C'], ['1', '2', '3']] })} />,
    );
    expect(container.querySelectorAll('td')).toHaveLength(6);
  });

  test('cell text content matches data', () => {
    const { container } = render(<TableElement element={make()} />);
    const tds = Array.from(container.querySelectorAll('td')).map((td) => td.textContent);
    expect(tds).toEqual(['A', 'B', '1', '2']);
  });

  test('positions absolute at action coords + sizes container', () => {
    render(<TableElement element={make({ x: 50, y: 60, width: 220, height: 80 })} />);
    const wrapper = screen.getByTestId('maic-v2-wb-table');
    expect(wrapper).toHaveStyle({
      left: '50px',
      top: '60px',
      width: '220px',
      height: '80px',
    });
  });

  test('default outline 1px solid #ccc when not specified', () => {
    const { container } = render(<TableElement element={make()} />);
    const td = container.querySelector('td');
    expect(td!.getAttribute('style')).toContain('1px solid');
  });

  test('honors caller-provided outline width/style/color', () => {
    const { container } = render(
      <TableElement
        element={make({ outline: { width: 2, style: 'dashed', color: '#ff0000' } })}
      />,
    );
    const td = container.querySelector('td');
    const style = td!.getAttribute('style') ?? '';
    expect(style).toContain('2px');
    expect(style).toContain('dashed');
    expect(style).toContain('#ff0000');
  });

  test('first row gets theme color background when theme.color provided', () => {
    const { container } = render(
      <TableElement
        element={make({
          theme: { color: '#1f77b4' },
          data: [['Header A', 'Header B'], ['1', '2']],
        })}
      />,
    );
    const firstRowCells = container.querySelectorAll('tr')[0].querySelectorAll('td');
    expect(firstRowCells[0].getAttribute('style')).toContain('#1f77b4');
    const secondRowCells = container.querySelectorAll('tr')[1].querySelectorAll('td');
    // Body row has no theme background
    expect(secondRowCells[0].getAttribute('style')).not.toContain('#1f77b4');
  });

  test('exposes data-element-id (elementId wins over id)', () => {
    render(<TableElement element={make({ id: 'a1', elementId: 't1' })} />);
    expect(screen.getByTestId('maic-v2-wb-table')).toHaveAttribute('data-element-id', 't1');
  });
});
