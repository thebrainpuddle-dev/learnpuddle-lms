// src/components/maic/TypewriterText.tsx
//
// Character-by-character text reveal used by PresentationSpeechOverlay
// (Sprint 1 · B.2). Takes a string and a speed (ms/char) and streams the
// characters in over time so speech lines feel typed rather than dumped.
//
// Design notes:
//   - We don't animate on every keystroke — we use a single setInterval
//     and slice the text. This keeps DOM churn low even for long lines.
//   - Respects `prefers-reduced-motion`: if the user has it set, we
//     render the full string immediately (no animation).
//   - Restart-on-text-change is handled by the PARENT via `key={text}`
//     so we don't need to diff here; a fresh mount starts a fresh run.
//   - Keeps the exact surrounding whitespace (doesn't trim).

import React, { useEffect, useRef, useState } from 'react';
import { useMAICSettingsStore } from '../../stores/maicSettingsStore';

export interface TypewriterTextProps {
  /** The full string to reveal. */
  text: string;
  /** Milliseconds per character. Default 30ms. */
  speedMs?: number;
  /** Optional className forwarded to the <span>. */
  className?: string;
  /** Render element. Defaults to <span> to sit inline. */
  as?: 'span' | 'p' | 'div';
}

function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined' || !window.matchMedia) return false;
  try {
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  } catch {
    return false;
  }
}

export const TypewriterText = React.memo<TypewriterTextProps>(function TypewriterText({
  text,
  speedMs = 30,
  className,
  as = 'span',
}) {
  // Sync reveal speed with the global playback speed setting so text reveal,
  // TTS audio (audio.playbackRate), and video (video.playbackRate) finish
  // together. `speedMs` here is the delay between chars, so higher playback
  // speed means SHORTER per-char delay. Clamp so reduced speed doesn't make
  // chars jitter-slow and max speed doesn't overflow microtask queue.
  const playbackSpeed = useMAICSettingsStore((s) => s.playbackSpeed);
  const effectiveSpeedMs = Math.max(5, Math.min(200, Math.round(speedMs / (playbackSpeed || 1))));

  const reduced = useRef(prefersReducedMotion());
  const [visibleCount, setVisibleCount] = useState<number>(() =>
    reduced.current ? text.length : 0,
  );
  // Track the last text we animated for so we can detect whether the
  // parent replaced the text (new message — restart) or APPENDED to it
  // (streaming chunk — continue from current cursor). T2 relies on the
  // append path so SSE deltas don't replay the full message each chunk.
  const lastTextRef = useRef<string>(text);
  const visibleCountRef = useRef<number>(visibleCount);
  visibleCountRef.current = visibleCount;

  useEffect(() => {
    if (reduced.current) {
      setVisibleCount(text.length);
      lastTextRef.current = text;
      return;
    }
    // Decide: fresh run (replacement) or continuation (append)?
    const prev = lastTextRef.current;
    const isAppend = text.length >= prev.length && text.startsWith(prev);
    const startAt = isAppend
      ? Math.min(visibleCountRef.current, text.length)
      : 0;
    lastTextRef.current = text;
    setVisibleCount(startAt);
    if (!text || startAt >= text.length) return;

    let cancelled = false;
    let i = startAt;
    const tick = () => {
      if (cancelled) return;
      i += 1;
      setVisibleCount(i);
      if (i < text.length) {
        timer = window.setTimeout(tick, effectiveSpeedMs);
      }
    };
    let timer = window.setTimeout(tick, effectiveSpeedMs);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [text, effectiveSpeedMs]);

  const shown = text.slice(0, visibleCount);
  const Tag = as;
  return <Tag className={className}>{shown}</Tag>;
});
