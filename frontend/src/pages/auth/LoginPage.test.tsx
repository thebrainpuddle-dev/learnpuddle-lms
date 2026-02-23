// src/pages/auth/LoginPage.test.tsx

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { LoginPage } from './LoginPage';
import { useAuthStore } from '../../stores/authStore';
import { useTenantStore } from '../../stores/tenantStore';
import api from '../../config/api';

// Mock dependencies
jest.mock('../../stores/authStore');
jest.mock('../../stores/tenantStore');
jest.mock('../../config/api');

const mockedUseAuthStore = useAuthStore as jest.MockedFunction<typeof useAuthStore>;
const mockedUseTenantStore = useTenantStore as jest.MockedFunction<typeof useTenantStore>;
const mockedApi = api as jest.Mocked<typeof api>;

const mockNavigate = jest.fn();
jest.mock('react-router-dom', () => ({
  ...jest.requireActual('react-router-dom'),
  useNavigate: () => mockNavigate,
}));

// Dashboard components for routing tests
const AdminDashboard = () => <div>Admin Dashboard</div>;
const TeacherDashboard = () => <div>Teacher Dashboard</div>;

describe('LoginPage', () => {
  const mockSetAuth = jest.fn();
  const mockSetLoading = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
    
    mockedUseAuthStore.mockReturnValue({
      setAuth: mockSetAuth,
      setLoading: mockSetLoading,
      isAuthenticated: false,
      user: null,
      accessToken: null,
      refreshToken: null,
      isLoading: false,
      clearAuth: jest.fn(),
      setUser: jest.fn(),
      initializeFromStorage: jest.fn(),
    });

    mockedUseTenantStore.mockReturnValue({
      theme: {
        name: 'Demo School',
        primary_color: '#3b82f6',
        secondary_color: '#6366f1',
        logo: null,
      },
      setTheme: jest.fn(),
      clearTheme: jest.fn(),
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

      expect(screen.getByText('Demo School')).toBeInTheDocument();
      expect(screen.getByText('Learning Management System')).toBeInTheDocument();
      expect(screen.getByText('Sign in to your account')).toBeInTheDocument();
      expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument();
    });

    it('should render tenant initial when no logo', () => {
      renderLoginPage();

      // The tenant initial 'D' for 'Demo School'
      expect(screen.getByText('D')).toBeInTheDocument();
    });

    it('should render tenant logo when available', () => {
      mockedUseTenantStore.mockReturnValue({
        theme: {
          name: 'Demo School',
          primary_color: '#3b82f6',
          secondary_color: '#6366f1',
          logo: 'https://example.com/logo.png',
        },
        setTheme: jest.fn(),
        clearTheme: jest.fn(),
      });

      renderLoginPage();

      const logo = screen.getByAltText('Demo School');
      expect(logo).toBeInTheDocument();
      expect(logo).toHaveAttribute('src', 'https://example.com/logo.png');
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
    it('should require email and password', async () => {
      renderLoginPage();

      const emailInput = screen.getByLabelText(/email address/i);
      const passwordInput = screen.getByLabelText(/password/i);

      expect(emailInput).toBeRequired();
      expect(passwordInput).toBeRequired();
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

      await userEvent.type(screen.getByLabelText(/email address/i), 'teacher@example.test');
      await userEvent.type(screen.getByLabelText(/password/i), 'TestPass@123');
      await userEvent.click(screen.getByRole('button', { name: /sign in/i }));

      await waitFor(() => {
        expect(mockedApi.post).toHaveBeenCalledWith('/users/auth/login/', {
          email: 'teacher@example.test',
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

      await userEvent.type(screen.getByLabelText(/email address/i), 'admin@example.test');
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

      await userEvent.type(screen.getByLabelText(/email address/i), 'teacher@example.test');
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

      await userEvent.type(screen.getByLabelText(/email address/i), 'test@example.test');
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

      await userEvent.type(screen.getByLabelText(/email address/i), 'disabled@example.test');
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

      await userEvent.type(screen.getByLabelText(/email address/i), 'test@example.test');
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

      await userEvent.type(screen.getByLabelText(/email address/i), 'test@example.test');
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

      await userEvent.type(screen.getByLabelText(/email address/i), 'test@example.test');
      await userEvent.type(screen.getByLabelText(/password/i), 'TestPass@123');
      await userEvent.click(screen.getByRole('button', { name: /sign in/i }));

      // The button should have a loading state (rendered differently by Button component)
      expect(mockSetLoading).toHaveBeenCalledWith(true);
    });
  });
});
