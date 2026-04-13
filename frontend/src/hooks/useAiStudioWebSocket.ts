// src/hooks/useAiStudioWebSocket.ts
//
// WebSocket hook for real-time AI Studio generation status updates.
// Mirrors the auth pattern from useNotifications (Bearer subprotocol).

import { useEffect, useRef, useCallback, useState } from 'react';
import { getAccessToken } from '../utils/authSession';

// ─── Types ─────────────────────────────────────────────────────────────────

export interface AiStudioWsMessage {
  type: 'generation_status' | 'generation_complete' | 'generation_error' | 'pong';
  status?: string;
  phase?: string;
  progress?: {
    current_scene: number;
    total_scenes: number;
    percentage: number;
  };
  phases_completed?: string[];
  phases_remaining?: string[];
  lesson_id?: string;
  scene_count?: number;
  error?: string;
}

export interface UseAiStudioWebSocketOptions {
  /** UUID of the lesson or scenario to watch */
  itemId: string | null;
  /** Called on each status update */
  onStatus?: (msg: AiStudioWsMessage) => void;
  /** Called when generation completes */
  onComplete?: (msg: AiStudioWsMessage) => void;
  /** Called on error */
  onError?: (msg: AiStudioWsMessage) => void;
  /** Enable/disable the connection (default true) */
  enabled?: boolean;
}

export interface UseAiStudioWebSocketReturn {
  /** Whether the WebSocket is connected */
  isConnected: boolean;
  /** Last received message */
  lastMessage: AiStudioWsMessage | null;
  /** Send a message (e.g., ping) */
  send: (data: Record<string, unknown>) => void;
}

// ─── Constants ─────────────────────────────────────────────────────────────

const WS_BASE_URL =
  typeof window !== 'undefined'
    ? (window.location.protocol === 'https:' ? 'wss://' : 'ws://') +
      window.location.host
    : 'ws://localhost:8001';

const PING_INTERVAL_MS = 30_000;
const INITIAL_RECONNECT_DELAY_MS = 1_000;
const MAX_RECONNECT_DELAY_MS = 30_000;

// ─── Hook ──────────────────────────────────────────────────────────────────

export function useAiStudioWebSocket(
  options: UseAiStudioWebSocketOptions,
): UseAiStudioWebSocketReturn {
  const { itemId, onStatus, onComplete, onError, enabled = true } = options;

  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<AiStudioWsMessage | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const pingTimerRef = useRef<ReturnType<typeof setInterval> | undefined>(undefined);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const reconnectDelayRef = useRef(INITIAL_RECONNECT_DELAY_MS);
  const unmountedRef = useRef(false);

  // Keep callback refs stable to avoid reconnect on every render
  const onStatusRef = useRef(onStatus);
  onStatusRef.current = onStatus;
  const onCompleteRef = useRef(onComplete);
  onCompleteRef.current = onComplete;
  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;

  // ── Cleanup helpers ────────────────────────────────────────────────────

  const clearTimers = useCallback(() => {
    if (pingTimerRef.current !== undefined) {
      clearInterval(pingTimerRef.current);
      pingTimerRef.current = undefined;
    }
    if (reconnectTimerRef.current !== undefined) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = undefined;
    }
  }, []);

  // ── Send ───────────────────────────────────────────────────────────────

  const send = useCallback((data: Record<string, unknown>) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(data));
    }
  }, []);

  // ── Connect ────────────────────────────────────────────────────────────

  const connect = useCallback(() => {
    if (unmountedRef.current) return;
    if (!itemId) return;

    const token = getAccessToken();
    if (!token) return;

    // Tear down any existing connection
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    clearTimers();

    const wsUrl = `${WS_BASE_URL}/ws/ai-studio/${itemId}/`;
    const ws = new WebSocket(wsUrl, [`Bearer.${token}`]);
    wsRef.current = ws;

    ws.onopen = () => {
      if (unmountedRef.current) return;
      setIsConnected(true);
      reconnectDelayRef.current = INITIAL_RECONNECT_DELAY_MS;

      // Keep-alive pings
      pingTimerRef.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'ping' }));
        }
      }, PING_INTERVAL_MS);
    };

    ws.onmessage = (event) => {
      if (unmountedRef.current) return;

      try {
        const msg: AiStudioWsMessage = JSON.parse(event.data);
        setLastMessage(msg);

        switch (msg.type) {
          case 'generation_status':
            onStatusRef.current?.(msg);
            break;
          case 'generation_complete':
            onCompleteRef.current?.(msg);
            break;
          case 'generation_error':
            onErrorRef.current?.(msg);
            break;
          case 'pong':
            // keep-alive ack; no action
            break;
        }
      } catch {
        console.warn('[useAiStudioWebSocket] Malformed message received');
      }
    };

    ws.onerror = () => {
      // Handled via onclose reconnection logic
    };

    ws.onclose = (event) => {
      if (unmountedRef.current) return;
      setIsConnected(false);
      wsRef.current = null;
      clearTimers();

      // Reconnect unless intentionally closed (1000) or auth failure (4001)
      if (event.code !== 1000 && event.code !== 4001) {
        const delay = reconnectDelayRef.current;
        reconnectDelayRef.current = Math.min(
          delay * 2,
          MAX_RECONNECT_DELAY_MS,
        );
        reconnectTimerRef.current = setTimeout(connect, delay);
      }
    };
  }, [itemId, clearTimers]);

  // ── Lifecycle ──────────────────────────────────────────────────────────

  useEffect(() => {
    unmountedRef.current = false;

    if (enabled && itemId) {
      connect();
    }

    return () => {
      unmountedRef.current = true;
      clearTimers();
      if (wsRef.current) {
        wsRef.current.close(1000);
        wsRef.current = null;
      }
      setIsConnected(false);
    };
  }, [enabled, itemId, connect, clearTimers]);

  return { isConnected, lastMessage, send };
}

export default useAiStudioWebSocket;
