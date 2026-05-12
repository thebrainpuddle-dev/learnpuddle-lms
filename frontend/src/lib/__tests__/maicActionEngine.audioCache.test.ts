// maicActionEngine.audioCache.test.ts — Offline audio durability re-wire.
// Asserts the prefetch path persists buffers to IDB, and that the live-TTS
// path falls back to IDB when the network fetch fails.
//
// Acceptance criteria:
//   1. prefetchSpeech persists the decoded buffer to IDB after a successful
//      fetch.
//   2. prefetchSpeech does NOT persist if the AV-P0-2 controller-presence
//      recheck fails (the prefetch was aborted between fetch + then).
//   3. The live-TTS path reads the IDB-cached buffer before hitting the
//      network, preventing reload-time duplicate synthesis.
//   4. The read path (IDB cache hit during fetchTtsBlob) does NOT call
//      cacheAudio again — no double-write loop.

import 'fake-indexeddb/auto';
import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest';
import { MAICActionEngine } from '../maicActionEngine';
import { useMAICStageStore } from '../../stores/maicStageStore';
import { useMAICSettingsStore } from '../../stores/maicSettingsStore';
import {
  maicDb,
  saveClassroom,
  cacheAudio,
  getCachedAudio,
  purgeAll,
  _invalidateEstimateCacheForTests,
  type StoredClassroom,
} from '../maicDb';

function makeClassroom(id: string, overrides: Partial<StoredClassroom> = {}): StoredClassroom {
  return {
    id,
    title: `Classroom ${id}`,
    slides: [],
    scenes: [],
    outlines: [],
    agents: [],
    chatHistory: [],
    config: {},
    sceneSlideBounds: [],
    syncedAt: Date.now(),
    ...overrides,
  };
}

// ─── Mock HTMLAudioElement — same pattern as maicActionEngine.test.ts ──────

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
    setTimeout(() => {
      if (!this.paused) this.onplaying?.();
    }, 5);
    return Promise.resolve();
  });
  pause = vi.fn().mockImplementation(() => {
    this.paused = true;
  });
  constructor() {
    mockAudios.push(this);
  }
  endNow() {
    this.onended?.();
  }
}

// ─── Setup ──────────────────────────────────────────────────────────────────

beforeEach(async () => {
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

  await purgeAll();
  _invalidateEstimateCacheForTests();
});

let _nextBlobId = 0;
const _revokedUrls = new Set<string>();
beforeEach(() => {
  _nextBlobId = 0;
  _revokedUrls.clear();
  // @ts-expect-error jsdom lacks these
  global.URL.createObjectURL = vi.fn(() => `blob:mock-${++_nextBlobId}`);
  // @ts-expect-error same
  global.URL.revokeObjectURL = vi.fn((u: string) => {
    _revokedUrls.add(u);
  });
});

afterEach(async () => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  await purgeAll();
});

// ─── Tests ──────────────────────────────────────────────────────────────────

describe('MAICActionEngine.prefetchSpeech — IDB persistence', () => {
  test('persists buffer to IDB after a successful fetch', async () => {
    // Seed a classroom row so cacheAudio has something to attach to.
    await saveClassroom(makeClassroom('classroom-1'));

    // Mock fetch to return a small MP3 blob whose ArrayBuffer is observable.
    const fetchMock = vi.fn().mockImplementation(() => {
      const blob = new Blob([new Uint8Array([0xff, 0xfb, 0x90, 0x44])], {
        type: 'audio/mpeg',
      });
      return Promise.resolve(new Response(blob, { status: 200 }));
    });
    // @ts-expect-error browser global
    global.fetch = fetchMock;

    const engine = new MAICActionEngine({
      ttsEndpoint: '/tts',
      token: 't',
      classroomId: 'classroom-1',
    });

    engine.prefetchSpeech({
      type: 'speech',
      agentId: 'a1',
      text: 'Hello durably-cached students',
    } as any);

    // Wait for fetch + arrayBuffer + idb put to settle.
    await new Promise((r) => setTimeout(r, 30));

    // The IDB row should now have an audioCache entry. We don't know the
    // engine's internal cache key, but there should be exactly one entry.
    const row = await maicDb.classrooms.get('classroom-1');
    expect(row).toBeDefined();
    expect(row!.audioCache).toBeDefined();
    const keys = Object.keys(row!.audioCache!);
    expect(keys).toHaveLength(1);
    const buf = row!.audioCache![keys[0]];
    expect(buf).toBeInstanceOf(ArrayBuffer);
    expect(buf.byteLength).toBe(4);

    engine.dispose();
  });

  test('does NOT persist when the AV-P0-2 controller-presence recheck fails', async () => {
    await saveClassroom(makeClassroom('classroom-2'));

    // Slow fetch: resolves only after we abort. We simulate by gating the
    // resolution on a manually-resolved promise.
    let releaseFetch!: () => void;
    const gate = new Promise<void>((res) => {
      releaseFetch = res;
    });
    const fetchMock = vi.fn().mockImplementation(async () => {
      await gate;
      return new Response(
        new Blob([new Uint8Array([0xaa, 0xbb])], { type: 'audio/mpeg' }),
        { status: 200 },
      );
    });
    // @ts-expect-error browser global
    global.fetch = fetchMock;

    const engine = new MAICActionEngine({
      ttsEndpoint: '/tts',
      token: 't',
      classroomId: 'classroom-2',
    });

    engine.prefetchSpeech({
      type: 'speech',
      agentId: 'a1',
      text: 'aborted prefetch',
    } as any);

    // Abort BEFORE the fetch resolves — clearPrefetchCache nukes the
    // controller map; the recheck inside the .then() must bail out.
    engine.abortCurrentAction();
    releaseFetch();

    await new Promise((r) => setTimeout(r, 20));

    const row = await maicDb.classrooms.get('classroom-2');
    expect(row).toBeDefined();
    // Either undefined or empty — the prefetch must NOT have persisted.
    const cache = row!.audioCache ?? {};
    expect(Object.keys(cache)).toHaveLength(0);

    engine.dispose();
  });

  test('uses IDB cache during prefetch without issuing a duplicate TTS fetch', async () => {
    await saveClassroom(makeClassroom('classroom-prefetch-cache'));

    const voiceId = 'en-IN-PrabhatNeural';
    const text = 'Already synthesized before reload';
    const key = `${voiceId}::${text}`;
    await cacheAudio('classroom-prefetch-cache', key, new Uint8Array([0xff, 0xfb]).buffer);

    const fetchMock = vi.fn().mockRejectedValue(new Error('network should not be touched'));
    // @ts-expect-error browser global
    global.fetch = fetchMock;

    const engine = new MAICActionEngine({
      ttsEndpoint: '/tts',
      token: 't',
      classroomId: 'classroom-prefetch-cache',
    });

    engine.prefetchSpeech({
      type: 'speech',
      agentId: 'a1',
      text,
    } as any);

    await new Promise((r) => setTimeout(r, 30));

    expect(fetchMock).not.toHaveBeenCalled();

    const promise = engine.execute({
      type: 'speech',
      agentId: 'a1',
      text,
    } as any);
    await new Promise((r) => setTimeout(r, 30));
    expect(fetchMock).not.toHaveBeenCalled();
    mockAudios[mockAudios.length - 1]?.endNow();
    await promise;

    engine.dispose();
  });
});

describe('MAICActionEngine.executeSpeech — IDB cache-first playback', () => {
  test('uses IDB-cached buffer before attempting live fetch', async () => {
    await saveClassroom(makeClassroom('classroom-3'));

    // Pre-seed IDB with a buffer that the engine will look up by its
    // deterministic prefetch key (voiceId+text). The engine's helper is
    // private, so we shadow the key-derivation by writing under the same
    // string the engine will produce: `${voiceId}::${text.slice(0,200)}`.
    // The agent's role 'professor' resolves through ROLE_VOICE_MAP — we
    // gave the agent an explicit voiceId in beforeEach so the key uses it.
    const voiceId = 'en-IN-PrabhatNeural';
    const text = 'Offline survives';
    const key = `${voiceId}::${text}`;

    const seed = new Uint8Array([0x49, 0x44, 0x33, 0x04]); // "ID3\x04"
    await cacheAudio('classroom-3', key, seed.buffer);

    // Verify our seed landed.
    const seeded = await getCachedAudio('classroom-3', key);
    expect(seeded).toBeDefined();
    expect(seeded!.byteLength).toBe(4);

    // A cache hit should avoid live TTS entirely.
    const fetchMock = vi.fn().mockRejectedValue(new Error('network off'));
    // @ts-expect-error browser global
    global.fetch = fetchMock;

    const engine = new MAICActionEngine({
      ttsEndpoint: '/tts',
      token: 't',
      classroomId: 'classroom-3',
    });

    const promise = engine.execute({
      type: 'speech',
      agentId: 'a1',
      text,
    } as any);

    // Let the failed fetch + IDB lookup + audio.play() pipeline settle.
    await new Promise((r) => setTimeout(r, 30));

    // The engine should have built an Audio element from the durable cache.
    expect(mockAudios.length).toBeGreaterThanOrEqual(1);
    const audio = mockAudios[mockAudios.length - 1];
    expect(audio.src.startsWith('blob:mock-')).toBe(true);
    expect(audio.play).toHaveBeenCalled();
    expect(fetchMock).not.toHaveBeenCalled();

    audio.endNow();
    await promise;

    engine.dispose();
  });

  test('cache hit during fetchTtsBlob does NOT trigger a write back to IDB (no loop)', async () => {
    // Seed IDB with a row + an audio buffer for our key.
    await saveClassroom(makeClassroom('classroom-4'));
    const voiceId = 'en-IN-PrabhatNeural';
    const text = 'no loop';
    const key = `${voiceId}::${text}`;
    await cacheAudio('classroom-4', key, new Uint8Array([0x01, 0x02]).buffer);

    // Snapshot the audioCache size — the read path must not grow it.
    const before = await maicDb.classrooms.get('classroom-4');
    const beforeKeys = Object.keys(before!.audioCache ?? {});
    expect(beforeKeys).toHaveLength(1);

    // Network is offline so the read path triggers (live fetch fails →
    // IDB fallback hits).
    const fetchMock = vi.fn().mockRejectedValue(new Error('offline'));
    // @ts-expect-error browser global
    global.fetch = fetchMock;

    const engine = new MAICActionEngine({
      ttsEndpoint: '/tts',
      token: 't',
      classroomId: 'classroom-4',
    });

    const promise = engine.execute({
      type: 'speech',
      agentId: 'a1',
      text,
    } as any);
    await new Promise((r) => setTimeout(r, 30));
    mockAudios[mockAudios.length - 1]?.endNow();
    await promise;

    const after = await maicDb.classrooms.get('classroom-4');
    const afterKeys = Object.keys(after!.audioCache ?? {});
    // Same key set; no extra entries written by the read path.
    expect(afterKeys.sort()).toEqual(beforeKeys.sort());

    engine.dispose();
  });
});
