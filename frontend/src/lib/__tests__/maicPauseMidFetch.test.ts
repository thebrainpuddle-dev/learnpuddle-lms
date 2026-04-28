// CG-P1-13 — pause-mid-fetch race
//
// Bug (audit P0-2 / F6): pressing Pause while a TTS fetch is in flight is
// a no-op for `pauseCurrentAudio` (no audio element exists yet). When the
// fetch resolves, `playAudioSynced` runs `audio.play()` regardless of the
// playback engine's mode. UI says "paused" but audio plays.
//
// Fix: action engine exposes `abortInFlightFetch()`. Playback engine's
// `pause()` calls it; if a fetch was actually aborted (vs pause hitting
// during active audio), it ALSO rewinds `currentActionIndex` so the
// in-progress speech action replays cleanly on `resume()`.
//
// These tests target the action-engine surface (`abortInFlightFetch`)
// directly. The playback-engine integration is covered by existing
// pause/resume tests; the addition is a guarded conditional.

import { describe, test, expect, vi, beforeEach } from 'vitest';
import { MAICActionEngine } from '../maicActionEngine';

// Minimal mock so the engine's audio path (irrelevant to this test) doesn't
// throw on construction.
class _MockAudio {
  src = '';
  volume = 1;
  playbackRate = 1;
  currentTime = 0;
  paused = true;
  onplaying: (() => void) | null = null;
  onended: (() => void) | null = null;
  onerror: (() => void) | null = null;
  play = vi.fn().mockResolvedValue(undefined);
  pause = vi.fn();
  load = vi.fn();
  addEventListener = vi.fn();
  removeEventListener = vi.fn();
}
beforeEach(() => {
  // @ts-expect-error window.Audio shim
  global.Audio = _MockAudio;
});

describe('CG-P1-13 abortInFlightFetch — pause-mid-fetch race', () => {
  test('returns false when no fetch is in flight', () => {
    const engine = new MAICActionEngine({ ttsEndpoint: '/tts', token: 't' });
    // No fetch has been started — controller is null
    expect(engine.abortInFlightFetch()).toBe(false);
  });

  test('aborts the controller and returns true when a fetch IS in flight', async () => {
    // Mock fetch to NEVER resolve so we can pause "mid-fetch" deterministically.
    const fetchMock = vi.fn().mockImplementation(
      () => new Promise(() => { /* hang forever */ }),
    );
    // @ts-expect-error browser global
    global.fetch = fetchMock;

    const engine = new MAICActionEngine({ ttsEndpoint: '/tts', token: 't' });

    // Kick off a fetch (do not await — it never resolves)
    void engine.fetchTtsBlob?.('hello', 'voice', 0);
    // Give the engine a microtask to set currentFetchController
    await new Promise((r) => setTimeout(r, 5));

    // Now in the "mid-fetch" state — abort should succeed.
    const aborted = engine.abortInFlightFetch();
    expect(aborted).toBe(true);

    // Internal state: controller cleared, token bumped
    // @ts-expect-error internal field probe
    expect(engine.currentFetchController).toBeNull();
  });

  test('bumps generationToken so a post-fetch executeSpeech path returns early', async () => {
    const engine = new MAICActionEngine({ ttsEndpoint: '/tts', token: 't' });
    // @ts-expect-error internal probe
    const beforeToken = engine.generationToken;

    // Fake a controller so abortInFlightFetch has something to abort.
    // @ts-expect-error internal field probe
    engine.currentFetchController = new AbortController();

    engine.abortInFlightFetch();

    // @ts-expect-error internal probe
    const afterToken = engine.generationToken;
    expect(afterToken).toBeGreaterThan(beforeToken);
  });

  test('idempotent — second call when nothing is in flight returns false', () => {
    const engine = new MAICActionEngine({ ttsEndpoint: '/tts', token: 't' });
    // @ts-expect-error internal field probe
    engine.currentFetchController = new AbortController();
    expect(engine.abortInFlightFetch()).toBe(true);
    expect(engine.abortInFlightFetch()).toBe(false);
  });
});
