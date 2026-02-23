// src/components/layout/TeacherLayout.tsx

import React from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { TeacherSidebar } from './TeacherSidebar';
import { TeacherHeader } from './TeacherHeader';

export const TeacherLayout: React.FC = () => {
  const location = useLocation();
  const [sidebarOpen, setSidebarOpen] = React.useState(false);
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
  }, [location.pathname, isDesktop, sidebarOpen]);

  return (
    <div className="min-h-screen overflow-x-hidden bg-gray-50">
      {/* Mobile sidebar */}
      {!isDesktop && <TeacherSidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />}
      
      {/* Desktop sidebar */}
      <div className="hidden lg:fixed lg:inset-y-0 lg:flex lg:w-64 lg:flex-col">
        <TeacherSidebar open={true} />
      </div>
      
      {/* Main content */}
      <div className="flex min-w-0 flex-1 flex-col lg:pl-64">
        <TeacherHeader onMenuClick={() => setSidebarOpen(true)} />
        
        <main className="flex-1 min-w-0">
          <div className="py-4 sm:py-6">
            <div className="mx-auto max-w-7xl px-3 sm:px-6 md:px-8">
              <Outlet />
            </div>
          </div>
        </main>
      </div>
    </div>
  );
};
