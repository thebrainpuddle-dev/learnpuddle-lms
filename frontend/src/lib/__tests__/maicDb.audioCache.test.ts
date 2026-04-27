// maicDb.audioCache.test.ts — Tests for the IDB-backed audio cache (offline
// audio durability re-wire, 2026-04-26 P1 gap).
//
// Acceptance criteria covered:
//   1. cacheAudio writes a buffer to IDB; getCachedAudio reads it back.
//   2. cacheAudio evicts oldest classrooms' audio when the total exceeds
//      AUDIO_CACHE_BUDGET_BYTES.
//   3. cacheAudio respects withQuotaCheck (a simulated QuotaExceededError
//      triggers the standard quota fallback / retry).
//   4. getCachedAudio returns undefined for unknown sceneId.
//   5. When the whole classroom is evicted by the quota manager, its
//      audioCache field disappears with it.

import 'fake-indexeddb/auto';
import { beforeEach, afterEach, describe, expect, test, vi } from 'vitest';

import {
  maicDb,
  saveClassroom,
  purgeAll,
  cacheAudio,
  getCachedAudio,
  evictOldestN,
  AUDIO_CACHE_BUDGET_BYTES,
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

function makeBuffer(size: number, fillByte = 0x41): ArrayBuffer {
  const buf = new ArrayBuffer(size);
  new Uint8Array(buf).fill(fillByte);
  return buf;
}

beforeEach(async () => {
  await purgeAll();
  _invalidateEstimateCacheForTests();
});

afterEach(() => {
  vi.restoreAllMocks();
  _invalidateEstimateCacheForTests();
});

describe('maicDb audioCache — round-trip', () => {
  test('cacheAudio writes buffer to IndexedDB and getCachedAudio reads it back', async () => {
    await saveClassroom(makeClassroom('c1'));

    const buf = makeBuffer(1024, 0x7f);
    await cacheAudio('c1', 'scene-1', buf);

    const back = await getCachedAudio('c1', 'scene-1');
    expect(back).toBeDefined();
    expect(back!.byteLength).toBe(1024);
    // Sanity: bytes survived the round-trip.
    const view = new Uint8Array(back!);
    expect(view[0]).toBe(0x7f);
    expect(view[1023]).toBe(0x7f);
  });

  test('getCachedAudio returns undefined for unknown sceneId', async () => {
    await saveClassroom(makeClassroom('c1'));
    const back = await getCachedAudio('c1', 'never-cached');
    expect(back).toBeUndefined();
  });

  test('getCachedAudio returns undefined for unknown classroom', async () => {
    const back = await getCachedAudio('does-not-exist', 's1');
    expect(back).toBeUndefined();
  });

  test('cacheAudio is a no-op when the classroom row is absent', async () => {
    // No row yet — cacheAudio should silently no-op rather than create a
    // ghost row. The fire-and-forget caller in the action engine has no
    // reasonable fallback so we degrade gracefully.
    const buf = makeBuffer(64);
    await cacheAudio('ghost', 'scene-1', buf);
    const row = await maicDb.classrooms.get('ghost');
    expect(row).toBeUndefined();
  });
});

describe('maicDb audioCache — budget eviction', () => {
  test('cacheAudio evicts oldest classrooms when total exceeds AUDIO_CACHE_BUDGET_BYTES', async () => {
    // Seed three classrooms with strictly ascending lastAccessedAt so we
    // know which is "oldest". Each has 40% of the budget worth of audio.
    const now = Date.now();
    const fortyPercent = Math.floor(AUDIO_CACHE_BUDGET_BYTES * 0.4);
    await maicDb.classrooms.put(makeClassroom('old', { lastAccessedAt: now - 3000 }));
    await maicDb.classrooms.put(makeClassroom('mid', { lastAccessedAt: now - 2000 }));
    await maicDb.classrooms.put(makeClassroom('new', { lastAccessedAt: now - 1000 }));

    await cacheAudio('old', 's1', makeBuffer(fortyPercent));
    await cacheAudio('mid', 's1', makeBuffer(fortyPercent));
    // Total now ~80% of budget.

    // Adding a third 40% buffer would push us to 120% → eviction must drop
    // the oldest classroom's audioCache to make room.
    await cacheAudio('new', 's1', makeBuffer(fortyPercent));

    // 'old' should have lost its audio (oldest by lastAccessedAt).
    const oldBack = await getCachedAudio('old', 's1');
    expect(oldBack).toBeUndefined();
    // 'new' definitely landed.
    const newBack = await getCachedAudio('new', 's1');
    expect(newBack).toBeDefined();
    expect(newBack!.byteLength).toBe(fortyPercent);
  });

  test('cacheAudio rejects (no-op) a single buffer larger than the entire budget', async () => {
    await saveClassroom(makeClassroom('big'));
    // Buffer larger than the whole budget — caching it would be silly.
    // We should silently drop it rather than evict everything else for
    // an unstoreable single payload.
    const overSized = AUDIO_CACHE_BUDGET_BYTES + 1024;
    await cacheAudio('big', 's1', makeBuffer(overSized));
    const back = await getCachedAudio('big', 's1');
    expect(back).toBeUndefined();
  });
});

describe('maicDb audioCache — withQuotaCheck integration', () => {
  test('cacheAudio surfaces the standard quota fallback on QuotaExceededError', async () => {
    // Seed enough classrooms to make 25%-fallback meaningful.
    const now = Date.now();
    for (let i = 0; i < 8; i += 1) {
      await maicDb.classrooms.put(
        makeClassroom(`q${i}`, { lastAccessedAt: now - (8 - i) * 1000 }),
      );
    }

    // First put throws QuotaExceededError; second succeeds (real impl).
    const realPut = maicDb.classrooms.put.bind(maicDb.classrooms);
    let calls = 0;
    const spy = vi.spyOn(maicDb.classrooms, 'put');
    spy.mockImplementation(((...args: unknown[]) => {
      calls += 1;
      if (calls === 1) {
        return Promise.reject(
          Object.assign(new Error('quota'), { name: 'QuotaExceededError' }),
        );
      }
      // @ts-expect-error passthrough
      return realPut(...args);
    }) as typeof maicDb.classrooms.put);

    await cacheAudio('q5', 'scene-1', makeBuffer(2048));
    expect(spy).toHaveBeenCalledTimes(2); // initial throw + retry
    spy.mockRestore();

    // The retry succeeded: row q5 still has its audio.
    const back = await getCachedAudio('q5', 'scene-1');
    expect(back).toBeDefined();
    expect(back!.byteLength).toBe(2048);

    // 25% of 8 = 2 oldest evicted by the quota fallback.
    const remaining = await maicDb.classrooms.count();
    expect(remaining).toBe(6);
  });
});

describe('maicDb audioCache — classroom-level eviction takes audioCache with it', () => {
  test('evictOldestN removes the audioCache field along with the classroom row', async () => {
    const now = Date.now();
    await maicDb.classrooms.put(makeClassroom('alpha', { lastAccessedAt: now - 3000 }));
    await maicDb.classrooms.put(makeClassroom('beta', { lastAccessedAt: now - 2000 }));
    await maicDb.classrooms.put(makeClassroom('gamma', { lastAccessedAt: now - 1000 }));

    await cacheAudio('alpha', 's1', makeBuffer(512));
    await cacheAudio('beta', 's1', makeBuffer(512));
    await cacheAudio('gamma', 's1', makeBuffer(512));

    // Evict the two oldest (alpha, beta).
    const removed = await evictOldestN(2);
    expect(removed).toBe(2);

    // Both rows are gone — and so are their audioCache buffers.
    expect(await getCachedAudio('alpha', 's1')).toBeUndefined();
    expect(await getCachedAudio('beta', 's1')).toBeUndefined();
    // gamma survives untouched.
    const survivor = await getCachedAudio('gamma', 's1');
    expect(survivor).toBeDefined();
    expect(survivor!.byteLength).toBe(512);
  });
});

describe('maicDb audioCache — multiple scenes per classroom', () => {
  test('two cacheAudio calls under the same classroom add two scene keys', async () => {
    await saveClassroom(makeClassroom('multi'));
    await cacheAudio('multi', 'scene-a', makeBuffer(128, 0x10));
    await cacheAudio('multi', 'scene-b', makeBuffer(256, 0x20));

    const a = await getCachedAudio('multi', 'scene-a');
    const b = await getCachedAudio('multi', 'scene-b');
    expect(a).toBeDefined();
    expect(b).toBeDefined();
    expect(a!.byteLength).toBe(128);
    expect(b!.byteLength).toBe(256);
    expect(new Uint8Array(a!)[0]).toBe(0x10);
    expect(new Uint8Array(b!)[0]).toBe(0x20);
  });
});
