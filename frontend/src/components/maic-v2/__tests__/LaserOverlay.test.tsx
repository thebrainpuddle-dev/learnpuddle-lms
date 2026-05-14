/**
 * Tests for src/components/maic-v2/LaserOverlay.tsx (MAIC-216).
 *
 * Real DOM measurement; no mocks. The overlay queries
 * `[data-testid="maic-v2-whiteboard"]` for the surface and the target
 * by `[data-element-id]` — tests render a stub surface alongside.
 */
import { describe, test, expect, vi } from 'vitest';
import { render, screen, act, cleanup } from '@testing-library/react';

import { LaserOverlay } from '../LaserOverlay';


function MockSurface({
  children,
  w = 1000,
  h = 562,
}: {
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


describe('LaserOverlay', () => {
  test('renders dot + ring when target exists', () => {
    render(
      <MockSurface>
        <div data-element-id="t1" style={{ position: 'absolute' }}>x</div>
        <LaserOverlay targetId="t1" />
      </MockSurface>,
    );
    expect(screen.getByTestId('maic-v2-laser-overlay')).toBeInTheDocument();
    expect(screen.getByTestId('maic-v2-laser-dot')).toBeInTheDocument();
    expect(screen.getByTestId('maic-v2-laser-ring')).toBeInTheDocument();
  });

  test('exposes data-target-id on the wrapper', () => {
    render(
      <MockSurface>
        <div data-element-id="t1" style={{ position: 'absolute' }}>x</div>
        <LaserOverlay targetId="t1" />
      </MockSurface>,
    );
    expect(screen.getByTestId('maic-v2-laser-overlay')).toHaveAttribute(
      'data-target-id',
      't1',
    );
  });

  test('falls back to surface center when target is missing', () => {
    render(
      <MockSurface>
        <LaserOverlay targetId="missing" />
      </MockSurface>,
    );
    // Race-safe path renders without crash.
    expect(screen.getByTestId('maic-v2-laser-dot')).toBeInTheDocument();
  });

  test('returns null when surface element is missing', () => {
    const { container } = render(<LaserOverlay targetId="t1" />);
    expect(container.firstChild).toBeNull();
  });

  test('honors color prop (default red, custom color flows through)', () => {
    render(
      <MockSurface>
        <div data-element-id="t2" style={{ position: 'absolute' }}>x</div>
        <LaserOverlay targetId="t2" color="#00ff88" />
      </MockSurface>,
    );
    const ring = screen.getByTestId('maic-v2-laser-ring');
    const ringStyle = ring.getAttribute('style') ?? '';
    expect(ringStyle).toContain('#00ff88');
  });

  test('default color is the upstream red #ff3b30', () => {
    render(
      <MockSurface>
        <div data-element-id="t3" style={{ position: 'absolute' }}>x</div>
        <LaserOverlay targetId="t3" />
      </MockSurface>,
    );
    const ring = screen.getByTestId('maic-v2-laser-ring');
    expect(ring.getAttribute('style') ?? '').toContain('#ff3b30');
  });

  test('dot has CSS transition for fly-in animation', () => {
    render(
      <MockSurface>
        <div data-element-id="t4" style={{ position: 'absolute' }}>x</div>
        <LaserOverlay targetId="t4" />
      </MockSurface>,
    );
    const dot = screen.getByTestId('maic-v2-laser-dot');
    const style = dot.getAttribute('style') ?? '';
    expect(style).toContain('500ms');
    expect(style).toContain('cubic-bezier');
    expect(style).toContain('opacity');
  });

  test('ring uses the maic-v2-laser-pulse keyframe animation', () => {
    render(
      <MockSurface>
        <div data-element-id="t5" style={{ position: 'absolute' }}>x</div>
        <LaserOverlay targetId="t5" />
      </MockSurface>,
    );
    const ring = screen.getByTestId('maic-v2-laser-ring');
    expect(ring.getAttribute('style') ?? '').toContain('maic-v2-laser-pulse');
  });

  test('inline @keyframes maic-v2-laser-pulse style block is emitted', () => {
    render(
      <MockSurface>
        <div data-element-id="t6" style={{ position: 'absolute' }}>x</div>
        <LaserOverlay targetId="t6" />
      </MockSurface>,
    );
    // The component emits an inline <style> with @keyframes
    // maic-v2-laser-pulse — required for the ring's pulse animation.
    const styleBlocks = Array.from(document.querySelectorAll('style'))
      .map((el) => el.textContent ?? '')
      .join('\n');
    expect(styleBlocks).toContain('maic-v2-laser-pulse');
    expect(styleBlocks).toContain('@keyframes');
  });

  test('auto-clears via onClear at AUTO_CLEAR_MS=5000', () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    const onClear = vi.fn();
    render(
      <MockSurface>
        <div data-element-id="t7" style={{ position: 'absolute' }}>x</div>
        <LaserOverlay targetId="t7" onClear={onClear} />
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
        <div data-element-id="t8" style={{ position: 'absolute' }}>x</div>
        <LaserOverlay targetId="t8" onClear={onClear} />
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
