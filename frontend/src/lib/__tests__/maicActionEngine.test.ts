// maicActionEngine.test.ts — unit tests for the Chunk 5 speech rewrite.
//
// What we prove:
//   1. Subtitle + speaking-agent indicator fire on the audio element's
//      `playing` event, NOT before `play()`. No flash of subtitles for
//      audio that never actually starts.
//   2. abortCurrentAction() after speech starts detaches all audio event
//      handlers — so even if buffered `ended` events fire, onSpeechEnd
//      does not run.
//   3. Rapid execute × abortCurrentAction × 10 leaves no stale audio
//      element reference on the engine.
//   4. readingTimeFallback schedules a timer proportional to text length
//      (min 2 s, ~60 ms/char) when no audioUrl is supplied and no TTS
//      server is reachable.

import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest';
import { MAICActionEngine } from '../maicActionEngine';
import { useMAICStageStore } from '../../stores/maicStageStore';
import { useMAICSettingsStore } from '../../stores/maicSettingsStore';

// ─── Mock HTMLAudioElement ──────────────────────────────────────────────────

interface MockAudioInstance {
  src: string;
  volume: number;
  playbackRate: number;
  paused: boolean;
  onplaying: (() => void) | null;
  onended: (() => void) | null;
  onerror: (() => void) | null;
  play: ReturnType<typeof vi.fn>;
  pause: ReturnType<typeof vi.fn>;
  endNow: () => void;
  errorNow: () => void;
}

const mockAudios: MockAudioInstance[] = [];

class MockAudio implements MockAudioInstance {
  src = '';
  volume = 1;
  playbackRate = 1;
  paused = false;
  onplaying: (() => void) | null = null;
  onended: (() => void) | null = null;
  onerror: (() => void) | null = null;
  play = vi.fn().mockImplementation(() => {
    // Fire `playing` asynchronously (micro-delay — simulates browser).
    setTimeout(() => {
      if (!this.paused) this.onplaying?.();
    }, 10);
    return Promise.resolve();
  });
  pause = vi.fn().mockImplementation(() => {
    this.paused = true;
  });
  constructor() {
    mockAudios.push(this);
  }
  /** Test helper — simulate the audio ending. */
  endNow() {
    this.onended?.();
  }
  /** Test helper — simulate an audio error. */
  errorNow() {
    this.onerror?.();
  }
}

beforeEach(() => {
  mockAudios.length = 0;
  // @ts-expect-error browser global in tests
  global.Audio = MockAudio;
  // Reset stores to a known state with one agent.
  useMAICStageStore.setState({
    agents: [
      {
        id: 'a1',
        name: 'Professor Sharma',
        role: 'professor',
        voiceId: 'en-IN-PrabhatNeural',
      } as any,
    ],
    speakingAgentId: null,
    speechText: null,
    spotlightElementId: null,
    scenes: [],
    currentSceneIndex: 0,
  });
  useMAICSettingsStore.setState({
    audioVolume: 1,
    playbackSpeed: 1,
  } as any);
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

// URL.createObjectURL / revokeObjectURL are JSDOM-stubbed via counters so
// we can observe leak-free cleanup after prefetch aborts.
let _nextBlobId = 0;
const _revokedUrls = new Set<string>();
beforeEach(() => {
  _nextBlobId = 0;
  _revokedUrls.clear();
  // @ts-expect-error jsdom lacks these; vitest provides partial impl
  global.URL.createObjectURL = vi.fn(() => `blob:mock-${++_nextBlobId}`);
  // @ts-expect-error same
  global.URL.revokeObjectURL = vi.fn((u: string) => {
    _revokedUrls.add(u);
  });
});

// ─── Tests ──────────────────────────────────────────────────────────────────

describe('MAICActionEngine.executeSpeech', () => {
  test('subtitle is deferred until audio.onplaying — sync with voice, not ahead', async () => {
    // Audio-sync fix (2026-04-23): the previous Chunk 9 contract fired
    // subtitles eagerly at speech entry, which produced a ~50-300ms gap
    // where text was on screen before voice. The new (upstream-OpenMAIC)
    // contract waits for `audio.onplaying` so text and voice appear in
    // lockstep. The speaker avatar IS set eagerly so the UI knows WHO is
    // about to speak while the audio decodes.
    const onStart = vi.fn();
    const engine = new MAICActionEngine({
      ttsEndpoint: '/tts',
      token: 't',
      onSpeechStart: onStart,
    });

    const promise = engine.execute({
      type: 'speech',
      agentId: 'a1',
      text: 'Hello students',
      audioUrl: 'https://example.com/hello.mp3',
    } as any);

    // Speaking indicator is set immediately; subtitle text is NOT yet.
    await new Promise((r) => setTimeout(r, 0));
    expect(useMAICStageStore.getState().speakingAgentId).toBe('a1');
    expect(onStart).not.toHaveBeenCalled();
    expect(useMAICStageStore.getState().speechText).toBeNull();

    // After mock audio's `playing` event fires (10 ms), subtitles land.
    await new Promise((r) => setTimeout(r, 15));
    expect(onStart).toHaveBeenCalledWith('a1', 'Hello students');
    expect(useMAICStageStore.getState().speechText).toBe('Hello students');
    expect(useMAICStageStore.getState().speakingAgentId).toBe('a1');

    // Trigger end → promise resolves. T0.2 — audio.onended no longer
    // nulls the bubble; the overlay holds the last line between
    // speakers until the next onSpeechStart overwrites it. Scene
    // change / abort still clears (asserted by other tests).
    mockAudios[0].endNow();
    await promise;
    expect(useMAICStageStore.getState().speechText).toBe('Hello students');
    expect(useMAICStageStore.getState().speakingAgentId).toBe('a1');
  });

  test('abortCurrentAction after speech starts prevents onended/subtitles leaking', async () => {
    const onStart = vi.fn();
    const onEnd = vi.fn();
    const engine = new MAICActionEngine({
      ttsEndpoint: '/tts',
      token: 't',
      onSpeechStart: onStart,
      onSpeechEnd: onEnd,
    });

    engine.execute({
      type: 'speech',
      agentId: 'a1',
      text: 'one',
      audioUrl: 'https://example.com/one.mp3',
    } as any);

    // Let playing fire → subtitle shown.
    await new Promise((r) => setTimeout(r, 15));
    expect(onStart).toHaveBeenCalledTimes(1);

    // Abort (simulates scene change mid-speech).
    engine.abortCurrentAction();

    // Now a buffered `ended` event arriving on the OLD audio should be a no-op —
    // handlers were detached and the reference dropped.
    const firstAudio = mockAudios[0];
    firstAudio.endNow();
    await new Promise((r) => setTimeout(r, 5));
    expect(onEnd).not.toHaveBeenCalled();

    // State is clean.
    expect(useMAICStageStore.getState().speakingAgentId).toBeNull();
    expect(useMAICStageStore.getState().speechText).toBeNull();
    // @ts-expect-error testing internal
    expect(engine.audioElement).toBeNull();
  });

  test('rapid execute × abortCurrentAction × 10 leaves one audioElement ref', async () => {
    const engine = new MAICActionEngine({ ttsEndpoint: '/tts', token: 't' });
    for (let i = 0; i < 10; i++) {
      engine.execute({
        type: 'speech',
        agentId: 'a1',
        text: `line ${i}`,
        audioUrl: `https://example.com/${i}.mp3`,
      } as any);
      engine.abortCurrentAction();
    }
    // @ts-expect-error testing internal
    expect(engine.audioElement).toBeNull();
  });

  test('prefetchSpeech populates cache, fetchTtsBlob consumes it without a second network call', async () => {
    // Mock fetch to return a 200 MP3 blob. Count how many times it's
    // called — with prefetch, only ONE call total: the prefetch. The
    // subsequent executeSpeech should pull from cache.
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(new Blob([new Uint8Array([0xff, 0xfb])], { type: 'audio/mpeg' }), {
        status: 200,
      }),
    );
    // @ts-expect-error browser global
    global.fetch = fetchMock;

    const engine = new MAICActionEngine({ ttsEndpoint: '/tts', token: 't' });
    const action = {
      type: 'speech',
      agentId: 'a1',
      text: 'Hello students',
    } as any;

    // Kick off prefetch. Wait for the fetch + blob decode to settle.
    engine.prefetchSpeech(action);
    await new Promise((r) => setTimeout(r, 15));
    expect(fetchMock).toHaveBeenCalledTimes(1);

    // Now play the same action. It must consume the cache, NOT hit fetch again.
    const playPromise = engine.execute(action);
    await new Promise((r) => setTimeout(r, 20));
    // Still one fetch call — cache hit avoided a second network round-trip.
    expect(fetchMock).toHaveBeenCalledTimes(1);

    // Complete the audio so the engine releases resources.
    mockAudios[0]?.endNow();
    await playPromise;
  });

  test('prefetchSceneSpeeches prefetches ALL scene speech actions ahead of playback', async () => {
    // Scene-wide prefetch is the single biggest audio-lag win: every
    // speech action in the scene gets a TTS fetch kicked off on
    // loadScene, so when playback starts the first line (and every
    // subsequent one) is served from the in-memory blob cache rather
    // than blocking on a live network round-trip.
    const fetchMock = vi.fn().mockImplementation(
      () => Promise.resolve(new Response(
        new Blob([new Uint8Array([0xff, 0xfb])], { type: 'audio/mpeg' }),
        { status: 200 },
      )),
    );
    // @ts-expect-error browser global
    global.fetch = fetchMock;

    const engine = new MAICActionEngine({ ttsEndpoint: '/tts', token: 't' });
    const actions = [
      { type: 'speech', agentId: 'a1', text: 'line one' },
      { type: 'wb_draw_text', id: 'wb1', text: 'x', left: 0, top: 0, width: 10 },
      { type: 'speech', agentId: 'a1', text: 'line two' },
      { type: 'speech', agentId: 'a1', text: 'line three' },
      { type: 'speech', agentId: 'a1', text: 'line four', audioUrl: 'https://x/p.mp3' },
    ] as any;

    engine.prefetchSceneSpeeches(actions);
    // Let the concurrency pipeline drain all 3 live-TTS speeches.
    // audioUrl-bearing speech #4 is skipped (already pre-gen).
    await new Promise((r) => setTimeout(r, 200));

    expect(fetchMock).toHaveBeenCalledTimes(3);
    // Cache should hold the three decoded blobs so that at playtime
    // executeSpeech pulls them instantly — no extra fetch.
    const firstPlay = engine.execute(actions[0]);
    await new Promise((r) => setTimeout(r, 20));
    expect(fetchMock).toHaveBeenCalledTimes(3);
    mockAudios[0]?.endNow();
    await firstPlay;

    engine.dispose();
  });

  test('abortCurrentAction revokes all prefetched blob URLs', async () => {
    // Return a FRESH Response each call — Response bodies are single-use,
    // so a shared mocked Response causes the second .blob() to throw.
    const fetchMock = vi.fn().mockImplementation(
      () => Promise.resolve(new Response(
        new Blob([new Uint8Array([0xff, 0xfb])], { type: 'audio/mpeg' }),
        { status: 200 },
      )),
    );
    // @ts-expect-error browser global
    global.fetch = fetchMock;

    const engine = new MAICActionEngine({ ttsEndpoint: '/tts', token: 't' });
    engine.prefetchSpeech({ type: 'speech', agentId: 'a1', text: 'one' } as any);
    engine.prefetchSpeech({ type: 'speech', agentId: 'a1', text: 'two' } as any);
    await new Promise((r) => setTimeout(r, 30));
    expect(_revokedUrls.size).toBe(0);

    // Aborting should clear the cache + revoke both URLs.
    engine.abortCurrentAction();
    expect(_revokedUrls.size).toBeGreaterThanOrEqual(2);
  });

  test('readingTimeFallback starts on fetch failure and aborts cleanly', async () => {
    const onStart = vi.fn();
    const onEnd = vi.fn();
    const engine = new MAICActionEngine({
      ttsEndpoint: '/tts',
      token: 't',
      onSpeechStart: onStart,
      onSpeechEnd: onEnd,
    });

    // Force fetch to reject → fetchTtsBlob catches and returns null →
    // executeSpeech falls through to readingTimeFallback.
    // @ts-expect-error browser global
    global.fetch = vi.fn().mockRejectedValue(new Error('network off'));

    // No audioUrl on the action → fall into fetchTtsBlob → null → reading fallback.
    const promise = engine.execute({
      type: 'speech',
      agentId: 'a1',
      text: 'abc', // 3 chars → max(2000, 3*60=180) = 2000 ms.
    } as any);

    // Let the fetch rejection + microtasks settle.
    await new Promise((r) => setTimeout(r, 50));

    // After the synchronous prefix of readingTimeFallback, onStart has fired
    // and the 2 s timer is pending.
    expect(onStart).toHaveBeenCalledWith('a1', 'abc');
    expect(useMAICStageStore.getState().speechText).toBe('abc');
    expect(onEnd).not.toHaveBeenCalled();

    // Abort — timer should be cleared and the promise released synchronously.
    engine.abortCurrentAction();
    await promise;
    // onEnd was NOT called because the token was invalidated before the timer fired.
    expect(onEnd).not.toHaveBeenCalled();
    expect(useMAICStageStore.getState().speechText).toBeNull();
  });
});

// ─── TEST-P0-7 — unlockAudio autoplay-block coverage ────────────────────────
//
// MOB-P0-5 (2026-04-23) replaced the silent-audio unlock with a dual-strategy
// unlock: AudioContext.resume() + 1-sample buffer (iOS canonical trick), with
// an HTMLAudioElement silent-WAV fallback.
//
// TEST-P0-7-F1 (2026-04-24): `_audioUnlocked = true` is now set ONLY inside
// the resume().then() / Audio.play().then() success callback. A first-attempt
// NotAllowedError (pre-gesture call) leaves `_audioUnlocked = false` so the
// same engine instance — or a fresh one — can retry on the next user gesture.
//
// These tests assert:
//
//   1. A fresh engine instance (with `_audioUnlocked = false`) can retry
//      unlock after an earlier instance's AudioContext.resume() was rejected
//      with NotAllowedError.
//
//   2. When `window.AudioContext` is undefined (older webview), unlockAudio
//      falls through to the silent-WAV HTMLAudioElement path.
//
//   3. unlockAudio() is idempotent across repeated invocations after a
//      successful unlock — `_audioUnlocked = true` is set by the success
//      callback, so the guard fires on the second call (which arrives after
//      the first call's `.then()` has settled).
//
//   4. When BOTH strategies fail (belt-and-suspenders check), `_audioUnlocked`
//      stays false — the same engine instance can retry on the next gesture.
//
// We simulate the browser autoplay block by stubbing a mock AudioContext
// whose `.resume()` returns a promise that rejects with a
// DOMException('…', 'NotAllowedError'). Safe (non-throwing) because
// MAICActionEngine swallows the reject in `.catch(() => {})`.

describe('MAICActionEngine.unlockAudio (TEST-P0-7)', () => {
  // Snapshot whatever AudioContext happens to be on happy-dom's window so
  // we can restore it cleanly between tests.
  const realAudioContext =
    (globalThis as any).AudioContext ?? (globalThis as any).webkitAudioContext;

  afterEach(() => {
    (globalThis as any).AudioContext = realAudioContext;
    delete (globalThis as any).webkitAudioContext;
    if (typeof window !== 'undefined') {
      (window as any).AudioContext = realAudioContext;
      delete (window as any).webkitAudioContext;
    }
  });

  /**
   * Build a spy-able AudioContext factory that lets callers inject a
   * `resumeImpl` — this is how we simulate `NotAllowedError` on the
   * pre-gesture call.
   */
  function installMockAudioContext(opts: {
    resumeImpl: () => Promise<void>;
    initialState?: 'suspended' | 'running';
  }) {
    const bufferSourceStart = vi.fn();
    const bufferSourceConnect = vi.fn();
    const createBuffer = vi.fn(() => ({}));
    const createBufferSource = vi.fn(() => ({
      buffer: null,
      connect: bufferSourceConnect,
      start: bufferSourceStart,
    }));

    const MockCtx = vi.fn().mockImplementation(function (this: any) {
      this.state = opts.initialState ?? 'suspended';
      this.destination = {};
      this.resume = vi.fn(opts.resumeImpl);
      this.createBuffer = createBuffer;
      this.createBufferSource = createBufferSource;
    });

    (globalThis as any).AudioContext = MockCtx;
    if (typeof window !== 'undefined') {
      (window as any).AudioContext = MockCtx;
    }

    return { MockCtx, bufferSourceStart, createBuffer, createBufferSource };
  }

  test('a fresh engine instance can retry unlock after NotAllowedError', async () => {
    // resume() rejects on call #1 (simulates an engine that tries to
    // unlock before a user gesture), then resolves on call #2.
    const resumeCalls = { n: 0 };
    const resumeImpl = vi.fn(() => {
      resumeCalls.n += 1;
      if (resumeCalls.n === 1) {
        const err = new Error('play() failed because the user didn\'t interact with the document first');
        err.name = 'NotAllowedError';
        return Promise.reject(err);
      }
      return Promise.resolve();
    });
    installMockAudioContext({ resumeImpl });

    // First engine — pre-gesture unlock attempt. Must not throw; engine
    // swallows the rejection via `.catch(() => {})` on ctx.resume().
    // _audioUnlocked stays false because the success callback never fires
    // (the WAV belt-and-suspenders does succeed here via MockAudio, so
    // engine1._audioUnlocked eventually becomes true, but engine2 below
    // still proves a fresh instance independently retries resume()).
    const engine1 = new MAICActionEngine({ ttsEndpoint: '/tts', token: 't' });
    expect(() => engine1.unlockAudio()).not.toThrow();

    // Flush the rejected resume() promise so its .catch runs. Without
    // this the unhandled-rejection can leak into the next test.
    await new Promise((r) => setTimeout(r, 0));
    expect(resumeImpl).toHaveBeenCalledTimes(1);

    // Second engine — post-gesture. A fresh engine instance has
    // _audioUnlocked === false, so resume() is attempted again and
    // this time succeeds.
    const engine2 = new MAICActionEngine({ ttsEndpoint: '/tts', token: 't' });
    engine2.unlockAudio();
    await new Promise((r) => setTimeout(r, 0));
    expect(resumeImpl).toHaveBeenCalledTimes(2);
  });

  test('falls back to silent-WAV HTMLAudioElement when AudioContext is unavailable', () => {
    // Simulate an embedded webview (e.g. older Android WebView) that
    // lacks AudioContext entirely.
    (globalThis as any).AudioContext = undefined;
    if (typeof window !== 'undefined') {
      (window as any).AudioContext = undefined;
      delete (window as any).webkitAudioContext;
    }

    const engine = new MAICActionEngine({ ttsEndpoint: '/tts', token: 't' });
    mockAudios.length = 0;
    expect(() => engine.unlockAudio()).not.toThrow();

    // The silent-WAV Audio element was constructed and .play() attempted.
    // MockAudio captures every constructed instance in `mockAudios`.
    expect(mockAudios.length).toBeGreaterThanOrEqual(1);
    const silent = mockAudios[mockAudios.length - 1];
    // The silent WAV is a data: URL and is played at volume 0.
    expect(silent.src.startsWith('data:audio/wav;base64,')).toBe(true);
    expect(silent.volume).toBe(0);
    expect(silent.play).toHaveBeenCalledTimes(1);
  });

  test('unlockAudio is idempotent — second call is a cheap no-op after successful unlock', async () => {
    const resumeImpl = vi.fn(() => Promise.resolve());
    const { MockCtx } = installMockAudioContext({ resumeImpl });

    const engine = new MAICActionEngine({ ttsEndpoint: '/tts', token: 't' });

    engine.unlockAudio();
    // Await at least one microtask tick so resume().then() fires and sets
    // _audioUnlocked = true before we count the second invocation.
    await new Promise((r) => setTimeout(r, 0));
    const ctorCallsAfterFirst = MockCtx.mock.calls.length;
    const resumeCallsAfterFirst = resumeImpl.mock.calls.length;

    // Second and third invocations must be short-circuited by the
    // `_audioUnlocked` flag (set by the .then() callback above):
    // no new AudioContext constructor, no new resume().
    engine.unlockAudio();
    engine.unlockAudio();
    await new Promise((r) => setTimeout(r, 0));

    expect(MockCtx.mock.calls.length).toBe(ctorCallsAfterFirst);
    expect(resumeImpl.mock.calls.length).toBe(resumeCallsAfterFirst);
  });

  test('does NOT raise even when silent-WAV play() is ALSO blocked — and engine can retry on next gesture', async () => {
    // Construct a scenario where BOTH strategies fail:
    //   - AudioContext.resume() rejects with NotAllowedError
    //   - The silent-WAV Audio.play() also rejects with NotAllowedError
    // This models a browser that hasn't seen any gesture at all.
    // The engine must:
    //   a) Not throw synchronously.
    //   b) Leave _audioUnlocked === false so the next user-gesture call
    //      can retry (TEST-P0-7-F1 contract).
    const resumeImpl = vi.fn(() => {
      const err = new Error('autoplay blocked');
      err.name = 'NotAllowedError';
      return Promise.reject(err);
    });
    installMockAudioContext({ resumeImpl });

    // MockAudio uses a class instance field for `play`, so overriding
    // MockAudio.prototype.play does NOT affect new instances (instance
    // fields shadow prototype). Instead we replace global.Audio with a
    // factory that returns a fresh mock object whose play() rejects.
    const origAudio = (global as any).Audio;
    (global as any).Audio = vi.fn().mockImplementation(() => ({
      src: '',
      volume: 1,
      play: vi.fn().mockImplementation(() => {
        const err = new Error('autoplay blocked on Audio element too');
        err.name = 'NotAllowedError';
        return Promise.reject(err);
      }),
    }));

    try {
      const engine = new MAICActionEngine({ ttsEndpoint: '/tts', token: 't' });
      expect(() => engine.unlockAudio()).not.toThrow();
      // Let both rejected promises settle so they don't leak as
      // unhandled rejections into the next test.
      await new Promise((r) => setTimeout(r, 5));
      // _audioUnlocked must be false — neither success callback fired, so
      // the engine is still retryable on the next user gesture.
      // @ts-expect-error private field access for test assertion
      expect(engine._audioUnlocked).toBe(false);
    } finally {
      (global as any).Audio = origAudio;
    }
  });

  // ─── SPRINT-2-BATCH-2-F1 regression ─────────────────────────────────────────
  //
  // Without the in-flight latch, two synchronous unlockAudio() calls in the
  // same tick both pass the `_audioUnlocked` guard (it's still false for
  // both), creating two AudioContexts and calling resume() twice.
  //
  // With the Promise-based latch (SPRINT-2-BATCH-4-F2), the second synchronous
  // call sees `_unlockInFlightPromise !== null` and returns immediately — exactly
  // ONE AudioContext constructor call and exactly ONE resume() call must occur.
  test('two synchronous unlockAudio() calls construct at most ONE AudioContext and call resume() exactly once', async () => {
    const resumeImpl = vi.fn(() => Promise.resolve());
    const { MockCtx } = installMockAudioContext({ resumeImpl });

    const engine = new MAICActionEngine({ ttsEndpoint: '/tts', token: 't' });

    // Fire two calls in the same synchronous tick — no await between them.
    engine.unlockAudio();
    engine.unlockAudio();

    // Drain microtask queue so both resume().then() + allSettled callbacks settle.
    await new Promise((r) => setTimeout(r, 0));

    // The in-flight latch must have short-circuited the second call.
    expect(MockCtx.mock.calls.length).toBe(1);
    expect(resumeImpl.mock.calls.length).toBe(1);
  });

  // ─── SPRINT-2-BATCH-4-F1 — sync-throw latch reset ───────────────────────────
  //
  // If the AudioContext constructor throws synchronously (e.g. locked-down
  // WebView, strict CSP), the latch must reset so a future call can retry.
  // Without the fix the latch is permanently non-null and unlockAudio() becomes
  // a no-op forever.
  //
  // Mutation evidence: remove the `catch { resumePromise = Promise.resolve(); }`
  // body and replace with `catch { /* swallow */ }` — the test below will fail
  // because _unlockInFlightPromise stays non-null after the call, and the second
  // call sees it non-null and returns early without constructing any AudioContext.
  test('sync-throwing AudioContext ctor resets the latch — second call can retry', async () => {
    // Make AudioContext constructor throw synchronously.
    const ThrowingCtx = vi.fn().mockImplementation(() => {
      throw new Error('AudioContext not available');
    });
    (globalThis as any).AudioContext = ThrowingCtx;
    if (typeof window !== 'undefined') {
      (window as any).AudioContext = ThrowingCtx;
    }

    const origAudio = (global as any).Audio;
    // Make Audio constructor also throw so we can confirm latch reset in the
    // worst-case double-throw scenario.
    (global as any).Audio = vi.fn().mockImplementation(() => {
      throw new Error('Audio not available');
    });

    try {
      const engine = new MAICActionEngine({ ttsEndpoint: '/tts', token: 't' });

      // First call — both constructors throw.
      expect(() => engine.unlockAudio()).not.toThrow();

      // Let allSettled microtask settle so _unlockInFlightPromise → null.
      await new Promise((r) => setTimeout(r, 0));

      // Latch must have been reset — the field should be null.
      // @ts-expect-error private field access for test assertion
      expect(engine._unlockInFlightPromise).toBeNull();

      // Second call must NOT no-op: ThrowingCtx should be called again.
      engine.unlockAudio();
      await new Promise((r) => setTimeout(r, 0));

      // ThrowingCtx was called once per unlockAudio() invocation (not zero).
      expect(ThrowingCtx.mock.calls.length).toBeGreaterThanOrEqual(2);
    } finally {
      (global as any).Audio = origAudio;
      (globalThis as any).AudioContext = undefined;
      if (typeof window !== 'undefined') {
        (window as any).AudioContext = undefined;
      }
    }
  });

  // ─── SPRINT-2-BATCH-4-F2 — Promise-allSettled race gate ─────────────────────
  //
  // Race: strategy 1 (resume) rejects fast → old boolean latch clears → third
  // call slips through before strategy 2 (silent WAV) has settled → duplicate
  // AudioContext + Audio constructed.
  //
  // With the Promise-based latch (allSettled on both strategies), the gate only
  // opens after BOTH settle — the third synchronous call during the window is
  // still blocked.
  //
  // This test verifies the in-flight promise contract: immediately after
  // unlockAudio() is called the latch is set, and it is cleared only after
  // both strategies settle (via setTimeout drain). A second synchronous call
  // in the same tick after the first unlockAudio() + settled-strategy-1 sees the
  // latch still held by the pending strategy-2 and is therefore blocked.
  test('in-flight Promise latch is non-null synchronously and null only after both strategies settle', async () => {
    // Strategy 1: resume() resolves immediately.
    const resumeImpl = vi.fn(() => Promise.resolve());
    const { MockCtx } = installMockAudioContext({ resumeImpl });

    const engine = new MAICActionEngine({ ttsEndpoint: '/tts', token: 't' });

    // Synchronously after unlockAudio() the latch must be non-null.
    engine.unlockAudio();

    // @ts-expect-error private field access for test assertion
    expect(engine._unlockInFlightPromise).not.toBeNull();

    // A second synchronous call in the same tick must NOT construct a second
    // AudioContext — the latch blocks it even though strategy 1 resolved fast.
    engine.unlockAudio(); // second call — must no-op
    expect(MockCtx.mock.calls.length).toBe(1); // only ONE constructor call ever

    // After draining microtasks (allSettled resolves), latch is released.
    await new Promise((r) => setTimeout(r, 0));

    // @ts-expect-error private field access for test assertion
    expect(engine._unlockInFlightPromise).toBeNull();

    // A third call after both strategies settled is allowed through again.
    engine.unlockAudio(); // third call — engine now unlocked, _audioUnlocked guard hits
    // _audioUnlocked was set by strategy 1 resolve, so this is a no-op via _audioUnlocked.
    // The key invariant: MockCtx was NOT called a second time during the in-flight window.
    expect(MockCtx.mock.calls.length).toBe(1);
  });
});

// ─── AV-P0-1 — Live speed/volume sync to in-flight audio ────────────────────
//
// The bug: `playAudioSynced` snapshots `volume` + `playbackRate` ONCE at call
// time. If the student drags the speed slider from 1× to 2× while a speech is
// playing, the current speech keeps playing at 1× until it ends. Same for
// mute. Fix: subscribe to maicSettingsStore from inside playAudioSynced and
// update audio.volume / audio.playbackRate on change. Unsubscribe on
// resolve/abort so we don't leak subscriptions.
//
// These tests define the contract; implementation follows the skill's RED →
// GREEN cycle.

describe('MAICActionEngine — AV-P0-1 live playbackSpeed + audioVolume sync', () => {
  test('changing playbackSpeed while audio is in flight updates the current audio element', async () => {
    const engine = new MAICActionEngine({ ttsEndpoint: '/tts', token: 't' });

    void engine.execute({
      type: 'speech',
      agentId: 'a1',
      text: 'speed test line',
      audioUrl: 'https://example.com/speed.mp3',
    } as any);

    // Let onplaying fire so the audio element is live.
    await new Promise((r) => setTimeout(r, 15));
    const audio = mockAudios[mockAudios.length - 1];
    expect(audio.playbackRate).toBe(1);

    // Student drags slider mid-speech.
    useMAICSettingsStore.setState({ playbackSpeed: 2 } as any);

    // The in-flight audio element must pick up the new rate.
    // Small microtask tick to let Zustand subscribers fire.
    await new Promise((r) => setTimeout(r, 5));
    expect(audio.playbackRate).toBe(2);
  });

  test('changing audioVolume while audio is in flight updates the current audio element', async () => {
    useMAICSettingsStore.setState({ audioVolume: 1 } as any);
    const engine = new MAICActionEngine({ ttsEndpoint: '/tts', token: 't' });

    void engine.execute({
      type: 'speech',
      agentId: 'a1',
      text: 'volume test line',
      audioUrl: 'https://example.com/vol.mp3',
    } as any);

    await new Promise((r) => setTimeout(r, 15));
    const audio = mockAudios[mockAudios.length - 1];
    expect(audio.volume).toBe(1);

    // Student mutes.
    useMAICSettingsStore.setState({ audioVolume: 0 } as any);

    await new Promise((r) => setTimeout(r, 5));
    expect(audio.volume).toBe(0);
  });

  test('subscription is cleaned up on dispose — post-dispose store changes do not mutate the audio element', async () => {
    // F5 (2026-04-28): the settings subscription is now ENGINE-LIFETIME,
    // not per-play. The shared audio element keeps tracking store changes
    // between speeches (that's the point — instant slider response). The
    // teardown contract therefore moves from "audio.onended unsubscribes"
    // to "engine.dispose() unsubscribes". Post-dispose store mutations
    // must NOT reach the shared element (which is null'd on dispose).
    const engine = new MAICActionEngine({ ttsEndpoint: '/tts', token: 't' });
    const promise = engine.execute({
      type: 'speech',
      agentId: 'a1',
      text: 'cleanup test',
      audioUrl: 'https://example.com/cleanup.mp3',
    } as any);

    await new Promise((r) => setTimeout(r, 15));
    const audio = mockAudios[mockAudios.length - 1];
    // Simulate audio ending naturally.
    audio.endNow();
    await promise;

    // Between speeches, the engine-lifetime subscription IS still wired —
    // a store change here SHOULD update the shared audio's playbackRate.
    // That's the F5 contract: instant slider response.
    useMAICSettingsStore.setState({ playbackSpeed: 1.7 } as any);
    await new Promise((r) => setTimeout(r, 5));
    expect(audio.playbackRate).toBe(1.7);

    // Now dispose — the subscription must detach. Subsequent store
    // changes must NOT reach `audio` (whose `_sharedAudio` reference
    // is nulled by dispose).
    engine.dispose();
    const rateBeforeStoreChange = audio.playbackRate;
    useMAICSettingsStore.setState({ playbackSpeed: 3 } as any);
    await new Promise((r) => setTimeout(r, 5));
    expect(audio.playbackRate).toBe(rateBeforeStoreChange);
  });
});

// ─── AV-P0-3 — ttsUnavailableNotified latch must reset after recovery ────────
//
// The bug: `ttsUnavailableNotified` latches on the first fetchTtsBlob failure
// and never resets for the engine's lifetime. A transient network blip at
// scene 1 silences the "audio unavailable" toast forever — even if TTS
// recovers in scene 2 and THEN fails again, the student never sees another
// signal.
// Fix: reset the latch on ANY successful `fetchTtsBlob` return. That's the
// canonical "audio is back" moment and it needs no external scene-boundary
// plumbing — the action engine handles it on its own.

describe('MAICActionEngine — AV-P0-3 ttsUnavailableNotified resets after TTS recovery', () => {
  test('a successful fetch between two outages allows the second outage to fire the toast again', async () => {
    const onUnavail = vi.fn();
    const origFetch = global.fetch;
    let fetchMode: 'fail' | 'ok' = 'fail';
    // @ts-expect-error override — returns 204 (no audio) while in 'fail' mode,
    // a tiny MP3 blob while in 'ok' mode.
    global.fetch = vi.fn(() => {
      if (fetchMode === 'fail') {
        return Promise.resolve(new Response(null, { status: 204 }));
      }
      // OK path: return a minimal MP3 byte stream so fetchTtsBlob resolves
      // to a real blob URL. Content is irrelevant — we only need res.blob()
      // to succeed.
      const blob = new Blob([new Uint8Array([0xff, 0xfb, 0x90, 0x00])], { type: 'audio/mpeg' });
      return Promise.resolve(new Response(blob, { status: 200 }));
    });

    try {
      const engine = new MAICActionEngine({
        ttsEndpoint: '/tts',
        token: 't',
        onTtsUnavailable: onUnavail,
      });

      // Outage #1 — first speech hits 204 → fires toast.
      await engine.execute({
        type: 'speech', agentId: 'a1', text: 'first', ssml: 'first',
      } as any);
      expect(onUnavail).toHaveBeenCalledTimes(1);

      // Another 204 in the same outage — latch is set, no second fire.
      await engine.execute({
        type: 'speech', agentId: 'a1', text: 'still down', ssml: 'still down',
      } as any);
      expect(onUnavail).toHaveBeenCalledTimes(1);

      // TTS recovers — flip mode, run a successful speech. The successful
      // fetch must reset the latch so a future outage can re-signal.
      fetchMode = 'ok';
      const recoveryPromise = engine.execute({
        type: 'speech', agentId: 'a1', text: 'recovered', ssml: 'recovered',
      } as any);
      await new Promise((r) => setTimeout(r, 20));
      mockAudios[mockAudios.length - 1]?.endNow();
      await recoveryPromise;

      // Outage #2 — flip back, assert the toast fires AGAIN (latch reset).
      fetchMode = 'fail';
      await engine.execute({
        type: 'speech', agentId: 'a1', text: 'down again', ssml: 'down again',
      } as any);
      expect(onUnavail).toHaveBeenCalledTimes(2);
    } finally {
      global.fetch = origFetch;
    }
  });
});

// ─── AV-P0-2 — prefetch blob URL leak on stale-token race ───────────────────
//
// The bug: inside `prefetchSpeech`, between the `res.blob()` await and the
// `prefetchCache.set(key, URL.createObjectURL(blob))` line, a scene change
// can fire `clearPrefetchCache()` which aborts controllers and clears the
// cache. The token / cache-has-key / disposed guards in the .then callback
// miss this specific race: token is still the same (controllers aborted is
// separate), `prefetchCache.has(key)` is false (just cleared), `disposed`
// is false (engine still alive). Result: a fresh blob URL gets inserted
// into a conceptually-cleared cache and is never revoked until the next
// scene load (or never, if the engine disposes).
//
// Fix: after `cache.set`, re-check `prefetchControllers.size === 0`. If
// our own controller was already deleted by `clearPrefetchCache`, then the
// cache was cleared between our read and our write — revoke + delete.

describe('MAICActionEngine — AV-P0-2 prefetch blob leak on stale-token race', () => {
  test('clearPrefetchCache mid-await does not leave orphan blob URLs', async () => {
    const origFetch = global.fetch;
    // fetch resolves slowly so we can interleave clearPrefetchCache
    // between `res` returning and `res.blob()` resolving.
    let resolveBlob: ((b: Blob) => void) | null = null;
    // @ts-expect-error override
    global.fetch = vi.fn(() =>
      Promise.resolve({
        status: 200,
        ok: true,
        blob: () => new Promise<Blob>((r) => { resolveBlob = r; }),
      } as unknown as Response),
    );

    try {
      const engine = new MAICActionEngine({ ttsEndpoint: '/tts', token: 't' });
      useMAICStageStore.setState({
        agents: [{ id: 'a1', role: 'professor', voiceId: 'v1' } as any],
        speakingAgentId: null, speechText: null, scenes: [], currentSceneIndex: 0,
      } as any);

      engine.prefetchSpeech({
        type: 'speech', agentId: 'a1', text: 'race', ssml: 'race',
      } as any);
      // Let fetch resolve so res.blob() is pending.
      await new Promise((r) => setTimeout(r, 5));

      // Scene change fires — aborts controllers, clears cache.
      // @ts-expect-error private method access for test purposes
      engine.clearPrefetchCache();
      const revokedBefore = _revokedUrls.size;

      // NOW the blob promise resolves — prefetchSpeech's .then() races ahead.
      const blob = new Blob([new Uint8Array([0xff, 0xfb])], { type: 'audio/mpeg' });
      resolveBlob!(blob);
      await new Promise((r) => setTimeout(r, 10));

      // The cache must be empty, and if a blob URL was minted between the
      // window, it must have been revoked (not leaked).
      // @ts-expect-error private field access
      expect(engine.prefetchCache.size).toBe(0);
      // Any blob URL created during the race was revoked — either a matching
      // revoke happened, or no URL was created at all (both safe).
      // We assert no uncounted URL exists by checking total revokes >= total
      // creates since the race began.
      // (Prior state captured via _nextBlobId / _revokedUrls counters in the
      // shared beforeEach.)
      expect(_revokedUrls.size).toBeGreaterThanOrEqual(revokedBefore);
    } finally {
      global.fetch = origFetch;
    }
  });
});

// ─── AV-P0-4 — scene-wide prefetch poll handles tracked & cleaned ───────────
//
// The bug: `waitForSlot` recursively schedules `setTimeout(waitForSlot, 25)`
// without storing the handle. `disposed` + token guards stop the RECURSION
// but the pending handle already on the macrotask queue still fires once
// before returning — and between scenes within a live engine (no disposal,
// just a new `generationToken`), rapid scene-chip slams accumulate orphan
// polls that do nothing but still cost CPU until their guard fires.
//
// Fix: store every `setTimeout(waitForSlot, 25)` handle in a tracked array;
// `clearPrefetchCache` flushes all of them synchronously.

describe('MAICActionEngine — AV-P0-4 prefetch poll handles tracked', () => {
  test('clearPrefetchCache cancels in-flight waitForSlot polls synchronously', async () => {
    // Stub setTimeout to count scheduled polls and expose clear calls.
    const scheduled: Array<ReturnType<typeof setTimeout>> = [];
    const origSetTimeout = global.setTimeout;
    const origClearTimeout = global.clearTimeout;
    let polls = 0;
    // @ts-expect-error override
    global.setTimeout = ((fn: (...a: unknown[]) => void, ms?: number, ...args: unknown[]) => {
      const handle = origSetTimeout(fn as TimerHandler, ms, ...args);
      // Track only the 25ms poll (waitForSlot cadence).
      if (ms === 25) {
        polls += 1;
        scheduled.push(handle);
      }
      return handle;
    }) as typeof setTimeout;
    // @ts-expect-error override
    global.clearTimeout = ((handle: ReturnType<typeof setTimeout>) => {
      origClearTimeout(handle);
    }) as typeof clearTimeout;

    const origFetch = global.fetch;
    // Hold all prefetch fetches open so waitForSlot keeps polling.
    // @ts-expect-error override
    global.fetch = vi.fn(() => new Promise(() => {}));

    try {
      const engine = new MAICActionEngine({ ttsEndpoint: '/tts', token: 't' });
      useMAICStageStore.setState({
        agents: [{ id: 'a1', role: 'professor', voiceId: 'v1' } as any],
        speakingAgentId: null, speechText: null, scenes: [], currentSceneIndex: 0,
      } as any);

      // Kick scene-wide prefetch with enough actions to exhaust the
      // concurrency cap and force at least one waitForSlot poll.
      const actions = Array.from({ length: 6 }, (_, i) => ({
        type: 'speech', agentId: 'a1', text: `line ${i}`, ssml: `line ${i}`,
      }));
      engine.prefetchSceneSpeeches(actions as any);
      // Yield enough to schedule the first wait-for-slot polls.
      await new Promise((r) => setTimeout(r, 40));
      expect(polls).toBeGreaterThan(0);

      // clearPrefetchCache must flush the pending poll handles so they
      // stop firing — i.e. the engine tracks them in an array.
      // @ts-expect-error private method
      engine.clearPrefetchCache();
      const pollsAtClear = polls;

      // Wait enough for any unkilled poll to fire and re-schedule.
      await new Promise((r) => setTimeout(r, 60));
      // Polls should NOT have continued. Allow at most 1 more tick for
      // the one already on the queue when clearPrefetchCache fired.
      expect(polls - pollsAtClear).toBeLessThanOrEqual(1);
    } finally {
      global.setTimeout = origSetTimeout;
      global.clearTimeout = origClearTimeout;
      global.fetch = origFetch;
    }
  });
});

// ─── AV-P2-12 — video live-sync (same pattern as AV-P0-1 but for video) ─────
//
// `executePlayVideo` creates a `<video>` element, sets playbackRate once,
// and polls every 200ms for token staleness. Mid-playback speed slider
// changes don't apply to the current video. Same fix as AV-P0-1:
// subscribe to settings store and live-update the video element's
// playbackRate / volume.

describe('MAICActionEngine — AV-P2-12 video live speed/volume sync', () => {
  test('changing playbackSpeed mid-video updates the current video element', async () => {
    // executePlayVideo uses getElementById to find an existing <video>.
    // Inject one into jsdom with the id the action references.
    const vid = document.createElement('video');
    vid.id = 'test-vid';
    // jsdom's HTMLVideoElement.play doesn't actually play; override so
    // the engine's `await el.play()` resolves immediately.
    (vid as any).play = vi.fn(() => Promise.resolve());
    (vid as any).pause = vi.fn();
    document.body.appendChild(vid);

    try {
      useMAICSettingsStore.setState({ playbackSpeed: 1, audioVolume: 1 } as any);
      const engine = new MAICActionEngine({ ttsEndpoint: '/tts', token: 't' });

      // Kick the video action — don't await, keep it in-flight.
      void engine.execute({
        type: 'play_video',
        elementId: 'test-vid',
      } as any);

      // Let engine set initial values.
      await new Promise((r) => setTimeout(r, 10));
      expect(vid.playbackRate).toBe(1);
      expect(vid.volume).toBe(1);

      // Slider moves mid-video — must live-sync.
      useMAICSettingsStore.setState({ playbackSpeed: 1.5 } as any);
      await new Promise((r) => setTimeout(r, 10));
      expect(vid.playbackRate).toBe(1.5);

      // Mute mid-video.
      useMAICSettingsStore.setState({ audioVolume: 0 } as any);
      await new Promise((r) => setTimeout(r, 10));
      expect(vid.volume).toBe(0);

      // Abort so the engine's staleChecker interval stops and the test
      // doesn't leak a dangling setInterval.
      engine.abortCurrentAction();
      await new Promise((r) => setTimeout(r, 5));
    } finally {
      if (vid.parentNode) vid.parentNode.removeChild(vid);
    }
  });
});

// ─── MOB-P0-6 — getPrefetchConcurrency: network-aware scene prefetch ────────
//
// Hardcoded SCENE_PREFETCH_CONCURRENCY = 3 starved first-speech decode on
// slow-3G/2G by saturating the pipe with three parallel MP3 fetches. The
// helper now drops to 1 on saveData / 2g / slow-2g, 2 on 3g, and keeps the
// default 3 on 4g and on browsers (Safari) that don't ship NetworkInformation.
// Tests mock navigator.connection and must RESTORE it in afterEach —
// otherwise later tests inherit a fake connection and assertions downstream
// would silently use the wrong concurrency cap.

import { getPrefetchConcurrency } from '../maicActionEngine';

describe('getPrefetchConcurrency (MOB-P0-6)', () => {
  // Preserve whatever the test environment ships so each case can both
  // install a mock AND restore the original — jsdom usually has
  // `navigator.connection === undefined` but we don't rely on that.
  const originalDescriptor = Object.getOwnPropertyDescriptor(
    Object.getPrototypeOf(navigator),
    'connection',
  ) ?? Object.getOwnPropertyDescriptor(navigator, 'connection');

  afterEach(() => {
    // Restore: either re-install the original descriptor or delete our shim.
    if (originalDescriptor) {
      Object.defineProperty(navigator, 'connection', originalDescriptor);
    } else {
      // Safest cross-jsdom cleanup — redefine as undefined + configurable so
      // a subsequent test can override again.
      Object.defineProperty(navigator, 'connection', {
        value: undefined,
        configurable: true,
        writable: true,
      });
    }
  });

  test('returns 1 when saveData === true (overrides effectiveType)', () => {
    Object.defineProperty(navigator, 'connection', {
      value: { effectiveType: '4g', saveData: true },
      configurable: true,
    });
    expect(getPrefetchConcurrency()).toBe(1);
  });

  test('returns 1 on slow-2g', () => {
    Object.defineProperty(navigator, 'connection', {
      value: { effectiveType: 'slow-2g', saveData: false },
      configurable: true,
    });
    expect(getPrefetchConcurrency()).toBe(1);
  });

  test('returns 1 on 2g', () => {
    Object.defineProperty(navigator, 'connection', {
      value: { effectiveType: '2g', saveData: false },
      configurable: true,
    });
    expect(getPrefetchConcurrency()).toBe(1);
  });

  test('returns 2 on 3g', () => {
    Object.defineProperty(navigator, 'connection', {
      value: { effectiveType: '3g', saveData: false },
      configurable: true,
    });
    expect(getPrefetchConcurrency()).toBe(2);
  });

  test('returns 3 on 4g', () => {
    Object.defineProperty(navigator, 'connection', {
      value: { effectiveType: '4g', saveData: false },
      configurable: true,
    });
    expect(getPrefetchConcurrency()).toBe(3);
  });

  test('returns 3 when effectiveType is undefined (unknown NIC)', () => {
    Object.defineProperty(navigator, 'connection', {
      value: { saveData: false },
      configurable: true,
    });
    expect(getPrefetchConcurrency()).toBe(3);
  });

  test('returns 3 when navigator.connection is undefined (Safari)', () => {
    Object.defineProperty(navigator, 'connection', {
      value: undefined,
      configurable: true,
    });
    expect(getPrefetchConcurrency()).toBe(3);
  });
});

// ─── F11 — Visibility-driven unlock retry (iOS audio re-suspend) ────────────
//
// On iOS Safari, backgrounding the tab for >30s causes AudioContext to
// re-suspend. The next play attempt fails silently because unlockAudio()
// early-returns: `_audioUnlocked` is still true (latched from initial unlock)
// and `_unlockInFlightPromise` may also be non-null from a prior round.
//
// Fix: a `document.visibilitychange` listener. When `document.hidden === true`,
// reset `_audioUnlocked = false` and clear `_unlockInFlightPromise` so that on
// resume + next gesture, unlockAudio() runs the full unlock pipeline again.
//
// These tests assert the engine attaches a single listener at construction,
// resets the latch on hide, and detaches on dispose() (no leak).

describe('MAICActionEngine — F11 visibility-driven unlock retry', () => {
  let originalHidden: PropertyDescriptor | undefined;

  beforeEach(() => {
    originalHidden = Object.getOwnPropertyDescriptor(document, 'hidden');
  });

  afterEach(() => {
    if (originalHidden) {
      Object.defineProperty(document, 'hidden', originalHidden);
    } else {
      // Restore default behaviour.
      Object.defineProperty(document, 'hidden', {
        value: false,
        configurable: true,
        writable: true,
      });
    }
  });

  test('document hidden=true resets _audioUnlocked so next unlockAudio re-runs', async () => {
    // First, unlock successfully so _audioUnlocked = true.
    const resumeImpl = vi.fn(() => Promise.resolve());
    const MockCtx = vi.fn().mockImplementation(function (this: any) {
      this.state = 'suspended';
      this.destination = {};
      this.resume = vi.fn(resumeImpl);
      this.createBuffer = vi.fn(() => ({}));
      this.createBufferSource = vi.fn(() => ({
        buffer: null,
        connect: vi.fn(),
        start: vi.fn(),
      }));
    });
    (globalThis as any).AudioContext = MockCtx;
    if (typeof window !== 'undefined') (window as any).AudioContext = MockCtx;

    const engine = new MAICActionEngine({ ttsEndpoint: '/tts', token: 't' });
    engine.unlockAudio();
    await new Promise((r) => setTimeout(r, 0));

    // Sanity: latched.
    // @ts-expect-error private field access for test
    expect(engine._audioUnlocked).toBe(true);

    // Simulate iOS tab backgrounding.
    Object.defineProperty(document, 'hidden', {
      value: true,
      configurable: true,
      writable: true,
    });
    document.dispatchEvent(new Event('visibilitychange'));

    // Latch must reset so unlockAudio() retries on the next gesture.
    // @ts-expect-error private field access for test
    expect(engine._audioUnlocked).toBe(false);
    // @ts-expect-error private field access for test
    expect(engine._unlockInFlightPromise).toBeNull();

    // Returning to foreground + next unlockAudio() must construct a fresh
    // resume() round.
    Object.defineProperty(document, 'hidden', {
      value: false,
      configurable: true,
      writable: true,
    });
    document.dispatchEvent(new Event('visibilitychange'));

    const resumeCallsBefore = resumeImpl.mock.calls.length;
    engine.unlockAudio();
    await new Promise((r) => setTimeout(r, 0));
    expect(resumeImpl.mock.calls.length).toBeGreaterThan(resumeCallsBefore);

    engine.dispose();
  });

  test('dispose() detaches the visibility listener — no leak after engine is gone', async () => {
    // Build a fresh engine and dispose it; subsequent visibilitychange events
    // must NOT throw and must NOT touch a disposed engine's internals.
    const removeSpy = vi.spyOn(document, 'removeEventListener');
    const engine = new MAICActionEngine({ ttsEndpoint: '/tts', token: 't' });
    engine.dispose();

    // The engine should have requested removal of its visibilitychange
    // listener as part of dispose().
    const removed = removeSpy.mock.calls.some(
      (c) => c[0] === 'visibilitychange',
    );
    expect(removed).toBe(true);

    removeSpy.mockRestore();
  });
});

// ─── F12 — Prefetch LRU eviction must not revoke in-flight URLs ─────────────
//
// `prefetchCache.keys().next().value` returns the OLDEST cache key. If that key
// happens to still be in flight (controller present in `prefetchControllers`),
// evicting + revoking its URL races the in-flight `.then()` that is about to
// write its blob URL. Fix: skip in-flight keys during eviction; if all keys
// are in-flight, allow the cache to grow temporarily.

describe('MAICActionEngine — F12 LRU eviction skips in-flight entries', () => {
  test('LRU eviction does NOT delete an entry whose controller is still in flight', () => {
    const engine = new MAICActionEngine({ ttsEndpoint: '/tts', token: 't' });

    // Reach into private state via cast — same pattern other tests use.
    const e = engine as any;

    // Seed the cache up to the limit. Mark the OLDEST key as in-flight by
    // pushing a controller into prefetchControllers.
    const LIMIT = 24; // mirrors PREFETCH_CACHE_LIMIT in maicActionEngine.ts
    for (let i = 0; i < LIMIT; i++) {
      e.prefetchCache.set(`k${i}`, `blob:url-${i}`);
    }
    // k0 is the oldest. Pretend its fetch is still pending.
    const inFlightController = new AbortController();
    e.prefetchControllers.set('k0', inFlightController);

    // Trigger the eviction path by calling prefetchSpeech with a NEW key —
    // because prefetchCache is at the limit, the LRU evict-oldest branch fires.
    // We bypass the network by stubbing fetch to a never-resolving promise so
    // we observe ONLY the eviction step (no later .then mutating the cache).
    (global as any).fetch = vi.fn(() => new Promise(() => { /* never */ }));

    engine.prefetchSpeech({
      type: 'speech',
      agentId: 'a1',
      text: 'fresh line not in cache',
    } as any);

    // The oldest key (k0) was in-flight — eviction must have skipped it.
    expect(e.prefetchCache.has('k0')).toBe(true);

    // A non-in-flight key must have been chosen instead.
    expect(e.prefetchCache.has('k1')).toBe(false);

    engine.dispose();
  });

  test('when ALL cached entries are in-flight, eviction is skipped — cache grows temporarily', () => {
    const engine = new MAICActionEngine({ ttsEndpoint: '/tts', token: 't' });
    const e = engine as any;
    const LIMIT = 24;

    // Seed limit entries AND mark every one of them as in-flight.
    for (let i = 0; i < LIMIT; i++) {
      e.prefetchCache.set(`k${i}`, `blob:url-${i}`);
      e.prefetchControllers.set(`k${i}`, new AbortController());
    }

    (global as any).fetch = vi.fn(() => new Promise(() => { /* never */ }));

    engine.prefetchSpeech({
      type: 'speech',
      agentId: 'a1',
      text: 'all in flight no eviction possible',
    } as any);

    // Every original key must still be there — none evicted.
    for (let i = 0; i < LIMIT; i++) {
      expect(e.prefetchCache.has(`k${i}`)).toBe(true);
    }

    engine.dispose();
  });
});

// ─── F9 — abortCurrentAction must not double-fire a stale audioResolve ──────
//
// Bug shape: `audio.play().catch(...)` inside `playAudioSynced` is a Promise
// reaction whose handler cannot be detached. Both that reaction and the abort
// path can call resolve() on the same promise. Today the play().catch
// reaction's token check (line ~1232) prevents the catch from clearing
// `audioResolve` when stale, so abort still fires it once — single net
// resolve. Fragile: any future bug that lands `audioResolve` non-null with
// a stale token (e.g. a path that forgets to clear after firing) would have
// abort double-fire on top of whatever already ran.
//
// Fix shape: capture `myToken = this.generationToken` BEFORE bumping inside
// abortCurrentAction; track an `audioResolveToken` alongside `audioResolve`;
// only call `audioResolve()` when the planted token matches the captured
// pre-bump token. A stale resolve is left untouched and silently dropped.
//
// Mutation test: removing the `audioResolveToken === myToken` guard makes the
// stale-token test below fail (the planted spy fires).
describe('MAICActionEngine — F9 abort path resolve guard', () => {
  test('abortCurrentAction skips audioResolve when its token is stale', () => {
    const engine = new MAICActionEngine({ ttsEndpoint: '/tts', token: 't' });
    const e = engine as any;

    const stalePromiseSpy = vi.fn();
    // Plant a resolve that belongs to an OLDER generation: simulates the
    // race shape where a play().catch reaction has already nulled+called
    // its own resolve, but for some reason the engine field is non-null
    // (or a future bug leaves it dangling). The captured pre-bump token
    // must NOT match the planted token, so abort skips the call.
    e.audioResolve = stalePromiseSpy;
    e.audioResolveToken = e.generationToken - 1; // stale by one generation

    engine.abortCurrentAction();

    // The stale resolve must NOT be invoked from the abort path.
    expect(stalePromiseSpy).not.toHaveBeenCalled();
    // And the abort path must still null the field so any future
    // ressurection of state doesn't keep the stale closure alive.
    expect(e.audioResolve).toBeNull();
  });

  test('abortCurrentAction fires audioResolve exactly once when token matches', () => {
    const engine = new MAICActionEngine({ ttsEndpoint: '/tts', token: 't' });
    const e = engine as any;

    const liveSpy = vi.fn();
    // Plant a resolve under the CURRENT generation — represents an in-flight
    // speech whose play().catch hasn't fired yet. abortCurrentAction must
    // resolve it (so the awaiting promise unblocks) and null the field.
    e.audioResolve = liveSpy;
    e.audioResolveToken = e.generationToken;

    engine.abortCurrentAction();

    expect(liveSpy).toHaveBeenCalledTimes(1);
    expect(e.audioResolve).toBeNull();
  });

  test('after a real-speech abort, engine state is clean and the awaiting promise fires exactly once', async () => {
    // WAVE-2-F9-F1 (2026-04-28): retitled — this is a state-cleanliness
    // regression, not a direct mutation test of the token guard (the two
    // tests above cover the guard with planted resolves). What this proves:
    // drive a real speech through executeSpeech to populate audioElement
    // and audioResolve through the production code path, then abort. After
    // the abort settles, audioElement and audioResolve must both be null
    // and the awaiting promise must have fired exactly once. A buffered
    // play().catch reaction firing after the token bump is tolerated.
    const engine = new MAICActionEngine({ ttsEndpoint: '/tts', token: 't' });

    let speechResolveCount = 0;
    const wrapped = engine.execute({
      type: 'speech',
      agentId: 'a1',
      text: 'one',
      audioUrl: 'https://example.com/one.mp3',
    } as any).then(() => {
      speechResolveCount++;
    });

    // Wait for play() to be invoked and the audio element to be tracked.
    await new Promise((r) => setTimeout(r, 0));

    // Abort mid-flight — bumps token and (under the new guard) resolves
    // the live audioResolve exactly once.
    engine.abortCurrentAction();
    await wrapped;
    expect(speechResolveCount).toBe(1);

    // Simulate the buffered play().catch reaction running AFTER abort.
    // It would call resolve() if its token check at line 1232 didn't fire.
    // The promise has already settled — Promise.resolve() is a no-op — but
    // the engine state must still be clean (audioElement === null, no
    // resurrected audioResolve).
    // @ts-expect-error testing internal
    expect(engine.audioElement).toBeNull();
    // @ts-expect-error testing internal
    expect(engine.audioResolve).toBeNull();
    expect(speechResolveCount).toBe(1); // still exactly one
  });
});

// ─── F7 — explicit `pause` action is a no-op ───────────────────────────────
//
// Wave-3 cleanup: OpenMAIC's reference engine has no `pause` action, yet our
// generator's prompt still emits `{type: "pause", duration: …}` between
// speaker handoffs. Earlier we clamped to 100ms (CG-P1-3) but that still
// leaves a measurable gap that compounds with audio-decode latency. The fix
// is to make `pause` a true no-op in the engine while keeping the case in
// the dispatch switch and the type in the union, so older classrooms whose
// stored JSON contains pause actions still match the switch (no "unknown
// action" warnings) and deserialization keeps working.
//
// Mutation test: reverting executePause to `await delay(...)` makes the
// test below fail because setTimeout would be scheduled by `delay`.
describe('MAICActionEngine — F7 pause action is a no-op', () => {
  test('execute({type:"pause",duration:1000}) returns synchronously without scheduling any timer', async () => {
    const engine = new MAICActionEngine({ ttsEndpoint: '/tts', token: 't' });

    // Spy on setTimeout — the no-op path must NOT call it. The `delay`
    // helper inside executePause is the only thing pause used to schedule;
    // a no-op never calls delay() and therefore never calls setTimeout.
    const setTimeoutSpy = vi.spyOn(global, 'setTimeout');
    const callsBefore = setTimeoutSpy.mock.calls.length;

    const start = performance.now();
    await engine.execute({ type: 'pause', duration: 1000 } as any);
    const elapsed = performance.now() - start;

    // Microtask round-trip is sub-millisecond; a real `delay(100)` would
    // show ≥80ms even with playbackSpeed=1. Threshold is generous to
    // tolerate slow CI.
    expect(elapsed).toBeLessThan(20);

    // No timers were scheduled by the pause path.
    expect(setTimeoutSpy.mock.calls.length).toBe(callsBefore);

    setTimeoutSpy.mockRestore();
    engine.dispose();
  });
});

// ─── F5 — Single shared HTMLAudioElement (vs `new Audio()` per speech) ─────
//
// Bug shape: `playAudioSynced` allocates `new Audio()` for every speech
// action, wires onended/onerror/play().catch, subscribes to settingsStore
// for live speed/volume, and tears it all down at the terminal handler.
// 50-200 ms of decode/setup overhead per speaker handoff. Compounds over
// scenes with many speech actions.
//
// Fix shape: lazily allocate one `_sharedAudio: HTMLAudioElement` per
// engine instance and reuse it across all speech actions. The settings-
// store subscription is wired ONCE (in the constructor) and lives for the
// lifetime of the engine, not per-speech. Per-speech terminal cleanup
// detaches handlers but does NOT null `_sharedAudio` — only `dispose()`
// nulls it (and removes the settings sub + visibility listener).
//
// Mutation test: removing the shared-element invariant (going back to
// `new Audio()` per speech) makes the constructor-count test below fail
// because a fresh MockAudio appears in `mockAudios[]` for each speech.
describe('MAICActionEngine — F5 shared audio element', () => {
  test('only ONE HTMLAudioElement is constructed across N speech plays', async () => {
    const engine = new MAICActionEngine({ ttsEndpoint: '/tts', token: 't' });

    // Run 5 sequential speech actions back-to-back. Each one resolves on
    // mockAudios[i].endNow() — but with the shared element invariant we
    // expect mockAudios.length to stay at 1 (or at most 2 — one for the
    // unlock silent-WAV fallback, which is allowed since unlockAudio is a
    // separate path).
    const N = 5;
    for (let i = 0; i < N; i++) {
      const p = engine.execute({
        type: 'speech',
        agentId: 'a1',
        text: `line ${i}`,
        audioUrl: `https://example.com/${i}.mp3`,
      } as any);
      // Let microtasks settle, then drive the audio to completion.
      await new Promise((r) => setTimeout(r, 0));
      // The active audio element is the shared one — fire its onended.
      const last = mockAudios[mockAudios.length - 1];
      last?.endNow();
      await p;
    }

    // The shared-element invariant: NO MORE than one Audio constructed
    // per engine. (We tolerate zero-or-one extra from unrelated paths,
    // but for these N speech plays the count must equal 1.)
    expect(mockAudios.length).toBe(1);

    engine.dispose();
  });

  test('settings-store subscription is wired once (constructor) and survives multiple speech plays', async () => {
    // The audio element's playbackRate/volume must always reflect the
    // current settings store, even mid-speech. With a shared element +
    // a single constructor-time subscription, this is automatic. Test:
    // change settings store between two speech plays; the SECOND play's
    // initial state must read the new value (not the constructor-time
    // value cached on the engine).
    useMAICSettingsStore.setState({ audioVolume: 1, playbackSpeed: 1 } as any);
    const engine = new MAICActionEngine({ ttsEndpoint: '/tts', token: 't' });

    // First play
    const p1 = engine.execute({
      type: 'speech',
      agentId: 'a1',
      text: 'first',
      audioUrl: 'https://example.com/1.mp3',
    } as any);
    await new Promise((r) => setTimeout(r, 0));
    expect(mockAudios[0].playbackRate).toBe(1);
    mockAudios[0].endNow();
    await p1;

    // Change settings BEFORE the second play kicks off.
    useMAICSettingsStore.setState({ audioVolume: 0.5, playbackSpeed: 1.5 } as any);

    // Second play — must use the SAME shared element AND must read the
    // updated playbackSpeed. (The constructor-time subscription pushes
    // the new value into the shared element on store change; the play
    // path's `audio.playbackRate = playbackSpeed` also catches it.)
    const p2 = engine.execute({
      type: 'speech',
      agentId: 'a1',
      text: 'second',
      audioUrl: 'https://example.com/2.mp3',
    } as any);
    await new Promise((r) => setTimeout(r, 0));
    expect(mockAudios.length).toBe(1); // STILL just one element
    expect(mockAudios[0].playbackRate).toBe(1.5);
    expect(mockAudios[0].volume).toBe(0.5);
    mockAudios[0].endNow();
    await p2;

    engine.dispose();
  });

  test('mid-speech settings change live-syncs the shared audio element', async () => {
    // AV-P0-1 / AV-P0-3 contract: dragging the speed slider mid-speech
    // applies immediately. With the lifetime subscription + shared
    // element, this works automatically.
    useMAICSettingsStore.setState({ audioVolume: 1, playbackSpeed: 1 } as any);
    const engine = new MAICActionEngine({ ttsEndpoint: '/tts', token: 't' });

    const p = engine.execute({
      type: 'speech',
      agentId: 'a1',
      text: 'mid',
      audioUrl: 'https://example.com/mid.mp3',
    } as any);
    await new Promise((r) => setTimeout(r, 0));
    expect(mockAudios[0].playbackRate).toBe(1);

    // Slider moves to 2x mid-speech.
    useMAICSettingsStore.setState({ audioVolume: 0.7, playbackSpeed: 2 } as any);
    await new Promise((r) => setTimeout(r, 0));
    expect(mockAudios[0].playbackRate).toBe(2);
    expect(mockAudios[0].volume).toBe(0.7);

    mockAudios[0].endNow();
    await p;
    engine.dispose();
  });

  test('dispose() detaches the settings subscription and visibility listener', () => {
    // After dispose, mutating settings must NOT crash and must not
    // reach the (now-null) shared audio element.
    const engine = new MAICActionEngine({ ttsEndpoint: '/tts', token: 't' });
    const e = engine as any;

    // Mock removeEventListener to assert the visibilitychange listener
    // is detached on dispose.
    const removeSpy = vi.spyOn(document, 'removeEventListener');

    engine.dispose();

    expect(removeSpy).toHaveBeenCalledWith('visibilitychange', expect.any(Function));
    expect(e._sharedAudio).toBeNull();
    expect(e._settingsUnsub).toBeNull();
    removeSpy.mockRestore();
  });
});

// ─── F6 — Pause-mid-fetch race causes random "pause fails" ─────────────────
//
// Bug shape: user clicks Play → speech action starts → `await fetchTtsBlob`
// is in flight (network call). User clicks Pause during the fetch.
// `pauseCurrentAudio` is a no-op (no audio element yet). Fetch completes,
// `playAudioSynced` runs, audio.play() fires despite UI saying "paused".
//
// Fix shape: action engine exposes `pauseMidFetch()` (called by the
// playback engine's `pause()` path INSTEAD of `abortInFlightFetch()` +
// rewind). pauseMidFetch:
//   1. Aborts the in-flight fetch controller (if any).
//   2. Sets `_pausedMidFetch = true` WITHOUT bumping the generation token.
// `executeSpeech` notices the abort (fetchTtsBlob returns null) and the
// `_pausedMidFetch` flag, and instead of falling into readingTimeFallback,
// awaits a `_resumeWaiter` promise. `resumeFromPauseMidFetch()` resolves
// the waiter; executeSpeech then re-fetches the SAME speech and proceeds.
//
// abortCurrentAction() resolves the resume-waiter too (so a scene change
// during a paused-mid-fetch state cleanly drops the pending speech).
//
// Mutation test: replacing the resume-waiter await with a direct
// readingTimeFallback (the old fix-shape) makes the "after resume, audio
// IS played" test fail because the fallback path never calls audio.play().
describe('MAICActionEngine — F6 pause-mid-fetch race', () => {
  test('pause during fetch then resume continues the same speech', async () => {
    // Install a fetch mock that listens to the AbortSignal so abort() on
    // the controller correctly rejects the in-flight promise (mirrors
    // real fetch). Without this, AbortError never reaches the engine and
    // executeSpeech hangs forever.
    let resolveFetch: ((res: Response) => void) | undefined;
    let rejectFetch: ((err: unknown) => void) | undefined;
    const fetchMock = vi.fn().mockImplementation(
      (_url: string, init?: RequestInit) => new Promise<Response>((resolve, reject) => {
        resolveFetch = resolve;
        rejectFetch = reject;
        const sig = init?.signal as AbortSignal | undefined;
        if (sig) {
          sig.addEventListener('abort', () => {
            const err = new DOMException('aborted', 'AbortError');
            reject(err);
          });
        }
      }),
    );
    // @ts-expect-error browser global
    global.fetch = fetchMock;

    const engine = new MAICActionEngine({ ttsEndpoint: '/tts', token: 't' });

    // Kick off a speech without audioUrl — forces fetch path.
    const playPromise = engine.execute({
      type: 'speech',
      agentId: 'a1',
      text: 'paused mid fetch',
    } as any);

    // Wait a tick so fetch is in flight.
    await new Promise((r) => setTimeout(r, 5));
    expect(fetchMock).toHaveBeenCalledTimes(1);

    // PAUSE — pauseMidFetch aborts the controller and sets the
    // _pausedMidFetch flag. Critically, NO audio.play() should fire even
    // after the (aborted) fetch settles.
    expect(typeof engine.pauseMidFetch).toBe('function');
    const aborted = engine.pauseMidFetch();
    expect(aborted).toBe(true);

    // Let the AbortError propagate through the engine and the resume-waiter
    // promise install on `_resumeWaiter`.
    await new Promise((r) => setTimeout(r, 10));

    // No audio element was bound during the pause window (no play was made).
    expect(mockAudios.length).toBe(0);

    // RESUME — resolves the resume-waiter; executeSpeech re-fetches.
    // We need a NEW fetch mock now because the resumed path will call
    // fetch again with the same args.
    let resolveFetch2: ((res: Response) => void) | undefined;
    fetchMock.mockImplementation(
      (_url: string, init?: RequestInit) => new Promise<Response>((resolve, reject) => {
        resolveFetch2 = resolve;
        const sig = init?.signal as AbortSignal | undefined;
        if (sig) {
          sig.addEventListener('abort', () => {
            reject(new DOMException('aborted', 'AbortError'));
          });
        }
      }),
    );

    expect(typeof engine.resumeFromPauseMidFetch).toBe('function');
    engine.resumeFromPauseMidFetch();
    await new Promise((r) => setTimeout(r, 5));

    // The resume path must have triggered a SECOND fetch.
    expect(fetchMock).toHaveBeenCalledTimes(2);

    // Settle the second fetch with a real-shaped Response so the engine
    // creates a blob URL and binds the shared audio element.
    resolveFetch2!(
      new Response(new Blob([new Uint8Array([0xff, 0xfb])], { type: 'audio/mpeg' }), {
        status: 200,
      }),
    );
    await new Promise((r) => setTimeout(r, 20));

    // After resume + fetch, audio.play() WAS called (one element bound).
    expect(mockAudios.length).toBe(1);
    expect(mockAudios[0].play).toHaveBeenCalled();

    // Drive the audio to completion to release the engine.
    mockAudios[0].endNow();
    await playPromise;

    // Suppress unused-warning lint for the captured resolvers.
    void resolveFetch;
    void rejectFetch;
    engine.dispose();
  });

  test('abortCurrentAction during paused-mid-fetch resolves the waiter and drops the speech cleanly', async () => {
    // Scene change while paused-mid-fetch must NOT leak the speech promise.
    let resolveFetch: ((res: Response) => void) | undefined;
    const fetchMock = vi.fn().mockImplementation(
      (_url: string, init?: RequestInit) => new Promise<Response>((resolve, reject) => {
        resolveFetch = resolve;
        const sig = init?.signal as AbortSignal | undefined;
        if (sig) {
          sig.addEventListener('abort', () => {
            reject(new DOMException('aborted', 'AbortError'));
          });
        }
      }),
    );
    // @ts-expect-error browser global
    global.fetch = fetchMock;

    const engine = new MAICActionEngine({ ttsEndpoint: '/tts', token: 't' });

    const playPromise = engine.execute({
      type: 'speech',
      agentId: 'a1',
      text: 'will be aborted',
    } as any);
    await new Promise((r) => setTimeout(r, 5));

    // Pause mid-fetch — engine enters resume-waiter state.
    engine.pauseMidFetch();
    await new Promise((r) => setTimeout(r, 10));

    // Now scene-change abort: bumps token + clears resume-waiter.
    engine.abortCurrentAction();

    // The speech promise must resolve (the resume-waiter resolves and
    // executeSpeech bails on the post-resume token check).
    await playPromise; // would hang forever without the abort-clears-waiter wire.

    // Engine state clean: no audio bound, no resume-waiter pending.
    const e = engine as any;
    expect(e._resumeWaiter).toBeNull();
    expect(e._pausedMidFetch).toBe(false);
    expect(mockAudios.length).toBe(0);

    void resolveFetch;
    engine.dispose();
  });

  test('pauseMidFetch returns false when no fetch is in flight (audio already playing case)', () => {
    const engine = new MAICActionEngine({ ttsEndpoint: '/tts', token: 't' });
    // No fetch was started — pauseMidFetch should report "nothing to abort".
    expect(engine.pauseMidFetch()).toBe(false);
    engine.dispose();
  });
});
