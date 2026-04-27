// lib/maicDb.ts — Client-side IndexedDB storage for MAIC classroom content.
//
// PERF-P0-6 (2026-04-25): Added proactive IndexedDB quota management with LRU
// eviction. The MAIC player caches scenes, audio blobs, and image URLs inside
// `StoredClassroom.slides`/`scenes`. On long sessions or low-storage devices
// this can grow unbounded and trigger `QuotaExceededError`. The quota manager:
//
//   1. On every write, calls `navigator.storage.estimate()` (cached for
//      STORAGE_ESTIMATE_TTL_MS, default 5 s — AUDIT-2026-04-25-5). When
//      `usage / quota > QUOTA_HIGH_WATERMARK` (0.8) it evicts oldest entries
//      (by `lastAccessedAt`) until the ratio drops below
//      `QUOTA_LOW_WATERMARK` (0.6).
//   2. If a write still throws `QuotaExceededError`, it falls back to evicting
//      25% of the oldest entries and retries the write exactly once.
//      The estimate cache is invalidated on QuotaExceededError so the post-
//      eviction retry gets a fresh number.
//   3. `lastAccessedAt` is bumped on every `getStoredClassroom()` so frequently
//      accessed classrooms are kept.
//   4. Eviction is async-safe: a single shared promise serialises eviction so
//      concurrent writes don't double-evict.
//   5. Eviction uses a two-pass batch algorithm (AUDIT-2026-04-25-7): one
//      estimate call to compute the batch size, one re-estimate to verify.
//      `evictOldestN` uses `orderBy().limit().primaryKeys()` so it never
//      pulls full rows into memory.
//
// `purgeAll()` is exported for a manual "Clear cache" admin action.

import Dexie, { type Table } from 'dexie';
import type { MAICSlide, MAICAgent, MAICOutlineScene, MAICChatMessage } from '../types/maic';
import type { MAICScene, SceneSlideBounds } from '../types/maic-scenes';

export interface StoredClassroom {
  id: string;
  title: string;
  slides: MAICSlide[];
  scenes: MAICScene[];
  outlines: MAICOutlineScene[];
  agents: MAICAgent[];
  chatHistory: MAICChatMessage[];
  /**
   * Offline-audio-durability re-wire (2026-04-26): TTS ArrayBuffers keyed by
   * a deterministic per-utterance cache key (typically `voiceId::text`). The
   * field is OPTIONAL — older rows written before the re-wire never had it,
   * and rows for non-classroom uses (chat-only sessions, etc.) skip it.
   *
   * Total byte size across all classrooms is gated by AUDIO_CACHE_BUDGET_BYTES
   * inside `cacheAudio`; classroom-level eviction (`evictOldestN`) drops the
   * audioCache field along with the row.
   */
  audioCache?: Record<string, ArrayBuffer>;
  config: Record<string, unknown>;
  /** Maps each scene to its slide range in the flat slides[] array */
  sceneSlideBounds?: SceneSlideBounds[];
  syncedAt: number;
  /** LRU tracking: bumped on every read so frequently-accessed entries are kept. */
  lastAccessedAt?: number;
}

class MAICDatabase extends Dexie {
  classrooms!: Table<StoredClassroom, string>;

  constructor() {
    super('learnpuddle-maic');
    this.version(1).stores({
      classrooms: 'id, title, syncedAt',
    });
    // v2: adds scenes field (non-indexed, so no schema change needed — Dexie
    // stores all fields regardless, but bumping version signals the upgrade)
    this.version(2).stores({
      classrooms: 'id, title, syncedAt',
    }).upgrade((tx) => {
      return tx.table('classrooms').toCollection().modify((classroom) => {
        if (!classroom.scenes) {
          classroom.scenes = [];
        }
      });
    });

    // v3: adds sceneSlideBounds for multi-slide scene support
    // Non-indexed field — Dexie stores all fields regardless, but version bump
    // triggers the upgrade to backfill legacy 1:1 classrooms
    this.version(3).stores({
      classrooms: 'id, title, syncedAt',
    }).upgrade((tx) => {
      return tx.table('classrooms').toCollection().modify((classroom) => {
        if (!classroom.sceneSlideBounds) {
          // Backward compat: legacy classrooms have 1 slide per scene
          classroom.sceneSlideBounds = (classroom.scenes || []).map((_: unknown, i: number) => ({
            sceneIdx: i,
            startSlide: i,
            endSlide: i,
          }));
        }
      });
    });

    // v4 (PERF-P0-6): adds `lastAccessedAt` for LRU eviction. Indexed so we can
    // cheaply pull oldest-first via `orderBy('lastAccessedAt')`.
    this.version(4).stores({
      classrooms: 'id, title, syncedAt, lastAccessedAt',
    }).upgrade((tx) => {
      return tx.table('classrooms').toCollection().modify((classroom) => {
        if (typeof classroom.lastAccessedAt !== 'number') {
          // Seed from syncedAt so existing entries get a sensible LRU position.
          classroom.lastAccessedAt = classroom.syncedAt || Date.now();
        }
      });
    });
  }
}

export const maicDb = new MAICDatabase();

// ─── Quota Management ──────────────────────────────────────────────────────

/** Default high-watermark when no env override is set. */
const DEFAULT_HIGH_WATERMARK = 0.8;
/** Default low-watermark when no env override is set. */
const DEFAULT_LOW_WATERMARK = 0.6;

/**
 * PERF-P0-6 follow-up F4: read watermarks from `import.meta.env` so ops can
 * tune them per-deploy without a code change. Validates `0 < low < high <= 1`
 * and falls back to defaults with a one-time `console.warn` if invalid.
 *
 * `getEnv` is a thin indirection so tests can shim `import.meta.env` via
 * `vi.stubEnv`. We re-read on module load only — runtime mutation is not
 * supported (callers cache the exported consts).
 */
function readWatermarksFromEnv(): { high: number; low: number } {
  // Read directly from `import.meta.env` so Vite's static-replacement and
  // vitest's `vi.stubEnv` proxy both see this as a real env access (avoid
  // intermediate casts which can break the transformer's recognition).
  let rawHigh: string | undefined;
  let rawLow: string | undefined;
  try {
    rawHigh = import.meta.env?.VITE_QUOTA_HIGH_WATERMARK;
    rawLow = import.meta.env?.VITE_QUOTA_LOW_WATERMARK;
  } catch {
    /* ignore — fall through with defaults (SSR / non-Vite runtimes) */
  }
  if (rawHigh === undefined && rawLow === undefined) {
    return { high: DEFAULT_HIGH_WATERMARK, low: DEFAULT_LOW_WATERMARK };
  }
  const high = rawHigh === undefined ? DEFAULT_HIGH_WATERMARK : Number(rawHigh);
  const low = rawLow === undefined ? DEFAULT_LOW_WATERMARK : Number(rawLow);
  const valid =
    Number.isFinite(high) &&
    Number.isFinite(low) &&
    high > 0 &&
    high <= 1 &&
    low > 0 &&
    low < high;
  if (!valid) {
    // eslint-disable-next-line no-console
    console.warn(
      `[maicDb] Invalid VITE_QUOTA_*_WATERMARK overrides ` +
        `(high=${rawHigh}, low=${rawLow}); falling back to defaults ` +
        `(${DEFAULT_HIGH_WATERMARK}/${DEFAULT_LOW_WATERMARK}).`,
    );
    return { high: DEFAULT_HIGH_WATERMARK, low: DEFAULT_LOW_WATERMARK };
  }
  return { high, low };
}

const _watermarks = readWatermarksFromEnv();

/** When usage/quota exceeds this ratio, eviction kicks in. */
export const QUOTA_HIGH_WATERMARK = _watermarks.high;
/** Eviction continues until usage/quota drops below this ratio. */
export const QUOTA_LOW_WATERMARK = _watermarks.low;
/** Fraction of oldest entries to evict on QuotaExceededError fallback. */
export const QUOTA_FALLBACK_EVICTION_FRACTION = 0.25;

/**
 * Test-only re-read of env-driven watermarks. Returns the freshly-parsed
 * values without mutating module-level exports (those are frozen at load).
 * Exported so tests can verify validation behaviour with `vi.stubEnv`.
 */
export function _readWatermarksFromEnvForTests(): { high: number; low: number } {
  return readWatermarksFromEnv();
}

interface StorageEstimateLike {
  usage?: number;
  quota?: number;
}

/**
 * Reads `navigator.storage.estimate()` if available. Returns `null` when the
 * browser doesn't expose it (Safari <16, some embedded WebViews, jsdom/happy-dom).
 */
export async function getStorageEstimate(): Promise<StorageEstimateLike | null> {
  try {
    const nav = (globalThis as unknown as { navigator?: Navigator }).navigator;
    const storage = nav?.storage;
    if (!storage || typeof storage.estimate !== 'function') return null;
    const est = await storage.estimate();
    return est ?? null;
  } catch {
    return null;
  }
}

function ratioOf(est: StorageEstimateLike | null): number | null {
  if (!est || !est.quota || est.quota <= 0 || typeof est.usage !== 'number') return null;
  return est.usage / est.quota;
}

// ─── AUDIT-2026-04-25-5: module-level estimate cache ──────────────────────
//
// `navigator.storage.estimate()` takes 10-30 ms on Firefox/Safari. Calling it
// on every chat-history mutation (every keystroke or message send) is wasteful.
// We cache the result for STORAGE_ESTIMATE_TTL_MS and only re-request when the
// cached value is stale. The cache is invalidated immediately after any
// QuotaExceededError (so the post-eviction retry sees a fresh number) and
// after each successful eviction pass.

/** TTL (ms) for the module-level `navigator.storage.estimate()` cache. */
export const STORAGE_ESTIMATE_TTL_MS = 5_000;

interface EstimateCache {
  value: StorageEstimateLike | null;
  ts: number;
}
let _estimateCache: EstimateCache | null = null;

/** Invalidate the estimate cache. Exported for tests only. */
export function _invalidateEstimateCacheForTests(): void {
  _estimateCache = null;
}

/**
 * Like `getStorageEstimate()` but returns a cached result within the TTL.
 * Use this in `withQuotaCheck` to avoid repeated API calls. The eviction loop
 * calls the raw `getStorageEstimate()` directly so it always sees live numbers.
 */
async function getCachedStorageEstimate(): Promise<StorageEstimateLike | null> {
  const now = Date.now();
  if (_estimateCache !== null && now - _estimateCache.ts < STORAGE_ESTIMATE_TTL_MS) {
    return _estimateCache.value;
  }
  const value = await getStorageEstimate();
  _estimateCache = { value, ts: now };
  return value;
}

/**
 * Lock to make eviction async-safe. Concurrent puts share a single eviction
 * promise (PERF-P0-6 follow-up F3 — coalescing pattern: the slot is only
 * cleared inside the worker's `finally`, *after* the promise resolves, so any
 * caller that arrives during the eviction's microtask gap also joins the same
 * promise. New callers arriving after the slot has been cleared start a fresh
 * pass, which is safe and bounded by row count.
 */
let _pendingEvictionPromise: Promise<void> | null = null;

/**
 * Evict oldest entries (by `lastAccessedAt`) until the storage ratio drops
 * below `QUOTA_LOW_WATERMARK`. Safe under concurrent invocation: callers share
 * the in-flight eviction promise (same `Promise` reference) until it settles.
 *
 * AUDIT-2026-04-25-7 — batch eviction algorithm:
 *   Choice: "single-shot batch" — compute N entries from the usage/quota gap
 *   using the average row size (`usage / total`), evict all N in one
 *   `bulkDelete`, then take ONE re-estimate to verify. If still over watermark,
 *   do exactly one more batch. Total estimate API calls: ≤ 2 (not per-row).
 *   This is preferred over the `bytesFreed` tracking approach because entries
 *   don't carry an individual size hint, so per-entry tracking would be as
 *   brittle as per-row estimation.
 */
export function evictUntilUnderWatermark(): Promise<void> {
  if (_pendingEvictionPromise) return _pendingEvictionPromise;
  const pending = (async () => {
    try {
      // Fast path: if we can't estimate, do a single-shot eviction of one
      // oldest entry to make some room (best effort).
      const est = await getStorageEstimate(); // raw — eviction must see live data
      const r = ratioOf(est);
      if (r === null) {
        await evictOldestN(1);
        return;
      }
      if (r <= QUOTA_LOW_WATERMARK) return; // already safe

      const total = await maicDb.classrooms.count();
      if (total === 0) return;

      // --- Batch 1: compute eviction count from average row size ---------------
      // `est` is non-null here: ratioOf() returns null when est is null OR when
      // quota <= 0. Both cases are caught by the `r === null` guard above.
      const usage1 = (est as NonNullable<typeof est>).usage ?? 0;
      const quota1 = (est as NonNullable<typeof est>).quota ?? 1;
      const avg = usage1 / total;
      // Subtract a small epsilon before ceil() to avoid floating-point over-
      // ceiling when the exact result is an integer
      // (e.g. (0.9-0.6)/0.3 = 1.0000000000000002 → ceil = 2 without guard).
      const n1 = avg > 0
        ? Math.ceil(((r - QUOTA_LOW_WATERMARK) * quota1) / avg - 1e-10)
        : total; // no size info → evict everything
      const toEvict1 = Math.max(1, Math.min(n1, total));
      await evictOldestN(toEvict1);

      // --- One verification re-estimate ----------------------------------------
      const est2 = await getStorageEstimate();
      const r2 = ratioOf(est2);
      if (r2 === null || r2 <= QUOTA_LOW_WATERMARK) return;

      // Still over watermark after batch 1 → one more batch with fresh numbers.
      const total2 = await maicDb.classrooms.count();
      if (total2 === 0) return;
      const usage2 = (est2 as NonNullable<typeof est2>).usage ?? 0;
      const quota2 = (est2 as NonNullable<typeof est2>).quota ?? 1;
      const avg2 = usage2 / total2;
      const n2 = avg2 > 0
        ? Math.ceil(((r2 - QUOTA_LOW_WATERMARK) * quota2) / avg2 - 1e-10)
        : total2;
      await evictOldestN(Math.max(1, Math.min(n2, total2)));
    } finally {
      // Invalidate the AUDIT-5 estimate cache after a successful eviction pass
      // so the next write sees post-eviction quota numbers.
      _estimateCache = null;
      // Clear the slot AFTER the promise resolves. Any callers awaiting
      // `_pendingEvictionPromise` see the same resolution. New callers
      // arriving on subsequent ticks start a fresh (possibly no-op) pass.
      _pendingEvictionPromise = null;
    }
  })();
  _pendingEvictionPromise = pending;
  return pending;
}

/**
 * Evict the N oldest classrooms (by `lastAccessedAt`). Returns the number
 * actually deleted.
 *
 * AUDIT-2026-04-25-7: Uses `orderBy('lastAccessedAt').limit(n).primaryKeys()`
 * so only the key column is loaded — no full row materialisation of potentially
 * large blob/slide payloads. `lastAccessedAt` is indexed (added in v4 schema).
 */
export async function evictOldestN(n: number): Promise<number> {
  if (n <= 0) return 0;
  // Pull only primary keys, ordered by lastAccessedAt ascending (oldest first).
  const ids = await maicDb.classrooms
    .orderBy('lastAccessedAt')
    .limit(n)
    .primaryKeys() as string[];
  if (ids.length === 0) return 0;
  await maicDb.classrooms.bulkDelete(ids);
  return ids.length;
}

/**
 * Wraps an IDB write with quota management:
 *  - Pre-flight: if usage/quota > HIGH_WATERMARK, evict before the write.
 *  - On QuotaExceededError: evict 25% of oldest entries and retry once.
 *
 * `op` is invoked at most twice (once normally, once after fallback eviction).
 *
 * AUDIT-2026-04-25-5: Uses `getCachedStorageEstimate()` for the pre-flight
 * check so repeated writes within STORAGE_ESTIMATE_TTL_MS (5 s) skip the
 * 10-30 ms `navigator.storage.estimate()` API call. The cache is invalidated
 * immediately on QuotaExceededError so the post-eviction retry is accurate.
 */
export async function withQuotaCheck<T>(op: () => Promise<T>): Promise<T> {
  const est = await getCachedStorageEstimate();
  const r = ratioOf(est);
  if (r !== null && r > QUOTA_HIGH_WATERMARK) {
    // Best-effort proactive eviction. Failures here are swallowed so the
    // primary write still gets a chance.
    try {
      await evictUntilUnderWatermark();
    } catch {
      /* ignore — fall through to the write */
    }
  }
  try {
    return await op();
  } catch (err) {
    if (isQuotaExceeded(err)) {
      // Invalidate the estimate cache so the next write sees post-eviction numbers.
      _estimateCache = null;
      const total = await maicDb.classrooms.count();
      const fallbackN = Math.max(1, Math.ceil(total * QUOTA_FALLBACK_EVICTION_FRACTION));
      try {
        await evictOldestN(fallbackN);
      } catch {
        /* ignore — surface the original error if retry also fails */
      }
      // Single retry — if this throws too, propagate.
      return await op();
    }
    throw err;
  }
}

function isQuotaExceeded(err: unknown): boolean {
  if (!err || typeof err !== 'object') return false;
  const name = (err as { name?: unknown }).name;
  if (name === 'QuotaExceededError') return true;
  // Dexie wraps errors; check inner DOM exception too.
  const inner = (err as { inner?: unknown }).inner;
  if (inner && typeof inner === 'object' && (inner as { name?: unknown }).name === 'QuotaExceededError') return true;
  // Some Safari builds throw a plain DOMException with code 22.
  const code = (err as { code?: unknown }).code;
  if (code === 22) return true;
  return false;
}

/**
 * Manual purge — wipes every cached classroom. Wire this to a "Clear cache"
 * admin/user action when one exists. Idempotent and safe on an empty DB.
 */
export async function purgeAll(): Promise<void> {
  await maicDb.classrooms.clear();
}

// ─── CRUD Helpers ─────────────────────────────────────────────────────────

export async function getStoredClassroom(id: string): Promise<StoredClassroom | undefined> {
  const row = await maicDb.classrooms.get(id);
  if (row) {
    // Fire-and-forget LRU bump. Failures must not break reads.
    maicDb.classrooms.update(id, { lastAccessedAt: Date.now() }).catch(() => {});
  }
  return row;
}

export async function saveClassroom(classroom: StoredClassroom): Promise<void> {
  await withQuotaCheck(() =>
    maicDb.classrooms.put({
      ...classroom,
      syncedAt: Date.now(),
      lastAccessedAt: Date.now(),
    }),
  );
}

export async function updateClassroomSlides(id: string, slides: MAICSlide[]): Promise<void> {
  await withQuotaCheck(() =>
    maicDb.classrooms.update(id, { slides, syncedAt: Date.now(), lastAccessedAt: Date.now() }),
  );
}

export async function updateClassroomScenes(id: string, scenes: MAICScene[]): Promise<void> {
  await withQuotaCheck(() =>
    maicDb.classrooms.update(id, { scenes, syncedAt: Date.now(), lastAccessedAt: Date.now() }),
  );
}

export async function updateClassroomChat(id: string, chatHistory: MAICChatMessage[]): Promise<void> {
  await withQuotaCheck(() =>
    maicDb.classrooms.update(id, { chatHistory, syncedAt: Date.now(), lastAccessedAt: Date.now() }),
  );
}

export async function deleteStoredClassroom(id: string): Promise<void> {
  await maicDb.classrooms.delete(id);
}

export async function listStoredClassrooms(): Promise<StoredClassroom[]> {
  return maicDb.classrooms.orderBy('syncedAt').reverse().toArray();
}

// ─── Offline Audio Cache ───────────────────────────────────────────────────
//
// Offline-audio-durability re-wire (2026-04-26 P1 gap). The MAIC action
// engine fires-and-forgets `cacheAudio` after every successful TTS prefetch
// so a student who goes offline mid-class still hears prefetched scenes on
// reload. Reads happen via `getCachedAudio` from the live-TTS fetch fallback
// path inside `maicActionEngine.fetchTtsBlob`.
//
// Sizing: the budget is intentionally separate from the IDB watermark quota
// because a single classroom's audioCache can balloon past the row average
// while overall usage is still well below the high-watermark. We track the
// audio byte total ourselves and evict oldest classrooms' audioCache (NOT
// the whole row — chat / scenes survive) when a write would push us over.

/**
 * Soft budget for the total bytes held in `audioCache` across all classrooms.
 * Defaults to 50 MB; ops can override via `VITE_AUDIO_CACHE_BUDGET_BYTES`.
 *
 * Not enforced by Dexie / the browser — purely a self-imposed cap so the
 * audio cache doesn't dominate per-tenant IDB usage. The IDB-wide quota
 * watermark (`QUOTA_HIGH_WATERMARK`) is the hard backstop.
 */
function readAudioBudgetFromEnv(): number {
  const DEFAULT = 50 * 1024 * 1024; // 50 MB
  let raw: string | undefined;
  try {
    raw = import.meta.env?.VITE_AUDIO_CACHE_BUDGET_BYTES;
  } catch {
    return DEFAULT;
  }
  if (raw === undefined) return DEFAULT;
  const n = Number(raw);
  if (!Number.isFinite(n) || n <= 0) {
    // eslint-disable-next-line no-console
    console.warn(
      `[maicDb] Invalid VITE_AUDIO_CACHE_BUDGET_BYTES (${raw}); ` +
        `falling back to default ${DEFAULT}.`,
    );
    return DEFAULT;
  }
  return n;
}

export const AUDIO_CACHE_BUDGET_BYTES = readAudioBudgetFromEnv();

/** Sum the byteLengths of every audioCache buffer across every classroom. */
async function computeAudioCacheTotalBytes(
  exceptClassroomId?: string,
): Promise<number> {
  let total = 0;
  await maicDb.classrooms.each((row) => {
    if (exceptClassroomId !== undefined && row.id === exceptClassroomId) return;
    const cache = row.audioCache;
    if (!cache) return;
    for (const key of Object.keys(cache)) {
      const buf = cache[key];
      if (buf && typeof buf.byteLength === 'number') total += buf.byteLength;
    }
  });
  return total;
}

/**
 * Evict the `audioCache` field on the oldest classrooms (by `lastAccessedAt`)
 * until the cumulative bytes dropped meet or exceed `bytesToFree`. The
 * classroom row itself is preserved — only the audio buffers are dropped, so
 * the student can still see scene/slide metadata for older classrooms.
 *
 * Returns the number of classrooms whose audioCache was cleared.
 */
async function evictAudioCacheUntilUnderBudget(
  bytesToFree: number,
): Promise<number> {
  if (bytesToFree <= 0) return 0;
  let cleared = 0;
  let freed = 0;
  // Bounded scan — even a runaway eviction loop terminates in O(SAFETY_CAP).
  const SAFETY_CAP = 200;
  let scanned = 0;
  await maicDb.classrooms
    .orderBy('lastAccessedAt')
    .until(() => {
      scanned += 1;
      if (scanned > SAFETY_CAP) return true;
      return freed >= bytesToFree;
    })
    .modify((row) => {
      if (!row.audioCache) return;
      const keys = Object.keys(row.audioCache);
      if (keys.length === 0) return;
      let rowBytes = 0;
      for (const k of keys) {
        const b = row.audioCache[k];
        if (b && typeof b.byteLength === 'number') rowBytes += b.byteLength;
      }
      if (rowBytes <= 0) return;
      // Drop this classroom's audioCache entirely — it's the cheapest unit
      // to evict (matches spec: "clear audioCache to {} on older classrooms
      // before deleting whole rows"). The row itself is preserved.
      row.audioCache = {};
      cleared += 1;
      freed += rowBytes;
    });
  return cleared;
}

/**
 * Persist a single TTS audio buffer for `(classroomId, sceneId)`. The
 * `sceneId` parameter is the deterministic per-utterance cache key (the
 * action engine uses `voiceId::text-slice(0,200)` so reads match the
 * in-memory prefetch cache key).
 *
 * Behaviour contract:
 *   - No-op when the classroom row is absent (nothing to attach to).
 *   - No-op when the buffer alone exceeds AUDIO_CACHE_BUDGET_BYTES — a
 *     single payload that dwarfs the budget would force eviction of every
 *     other classroom's audio for nothing.
 *   - Evicts oldest classrooms' audioCache fields before writing if the
 *     total would otherwise exceed the budget.
 *   - Wrapped by `withQuotaCheck` so a real `QuotaExceededError` triggers
 *     the standard quota fallback (25% oldest-row eviction + retry).
 *
 * Fire-and-forget callers (action engine prefetch) should `.catch(() => {})`
 * the returned promise — failures here must not break playback.
 */
export async function cacheAudio(
  classroomId: string,
  sceneId: string,
  buffer: ArrayBuffer,
): Promise<void> {
  if (!buffer || buffer.byteLength === 0) return;
  // Reject single buffers that exceed the entire budget — caching them
  // would force-evict every other classroom's audio for one payload.
  if (buffer.byteLength > AUDIO_CACHE_BUDGET_BYTES) return;

  const row = await maicDb.classrooms.get(classroomId);
  if (!row) return; // graceful: don't ghost-create classroom rows.

  // Compute incoming byte total = (existing total — this classroom's
  // existing buffer for this key, if any) + new buffer size. This handles
  // overwrite correctly: an old buffer at the same key is being replaced.
  const existingBuf = row.audioCache?.[sceneId];
  const existingBytes = existingBuf?.byteLength ?? 0;
  const totalOthers = await computeAudioCacheTotalBytes(classroomId);
  const thisRowBytes =
    Object.values(row.audioCache ?? {}).reduce(
      (acc, b) => acc + (b?.byteLength ?? 0),
      0,
    ) - existingBytes;
  const projected = totalOthers + thisRowBytes + buffer.byteLength;

  if (projected > AUDIO_CACHE_BUDGET_BYTES) {
    // Evict oldest classrooms' audioCache (excluding ours) until under budget.
    await evictAudioCacheUntilUnderBudget(AUDIO_CACHE_BUDGET_BYTES - buffer.byteLength);
  }

  // Re-fetch the row after eviction (the modify may or may not have touched
  // ours — guard both ways).
  const fresh = await maicDb.classrooms.get(classroomId);
  if (!fresh) return;
  const updatedAudioCache: Record<string, ArrayBuffer> = {
    ...(fresh.audioCache ?? {}),
    [sceneId]: buffer,
  };

  await withQuotaCheck(() =>
    maicDb.classrooms.put({
      ...fresh,
      audioCache: updatedAudioCache,
      lastAccessedAt: Date.now(),
    }),
  );
}

/**
 * Look up a previously-cached audio buffer for `(classroomId, sceneId)`.
 * Returns `undefined` when the classroom row, the audioCache field, or the
 * specific key is missing. Cheap: pulls only one row, no eviction work.
 */
export async function getCachedAudio(
  classroomId: string,
  sceneId: string,
): Promise<ArrayBuffer | undefined> {
  const row = await maicDb.classrooms.get(classroomId);
  if (!row || !row.audioCache) return undefined;
  return row.audioCache[sceneId];
}
