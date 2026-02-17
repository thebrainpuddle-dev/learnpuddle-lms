// src/config/api.ts

import axios, { AxiosInstance } from 'axios';

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

/**
 * Clear persisted Zustand auth state so stale isAuthenticated=true
 * does not cause redirect loops on page reload.
 */
function clearPersistedAuth() {
  try {
    for (const storage of [sessionStorage, localStorage]) {
      const raw = storage.getItem('auth-storage');
      if (raw) {
        const parsed = JSON.parse(raw);
        if (parsed?.state) {
          parsed.state.isAuthenticated = false;
          parsed.state.user = null;
          parsed.state.accessToken = null;
          parsed.state.refreshToken = null;
          storage.setItem('auth-storage', JSON.stringify(parsed));
        }
      }
    }
  } catch { /* best-effort */ }
}

/**
 * Request interceptor to add auth token and set Content-Type
 * Uses sessionStorage for tab-isolated sessions (prevents cross-tab token conflicts)
 */
api.interceptors.request.use(
  (config) => {
    const token = sessionStorage.getItem('access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
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
    const originalRequest = error.config;

    // If token expired and not already retrying this specific request
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;

      const refreshToken = sessionStorage.getItem('refresh_token');
      // Determine which login page to redirect to based on current path
      const currentPath = window.location.pathname;
      const loginPath = currentPath.startsWith('/super-admin')
        ? '/super-admin/login'
        : '/login';

      // Avoid redirect loop: if already on a login page, just reject
      const isOnLoginPage = currentPath === '/login' || currentPath === '/super-admin/login';

      if (!refreshToken) {
        // No refresh token - session expired
        sessionStorage.removeItem('access_token');
        sessionStorage.removeItem('refresh_token');
        clearPersistedAuth();
        if (!isOnLoginPage) window.location.href = loginPath;
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
        sessionStorage.setItem('access_token', access);

        // Update Zustand store if available
        try {
          const authData = sessionStorage.getItem('auth-storage');
          if (authData) {
            const parsed = JSON.parse(authData);
            if (parsed?.state) {
              parsed.state.accessToken = access;
              sessionStorage.setItem('auth-storage', JSON.stringify(parsed));
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
        // Refresh failed, logout user and redirect to login
        sessionStorage.removeItem('access_token');
        sessionStorage.removeItem('refresh_token');
        clearPersistedAuth();
        if (!isOnLoginPage) window.location.href = loginPath;
        return Promise.reject(refreshError);
      }
    }

    return Promise.reject(error);
  }
);

export default api;
