// src/App.tsx

import React, { useEffect, useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { applyTheme, loadTenantTheme, DEFAULT_THEME, type TenantTheme } from './config/theme';
import { ProtectedRoute, ToastProvider, ErrorBoundary, PWAPrompt, OfflineIndicator } from './components/common';
import { LoginPage } from './pages/auth/LoginPage';
import { SuperAdminLoginPage } from './pages/auth/SuperAdminLoginPage';
import { ForgotPasswordPage } from './pages/auth/ForgotPasswordPage';
import { ResetPasswordPage } from './pages/auth/ResetPasswordPage';
import { SSOCallbackPage } from './pages/auth/SSOCallbackPage';
import { SignupPage } from './pages/onboarding/SignupPage';
import { SecuritySettings } from './pages/settings/SecuritySettings';
import { AdminLayout } from './components/layout/AdminLayout';
import { TeacherLayout } from './components/layout/TeacherLayout';
import {
  DashboardPage as AdminDashboardPage,
  TeachersPage,
  CreateTeacherPage,
  CoursesPage as AdminCoursesPage,
  CourseEditorPage,
  AnalyticsPage,
  SettingsPage,
  GroupsPage,
  RemindersPage,
  MediaLibraryPage,
  AnnouncementsPage,
} from './pages/admin';
import {
  DashboardPage as TeacherDashboardPage,
  MyCoursesPage,
  CourseViewPage,
  AssignmentsPage,
  RemindersPage as TeacherRemindersPage,
  QuizPage,
  ProfilePage,
} from './pages/teacher';
import { SuperAdminLayout } from './components/layout/SuperAdminLayout';
import {
  SuperAdminDashboardPage,
  OperationsPage as SuperAdminOperationsPage,
  SchoolsPage as SuperAdminSchoolsPage,
  SchoolDetailPage as SuperAdminSchoolDetailPage,
} from './pages/superadmin';
import api from './config/api';
import { useSessionLifecycle } from './hooks/useSessionLifecycle';
import { useAuthStore } from './stores/authStore';
import { useTenantStore } from './stores/tenantStore';
import { TourProvider } from './components/tour';
import './assets/styles/index.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
      staleTime: 2 * 60 * 1000, // 2 minutes — prevents cascading refetches on every mount
    },
  },
});

function getDashboardPathForRole(role?: string | null): string | null {
  if (role === 'SUPER_ADMIN') return '/super-admin/dashboard';
  if (role === 'SCHOOL_ADMIN') return '/admin/dashboard';
  if (role === 'TEACHER' || role === 'HOD' || role === 'IB_COORDINATOR') return '/teacher/dashboard';
  return null;
}

function AppContent() {
  const { isAuthenticated, user, setUser, clearAuth } = useAuthStore();
  const { setConfig } = useTenantStore();
  const [authValidated, setAuthValidated] = React.useState(!isAuthenticated);
  useSessionLifecycle();
  const dashboardPath = getDashboardPathForRole(user?.role);

  // On startup, validate any persisted token by calling /auth/me/.
  // If the token is expired or missing, clear auth and redirect to login
  // instead of rendering protected pages with broken API calls.
  React.useEffect(() => {
    if (!isAuthenticated) {
      setAuthValidated(true);
      return;
    }
    api.get('/users/auth/me/')
      .then((res) => {
        setUser(res.data);
        setAuthValidated(true);
      })
      .catch(() => {
        clearAuth();
        setAuthValidated(true);
      });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // intentionally runs once on mount

  // Fetch tenant config (features + limits) after login
  React.useEffect(() => {
    if (!isAuthenticated || user?.role === 'SUPER_ADMIN') return;
    api.get('/tenants/config/')
      .then((res) => setConfig(res.data))
      .catch(() => {});
  }, [isAuthenticated, user?.role, setConfig]);

  if (!authValidated) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600" />
      </div>
    );
  }

  return (
    <Routes>
      {/* Public Routes — Tenant login (school admin + teachers) */}
      <Route
        path="/login"
        element={
          isAuthenticated && user && dashboardPath ? (
            <Navigate to={dashboardPath} replace />
          ) : (
            <LoginPage />
          )
        }
      />

      {/* Public Routes — Password Reset */}
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />

      {/* Public Routes — SSO Callback */}
      <Route path="/auth/sso-callback" element={<SSOCallbackPage />} />

      {/* Public Routes — Tenant Self-Service Signup */}
      <Route path="/signup" element={<SignupPage />} />

      {/* Public Routes — Super Admin login (platform admin) */}
      <Route
        path="/super-admin/login"
        element={
          isAuthenticated && user ? (
            <Navigate to={getDashboardPathForRole(user.role) || '/login'} replace />
          ) : (
            <SuperAdminLoginPage />
          )
        }
      />
      
      {/* Protected Super Admin (Command Center) Routes */}
      <Route
        path="/super-admin"
        element={
          <ProtectedRoute allowedRoles={['SUPER_ADMIN']}>
            <SuperAdminLayout />
          </ProtectedRoute>
        }
      >
        <Route path="dashboard" element={<SuperAdminDashboardPage />} />
        <Route path="operations" element={<SuperAdminOperationsPage />} />
        <Route path="schools" element={<SuperAdminSchoolsPage />} />
        <Route path="schools/:tenantId" element={<SuperAdminSchoolDetailPage />} />
        <Route index element={<Navigate to="/super-admin/dashboard" replace />} />
        <Route path="*" element={<Navigate to="/super-admin/dashboard" replace />} />
      </Route>

      {/* Protected Admin Routes with Layout */}
      <Route
        path="/admin"
        element={
          <ProtectedRoute allowedRoles={['SCHOOL_ADMIN']}>
            <AdminLayout />
          </ProtectedRoute>
        }
      >
        <Route path="dashboard" element={<AdminDashboardPage />} />
        <Route path="courses" element={<AdminCoursesPage />} />
        <Route path="courses/new" element={<CourseEditorPage />} />
        <Route path="courses/:courseId/edit" element={<CourseEditorPage />} />
        <Route path="media" element={<MediaLibraryPage />} />
        <Route path="teachers" element={<TeachersPage />} />
        <Route path="teachers/new" element={<CreateTeacherPage />} />
        <Route path="groups" element={<GroupsPage />} />
        <Route path="reminders" element={<RemindersPage />} />
        <Route path="announcements" element={<AnnouncementsPage />} />
        <Route path="analytics" element={<AnalyticsPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="settings/security" element={<SecuritySettings />} />
        <Route index element={<Navigate to="/admin/dashboard" replace />} />
        <Route path="*" element={<Navigate to="/admin/dashboard" replace />} />
      </Route>
      
      {/* Protected Teacher Routes with Layout */}
      <Route
        path="/teacher"
        element={
          <ProtectedRoute allowedRoles={['TEACHER', 'HOD', 'IB_COORDINATOR']}>
            <TeacherLayout />
          </ProtectedRoute>
        }
      >
        <Route path="dashboard" element={<TeacherDashboardPage />} />
        <Route path="courses" element={<MyCoursesPage />} />
        <Route path="courses/:courseId" element={<CourseViewPage />} />
        <Route path="assignments" element={<AssignmentsPage />} />
        <Route path="reminders" element={<TeacherRemindersPage />} />
        <Route path="quizzes/:assignmentId" element={<QuizPage />} />
        <Route path="profile" element={<ProfilePage />} />
        <Route path="settings/security" element={<SecuritySettings />} />
        <Route index element={<Navigate to="/teacher/dashboard" replace />} />
        <Route path="*" element={<Navigate to="/teacher/dashboard" replace />} />
      </Route>
      
      {/* Default redirect */}
      <Route
        path="/"
        element={
          <Navigate
            to={
              isAuthenticated && user && dashboardPath
                ? dashboardPath
                : '/login'
            }
            replace
          />
        }
      />
      
      {/* 404 */}
      <Route
        path="*"
        element={
          <div className="min-h-screen flex items-center justify-center">
            <div className="text-center">
              <h1 className="text-4xl font-bold text-gray-900 mb-4">404</h1>
              <p className="text-gray-600">Page Not Found</p>
            </div>
          </div>
        }
      />
    </Routes>
  );
}

function TenantErrorPage({ theme }: { theme: TenantTheme }) {
  const getIcon = () => {
    switch (theme.tenantErrorReason) {
      case 'trial_expired':
        return (
          <svg className="w-16 h-16 text-amber-500 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        );
      case 'deactivated':
        return (
          <svg className="w-16 h-16 text-red-500 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
          </svg>
        );
      default:
        return (
          <svg className="w-16 h-16 text-gray-400 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        );
    }
  };

  const getTitle = () => {
    switch (theme.tenantErrorReason) {
      case 'trial_expired':
        return 'Trial Period Expired';
      case 'deactivated':
        return 'Account Deactivated';
      default:
        return 'School Not Found';
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 flex items-center justify-center p-4">
      <div className="max-w-md w-full bg-white rounded-2xl shadow-xl p-8 text-center">
        {getIcon()}
        <h1 className="text-2xl font-bold text-gray-900 mb-2">{getTitle()}</h1>
        {theme.name && theme.name !== 'School Not Found' && (
          <p className="text-lg text-gray-600 mb-4">{theme.name}</p>
        )}
        <p className="text-gray-500 mb-6">
          {theme.tenantErrorMessage || 'This school is not accessible. Please contact support.'}
        </p>
        <div className="space-y-3">
          <a
            href="mailto:support@learnpuddle.com"
            className="block w-full py-3 px-4 bg-primary-600 hover:bg-primary-700 text-white font-medium rounded-lg transition-colors"
          >
            Contact Support
          </a>
          <a
            href="https://learnpuddle.com"
            className="block w-full py-3 px-4 bg-gray-100 hover:bg-gray-200 text-gray-700 font-medium rounded-lg transition-colors"
          >
            Go to LearnPuddle Home
          </a>
        </div>
        {theme.tenantErrorReason === 'trial_expired' && (
          <p className="mt-6 text-sm text-gray-400">
            Trial ended? Upgrade your plan to continue using the platform.
          </p>
        )}
      </div>
    </div>
  );
}

function App() {
  const [loading, setLoading] = useState(true);
  const { theme, setTheme } = useTenantStore();
  
  useEffect(() => {
    loadTenantTheme()
      .then((tenantTheme) => {
        applyTheme(tenantTheme);
        setTheme(tenantTheme);
        setLoading(false);
      })
      .catch(() => {
        applyTheme(DEFAULT_THEME);
        setTheme(DEFAULT_THEME);
        setLoading(false);
      });
  }, [setTheme]);
  
  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600"></div>
      </div>
    );
  }

  // Show tenant error page if tenant not found or deactivated
  if (!theme.tenantFound) {
    return <TenantErrorPage theme={theme} />;
  }
  
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <BrowserRouter>
            <OfflineIndicator />
            <TourProvider>
              <AppContent />
            </TourProvider>
            <PWAPrompt />
          </BrowserRouter>
        </ToastProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  );
}

export default App;
