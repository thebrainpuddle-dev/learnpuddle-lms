// src/stores/authStore.ts

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { User } from '../types';
import { useTenantStore } from './tenantStore';
import { useBillingStore } from './billingStore';
import { useGamificationStore } from './gamificationStore';

// Storage key constants
const ACCESS_TOKEN_KEY = 'access_token';
const REFRESH_TOKEN_KEY = 'refresh_token';
const REMEMBER_ME_KEY = 'remember_me';
const SESSION_LAST_ACTIVITY_KEY = 'auth:last_activity_at';

/**
 * Get the appropriate storage based on remember me preference.
 * Checks localStorage first for the remember_me flag.
 */
const getStorage = (): Storage => {
  const rememberMe = localStorage.getItem(REMEMBER_ME_KEY) === 'true';
  return rememberMe ? localStorage : sessionStorage;
};

/**
 * Get tokens from whichever storage they exist in.
 * Checks localStorage first (persistent), then sessionStorage (tab-specific).
 */
const getStoredTokens = () => {
  // Check localStorage first (remember me)
  let accessToken = localStorage.getItem(ACCESS_TOKEN_KEY);
  let refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);
  
  if (accessToken && refreshToken) {
    return { accessToken, refreshToken, storage: 'local' as const };
  }
  
  // Fall back to sessionStorage
  accessToken = sessionStorage.getItem(ACCESS_TOKEN_KEY);
  refreshToken = sessionStorage.getItem(REFRESH_TOKEN_KEY);
  
  if (accessToken && refreshToken) {
    return { accessToken, refreshToken, storage: 'session' as const };
  }
  
  return null;
};

interface AuthState {
  user: User | null;
  accessToken: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  
  // Actions
  setAuth: (user: User, tokens: { access: string; refresh: string }, rememberMe?: boolean) => void;
  clearAuth: () => void;
  setUser: (user: User) => void;
  setLoading: (loading: boolean) => void;
  initializeFromStorage: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
      isLoading: false,
      
      setAuth: (user, tokens, rememberMe = false) => {
        // Clear tokens from the tab-local sessionStorage (always safe)
        sessionStorage.removeItem(ACCESS_TOKEN_KEY);
        sessionStorage.removeItem(REFRESH_TOKEN_KEY);

        // Only clear localStorage tokens when *this* tab is switching to
        // localStorage ("remember me").  Blindly clearing localStorage
        // would destroy another tab's persistent session.
        if (rememberMe) {
          localStorage.setItem(REMEMBER_ME_KEY, 'true');
          localStorage.removeItem(ACCESS_TOKEN_KEY);
          localStorage.removeItem(REFRESH_TOKEN_KEY);
        }

        // Choose storage based on remember me
        const storage = rememberMe ? localStorage : sessionStorage;
        storage.setItem(ACCESS_TOKEN_KEY, tokens.access);
        storage.setItem(REFRESH_TOKEN_KEY, tokens.refresh);
        localStorage.setItem(SESSION_LAST_ACTIVITY_KEY, String(Date.now()));

        // Store tenant subdomain for X-Tenant-Subdomain header (localhost dev)
        if (user.tenant_subdomain) {
          storage.setItem('tenant_subdomain', user.tenant_subdomain);
        }
        
        set({
          user,
          accessToken: tokens.access,
          refreshToken: tokens.refresh,
          isAuthenticated: true,
        });
      },
      
      clearAuth: () => {
        // Always clear tab-local sessionStorage
        sessionStorage.removeItem(ACCESS_TOKEN_KEY);
        sessionStorage.removeItem(REFRESH_TOKEN_KEY);
        sessionStorage.removeItem('tenant_subdomain');

        // Only clear localStorage tokens if *this* session uses "remember me"
        // (i.e. tokens were stored in localStorage). This prevents a logout
        // in one tab from wiping another user's persistent session.
        const wasRememberMe = localStorage.getItem(REMEMBER_ME_KEY) === 'true';
        if (wasRememberMe) {
          localStorage.removeItem(ACCESS_TOKEN_KEY);
          localStorage.removeItem(REFRESH_TOKEN_KEY);
          localStorage.removeItem(REMEMBER_ME_KEY);
          localStorage.removeItem('tenant_subdomain');
        }
        localStorage.removeItem(SESSION_LAST_ACTIVITY_KEY);

        set({
          user: null,
          accessToken: null,
          refreshToken: null,
          isAuthenticated: false,
        });

        // Reset tenant-scoped stores to prevent cross-tenant data leakage
        useTenantStore.getState().reset();
        useBillingStore.getState().reset();
        useGamificationStore.getState().reset();
      },
      
      setUser: (user) => set({ user }),
      setLoading: (loading) => set({ isLoading: loading }),
      
      /**
       * Initialize auth state from stored tokens.
       * Called on app startup to restore session.
       */
      initializeFromStorage: () => {
        const stored = getStoredTokens();
        if (stored) {
          set({
            accessToken: stored.accessToken,
            refreshToken: stored.refreshToken,
            // Note: user data will be fetched via /auth/me/ endpoint
          });
        }
      },
    }),
    {
      name: 'auth-storage',
      // Dynamic storage based on remember me preference
      storage: createJSONStorage(() => getStorage()),
      partialize: (state) => ({
        user: state.user,
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
);
