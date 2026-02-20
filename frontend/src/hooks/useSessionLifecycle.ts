import { useEffect, useRef } from 'react';
import { authService } from '../services/authService';
import { useAuthStore } from '../stores/authStore';
import {
  buildLoginRedirectUrl,
  broadcastLogout,
  clearAuthArtifacts,
  getIdleTimeoutMs,
  getLastActivityTimestamp,
  getRefreshToken,
  isLoginPath,
  parseLogoutEvent,
  SESSION_LAST_ACTIVITY_KEY,
  SESSION_LOGOUT_EVENT_KEY,
  setLastActivityTimestamp,
  type LogoutReason,
} from '../utils/authSession';

const ACTIVITY_EVENTS: Array<keyof WindowEventMap> = [
  'mousedown',
  'mousemove',
  'keydown',
  'scroll',
  'touchstart',
];

const ACTIVITY_SYNC_THROTTLE_MS = 15000;
const IDLE_CHECK_INTERVAL_MS = 15000;

export function useSessionLifecycle() {
  const { isAuthenticated, clearAuth } = useAuthStore();
  const idleTimeoutMs = getIdleTimeoutMs(30);
  const tabIdRef = useRef(`${Date.now()}-${Math.random().toString(36).slice(2, 10)}`);
  const lastActivityWriteRef = useRef(0);
  const logoutInProgressRef = useRef(false);

  useEffect(() => {
    if (!isAuthenticated) {
      return;
    }

    logoutInProgressRef.current = false;

    const redirectToLogin = (reason?: LogoutReason) => {
      if (isLoginPath()) {
        return;
      }
      window.location.href = buildLoginRedirectUrl(reason);
    };

    const localLogout = (reason: LogoutReason) => {
      if (logoutInProgressRef.current) {
        return;
      }
      logoutInProgressRef.current = true;
      clearAuth();
      clearAuthArtifacts();
      redirectToLogin(reason);
    };

    const writeActivity = () => {
      const now = Date.now();
      if (now - lastActivityWriteRef.current < ACTIVITY_SYNC_THROTTLE_MS) {
        return;
      }
      lastActivityWriteRef.current = now;
      setLastActivityTimestamp(now);
    };

    const handleStorage = (event: StorageEvent) => {
      if (event.key === SESSION_LOGOUT_EVENT_KEY && event.newValue) {
        const payload = parseLogoutEvent(event.newValue);
        if (!payload) {
          return;
        }
        if (payload.sourceTabId === tabIdRef.current) {
          return;
        }
        localLogout('external_logout');
      }

      if (event.key === SESSION_LAST_ACTIVITY_KEY && event.newValue) {
        const ts = Number(event.newValue);
        if (Number.isFinite(ts) && ts > lastActivityWriteRef.current) {
          lastActivityWriteRef.current = ts;
        }
      }
    };

    const terminateForIdleTimeout = async () => {
      logoutInProgressRef.current = true;
      const refreshToken = getRefreshToken();
      try {
        if (refreshToken) {
          await authService.logout(refreshToken);
        }
      } catch {
        // Best-effort server-side logout. Local cleanup still proceeds.
      } finally {
        clearAuth();
        clearAuthArtifacts();
        broadcastLogout('idle_timeout', tabIdRef.current);
        redirectToLogin('idle_timeout');
      }
    };

    const checkIdleTimeout = async (): Promise<boolean> => {
      if (logoutInProgressRef.current) {
        return true;
      }

      const lastActivity = getLastActivityTimestamp();
      if (!lastActivity) {
        const now = Date.now();
        lastActivityWriteRef.current = now;
        setLastActivityTimestamp(now);
        return false;
      }

      if (Date.now() - lastActivity < idleTimeoutMs) {
        return false;
      }

      await terminateForIdleTimeout();
      return true;
    };

    const handleActivity = () => {
      void (async () => {
        const timedOut = await checkIdleTimeout();
        if (!timedOut) {
          writeActivity();
        }
      })();
    };

    const handleVisibilityChange = () => {
      if (!document.hidden) {
        handleActivity();
      }
    };

    const initialLastActivity = getLastActivityTimestamp();
    if (initialLastActivity) {
      lastActivityWriteRef.current = initialLastActivity;
    } else {
      const now = Date.now();
      lastActivityWriteRef.current = now;
      setLastActivityTimestamp(now);
    }

    for (const eventName of ACTIVITY_EVENTS) {
      window.addEventListener(eventName, handleActivity, { passive: true });
    }
    window.addEventListener('focus', handleActivity);
    document.addEventListener('visibilitychange', handleVisibilityChange);
    window.addEventListener('storage', handleStorage);

    void checkIdleTimeout();

    const intervalId = window.setInterval(() => {
      void checkIdleTimeout();
    }, IDLE_CHECK_INTERVAL_MS);

    return () => {
      window.clearInterval(intervalId);
      for (const eventName of ACTIVITY_EVENTS) {
        window.removeEventListener(eventName, handleActivity);
      }
      window.removeEventListener('focus', handleActivity);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      window.removeEventListener('storage', handleStorage);
    };
  }, [clearAuth, idleTimeoutMs, isAuthenticated]);
}
