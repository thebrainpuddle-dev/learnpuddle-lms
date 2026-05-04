/**
 * Tests for Phase3TtsFallbackDemo (MAIC-418.2).
 *
 * In jsdom/happy-dom, `window.speechSynthesis` is undefined →
 * BrowserTTSPlayer.isAvailable() returns false → engine routes through
 * the silent reading-timer instead of speechSynthesis. So these unit
 * tests verify:
 *   - Demo renders with idle state
 *   - data-tts-state flips on Start (via the engine's onSpeechStart
 *     callback, which fires regardless of which fallback path runs)
 *   - The scene's text is long enough that `_estimateReadingMs` would
 *     route through BrowserTTS in a real browser
 *
 * The actual speechSynthesis behavior is validated by the headless
 * Chromium smoke (MAIC-418.4).
 */
import { describe, expect, test, vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';

import Phase3TtsFallbackDemo from '../Phase3TtsFallbackDemo';


describe('Phase3TtsFallbackDemo', () => {
  test('renders the demo root with idle mode + idle tts-state', () => {
    render(<Phase3TtsFallbackDemo />);
    const root = screen.getByTestId('phase3-tts-fallback');
    expect(root).toHaveAttribute('data-engine-mode', 'idle');
    expect(root).toHaveAttribute('data-tts-state', 'idle');
  });

  test('exposes the documented testids', () => {
    render(<Phase3TtsFallbackDemo />);
    expect(screen.getByTestId('phase3-tts-start')).toBeInTheDocument();
  });

  test('clicking Start fires onSpeechStart → tts-state becomes "speaking"', () => {
    vi.useFakeTimers();
    try {
      const { container } = render(<Phase3TtsFallbackDemo />);
      fireEvent.click(screen.getByTestId('phase3-tts-start'));
      // Engine processes immediately. Speech action dispatches; the
      // engine's audioPlayer.play() returns false (no audioUrl), then
      // _dispatchSpeechFallback fires onSpeechStart synchronously
      // before scheduling the reading timer.
      // (In real Chrome with speechSynthesis available, the
      // BrowserTTSPlayer.speak path also fires onSpeechStart.)
      const root = container.querySelector('[data-testid="phase3-tts-fallback"]')!;
      expect(root.getAttribute('data-tts-state')).toBe('speaking');
    } finally {
      vi.useRealTimers();
    }
  });

  test('reading-timer completion fires onSpeechEnd → tts-state becomes "ended"', async () => {
    vi.useFakeTimers();
    try {
      const { container } = render(<Phase3TtsFallbackDemo />);
      fireEvent.click(screen.getByTestId('phase3-tts-start'));

      // audioPlayer.play() returns a Promise that resolves to false
      // (no audioUrl). The reading-timer setTimeout schedules INSIDE
      // that .then() — runAllTimersAsync flushes microtasks AND
      // advances timers, which is what the engine flow needs.
      await act(async () => {
        await vi.runAllTimersAsync();
      });

      const root = container.querySelector('[data-testid="phase3-tts-fallback"]')!;
      expect(root.getAttribute('data-tts-state')).toBe('ended');
    } finally {
      vi.useRealTimers();
    }
  });

  test('Stop returns the demo to idle', () => {
    vi.useFakeTimers();
    try {
      const { container } = render(<Phase3TtsFallbackDemo />);
      fireEvent.click(screen.getByTestId('phase3-tts-start'));
      // Stop button only renders when mode != 'idle'
      const stopBtn = screen.queryByTestId('phase3-tts-stop');
      if (stopBtn) {
        fireEvent.click(stopBtn);
      }
      const root = container.querySelector('[data-testid="phase3-tts-fallback"]')!;
      expect(root.getAttribute('data-tts-state')).toBe('idle');
    } finally {
      vi.useRealTimers();
    }
  });

  test('scene text is long enough to trigger BrowserTTS routing in a real browser', () => {
    // Lock the contract: the demo's text MUST be long enough that
    // _estimateReadingMs returns >= 15000ms. If a future edit
    // shortens the text below threshold, the smoke would silently
    // fall through to reading-timer and never exercise speechSynthesis.
    render(<Phase3TtsFallbackDemo />);
    const text = screen.getByText(/photosynthesis/i, { selector: 'pre' });
    const wordCount = (text.textContent ?? '').split(/\s+/).filter(Boolean).length;
    // 240 ms/word × 63 words = 15120ms (just over the threshold);
    // we want comfortable margin.
    expect(wordCount).toBeGreaterThanOrEqual(70);
  });
});
