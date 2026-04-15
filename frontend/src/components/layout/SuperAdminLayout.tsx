import React from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { Bars3Icon } from '@heroicons/react/24/outline';
import { SuperAdminSidebar } from './SuperAdminSidebar';
import { useGuidedTour } from '../tour';
import { ErrorBoundary } from '../common';

export const SuperAdminLayout: React.FC = () => {
  const [sidebarOpen, setSidebarOpen] = React.useState(false);
  const location = useLocation();
  const [isDesktop, setIsDesktop] = React.useState(() =>
    typeof window !== 'undefined' && typeof window.matchMedia === 'function'
      ? window.matchMedia('(min-width: 1024px)').matches
      : true,
  );
  const { isActive: isTourActive } = useGuidedTour();

  React.useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return;
    const media = window.matchMedia('(min-width: 1024px)');
    const onChange = (event: MediaQueryListEvent) => setIsDesktop(event.matches);
    setIsDesktop(media.matches);
    media.addEventListener('change', onChange);
    return () => media.removeEventListener('change', onChange);
  }, []);

  React.useEffect(() => {
    if (isDesktop && sidebarOpen) setSidebarOpen(false);
  }, [isDesktop, sidebarOpen]);

  React.useEffect(() => {
    if (!isDesktop && isTourActive) setSidebarOpen(true);
    if (!isDesktop && !isTourActive) setSidebarOpen(false);
  }, [isDesktop, isTourActive]);

  React.useEffect(() => {
    if (!isDesktop && sidebarOpen) setSidebarOpen(false);
  }, [isDesktop, location.pathname, sidebarOpen]);

  return (
    <div className="min-h-screen overflow-x-hidden bg-slate-50">
      {!isDesktop && (
        <SuperAdminSidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      )}

      <div className="hidden lg:fixed lg:inset-y-0 lg:flex lg:w-[240px] lg:flex-col">
        <SuperAdminSidebar open />
      </div>

      <div className="flex min-h-screen min-w-0 flex-1 flex-col lg:pl-[240px]">
        <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b border-slate-200/80 bg-white/80 backdrop-blur-md px-4 lg:hidden">
          <button
            type="button"
            onClick={() => setSidebarOpen(true)}
            data-tour="superadmin-mobile-menu"
            className="inline-flex items-center justify-center rounded-lg text-slate-600 hover:bg-slate-100 transition-colors p-2.5 min-h-[44px] min-w-[44px]"
            aria-label="Open navigation"
          >
            <Bars3Icon className="h-5 w-5" />
          </button>
          <span className="text-[13px] font-semibold tracking-wide text-slate-700">
            Command Center
          </span>
          <span className="w-9" />
        </header>

        <main className="min-w-0 flex-1">
          <div className="py-6 pb-16 lg:pb-6">
            <div className="mx-auto max-w-[1400px] px-4 lg:px-6">
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
