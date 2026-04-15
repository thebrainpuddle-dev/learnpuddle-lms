// src/App.test.tsx

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import App from './App';
import { useAuthStore } from './stores/authStore';
import { useTenantStore } from './stores/tenantStore';
import api from './config/api';
import { isPlatformRequest } from './utils/hostRouting';

// Mock stores
vi.mock('./stores/authStore');
vi.mock('./stores/tenantStore');
vi.mock('./utils/hostRouting', () => ({
  isPlatformRequest: vi.fn(),
}));

const mockedUseAuthStore = useAuthStore as unknown as ReturnType<typeof vi.fn>;
const mockedUseTenantStore = useTenantStore as unknown as ReturnType<typeof vi.fn>;
const mockedIsPlatformRequest = isPlatformRequest as unknown as ReturnType<typeof vi.fn>;

// Mock api to prevent actual network calls
vi.mock('./config/api', () => {
  const shared = {
    get: vi.fn(),
    post: vi.fn(),
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
  };

  return {
    __esModule: true,
    api: shared,
    default: shared,
  };
});

const mockedApi = api as unknown as { get: ReturnType<typeof vi.fn>; post: ReturnType<typeof vi.fn> };

describe('App', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedApi.get.mockResolvedValue({
      data: {
        name: 'LearnPuddle',
        subdomain: '',
        primary_color: '#8B7CFA',
        secondary_color: '#6D47E8',
        font_family: 'Inter',
        tenant_found: true,
      },
    } as any);
    mockedIsPlatformRequest.mockReturnValue(false);

    // Default unauthenticated state
    mockedUseAuthStore.mockReturnValue({
      isAuthenticated: false,
      user: null,
      accessToken: null,
      refreshToken: null,
      isLoading: false,
      setAuth: vi.fn(),
      clearAuth: vi.fn(),
      setUser: vi.fn(),
      setLoading: vi.fn(),
      initializeFromStorage: vi.fn(),
    });

    mockedUseTenantStore.mockReturnValue({
      theme: {
        name: 'Test School',
        subdomain: 'demo',
        primaryColor: '#3b82f6',
        secondaryColor: '#6366f1',
        fontFamily: 'Inter',
        tenantFound: true,
        logo: null,
      },
      setTheme: vi.fn(),
      setConfig: vi.fn(),
      hasFeature: vi.fn(() => true),
      clearTheme: vi.fn(),
    });
  });

  it('renders without crashing', () => {
    render(<App />);
    // App should render some content
    expect(document.body).toBeInTheDocument();
  });

  it('shows login page for unauthenticated users', async () => {
    render(<App />);

    await waitFor(() => {
      // The login page should be rendered for unauthenticated users
      expect(screen.getByText(/sign in to continue to your dashboard/i)).toBeInTheDocument();
    });
  });

  it('keeps user on login page when auth is partial (prevents redirect loop)', async () => {
    mockedApi.get.mockRejectedValue(new Error('expired'));
    window.history.pushState({}, '', '/login');
    mockedUseAuthStore.mockReturnValue({
      isAuthenticated: true,
      user: null,
      accessToken: 'stale-access-token',
      refreshToken: 'stale-refresh-token',
      isLoading: false,
      setAuth: vi.fn(),
      clearAuth: vi.fn(),
      setUser: vi.fn(),
      setLoading: vi.fn(),
      initializeFromStorage: vi.fn(),
    });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText(/sign in to continue to your dashboard/i)).toBeInTheDocument();
    });
  });

  it('shows product landing page at root on platform host', async () => {
    mockedIsPlatformRequest.mockReturnValue(true);
    window.history.pushState({}, '', '/');

    render(<App />);

    await waitFor(() => {
      expect(
        screen.getByRole('heading', {
          level: 1,
        }),
      ).toBeInTheDocument();
      expect(screen.getByText(/talks back/i)).toBeInTheDocument();
    });
  });

  it('redirects /login to / on platform host', async () => {
    mockedIsPlatformRequest.mockReturnValue(true);
    window.history.pushState({}, '', '/login');

    render(<App />);

    await waitFor(() => {
      expect(
        screen.getByRole('heading', {
          level: 1,
        }),
      ).toBeInTheDocument();
      expect(screen.getByText(/talks back/i)).toBeInTheDocument();
    });
  });
});
