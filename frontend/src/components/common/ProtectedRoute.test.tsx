// src/components/common/ProtectedRoute.test.tsx

import React from 'react';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { ProtectedRoute } from './ProtectedRoute';
import { useAuthStore } from '../../stores/authStore';

// Mock the auth store
jest.mock('../../stores/authStore');
const mockedUseAuthStore = useAuthStore as jest.MockedFunction<typeof useAuthStore>;

const TestComponent = () => <div>Protected Content</div>;
const LoginPage = () => <div>Login Page</div>;
const SuperAdminLoginPage = () => <div>Super Admin Login Page</div>;
const AdminDashboard = () => <div>Admin Dashboard</div>;
const TeacherDashboard = () => <div>Teacher Dashboard</div>;
const SuperAdminDashboard = () => <div>Super Admin Dashboard</div>;

describe('ProtectedRoute', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('unauthenticated users', () => {
    beforeEach(() => {
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
    });

    it('should redirect to /login for unauthenticated users', () => {
      render(
        <MemoryRouter initialEntries={['/protected']}>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route
              path="/protected"
              element={
                <ProtectedRoute>
                  <TestComponent />
                </ProtectedRoute>
              }
            />
          </Routes>
        </MemoryRouter>
      );

      expect(screen.getByText('Login Page')).toBeInTheDocument();
      expect(screen.queryByText('Protected Content')).not.toBeInTheDocument();
    });

    it('should redirect to /super-admin/login for super admin routes', () => {
      render(
        <MemoryRouter initialEntries={['/super-admin/dashboard']}>
          <Routes>
            <Route path="/super-admin/login" element={<SuperAdminLoginPage />} />
            <Route
              path="/super-admin/dashboard"
              element={
                <ProtectedRoute>
                  <TestComponent />
                </ProtectedRoute>
              }
            />
          </Routes>
        </MemoryRouter>
      );

      expect(screen.getByText('Super Admin Login Page')).toBeInTheDocument();
      expect(screen.queryByText('Protected Content')).not.toBeInTheDocument();
    });
  });

  describe('authenticated users without role restrictions', () => {
    beforeEach(() => {
      mockedUseAuthStore.mockReturnValue({
        isAuthenticated: true,
        user: {
          id: 'user-123',
          email: 'test@example.com',
          first_name: 'John',
          last_name: 'Doe',
          role: 'TEACHER',
          is_active: true,
        },
        accessToken: 'mock-token',
        refreshToken: 'mock-refresh',
        isLoading: false,
        setAuth: jest.fn(),
        clearAuth: jest.fn(),
        setUser: jest.fn(),
        setLoading: jest.fn(),
        initializeFromStorage: jest.fn(),
      });
    });

    it('should render protected content for authenticated users', () => {
      render(
        <MemoryRouter initialEntries={['/protected']}>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route
              path="/protected"
              element={
                <ProtectedRoute>
                  <TestComponent />
                </ProtectedRoute>
              }
            />
          </Routes>
        </MemoryRouter>
      );

      expect(screen.getByText('Protected Content')).toBeInTheDocument();
      expect(screen.queryByText('Login Page')).not.toBeInTheDocument();
    });
  });

  describe('role-based access control', () => {
    it('should allow access when user has correct role', () => {
      mockedUseAuthStore.mockReturnValue({
        isAuthenticated: true,
        user: {
          id: 'user-123',
          email: 'admin@example.com',
          first_name: 'Admin',
          last_name: 'User',
          role: 'SCHOOL_ADMIN',
          is_active: true,
        },
        accessToken: 'mock-token',
        refreshToken: 'mock-refresh',
        isLoading: false,
        setAuth: jest.fn(),
        clearAuth: jest.fn(),
        setUser: jest.fn(),
        setLoading: jest.fn(),
        initializeFromStorage: jest.fn(),
      });

      render(
        <MemoryRouter initialEntries={['/admin/settings']}>
          <Routes>
            <Route
              path="/admin/settings"
              element={
                <ProtectedRoute allowedRoles={['SCHOOL_ADMIN']}>
                  <TestComponent />
                </ProtectedRoute>
              }
            />
          </Routes>
        </MemoryRouter>
      );

      expect(screen.getByText('Protected Content')).toBeInTheDocument();
    });

    it('should redirect TEACHER to teacher dashboard when accessing admin routes', () => {
      mockedUseAuthStore.mockReturnValue({
        isAuthenticated: true,
        user: {
          id: 'user-123',
          email: 'teacher@example.com',
          first_name: 'Teacher',
          last_name: 'User',
          role: 'TEACHER',
          is_active: true,
        },
        accessToken: 'mock-token',
        refreshToken: 'mock-refresh',
        isLoading: false,
        setAuth: jest.fn(),
        clearAuth: jest.fn(),
        setUser: jest.fn(),
        setLoading: jest.fn(),
        initializeFromStorage: jest.fn(),
      });

      render(
        <MemoryRouter initialEntries={['/admin/settings']}>
          <Routes>
            <Route path="/teacher/dashboard" element={<TeacherDashboard />} />
            <Route
              path="/admin/settings"
              element={
                <ProtectedRoute allowedRoles={['SCHOOL_ADMIN']}>
                  <TestComponent />
                </ProtectedRoute>
              }
            />
          </Routes>
        </MemoryRouter>
      );

      expect(screen.getByText('Teacher Dashboard')).toBeInTheDocument();
      expect(screen.queryByText('Protected Content')).not.toBeInTheDocument();
    });

    it('should redirect SCHOOL_ADMIN to admin dashboard when accessing teacher routes', () => {
      mockedUseAuthStore.mockReturnValue({
        isAuthenticated: true,
        user: {
          id: 'user-123',
          email: 'admin@example.com',
          first_name: 'Admin',
          last_name: 'User',
          role: 'SCHOOL_ADMIN',
          is_active: true,
        },
        accessToken: 'mock-token',
        refreshToken: 'mock-refresh',
        isLoading: false,
        setAuth: jest.fn(),
        clearAuth: jest.fn(),
        setUser: jest.fn(),
        setLoading: jest.fn(),
        initializeFromStorage: jest.fn(),
      });

      render(
        <MemoryRouter initialEntries={['/teacher/courses']}>
          <Routes>
            <Route path="/admin/dashboard" element={<AdminDashboard />} />
            <Route
              path="/teacher/courses"
              element={
                <ProtectedRoute allowedRoles={['TEACHER']}>
                  <TestComponent />
                </ProtectedRoute>
              }
            />
          </Routes>
        </MemoryRouter>
      );

      expect(screen.getByText('Admin Dashboard')).toBeInTheDocument();
      expect(screen.queryByText('Protected Content')).not.toBeInTheDocument();
    });

    it('should redirect SUPER_ADMIN to super admin dashboard when accessing wrong routes', () => {
      mockedUseAuthStore.mockReturnValue({
        isAuthenticated: true,
        user: {
          id: 'user-123',
          email: 'superadmin@example.com',
          first_name: 'Super',
          last_name: 'Admin',
          role: 'SUPER_ADMIN',
          is_active: true,
        },
        accessToken: 'mock-token',
        refreshToken: 'mock-refresh',
        isLoading: false,
        setAuth: jest.fn(),
        clearAuth: jest.fn(),
        setUser: jest.fn(),
        setLoading: jest.fn(),
        initializeFromStorage: jest.fn(),
      });

      render(
        <MemoryRouter initialEntries={['/admin/settings']}>
          <Routes>
            <Route path="/super-admin/dashboard" element={<SuperAdminDashboard />} />
            <Route
              path="/admin/settings"
              element={
                <ProtectedRoute allowedRoles={['SCHOOL_ADMIN']}>
                  <TestComponent />
                </ProtectedRoute>
              }
            />
          </Routes>
        </MemoryRouter>
      );

      expect(screen.getByText('Super Admin Dashboard')).toBeInTheDocument();
      expect(screen.queryByText('Protected Content')).not.toBeInTheDocument();
    });

    it('should allow multiple roles', () => {
      mockedUseAuthStore.mockReturnValue({
        isAuthenticated: true,
        user: {
          id: 'user-123',
          email: 'teacher@example.com',
          first_name: 'Teacher',
          last_name: 'User',
          role: 'TEACHER',
          is_active: true,
        },
        accessToken: 'mock-token',
        refreshToken: 'mock-refresh',
        isLoading: false,
        setAuth: jest.fn(),
        clearAuth: jest.fn(),
        setUser: jest.fn(),
        setLoading: jest.fn(),
        initializeFromStorage: jest.fn(),
      });

      render(
        <MemoryRouter initialEntries={['/shared/page']}>
          <Routes>
            <Route
              path="/shared/page"
              element={
                <ProtectedRoute allowedRoles={['TEACHER', 'SCHOOL_ADMIN']}>
                  <TestComponent />
                </ProtectedRoute>
              }
            />
          </Routes>
        </MemoryRouter>
      );

      expect(screen.getByText('Protected Content')).toBeInTheDocument();
    });
  });
});
