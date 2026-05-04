/**
 * Browser-native TTS player — wrapper around `window.speechSynthesis`.
 *
 * Source:
 *   /Volumes/CrucialX9/OpenMAIC/lib/playback/engine.ts:601-744
 *   (the inline browser-TTS path upstream embeds in the engine; we
 *   factor it into its own module so the engine integration in
 *   MAIC-413.2 is a thin call-site change.)
 *
 * Used by:
 *   - frontend/src/lib/maic-v2/playback-engine.ts (MAIC-413.2)
 *     when a `speech` action arrives with no pre-generated audio AND
 *     the estimated reading time is >=15s, the engine routes through
 *     `BrowserTTSPlayer.speak(text, onEnded)` instead of the
 *     reading-timer fallback.
 *
 * Why a separate module
 *   speechSynthesis is a real DOM API, not a polyfillable shim.
 *   Tests that touch the actual API run only in real-browser headless
 *   Chromium (`/tmp/maic_phase3_tts_chunked.mjs`); the chunking logic
 *   `chunkUtterance` is a pure function and IS unit-tested in vitest.
 *
 * Chrome quirks this module mitigates
 *   1. 15-second cutoff per utterance — sentence-boundary chunking.
 *   2. `onend` doesn't fire when window blurs — watchdog timer.
 *   3. Queue stalls after multiple utterances — cancel + restart on
 *      every new `speak()` call.
 *   4. `getVoices()` is async at startup — we don't pin a voice; the
 *      browser uses its default.
 */


// ── Constants ──────────────────────────────────────────────────────


/** Default chunk size — well below Chrome's 15s utterance cutoff. */
const DEFAULT_MAX_CHARS = 120;

/** Watchdog padding: per-character ms estimate + buffer. Mirrors
 *  the plan's `text.length * 80ms + 5s` formula. */
const WATCHDOG_MS_PER_CHAR = 80;
const WATCHDOG_BUFFER_MS = 5000;

const SENTENCE_TERMINATORS = ['.', '!', '?', '。', '！', '？'];
const SECONDARY_TERMINATORS = [',', ';', ':', '，', '；', '：'];


// ── Pure-function chunking helper (unit-tested) ────────────────────


/**
 * Split `text` into chunks ≤ `maxChars`, preferring sentence
 * boundaries.
 *
 * Rules (applied per source-text segment, in order):
 *   1. Split on sentence terminators (.!?。！？). Punctuation kept
 *      attached to the trailing chunk.
 *   2. If a chunk is still > `maxChars`, secondary-split on
 *      ,;:，；： (clauses).
 *   3. If still too long, split on whitespace at the latest position
 *      ≤ `maxChars`.
 *   4. Final fallback: hard-cut at `maxChars` (rare; only triggered
 *      by single-word > `maxChars` inputs like base64-encoded blobs).
 *
 * Empty / whitespace-only chunks are dropped; surviving chunks are
 * trimmed.
 */
export function chunkUtterance(text: string, maxChars = DEFAULT_MAX_CHARS): string[] {
  if (!text || !text.trim()) return [];
  if (maxChars <= 0) return [text.trim()];

  // Pass 1 — sentence boundaries.
  const sentences = _splitKeepingTerminators(text, SENTENCE_TERMINATORS);

  // Pass 2/3/4 — recursively shrink any sentence still over the cap.
  const out: string[] = [];
  for (const s of sentences) {
    _splitToMax(s, maxChars, out);
  }
  return out.map((c) => c.trim()).filter(Boolean);
}


function _splitKeepingTerminators(text: string, terminators: string[]): string[] {
  const out: string[] = [];
  let buf = '';
  for (const ch of text) {
    buf += ch;
    if (terminators.includes(ch)) {
      out.push(buf);
      buf = '';
    }
  }
  if (buf.length > 0) out.push(buf);
  return out;
}


function _splitToMax(text: string, maxChars: number, out: string[]): void {
  const trimmed = text.trim();
  if (!trimmed) return;
  if (trimmed.length <= maxChars) {
    out.push(trimmed);
    return;
  }

  // Pass 2 — secondary terminators (clause splits).
  const clauses = _splitKeepingTerminators(trimmed, SECONDARY_TERMINATORS);
  if (clauses.length > 1) {
    for (const c of clauses) _splitToMax(c, maxChars, out);
    return;
  }

  // Pass 3 — whitespace at the latest position ≤ maxChars.
  const wsIndex = trimmed.lastIndexOf(' ', maxChars);
  if (wsIndex > 0) {
    out.push(trimmed.slice(0, wsIndex).trim());
    _splitToMax(trimmed.slice(wsIndex + 1), maxChars, out);
    return;
  }

  // Pass 4 — hard cut. Only reached on single-word > maxChars inputs.
  out.push(trimmed.slice(0, maxChars));
  _splitToMax(trimmed.slice(maxChars), maxChars, out);
}


// ── Public interface ──────────────────────────────────────────────


export interface BrowserTTSPlayer {
  /** Speak `text`, calling `onEnded` exactly once when complete or
   *  when the watchdog force-completes after a Chrome `onend` skip. */
  speak(text: string, onEnded: () => void): void;
  pause(): void;
  resume(): void;
  /** Stop immediately, clear the queue, swallow any pending onEnded. */
  cancel(): void;
  isSpeaking(): boolean;
  /** False when the runtime has no `speechSynthesis` (jsdom, happy-dom,
   *  certain embedded browsers). Callers should fall back to the
   *  reading-time path when this returns false. */
  isAvailable(): boolean;
}


// ── Factory ────────────────────────────────────────────────────────


export function createBrowserTTSPlayer(): BrowserTTSPlayer {
  return new _BrowserTTSPlayerImpl();
}


// ── Implementation ────────────────────────────────────────────────


class _BrowserTTSPlayerImpl implements BrowserTTSPlayer {
  private _watchdog: ReturnType<typeof setTimeout> | null = null;
  private _watchdogStart = 0;
  private _watchdogRemaining = 0;
  private _activeOnEnded: (() => void) | null = null;
  private _isPausedFlag = false;

  isAvailable(): boolean {
    return (
      typeof window !== 'undefined' &&
      typeof window.speechSynthesis !== 'undefined' &&
      typeof window.SpeechSynthesisUtterance === 'function'
    );
  }

  isSpeaking(): boolean {
    if (!this.isAvailable()) return false;
    return window.speechSynthesis.speaking || window.speechSynthesis.pending;
  }

  speak(text: string, onEnded: () => void): void {
    if (!this.isAvailable()) {
      // Fast fall-through — caller should have already gated on
      // isAvailable(), but guard anyway so we always honor the
      // onEnded contract (called exactly once).
      onEnded();
      return;
    }

    // Cancel any in-flight queue (Chrome bug: queue stalls if you
    // speak() into a non-empty queue without canceling first).
    this._clearWatchdog();
    if (this._activeOnEnded) {
      // A new speak() supersedes the old one — drop the old callback.
      this._activeOnEnded = null;
    }
    window.speechSynthesis.cancel();
    this._isPausedFlag = false;

    const chunks = chunkUtterance(text);
    if (chunks.length === 0) {
      onEnded();
      return;
    }

    this._activeOnEnded = onEnded;

    // Queue every chunk; only the last utterance's `onend` invokes
    // the caller's callback.  Earlier chunks' `onend` does nothing.
    const lastIndex = chunks.length - 1;
    chunks.forEach((chunk, i) => {
      const u = new window.SpeechSynthesisUtterance(chunk);
      if (i === lastIndex) {
        u.onend = () => this._fireOnEnded();
      }
      // No onerror handler — speechSynthesis errors are typically
      // silent failures (the watchdog catches them). If a future
      // browser surfaces useful errors here, add per-utterance
      // handling.
      window.speechSynthesis.speak(u);
    });

    // Arm the watchdog. Total estimate covers ALL chunks together.
    const totalMs = text.length * WATCHDOG_MS_PER_CHAR + WATCHDOG_BUFFER_MS;
    this._armWatchdog(totalMs);
  }

  pause(): void {
    if (!this.isAvailable()) return;
    if (this._isPausedFlag) return;
    this._isPausedFlag = true;
    window.speechSynthesis.pause();
    // Freeze watchdog: capture remaining time so resume() can
    // reschedule precisely.  Without this, a long pause would let
    // the watchdog fire spuriously.
    if (this._watchdog) {
      const elapsed = Date.now() - this._watchdogStart;
      this._watchdogRemaining = Math.max(0, this._watchdogRemaining - elapsed);
      clearTimeout(this._watchdog);
      this._watchdog = null;
    }
  }

  resume(): void {
    if (!this.isAvailable()) return;
    if (!this._isPausedFlag) return;
    this._isPausedFlag = false;
    window.speechSynthesis.resume();
    // Reschedule watchdog with the remaining time captured at pause().
    if (this._watchdogRemaining > 0) {
      this._armWatchdog(this._watchdogRemaining);
      this._watchdogRemaining = 0;
    }
  }

  cancel(): void {
    if (!this.isAvailable()) {
      this._activeOnEnded = null;
      return;
    }
    this._clearWatchdog();
    // Drop the callback BEFORE speechSynthesis.cancel — some browsers
    // synchronously fire `onend` with `event.utterance.onend`, and
    // we don't want a cancel to invoke the onEnded contract.
    this._activeOnEnded = null;
    this._isPausedFlag = false;
    window.speechSynthesis.cancel();
  }

  // ── Internal ────────────────────────────────────────────────────

  private _armWatchdog(ms: number): void {
    this._clearWatchdog();
    this._watchdogStart = Date.now();
    this._watchdogRemaining = ms;
    this._watchdog = setTimeout(() => {
      this._watchdog = null;
      this._watchdogRemaining = 0;
      // Watchdog fired: speechSynthesis didn't deliver onend in time.
      // Force-fire the caller's callback so the engine doesn't hang.
      console.warn(
        '[BrowserTTSPlayer] watchdog fired — speechSynthesis.onend skipped',
      );
      this._fireOnEnded();
    }, ms);
  }

  private _clearWatchdog(): void {
    if (this._watchdog) {
      clearTimeout(this._watchdog);
      this._watchdog = null;
    }
    this._watchdogRemaining = 0;
  }

  private _fireOnEnded(): void {
    const cb = this._activeOnEnded;
    this._activeOnEnded = null;
    this._clearWatchdog();
    if (cb) cb();
  }
}
