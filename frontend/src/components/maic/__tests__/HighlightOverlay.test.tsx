/**
 * Chunk 5 — HighlightOverlay ResizeObserver wiring.
 *
 * Pins the contract that an element-driven highlight stays aligned when
 * the target element resizes mid-playback (image lazy-load, font swap,
 * slide animation). Previously the overlay only re-measured on window
 * resize / scroll, so the cutout could drift after layout shifts that
 * didn't propagate to the viewport.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render } from '@testing-library/react';
import { HighlightOverlay } from '../HighlightOverlay';

type Observer = {
  callback: ResizeObserverCallback;
  observed: Element[];
  disconnect: ReturnType<typeof vi.fn>;
};

let activeObservers: Observer[] = [];

class MockResizeObserver implements ResizeObserver {
  callback: ResizeObserverCallback;
  observed: Element[] = [];
  disconnect = vi.fn();
  constructor(cb: ResizeObserverCallback) {
    this.callback = cb;
    activeObservers.push({
      callback: cb,
      observed: this.observed,
      disconnect: this.disconnect,
    });
  }
  observe(el: Element) {
    this.observed.push(el);
  }
  unobserve() {}
}

beforeEach(() => {
  activeObservers = [];
  global.ResizeObserver = MockResizeObserver as unknown as typeof ResizeObserver;
});

afterEach(() => {
  // Wipe DOM so the next test's getElementById returns the freshly-
  // created element, not a stale one left behind by a previous test.
  document.body.innerHTML = '';
});

function placeTargetElement(rect: Partial<DOMRect>): HTMLElement {
  const el = document.createElement('div');
  el.id = 'target-el';
  el.getBoundingClientRect = () =>
    ({
      x: rect.x ?? 100,
      y: rect.y ?? 100,
      left: rect.left ?? rect.x ?? 100,
      top: rect.top ?? rect.y ?? 100,
      width: rect.width ?? 200,
      height: rect.height ?? 150,
      right: (rect.left ?? rect.x ?? 100) + (rect.width ?? 200),
      bottom: (rect.top ?? rect.y ?? 100) + (rect.height ?? 150),
      toJSON: () => ({}),
    }) as DOMRect;
  document.body.appendChild(el);
  return el;
}

describe('HighlightOverlay — Chunk 5 ResizeObserver wiring', () => {
  it('observes the target element via ResizeObserver when active', () => {
    const el = placeTargetElement({ x: 100, y: 100, width: 200, height: 150 });

    render(<HighlightOverlay elementId="target-el" active duration={0} />);

    expect(activeObservers).toHaveLength(1);
    expect(activeObservers[0].observed).toContain(el);
  });

  it('does not create an observer when inactive', () => {
    placeTargetElement({});
    render(<HighlightOverlay elementId="target-el" active={false} duration={0} />);
    expect(activeObservers).toHaveLength(0);
  });

  it('disconnects the observer on unmount', () => {
    placeTargetElement({});
    const { unmount } = render(
      <HighlightOverlay elementId="target-el" active duration={0} />,
    );
    expect(activeObservers).toHaveLength(1);
    const disconnect = activeObservers[0].disconnect;
    unmount();
    expect(disconnect).toHaveBeenCalled();
  });

  it('skips observer when elementId is missing from the DOM', () => {
    // No element created — observer must not attach to anything.
    render(<HighlightOverlay elementId="ghost" active duration={0} />);
    expect(activeObservers).toHaveLength(0);
  });
});
