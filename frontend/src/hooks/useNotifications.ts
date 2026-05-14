// src/hooks/useNotifications.ts
/**
 * React hook for real-time notifications via WebSocket.
 * 
 * Features:
 * - Automatic WebSocket connection with JWT authentication
 * - Reconnection with exponential backoff
 * - Fallback to polling when WebSocket unavailable
 * - Notification state management
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { useAuthStore } from '../stores/authStore';
import { notificationService, type Notification } from '../services/notificationService';

export type { Notification };

type RawWebSocketNotification = Partial<Notification> & {
  type?: Notification['notification_type'];
  course_id?: string | null;
  assignment_id?: string | null;
};

interface WebSocketMessage {
  type: 'notification' | 'unread_count' | 'notification_read' | 'pong';
  notification?: RawWebSocketNotification;
  count?: number;
  ids?: string[];
  unread_count?: number;
}

interface UseNotificationsOptions {
  /** Enable WebSocket connection */
  enabled?: boolean;
  /** Polling interval in ms (fallback when WS unavailable) */
  pollingInterval?: number;
  /** Max reconnection attempts before falling back to polling */
  maxReconnectAttempts?: number;
  /** Number of recent notifications to keep in memory */
  limit?: number;
}

interface UseNotificationsReturn {
  /** List of recent notifications */
  notifications: Notification[];
  /** Count of unread notifications */
  unreadCount: number;
  /** WebSocket connection status */
  connectionStatus: 'connecting' | 'connected' | 'disconnected' | 'polling';
  /** Mark specific notifications as read */
  markAsRead: (ids: string[]) => void;
  /** Mark all notifications as read */
  markAllAsRead: () => void;
  /** Manually add a notification (for testing) */
  addNotification: (notification: Notification) => void;
}

const WS_BASE_URL = process.env.REACT_APP_WS_URL ||
  (window.location.protocol === 'https:' ? 'wss://' : 'ws://') + 
  window.location.host;

function normalizeNotification(raw: RawWebSocketNotification): Notification {
  return {
    id: String(raw.id || ''),
    notification_type: (raw.notification_type || raw.type || 'SYSTEM') as Notification['notification_type'],
    title: String(raw.title || ''),
    message: String(raw.message || ''),
    course: raw.course || raw.course_id || undefined,
    course_title: raw.course_title,
    assignment: raw.assignment || raw.assignment_id || undefined,
    assignment_title: raw.assignment_title,
    is_read: Boolean(raw.is_read),
    is_actionable: Boolean(raw.is_actionable),
    read_at: raw.read_at,
    created_at: String(raw.created_at || new Date().toISOString()),
  };
}

export function useNotifications(options: UseNotificationsOptions = {}): UseNotificationsReturn {
  const {
    enabled = true,
    pollingInterval = 30000,
    maxReconnectAttempts = 5,
    limit = 50,
  } = options;

  const { accessToken, isAuthenticated } = useAuthStore();
  
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [connectionStatus, setConnectionStatus] = useState<UseNotificationsReturn['connectionStatus']>('disconnected');
  
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | undefined>(undefined);
  const pollingIntervalRef = useRef<NodeJS.Timeout | undefined>(undefined);
  const pingIntervalRef = useRef<NodeJS.Timeout | undefined>(undefined);
  const mountedRef = useRef(false);
  const reconnectAllowedRef = useRef(false);

  const loadSnapshot = useCallback(async () => {
    const [recent, unread] = await Promise.all([
      notificationService.getNotifications({ limit }),
      notificationService.getUnreadCount(),
    ]);
    setNotifications(recent.slice(0, limit));
    setUnreadCount(unread);
  }, [limit]);

  // Calculate reconnect delay with exponential backoff
  const getReconnectDelay = useCallback(() => {
    const baseDelay = 1000;
    const maxDelay = 30000;
    const delay = Math.min(baseDelay * Math.pow(2, reconnectAttemptsRef.current), maxDelay);
    return delay + Math.random() * 1000; // Add jitter
  }, []);

  // Polling fallback
  const startPolling = useCallback(() => {
    const poll = async () => {
      try {
        await loadSnapshot();
      } catch {
        // Polling failed silently; will retry on next interval
      }
    };

    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
    }
    poll();
    pollingIntervalRef.current = setInterval(poll, pollingInterval);
  }, [loadSnapshot, pollingInterval]);

  const clearPingInterval = useCallback(() => {
    if (pingIntervalRef.current) {
      clearInterval(pingIntervalRef.current);
      pingIntervalRef.current = undefined;
    }
  }, []);

  const closeCurrentSocket = useCallback((code = 1000) => {
    const ws = wsRef.current;
    if (!ws) return;

    wsRef.current = null;
    clearPingInterval();

    if (
      typeof WebSocket !== 'undefined' &&
      (ws.readyState === WebSocket.CLOSED || ws.readyState === WebSocket.CLOSING)
    ) {
      return;
    }

    if (typeof WebSocket !== 'undefined' && ws.readyState === WebSocket.CONNECTING) {
      let cleanup = () => {};
      const closeAfterOpen = () => {
        cleanup();
        try {
          ws.close(code);
        } catch {
          // Already gone.
        }
      };
      cleanup = () => {
        ws.removeEventListener('open', closeAfterOpen);
        ws.removeEventListener('close', cleanup);
        ws.removeEventListener('error', cleanup);
      };
      ws.addEventListener('open', closeAfterOpen, { once: true });
      ws.addEventListener('close', cleanup, { once: true });
      ws.addEventListener('error', cleanup, { once: true });
      return;
    }

    try {
      ws.close(code);
    } catch {
      // Already gone.
    }
  }, [clearPingInterval]);

  // Connect to WebSocket
  const connect = useCallback(() => {
    if (!enabled || !isAuthenticated || !accessToken) {
      return;
    }

    // Clean up existing connection
    closeCurrentSocket(1000);

    if (mountedRef.current) {
      setConnectionStatus('connecting');
    }

    // Pass JWT via subprotocol instead of URL query string to avoid
    // token leakage in browser history, server logs, and referer headers.
    const wsUrl = `${WS_BASE_URL}/ws/notifications/`;
    const ws = new WebSocket(wsUrl, [`Bearer.${accessToken}`]);
    wsRef.current = ws;

    ws.onopen = () => {
      if (wsRef.current !== ws || !mountedRef.current) {
        try {
          ws.close(1000);
        } catch {
          // Already gone.
        }
        return;
      }
      setConnectionStatus('connected');
      reconnectAttemptsRef.current = 0;
      
      // Start ping interval to keep connection alive
      pingIntervalRef.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'ping' }));
        }
      }, 30000);
    };

    ws.onmessage = (event) => {
      if (wsRef.current !== ws || !mountedRef.current) return;
      try {
        const data: WebSocketMessage = JSON.parse(event.data);
        
        switch (data.type) {
          case 'notification':
            if (data.notification) {
              const notification = normalizeNotification(data.notification);
              setNotifications(prev => [
                notification,
                ...prev.filter(n => n.id !== notification.id),
              ].slice(0, limit));
              if (!notification.is_read) {
                setUnreadCount(prev => prev + 1);
              }
            }
            break;
          
          case 'unread_count':
            if (typeof data.count === 'number') {
              setUnreadCount(data.count);
            }
            break;
          
          case 'notification_read':
            if (data.ids) {
              setNotifications(prev =>
                prev.map(n =>
                  data.ids!.includes(n.id) ? { ...n, is_read: true } : n
                )
              );
              if (typeof data.unread_count === 'number') {
                setUnreadCount(data.unread_count);
              } else {
                setUnreadCount(prev => Math.max(0, prev - data.ids!.length));
              }
            }
            break;
          
          case 'pong':
            // Connection is alive
            break;
        }
      } catch {
        // Malformed WS message; skip
      }
    };

    ws.onerror = () => {
      // WS error handled by onclose reconnection logic
    };

    ws.onclose = (event) => {
      const isCurrentSocket = wsRef.current === ws;
      if (isCurrentSocket) {
        wsRef.current = null;
      }
      clearPingInterval();
      if (!isCurrentSocket || !mountedRef.current || !reconnectAllowedRef.current) {
        return;
      }
      setConnectionStatus('disconnected');

      // Attempt reconnection if not intentionally closed
      if (event.code !== 1000 && event.code !== 4001) {
        reconnectAttemptsRef.current++;
        
        if (reconnectAttemptsRef.current <= maxReconnectAttempts) {
          const delay = getReconnectDelay();
          reconnectTimeoutRef.current = setTimeout(connect, delay);
        } else {
          // Fall back to polling after max reconnect attempts
          setConnectionStatus('polling');
          startPolling();
        }
      }
    };
  }, [
    enabled,
    isAuthenticated,
    accessToken,
    maxReconnectAttempts,
    getReconnectDelay,
    startPolling,
    limit,
    closeCurrentSocket,
    clearPingInterval,
  ]);

  // Mark notifications as read
  const markAsRead = useCallback((ids: string[]) => {
    const unreadMarked = notifications.filter(n => ids.includes(n.id) && !n.is_read).length;
    setNotifications(prev =>
      prev.map(n => (ids.includes(n.id) ? { ...n, is_read: true } : n))
    );
    if (unreadMarked > 0) {
      setUnreadCount(prev => Math.max(0, prev - unreadMarked));
    }

    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'mark_read', ids }));
    } else {
      // Fallback: update via REST API (bulk endpoint)
      notificationService.markManyAsRead(ids).catch(() => {
        void loadSnapshot().catch(() => undefined);
      });
    }
  }, [loadSnapshot, notifications]);

  // Mark all as read
  const markAllAsRead = useCallback(() => {
    setNotifications(prev => prev.map(n => ({ ...n, is_read: true })));
    setUnreadCount(0);

    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'mark_all_read' }));
    } else {
      notificationService.markAllAsRead().catch(() => {
        void loadSnapshot().catch(() => undefined);
      });
    }
  }, [loadSnapshot]);

  // Add notification manually (for testing/local notifications)
  const addNotification = useCallback((notification: Notification) => {
    setNotifications(prev => [notification, ...prev].slice(0, 50));
    if (!notification.is_read) {
      setUnreadCount(prev => prev + 1);
    }
  }, []);

  // Connect on mount
  useEffect(() => {
    mountedRef.current = true;
    reconnectAllowedRef.current = Boolean(enabled && isAuthenticated && accessToken);

    if (enabled && isAuthenticated && accessToken) {
      void loadSnapshot().catch(() => undefined);
      connect();
    } else {
      closeCurrentSocket(1000);
      setConnectionStatus('disconnected');
    }

    return () => {
      mountedRef.current = false;
      reconnectAllowedRef.current = false;
      closeCurrentSocket(1000);
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = undefined;
      }
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current);
        pollingIntervalRef.current = undefined;
      }
      clearPingInterval();
    };
  }, [
    enabled,
    isAuthenticated,
    accessToken,
    connect,
    loadSnapshot,
    closeCurrentSocket,
    clearPingInterval,
  ]);

  return {
    notifications,
    unreadCount,
    connectionStatus,
    markAsRead,
    markAllAsRead,
    addNotification,
  };
}

export default useNotifications;
