/**
 * Tests for src/components/maic-v2/whiteboard/TextElement.tsx
 * (MAIC-211.2).
 */
import { describe, test, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { TextElement } from '../TextElement';
import type { Action } from '../../../../lib/maic-v2/action-types';

type T = Extract<Action, { type: 'wb_draw_text' }>;

function make(overrides: Partial<T> = {}): T {
  return {
    id: 'a1',
    type: 'wb_draw_text',
    content: 'hello',
    x: 50,
    y: 100,
    ...overrides,
  };
}

describe('TextElement', () => {
  test('positions absolute at the action coords', () => {
    render(<TextElement element={make({ x: 73, y: 42 })} />);
    const el = screen.getByTestId('maic-v2-wb-text');
    expect(el).toHaveStyle({ left: '73px', top: '42px' });
  });

  test('exposes data-element-id (elementId wins over id)', () => {
    render(<TextElement element={make({ id: 'a1', elementId: 't1' })} />);
    expect(screen.getByTestId('maic-v2-wb-text')).toHaveAttribute('data-element-id', 't1');
  });

  test('falls back to id when elementId absent', () => {
    render(<TextElement element={make({ id: 'a1' })} />);
    expect(screen.getByTestId('maic-v2-wb-text')).toHaveAttribute('data-element-id', 'a1');
  });

  test('wraps plain text content in a <p> with fontSize', () => {
    render(<TextElement element={make({ content: 'plain text', fontSize: 24 })} />);
    const el = screen.getByTestId('maic-v2-wb-text');
    expect(el.innerHTML).toContain('font-size:24px');
    expect(el.innerHTML).toContain('plain text');
  });

  test('passes through HTML content unchanged when leading <', () => {
    render(<TextElement element={make({ content: '<strong>bold</strong>' })} />);
    const el = screen.getByTestId('maic-v2-wb-text');
    expect(el.innerHTML).toContain('<strong>bold</strong>');
  });

  test('uses default width 400 + minHeight 100 + color #333 when not specified', () => {
    render(<TextElement element={make()} />);
    const el = screen.getByTestId('maic-v2-wb-text');
    const style = el.getAttribute('style') ?? '';
    expect(style).toContain('width: 400px');
    expect(style).toContain('min-height: 100px');
    expect(style).toContain('color: #333333');
  });

  test('honors caller-provided width/height/color', () => {
    render(<TextElement element={make({ width: 250, height: 80, color: '#ff0000' })} />);
    const el = screen.getByTestId('maic-v2-wb-text');
    const style = el.getAttribute('style') ?? '';
    expect(style).toContain('width: 250px');
    expect(style).toContain('min-height: 80px');
    expect(style).toContain('color: #ff0000');
  });
});
