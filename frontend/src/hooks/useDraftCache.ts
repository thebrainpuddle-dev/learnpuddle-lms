// src/hooks/useDraftCache.ts
//
// Drop-in replacement for `useState<string>` that persists to
// localStorage so an interrupted flow (accidental refresh, browser
// crash, tab close) doesn't lose the user's typed draft. Sprint 2 · A.4
// — currently used for the GenerationWizard "topic" field but generic
// enough to reuse on other long-form drafts.
//
// Design:
//   - Debounced write (300ms) so keystroke storms don't hammer
//     localStorage — important on lower-end devices.
//   - Synchronous read on init so the initial render already shows the
//     restored value (no flicker).
//   - Call `clearDraft()` after a successful submit to avoid restoring
//     a stale draft for the next session.
//   - SSR-safe: guards `window` access so this can be imported from
//     code paths that may render on the server.

import { useCallback, useEffect, useRef, useState } from 'react';

const DEBOUNCE_MS = 300;

export interface UseDraftCacheReturn<T extends string> {
  value: T;
  setValue: (next: T) => void;
  clearDraft: () => void;
}

function readStorage(key: string, fallback: string): string {
  if (typeof window === 'undefined') return fallback;
  try {
    const v = window.localStorage.getItem(key);
    return v == null ? fallback : v;
  } catch {
    return fallback;
  }
}

function writeStorage(key: string, value: string): void {
  if (typeof window === 'undefined') return;
  try {
    if (value === '') window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    /* quota / privacy-mode — silent no-op */
  }
}

export function useDraftCache<T extends string = string>(
  key: string,
  initialValue: T = '' as T,
): UseDraftCacheReturn<T> {
  const [value, setValueState] = useState<T>(() => readStorage(key, initialValue) as T);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const setValue = useCallback((next: T) => {
    setValueState(next);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => writeStorage(key, next), DEBOUNCE_MS);
  }, [key]);

  const clearDraft = useCallback(() => {
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
      debounceRef.current = null;
    }
    writeStorage(key, '');
    setValueState('' as T);
  }, [key]);

  // Flush pending write on unmount so a quick typing → navigate-away
  // cycle doesn't drop the last few characters.
  useEffect(() => {
    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
        debounceRef.current = null;
      }
      // Persist the latest observed value synchronously on unmount.
      writeStorage(key, value);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- we only flush latest value on unmount
  }, []);

  return { value, setValue, clearDraft };
}
