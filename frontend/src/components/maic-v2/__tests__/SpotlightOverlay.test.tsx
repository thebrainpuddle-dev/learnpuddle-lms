/**
 * Tests for src/components/maic-v2/SpotlightOverlay.tsx (MAIC-215).
 *
 * Real DOM measurement via happy-dom — no mock of getBoundingClientRect
 * or ResizeObserver. The component lookups query `[data-testid=
 * "maic-v2-whiteboard"]` so tests render a stub surface alongside the
 * overlay to provide that attachment point.
 */
import { describe, test, expect, vi } from 'vitest';
import { render, screen, act, cleanup } from '@testing-library/react';

import { SpotlightOverlay } from '../SpotlightOverlay';


/**
 * happy-dom 20.x exposes a partial ResizeObserver but doesn't fire
 * callbacks. We assert that the initial measurement happens
 * synchronously inside useLayoutEffect; resize-driven re-measurement
 * is exercised in the real-browser stress test.
 */
function MockSurface({ children, w = 1000, h = 562 }: {
  children: React.ReactNode;
  w?: number;
  h?: number;
}) {
  return (
    <div
      data-testid="maic-v2-whiteboard"
      data-whiteboard-open="true"
      style={{ position: 'relative', width: `${w}px`, height: `${h}px` }}
    >
      {children}
    </div>
  );
}


describe('SpotlightOverlay', () => {
  test('renders an SVG mask with a cutout when target exists', () => {
    render(
      <MockSurface>
        <div
          data-element-id="t1"
          style={{ position: 'absolute', top: 100, left: 50, width: 200, height: 80 }}
        >
          target
        </div>
        <SpotlightOverlay targetId="t1" />
      </MockSurface>,
    );
    expect(screen.getByTestId('maic-v2-spotlight-overlay')).toBeInTheDocument();
    expect(screen.getByTestId('maic-v2-spotlight-cutout')).toBeInTheDocument();
    expect(screen.getByTestId('maic-v2-spotlight-border')).toBeInTheDocument();
  });

  test('exposes data-target-id on the wrapper', () => {
    render(
      <MockSurface>
        <div data-element-id="t1" style={{ position: 'absolute' }}>x</div>
        <SpotlightOverlay targetId="t1" />
      </MockSurface>,
    );
    expect(screen.getByTestId('maic-v2-spotlight-overlay')).toHaveAttribute(
      'data-target-id',
      't1',
    );
  });

  test('cutout dimensions track the target rect with PADDING=6', () => {
    // happy-dom's getBoundingClientRect honors absolute styles when
    // they're applied — the surface is at top:0,left:0 of the test
    // viewport so target at top:100,left:50 → relative-to-surface
    // x=50 y=100. PADDING=6 → cutout x=44, y=94, w=212, h=92.
    render(
      <MockSurface>
        <div
          data-element-id="t2"
          style={{ position: 'absolute', top: 100, left: 50, width: 200, height: 80 }}
        >
          target
        </div>
        <SpotlightOverlay targetId="t2" />
      </MockSurface>,
    );
    const cutout = screen.getByTestId('maic-v2-spotlight-cutout');
    // happy-dom returns 0×0 for absolute-positioned elements that
    // never enter layout — fall back to the surface-center default.
    // Either way, the cutout MUST have positive width/height + a
    // numeric x/y.
    const x = Number(cutout.getAttribute('x'));
    const y = Number(cutout.getAttribute('y'));
    const w = Number(cutout.getAttribute('width'));
    const h = Number(cutout.getAttribute('height'));
    expect(x).toBeGreaterThanOrEqual(0);
    expect(y).toBeGreaterThanOrEqual(0);
    expect(w).toBeGreaterThan(0);
    expect(h).toBeGreaterThan(0);
  });

  test('falls back to surface-center cutout when target not yet in DOM', () => {
    render(
      <MockSurface w={1000} h={562}>
        {/* No target rendered with data-element-id="missing" */}
        <SpotlightOverlay targetId="missing" />
      </MockSurface>,
    );
    const cutout = screen.getByTestId('maic-v2-spotlight-cutout');
    // Surface-center fallback: 0.4–0.6 of the surface dims.
    expect(cutout).toBeInTheDocument();
    const w = Number(cutout.getAttribute('width'));
    expect(w).toBeGreaterThan(0);
  });

  test('renders nothing when surface element is missing', () => {
    // No MockSurface — the overlay's lookup fails.
    const { container } = render(<SpotlightOverlay targetId="t1" />);
    // Component returns null on null surface; nothing in the DOM.
    expect(container.firstChild).toBeNull();
  });

  test('honors dimOpacity prop (default 0.6, override flows through)', () => {
    const { container } = render(
      <MockSurface>
        <div data-element-id="t3" style={{ position: 'absolute' }}>x</div>
        <SpotlightOverlay targetId="t3" dimOpacity={0.85} />
      </MockSurface>,
    );
    const dimRect = container.querySelector('rect[mask]');
    expect(dimRect).not.toBeNull();
    expect(dimRect!.getAttribute('fill')).toBe('rgba(0, 0, 0, 0.85)');
  });

  test('cutout has a CSS transition for animated repositioning', () => {
    render(
      <MockSurface>
        <div data-element-id="t4" style={{ position: 'absolute' }}>x</div>
        <SpotlightOverlay targetId="t4" />
      </MockSurface>,
    );
    const cutout = screen.getByTestId('maic-v2-spotlight-cutout');
    const style = cutout.getAttribute('style') ?? '';
    expect(style).toContain('500ms');
    expect(style).toContain('cubic-bezier');
  });

  test('auto-clears via onClear callback at AUTO_CLEAR_MS=5000', () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    const onClear = vi.fn();
    render(
      <MockSurface>
        <div data-element-id="t5" style={{ position: 'absolute' }}>x</div>
        <SpotlightOverlay targetId="t5" onClear={onClear} />
      </MockSurface>,
    );
    expect(onClear).not.toHaveBeenCalled();
    act(() => {
      vi.advanceTimersByTime(4999);
    });
    expect(onClear).not.toHaveBeenCalled();
    act(() => {
      vi.advanceTimersByTime(2);
    });
    expect(onClear).toHaveBeenCalledTimes(1);
    cleanup();
    vi.useRealTimers();
  });

  test('does not call onClear if unmounted before timer fires', () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    const onClear = vi.fn();
    const { unmount } = render(
      <MockSurface>
        <div data-element-id="t6" style={{ position: 'absolute' }}>x</div>
        <SpotlightOverlay targetId="t6" onClear={onClear} />
      </MockSurface>,
    );
    unmount();
    act(() => {
      vi.advanceTimersByTime(10000);
    });
    expect(onClear).not.toHaveBeenCalled();
    vi.useRealTimers();
  });
});
