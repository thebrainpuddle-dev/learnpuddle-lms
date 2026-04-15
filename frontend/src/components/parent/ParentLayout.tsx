// src/components/parent/ParentLayout.tsx
//
// Minimal layout wrapper for parent dashboard.
// No sidebar — just checks authentication and renders outlet.

import { Outlet, Navigate } from 'react-router-dom';
import { useParentStore } from '../../stores/parentStore';

export function ParentLayout() {
  const isAuthenticated = useParentStore((s) => s.isAuthenticated);

  if (!isAuthenticated) {
    return <Navigate to="/parent" replace />;
  }

  return <Outlet />;
}
