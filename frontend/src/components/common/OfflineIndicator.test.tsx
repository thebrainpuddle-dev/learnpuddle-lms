// components/common/OfflineIndicator.test.tsx
/**
 * Unit tests for the OfflineIndicator (offline banner) component.
 *
 * Key behaviours tested:
 *  1. Banner is hidden when online.
 *  2. Banner appears when the 'offline' window event fires.
 *  3. Banner disappears when the 'online' window event fires.
 *  4. Dismiss button hides the banner while still offline.
 *  5. After dismiss + back-online + offline again, the banner reappears
 *     (dismiss is per-episode, not permanent).
 */

import React from 'react';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { OfflineIndicator } from './OfflineIndicator';

// Helper: simulate navigator.onLine value.
// The component reads this on mount to set initial state.
function mockOnlineStatus(online: boolean) {
  Object.defineProperty(navigator, 'onLine', {
    configurable: true,
    get: () => online,
  });
}

describe('OfflineIndicator', () => {
  beforeEach(() => {
    // Start online by default.
    mockOnlineStatus(true);
  });

  it('renders nothing when online', () => {
    mockOnlineStatus(true);
    render(<OfflineIndicator />);
    expect(screen.queryByTestId('offline-banner')).not.toBeInTheDocument();
  });

  it('renders the banner when already offline on mount', () => {
    mockOnlineStatus(false);
    render(<OfflineIndicator />);
    expect(screen.getByTestId('offline-banner')).toBeInTheDocument();
    expect(screen.getByText(/you're offline/i)).toBeInTheDocument();
  });

  it('shows banner when the "offline" window event fires', () => {
    mockOnlineStatus(true);
    render(<OfflineIndicator />);
    expect(screen.queryByTestId('offline-banner')).not.toBeInTheDocument();

    act(() => {
      fireEvent(window, new Event('offline'));
    });

    expect(screen.getByTestId('offline-banner')).toBeInTheDocument();
  });

  it('hides banner when the "online" window event fires', () => {
    mockOnlineStatus(false);
    render(<OfflineIndicator />);
    expect(screen.getByTestId('offline-banner')).toBeInTheDocument();

    act(() => {
      fireEvent(window, new Event('online'));
    });

    expect(screen.queryByTestId('offline-banner')).not.toBeInTheDocument();
  });

  it('dismiss button hides the banner while offline', () => {
    mockOnlineStatus(false);
    render(<OfflineIndicator />);

    const dismissBtn = screen.getByRole('button', { name: /dismiss offline/i });
    act(() => {
      fireEvent.click(dismissBtn);
    });

    expect(screen.queryByTestId('offline-banner')).not.toBeInTheDocument();
  });

  it('banner reappears after dismiss → back-online → offline again (per-episode dismiss)', () => {
    mockOnlineStatus(false);
    render(<OfflineIndicator />);

    // Dismiss during offline episode 1.
    const dismissBtn = screen.getByRole('button', { name: /dismiss offline/i });
    act(() => {
      fireEvent.click(dismissBtn);
    });
    expect(screen.queryByTestId('offline-banner')).not.toBeInTheDocument();

    // Go back online — dismiss flag should reset.
    act(() => {
      fireEvent(window, new Event('online'));
    });
    expect(screen.queryByTestId('offline-banner')).not.toBeInTheDocument();

    // Go offline again (episode 2) — banner should reappear.
    act(() => {
      fireEvent(window, new Event('offline'));
    });
    expect(screen.getByTestId('offline-banner')).toBeInTheDocument();
  });

  it('has correct accessibility attributes', () => {
    mockOnlineStatus(false);
    render(<OfflineIndicator />);

    const banner = screen.getByTestId('offline-banner');
    expect(banner).toHaveAttribute('role', 'status');
    expect(banner).toHaveAttribute('aria-live', 'polite');
  });

  it('removes event listeners on unmount', () => {
    const removeSpy = vi.spyOn(window, 'removeEventListener');
    mockOnlineStatus(true);
    const { unmount } = render(<OfflineIndicator />);
    unmount();
    expect(removeSpy).toHaveBeenCalledWith('online', expect.any(Function));
    expect(removeSpy).toHaveBeenCalledWith('offline', expect.any(Function));
    removeSpy.mockRestore();
  });

  // ── visualViewport / iOS keyboard tests (F5) ───────────────────────────

  it('uses inline bottom style when visualViewport reports keyboard open', () => {
    mockOnlineStatus(false);

    // Simulate a viewport where the keyboard consumes 300 px of the 800 px
    // window height — the visual viewport height is therefore 500 px.
    const mockVV = {
      height: 500,
      offsetTop: 0,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    };
    Object.defineProperty(window, 'innerHeight', { configurable: true, get: () => 800 });
    Object.defineProperty(window, 'visualViewport', { configurable: true, value: mockVV });

    render(<OfflineIndicator />);

    const banner = screen.getByTestId('offline-banner');
    // Expected bottom = keyboardHeight(300) + 16 = 316 px
    expect(banner).toHaveStyle({ bottom: '316px' });
    // Should NOT have the static bottom-4 Tailwind class when viewport API is present
    expect(banner.className).not.toContain('bottom-4');

    // Restore
    Object.defineProperty(window, 'visualViewport', { configurable: true, value: undefined });
  });

  it('falls back to static bottom-4 class when visualViewport is undefined', () => {
    mockOnlineStatus(false);

    // Ensure visualViewport is not available
    Object.defineProperty(window, 'visualViewport', { configurable: true, value: undefined });

    render(<OfflineIndicator />);

    const banner = screen.getByTestId('offline-banner');
    expect(banner.className).toContain('bottom-4');
    // No inline bottom style should be set
    expect(banner.style.bottom).toBe('');
  });

  // ── SPRINT-2-BATCH-4-F5 — visualViewport resize-listener path ────────────
  //
  // The component wires `vv.addEventListener('resize', onViewportResize)` in a
  // useEffect.  When the keyboard opens AFTER the banner has rendered, the
  // resize event fires and the bottom offset should recompute dynamically.
  // The F5 test above only covers the initial-mount value; this test covers
  // the mid-render update path.

  it('updates inline bottom style dynamically when visualViewport fires a resize event', () => {
    mockOnlineStatus(false);

    // Initial state: keyboard is NOT open — viewport equals full window height.
    let vvHeight = 800;
    let vvOffsetTop = 0;
    Object.defineProperty(window, 'innerHeight', { configurable: true, get: () => 800 });

    // Use a real EventTarget so that dispatchEvent propagates to registered listeners.
    // Define height/offsetTop as proper getters (not copies) so that mutations to
    // the closure variables are reflected when the component reads them after resize.
    const vvTarget = new EventTarget();
    Object.defineProperty(vvTarget, 'height', { configurable: true, get: () => vvHeight });
    Object.defineProperty(vvTarget, 'offsetTop', { configurable: true, get: () => vvOffsetTop });
    Object.defineProperty(window, 'visualViewport', { configurable: true, value: vvTarget });

    render(<OfflineIndicator />);

    const banner = screen.getByTestId('offline-banner');

    // On initial mount: keyboard is not open — keyboardHeight = 0, bottom = 16px.
    expect(banner).toHaveStyle({ bottom: '16px' });

    // Simulate keyboard opening: visual viewport shrinks to 500px, offsetTop = 0.
    act(() => {
      vvHeight = 500;
      vvOffsetTop = 0;
      vvTarget.dispatchEvent(new Event('resize'));
    });

    // Expected: keyboardHeight = max(0, 800 - (0 + 500)) = 300; bottom = 300 + 16 = 316px.
    expect(banner).toHaveStyle({ bottom: '316px' });

    // Simulate keyboard closing again — viewport restores.
    act(() => {
      vvHeight = 800;
      vvOffsetTop = 0;
      vvTarget.dispatchEvent(new Event('resize'));
    });

    expect(banner).toHaveStyle({ bottom: '16px' });

    // Restore
    Object.defineProperty(window, 'visualViewport', { configurable: true, value: undefined });
  });
});
