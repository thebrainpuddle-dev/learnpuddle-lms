/* eslint-disable no-restricted-globals */
// Service Worker for LearnPuddle PWA
// Provides offline support, caching, background sync, and push notifications

// Auto-replaced by postbuild script with git hash + timestamp on production builds.
// In development, '__BUILD_HASH__' is treated as a static string (caches persist across reloads).
const SW_VERSION = '__BUILD_HASH__';
const CACHE_NAME = `brain-lms-v${SW_VERSION}`;
const STATIC_CACHE = `brain-lms-static-v${SW_VERSION}`;
const DYNAMIC_CACHE = `brain-lms-dynamic-v${SW_VERSION}`;
const API_CACHE = `brain-lms-api-v${SW_VERSION}`;
const OFFLINE_QUEUE_CACHE = 'brain-lms-offline-queue';

// Resources to cache immediately on install
const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/manifest.json',
  '/favicon.ico',
  '/logo192.png',
  '/logo512.png',
  '/offline.html',
];

// Install event - cache static assets
self.addEventListener('install', (event) => {
  console.log('[SW] Installing service worker...');
  
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then((cache) => {
        console.log('[SW] Pre-caching static assets');
        return cache.addAll(STATIC_ASSETS.map(url => {
          return new Request(url, { credentials: 'same-origin' });
        })).catch(err => {
          console.warn('[SW] Some static assets failed to cache:', err);
        });
      })
      .then(() => self.skipWaiting())
  );
});

// Activate event - clean up ALL old caches and force refresh clients
self.addEventListener('activate', (event) => {
  console.log(`[SW] Activating service worker v${SW_VERSION}...`);
  
  const currentCaches = [CACHE_NAME, STATIC_CACHE, DYNAMIC_CACHE, API_CACHE, OFFLINE_QUEUE_CACHE];
  
  event.waitUntil(
    caches.keys()
      .then((keys) => {
        return Promise.all(
          keys
            .filter((key) => !currentCaches.includes(key))
            .map((key) => {
              console.log('[SW] Removing old cache:', key);
              return caches.delete(key);
            })
        );
      })
      .then(() => self.clients.claim())
      // SW_UPDATED postMessage removed: the 'controllerchange' event in the page
      // already triggers window.location.reload() once. Sending SW_UPDATED on top
      // caused a second reload in rapid succession, wiping in-flight state.
  );
});

// Fetch event - serve from cache, fallback to network
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);
  
  // Skip non-GET requests
  if (request.method !== 'GET') {
    return;
  }
  
  // Skip cross-origin requests
  if (url.origin !== location.origin) {
    return;
  }
  
  // Never intercept API calls in the service worker.
  // API auth/session flow must always go directly browser -> origin to avoid
  // replay/amplification behavior during token/session transitions.
  if (url.pathname.startsWith('/api/')) {
    return;
  }
  
  // Handle static assets
  if (isStaticAsset(url.pathname)) {
    event.respondWith(cacheFirstStrategy(request));
    return;
  }
  
  // Handle navigation requests (SPA)
  if (request.mode === 'navigate') {
    event.respondWith(
      caches.match('/index.html')
        .then((cachedResponse) => {
          return cachedResponse || fetch(request).catch(() => caches.match('/offline.html'));
        })
    );
    return;
  }
  
  // Default: stale-while-revalidate
  event.respondWith(staleWhileRevalidate(request));
});

// Cache-first strategy (for static assets)
async function cacheFirstStrategy(request) {
  const cachedResponse = await caches.match(request);
  
  if (cachedResponse) {
    return cachedResponse;
  }
  
  try {
    const networkResponse = await fetch(request);
    
    if (networkResponse.ok) {
      const cache = await caches.open(STATIC_CACHE);
      cache.put(request, networkResponse.clone());
    }
    
    return networkResponse;
  } catch (error) {
    console.warn('[SW] Cache-first fetch failed:', request.url);
    return new Response('Offline', { status: 503 });
  }
}

// Stale-while-revalidate strategy
async function staleWhileRevalidate(request) {
  const cachedResponse = await caches.match(request);
  
  const fetchPromise = fetch(request)
    .then(async (networkResponse) => {
      if (networkResponse.ok) {
        // Clone BEFORE the response body can be consumed
        // This prevents "Response body is already used" errors
        const responseToCache = networkResponse.clone();
        const cache = await caches.open(DYNAMIC_CACHE);
        cache.put(request, responseToCache);

        // LRU cache eviction: keep dynamic cache under 100 entries
        const keys = await cache.keys();
        if (keys.length > 100) {
          await cache.delete(keys[0]); // Remove oldest entry
        }
      }
      return networkResponse;
    })
    .catch(() => null);
  
  return cachedResponse || fetchPromise;
}

// Check if URL is a static asset
function isStaticAsset(pathname) {
  return /\.(js|css|png|jpg|jpeg|gif|svg|woff|woff2|ttf|eot|ico)$/i.test(pathname);
}

// Push notification handling
self.addEventListener('push', (event) => {
  console.log('[SW] Push notification received');
  
  let data = {
    title: 'LearnPuddle',
    body: 'You have a new notification',
    icon: '/logo192.png',
    badge: '/logo192.png',
    data: {},
  };
  
  if (event.data) {
    try {
      data = { ...data, ...event.data.json() };
    } catch (e) {
      data.body = event.data.text();
    }
  }
  
  const options = {
    body: data.body,
    icon: data.icon,
    badge: data.badge,
    vibrate: [100, 50, 100],
    data: data.data,
    actions: data.actions || [],
    tag: data.tag || 'default',
    renotify: true,
  };
  
  event.waitUntil(
    self.registration.showNotification(data.title, options)
  );
});

// Notification click handling
self.addEventListener('notificationclick', (event) => {
  console.log('[SW] Notification clicked');
  
  event.notification.close();
  
  const urlToOpen = event.notification.data?.url || '/';
  
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true })
      .then((clientList) => {
        // Focus existing window if available
        for (const client of clientList) {
          if (client.url.includes(self.location.origin) && 'focus' in client) {
            client.navigate(urlToOpen);
            return client.focus();
          }
        }
        
        // Open new window
        if (self.clients.openWindow) {
          return self.clients.openWindow(urlToOpen);
        }
      })
  );
});

// Background sync for offline actions
self.addEventListener('sync', (event) => {
  console.log('[SW] Background sync:', event.tag);

  if (event.tag === 'sync-offline-queue') {
    event.waitUntil(replayOfflineQueue());
  }
});

// Replay queued offline mutations when connectivity is restored.
// Each entry in the offline-queue cache stores a JSON payload with
// { url, method, headers, body, timestamp }.
async function replayOfflineQueue() {
  try {
    const cache = await caches.open(OFFLINE_QUEUE_CACHE);
    const keys = await cache.keys();

    const results = { synced: 0, failed: 0 };

    for (const request of keys) {
      try {
        const cached = await cache.match(request);
        if (!cached) continue;

        const entry = await cached.json();

        const response = await fetch(entry.url, {
          method: entry.method || 'POST',
          headers: entry.headers || { 'Content-Type': 'application/json' },
          body: entry.body ? JSON.stringify(entry.body) : undefined,
          credentials: 'same-origin',
        });

        if (response.ok || (response.status >= 400 && response.status < 500)) {
          // Remove from queue on success or client error (retrying won't help)
          await cache.delete(request);
          results.synced++;
          console.log('[SW] Replayed offline request:', entry.url);
        } else {
          results.failed++;
          console.warn('[SW] Replay failed (will retry):', entry.url, response.status);
        }
      } catch (err) {
        results.failed++;
        console.warn('[SW] Replay network error:', err);
      }
    }

    // Notify all clients about sync results
    const clients = await self.clients.matchAll({ type: 'window' });
    for (const client of clients) {
      client.postMessage({
        type: 'OFFLINE_QUEUE_SYNCED',
        synced: results.synced,
        failed: results.failed,
      });
    }
  } catch (error) {
    console.error('[SW] Offline queue replay failed:', error);
  }
}

// Message handling from main app
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
  
  if (event.data && event.data.type === 'CACHE_URLS') {
    event.waitUntil(
      caches.open(DYNAMIC_CACHE)
        .then((cache) => cache.addAll(event.data.urls))
    );
  }
  
  if (event.data && event.data.type === 'GET_VERSION') {
    event.ports[0].postMessage({ version: SW_VERSION });
  }
  
  if (event.data && event.data.type === 'CLEAR_ALL_CACHES') {
    event.waitUntil(
      caches.keys().then((keys) => {
        return Promise.all(keys.map((key) => caches.delete(key)));
      }).then(() => {
        console.log('[SW] All caches cleared');
        if (event.ports[0]) {
          event.ports[0].postMessage({ cleared: true });
        }
      })
    );
  }

  // Queue a mutation for offline replay.
  // Payload: { url, method, headers, body, timestamp }
  if (event.data && event.data.type === 'QUEUE_OFFLINE_MUTATION') {
    const entry = event.data.payload;
    event.waitUntil(
      caches.open(OFFLINE_QUEUE_CACHE).then(async (cache) => {
        // Cap queue at 100 entries — drop oldest if full
        const keys = await cache.keys();
        if (keys.length >= 100) {
          await cache.delete(keys[0]);
        }

        const key = `${entry.url}__${entry.timestamp || Date.now()}`;
        return cache.put(
          new Request(key),
          new Response(JSON.stringify(entry), {
            headers: { 'Content-Type': 'application/json' },
          })
        );
      }).then(() => {
        console.log('[SW] Queued offline mutation:', entry.url);
        // Register for background sync if available
        if (self.registration.sync) {
          return self.registration.sync.register('sync-offline-queue');
        }
      })
    );
  }

  // Return the current offline queue size
  if (event.data && event.data.type === 'GET_OFFLINE_QUEUE_SIZE') {
    event.waitUntil(
      caches.open(OFFLINE_QUEUE_CACHE).then((cache) => {
        return cache.keys();
      }).then((keys) => {
        if (event.ports[0]) {
          event.ports[0].postMessage({ size: keys.length });
        }
      })
    );
  }
});
