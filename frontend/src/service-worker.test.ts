/**
 * service-worker.test.ts
 *
 * Unit tests for frontend/public/service-worker.js using a node:vm sandbox.
 *
 * The SW source is read as text and evaluated inside a vm.Context that stubs
 * the Service-Worker globals (self, caches, fetch, Request, Response,
 * location).  This lets us exercise the core logic functions without a real
 * browser environment:
 *
 *   • isImageRequest()           — URL matcher
 *   • imageStaleWhileRevalidate() — stale-while-revalidate + LRU eviction
 *   • Authorization-skip         — early return before image-request branch
 *
 * Coverage targets (SPRINT-2-BATCH-2-F4):
 *   ≥5 isImageRequest cases
 *   LRU eviction at 50 entries (oldest deleted, newest kept)
 *   imageStaleWhileRevalidate cache-HIT, cache-MISS, non-200, fetch-throws
 *   Authorization header bypass
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import * as fs from 'node:fs';
import * as vm from 'node:vm';
import * as path from 'node:path';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Minimal mock of the Cache interface. */
function makeMockCache(initialKeys: string[] = []) {
  const store = new Map<string, object>();
  // Pre-populate for LRU tests
  for (const k of initialKeys) {
    store.set(k, { url: k });
  }

  // SPRINT-2-BATCH-4-F4: keys() walks the live _store Map so that put-then-evict
  // integration is tested rather than eviction-in-isolation. The LRU test can
  // still override keys() with vi.fn() if it needs to pre-set a specific snapshot,
  // but the default is now fully integrated with the real put() above.
  const cache = {
    _store: store,
    match: vi.fn(async (_req: object) => undefined as object | undefined),
    put: vi.fn(async (req: { url: string } | string, _res: object) => {
      const key = typeof req === 'string' ? req : req.url;
      store.set(key, _res as object);
    }),
    delete: vi.fn(async (req: { url: string } | string) => {
      const key = typeof req === 'string' ? req : req.url;
      return store.delete(key);
    }),
    // keys() returns request-like objects reflecting the current _store state.
    // Because put() above mutates `store`, this naturally models put-then-evict:
    // the SW calls put(), then keys() to check the count, seeing the newly-added
    // entry in the list — exercising true integration rather than a static mock.
    keys: vi.fn(async () =>
      Array.from(store.keys()).map((url) => ({ url })),
    ),
  };
  return cache;
}

type MockCache = ReturnType<typeof makeMockCache>;

/** Build a vm.Context with stubbed SW globals and return the evaluated SW exports. */
function buildSWContext(overrides: {
  imageCache?: MockCache;
  fetchImpl?: (req: object) => Promise<object>;
}) {
  const swSrc = fs.readFileSync(
    path.resolve(__dirname, '../public/service-worker.js'),
    'utf-8',
  );

  // Stubs for globals the SW uses at evaluation time
  const selfStub: Record<string, unknown> = {
    addEventListener: vi.fn(),
    skipWaiting: vi.fn(),
    clients: { claim: vi.fn(), matchAll: vi.fn(async () => []) },
    registration: { showNotification: vi.fn(), sync: null },
    location: { origin: 'https://demo.learnpuddle.com' },
  };

  const imageCache = overrides.imageCache ?? makeMockCache();

  const cachesStub = {
    open: vi.fn(async (name: string) => {
      // Return imageCache for the IMAGE_CACHE name, a generic one otherwise
      if (name.startsWith('brain-lms-images')) return imageCache;
      return makeMockCache();
    }),
    match: vi.fn(async (_req: object, opts?: { cacheName?: string }) => {
      if (opts?.cacheName?.startsWith('brain-lms-images')) {
        return imageCache.match(_req);
      }
      return undefined;
    }),
    keys: vi.fn(async () => []),
    delete: vi.fn(async () => true),
  };

  const fetchStub = overrides.fetchImpl ?? vi.fn(async () => ({ ok: true, status: 200, clone: () => ({}) }));

  const context = vm.createContext({
    self: selfStub,
    caches: cachesStub,
    fetch: fetchStub,
    location: { origin: 'https://demo.learnpuddle.com' },
    // Minimal Request / Response stubs
    Request: class MockRequest {
      url: string;
      method: string;
      mode: string;
      headers: { has: (k: string) => boolean; get: (k: string) => string | null };
      constructor(
        url: string,
        init: { method?: string; mode?: string; headers?: Record<string, string>; credentials?: string } = {},
      ) {
        this.url = url;
        this.method = init.method ?? 'GET';
        this.mode = init.mode ?? 'cors';
        // Normalise to lower-case keys so that `headers.has` is case-insensitive,
        // matching the behaviour of the real browser Headers API.
        // (SPRINT-2-BATCH-4-F3: a SW change to `headers.has('authorization')` must
        // behave identically to `headers.has('Authorization')`.)
        const hdrs: Record<string, string> = {};
        for (const [k, v] of Object.entries(init.headers ?? {})) {
          hdrs[k.toLowerCase()] = v;
        }
        this.headers = {
          has: (k: string) => k.toLowerCase() in hdrs,
          get: (k: string) => hdrs[k.toLowerCase()] ?? null,
        };
      }
    },
    Response: class MockResponse {
      ok: boolean;
      status: number;
      body: unknown;
      constructor(body?: unknown, init: { status?: number; headers?: Record<string, string> } = {}) {
        this.status = init.status ?? 200;
        this.ok = this.status >= 200 && this.status < 300;
        this.body = body;
      }
      clone() { return Object.assign(Object.create(Object.getPrototypeOf(this)), this); }
      json() { return Promise.resolve(this.body); }
      text() { return Promise.resolve(String(this.body)); }
    },
    URL: URL,
    Promise: Promise,
    console: { log: () => {}, warn: () => {}, error: () => {} },
  });

  vm.runInContext(swSrc, context);

  return { context, cachesStub, imageCache, fetchStub };
}

// ---------------------------------------------------------------------------
// isImageRequest tests (≥5 cases)
// ---------------------------------------------------------------------------

describe('isImageRequest()', () => {
  let isImageRequest: (pathname: string) => boolean;

  beforeEach(() => {
    const { context } = buildSWContext({});
    isImageRequest = context.isImageRequest as (p: string) => boolean;
  });

  it('returns true for .png extension', () => {
    expect(isImageRequest('/static/logo.png')).toBe(true);
  });

  it('returns true for .jpg extension', () => {
    expect(isImageRequest('/assets/photo.jpg')).toBe(true);
  });

  it('returns true for /media/ path without image extension', () => {
    // /media/ uploads might lack extensions but should still be cached
    expect(isImageRequest('/media/tenant/42/uploads/course-thumbnail/abc')).toBe(true);
  });

  it('returns true for .webp extension', () => {
    expect(isImageRequest('/maic/scene.webp')).toBe(true);
  });

  it('returns true for .svg extension', () => {
    expect(isImageRequest('/icons/icon.svg')).toBe(true);
  });

  it('returns true for .avif extension', () => {
    expect(isImageRequest('/images/hero.avif')).toBe(true);
  });

  it('returns false for a JS file path', () => {
    expect(isImageRequest('/static/main.js')).toBe(false);
  });

  it('returns false for an API path', () => {
    expect(isImageRequest('/api/v1/courses/')).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// LRU eviction at IMAGE_CACHE_MAX_ENTRIES (50)
// ---------------------------------------------------------------------------

describe('imageStaleWhileRevalidate() — LRU eviction', () => {
  it('deletes oldest entry when cache has 51 entries after a new put (put-then-evict integration)', async () => {
    // SPRINT-2-BATCH-4-F4: keys() now walks the live _store Map so this test
    // exercises true put-then-evict integration rather than eviction-in-isolation.
    // The SW calls put() (which adds img-50 to _store), then keys() which returns
    // 51 entries from the real _store, then delete() on the oldest — without any
    // manual keys() override.

    // Pre-populate cache with 50 entries (keys url-0 … url-49) in insertion order.
    const preKeys = Array.from({ length: 50 }, (_, i) => `https://demo.learnpuddle.com/media/img-${i}.png`);
    const imageCache = makeMockCache(preKeys);

    // No keys() override — the default implementation reads _store, which put() mutates.
    const newUrl = 'https://demo.learnpuddle.com/media/img-50.png';

    const fetchImpl = vi.fn(async () => ({
      ok: true,
      status: 200,
      clone: () => ({ ok: true, status: 200 }),
    }));

    const { context } = buildSWContext({ imageCache, fetchImpl });
    const imageStaleWhileRevalidate = context.imageStaleWhileRevalidate as (req: object) => Promise<object>;

    const MockRequest = context.Request as new (url: string) => { url: string; headers: { has: () => boolean } };
    const req = new MockRequest(newUrl);

    // Cache miss on the initial lookup
    imageCache.match = vi.fn(async () => undefined);

    await imageStaleWhileRevalidate(req);

    // put() must have been called — which added img-50 to _store (now 51 entries).
    expect(imageCache.put).toHaveBeenCalledOnce();

    // keys() must have seen 51 entries (the 50 pre-populated + the newly put one).
    // The SW then calls delete() for the OLDEST entry (img-0), not any newer one.
    const deletedKeys = (imageCache.delete as ReturnType<typeof vi.fn>).mock.calls.map(
      (call: [{ url: string }]) => call[0].url,
    );
    expect(deletedKeys).toContain(`https://demo.learnpuddle.com/media/img-0.png`);
    // Newest entry must NOT be deleted
    expect(deletedKeys).not.toContain(newUrl);
  });
});

// ---------------------------------------------------------------------------
// imageStaleWhileRevalidate() — cache HIT / MISS / non-200 / fetch-throws
// ---------------------------------------------------------------------------

describe('imageStaleWhileRevalidate() — caching behaviour', () => {
  it('cache HIT: returns cached response immediately (no waiting for network)', async () => {
    const cachedResponse = { ok: true, status: 200, body: 'cached' };
    const imageCache = makeMockCache();
    imageCache.match = vi.fn(async () => cachedResponse as object);

    // fetch resolves slowly but we should get cached response first
    const fetchImpl = vi.fn(
      () => new Promise<object>((resolve) => setTimeout(() => resolve({ ok: true, status: 200, clone: () => ({}) }), 100)),
    );

    const { context } = buildSWContext({ imageCache, fetchImpl });
    const imageStaleWhileRevalidate = context.imageStaleWhileRevalidate as (req: object) => Promise<object>;
    const MockRequest = context.Request as new (url: string) => object;

    const result = await imageStaleWhileRevalidate(new MockRequest('https://demo.learnpuddle.com/media/hit.png'));
    expect(result).toBe(cachedResponse);
  });

  it('cache MISS: waits on network and stores a 200 response', async () => {
    const imageCache = makeMockCache();
    imageCache.match = vi.fn(async () => undefined);

    const networkResponse = { ok: true, status: 200, clone: () => networkResponse };
    const fetchImpl = vi.fn(async () => networkResponse);

    const { context } = buildSWContext({ imageCache, fetchImpl });
    const imageStaleWhileRevalidate = context.imageStaleWhileRevalidate as (req: object) => Promise<object>;
    const MockRequest = context.Request as new (url: string) => object;

    const result = await imageStaleWhileRevalidate(new MockRequest('https://demo.learnpuddle.com/media/miss.png'));

    expect(result).toBe(networkResponse);
    // put() must have been called to store the response
    expect(imageCache.put).toHaveBeenCalledOnce();
  });

  it('cache MISS + non-200 response: does NOT store in cache', async () => {
    const imageCache = makeMockCache();
    imageCache.match = vi.fn(async () => undefined);

    const notFoundResponse = { ok: false, status: 404, clone: () => notFoundResponse };
    const fetchImpl = vi.fn(async () => notFoundResponse);

    const { context } = buildSWContext({ imageCache, fetchImpl });
    const imageStaleWhileRevalidate = context.imageStaleWhileRevalidate as (req: object) => Promise<object>;
    const MockRequest = context.Request as new (url: string) => object;

    await imageStaleWhileRevalidate(new MockRequest('https://demo.learnpuddle.com/media/broken.png'));

    // put() must NOT have been called for a non-200 response
    expect(imageCache.put).not.toHaveBeenCalled();
  });

  it('cache MISS + fetch throws: resolves to null (no crash, no cache store)', async () => {
    const imageCache = makeMockCache();
    imageCache.match = vi.fn(async () => undefined);

    const fetchImpl = vi.fn(async () => { throw new Error('Network error'); });

    const { context } = buildSWContext({ imageCache, fetchImpl });
    const imageStaleWhileRevalidate = context.imageStaleWhileRevalidate as (req: object) => Promise<object | null>;
    const MockRequest = context.Request as new (url: string) => object;

    const result = await imageStaleWhileRevalidate(new MockRequest('https://demo.learnpuddle.com/media/network-err.png'));

    expect(result).toBeNull();
    expect(imageCache.put).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Authorization-skip — request bypasses SW logic entirely
// ---------------------------------------------------------------------------

describe('Authorization header skip', () => {
  it('skips SW processing for requests with Authorization header', () => {
    /**
     * The Authorization early-return lives inside the 'fetch' event handler,
     * not in an exported function.  We test it by inspecting the registered
     * fetch event handler logic.
     *
     * Strategy: build a minimal respondWith / waitUntil capture, then fire a
     * synthetic fetch event with an Authorization-bearing request and verify
     * that respondWith() is NEVER called.
     */
    const respondWith = vi.fn();
    const waitUntil = vi.fn();

    // We need to extract the fetch handler registered via self.addEventListener
    const fetchHandlers: Array<(event: object) => void> = [];
    const selfStub = {
      addEventListener: vi.fn((type: string, handler: (event: object) => void) => {
        if (type === 'fetch') fetchHandlers.push(handler);
      }),
      skipWaiting: vi.fn(),
      clients: { claim: vi.fn(), matchAll: vi.fn(async () => []) },
      registration: { showNotification: vi.fn(), sync: null },
      location: { origin: 'https://demo.learnpuddle.com' },
    };

    const swSrc = fs.readFileSync(
      path.resolve(__dirname, '../public/service-worker.js'),
      'utf-8',
    );

    const context = vm.createContext({
      self: selfStub,
      caches: { open: vi.fn(), match: vi.fn(), keys: vi.fn(async () => []), delete: vi.fn() },
      fetch: vi.fn(),
      location: { origin: 'https://demo.learnpuddle.com' },
      Request: class {
        url: string; method: string; mode: string;
        headers: { has: (k: string) => boolean };
        constructor(url: string, init: { method?: string; headers?: Record<string, string> } = {}) {
          this.url = url; this.method = init.method ?? 'GET'; this.mode = 'cors';
          // Case-insensitive, matching real browser Headers API.
          // (SPRINT-2-BATCH-4-F3)
          const h: Record<string, string> = {};
          for (const [k, v] of Object.entries(init.headers ?? {})) {
            h[k.toLowerCase()] = v;
          }
          this.headers = { has: (k: string) => k.toLowerCase() in h };
        }
      },
      Response: class {
        status: number; ok: boolean;
        constructor(_body?: unknown, init: { status?: number } = {}) {
          this.status = init.status ?? 200; this.ok = this.status < 300;
        }
        clone() { return this; }
      },
      URL: URL,
      Promise: Promise,
      console: { log: () => {}, warn: () => {}, error: () => {} },
    });

    vm.runInContext(swSrc, context);

    // There should be exactly one fetch handler registered
    expect(fetchHandlers.length).toBeGreaterThan(0);

    const fetchHandler = fetchHandlers[0];

    // Fire with an Authorization-bearing GET request
    const authRequest = new (context.Request as new (url: string, init: object) => object)(
      'https://demo.learnpuddle.com/media/protected.png',
      { method: 'GET', headers: { Authorization: 'Bearer tok123' } },
    );

    fetchHandler({ request: authRequest, respondWith, waitUntil });

    // respondWith must NOT have been called — the handler returned early
    expect(respondWith).not.toHaveBeenCalled();
  });
});
