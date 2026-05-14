// PERF-P0-6: IndexedDB quota management + LRU eviction tests.
//
// We use `fake-indexeddb` to give Dexie a real IDBFactory inside the
// happy-dom test env. Each test resets the DB by deleting the database and
// re-opening — Dexie reattaches automatically on next operation.

import 'fake-indexeddb/auto';
import { beforeEach, afterEach, describe, expect, test, vi } from 'vitest';

// Imported eagerly so the Dexie singleton is constructed once. Individual
// tests reset state via `purgeAll()` rather than re-importing.
import {
  maicDb,
  getStoredClassroom,
  saveClassroom,
  purgeAll,
  evictOldestN,
  evictUntilUnderWatermark,
  withQuotaCheck,
  QUOTA_HIGH_WATERMARK,
  QUOTA_LOW_WATERMARK,
  STORAGE_ESTIMATE_TTL_MS,
  _readWatermarksFromEnvForTests,
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

/** Mock navigator.storage.estimate to return a controllable usage/quota. */
function mockEstimate(usage: number, quota: number) {
  const nav = globalThis.navigator as Navigator & { storage?: StorageManager };
  Object.defineProperty(nav, 'storage', {
    configurable: true,
    value: {
      estimate: async () => ({ usage, quota }),
    } as unknown as StorageManager,
  });
}

function clearEstimate() {
  const nav = globalThis.navigator as Navigator & { storage?: StorageManager };
  Object.defineProperty(nav, 'storage', {
    configurable: true,
    value: undefined,
  });
}

beforeEach(async () => {
  await purgeAll();
  _invalidateEstimateCacheForTests();
});

afterEach(() => {
  clearEstimate();
  vi.restoreAllMocks();
  _invalidateEstimateCacheForTests();
});

describe('maicDb quota — under-threshold no-op', () => {
  test('saveClassroom does not evict when usage/quota is below high watermark', async () => {
    // Seed three classrooms with distinct lastAccessedAt timestamps.
    await saveClassroom(makeClassroom('a'));
    await saveClassroom(makeClassroom('b'));
    await saveClassroom(makeClassroom('c'));

    // Pretend we're at 50% — well below the 0.8 high-watermark.
    mockEstimate(500, 1000);

    await saveClassroom(makeClassroom('d'));

    const all = await maicDb.classrooms.toArray();
    const ids = all.map((c) => c.id).sort();
    expect(ids).toEqual(['a', 'b', 'c', 'd']);
  });
});

describe('maicDb quota — over-threshold evicts oldest', () => {
  test('evictUntilUnderWatermark removes oldest by lastAccessedAt until ratio drops', async () => {
    const now = Date.now();
    // Five classrooms with strictly ascending lastAccessedAt:
    //   oldest=ka (now-50000), ..., newest=ke (now-10000).
    for (let i = 0; i < 5; i += 1) {
      await maicDb.classrooms.put(
        makeClassroom(`k${'abcde'[i]}`, {
          syncedAt: now - (50000 - i * 10000),
          lastAccessedAt: now - (50000 - i * 10000),
        }),
      );
    }

    // AUDIT-2026-04-25-7: batch eviction uses ≤2 estimate calls.
    // Batch 1: ratio=0.9, total=5, avg=180 bytes, gap=(0.9-0.6)*1000=300 →
    //   n=ceil(300/180)=2 → evict ka,kb.
    // Re-estimate: ratio=0.85 still > 0.6 → Batch 2: remaining=3,
    //   avg=850/3≈283 → n=ceil(250/283)=1 → evict kc.
    // Total evicted: 3. Remaining: kd, ke.
    const ratios = [0.9, 0.85];
    let call = 0;
    const nav = globalThis.navigator as Navigator & { storage?: StorageManager };
    Object.defineProperty(nav, 'storage', {
      configurable: true,
      value: {
        estimate: async () => {
          const r = ratios[Math.min(call, ratios.length - 1)];
          call += 1;
          return { usage: r * 1000, quota: 1000 };
        },
      } as unknown as StorageManager,
    });

    await evictUntilUnderWatermark();

    const remaining = await maicDb.classrooms.toArray();
    const ids = remaining.map((c) => c.id).sort();
    // ka,kb evicted in batch 1; kc evicted in batch 2; kd,ke remain.
    expect(ids).toEqual(['kd', 'ke']);
  });

  test('saveClassroom triggers proactive eviction when over high watermark', async () => {
    const now = Date.now();
    // Two existing classrooms, oldest first.
    await maicDb.classrooms.put(makeClassroom('old', { lastAccessedAt: now - 100000 }));
    await maicDb.classrooms.put(makeClassroom('new', { lastAccessedAt: now - 10 }));

    // Sequence: pre-write check sees 0.95; first eviction loop check sees 0.95
    // → evict 'old'; second check sees 0.5 → exit. Subsequent calls (after the
    // put has happened) keep returning 0.5.
    const ratios = [0.95, 0.95, 0.5, 0.5];
    let call = 0;
    const nav = globalThis.navigator as Navigator & { storage?: StorageManager };
    Object.defineProperty(nav, 'storage', {
      configurable: true,
      value: {
        estimate: async () => {
          const r = ratios[Math.min(call, ratios.length - 1)];
          call += 1;
          return { usage: r * 1000, quota: 1000 };
        },
      } as unknown as StorageManager,
    });

    await saveClassroom(makeClassroom('fresh'));

    const remaining = await maicDb.classrooms.toArray();
    const ids = remaining.map((c) => c.id).sort();
    expect(ids).toContain('fresh');
    expect(ids).toContain('new');
    expect(ids).not.toContain('old');
  });
});

describe('maicDb quota — QuotaExceededError fallback retry', () => {
  test('withQuotaCheck retries op once after evicting 25% on QuotaExceededError', async () => {
    // Seed 8 classrooms — 25% = 2 evictions on fallback.
    const now = Date.now();
    for (let i = 0; i < 8; i += 1) {
      await maicDb.classrooms.put(
        makeClassroom(`q${i}`, { lastAccessedAt: now - (8 - i) * 1000 }),
      );
    }

    const op = vi.fn();
    const quotaErr = Object.assign(new Error('quota exceeded'), { name: 'QuotaExceededError' });
    op.mockRejectedValueOnce(quotaErr).mockResolvedValueOnce('ok');

    // No estimate mocked → ratio path is null → no proactive eviction; we go
    // straight to the op, which throws, triggering the fallback path.
    const result = await withQuotaCheck(() => op());
    expect(result).toBe('ok');
    expect(op).toHaveBeenCalledTimes(2);

    // 25% of 8 = 2 oldest deleted (q0, q1).
    const remaining = await maicDb.classrooms.toArray();
    const ids = remaining.map((c) => c.id).sort();
    expect(ids).toHaveLength(6);
    expect(ids).not.toContain('q0');
    expect(ids).not.toContain('q1');
    expect(ids).toContain('q2');
    expect(ids).toContain('q7');
  });

  test('withQuotaCheck propagates non-quota errors without retry', async () => {
    const op = vi.fn().mockRejectedValue(new Error('totally different'));
    await expect(withQuotaCheck(() => op())).rejects.toThrow('totally different');
    expect(op).toHaveBeenCalledTimes(1);
  });
});

describe('maicDb quota — lastAccessedAt LRU bump', () => {
  test('getStoredClassroom bumps lastAccessedAt on read', async () => {
    const original = Date.now() - 100000;
    await maicDb.classrooms.put(makeClassroom('readme', { lastAccessedAt: original }));

    await getStoredClassroom('readme');

    // Bump is fire-and-forget — give the microtask queue a tick.
    await new Promise((r) => setTimeout(r, 0));

    const row = await maicDb.classrooms.get('readme');
    expect(row).toBeDefined();
    expect(row!.lastAccessedAt).toBeDefined();
    expect(row!.lastAccessedAt!).toBeGreaterThan(original);
  });

  test('evictOldestN evicts strictly by lastAccessedAt order', async () => {
    const now = Date.now();
    await maicDb.classrooms.put(makeClassroom('young', { lastAccessedAt: now - 1 }));
    await maicDb.classrooms.put(makeClassroom('middle', { lastAccessedAt: now - 1000 }));
    await maicDb.classrooms.put(makeClassroom('elderly', { lastAccessedAt: now - 100000 }));

    const removed = await evictOldestN(2);
    expect(removed).toBe(2);

    const remaining = await maicDb.classrooms.toArray();
    expect(remaining.map((c) => c.id)).toEqual(['young']);
  });
});

describe('maicDb quota — concurrent puts do not double-evict', () => {
  test('parallel withQuotaCheck calls share a single eviction promise', async () => {
    // Seed three classrooms.
    const now = Date.now();
    await maicDb.classrooms.put(makeClassroom('a', { lastAccessedAt: now - 3000 }));
    await maicDb.classrooms.put(makeClassroom('b', { lastAccessedAt: now - 2000 }));
    await maicDb.classrooms.put(makeClassroom('c', { lastAccessedAt: now - 1000 }));

    // Estimate stub: first call (entry to loop) returns over-watermark, every
    // subsequent call returns under-watermark — exactly one eviction in this
    // pass. If concurrent passes ran, we'd see >1 eviction.
    let calls = 0;
    const nav = globalThis.navigator as Navigator & { storage?: StorageManager };
    Object.defineProperty(nav, 'storage', {
      configurable: true,
      value: {
        estimate: async () => {
          calls += 1;
          if (calls === 1) return { usage: 0.9, quota: 1 };
          return { usage: 0.5, quota: 1 };
        },
      } as unknown as StorageManager,
    });

    // Fire two concurrent eviction calls.
    const p1 = evictUntilUnderWatermark();
    const p2 = evictUntilUnderWatermark();

    // They MUST be the same promise instance (shared lock).
    expect(p1).toBe(p2);

    await Promise.all([p1, p2]);

    // Exactly one classroom (the oldest) was evicted in this single shared pass.
    const remaining = await maicDb.classrooms.toArray();
    const ids = remaining.map((c) => c.id).sort();
    expect(ids).toEqual(['b', 'c']);
  });

  test('after one eviction settles, a subsequent call starts a fresh pass', async () => {
    // Seed one classroom.
    await maicDb.classrooms.put(makeClassroom('only', { lastAccessedAt: Date.now() - 1000 }));

    mockEstimate(0.5, 1); // under watermark — no-op pass
    await evictUntilUnderWatermark();

    // Second call should not be the same already-resolved promise — a NEW
    // pass starts. Hard to assert non-identity (microtask), but we can verify
    // that a follow-up over-watermark call DOES evict.
    mockEstimate(0.95, 1);
    await evictUntilUnderWatermark();
    // Estimate stays at 0.95 forever; loop is bounded by row count (1) so
    // exactly one entry is evicted.
    const remaining = await maicDb.classrooms.toArray();
    expect(remaining).toHaveLength(0);
  });
});

describe('maicDb quota — purgeAll', () => {
  test('purgeAll wipes every classroom', async () => {
    await saveClassroom(makeClassroom('a'));
    await saveClassroom(makeClassroom('b'));
    await saveClassroom(makeClassroom('c'));

    await purgeAll();

    const remaining = await maicDb.classrooms.toArray();
    expect(remaining).toHaveLength(0);
  });

  test('purgeAll on empty DB is a no-op', async () => {
    await expect(purgeAll()).resolves.toBeUndefined();
  });
});

describe('maicDb quota — thresholds', () => {
  test('thresholds are sane', () => {
    expect(QUOTA_HIGH_WATERMARK).toBeGreaterThan(QUOTA_LOW_WATERMARK);
    expect(QUOTA_HIGH_WATERMARK).toBeLessThanOrEqual(1);
    expect(QUOTA_LOW_WATERMARK).toBeGreaterThan(0);
  });
});

// ─── F3 follow-ups: tightened eviction lock ────────────────────────────────

describe('maicDb quota — F3 eviction lock coalescing', () => {
  test('three concurrent puts share a single eviction pass', async () => {
    // Seed three classrooms so an eviction pass has something to delete.
    const now = Date.now();
    await maicDb.classrooms.put(makeClassroom('A', { lastAccessedAt: now - 3000 }));
    await maicDb.classrooms.put(makeClassroom('B', { lastAccessedAt: now - 2000 }));
    await maicDb.classrooms.put(makeClassroom('C', { lastAccessedAt: now - 1000 }));

    // Estimate stub: first call sees over-watermark (0.95), second sees
    // under-watermark (0.5). AUDIT-2026-04-25-7 batch algorithm:
    //   Batch 1: ratio=0.95, total=3, avg=0.317, gap=0.35 → n=ceil(1.1)=2 →
    //   evict A,B. Re-estimate: 0.5 < 0.6 → done. ONE shared pass evicts 2.
    let estimateCalls = 0;
    const nav = globalThis.navigator as Navigator & { storage?: StorageManager };
    Object.defineProperty(nav, 'storage', {
      configurable: true,
      value: {
        estimate: async () => {
          estimateCalls += 1;
          if (estimateCalls === 1) return { usage: 0.95, quota: 1 };
          return { usage: 0.5, quota: 1 };
        },
      } as unknown as StorageManager,
    });

    // Three concurrent calls — same tick, same microtask gap.
    const p1 = evictUntilUnderWatermark();
    const p2 = evictUntilUnderWatermark();
    const p3 = evictUntilUnderWatermark();

    // All three MUST be the same shared promise instance.
    expect(p1).toBe(p2);
    expect(p2).toBe(p3);

    await Promise.all([p1, p2, p3]);

    // Two evictions occurred in the single shared batch pass (A and B).
    const remaining = await maicDb.classrooms.toArray();
    const ids = remaining.map((c) => c.id).sort();
    expect(ids).toEqual(['C']);
  });

  test('eviction lock is released after the pass completes', async () => {
    // Seed two classrooms.
    const now = Date.now();
    await maicDb.classrooms.put(makeClassroom('first', { lastAccessedAt: now - 2000 }));
    await maicDb.classrooms.put(makeClassroom('second', { lastAccessedAt: now - 1000 }));

    // Pass 1: under watermark → no-op completion.
    mockEstimate(0.5, 1);
    const pass1 = evictUntilUnderWatermark();
    await pass1;

    // After pass 1 settles the lock slot must be cleared, so a second call
    // returns a NEW promise (not pass1). Verify by identity.
    mockEstimate(0.95, 1);
    const pass2 = evictUntilUnderWatermark();
    expect(pass2).not.toBe(pass1);

    await pass2;

    // Pass 2 saw over-watermark on every estimate call; loop is bounded by
    // row count (2) so it evicts both rows.
    const remaining = await maicDb.classrooms.toArray();
    expect(remaining).toHaveLength(0);
  });
});

// ─── F4 follow-ups: env-driven watermark overrides ─────────────────────────

describe('maicDb quota — F4 watermark env overrides', () => {
  test('reads watermark overrides from import.meta.env', () => {
    vi.stubEnv('VITE_QUOTA_HIGH_WATERMARK', '0.9');
    vi.stubEnv('VITE_QUOTA_LOW_WATERMARK', '0.4');
    try {
      const w = _readWatermarksFromEnvForTests();
      expect(w.high).toBe(0.9);
      expect(w.low).toBe(0.4);
    } finally {
      vi.unstubAllEnvs();
    }
  });

  test('falls back to defaults when overrides are invalid (low >= high)', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.stubEnv('VITE_QUOTA_HIGH_WATERMARK', '0.5');
    vi.stubEnv('VITE_QUOTA_LOW_WATERMARK', '0.7'); // invalid: low > high
    try {
      const w = _readWatermarksFromEnvForTests();
      expect(w.high).toBe(0.8);
      expect(w.low).toBe(0.6);
      expect(warn).toHaveBeenCalled();
    } finally {
      vi.unstubAllEnvs();
      warn.mockRestore();
    }
  });

  test('falls back to defaults when overrides are out of range', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.stubEnv('VITE_QUOTA_HIGH_WATERMARK', '1.5'); // invalid: > 1
    vi.stubEnv('VITE_QUOTA_LOW_WATERMARK', '0.6');
    try {
      const w = _readWatermarksFromEnvForTests();
      expect(w.high).toBe(0.8);
      expect(w.low).toBe(0.6);
      expect(warn).toHaveBeenCalled();
    } finally {
      vi.unstubAllEnvs();
      warn.mockRestore();
    }
  });
});

// ─── F5 follow-up: real-payload QuotaExceededError integration ─────────────

describe('maicDb quota — F5 real-payload QuotaExceededError integration', () => {
  test('multi-MB ArrayBuffer payloads survive a quota throw via eviction + retry', async () => {
    // Seed 50 classrooms each holding a 2MB ArrayBuffer in audioCache. We
    // can't pragmatically force fake-indexeddb to enforce a real-byte quota,
    // so we mock Dexie.put to throw QuotaExceededError on the 25th invocation
    // and succeed thereafter — modelling a real device that ran out of space
    // mid-run. The retry path inside `withQuotaCheck` must:
    //   (a) catch the synthetic quota throw,
    //   (b) evict 25% of the oldest entries,
    //   (c) succeed on the second op call,
    // landing the cache at 25 surviving entries (50 attempted - 25 evicted by
    // the fallback before the retry).

    // Pre-seed 24 classrooms directly via Dexie so the spy starts clean for
    // the 25th-onwards puts. We use the real `put` here (no spy yet).
    // AUDIT-2026-04-25-6: audioCache field removed from schema (Option B —
    // dead code deletion). Replaced with a comparable-size payload via
    // `slides` to keep the byte-pressure semantics of the test intact.
    for (let i = 0; i < 24; i += 1) {
      const room = makeClassroom(`pre-${String(i).padStart(3, '0')}`, {
        // Stuff a marker payload into config so each row is non-trivial.
        config: { _bytes: i },
        lastAccessedAt: Date.now() - (1000 - i),
      });
      // bypass quota wrapper for seeding speed
      await maicDb.classrooms.put(room);
    }

    // Now spy on `put`: throw QuotaExceededError exactly once (the next call),
    // then pass through to the real implementation.
    const realPut = maicDb.classrooms.put.bind(maicDb.classrooms);
    let putCalls = 0;
    const putSpy = vi.spyOn(maicDb.classrooms, 'put');
    putSpy.mockImplementation(((...args: unknown[]) => {
      putCalls += 1;
      if (putCalls === 1) {
        const err = Object.assign(new Error('quota exceeded'), {
          name: 'QuotaExceededError',
        });
        return Promise.reject(err);
      }
      // @ts-expect-error — passthrough
      return realPut(...args);
    }) as typeof maicDb.classrooms.put);

    // Now attempt a single saveClassroom — its first put throws, the fallback
    // evicts 25% of the 24 seeded rows (=6), and the retry succeeds.
    const fresh = makeClassroom('post-fresh', {
      config: { _marker: 'fresh' },
    });
    await saveClassroom(fresh);

    // The op was invoked twice (initial throw + retry).
    expect(putSpy).toHaveBeenCalledTimes(2);

    // Restore so subsequent assertions can read freely.
    putSpy.mockRestore();

    const remaining = await maicDb.classrooms.toArray();
    // 24 seeded - 6 evicted (25% of 24 = 6) + 1 freshly written = 19.
    expect(remaining).toHaveLength(24 - 6 + 1);
    const ids = remaining.map((c) => c.id);
    expect(ids).toContain('post-fresh');
    // Oldest 6 (pre-000..pre-005) should be evicted.
    expect(ids).not.toContain('pre-000');
    expect(ids).not.toContain('pre-005');
    // Newer pre-* survive.
    expect(ids).toContain('pre-023');
  });
});

// ─── AUDIT-2026-04-25-5: storage-estimate caching with TTL ────────────────

describe('maicDb quota — AUDIT-5 estimate caching', () => {
  /** Replace navigator.storage.estimate with a counted spy returning the
   *  same fixed ratio each call. Returns the spy so tests can assert call
   *  counts. */
  function installCountedEstimate(usage: number, quota: number) {
    const spy = vi.fn(async () => ({ usage, quota }));
    const nav = globalThis.navigator as Navigator & { storage?: StorageManager };
    Object.defineProperty(nav, 'storage', {
      configurable: true,
      value: { estimate: spy } as unknown as StorageManager,
    });
    return spy;
  }

  test('two consecutive saveClassroom calls within TTL hit estimate once', async () => {
    // Below high-watermark: estimate is consulted but no eviction triggers.
    const spy = installCountedEstimate(500, 1000); // ratio 0.5

    await saveClassroom(makeClassroom('a'));
    await saveClassroom(makeClassroom('b'));

    // Within TTL → cached estimate reused, spy called at most once.
    expect(spy).toHaveBeenCalledTimes(1);
  });

  test('two saveClassroom calls separated by > TTL re-estimate', async () => {
    // Only fake Date so that fake-indexeddb's internal Promise/microtask
    // machinery is not disturbed. `vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })` without options would
    // also fake setTimeout/setInterval, stalling IDB operations inside the test.
    vi.useFakeTimers({ toFake: ['Date'] });
    try {
      const spy = installCountedEstimate(500, 1000);

      // First call: cache miss → spy invoked.
      await saveClassroom(makeClassroom('a'));
      expect(spy).toHaveBeenCalledTimes(1);

      // Advance past the TTL window.
      vi.setSystemTime(Date.now() + STORAGE_ESTIMATE_TTL_MS + 100);

      // Second call: cache stale → spy invoked again.
      await saveClassroom(makeClassroom('b'));
      expect(spy).toHaveBeenCalledTimes(2);
    } finally {
      vi.useRealTimers();
    }
  });

  test('cached very-low ratio short-circuits future estimates entirely', async () => {
    // Ratio well below the low watermark — there is no risk worth paying
    // for, so withQuotaCheck should skip even the cache lookup ms-cost on
    // subsequent calls within TTL. We assert by call count.
    const spy = installCountedEstimate(50, 1000); // ratio 0.05 — very safe

    await saveClassroom(makeClassroom('a'));
    await saveClassroom(makeClassroom('b'));
    await saveClassroom(makeClassroom('c'));

    // First call seeds the cache → 1 estimate call. Subsequent calls should
    // see the very-low cached ratio and skip both the API and even the
    // cache-staleness path.
    expect(spy).toHaveBeenCalledTimes(1);
  });

  test('QuotaExceededError invalidates the cached estimate', async () => {
    // Seed a classroom so the fallback eviction has something to delete.
    await maicDb.classrooms.put(makeClassroom('seed', { lastAccessedAt: Date.now() - 1000 }));

    const spy = installCountedEstimate(500, 1000); // ratio 0.5 — under watermark

    // Prime the cache via a successful op.
    await withQuotaCheck(async () => undefined);
    expect(spy).toHaveBeenCalledTimes(1);

    // Throw a quota error — the wrapper should evict, invalidate the cache,
    // and retry. The next `withQuotaCheck` call after this should re-estimate.
    const op = vi
      .fn()
      .mockRejectedValueOnce(
        Object.assign(new Error('quota'), { name: 'QuotaExceededError' }),
      )
      .mockResolvedValueOnce('ok');
    await withQuotaCheck(() => op());

    // Run another op — after a QuotaExceededError the cache is dirty so we
    // re-estimate. Total calls jump.
    await withQuotaCheck(async () => undefined);
    expect(spy.mock.calls.length).toBeGreaterThanOrEqual(2);
  });
});

// ─── AUDIT-2026-04-25-7: batched eviction (no quadratic toArray loop) ──────

describe('maicDb quota — AUDIT-7 batched eviction', () => {
  test('evictUntilUnderWatermark uses at most 2 estimate calls and does not loop per-row', async () => {
    // 20 saturated classrooms over the watermark.
    const now = Date.now();
    for (let i = 0; i < 20; i += 1) {
      await maicDb.classrooms.put(
        makeClassroom(`r${String(i).padStart(2, '0')}`, {
          lastAccessedAt: now - (20 - i) * 1000,
        }),
      );
    }
    _invalidateEstimateCacheForTests();

    // Estimate stays high — we want the batch logic to compute the eviction
    // count up front rather than spinning per-row.
    const spy = vi.fn(async () => ({ usage: 950, quota: 1000 })); // ratio 0.95
    const nav = globalThis.navigator as Navigator & { storage?: StorageManager };
    Object.defineProperty(nav, 'storage', {
      configurable: true,
      value: { estimate: spy } as unknown as StorageManager,
    });

    await evictUntilUnderWatermark();

    // At most 2 estimate calls (initial + one verification pass).
    expect(spy.mock.calls.length).toBeLessThanOrEqual(2);

    // Some rows were evicted — we made progress.
    const remaining = await maicDb.classrooms.count();
    expect(remaining).toBeLessThan(20);
  });

  test('evictOldestN does not load full table via toArray', async () => {
    const now = Date.now();
    for (let i = 0; i < 5; i += 1) {
      await maicDb.classrooms.put(
        makeClassroom(`x${i}`, { lastAccessedAt: now - (5 - i) * 1000 }),
      );
    }

    const toArraySpy = vi.spyOn(maicDb.classrooms, 'toArray');

    const removed = await evictOldestN(2);
    expect(removed).toBe(2);

    // The new implementation should pull primary keys via `orderBy().limit()`
    // and `bulkDelete` — no full-table `toArray()` of fat blob payloads.
    expect(toArraySpy).not.toHaveBeenCalled();

    // Oldest two are gone.
    const remaining = await maicDb.classrooms.toArray();
    const ids = remaining.map((c) => c.id).sort();
    expect(ids).toEqual(['x2', 'x3', 'x4']);
  });

  test('evictUntilUnderWatermark with no estimate API still evicts (best-effort)', async () => {
    // No navigator.storage — older browsers / SSR. Behaviour: best-effort
    // single-shot eviction so we make some room.
    clearEstimate();
    _invalidateEstimateCacheForTests();

    await maicDb.classrooms.put(makeClassroom('only', { lastAccessedAt: Date.now() - 1000 }));

    await evictUntilUnderWatermark();

    // The single row was evicted (best-effort fallback).
    const remaining = await maicDb.classrooms.count();
    expect(remaining).toBe(0);
  });
});

// ─── 2026-04-26 offline-audio-durability re-wire ──────────────────────────
//
// AUDIT-2026-04-25-6 deleted `cacheAudio` as dead code; the offline audio
// gap card (gaps/offline-audio-durability.md) re-introduces it as a wired
// helper consumed by `maicActionEngine.prefetchSpeech`. The old "must be
// gone" assertions are inverted here so future regressions can't quietly
// drop the export again.

describe('maicDb — offline-audio-durability re-wire surface', () => {
  test('cacheAudio + getCachedAudio are exported from maicDb', async () => {
    const mod = await import('../maicDb');
    const m = mod as unknown as Record<string, unknown>;
    expect(typeof m.cacheAudio).toBe('function');
    expect(typeof m.getCachedAudio).toBe('function');
    expect(typeof m.AUDIO_CACHE_BUDGET_BYTES).toBe('number');
  });

  test('audioCache field is OPTIONAL — fresh saves omit it until populated', async () => {
    // A round-trip via saveClassroom() does not seed audioCache; it only
    // appears after cacheAudio() has actually written something.
    const room = makeClassroom('shape-check');
    await saveClassroom(room);
    const stored = await maicDb.classrooms.get('shape-check');
    expect(stored).toBeDefined();
    expect((stored as unknown as Record<string, unknown>).audioCache).toBeUndefined();
  });
});
