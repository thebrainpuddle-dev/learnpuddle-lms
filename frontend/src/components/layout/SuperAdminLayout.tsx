import React from 'react';
import { Outlet } from 'react-router-dom';
import { Bars3Icon } from '@heroicons/react/24/outline';
import { SuperAdminSidebar } from './SuperAdminSidebar';
import { useGuidedTour } from '../tour';

export const SuperAdminLayout: React.FC = () => {
  const [sidebarOpen, setSidebarOpen] = React.useState(false);
  const [isDesktop, setIsDesktop] = React.useState(() =>
    typeof window !== 'undefined' && typeof window.matchMedia === 'function'
      ? window.matchMedia('(min-width: 1024px)').matches
      : true
  );
  const { isActive: isTourActive } = useGuidedTour();

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
    if (!isDesktop && isTourActive) {
      setSidebarOpen(true);
    }
    if (!isDesktop && !isTourActive) {
      setSidebarOpen(false);
    }
  }, [isDesktop, isTourActive]);

  return (
    <div className="min-h-screen bg-slate-50">
      {!isDesktop && <SuperAdminSidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />}

      <div className="hidden lg:fixed lg:inset-y-0 lg:flex lg:w-64 lg:flex-col">
        <SuperAdminSidebar open />
      </div>

      <div className="flex min-h-screen min-w-0 flex-1 flex-col lg:pl-64">
        <header className="sticky top-0 z-20 flex h-16 items-center justify-between border-b border-slate-200 bg-white/95 px-4 backdrop-blur lg:hidden">
          <button
            type="button"
            onClick={() => setSidebarOpen(true)}
            data-tour="superadmin-mobile-menu"
            className="inline-flex h-10 w-10 items-center justify-center rounded-lg text-slate-700 hover:bg-slate-100"
            aria-label="Open navigation"
          >
            <Bars3Icon className="h-6 w-6" />
          </button>
          <span className="text-sm font-semibold tracking-wide text-slate-900">Command Center</span>
          <span className="w-10" />
        </header>

        <main className="flex-1 min-w-0 px-4 py-4 sm:px-6 sm:py-6 lg:px-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
};
