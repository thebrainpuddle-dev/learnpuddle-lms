// src/App.tsx

import React, { useEffect, useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { applyTheme, loadTenantTheme, DEFAULT_THEME } from './config/theme';
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
  SchoolsPage as SuperAdminSchoolsPage,
  SchoolDetailPage as SuperAdminSchoolDetailPage,
} from './pages/superadmin';
import api from './config/api';
import { useAuthStore } from './stores/authStore';
import { useTenantStore } from './stores/tenantStore';
import './assets/styles/index.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

function AppContent() {
  const { isAuthenticated, user } = useAuthStore();
  const { setConfig } = useTenantStore();

  // Fetch tenant config (features + limits) after login
  React.useEffect(() => {
    if (!isAuthenticated || user?.role === 'SUPER_ADMIN') return;
    api.get('/tenants/config/')
      .then((res) => setConfig(res.data))
      .catch(() => {});
  }, [isAuthenticated, user?.role, setConfig]);

  return (
    <Routes>
      {/* Public Routes — Tenant login (school admin + teachers) */}
      <Route
        path="/login"
        element={
          isAuthenticated ? (
            <Navigate
              to={
                user?.role === 'SUPER_ADMIN'
                  ? '/super-admin/dashboard'
                  : user?.role === 'SCHOOL_ADMIN'
                  ? '/admin/dashboard'
                  : '/teacher/dashboard'
              }
              replace
            />
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
          isAuthenticated && user?.role === 'SUPER_ADMIN' ? (
            <Navigate to="/super-admin/dashboard" replace />
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
              isAuthenticated
                ? user?.role === 'SUPER_ADMIN'
                  ? '/super-admin/dashboard'
                  : user?.role === 'SCHOOL_ADMIN'
                  ? '/admin/dashboard'
                  : '/teacher/dashboard'
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

function App() {
  const [loading, setLoading] = useState(true);
  const { setTheme } = useTenantStore();
  
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
  
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <BrowserRouter>
            <OfflineIndicator />
            <AppContent />
            <PWAPrompt />
          </BrowserRouter>
        </ToastProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  );
}

export default App;
