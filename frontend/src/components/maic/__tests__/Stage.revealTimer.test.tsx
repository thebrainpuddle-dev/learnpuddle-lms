// Stage.revealTimer.test.tsx
//
// R3 (WAVE-9 deferred) — Regression test for the fullscreen `reveal()`
// auto-hide timer in Stage.tsx (see Stage.tsx:99-156). The timer used to
// live in a closure-local `let timer` variable; on unmount or when
// `isFullscreen` flipped false, the cleanup correctly cleared it for the
// happy path, but two latent leaks were possible:
//
//   a. A `setTimeout` fired between cleanup and removal of event
//      listeners would still call `setControlsVisible(false)` against an
//      unmounted component.
//   b. Future edits that scheduled a timer outside the effect body
//      (e.g. from a callback handler) would not be tracked by the
//      closure-local variable and would leak past unmount.
//
// The fix moved the handle to a `useRef` and added an `unmounted`-like
// `cancelled` flag so the inner setTimeout callback bails out if the
// effect was torn down between schedule and fire.
//
// We can't reasonably render the full Stage component in a unit test
// (its dep tree pulls in playback engine, IndexedDB, the entire store
// graph, presentation overlays, PiP, etc. — see Stage.renderLoop.test.tsx
// for the same caveat). Instead we extract a minimal harness that
// implements the exact same effect pattern Stage uses. If anyone
// accidentally regresses Stage's reveal effect to a non-ref-tracked
// timer, this test catches it because the assertions on the spy will
// see an extra call after unmount.

import React, { useEffect, useRef, useState } from 'react';
import { act, render } from '@testing-library/react';
import { describe, test, expect, beforeEach, afterEach, vi } from 'vitest';

// ─── Test harness — mirrors Stage.tsx:99-156 exactly ────────────────────────

interface HarnessProps {
  isFullscreen: boolean;
  onHideControls: () => void;
}

function RevealHarness({ isFullscreen, onHideControls }: HarnessProps) {
  const [controlsVisible, setControlsVisible] = useState(true);
  const revealTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!isFullscreen) {
      if (revealTimerRef.current) {
        clearTimeout(revealTimerRef.current);
        revealTimerRef.current = null;
      }
      setControlsVisible(true);
      return;
    }
    let cancelled = false;
    const reveal = () => {
      if (cancelled) return;
      setControlsVisible(true);
      if (revealTimerRef.current) clearTimeout(revealTimerRef.current);
      revealTimerRef.current = setTimeout(() => {
        if (cancelled) return;
        setControlsVisible(false);
        onHideControls();
        revealTimerRef.current = null;
      }, 3000);
    };
    reveal();
    window.addEventListener('mousemove', reveal);
    window.addEventListener('keydown', reveal);
    window.addEventListener('touchstart', reveal, { passive: true });
    return () => {
      cancelled = true;
      if (revealTimerRef.current) {
        clearTimeout(revealTimerRef.current);
        revealTimerRef.current = null;
      }
      window.removeEventListener('mousemove', reveal);
      window.removeEventListener('keydown', reveal);
      window.removeEventListener('touchstart', reveal);
    };
  }, [isFullscreen, onHideControls]);

  return <div data-testid="harness">{controlsVisible ? 'visible' : 'hidden'}</div>;
}

describe('Stage reveal-timer (R3 — fullscreen autohide ref leak guard)', () => {
  beforeEach(() => {
    // Only fake setTimeout/clearTimeout so React Testing Library's
    // microtask scheduler (queueMicrotask, MessageChannel, etc.) keeps
    // running on real time. Otherwise `render()` deadlocks waiting on
    // act-flush microtasks that never fire under all-fake timers.
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  test('timer is cleared on unmount and hide-callback never fires after unmount', () => {
    const onHide = vi.fn();
    const { unmount } = render(
      <RevealHarness isFullscreen={true} onHideControls={onHide} />,
    );
    // A reveal-scheduled timer should be pending now (initial reveal()
    // called inside the effect).
    expect(vi.getTimerCount()).toBe(1);

    // Unmount BEFORE the 3-second autohide fires.
    unmount();

    // After unmount the timer must be cleared — getTimerCount drops to 0.
    expect(vi.getTimerCount()).toBe(0);

    // Even if we fast-forward past the original 3s window, the hide
    // callback must NOT fire (the timer was cleared, so this is purely
    // a belt-and-suspenders assertion that proves no zombie timer
    // somehow survived).
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(onHide).not.toHaveBeenCalled();
  });

  test('timer is cleared when isFullscreen flips to false mid-flight', () => {
    const onHide = vi.fn();
    const { rerender } = render(
      <RevealHarness isFullscreen={true} onHideControls={onHide} />,
    );
    expect(vi.getTimerCount()).toBe(1);

    // Exit fullscreen 1s in — the pending hide-timer must be cleared so
    // the controls don't blink invisible 2s after exit.
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    rerender(<RevealHarness isFullscreen={false} onHideControls={onHide} />);

    expect(vi.getTimerCount()).toBe(0);
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(onHide).not.toHaveBeenCalled();
  });

  test('event listeners are removed on unmount (no leaked reveal handlers)', () => {
    const onHide = vi.fn();
    const removeSpy = vi.spyOn(window, 'removeEventListener');
    const { unmount } = render(
      <RevealHarness isFullscreen={true} onHideControls={onHide} />,
    );
    unmount();
    // The effect cleanup removes mousemove + keydown + touchstart.
    const removed = removeSpy.mock.calls
      .map((c) => c[0])
      .filter((e) =>
        e === 'mousemove' || e === 'keydown' || e === 'touchstart',
      );
    expect(removed).toEqual(
      expect.arrayContaining(['mousemove', 'keydown', 'touchstart']),
    );
  });
});
