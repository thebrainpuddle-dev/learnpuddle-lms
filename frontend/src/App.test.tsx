// src/App.test.tsx

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import App from './App';
import { useAuthStore } from './stores/authStore';
import { useTenantStore } from './stores/tenantStore';

// Mock stores
jest.mock('./stores/authStore');
jest.mock('./stores/tenantStore');

const mockedUseAuthStore = useAuthStore as jest.MockedFunction<typeof useAuthStore>;
const mockedUseTenantStore = useTenantStore as jest.MockedFunction<typeof useTenantStore>;

// Mock api to prevent actual network calls
jest.mock('./config/api', () => ({
  __esModule: true,
  default: {
    get: jest.fn(),
    post: jest.fn(),
    interceptors: {
      request: { use: jest.fn() },
      response: { use: jest.fn() },
    },
  },
}));

describe('App', () => {
  beforeEach(() => {
    jest.clearAllMocks();

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
        primary_color: '#3b82f6',
        secondary_color: '#6366f1',
        logo: null,
      },
      setTheme: jest.fn(),
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
});
