import React, { Fragment } from 'react';
import { Dialog, Transition } from '@headlessui/react';
import { NavLink } from 'react-router-dom';
import {
  XMarkIcon,
  HomeIcon,
  SignalIcon,
  BuildingOffice2Icon,
  CalendarDaysIcon,
  ArrowRightOnRectangleIcon,
  QuestionMarkCircleIcon,
} from '@heroicons/react/24/outline';
import { useAuthStore } from '../../stores/authStore';
import { broadcastLogout } from '../../utils/authSession';
import { useGuidedTour } from '../tour';

const navItems = [
  { to: '/super-admin/dashboard', label: 'Dashboard', icon: HomeIcon, tourId: 'superadmin-nav-dashboard' },
  { to: '/super-admin/operations', label: 'Operations', icon: SignalIcon, tourId: 'superadmin-nav-operations' },
  { to: '/super-admin/schools', label: 'Schools', icon: BuildingOffice2Icon, tourId: 'superadmin-nav-schools' },
  { to: '/super-admin/demo-bookings', label: 'Demo Bookings', icon: CalendarDaysIcon, tourId: 'superadmin-nav-demo-bookings' },
];

interface SuperAdminSidebarProps {
  open: boolean;
  onClose?: () => void;
}

export const SuperAdminSidebar: React.FC<SuperAdminSidebarProps> = ({ open, onClose }) => {
  const { clearAuth } = useAuthStore();
  const { startTour } = useGuidedTour();

  const SidebarContent = () => (
    <aside
      data-tour="superadmin-sidebar"
      className="flex h-full w-full flex-col bg-slate-900 text-white"
    >
      {/* Brand */}
      <div className="flex h-[60px] items-center justify-between border-b border-slate-800/80 px-5">
        <div className="flex items-center gap-2.5">
          <div className="h-7 w-7 rounded-lg bg-gradient-to-br from-indigo-500 to-violet-500 flex items-center justify-center shadow-sm">
            <span className="text-white font-bold text-[11px]">LP</span>
          </div>
          <span className="text-[15px] font-semibold tracking-tight">Command Center</span>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            className="text-slate-500 hover:text-white lg:hidden transition-colors"
            aria-label="Close navigation"
          >
            <XMarkIcon className="h-5 w-5" />
          </button>
        )}
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-0.5 overflow-y-auto">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            data-tour={item.tourId}
            onClick={() => onClose?.()}
            className={({ isActive }) =>
              `relative flex items-center gap-2.5 px-3 py-[9px] rounded-lg text-[13px] font-medium transition-all duration-150 ${
                isActive
                  ? 'bg-slate-800 text-white'
                  : 'text-slate-400 hover:bg-slate-800/60 hover:text-slate-200'
              }`
            }
          >
            {({ isActive }) => (
              <>
                {isActive && (
                  <span className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-4 rounded-r-full bg-indigo-400" />
                )}
                <item.icon className={`h-[18px] w-[18px] flex-shrink-0 ${isActive ? 'text-indigo-400' : ''}`} />
                {item.label}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="p-3 border-t border-slate-800/80 space-y-0.5">
        <button
          type="button"
          onClick={startTour}
          data-tour="superadmin-tour-replay"
          className="flex items-center gap-2.5 w-full px-3 py-[9px] rounded-lg text-[13px] font-medium text-slate-400 hover:bg-slate-800/60 hover:text-slate-200 transition-colors"
        >
          <QuestionMarkCircleIcon className="h-[18px] w-[18px]" />
          Start Tour
        </button>
        <button
          onClick={() => {
            broadcastLogout('manual_logout');
            clearAuth();
            window.location.href = '/super-admin/login';
          }}
          className="flex items-center gap-2.5 w-full px-3 py-[9px] rounded-lg text-[13px] font-medium text-slate-400 hover:bg-red-500/10 hover:text-red-400 transition-colors"
        >
          <ArrowRightOnRectangleIcon className="h-[18px] w-[18px]" />
          Sign out
        </button>
      </div>
    </aside>
  );

  if (onClose) {
    return (
      <Transition.Root show={open} as={Fragment}>
        <Dialog as="div" className="relative z-50 lg:hidden" onClose={onClose}>
          <Transition.Child
            as={Fragment}
            enter="transition-opacity ease-linear duration-300"
            enterFrom="opacity-0"
            enterTo="opacity-100"
            leave="transition-opacity ease-linear duration-300"
            leaveFrom="opacity-100"
            leaveTo="opacity-0"
          >
            <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-[2px]" />
          </Transition.Child>

          <div className="fixed inset-0 flex">
            <Transition.Child
              as={Fragment}
              enter="transition ease-in-out duration-300 transform"
              enterFrom="-translate-x-full"
              enterTo="translate-x-0"
              leave="transition ease-in-out duration-300 transform"
              leaveFrom="translate-x-0"
              leaveTo="-translate-x-full"
            >
              <Dialog.Panel className="relative mr-16 flex w-[260px] flex-1">
                <SidebarContent />
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </Dialog>
      </Transition.Root>
    );
  }

  return <SidebarContent />;
};
