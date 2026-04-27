// src/lib/sprintFlags.ts
//
// Tiny localStorage-backed feature-flag helper used by Sprint 1's
// presence + rhythm improvements. Each new behavior is gated behind a
// key so the user can A/B compare during local testing without a
// rebuild.
//
// Keys are strings of the form `maic.sprint1.<feature>`. Default is
// "on" — set the key to the string `"off"` (from DevTools, or via
// `setSprintFlag`) to disable. Any other value is treated as on.
//
// This is intentionally NOT a zustand store — flags are rarely toggled
// and don't need to participate in React re-renders during normal use.
// The `useSprintFlag` hook subscribes to `storage` events so a
// DevTools edit triggers a re-render in the live session.

import { useEffect, useState } from 'react';

export const SPRINT1_FLAGS = {
  roundtableStrip: 'maic.sprint1.roundtableStrip',
  typewriter: 'maic.sprint1.typewriter',
  bubbleSwap: 'maic.sprint1.bubbleSwap',
  thinkingDots: 'maic.sprint1.thinkingDots',
  discussionGate: 'maic.sprint1.discussionGate',
} as const;

export type Sprint1Flag = (typeof SPRINT1_FLAGS)[keyof typeof SPRINT1_FLAGS];

/** Read the current value of a flag. Defaults to `true` (on) when the
 *  key is absent or the browser has no localStorage (SSR / privacy). */
export function isSprintFlagOn(key: Sprint1Flag): boolean {
  if (typeof window === 'undefined') return true;
  try {
    return window.localStorage.getItem(key) !== 'off';
  } catch {
    return true;
  }
}

/** Imperative setter — useful for tests, dev console, or an eventual
 *  in-app debug panel. Dispatches a `storage`-like event so any active
 *  `useSprintFlag` subscribers in the same tab re-render. */
export function setSprintFlag(key: Sprint1Flag, value: 'on' | 'off'): void {
  if (typeof window === 'undefined') return;
  try {
    if (value === 'on') window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, 'off');
    window.dispatchEvent(new StorageEvent('storage', { key, newValue: value === 'off' ? 'off' : null }));
  } catch {
    /* privacy-mode / quota — silent no-op */
  }
}

/** React hook wrapper. Re-renders on cross-tab localStorage changes
 *  AND on in-tab changes via setSprintFlag(). */
export function useSprintFlag(key: Sprint1Flag): boolean {
  const [on, setOn] = useState<boolean>(() => isSprintFlagOn(key));

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const onStorage = (e: StorageEvent) => {
      if (e.key === key) setOn(isSprintFlagOn(key));
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, [key]);

  return on;
}
