// src/utils/authSession.ts

export const ACCESS_TOKEN_KEY = 'access_token';
export const REFRESH_TOKEN_KEY = 'refresh_token';
export const REMEMBER_ME_KEY = 'remember_me';
export const AUTH_STORAGE_KEY = 'auth-storage';
export const SESSION_LAST_ACTIVITY_KEY = 'auth:last_activity_at';
export const SESSION_LOGOUT_EVENT_KEY = 'auth:logout_event';

export type LogoutReason =
  | 'idle_timeout'
  | 'session_expired'
  | 'manual_logout'
  | 'tenant_access_denied'
  | 'external_logout';

export interface LogoutEventPayload {
  reason: LogoutReason;
  at: number;
  sourceTabId?: string;
}

export function getAccessToken(): string | null {
  return sessionStorage.getItem(ACCESS_TOKEN_KEY) || localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function getRefreshToken(): string | null {
  return sessionStorage.getItem(REFRESH_TOKEN_KEY) || localStorage.getItem(REFRESH_TOKEN_KEY);
}

export function getTokenStorage(): Storage {
  return localStorage.getItem(REFRESH_TOKEN_KEY) ? localStorage : sessionStorage;
}

export function clearStoredTokens() {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
  localStorage.removeItem(REMEMBER_ME_KEY);
  sessionStorage.removeItem(ACCESS_TOKEN_KEY);
  sessionStorage.removeItem(REFRESH_TOKEN_KEY);
}

/**
 * Clear persisted Zustand auth state so stale isAuthenticated=true
 * does not cause redirect loops on page reload.
 */
export function clearPersistedAuthState() {
  try {
    for (const storage of [sessionStorage, localStorage]) {
      const raw = storage.getItem(AUTH_STORAGE_KEY);
      if (!raw) {
        continue;
      }

      const parsed = JSON.parse(raw);
      if (parsed?.state) {
        parsed.state.isAuthenticated = false;
        parsed.state.user = null;
        parsed.state.accessToken = null;
        parsed.state.refreshToken = null;
        storage.setItem(AUTH_STORAGE_KEY, JSON.stringify(parsed));
      }
    }
  } catch {
    // Best-effort cleanup
  }
}

export function clearAuthArtifacts() {
  clearStoredTokens();
  clearPersistedAuthState();
  localStorage.removeItem(SESSION_LAST_ACTIVITY_KEY);
}

export function isLoginPath(pathname: string = window.location.pathname): boolean {
  return pathname === '/login' || pathname === '/super-admin/login';
}

export function getLoginPath(pathname: string = window.location.pathname): string {
  return pathname.startsWith('/super-admin') ? '/super-admin/login' : '/login';
}

export function buildLoginRedirectUrl(
  reason?: LogoutReason,
  pathname: string = window.location.pathname,
): string {
  const loginPath = getLoginPath(pathname);
  if (!reason || reason === 'manual_logout' || reason === 'external_logout') {
    return loginPath;
  }
  return `${loginPath}?reason=${encodeURIComponent(reason)}`;
}

export function broadcastLogout(reason: LogoutReason, sourceTabId?: string) {
  const payload: LogoutEventPayload = {
    reason,
    at: Date.now(),
    sourceTabId,
  };
  localStorage.setItem(SESSION_LOGOUT_EVENT_KEY, JSON.stringify(payload));
}

export function parseLogoutEvent(raw: string | null): LogoutEventPayload | null {
  if (!raw) {
    return null;
  }
  try {
    const parsed = JSON.parse(raw) as LogoutEventPayload;
    if (!parsed?.reason || !parsed?.at) {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

export function getLastActivityTimestamp(): number | null {
  const raw = localStorage.getItem(SESSION_LAST_ACTIVITY_KEY);
  if (!raw) {
    return null;
  }
  const ts = Number(raw);
  return Number.isFinite(ts) && ts > 0 ? ts : null;
}

export function setLastActivityTimestamp(timestamp: number = Date.now()) {
  localStorage.setItem(SESSION_LAST_ACTIVITY_KEY, String(timestamp));
}

export function getIdleTimeoutMs(defaultMinutes = 30): number {
  const parsed = Number(process.env.REACT_APP_IDLE_TIMEOUT_MINUTES);
  const minutes = Number.isFinite(parsed) && parsed > 0 ? parsed : defaultMinutes;
  return minutes * 60 * 1000;
}
