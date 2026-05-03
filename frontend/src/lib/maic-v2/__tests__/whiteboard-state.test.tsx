/**
 * Tests for src/lib/maic-v2/whiteboard-state.tsx (MAIC-210.2).
 *
 * Two layers:
 *   1. Pure reducer — no React, drives every transition by hand.
 *   2. Provider + hooks — confirms identity stability + missing-context
 *      throws so the ActionEngine fails loudly if mounted outside the
 *      Stage's WhiteboardProvider.
 */
import { describe, test, expect } from 'vitest';
import { renderHook, act } from '@testing-library/react';

import {
  INITIAL_WHITEBOARD_STATE,
  WhiteboardProvider,
  getElementKey,
  useWhiteboardController,
  useWhiteboardState,
  whiteboardReducer,
  type WhiteboardElement,
  type WhiteboardState,
} from '../whiteboard-state';


// ── Helpers ────────────────────────────────────────────────────────


function textElement(
  id: string,
  overrides: Partial<Extract<WhiteboardElement, { type: 'wb_draw_text' }>> = {},
): WhiteboardElement {
  return {
    id,
    type: 'wb_draw_text',
    content: 'hi',
    x: 10,
    y: 10,
    ...overrides,
  };
}


// ── Reducer ────────────────────────────────────────────────────────


describe('whiteboardReducer — set_open / set_clearing', () => {
  test('set_open=true flips isOpen', () => {
    const next = whiteboardReducer(INITIAL_WHITEBOARD_STATE, { type: 'set_open', open: true });
    expect(next.isOpen).toBe(true);
  });

  test('set_open with same value returns same reference (identity stable)', () => {
    const next = whiteboardReducer(INITIAL_WHITEBOARD_STATE, { type: 'set_open', open: false });
    expect(next).toBe(INITIAL_WHITEBOARD_STATE);
  });

  test('set_clearing toggles isClearing', () => {
    const next = whiteboardReducer(INITIAL_WHITEBOARD_STATE, { type: 'set_clearing', clearing: true });
    expect(next.isClearing).toBe(true);
  });
});


describe('whiteboardReducer — add_element', () => {
  test('appends a new element', () => {
    const el = textElement('a1');
    const next = whiteboardReducer(INITIAL_WHITEBOARD_STATE, { type: 'add_element', element: el });
    expect(next.elements).toHaveLength(1);
    expect(next.elements[0]).toEqual(el);
  });

  test('upserts by key when re-emitted with same id', () => {
    const v1 = textElement('a1', { content: 'first' });
    const v2 = textElement('a1', { content: 'second' });
    let s: WhiteboardState = INITIAL_WHITEBOARD_STATE;
    s = whiteboardReducer(s, { type: 'add_element', element: v1 });
    s = whiteboardReducer(s, { type: 'add_element', element: v2 });
    expect(s.elements).toHaveLength(1);
    expect((s.elements[0] as { content: string }).content).toBe('second');
  });

  test('keys by elementId when present, falls back to id otherwise', () => {
    const a = textElement('action-a', { elementId: 't1' });
    const b = textElement('action-b', { elementId: 't1' });  // same elementId, different action id
    let s = INITIAL_WHITEBOARD_STATE;
    s = whiteboardReducer(s, { type: 'add_element', element: a });
    s = whiteboardReducer(s, { type: 'add_element', element: b });
    expect(s.elements).toHaveLength(1);  // upserted
    expect(getElementKey(s.elements[0])).toBe('t1');
  });
});


describe('whiteboardReducer — update_element', () => {
  test('applies patch to matching element', () => {
    const el = textElement('a1', { content: 'before' });
    let s = INITIAL_WHITEBOARD_STATE;
    s = whiteboardReducer(s, { type: 'add_element', element: el });
    s = whiteboardReducer(s, {
      type: 'update_element',
      key: 'a1',
      patch: { content: 'after' } as Partial<WhiteboardElement>,
    });
    expect((s.elements[0] as { content: string }).content).toBe('after');
  });

  test('no-op on missing key', () => {
    const next = whiteboardReducer(INITIAL_WHITEBOARD_STATE, {
      type: 'update_element',
      key: 'nope',
      patch: {},
    });
    expect(next).toBe(INITIAL_WHITEBOARD_STATE);
  });
});


describe('whiteboardReducer — delete_element', () => {
  test('removes by key', () => {
    let s = INITIAL_WHITEBOARD_STATE;
    s = whiteboardReducer(s, { type: 'add_element', element: textElement('a1') });
    s = whiteboardReducer(s, { type: 'add_element', element: textElement('a2') });
    s = whiteboardReducer(s, { type: 'delete_element', key: 'a1' });
    expect(s.elements).toHaveLength(1);
    expect(getElementKey(s.elements[0])).toBe('a2');
  });

  test('no-op on missing key (identity stable)', () => {
    const next = whiteboardReducer(INITIAL_WHITEBOARD_STATE, {
      type: 'delete_element',
      key: 'nope',
    });
    expect(next).toBe(INITIAL_WHITEBOARD_STATE);
  });
});


describe('whiteboardReducer — clear', () => {
  test('empties the elements array', () => {
    let s = INITIAL_WHITEBOARD_STATE;
    s = whiteboardReducer(s, { type: 'add_element', element: textElement('a1') });
    s = whiteboardReducer(s, { type: 'add_element', element: textElement('a2') });
    s = whiteboardReducer(s, { type: 'clear' });
    expect(s.elements).toEqual([]);
  });

  test('preserves isOpen / isClearing', () => {
    let s: WhiteboardState = { ...INITIAL_WHITEBOARD_STATE, isOpen: true, isClearing: true };
    s = whiteboardReducer(s, { type: 'add_element', element: textElement('a1') });
    s = whiteboardReducer(s, { type: 'clear' });
    expect(s.isOpen).toBe(true);
    expect(s.isClearing).toBe(true);
  });

  test('no-op on already-empty array', () => {
    const next = whiteboardReducer(INITIAL_WHITEBOARD_STATE, { type: 'clear' });
    expect(next).toBe(INITIAL_WHITEBOARD_STATE);
  });
});


// ── Provider + hooks ───────────────────────────────────────────────


describe('WhiteboardProvider + hooks', () => {
  test('useWhiteboardState returns initial state', () => {
    const { result } = renderHook(() => useWhiteboardState(), {
      wrapper: ({ children }) => <WhiteboardProvider>{children}</WhiteboardProvider>,
    });
    expect(result.current).toEqual(INITIAL_WHITEBOARD_STATE);
  });

  test('controller mutations update state', () => {
    const { result } = renderHook(
      () => ({ s: useWhiteboardState(), c: useWhiteboardController() }),
      { wrapper: ({ children }) => <WhiteboardProvider>{children}</WhiteboardProvider> },
    );
    act(() => result.current.c.setOpen(true));
    expect(result.current.s.isOpen).toBe(true);

    act(() => result.current.c.addElement(textElement('a1')));
    expect(result.current.s.elements).toHaveLength(1);

    act(() => result.current.c.deleteElement('a1'));
    expect(result.current.s.elements).toHaveLength(0);
  });

  test('controller identity is stable across renders', () => {
    const { result, rerender } = renderHook(() => useWhiteboardController(), {
      wrapper: ({ children }) => <WhiteboardProvider>{children}</WhiteboardProvider>,
    });
    const c1 = result.current;
    rerender();
    expect(result.current).toBe(c1);
  });

  test('useWhiteboardState throws when mounted outside provider', () => {
    const captured: unknown[] = [];
    const original = console.error;
    console.error = (...args: unknown[]) => captured.push(args);
    try {
      expect(() => renderHook(() => useWhiteboardState())).toThrow(
        /WhiteboardProvider/,
      );
    } finally {
      console.error = original;
    }
  });

  test('useWhiteboardController throws when mounted outside provider', () => {
    const captured: unknown[] = [];
    const original = console.error;
    console.error = (...args: unknown[]) => captured.push(args);
    try {
      expect(() => renderHook(() => useWhiteboardController())).toThrow(
        /WhiteboardProvider/,
      );
    } finally {
      console.error = original;
    }
  });

  test('initialState prop seeds the reducer', () => {
    const seeded: WhiteboardState = {
      isOpen: true,
      isClearing: false,
      elements: [textElement('seed-1')],
    };
    const { result } = renderHook(() => useWhiteboardState(), {
      wrapper: ({ children }) => (
        <WhiteboardProvider initialState={seeded}>{children}</WhiteboardProvider>
      ),
    });
    expect(result.current).toEqual(seeded);
  });
});
