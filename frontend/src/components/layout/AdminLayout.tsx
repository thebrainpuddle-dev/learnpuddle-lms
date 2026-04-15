// src/components/layout/AdminLayout.tsx

import React from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { AdminSidebar } from './AdminSidebar';
import { AdminHeader } from './AdminHeader';
import { ErrorBoundary } from '../common';

export const AdminLayout: React.FC = () => {
  const [sidebarOpen, setSidebarOpen] = React.useState(false);
  const location = useLocation();
  const [isDesktop, setIsDesktop] = React.useState(() =>
    typeof window !== 'undefined' && typeof window.matchMedia === 'function'
      ? window.matchMedia('(min-width: 1024px)').matches
      : true
  );

  React.useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      return;
    }
    const media = window.matchMedia('(min-width: 1024px)');
    const onChange = (event: MediaQueryListEvent) => setIsDesktop(event.matches);
    setIsDesktop(media.matches);

    if (media.addEventListener) {
      media.addEventListener('change', onChange);
      return () => media.removeEventListener('change', onChange);
    }

    media.addListener(onChange);
    return () => media.removeListener(onChange);
  }, []);

  React.useEffect(() => {
    if (isDesktop && sidebarOpen) {
      setSidebarOpen(false);
    }
  }, [isDesktop, sidebarOpen]);

  React.useEffect(() => {
    if (!isDesktop && sidebarOpen) {
      setSidebarOpen(false);
    }
    // close mobile drawer whenever route changes
  }, [isDesktop, location.pathname, sidebarOpen]);

  return (
    <div className="min-h-screen overflow-x-hidden bg-gray-50">
      {/* Mobile sidebar */}
      {!isDesktop && <AdminSidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />}
      
      {/* Desktop sidebar */}
      <div className="hidden lg:fixed lg:inset-y-0 lg:flex lg:w-[240px] lg:flex-col">
        <AdminSidebar open={true} />
      </div>
      
      {/* Main content */}
      <div className="flex min-w-0 flex-1 flex-col lg:pl-[240px]">
        <AdminHeader onMenuClick={() => setSidebarOpen(true)} />
        
        <main className="flex-1 min-w-0">
          <div className="py-4 sm:py-6">
            <div className="mx-auto max-w-[1400px] px-3 sm:px-6 md:px-8">
              <ErrorBoundary>
                <Outlet />
              </ErrorBoundary>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
};
