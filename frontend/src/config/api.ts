// src/config/api.ts

import axios, { AxiosInstance } from 'axios';
import { useAuthStore } from '../stores/authStore';
import { getOpsClientContext } from './opsRouteMap';
import {
  broadcastLogout,
  buildLoginRedirectUrl,
  clearAuthArtifacts,
  getAccessToken,
  getRefreshToken,
  getTokenStorage,
  isLoginPath,
} from '../utils/authSession';

const API_BASE_URL =
  process.env.REACT_APP_API_URL ||
  (process.env.NODE_ENV === 'production' ? '/api' : 'http://localhost:8000/api');

/**
 * Create axios instance with default config
 * Note: Don't set Content-Type here - let axios auto-detect for FormData
 */
export const api: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
});

const AUTH_HEADER_BYPASS_PATHS = [
  '/users/auth/login/',
  '/users/auth/refresh/',
  '/users/auth/request-password-reset/',
  '/users/auth/confirm-password-reset/',
  '/users/auth/verify-email/',
  '/users/auth/sso/providers/',
  '/tenants/theme/',
];

function normalizeRequestPath(url: string = ''): string {
  try {
    return new URL(url, API_BASE_URL).pathname;
  } catch {
    return url;
  }
}

function shouldBypassAuthHeader(url: string = ''): boolean {
  const path = normalizeRequestPath(url);
  return AUTH_HEADER_BYPASS_PATHS.some((allowedPath) => path.endsWith(allowedPath));
}

function isGatewayFailure(error: any): boolean {
  const status = error?.response?.status;
  if (status === 502 || status === 503 || status === 504) {
    return true;
  }
  // Covers transient network/proxy edge failures where status may be absent.
  const code = String(error?.code || '').toUpperCase();
  return code === 'ECONNABORTED' || code === 'ERR_NETWORK';
}

function isGatewayRetryableRequest(config: any): boolean {
  const method = String(config?.method || 'get').toLowerCase();
  if (method === 'get' || method === 'head' || method === 'options') {
    return true;
  }

  const path = normalizeRequestPath(String(config?.url || ''));
  // POST retries are intentionally narrow to avoid duplicate writes.
  return (
    method === 'post' &&
    (path.endsWith('/users/auth/login/') || path.endsWith('/users/auth/refresh/'))
  );
}

let sessionTerminationInProgress = false;

async function maybeRetryGatewayFailure(error: any): Promise<any | null> {
  const originalRequest = error?.config;
  if (!originalRequest || !isGatewayFailure(error) || !isGatewayRetryableRequest(originalRequest)) {
    return null;
  }

  const attempt = Number((originalRequest as any)._gatewayRetryCount || 0);
  if (attempt >= 2) {
    return null;
  }

  (originalRequest as any)._gatewayRetryCount = attempt + 1;
  const delayMs = 300 * (2 ** attempt) + Math.floor(Math.random() * 200);
  await new Promise((resolve) => setTimeout(resolve, delayMs));
  return api(originalRequest);
}

function terminateSession(reason: 'session_expired' | 'tenant_access_denied') {
  if (sessionTerminationInProgress) {
    return;
  }
  sessionTerminationInProgress = true;
  try {
    useAuthStore.getState().clearAuth();
  } catch {
    // In-memory store cleanup is best-effort.
  }
  clearAuthArtifacts();
  broadcastLogout(reason);
  if (!isLoginPath()) {
    window.location.href = buildLoginRedirectUrl(reason);
    return;
  }
  sessionTerminationInProgress = false;
}

function shouldAttemptRefresh(error: any): boolean {
  const status = error?.response?.status;
  if (status === 401) {
    return true;
  }
  if (status !== 403) {
    return false;
  }

  const data = error?.response?.data || {};
  const detail = String(data.detail || data.error || '').toLowerCase();
  const code = String(data.code || '').toLowerCase();
  const messages = Array.isArray(data.messages)
    ? data.messages.map((item: any) => String(item?.message || '')).join(' ').toLowerCase()
    : '';

  return (
    code.includes('token_not_valid') ||
    (detail.includes('token') && (detail.includes('expired') || detail.includes('invalid'))) ||
    messages.includes('token')
  );
}

function isTenantAccessDenied(error: any): boolean {
  if (error?.response?.status !== 403) {
    return false;
  }
  const data = error?.response?.data || {};
  const detail = String(data.detail || data.error || '').toLowerCase();
  return (
    detail.includes('does not belong to this tenant') ||
    detail.includes('tenant required') ||
    (detail.includes('tenant') && detail.includes('access denied'))
  );
}

function safeJson(value: any): any {
  if (value === null || value === undefined) return {};
  if (typeof value === 'string') {
    try {
      return JSON.parse(value);
    } catch {
      return { raw: value.slice(0, 1000) };
    }
  }
  if (typeof value === 'object') return value;
  return { value: String(value) };
}

function shouldEmitOpsBeacon(error: any): boolean {
  const path = normalizeRequestPath(String(error?.config?.url || ''));
  if (path.endsWith('/ops/client-errors/ingest/')) {
    return false;
  }
  const status = Number(error?.response?.status || 0);
  if (status === 429 || status === 500) {
    return true;
  }
  // Network/gateway failures often have no response status.
  return !status;
}

function emitOpsErrorBeacon(error: any): void {
  if (typeof window === 'undefined' || !shouldEmitOpsBeacon(error)) {
    return;
  }

  const status = Number(error?.response?.status || 0);
  const requestPath = normalizeRequestPath(String(error?.config?.url || ''));
  const method = String(error?.config?.method || 'GET').toUpperCase();
  const context = getOpsClientContext(window.location.pathname, window.location.search);
  const requestId = String(error?.response?.headers?.['x-request-id'] || '');
  const responseExcerpt = (() => {
    const data = error?.response?.data;
    if (typeof data === 'string') return data.slice(0, 2000);
    if (data && typeof data === 'object') {
      try {
        return JSON.stringify(data).slice(0, 2000);
      } catch {
        return String(data).slice(0, 2000);
      }
    }
    return String(error?.message || '').slice(0, 2000);
  })();

  const payload = {
    status_code: status,
    endpoint: requestPath,
    method,
    portal: context.portal,
    tab_key: context.tabKey,
    route_path: context.routePath,
    component_name: context.componentName,
    request_id: requestId,
    payload: safeJson(error?.config?.data),
    response_excerpt: responseExcerpt,
    error_message: String(error?.message || ''),
    observed_at: new Date().toISOString(),
  };

  const beaconUrl = `${API_BASE_URL}/ops/client-errors/ingest/`;
  try {
    const blob = new Blob([JSON.stringify(payload)], { type: 'application/json' });
    if (navigator.sendBeacon) {
      navigator.sendBeacon(beaconUrl, blob);
      return;
    }
  } catch {
    // Fall through to fetch fallback.
  }

  try {
    window.fetch(beaconUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      keepalive: true,
      credentials: 'include',
    }).catch(() => undefined);
  } catch {
    // Ignore beacon failures.
  }
}

/**
 * Request interceptor to add auth token and set Content-Type.
 * Checks both sessionStorage and localStorage so "Remember Me" users are handled correctly.
 */
api.interceptors.request.use(
  (config) => {
    if (typeof window !== 'undefined') {
      const opsContext = getOpsClientContext(window.location.pathname, window.location.search);
      config.headers['X-LP-Portal'] = opsContext.portal;
      config.headers['X-LP-Tab'] = opsContext.tabKey;
      config.headers['X-LP-Route'] = opsContext.routePath;
      config.headers['X-LP-Component'] = opsContext.componentName;
    }

    if (shouldBypassAuthHeader(String(config.url || ''))) {
      if (config.headers && 'Authorization' in config.headers) {
        delete (config.headers as any).Authorization;
      }
    } else {
      const token = getAccessToken();
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
    }
    
    // Set Content-Type for JSON, but let axios auto-detect for FormData
    // FormData needs multipart/form-data with boundary which axios sets automatically
    if (config.data && !(config.data instanceof FormData)) {
      config.headers['Content-Type'] = 'application/json';
    }
    
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

/**
 * Token refresh mutex -- ensures only one refresh happens at a time.
 * Concurrent 401 responses queue behind the first refresh attempt.
 */
let isRefreshing = false;
let refreshSubscribers: Array<{
  resolve: (token: string) => void;
  reject: (error: unknown) => void;
}> = [];

function subscribeTokenRefresh(
  resolve: (token: string) => void,
  reject: (error: unknown) => void,
) {
  refreshSubscribers.push({ resolve, reject });
}

function onRefreshed(token: string) {
  refreshSubscribers.forEach((sub) => sub.resolve(token));
  refreshSubscribers = [];
}

function onRefreshFailed(error: unknown) {
  refreshSubscribers.forEach((sub) => sub.reject(error));
  refreshSubscribers = [];
}

/**
 * Response interceptor to handle token refresh (with mutex to prevent parallel refreshes)
 */
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    emitOpsErrorBeacon(error);

    const retriedResponse = await maybeRetryGatewayFailure(error);
    if (retriedResponse) {
      return retriedResponse;
    }

    const originalRequest = error.config;
    const requestUrl = String(originalRequest?.url || '');
    const isRefreshRequest = requestUrl.includes('/users/auth/refresh/');
    const isBypassRequest = shouldBypassAuthHeader(requestUrl);

    // Recover token-expiration scenarios on both 401 and token-related 403.
    if (shouldAttemptRefresh(error) && !isRefreshRequest && !isBypassRequest && !originalRequest?._retry) {
      originalRequest._retry = true;

      const refreshToken = getRefreshToken();

      if (!refreshToken) {
        terminateSession('session_expired');
        return Promise.reject(error);
      }

      // If another request is already refreshing, queue this one
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          subscribeTokenRefresh(
            (newToken: string) => {
              originalRequest.headers.Authorization = `Bearer ${newToken}`;
              resolve(api(originalRequest));
            },
            (err: unknown) => {
              reject(err);
            },
          );
        });
      }

      isRefreshing = true;

      try {
        const response = await axios.post(`${API_BASE_URL}/users/auth/refresh/`, {
          refresh_token: refreshToken,
        });

        const { access } = response.data;
        // Save back to whichever storage originally held the token
        const tokenStorage = getTokenStorage();
        tokenStorage.setItem('access_token', access);

        // Update Zustand store in both storages (best-effort)
        try {
          for (const storage of [sessionStorage, localStorage]) {
            const authData = storage.getItem('auth-storage');
            if (authData) {
              const parsed = JSON.parse(authData);
              if (parsed?.state) {
                parsed.state.accessToken = access;
                storage.setItem('auth-storage', JSON.stringify(parsed));
              }
            }
          }
        } catch {
          // Zustand sync is best-effort
        }

        isRefreshing = false;
        onRefreshed(access);

        // Retry original request
        originalRequest.headers.Authorization = `Bearer ${access}`;
        return api(originalRequest);
      } catch (refreshError) {
        isRefreshing = false;
        onRefreshFailed(refreshError);
        terminateSession('session_expired');
        return Promise.reject(refreshError);
      }
    }

    // Token/state drift can surface as tenant-level 403s. Force clean logout.
    if (isTenantAccessDenied(error)) {
      terminateSession('tenant_access_denied');
    }

    return Promise.reject(error);
  }
);

export default api;
