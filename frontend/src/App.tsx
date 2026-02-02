// src/App.tsx

import React, { useEffect, useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { applyTheme, loadTenantTheme, DEFAULT_THEME } from './config/theme';
import { ProtectedRoute, ToastProvider } from './components/common';
import { LoginPage } from './pages/auth/LoginPage';
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
} from './pages/admin';
import {
  DashboardPage as TeacherDashboardPage,
  MyCoursesPage,
  CourseViewPage,
  AssignmentsPage,
  ProfilePage,
} from './pages/teacher';
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
  
  return (
    <Routes>
      {/* Public Routes */}
      <Route
        path="/login"
        element={
          isAuthenticated ? (
            <Navigate
              to={user?.role === 'SCHOOL_ADMIN' ? '/admin/dashboard' : '/teacher/dashboard'}
              replace
            />
          ) : (
            <LoginPage />
          )
        }
      />
      
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
        <Route path="teachers" element={<TeachersPage />} />
        <Route path="teachers/new" element={<CreateTeacherPage />} />
        <Route path="groups" element={<GroupsPage />} />
        <Route path="reminders" element={<RemindersPage />} />
        <Route path="analytics" element={<AnalyticsPage />} />
        <Route path="settings" element={<SettingsPage />} />
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
        <Route path="profile" element={<ProfilePage />} />
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
                ? user?.role === 'SCHOOL_ADMIN'
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
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <BrowserRouter>
          <AppContent />
        </BrowserRouter>
      </ToastProvider>
    </QueryClientProvider>
  );
}

export default App;
