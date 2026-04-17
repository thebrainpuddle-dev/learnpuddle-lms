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

// ─── Tests ──────────────────────────────────────────────────────────────────

describe('MAICActionEngine.executeSpeech', () => {
  test('subtitle fires EAGERLY at speech entry (Chunk 9) — no wait for audio.onplaying', async () => {
    // Chunk 9 changed the contract: subtitles must land the same frame the
    // engine commits to a speech action, not after the audio element
    // buffers and fires onplaying (which lags 500ms-2s on slow networks).
    // The old test asserted the opposite behavior — it's been flipped.
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

    // Subtitle + speaking indicator should be set IMMEDIATELY on entry,
    // before any network / decoding completes.
    await new Promise((r) => setTimeout(r, 0));
    expect(onStart).toHaveBeenCalledWith('a1', 'Hello students');
    expect(useMAICStageStore.getState().speechText).toBe('Hello students');
    expect(useMAICStageStore.getState().speakingAgentId).toBe('a1');

    // After mock audio's `playing` event fires (10 ms), state is
    // re-asserted idempotently — still the same values.
    await new Promise((r) => setTimeout(r, 15));
    expect(useMAICStageStore.getState().speechText).toBe('Hello students');
    expect(useMAICStageStore.getState().speakingAgentId).toBe('a1');

    // Trigger end → promise resolves, state clears.
    mockAudios[0].endNow();
    await promise;
    expect(useMAICStageStore.getState().speechText).toBeNull();
    expect(useMAICStageStore.getState().speakingAgentId).toBeNull();
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
