// src/config/api.ts

import axios, { AxiosInstance } from 'axios';

const API_BASE_URL =
  process.env.REACT_APP_API_URL ||
  (process.env.NODE_ENV === 'production' ? '/api' : 'http://localhost:8000/api');

/**
 * Create axios instance with default config
 */
export const api: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

/**
 * Request interceptor to add auth token
 * Uses sessionStorage for tab-isolated sessions (prevents cross-tab token conflicts)
 */
api.interceptors.request.use(
  (config) => {
    const token = sessionStorage.getItem('access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

/**
 * Response interceptor to handle token refresh
 */
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    
    // If token expired and not already retrying
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;
      
      const refreshToken = sessionStorage.getItem('refresh_token');
      // Determine which login page to redirect to based on current path
      const loginPath = window.location.pathname.startsWith('/super-admin')
        ? '/super-admin/login'
        : '/login';

      if (!refreshToken) {
        // No refresh token - session expired, redirect to login
        sessionStorage.removeItem('access_token');
        sessionStorage.removeItem('refresh_token');
        window.location.href = loginPath;
        return Promise.reject(error);
      }

      try {
        const response = await axios.post(`${API_BASE_URL}/users/auth/refresh/`, {
          refresh_token: refreshToken,
        });
        
        const { access } = response.data;
        sessionStorage.setItem('access_token', access);
        
        // Retry original request
        originalRequest.headers.Authorization = `Bearer ${access}`;
        return api(originalRequest);
      } catch (refreshError) {
        // Refresh failed, logout user and redirect to login
        sessionStorage.removeItem('access_token');
        sessionStorage.removeItem('refresh_token');
        window.location.href = loginPath;
        return Promise.reject(refreshError);
      }
    }
    
    return Promise.reject(error);
  }
);

export default api;
