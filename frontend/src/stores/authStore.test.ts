// src/stores/authStore.test.ts

import { act } from '@testing-library/react';
import { useAuthStore } from './authStore';

// Mock user for testing
const mockUser = {
  id: 'user-123',
  email: 'test@example.com',
  first_name: 'John',
  last_name: 'Doe',
  role: 'TEACHER' as const,
  is_active: true,
  email_verified: true,
  created_at: '2026-01-01T00:00:00Z',
};

const mockTokens = {
  access: 'mock-access-token',
  refresh: 'mock-refresh-token',
};

describe('authStore', () => {
  // Clear storage and reset store before each test
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    
    // Reset Zustand store state
    const { clearAuth } = useAuthStore.getState();
    clearAuth();
  });

  describe('initial state', () => {
    it('should have unauthenticated initial state', () => {
      const state = useAuthStore.getState();
      
      expect(state.user).toBeNull();
      expect(state.accessToken).toBeNull();
      expect(state.refreshToken).toBeNull();
      expect(state.isAuthenticated).toBe(false);
      expect(state.isLoading).toBe(false);
    });
  });

  describe('setAuth', () => {
    it('should set auth state correctly', () => {
      const { setAuth } = useAuthStore.getState();
      
      act(() => {
        setAuth(mockUser, mockTokens);
      });
      
      const state = useAuthStore.getState();
      expect(state.user).toEqual(mockUser);
      expect(state.accessToken).toBe(mockTokens.access);
      expect(state.refreshToken).toBe(mockTokens.refresh);
      expect(state.isAuthenticated).toBe(true);
    });

    it('should store tokens in sessionStorage when rememberMe is false', () => {
      const { setAuth } = useAuthStore.getState();
      
      act(() => {
        setAuth(mockUser, mockTokens, false);
      });
      
      expect(sessionStorage.getItem('access_token')).toBe(mockTokens.access);
      expect(sessionStorage.getItem('refresh_token')).toBe(mockTokens.refresh);
      expect(localStorage.getItem('access_token')).toBeNull();
      expect(localStorage.getItem('refresh_token')).toBeNull();
    });

    it('should store tokens in localStorage when rememberMe is true', () => {
      const { setAuth } = useAuthStore.getState();
      
      act(() => {
        setAuth(mockUser, mockTokens, true);
      });
      
      expect(localStorage.getItem('access_token')).toBe(mockTokens.access);
      expect(localStorage.getItem('refresh_token')).toBe(mockTokens.refresh);
      expect(localStorage.getItem('remember_me')).toBe('true');
      expect(sessionStorage.getItem('access_token')).toBeNull();
      expect(sessionStorage.getItem('refresh_token')).toBeNull();
    });

    it('should clear existing tokens before setting new ones', () => {
      // Pre-populate both storages
      localStorage.setItem('access_token', 'old-local-token');
      sessionStorage.setItem('access_token', 'old-session-token');
      
      const { setAuth } = useAuthStore.getState();
      
      act(() => {
        setAuth(mockUser, mockTokens, false);
      });
      
      // Old localStorage token should be cleared
      expect(localStorage.getItem('access_token')).toBeNull();
      // New token should be in sessionStorage
      expect(sessionStorage.getItem('access_token')).toBe(mockTokens.access);
    });
  });

  describe('clearAuth', () => {
    it('should clear all auth state', () => {
      const { setAuth, clearAuth } = useAuthStore.getState();
      
      // First set auth
      act(() => {
        setAuth(mockUser, mockTokens, true);
      });
      
      // Then clear it
      act(() => {
        clearAuth();
      });
      
      const state = useAuthStore.getState();
      expect(state.user).toBeNull();
      expect(state.accessToken).toBeNull();
      expect(state.refreshToken).toBeNull();
      expect(state.isAuthenticated).toBe(false);
    });

    it('should clear tokens from both storages', () => {
      localStorage.setItem('access_token', 'local-token');
      localStorage.setItem('refresh_token', 'local-refresh');
      localStorage.setItem('remember_me', 'true');
      sessionStorage.setItem('access_token', 'session-token');
      sessionStorage.setItem('refresh_token', 'session-refresh');
      
      const { clearAuth } = useAuthStore.getState();
      
      act(() => {
        clearAuth();
      });
      
      expect(localStorage.getItem('access_token')).toBeNull();
      expect(localStorage.getItem('refresh_token')).toBeNull();
      expect(localStorage.getItem('remember_me')).toBeNull();
      expect(sessionStorage.getItem('access_token')).toBeNull();
      expect(sessionStorage.getItem('refresh_token')).toBeNull();
    });
  });

  describe('setUser', () => {
    it('should update only the user', () => {
      const { setAuth, setUser } = useAuthStore.getState();
      
      // First set auth
      act(() => {
        setAuth(mockUser, mockTokens);
      });
      
      const updatedUser = { ...mockUser, first_name: 'Jane' };
      
      act(() => {
        setUser(updatedUser);
      });
      
      const state = useAuthStore.getState();
      expect(state.user?.first_name).toBe('Jane');
      // Tokens should remain unchanged
      expect(state.accessToken).toBe(mockTokens.access);
    });
  });

  describe('setLoading', () => {
    it('should update loading state', () => {
      const { setLoading } = useAuthStore.getState();
      
      act(() => {
        setLoading(true);
      });
      
      expect(useAuthStore.getState().isLoading).toBe(true);
      
      act(() => {
        setLoading(false);
      });
      
      expect(useAuthStore.getState().isLoading).toBe(false);
    });
  });

  describe('initializeFromStorage', () => {
    it('should restore tokens from localStorage', () => {
      localStorage.setItem('access_token', 'stored-access');
      localStorage.setItem('refresh_token', 'stored-refresh');
      
      const { initializeFromStorage } = useAuthStore.getState();
      
      act(() => {
        initializeFromStorage();
      });
      
      const state = useAuthStore.getState();
      expect(state.accessToken).toBe('stored-access');
      expect(state.refreshToken).toBe('stored-refresh');
    });

    it('should restore tokens from sessionStorage if not in localStorage', () => {
      sessionStorage.setItem('access_token', 'session-access');
      sessionStorage.setItem('refresh_token', 'session-refresh');
      
      const { initializeFromStorage } = useAuthStore.getState();
      
      act(() => {
        initializeFromStorage();
      });
      
      const state = useAuthStore.getState();
      expect(state.accessToken).toBe('session-access');
      expect(state.refreshToken).toBe('session-refresh');
    });

    it('should prefer localStorage over sessionStorage', () => {
      localStorage.setItem('access_token', 'local-access');
      localStorage.setItem('refresh_token', 'local-refresh');
      sessionStorage.setItem('access_token', 'session-access');
      sessionStorage.setItem('refresh_token', 'session-refresh');
      
      const { initializeFromStorage } = useAuthStore.getState();
      
      act(() => {
        initializeFromStorage();
      });
      
      const state = useAuthStore.getState();
      expect(state.accessToken).toBe('local-access');
      expect(state.refreshToken).toBe('local-refresh');
    });

    it('should do nothing if no tokens are stored', () => {
      const { initializeFromStorage } = useAuthStore.getState();
      
      act(() => {
        initializeFromStorage();
      });
      
      const state = useAuthStore.getState();
      expect(state.accessToken).toBeNull();
      expect(state.refreshToken).toBeNull();
    });
  });
});
