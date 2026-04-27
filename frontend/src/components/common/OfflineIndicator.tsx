// components/common/OfflineIndicator.tsx
/**
 * Offline banner component.
 *
 * Appears at the bottom of the viewport when the browser loses connectivity.
 * The banner is dismissible per offline episode: once dismissed it stays
 * hidden for the current offline period, but reappears automatically the
 * next time connectivity is lost (i.e. dismiss resets when back online).
 *
 * Positioned at the bottom to avoid overlapping the MAIC Stage chrome
 * and other fixed top-of-page headers.
 *
 * On iOS (and other platforms that support the visualViewport API), the
 * banner shifts upward when the on-screen keyboard is open so it is not
 * obscured by the keyboard surface.  Falls back to a static `bottom: 1rem`
 * (bottom-4) on browsers that do not expose window.visualViewport (e.g.
 * older Firefox).
 */

import React from 'react';
import { useEffect, useState } from 'react';

interface OfflineIndicatorProps {
  className?: string;
}

/** Returns true if the visualViewport API is available. */
function hasVisualViewport(): boolean {
  return typeof window !== 'undefined' && 'visualViewport' in window && window.visualViewport != null;
}

/**
 * Compute the bottom offset (in px) the banner should sit above the bottom
 * of the visual viewport.  When the software keyboard pushes the visual
 * viewport up, this keeps the banner visible above the keyboard.
 *
 * Returns null when the API is unavailable — callers should fall back to
 * the static Tailwind `bottom-4` class in that case.
 */
function getVisualViewportBottom(): number | null {
  if (!hasVisualViewport()) return null;
  const vv = window.visualViewport!;
  // The visual viewport may be smaller than the layout viewport when the
  // keyboard is open.  The gap at the bottom of the screen (keyboard area)
  // equals: window.innerHeight - (vv.offsetTop + vv.height).
  const keyboardHeight = Math.max(0, window.innerHeight - (vv.offsetTop + vv.height));
  // Place the banner 16 px above the top of the keyboard (or viewport edge).
  return keyboardHeight + 16;
}

export const OfflineIndicator: React.FC<OfflineIndicatorProps> = ({ className = '' }) => {
  const [isOnline, setIsOnline] = useState(
    typeof navigator !== 'undefined' ? navigator.onLine : true,
  );
  // dismissedEpisode tracks whether the user dismissed the banner during the
  // *current* offline period. It resets to false whenever connectivity returns.
  const [dismissedEpisode, setDismissedEpisode] = useState(false);

  // bottomOffset is null when visualViewport is unavailable (static bottom-4).
  const [bottomOffset, setBottomOffset] = useState<number | null>(() => getVisualViewportBottom());

  useEffect(() => {
    const onOnline = () => {
      setIsOnline(true);
      // Reset dismiss state so the banner will show again on next disconnect.
      setDismissedEpisode(false);
    };
    const onOffline = () => setIsOnline(false);

    window.addEventListener('online', onOnline);
    window.addEventListener('offline', onOffline);
    return () => {
      window.removeEventListener('online', onOnline);
      window.removeEventListener('offline', onOffline);
    };
  }, []);

  useEffect(() => {
    if (!hasVisualViewport()) return;

    const vv = window.visualViewport!;
    const onViewportResize = () => {
      setBottomOffset(getVisualViewportBottom());
    };

    vv.addEventListener('resize', onViewportResize);
    return () => {
      vv.removeEventListener('resize', onViewportResize);
    };
  }, []);

  // Hidden when online or when the user dismissed this offline episode.
  if (isOnline || dismissedEpisode) {
    return null;
  }

  // When visualViewport is available use an inline style for the dynamic
  // bottom offset; otherwise fall back to the Tailwind `bottom-4` class.
  const positionStyle = bottomOffset !== null ? { bottom: `${bottomOffset}px` } : undefined;
  const positionClass = bottomOffset === null ? 'bottom-4' : '';

  return (
    <div
      data-testid="offline-banner"
      className={`fixed ${positionClass} left-1/2 -translate-x-1/2 w-max max-w-[calc(100vw-2rem)] bg-neutral-800 text-neutral-100 py-2.5 px-4 rounded-lg shadow-lg text-sm font-medium z-50 flex items-center gap-3 ${className}`}
      style={positionStyle}
      role="status"
      aria-live="polite"
    >
      {/* Wi-Fi off icon */}
      <svg
        className="w-4 h-4 flex-shrink-0 text-amber-400"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        aria-hidden="true"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M18.364 5.636a9 9 0 010 12.728m0 0l-2.829-2.829m2.829 2.829L21 21M15.536 8.464a5 5 0 010 7.072m0 0l-2.829-2.829m-4.243 2.829a4.978 4.978 0 01-1.414-2.83m-1.414 5.658a9 9 0 01-2.167-9.238m7.824 2.167a1 1 0 111.414 1.414m-1.414-1.414L3 3"
        />
      </svg>

      <span>You&apos;re offline. Some features may be unavailable.</span>

      {/* Dismiss button */}
      <button
        type="button"
        onClick={() => setDismissedEpisode(true)}
        aria-label="Dismiss offline notification"
        className="flex-shrink-0 ml-1 rounded text-neutral-400 hover:text-neutral-100 focus:outline-none focus:ring-2 focus:ring-neutral-400 transition-colors"
      >
        <svg
          className="w-4 h-4"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          aria-hidden="true"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>
  );
};

export default OfflineIndicator;
