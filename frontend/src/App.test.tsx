// src/App.test.tsx

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import App from './App';
import { useAuthStore } from './stores/authStore';
import { useTenantStore } from './stores/tenantStore';
import api from './config/api';
import { isPlatformRequest } from './utils/hostRouting';

// Mock stores
jest.mock('./stores/authStore');
jest.mock('./stores/tenantStore');
jest.mock('./utils/hostRouting', () => ({
  isPlatformRequest: jest.fn(),
}));

const mockedUseAuthStore = useAuthStore as jest.MockedFunction<typeof useAuthStore>;
const mockedUseTenantStore = useTenantStore as jest.MockedFunction<typeof useTenantStore>;
const mockedApi = api as jest.Mocked<typeof api>;
const mockedIsPlatformRequest = isPlatformRequest as jest.MockedFunction<typeof isPlatformRequest>;

// Mock api to prevent actual network calls
jest.mock('./config/api', () => {
  const shared = {
    get: jest.fn(),
    post: jest.fn(),
    interceptors: {
      request: { use: jest.fn() },
      response: { use: jest.fn() },
    },
  };

  return {
    __esModule: true,
    api: shared,
    default: shared,
  };
});

describe('App', () => {
  beforeEach(() => {
    jest.clearAllMocks();
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
      setAuth: jest.fn(),
      clearAuth: jest.fn(),
      setUser: jest.fn(),
      setLoading: jest.fn(),
      initializeFromStorage: jest.fn(),
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
      setTheme: jest.fn(),
      setConfig: jest.fn(),
      hasFeature: jest.fn(() => true),
      clearTheme: jest.fn(),
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
      expect(screen.getByText(/sign in to your account/i)).toBeInTheDocument();
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
      setAuth: jest.fn(),
      clearAuth: jest.fn(),
      setUser: jest.fn(),
      setLoading: jest.fn(),
      initializeFromStorage: jest.fn(),
    });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText(/sign in to your account/i)).toBeInTheDocument();
    });
  });

  it('shows product landing page at root on platform host', async () => {
    mockedIsPlatformRequest.mockReturnValue(true);
    window.history.pushState({}, '', '/');

    render(<App />);

    await waitFor(() => {
      expect(
        screen.getByRole('heading', {
          name: /learning management infrastructure for schools and enterprises/i,
        }),
      ).toBeInTheDocument();
    });
  });

  it('redirects /login to / on platform host', async () => {
    mockedIsPlatformRequest.mockReturnValue(true);
    window.history.pushState({}, '', '/login');

    render(<App />);

    await waitFor(() => {
      expect(
        screen.getByRole('heading', {
          name: /learning management infrastructure for schools and enterprises/i,
        }),
      ).toBeInTheDocument();
    });
  });
});
