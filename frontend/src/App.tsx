// src/App.tsx

import React, { useEffect, useState, Suspense } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { applyTheme, loadTenantTheme, DEFAULT_THEME, type TenantTheme } from './config/theme';
import {
  ProtectedRoute,
  ToastProvider,
  ErrorBoundary,
  PageErrorBoundary,
  PWAPrompt,
  OfflineIndicator,
} from './components/common';
// InstallPrompt removed — PWAPrompt (via usePWA) handles both install and update notifications
// import { InstallPrompt } from './components/pwa';
import { AdminLayout } from './components/layout/AdminLayout';
import { TeacherLayout } from './components/layout/TeacherLayout';
import { StudentLayout } from './components/layout/StudentLayout';
import { SuperAdminLayout } from './components/layout/SuperAdminLayout';
import { PageShell } from './design-system/layout';
import api from './config/api';
import { useSessionLifecycle } from './hooks/useSessionLifecycle';
import { useAuthStore } from './stores/authStore';
import { useTenantStore } from './stores/tenantStore';
import { TourProvider } from './components/tour';
import { isPlatformRequest } from './utils/hostRouting';
import './assets/styles/index.css';
import 'katex/dist/katex.min.css';

// ─── Static imports (keep for fast initial load) ────────────────────────────
import { LoginPage } from './pages/auth/LoginPage';
import { PageLoader } from './components/PageLoader';

// ─── Lazy-loaded page components ────────────────────────────────────────────
// Auth
const SuperAdminLoginPage = React.lazy(() =>
  import('./pages/auth/SuperAdminLoginPage').then((m) => ({ default: m.SuperAdminLoginPage }))
);
const ForgotPasswordPage = React.lazy(() =>
  import('./pages/auth/ForgotPasswordPage').then((m) => ({ default: m.ForgotPasswordPage }))
);
const ResetPasswordPage = React.lazy(() =>
  import('./pages/auth/ResetPasswordPage').then((m) => ({ default: m.ResetPasswordPage }))
);
const VerifyEmailPage = React.lazy(() =>
  import('./pages/auth/VerifyEmailPage').then((m) => ({ default: m.VerifyEmailPage }))
);
const SSOCallbackPage = React.lazy(() =>
  import('./pages/auth/SSOCallbackPage').then((m) => ({ default: m.SSOCallbackPage }))
);
const AcceptInvitationPage = React.lazy(() =>
  import('./pages/auth/AcceptInvitationPage').then((m) => ({ default: m.AcceptInvitationPage }))
);

// Onboarding / settings
const SignupPage = React.lazy(() =>
  import('./pages/onboarding/SignupPage').then((m) => ({ default: m.SignupPage }))
);
const SecuritySettings = React.lazy(() =>
  import('./pages/settings/SecuritySettings').then((m) => ({ default: m.SecuritySettings }))
);

// Marketing
const ProductLandingPage = React.lazy(() =>
  import('./pages/marketing').then((m) => ({ default: m.ProductLandingPage }))
);

// Admin pages
const AdminDashboardPage = React.lazy(() =>
  import('./pages/admin/DashboardPage').then((m) => ({ default: m.DashboardPage }))
);
const TeachersPage = React.lazy(() =>
  import('./pages/admin/TeachersPage').then((m) => ({ default: m.TeachersPage }))
);
const CreateTeacherPage = React.lazy(() =>
  import('./pages/admin/CreateTeacherPage').then((m) => ({ default: m.CreateTeacherPage }))
);
const AdminCoursesPage = React.lazy(() =>
  import('./pages/admin/CoursesPage').then((m) => ({ default: m.CoursesPage }))
);
const CourseEditorPage = React.lazy(() =>
  import('./pages/admin/CourseEditorPage').then((m) => ({ default: m.CourseEditorPage }))
);
const AnalyticsPage = React.lazy(() =>
  import('./pages/admin/AnalyticsPage').then((m) => ({ default: m.AnalyticsPage }))
);
const SettingsPage = React.lazy(() =>
  import('./pages/admin/SettingsPage').then((m) => ({ default: m.SettingsPage }))
);
const GroupsPage = React.lazy(() =>
  import('./pages/admin/GroupsPage').then((m) => ({ default: m.GroupsPage }))
);
const RemindersPage = React.lazy(() =>
  import('./pages/admin/RemindersPage').then((m) => ({ default: m.RemindersPage }))
);
const CertificationsPage = React.lazy(() =>
  import('./pages/admin/CertificationsPage').then((m) => ({ default: m.CertificationsPage }))
);
const BillingPage = React.lazy(() =>
  import('./pages/admin/BillingPage').then((m) => ({ default: m.BillingPage }))
);
const SchoolViewPage = React.lazy(() =>
  import('./pages/admin/SchoolViewPage').then((m) => ({ default: m.SchoolViewPage }))
);
const GradeDetailPage = React.lazy(() =>
  import('./pages/admin/GradeDetailPage').then((m) => ({ default: m.GradeDetailPage }))
);
const AdminSectionDetailPage = React.lazy(() =>
  import('./pages/admin/SectionDetailPage').then((m) => ({ default: m.SectionDetailPage }))
);
const StudentsPage = React.lazy(() =>
  import('./pages/admin/StudentsPage').then((m) => ({ default: m.StudentsPage }))
);
const DirectoryPage = React.lazy(() =>
  import('./pages/admin/DirectoryPage').then((m) => ({ default: m.DirectoryPage }))
);
const AdminAttendancePage = React.lazy(() =>
  import('./pages/admin/AttendancePage').then((m) => ({ default: m.AdminAttendancePage }))
);

// Teacher pages
const TeacherDashboardPage = React.lazy(() =>
  import('./pages/teacher/DashboardPage').then((m) => ({ default: m.DashboardPage }))
);
const MyCoursesPage = React.lazy(() =>
  import('./pages/teacher/MyCoursesPage').then((m) => ({ default: m.MyCoursesPage }))
);
const CourseViewPage = React.lazy(() =>
  import('./pages/teacher/CourseViewPage').then((m) => ({ default: m.CourseViewPage }))
);
const AssignmentsPage = React.lazy(() =>
  import('./pages/teacher/AssignmentsPage').then((m) => ({ default: m.AssignmentsPage }))
);
const TeacherRemindersPage = React.lazy(() =>
  import('./pages/teacher/RemindersPage').then((m) => ({ default: m.RemindersPage }))
);
const QuizPage = React.lazy(() =>
  import('./pages/teacher/QuizPage').then((m) => ({ default: m.QuizPage }))
);
const ProfilePage = React.lazy(() =>
  import('./pages/teacher/ProfilePage').then((m) => ({ default: m.ProfilePage }))
);
const ProfessionalGrowthPage = React.lazy(() =>
  import('./pages/teacher/ProfessionalGrowthPage').then((m) => ({ default: m.ProfessionalGrowthPage }))
);
const MyCertificationsPage = React.lazy(() =>
  import('./pages/teacher/MyCertificationsPage').then((m) => ({ default: m.MyCertificationsPage }))
);
const TeacherStudyNotesPage = React.lazy(() =>
  import('./pages/teacher/TeacherStudyNotesPage').then((m) => ({ default: m.TeacherStudyNotesPage }))
);
const MyClassesPage = React.lazy(() =>
  import('./pages/teacher/MyClassesPage').then((m) => ({ default: m.MyClassesPage }))
);
const TeacherSectionDashboardPage = React.lazy(() =>
  import('./pages/teacher/SectionDashboardPage').then((m) => ({ default: m.SectionDashboardPage }))
);

// OpenMAIC Features
const DiscussionPage = React.lazy(() =>
  import('./pages/teacher/DiscussionPage').then((m) => ({ default: m.DiscussionPage }))
);
const DiscussionThreadPage = React.lazy(() =>
  import('./pages/teacher/DiscussionThreadPage').then((m) => ({ default: m.DiscussionThreadPage }))
);

// MAIC AI Classroom
const MAICLibraryPage = React.lazy(() =>
  import('./pages/teacher/MAICLibraryPage').then((m) => ({ default: m.MAICLibraryPage }))
);
const MAICCreatePage = React.lazy(() =>
  import('./pages/teacher/MAICCreatePage').then((m) => ({ default: m.MAICCreatePage }))
);
const MAICPlayerPage = React.lazy(() =>
  import('./pages/teacher/MAICPlayerPage').then((m) => ({ default: m.MAICPlayerPage }))
);
const MAICBrowsePage = React.lazy(() =>
  import('./pages/student/MAICBrowsePage').then((m) => ({ default: m.MAICBrowsePage }))
);
const StudentMAICPlayerPage = React.lazy(() =>
  import('./pages/student/MAICPlayerPage').then((m) => ({ default: m.StudentMAICPlayerPage }))
);
const StudentMAICCreatePage = React.lazy(() =>
  import('./pages/student/StudentMAICCreatePage').then((m) => ({ default: m.StudentMAICCreatePage }))
);
const StudentAttendancePage = React.lazy(() =>
  import('./pages/student/AttendancePage').then((m) => ({ default: m.StudentAttendancePage }))
);

// AI Chatbot
const ChatbotListPage = React.lazy(() =>
  import('./pages/teacher/ChatbotListPage').then((m) => ({ default: m.ChatbotListPage }))
);
const ChatbotBuilderPage = React.lazy(() =>
  import('./pages/teacher/ChatbotBuilderPage').then((m) => ({ default: m.ChatbotBuilderPage }))
);
const StudentChatbotsPage = React.lazy(() =>
  import('./pages/student/StudentChatbotsPage').then((m) => ({ default: m.StudentChatbotsPage }))
);
const StudentChatPage = React.lazy(() =>
  import('./pages/student/StudentChatPage').then((m) => ({ default: m.StudentChatPage }))
);

// Student pages
const StudentDashboardPage = React.lazy(() =>
  import('./pages/student/DashboardPage').then((m) => ({ default: m.DashboardPage }))
);
const StudentCourseListPage = React.lazy(() =>
  import('./pages/student/CourseListPage').then((m) => ({ default: m.CourseListPage }))
);
const StudentCourseViewPage = React.lazy(() =>
  import('./pages/student/CourseViewPage').then((m) => ({ default: m.CourseViewPage }))
);
const StudentAssignmentsPage = React.lazy(() =>
  import('./pages/student/AssignmentsPage').then((m) => ({ default: m.AssignmentsPage }))
);
const StudentQuizPage = React.lazy(() =>
  import('./pages/student/QuizPage').then((m) => ({ default: m.QuizPage }))
);
const StudentProfilePage = React.lazy(() =>
  import('./pages/student/ProfilePage').then((m) => ({ default: m.ProfilePage }))
);
const StudentSettingsPage = React.lazy(() =>
  import('./pages/student/SettingsPage').then((m) => ({ default: m.SettingsPage }))
);
const StudentAchievementsPage = React.lazy(() =>
  import('./pages/student/AchievementsPage').then((m) => ({ default: m.AchievementsPage }))
);
const StudyNotesPage = React.lazy(() =>
  import('./pages/student/StudyNotesPage').then((m) => ({ default: m.StudyNotesPage }))
);
const StudentDiscussionPage = React.lazy(() =>
  import('./pages/student/DiscussionPage').then((m) => ({ default: m.StudentDiscussionPage }))
);
const StudentDiscussionThreadPage = React.lazy(() =>
  import('./pages/student/DiscussionThreadPage').then((m) => ({ default: m.StudentDiscussionThreadPage }))
);
// Super Admin pages
const SuperAdminDashboardPage = React.lazy(() =>
  import('./pages/superadmin/DashboardPage').then((m) => ({ default: m.SuperAdminDashboardPage }))
);
const SuperAdminOperationsPage = React.lazy(() =>
  import('./pages/superadmin/OperationsPage').then((m) => ({ default: m.OperationsPage }))
);
const SuperAdminSchoolsPage = React.lazy(() =>
  import('./pages/superadmin/SchoolsPage').then((m) => ({ default: m.SchoolsPage }))
);
const SuperAdminSchoolDetailPage = React.lazy(() =>
  import('./pages/superadmin/SchoolDetailPage').then((m) => ({ default: m.SchoolDetailPage }))
);
const SuperAdminDemoBookingsPage = React.lazy(() =>
  import('./pages/superadmin/DemoBookingsPage').then((m) => ({ default: m.DemoBookingsPage }))
);

// ─── QueryClient ─────────────────────────────────────────────────────────────
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: (failureCount, error: any) => {
        const status = Number(error?.response?.status || 0);
        // Do not amplify auth/permission/validation failures.
        if (status >= 400 && status < 500) {
          return false;
        }
        // Single retry for transient server/network errors.
        return failureCount < 1;
      },
      staleTime: 2 * 60 * 1000, // 2 minutes — prevents cascading refetches on every mount
    },
  },
});

function getDashboardPathForRole(role?: string | null): string | null {
  if (role === 'SUPER_ADMIN') return '/super-admin/dashboard';
  if (role === 'SCHOOL_ADMIN') return '/admin/dashboard';
  if (role === 'TEACHER' || role === 'HOD' || role === 'IB_COORDINATOR') return '/teacher/dashboard';
  if (role === 'STUDENT') return '/student/dashboard';
  return null;
}

// Wrap a page element with both an ErrorBoundary and a Suspense boundary.
// The ErrorBoundary resets automatically when the URL pathname changes.
function RoutePage({ children }: { children: React.ReactNode }) {
  const { pathname } = useLocation();
  return (
    <PageErrorBoundary pathname={pathname}>
      <Suspense fallback={<PageLoader />}>
        {children}
      </Suspense>
    </PageErrorBoundary>
  );
}

function AppContent() {
  const { isAuthenticated, user, setUser, clearAuth } = useAuthStore();
  const { setConfig } = useTenantStore();
  const [authValidated, setAuthValidated] = React.useState(!isAuthenticated);
  useSessionLifecycle();
  const dashboardPath = getDashboardPathForRole(user?.role);
  const onPlatformHost = isPlatformRequest();

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
          onPlatformHost ? (
            <Navigate to="/" replace />
          ) : isAuthenticated && user && dashboardPath ? (
            <Navigate to={dashboardPath} replace />
          ) : (
            <RoutePage><LoginPage /></RoutePage>
          )
        }
      />

      {/* Public Routes — Password Reset */}
      <Route path="/forgot-password" element={<RoutePage><ForgotPasswordPage /></RoutePage>} />
      <Route path="/reset-password" element={<RoutePage><ResetPasswordPage /></RoutePage>} />
      <Route path="/verify-email" element={<RoutePage><VerifyEmailPage /></RoutePage>} />

      {/* Public Routes — SSO Callback */}
      <Route path="/auth/sso-callback" element={<RoutePage><SSOCallbackPage /></RoutePage>} />

      {/* Public Routes — Tenant Self-Service Signup */}
      <Route
        path="/signup"
        element={
          onPlatformHost ? (
            <Navigate to="/" replace />
          ) : (
            <RoutePage><SignupPage /></RoutePage>
          )
        }
      />

      {/* Public Routes — Teacher Invitation Acceptance */}
      <Route path="/accept-invitation/:token" element={<RoutePage><AcceptInvitationPage /></RoutePage>} />

      {/* Public Routes — Super Admin login (platform admin) */}
      <Route
        path="/super-admin/login"
        element={
          isAuthenticated && user ? (
            <Navigate to={getDashboardPathForRole(user.role) || '/login'} replace />
          ) : (
            <RoutePage><SuperAdminLoginPage /></RoutePage>
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
        <Route path="dashboard" element={<RoutePage><SuperAdminDashboardPage /></RoutePage>} />
        <Route path="operations" element={<RoutePage><SuperAdminOperationsPage /></RoutePage>} />
        <Route path="schools" element={<RoutePage><SuperAdminSchoolsPage /></RoutePage>} />
        <Route path="schools/:tenantId" element={<RoutePage><SuperAdminSchoolDetailPage /></RoutePage>} />
        <Route path="demo-bookings" element={<RoutePage><SuperAdminDemoBookingsPage /></RoutePage>} />
        <Route index element={<Navigate to="/super-admin/dashboard" replace />} />
        <Route path="*" element={<Navigate to="/super-admin/dashboard" replace />} />
      </Route>

      {/* Protected Admin Routes with Layout */}
      <Route
        path="/admin"
        element={
          <ProtectedRoute allowedRoles={['SCHOOL_ADMIN']}>
            <PageShell />
          </ProtectedRoute>
        }
      >
        <Route path="dashboard" element={<RoutePage><AdminDashboardPage /></RoutePage>} />
        <Route path="courses" element={<RoutePage><AdminCoursesPage /></RoutePage>} />
        <Route path="courses/new" element={<RoutePage><CourseEditorPage /></RoutePage>} />
        <Route path="certifications" element={<RoutePage><CertificationsPage /></RoutePage>} />
        <Route path="courses/:courseId/edit" element={<RoutePage><CourseEditorPage /></RoutePage>} />
        <Route path="teachers" element={<RoutePage><TeachersPage /></RoutePage>} />
        <Route path="teachers/new" element={<RoutePage><CreateTeacherPage /></RoutePage>} />
        <Route path="groups" element={<RoutePage><GroupsPage /></RoutePage>} />
        <Route path="students" element={<RoutePage><StudentsPage /></RoutePage>} />
        <Route path="directory" element={<RoutePage><DirectoryPage /></RoutePage>} />
        <Route path="reminders" element={<RoutePage><RemindersPage /></RoutePage>} />
        <Route path="school" element={<RoutePage><SchoolViewPage /></RoutePage>} />
        <Route path="school/grade/:gradeId" element={<RoutePage><GradeDetailPage /></RoutePage>} />
        <Route path="school/section/:sectionId" element={<RoutePage><AdminSectionDetailPage /></RoutePage>} />
        <Route path="attendance" element={<RoutePage><AdminAttendancePage /></RoutePage>} />
        <Route path="analytics" element={<RoutePage><AnalyticsPage /></RoutePage>} />
        <Route path="billing" element={<RoutePage><BillingPage /></RoutePage>} />
        <Route path="settings" element={<RoutePage><SettingsPage /></RoutePage>} />
        <Route path="settings/security" element={<RoutePage><SecuritySettings /></RoutePage>} />
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
        <Route path="dashboard" element={<RoutePage><TeacherDashboardPage /></RoutePage>} />
        <Route path="courses" element={<RoutePage><MyCoursesPage /></RoutePage>} />
        <Route path="courses/:courseId" element={<RoutePage><CourseViewPage /></RoutePage>} />
        <Route path="authoring" element={<RoutePage><AdminCoursesPage /></RoutePage>} />
        <Route path="authoring/new" element={<RoutePage><CourseEditorPage /></RoutePage>} />
        <Route path="authoring/:courseId/edit" element={<RoutePage><CourseEditorPage /></RoutePage>} />
        <Route path="assignments" element={<RoutePage><AssignmentsPage /></RoutePage>} />
        <Route path="reminders" element={<RoutePage><TeacherRemindersPage /></RoutePage>} />
        <Route path="quizzes/:assignmentId" element={<RoutePage><QuizPage /></RoutePage>} />
        <Route path="profile" element={<RoutePage><ProfilePage /></RoutePage>} />
        <Route path="growth" element={<RoutePage><ProfessionalGrowthPage /></RoutePage>} />
        <Route path="certifications" element={<RoutePage><MyCertificationsPage /></RoutePage>} />
        <Route path="study-notes" element={<RoutePage><TeacherStudyNotesPage /></RoutePage>} />
        {/* OpenMAIC Features */}
        <Route path="ai-classroom" element={<RoutePage><MAICLibraryPage /></RoutePage>} />
        <Route path="ai-classroom/new" element={<RoutePage><MAICCreatePage /></RoutePage>} />
        <Route path="ai-classroom/:id" element={<RoutePage><MAICPlayerPage /></RoutePage>} />
        <Route path="chatbots" element={<RoutePage><ChatbotListPage /></RoutePage>} />
        <Route path="chatbots/new" element={<RoutePage><ChatbotBuilderPage /></RoutePage>} />
        <Route path="chatbots/:id" element={<RoutePage><ChatbotBuilderPage /></RoutePage>} />
        <Route path="discussions" element={<RoutePage><DiscussionPage /></RoutePage>} />
        <Route path="discussions/:threadId" element={<RoutePage><DiscussionThreadPage /></RoutePage>} />
        <Route path="my-classes" element={<RoutePage><MyClassesPage /></RoutePage>} />
        <Route path="my-classes/section/:sectionId" element={<RoutePage><TeacherSectionDashboardPage /></RoutePage>} />
        <Route path="settings/security" element={<RoutePage><SecuritySettings /></RoutePage>} />
        <Route index element={<Navigate to="/teacher/dashboard" replace />} />
        <Route path="*" element={<Navigate to="/teacher/dashboard" replace />} />
      </Route>

      {/* Protected Student Routes with Layout */}
      <Route
        path="/student"
        element={
          <ProtectedRoute allowedRoles={['STUDENT']}>
            <StudentLayout />
          </ProtectedRoute>
        }
      >
        <Route path="dashboard" element={<RoutePage><StudentDashboardPage /></RoutePage>} />
        <Route path="courses" element={<RoutePage><StudentCourseListPage /></RoutePage>} />
        <Route path="courses/:courseId" element={<RoutePage><StudentCourseViewPage /></RoutePage>} />
        <Route path="assignments" element={<RoutePage><StudentAssignmentsPage /></RoutePage>} />
        <Route path="quizzes/:assignmentId" element={<RoutePage><StudentQuizPage /></RoutePage>} />
        <Route path="achievements" element={<RoutePage><StudentAchievementsPage /></RoutePage>} />
        <Route path="attendance" element={<RoutePage><StudentAttendancePage /></RoutePage>} />
        <Route path="study-notes" element={<RoutePage><StudyNotesPage /></RoutePage>} />
        <Route path="ai-classroom" element={<RoutePage><MAICBrowsePage /></RoutePage>} />
        <Route path="ai-classroom/new" element={<RoutePage><StudentMAICCreatePage /></RoutePage>} />
        <Route path="ai-classroom/:id" element={<RoutePage><StudentMAICPlayerPage /></RoutePage>} />
        <Route path="discussions" element={<RoutePage><StudentDiscussionPage /></RoutePage>} />
        <Route path="discussions/:threadId" element={<RoutePage><StudentDiscussionThreadPage /></RoutePage>} />
        <Route path="chatbots" element={<RoutePage><StudentChatbotsPage /></RoutePage>} />
        <Route path="chatbots/:id" element={<RoutePage><StudentChatPage /></RoutePage>} />
        <Route path="profile" element={<RoutePage><StudentProfilePage /></RoutePage>} />
        <Route path="settings" element={<RoutePage><StudentSettingsPage /></RoutePage>} />
        <Route path="settings/security" element={<RoutePage><SecuritySettings /></RoutePage>} />
        <Route index element={<Navigate to="/student/dashboard" replace />} />
        <Route path="*" element={<Navigate to="/student/dashboard" replace />} />
      </Route>

      {/* Default redirect */}
      <Route
        path="/"
        element={
          onPlatformHost ? (
            <RoutePage><ProductLandingPage /></RoutePage>
          ) : (
            <Navigate
              to={
                isAuthenticated && user && dashboardPath
                  ? dashboardPath
                  : '/login'
              }
              replace
            />
          )
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
