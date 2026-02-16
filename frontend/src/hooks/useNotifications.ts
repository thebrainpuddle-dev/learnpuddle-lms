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
import api from '../config/api';

// Types
export interface Notification {
  id: string;
  type: string;
  title: string;
  message: string;
  is_read: boolean;
  created_at: string;
  course_id?: string;
  assignment_id?: string;
}

interface WebSocketMessage {
  type: 'notification' | 'unread_count' | 'notification_read' | 'pong';
  notification?: Notification;
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

export function useNotifications(options: UseNotificationsOptions = {}): UseNotificationsReturn {
  const {
    enabled = true,
    pollingInterval = 30000,
    maxReconnectAttempts = 5,
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

  // Calculate reconnect delay with exponential backoff
  const getReconnectDelay = useCallback(() => {
    const baseDelay = 1000;
    const maxDelay = 30000;
    const delay = Math.min(baseDelay * Math.pow(2, reconnectAttemptsRef.current), maxDelay);
    return delay + Math.random() * 1000; // Add jitter
  }, []);

  // Connect to WebSocket
  const connect = useCallback(() => {
    if (!enabled || !isAuthenticated || !accessToken) {
      return;
    }

    // Clean up existing connection
    if (wsRef.current) {
      wsRef.current.close();
    }

    setConnectionStatus('connecting');

    const wsUrl = `${WS_BASE_URL}/ws/notifications/?token=${accessToken}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
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
      try {
        const data: WebSocketMessage = JSON.parse(event.data);
        
        switch (data.type) {
          case 'notification':
            if (data.notification) {
              setNotifications(prev => [data.notification!, ...prev].slice(0, 50));
              setUnreadCount(prev => prev + 1);
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
              }
            }
            break;
          
          case 'pong':
            // Connection is alive
            break;
        }
      } catch (e) {
        console.error('Failed to parse WebSocket message:', e);
      }
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };

    ws.onclose = (event) => {
      setConnectionStatus('disconnected');
      wsRef.current = null;
      
      // Clear ping interval
      if (pingIntervalRef.current) {
        clearInterval(pingIntervalRef.current);
      }

      // Attempt reconnection if not intentionally closed
      if (event.code !== 1000 && event.code !== 4001) {
        reconnectAttemptsRef.current++;
        
        if (reconnectAttemptsRef.current <= maxReconnectAttempts) {
          const delay = getReconnectDelay();
          reconnectTimeoutRef.current = setTimeout(connect, delay);
        } else {
          // Fall back to polling
          console.log('Max reconnection attempts reached, falling back to polling');
          setConnectionStatus('polling');
          startPolling();
        }
      }
    };
  }, [enabled, isAuthenticated, accessToken, maxReconnectAttempts, getReconnectDelay]);

  // Polling fallback
  const startPolling = useCallback(() => {
    const poll = async () => {
      try {
        const response = await api.get('/notifications/');
        const data = response.data;
        setNotifications(Array.isArray(data) ? data : (data.results || []));
        setUnreadCount(data.unread_count ?? 0);
      } catch (error) {
        console.error('Polling failed:', error);
      }
    };

    poll();
    pollingIntervalRef.current = setInterval(poll, pollingInterval);
  }, [pollingInterval]);

  // Mark notifications as read
  const markAsRead = useCallback((ids: string[]) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'mark_read', ids }));
    } else {
      // Fallback: update via REST API (bulk endpoint)
      api.post('/notifications/mark-read/', { ids }).then(() => {
        setNotifications(prev =>
          prev.map(n => (ids.includes(n.id) ? { ...n, is_read: true } : n))
        );
        setUnreadCount(prev => Math.max(0, prev - ids.length));
      });
    }
  }, []);

  // Mark all as read
  const markAllAsRead = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'mark_all_read' }));
    } else {
      api.post('/notifications/mark-all-read/').then(() => {
        setNotifications(prev => prev.map(n => ({ ...n, is_read: true })));
        setUnreadCount(0);
      });
    }
  }, []);

  // Add notification manually (for testing/local notifications)
  const addNotification = useCallback((notification: Notification) => {
    setNotifications(prev => [notification, ...prev].slice(0, 50));
    if (!notification.is_read) {
      setUnreadCount(prev => prev + 1);
    }
  }, []);

  // Connect on mount
  useEffect(() => {
    if (enabled && isAuthenticated && accessToken) {
      connect();
    }

    return () => {
      // Cleanup
      if (wsRef.current) {
        wsRef.current.close(1000);
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current);
      }
      if (pingIntervalRef.current) {
        clearInterval(pingIntervalRef.current);
      }
    };
  }, [enabled, isAuthenticated, accessToken, connect]);

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
