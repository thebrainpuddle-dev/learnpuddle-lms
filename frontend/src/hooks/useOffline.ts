// hooks/useOffline.ts
/**
 * Offline support hook.
 *
 * Provides:
 * - Online/offline status detection
 * - Mutation queue for offline API calls
 * - Automatic replay of queued mutations when back online
 * - Pending queue count for UI indicators
 */

import { useState, useEffect, useCallback, useRef } from 'react';

export interface OfflineMutation {
  /** Full URL to call when back online */
  url: string;
  /** HTTP method (default: POST) */
  method?: string;
  /** Request headers */
  headers?: Record<string, string>;
  /** JSON-serializable request body */
  body?: unknown;
  /** Timestamp when the mutation was queued */
  timestamp: number;
  /** Optional label shown in the offline queue UI */
  label?: string;
}

interface UseOfflineReturn {
  /** Whether the browser currently has network connectivity */
  isOnline: boolean;
  /** Number of mutations waiting to be replayed */
  pendingCount: number;
  /** Queue a mutation for later replay */
  queueMutation: (mutation: Omit<OfflineMutation, 'timestamp'>) => void;
  /** Manually trigger replay of all queued mutations */
  replayQueue: () => Promise<void>;
}

const QUEUE_STORAGE_KEY = 'learnpuddle-offline-queue';

/**
 * Read the queue from localStorage (fallback when SW is unavailable).
 */
function readLocalQueue(): OfflineMutation[] {
  try {
    const raw = localStorage.getItem(QUEUE_STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

/**
 * Write the queue to localStorage.
 */
function writeLocalQueue(queue: OfflineMutation[]): void {
  try {
    localStorage.setItem(QUEUE_STORAGE_KEY, JSON.stringify(queue));
  } catch {
    // Storage full or unavailable — drop silently
  }
}

export function useOffline(): UseOfflineReturn {
  const [isOnline, setIsOnline] = useState(navigator.onLine);
  const [pendingCount, setPendingCount] = useState(0);
  const replayingRef = useRef(false);

  // ------------------------------------------------------------------
  // Online / Offline listeners
  // ------------------------------------------------------------------
  useEffect(() => {
    const handleOnline = () => setIsOnline(true);
    const handleOffline = () => setIsOnline(false);

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, []);

  // ------------------------------------------------------------------
  // Keep pending count in sync
  // ------------------------------------------------------------------
  const refreshPendingCount = useCallback(() => {
    // Try the service worker first
    if ('serviceWorker' in navigator && navigator.serviceWorker.controller) {
      const channel = new MessageChannel();
      channel.port1.onmessage = (event) => {
        if (event.data && typeof event.data.size === 'number') {
          setPendingCount(event.data.size);
        }
      };
      navigator.serviceWorker.controller.postMessage(
        { type: 'GET_OFFLINE_QUEUE_SIZE' },
        [channel.port2],
      );
    } else {
      // Fallback to localStorage
      setPendingCount(readLocalQueue().length);
    }
  }, []);

  useEffect(() => {
    refreshPendingCount();
  }, [refreshPendingCount]);

  // Listen for SW sync completion messages
  useEffect(() => {
    if (!('serviceWorker' in navigator)) return;

    const handler = (event: MessageEvent) => {
      if (event.data?.type === 'OFFLINE_QUEUE_SYNCED') {
        refreshPendingCount();
      }
    };

    navigator.serviceWorker.addEventListener('message', handler);
    return () => navigator.serviceWorker.removeEventListener('message', handler);
  }, [refreshPendingCount]);

  // ------------------------------------------------------------------
  // Queue a mutation
  // ------------------------------------------------------------------
  const queueMutation = useCallback(
    (mutation: Omit<OfflineMutation, 'timestamp'>) => {
      const entry: OfflineMutation = {
        ...mutation,
        timestamp: Date.now(),
      };

      // Delegate to the service worker if available
      if ('serviceWorker' in navigator && navigator.serviceWorker.controller) {
        navigator.serviceWorker.controller.postMessage({
          type: 'QUEUE_OFFLINE_MUTATION',
          payload: entry,
        });
      } else {
        // Fallback: persist in localStorage
        const queue = readLocalQueue();
        // Cap queue at 100 entries — drop oldest if full
        if (queue.length >= 100) {
          queue.shift();
        }
        queue.push(entry);
        writeLocalQueue(queue);
      }

      setPendingCount((prev) => prev + 1);
    },
    [],
  );

  // ------------------------------------------------------------------
  // Replay the queue (manual trigger or called on reconnect)
  // ------------------------------------------------------------------
  const replayQueue = useCallback(async () => {
    if (replayingRef.current) return;
    replayingRef.current = true;

    try {
      // If the SW supports background sync, let it handle replay
      if (
        'serviceWorker' in navigator &&
        navigator.serviceWorker.controller &&
        'SyncManager' in window
      ) {
        const reg = await navigator.serviceWorker.ready;
        await (reg as any).sync.register('sync-offline-queue');
        // The SW will postMessage OFFLINE_QUEUE_SYNCED when done
        return;
      }

      // Otherwise, replay from localStorage directly
      const queue = readLocalQueue();
      if (queue.length === 0) return;

      const remaining: OfflineMutation[] = [];

      for (const entry of queue) {
        try {
          const response = await fetch(entry.url, {
            method: entry.method || 'POST',
            headers: entry.headers || { 'Content-Type': 'application/json' },
            body: entry.body ? JSON.stringify(entry.body) : undefined,
            credentials: 'same-origin',
          });

          if (!response.ok && response.status >= 500) {
            // Server error — keep for retry
            remaining.push(entry);
          }
          // 2xx or 4xx — consider handled
        } catch {
          // Network still down — keep for retry
          remaining.push(entry);
        }
      }

      writeLocalQueue(remaining);
      setPendingCount(remaining.length);
    } finally {
      replayingRef.current = false;
    }
  }, []);

  // ------------------------------------------------------------------
  // Auto-replay when going back online
  // ------------------------------------------------------------------
  useEffect(() => {
    if (isOnline) {
      // Small delay to let the network stabilize
      const timer = setTimeout(() => {
        replayQueue();
      }, 1500);
      return () => clearTimeout(timer);
    }
  }, [isOnline, replayQueue]);

  return {
    isOnline,
    pendingCount,
    queueMutation,
    replayQueue,
  };
}

export default useOffline;
