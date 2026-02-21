// src/components/common/ProtectedRoute.tsx

import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuthStore } from '../../stores/authStore';

interface ProtectedRouteProps {
  children: React.ReactNode;
  allowedRoles?: string[];
}

function getDashboardPathForRole(role?: string | null): string | null {
  if (role === 'SUPER_ADMIN') return '/super-admin/dashboard';
  if (role === 'SCHOOL_ADMIN') return '/admin/dashboard';
  if (role === 'TEACHER' || role === 'HOD' || role === 'IB_COORDINATOR') return '/teacher/dashboard';
  return null;
}

export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({
  children,
  allowedRoles,
}) => {
  const { isAuthenticated, user } = useAuthStore();
  const location = useLocation();
  
  // Not authenticated - redirect to the correct login page
  if (!isAuthenticated || !user) {
    const loginPath = location.pathname.startsWith('/super-admin')
      ? '/super-admin/login'
      : '/login';
    return <Navigate to={loginPath} state={{ from: location }} replace />;
  }
  
  // Check role if specified
  if (allowedRoles && !allowedRoles.includes(user.role)) {
    // Wrong/unknown role - redirect safely without self-redirect loops.
    const fallbackPath = getDashboardPathForRole(user.role) || '/login';
    if (fallbackPath === location.pathname) {
      const loginPath = location.pathname.startsWith('/super-admin')
        ? '/super-admin/login'
        : '/login';
      return <Navigate to={loginPath} replace />;
    }
    return <Navigate to={fallbackPath} replace />;
  }
  
  return <>{children}</>;
};
