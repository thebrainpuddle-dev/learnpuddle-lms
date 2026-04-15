// src/components/layout/StudentLayout.tsx
//
// Light layout for student portal: white sidebar + main content.

import React from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { StudentSidebar } from './StudentSidebar';
import { StudentHeader } from './StudentHeader';
import { ErrorBoundary } from '../common';
import { StudentMobileBottomNav } from './StudentMobileBottomNav';

export const StudentLayout: React.FC = () => {
  const location = useLocation();
  const [sidebarOpen, setSidebarOpen] = React.useState(false);
  const [isDesktop, setIsDesktop] = React.useState(() =>
    typeof window !== 'undefined' && typeof window.matchMedia === 'function'
      ? window.matchMedia('(min-width: 1024px)').matches
      : true,
  );

  React.useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return;
    const media = window.matchMedia('(min-width: 1024px)');
    const onChange = (e: MediaQueryListEvent) => setIsDesktop(e.matches);
    setIsDesktop(media.matches);
    media.addEventListener('change', onChange);
    return () => media.removeEventListener('change', onChange);
  }, []);

  // Close mobile sidebar on route change
  React.useEffect(() => {
    if (!isDesktop && sidebarOpen) setSidebarOpen(false);
  }, [location.pathname]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="min-h-screen bg-tp-bg overflow-x-hidden">
      {/* Mobile sidebar drawer */}
      {!isDesktop && (
        <StudentSidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      )}

      {/* Desktop sidebar */}
      <div className="hidden lg:fixed lg:inset-y-0 lg:flex lg:w-[240px] lg:flex-col">
        <StudentSidebar open={true} />
      </div>

      {/* Main content area */}
      <div className="flex min-w-0 flex-1 flex-col lg:pl-[240px]">
        <StudentHeader onMenuClick={() => setSidebarOpen(true)} />

        <main className="flex-1 min-w-0">
          <div className="py-6 pb-16 lg:pb-6">
            <div className="mx-auto max-w-[1400px] px-4 lg:px-6">
              <ErrorBoundary>
                <Outlet />
              </ErrorBoundary>
            </div>
          </div>
        </main>
      </div>

      {/* Mobile bottom tab bar */}
      <StudentMobileBottomNav />
    </div>
  );
};
