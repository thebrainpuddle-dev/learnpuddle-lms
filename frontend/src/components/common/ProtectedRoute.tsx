// src/components/common/ProtectedRoute.tsx

import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuthStore } from '../../stores/authStore';

interface ProtectedRouteProps {
  children: React.ReactNode;
  allowedRoles?: string[];
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
    // Wrong role - redirect to appropriate dashboard
    if (user.role === 'SUPER_ADMIN') {
      return <Navigate to="/super-admin/dashboard" replace />;
    } else if (user.role === 'SCHOOL_ADMIN') {
      return <Navigate to="/admin/dashboard" replace />;
    } else {
      return <Navigate to="/teacher/dashboard" replace />;
    }
  }
  
  return <>{children}</>;
};
