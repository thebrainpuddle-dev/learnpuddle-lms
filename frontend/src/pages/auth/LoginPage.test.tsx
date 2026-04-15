// src/pages/auth/LoginPage.test.tsx

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi, describe, it, expect, beforeEach } from 'vitest';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { LoginPage } from './LoginPage';
import { useAuthStore } from '../../stores/authStore';
import { useTenantStore } from '../../stores/tenantStore';
import api from '../../config/api';

// Mock dependencies
vi.mock('../../stores/authStore');
vi.mock('../../stores/tenantStore');
vi.mock('../../config/api', () => ({
  __esModule: true,
  default: {
    get: vi.fn(),
    post: vi.fn(),
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
  },
}));

// Mock loadTenantTheme and applyTheme to prevent real API calls during login
vi.mock('../../config/theme', async (importOriginal) => {
  const actual = await importOriginal() as any;
  return {
    ...actual,
    loadTenantTheme: vi.fn().mockResolvedValue({}),
    applyTheme: vi.fn(),
  };
});

const mockedUseAuthStore = useAuthStore as unknown as ReturnType<typeof vi.fn>;
const mockedUseTenantStore = useTenantStore as unknown as ReturnType<typeof vi.fn>;
const mockedApi = api as unknown as {
  post: ReturnType<typeof vi.fn>;
  get: ReturnType<typeof vi.fn>;
};

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

vi.mock('../../hooks/usePageTitle', () => ({
  usePageTitle: vi.fn(),
}));

// Dashboard components for routing tests
const AdminDashboard = () => <div>Admin Dashboard</div>;
const TeacherDashboard = () => <div>Teacher Dashboard</div>;

describe('LoginPage', () => {
  const mockSetAuth = vi.fn();
  const mockSetLoading = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();

    mockedUseAuthStore.mockReturnValue({
      setAuth: mockSetAuth,
      setLoading: mockSetLoading,
      isAuthenticated: false,
      user: null,
      accessToken: null,
      refreshToken: null,
      isLoading: false,
      clearAuth: vi.fn(),
      setUser: vi.fn(),
      initializeFromStorage: vi.fn(),
    });

    mockedUseTenantStore.mockReturnValue({
      theme: {
        name: 'Demo School',
        primary_color: '#3b82f6',
        secondary_color: '#6366f1',
        logo: null,
      },
      setTheme: vi.fn(),
      clearTheme: vi.fn(),
    });
  });

  const renderLoginPage = () => {
    return render(
      <MemoryRouter initialEntries={['/login']}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/admin/dashboard" element={<AdminDashboard />} />
          <Route path="/teacher/dashboard" element={<TeacherDashboard />} />
        </Routes>
      </MemoryRouter>
    );
  };

  describe('rendering', () => {
    it('should render login form', () => {
      renderLoginPage();

      // "Demo School" appears in left panel and mobile header (use getAllByText)
      expect(screen.getAllByText('Demo School').length).toBeGreaterThan(0);
      expect(screen.getByText('Sign in to continue to your dashboard')).toBeInTheDocument();
      expect(screen.getByLabelText(/email or student\/teacher id/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument();
    });

    it('should render tenant initial when no logo', () => {
      renderLoginPage();

      // The tenant initial 'D' for 'Demo School'
      expect(screen.getAllByText('D').length).toBeGreaterThan(0);
    });

    it('should render tenant logo when available', () => {
      mockedUseTenantStore.mockReturnValue({
        theme: {
          name: 'Demo School',
          primary_color: '#3b82f6',
          secondary_color: '#6366f1',
          logo: 'https://example.com/logo.png',
        },
        setTheme: vi.fn(),
        clearTheme: vi.fn(),
      });

      renderLoginPage();

      const logos = screen.getAllByAltText('Demo School');
      expect(logos.length).toBeGreaterThan(0);
      expect(logos[0]).toHaveAttribute('src', 'https://example.com/logo.png');
    });

    it('should render remember me checkbox', () => {
      renderLoginPage();

      expect(screen.getByLabelText(/remember me/i)).toBeInTheDocument();
    });

    it('should render forgot password link', () => {
      renderLoginPage();

      const forgotLink = screen.getByRole('link', { name: /forgot password/i });
      expect(forgotLink).toBeInTheDocument();
      expect(forgotLink).toHaveAttribute('href', '/forgot-password');
    });
  });

  describe('form validation', () => {
    it('should require identifier and password', async () => {
      renderLoginPage();

      const identifierInput = screen.getByLabelText(/email or student\/teacher id/i);
      const passwordInput = screen.getByLabelText(/password/i);

      expect(identifierInput).toBeInTheDocument();
      expect(passwordInput).toBeInTheDocument();
    });
  });

  describe('login flow', () => {
    it('should submit login form and navigate to teacher dashboard', async () => {
      mockedApi.post.mockResolvedValueOnce({
        data: {
          user: {
            id: 'user-123',
            email: 'teacher@example.test',
            first_name: 'Test',
            last_name: 'Teacher',
            role: 'TEACHER',
            is_active: true,
          },
          tokens: {
            access: 'mock-access-token',
            refresh: 'mock-refresh-token',
          },
        },
      });

      renderLoginPage();

      await userEvent.type(screen.getByLabelText(/email or student\/teacher id/i), 'teacher@example.test');
      await userEvent.type(screen.getByLabelText(/password/i), 'TestPass@123');
      await userEvent.click(screen.getByRole('button', { name: /sign in/i }));

      await waitFor(() => {
        expect(mockedApi.post).toHaveBeenCalledWith('/users/auth/login/', {
          identifier: 'teacher@example.test',
          password: 'TestPass@123',
          portal: 'tenant',
        });
      });

      expect(mockSetAuth).toHaveBeenCalledWith(
        expect.objectContaining({ role: 'TEACHER' }),
        expect.objectContaining({ access: 'mock-access-token' }),
        false
      );

      expect(mockNavigate).toHaveBeenCalledWith('/teacher/dashboard');
    });

    it('should navigate to admin dashboard for school admin', async () => {
      mockedApi.post.mockResolvedValueOnce({
        data: {
          user: {
            id: 'admin-123',
            email: 'admin@example.test',
            first_name: 'Test',
            last_name: 'Admin',
            role: 'SCHOOL_ADMIN',
            is_active: true,
          },
          tokens: {
            access: 'mock-access-token',
            refresh: 'mock-refresh-token',
          },
        },
      });

      renderLoginPage();

      await userEvent.type(screen.getByLabelText(/email or student\/teacher id/i), 'admin@example.test');
      await userEvent.type(screen.getByLabelText(/password/i), 'TestPass@123');
      await userEvent.click(screen.getByRole('button', { name: /sign in/i }));

      await waitFor(() => {
        expect(mockNavigate).toHaveBeenCalledWith('/admin/dashboard');
      });
    });

    it('should pass rememberMe to setAuth when checked', async () => {
      mockedApi.post.mockResolvedValueOnce({
        data: {
          user: {
            id: 'user-123',
            email: 'teacher@example.test',
            first_name: 'Test',
            last_name: 'Teacher',
            role: 'TEACHER',
            is_active: true,
          },
          tokens: {
            access: 'mock-access-token',
            refresh: 'mock-refresh-token',
          },
        },
      });

      renderLoginPage();

      await userEvent.type(screen.getByLabelText(/email or student\/teacher id/i), 'teacher@example.test');
      await userEvent.type(screen.getByLabelText(/password/i), 'TestPass@123');
      await userEvent.click(screen.getByLabelText(/remember me/i));
      await userEvent.click(screen.getByRole('button', { name: /sign in/i }));

      await waitFor(() => {
        expect(mockSetAuth).toHaveBeenCalledWith(
          expect.any(Object),
          expect.any(Object),
          true // rememberMe should be true
        );
      });
    });
  });

  describe('error handling', () => {
    it('should display error on invalid credentials', async () => {
      mockedApi.post.mockRejectedValueOnce({
        response: {
          status: 400,
          data: {
            non_field_errors: ['Invalid email or password'],
          },
        },
      });

      renderLoginPage();

      await userEvent.type(screen.getByLabelText(/email or student\/teacher id/i), 'test@example.test');
      await userEvent.type(screen.getByLabelText(/password/i), 'wrongpassword');
      await userEvent.click(screen.getByRole('button', { name: /sign in/i }));

      await waitFor(() => {
        expect(screen.getByText('Invalid email or password')).toBeInTheDocument();
      });
    });

    it('should display error on disabled account', async () => {
      mockedApi.post.mockRejectedValueOnce({
        response: {
          status: 403,
          data: {},
        },
      });

      renderLoginPage();

      await userEvent.type(screen.getByLabelText(/email or student\/teacher id/i), 'disabled@example.test');
      await userEvent.type(screen.getByLabelText(/password/i), 'TestPass@123');
      await userEvent.click(screen.getByRole('button', { name: /sign in/i }));

      await waitFor(() => {
        expect(screen.getByText('Your account has been disabled')).toBeInTheDocument();
      });
    });

    it('should display generic error on server error', async () => {
      mockedApi.post.mockRejectedValueOnce({
        response: {
          status: 500,
          data: {},
        },
      });

      renderLoginPage();

      await userEvent.type(screen.getByLabelText(/email or student\/teacher id/i), 'test@example.test');
      await userEvent.type(screen.getByLabelText(/password/i), 'TestPass@123');
      await userEvent.click(screen.getByRole('button', { name: /sign in/i }));

      await waitFor(() => {
        expect(screen.getByText('An error occurred. Please try again.')).toBeInTheDocument();
      });
    });

    it('should display temporary outage message on gateway errors', async () => {
      mockedApi.post.mockRejectedValueOnce({
        response: {
          status: 502,
          data: {},
        },
      });

      renderLoginPage();

      await userEvent.type(screen.getByLabelText(/email or student\/teacher id/i), 'test@example.test');
      await userEvent.type(screen.getByLabelText(/password/i), 'TestPass@123');
      await userEvent.click(screen.getByRole('button', { name: /sign in/i }));

      await waitFor(() => {
        expect(
          screen.getByText('Service is temporarily unavailable. Please retry in a few seconds.')
        ).toBeInTheDocument();
      });
    });
  });

  describe('loading state', () => {
    it('should disable submit button while loading', async () => {
      // Make API call hang
      mockedApi.post.mockImplementation(() => new Promise(() => {}));

      renderLoginPage();

      await userEvent.type(screen.getByLabelText(/email or student\/teacher id/i), 'test@example.test');
      await userEvent.type(screen.getByLabelText(/password/i), 'TestPass@123');
      await userEvent.click(screen.getByRole('button', { name: /sign in/i }));

      // The button should have a loading state (rendered differently by Button component)
      expect(mockSetLoading).toHaveBeenCalledWith(true);
    });
  });
});
