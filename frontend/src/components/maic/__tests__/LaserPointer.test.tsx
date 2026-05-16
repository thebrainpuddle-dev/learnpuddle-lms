/**
 * Chunk 5 — LaserPointer mode disambiguation + ResizeObserver wiring.
 *
 * Pins two contracts:
 *   1. Agent-pinned mode (`targetElementId` set) ignores mouse events.
 *      Previously the mouse listener was attached unconditionally and any
 *      mouse-move on the page yanked the dot away from the element-pinned
 *      position — a race the agent's intent always lost.
 *   2. Agent-pinned mode observes the target element via ResizeObserver so
 *      the dot follows lazy-loaded image growth, font swaps, slide
 *      transitions, and fullscreen geometry changes.
 *
 * Manual mouse-follow mode (no `targetElementId`) still attaches the mouse
 * listener — this is the presentation tool and should be unaffected.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render } from '@testing-library/react';
import { LaserPointer } from '../LaserPointer';

let activeObservers: { observed: Element[]; disconnect: ReturnType<typeof vi.fn> }[] = [];

class MockResizeObserver implements ResizeObserver {
  observed: Element[] = [];
  disconnect = vi.fn();
  constructor(_cb: ResizeObserverCallback) {
    activeObservers.push({ observed: this.observed, disconnect: this.disconnect });
  }
  observe(el: Element) {
    this.observed.push(el);
  }
  unobserve() {}
}

let mouseMoveListeners: number = 0;
const realAdd = window.addEventListener;
const realRemove = window.removeEventListener;

beforeEach(() => {
  activeObservers = [];
  mouseMoveListeners = 0;
  global.ResizeObserver = MockResizeObserver as unknown as typeof ResizeObserver;
  window.addEventListener = vi.fn((event: string, handler: EventListenerOrEventListenerObject, opts?: AddEventListenerOptions | boolean) => {
    if (event === 'mousemove') mouseMoveListeners += 1;
    return realAdd.call(window, event, handler, opts);
  }) as typeof window.addEventListener;
  window.removeEventListener = vi.fn((event: string, handler: EventListenerOrEventListenerObject, opts?: AddEventListenerOptions | boolean) => {
    if (event === 'mousemove') mouseMoveListeners -= 1;
    return realRemove.call(window, event, handler, opts);
  }) as typeof window.removeEventListener;
});

afterEach(() => {
  window.addEventListener = realAdd;
  window.removeEventListener = realRemove;
  // Tests append elements into document.body; React Testing Library only
  // cleans up nodes it rendered, so wipe the body so the next test's
  // getElementById returns the freshly-created node, not a stale one.
  document.body.innerHTML = '';
});

function placeTargetElement(): HTMLElement {
  const el = document.createElement('div');
  el.id = 'laser-target';
  el.getBoundingClientRect = () =>
    ({
      x: 200,
      y: 200,
      left: 200,
      top: 200,
      width: 100,
      height: 100,
      right: 300,
      bottom: 300,
      toJSON: () => ({}),
    }) as DOMRect;
  document.body.appendChild(el);
  return el;
}

describe('LaserPointer — Chunk 5 mode disambiguation', () => {
  it('does NOT attach mousemove listener when targetElementId is set (agent-pinned mode)', () => {
    placeTargetElement();
    render(<LaserPointer active targetElementId="laser-target" />);
    expect(mouseMoveListeners).toBe(0);
  });

  it('observes the target element via ResizeObserver in agent-pinned mode', () => {
    const el = placeTargetElement();
    render(<LaserPointer active targetElementId="laser-target" />);
    expect(activeObservers).toHaveLength(1);
    expect(activeObservers[0].observed).toContain(el);
  });

  it('disconnects the observer on unmount', () => {
    placeTargetElement();
    const { unmount } = render(
      <LaserPointer active targetElementId="laser-target" />,
    );
    const disconnect = activeObservers[0].disconnect;
    unmount();
    expect(disconnect).toHaveBeenCalled();
  });

  it('attaches mousemove listener when targetElementId is null (manual mode)', () => {
    render(<LaserPointer active targetElementId={null} />);
    expect(mouseMoveListeners).toBe(1);
    expect(activeObservers).toHaveLength(0);
  });

  it('attaches no listeners and no observer when inactive', () => {
    placeTargetElement();
    render(<LaserPointer active={false} targetElementId="laser-target" />);
    expect(mouseMoveListeners).toBe(0);
    expect(activeObservers).toHaveLength(0);
  });

  it('switches modes cleanly when targetElementId changes from null to a value', () => {
    placeTargetElement();
    const { rerender } = render(
      <LaserPointer active targetElementId={null} />,
    );
    expect(mouseMoveListeners).toBe(1);
    expect(activeObservers).toHaveLength(0);

    rerender(<LaserPointer active targetElementId="laser-target" />);
    // mouse listener removed, observer attached
    expect(mouseMoveListeners).toBe(0);
    expect(activeObservers).toHaveLength(1);
  });
});
