// hooks/useMaicClassroomChannel.ts
//
// F2 (P0) — WS subscription that streams `maic.image.task` events from
// `ws/maic/classrooms/<classroom_id>/` into the per-element media-task
// store. Auth pattern matches `useNotifications.ts`: JWT delivered via
// the `Bearer.<token>` subprotocol so the access token never lands in
// query strings, server logs, or referer headers.
//
// Behaviour:
//   - opens on mount when classroomId + accessToken are present;
//   - dispatches every `maic.image.task` payload into the store;
//   - reconnects with exponential backoff (matches notifications hook);
//   - closes cleanly on unmount.
//
// The hook is intentionally side-effect-only — callers don't read its
// return; they observe the store via `useMediaTask(elementKey)`.

import { useCallback, useEffect, useRef, useState } from 'react';
import { useAuthStore } from '../stores/authStore';
import {
  useMaicMediaGenerationStore,
  type MaicImageTaskEvent,
} from '../stores/maicMediaGenerationStore';

const WS_BASE_URL =
  process.env.REACT_APP_WS_URL ||
  (typeof window !== 'undefined'
    ? (window.location.protocol === 'https:' ? 'wss://' : 'ws://') +
      window.location.host
    : 'ws://localhost');

export type MaicClassroomChannelStatus =
  | 'idle'
  | 'connecting'
  | 'connected'
  | 'disconnected';

interface UseMaicClassroomChannelOptions {
  /** Disable the connection (e.g. while the page is showing a stall banner). */
  enabled?: boolean;
  /** Cap reconnection attempts before giving up. The notifications-hook
   *  fallback to polling is N/A here — the GET-detail polling is already
   *  a fallback for the data path. */
  maxReconnectAttempts?: number;
}

export function useMaicClassroomChannel(
  classroomId: string | null | undefined,
  options: UseMaicClassroomChannelOptions = {},
): MaicClassroomChannelStatus {
  const { enabled = true, maxReconnectAttempts = 5 } = options;
  const accessToken = useAuthStore((s) => s.accessToken);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  const applyEvent = useMaicMediaGenerationStore((s) => s.applyEvent);

  const [status, setStatus] = useState<MaicClassroomChannelStatus>('idle');

  const wsRef = useRef<WebSocket | null>(null);
  const mountedRef = useRef(false);
  const reconnectAllowedRef = useRef(false);
  const reconnectAttemptsRef = useRef(0);
  const connectTimeoutRef = useRef<ReturnType<typeof setTimeout> | undefined>(
    undefined,
  );
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | undefined>(
    undefined,
  );
  // Hold a stable ref to applyEvent so the effect below doesn't churn on
  // every Zustand re-render (function identity is stable, but this is
  // belt-and-braces and matches the notifications hook pattern).
  const applyEventRef = useRef(applyEvent);
  applyEventRef.current = applyEvent;

  const getReconnectDelay = useCallback(() => {
    const baseDelay = 1000;
    const maxDelay = 30000;
    const delay = Math.min(
      baseDelay * Math.pow(2, reconnectAttemptsRef.current),
      maxDelay,
    );
    return delay + Math.random() * 1000;
  }, []);

  const clearReconnectTimeout = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = undefined;
    }
  }, []);

  const clearConnectTimeout = useCallback(() => {
    if (connectTimeoutRef.current) {
      clearTimeout(connectTimeoutRef.current);
      connectTimeoutRef.current = undefined;
    }
  }, []);

  const closeSocket = useCallback((ws: WebSocket | null) => {
    if (!ws) return;
    try {
      if (ws.readyState === WebSocket.CONNECTING) {
        ws.addEventListener(
          'open',
          () => {
            try {
              ws.close(1000);
            } catch {
              // ignore
            }
          },
          { once: true },
        );
        return;
      }
      if (ws.readyState === WebSocket.OPEN) {
        ws.close(1000);
      }
    } catch {
      // ignore
    }
  }, []);

  const connect = useCallback(() => {
    if (
      !mountedRef.current ||
      !enabled ||
      !classroomId ||
      !isAuthenticated ||
      !accessToken
    ) {
      return;
    }
    if (wsRef.current) {
      // Replace any existing connection — caller changed classroomId.
      const previous = wsRef.current;
      wsRef.current = null;
      closeSocket(previous);
    }
    reconnectAllowedRef.current = true;
    clearReconnectTimeout();

    setStatus('connecting');

    const url = `${WS_BASE_URL}/ws/maic/classrooms/${classroomId}/`;
    const ws = new WebSocket(url, [`Bearer.${accessToken}`]);
    wsRef.current = ws;

    ws.onopen = () => {
      if (!mountedRef.current || wsRef.current !== ws) {
        return;
      }
      setStatus('connected');
      reconnectAttemptsRef.current = 0;
    };

    ws.onmessage = (event) => {
      if (!mountedRef.current || wsRef.current !== ws) {
        return;
      }
      try {
        const data = JSON.parse(event.data) as MaicImageTaskEvent;
        if (data?.type === 'maic.image.task') {
          applyEventRef.current(data);
        }
      } catch {
        // Malformed payload — drop silently.
      }
    };

    ws.onerror = () => {
      // Handled by onclose reconnection logic.
    };

    ws.onclose = (closeEvent) => {
      if (!mountedRef.current || wsRef.current !== ws) {
        return;
      }
      setStatus('disconnected');
      wsRef.current = null;

      // 1000 = normal close (we initiated); 4001 = auth-rejected by
      // backend consumer. Don't reconnect either of those.
      if (closeEvent.code === 1000 || closeEvent.code === 4001) {
        return;
      }
      reconnectAttemptsRef.current++;
      if (reconnectAttemptsRef.current <= maxReconnectAttempts) {
        const delay = getReconnectDelay();
        reconnectTimeoutRef.current = setTimeout(() => {
          reconnectTimeoutRef.current = undefined;
          if (mountedRef.current && reconnectAllowedRef.current) {
            connect();
          }
        }, delay);
      }
    };
  }, [
    enabled,
    classroomId,
    isAuthenticated,
    accessToken,
    maxReconnectAttempts,
    getReconnectDelay,
    clearReconnectTimeout,
    closeSocket,
  ]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      reconnectAllowedRef.current = false;
      clearConnectTimeout();
      clearReconnectTimeout();
      const ws = wsRef.current;
      wsRef.current = null;
      closeSocket(ws);
      reconnectAttemptsRef.current = 0;
    };
  }, [clearConnectTimeout, clearReconnectTimeout, closeSocket]);

  useEffect(() => {
    const shouldConnect = Boolean(
      enabled && classroomId && isAuthenticated && accessToken,
    );
    reconnectAllowedRef.current = shouldConnect;
    clearConnectTimeout();
    if (shouldConnect) {
      connectTimeoutRef.current = setTimeout(() => {
        connectTimeoutRef.current = undefined;
        if (mountedRef.current && reconnectAllowedRef.current) {
          connect();
        }
      }, 0);
    } else {
      clearReconnectTimeout();
      const ws = wsRef.current;
      wsRef.current = null;
      closeSocket(ws);
      reconnectAttemptsRef.current = 0;
      setStatus('idle');
    }
    return () => {
      reconnectAllowedRef.current = false;
      clearConnectTimeout();
      clearReconnectTimeout();
      const ws = wsRef.current;
      wsRef.current = null;
      closeSocket(ws);
      reconnectAttemptsRef.current = 0;
    };
  }, [
    enabled,
    classroomId,
    isAuthenticated,
    accessToken,
    connect,
    clearConnectTimeout,
    clearReconnectTimeout,
    closeSocket,
  ]);

  return status;
}

export default useMaicClassroomChannel;
